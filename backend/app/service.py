"""Conversation orchestrator: NLU -> profile update -> recommender -> grounded reply.

The recommender is the only component that decides *which* movies are returned. Claude (when
available) interprets the message and phrases the reply; with no key or on any failure the
rule-based parser and template replies take over and the app keeps working.
"""

from __future__ import annotations

import logging
import threading
import re
from collections.abc import Callable
from dataclasses import asdict

from .catalog import Catalog, normalize_text
from .engine.recommender import Query, Recommender, Recommendation
from .llm import ClaudeService, LLMUnavailable
from .nlp.spell import MAX_TOKENS, SpellCorrector, tokenize
from .nlp.spell_eval import build_corpus
from .nlu import ResolvedPreferences, mood_exclusions, parse_with_rules, resolve_preferences
from .schemas import (
    ChatResponse,
    CompareColumn,
    CompareResponse,
    FeedbackRequest,
    LLMStatus,
    MovieCard,
    Preferences,
    ProfileUpdate,
    RecommendRequest,
    ReasonOut,
    TasteProfile,
)
from .sessions import Session, SessionStore, Turn

log = logging.getLogger("rs.service")

HELP_REPLY = (
    "I recommend movies from the MovieLens dataset using three real techniques: popularity, content similarity "
    "(genres, tags, titles) and collaborative filtering from other people's ratings. Tell me what you like "
    "(\"I loved Inception\"), a mood or genre (\"a lighthearted comedy\"), things to avoid (\"no horror\"), "
    "or react to a card with like/dislike and I'll adapt."
)
EMPTY_REPLY = (
    "I couldn't find movies that match all of those filters. Try dropping a genre exclusion, lowering the minimum rating, "
    "or widening the years."
)


Emit = Callable[[dict], None]


def _emit(emit: Emit | None, **event) -> None:
    """Report a REAL milestone of the turn (used by the streaming endpoints). A misbehaving listener must never break a turn."""
    if emit is None:
        return
    try:
        emit(event)
    except Exception:  # noqa: BLE001
        log.debug("progress listener failed", exc_info=True)


# Words that mean "a bare title was NOT typed": greetings and chit-chat must never be turned into a movie
CHAT_WORDS = {"hi", "hello", "hey", "yo", "sup", "thanks", "thank", "you", "ok", "okay", "yes", "no", "yeah", "nope", "help", "bye", "goodbye", "what", "why",
              "how", "who", "when", "where", "cool", "nice", "good", "great", "wow", "please", "sorry", "lol", "hmm", "hm", "test", "testing", "a", "the", "i", "me", "it"}
FILLER_FIRST_WORDS = {"movie", "film"}


class ChatService:
    def __init__(self, catalog: Catalog, recommender: Recommender, sessions: SessionStore, claude: ClaudeService, max_results: int = 12) -> None:
        self.catalog = catalog
        self.rec = recommender
        self.sessions = sessions
        self.claude = claude
        self.max_results = max_results
        self._genres = set(catalog.all_genres)
        self._ids = set(catalog.index_by_id)
        self._spell: SpellCorrector | None = None
        self._spell_lock = threading.Lock()

    # ------------------------------------------------------------------ spelling repair (the NLP Lab's corrector, used inside the chat)
    @property
    def spell(self) -> SpellCorrector:
        with self._spell_lock:
            if self._spell is None:
                titles, extra = build_corpus(self.catalog)
                self._spell = SpellCorrector(titles, extra)
            return self._spell

    def _repair_title(self, text: str) -> int | None:
        """A title that did not match: fix its spelling, then accept only a (near-)exact catalogue title. Never guesses loosely."""
        tokens = tokenize(text)[:MAX_TOKENS]
        if not tokens or len(tokens) > 8:
            return None
        fixed = self.spell.correct(tokens)["corrected"]
        if fixed == " ".join(tokens):
            return None
        match = self.catalog.resolve_title(fixed, min_score=0.95)
        return match.movie_id if match else None

    def _bare_title(self, message: str) -> tuple[int, bool] | None:
        """The whole message is just a movie title (typos allowed), e.g. 'jordfather'. Returns (movie id, was it spelling-repaired)."""
        tokens = [t for i, t in enumerate(tokenize(message)) if not (i == 0 and t in FILLER_FIRST_WORDS)]
        if not tokens or len(tokens) > 8 or set(tokens) <= CHAT_WORDS:
            return None
        direct = self.catalog.resolve_title(" ".join(tokens), min_score=0.95)
        if direct:
            return direct.movie_id, False
        repaired = self._repair_title(" ".join(tokens))
        return (repaired, True) if repaired is not None else None

    # ------------------------------------------------------------------ public API
    def chat(self, session_id: str, message: str, emit: Emit | None = None) -> ChatResponse:
        session = self.sessions.get(session_id)
        message = message.strip()
        _emit(emit, event="step", step="interpret")
        prefs, mode, reason = self._interpret(message, session)
        resolved = resolve_preferences(prefs, self.catalog, rescue=self._repair_title)
        notes: list[str] = []
        changes: list[str] = []
        intent = prefs.intent
        nothing_recognised = not (resolved.genres or resolved.liked_ids or resolved.anchor_ids or resolved.disliked_ids or resolved.excluded_genres or prefs.mood
                                  or prefs.min_rating is not None or prefs.year_min is not None or prefs.year_max is not None)
        if intent in ("chitchat", "recommend") and nothing_recognised:
            # a message that is only a movie title is a request for that movie, whatever the language model labelled it (models are inconsistent here)
            bare = self._bare_title(message)
            if bare is not None:
                resolved.liked_ids = [bare[0]]
                if bare[1]:
                    resolved.corrections.append((message[:120], bare[0]))
                intent = prefs.intent = "recommend"
        for typed, mid in resolved.corrections:
            movie = self.catalog.get(mid)
            if movie:
                notes.append(f"I read \u201c{typed.strip()[:60]}\u201d as {movie.title}{f' ({movie.year})' if movie.year else ''}.")

        if intent == "reset":
            session = self.sessions.reset(session_id, keep_profile=False)
            return self._simple(session, "Fresh start - your taste profile and history are cleared. What are you in the mood for?", intent, mode, reason, suggestions=self._starter_suggestions())
        if intent == "help":
            return self._simple(session, HELP_REPLY, intent, mode, reason, suggestions=self._starter_suggestions())
        if intent == "chitchat" and not (resolved.genres or resolved.liked_ids or resolved.anchor_ids):
            return self._simple(session, "Happy to help! Tell me a genre, a mood, or a movie you loved and I'll find something.", intent, mode, reason, suggestions=self._starter_suggestions())

        if intent == "explain":
            return self._explain(session, message, prefs, mode, reason, emit)

        anchors = list(resolved.anchor_ids)
        if intent == "reject_last":
            rejected = [i for i in session.last_ids if i not in session.profile.disliked_ids]
            for mid in rejected:
                SessionStore.apply_feedback(session, mid, "dislike")
            if rejected:
                changes.append(f"Marked the last {len(rejected)} picks as not for you.")
            session.profile.novelty = min(0.8, session.profile.novelty + 0.25)
            changes.append("Shifted toward more varied picks.")
        if intent == "similar" and not anchors:
            target = self._ordinal_target(session, prefs.ordinal_reference)
            if target is not None:
                anchors = [target]
            elif not (resolved.liked_ids or session.profile.liked_ids):
                return self._simple(
                    session,
                    "Which movie should I use as the starting point? Name one, or like a card and I'll build from it.",
                    intent, mode, reason, suggestions=["More like Inception", "More like Toy Story", "More like The Godfather"],
                )

        changes += self._apply_message_to_profile(session, prefs, resolved)
        if resolved.unsupported:
            notes.append("MovieLens has no runtime data, so I couldn't filter by length.")
        for item in [u for u in prefs.unsupported if not re.search(r"runtime|minute|hour|length|long|short", u, re.I)][:3]:
            notes.append(f"I can't apply \u201c{item.strip()[:60]}\u201d because MovieLens has no data for it.")
        return self._respond(session, message, intent, mode, reason, notes, changes, anchors, resolved, count=prefs.count, emit=emit)

    def recommend(self, req: RecommendRequest, emit: Emit | None = None) -> ChatResponse:
        session = self.sessions.get(req.session_id)
        anchors: list[int] = []
        message = "Show me some picks"
        if req.anchor_movie_id is not None:
            movie = self.catalog.get(req.anchor_movie_id)
            if movie is None:
                raise KeyError(req.anchor_movie_id)
            anchors = [movie.movie_id]
            message = f"More like {movie.title}"
        if req.fresh:
            session.shown_ids = []
        resolved = ResolvedPreferences(prefs=Preferences(intent="similar" if anchors else "recommend"))
        mode = "claude" if self.claude.enabled else "fallback"
        return self._respond(
            session, message, "similar" if anchors else "recommend", mode,
            None if self.claude.enabled else "No Anthropic API key configured.", [], [], anchors, resolved, count=req.count, emit=emit,
        )

    COMPARE_ORDER = ("popular", "content", "collaborative", "hybrid")

    def compare(self, session_id: str, count: int = 5, anchor_movie_id: int | None = None) -> CompareResponse:
        """Rank the SAME request with every strategy. Read-only: it does not touch the session's history or shown movies."""
        session = self.sessions.get(session_id)
        anchors: list[int] = []
        if anchor_movie_id is not None:
            if self.catalog.get(anchor_movie_id) is None:
                raise KeyError(anchor_movie_id)
            anchors = [anchor_movie_id]
        columns: dict[str, CompareColumn] = {}
        for strategy in self.COMPARE_ORDER:
            query = self._query(session, anchors, [] if anchors else None, count)
            query.strategy = strategy
            query.exclude_ids = set()  # comparing: previously shown movies stay eligible (liked/disliked are still excluded)
            result = self.rec.rank(query)
            columns[strategy] = CompareColumn(
                strategy_used=result.strategy_used,
                notes=result.notes,
                regime=result.regime if strategy == "hybrid" else None,
                movies=[self._card(r, session) for r in result.recommendations],
            )
        p = session.profile
        return CompareResponse(
            columns=columns,
            signals={
                "liked": len(p.liked_ids) + len(anchors),
                "disliked": len(p.disliked_ids),
                "genres": list(p.genres),
                "excluded_genres": list(p.excluded_genres),
            },
        )

    def update_profile(self, session_id: str, update: ProfileUpdate) -> TasteProfile:
        session = self.sessions.get(session_id)
        self.sessions.apply_update(session, update, self._genres, self._ids)
        self.sessions.save(session)
        return session.profile

    def feedback(self, req: FeedbackRequest) -> TasteProfile:
        if req.movie_id not in self._ids:
            raise KeyError(req.movie_id)
        session = self.sessions.get(req.session_id)
        SessionStore.apply_feedback(session, req.movie_id, req.action)
        for card in session.last_cards:  # keep the stored cards consistent with the profile
            if card["movie_id"] == req.movie_id:
                card["feedback"] = None if req.action == "clear" else req.action
        self.sessions.save(session)
        return session.profile

    # ------------------------------------------------------------------ NLU
    def _context(self, session: Session) -> str:
        p = session.profile
        title = lambda ids: ", ".join(self.catalog.get(i).title for i in ids[-6:] if self.catalog.get(i)) or "none"
        last = "\n".join(f"{n}. {self.catalog.get(i).title}" for n, i in enumerate(session.last_ids, 1) if self.catalog.get(i)) or "none"
        recent = "\n".join(f"{t.role}: {t.text[:160]}" for t in session.history[-4:]) or "none"
        return (
            f"Last shown movies (numbered):\n{last}\nProfile - liked: {title(p.liked_ids)}; disliked: {title(p.disliked_ids)}; "
            f"genres: {', '.join(p.genres) or 'none'}; excluded: {', '.join(p.excluded_genres) or 'none'}\nRecent turns:\n{recent}"
        )

    def _interpret(self, message: str, session: Session) -> tuple[Preferences, str, str | None]:
        if not self.claude.enabled:
            return parse_with_rules(message, self.catalog), "fallback", "No Anthropic API key configured."
        try:
            return self.claude.parse(message, self.catalog.all_genres, self._context(session)), "claude", None
        except LLMUnavailable as exc:
            log.info("claude parse unavailable: %s", exc.reason)
            return parse_with_rules(message, self.catalog), "fallback", exc.reason

    # ------------------------------------------------------------------ profile changes
    def _apply_message_to_profile(self, session: Session, prefs: Preferences, r: ResolvedPreferences) -> list[str]:
        p = session.profile
        changes: list[str] = []
        title = lambda i: self.catalog.get(i).title
        for mid in r.liked_ids:
            if mid not in p.liked_ids:
                SessionStore.apply_feedback(session, mid, "like")
                changes.append(f"Added {title(mid)} to your liked movies.")
        for mid in r.disliked_ids:
            if mid not in p.disliked_ids:
                SessionStore.apply_feedback(session, mid, "dislike")
                changes.append(f"Added {title(mid)} to your disliked movies.")
        for g in r.excluded_genres:
            if g not in p.excluded_genres:
                p.excluded_genres.append(g)
                changes.append(f"Excluding {g}.")
        p.genres = [g for g in p.genres if g not in p.excluded_genres]
        if prefs.intent not in ("similar", "reject_last") and not r.genres and (r.liked_ids or r.anchor_ids) and p.genres:
            p.genres = []
            changes.append("Cleared the genre focus so picks follow the movies you named.")
        if prefs.intent != "similar" and r.genres and set(r.genres) != set(p.genres):
            p.genres = r.genres[:6]
            changes.append(f"Focus genres: {', '.join(p.genres)}.")
            # a new topic starts fresh on the soft constraints so old ones don't silently carry over
            if prefs.year_min is None and prefs.year_max is None:
                p.year_min = p.year_max = None
            if prefs.min_rating is None:
                p.min_rating = None
        if prefs.min_rating is not None and prefs.min_rating != p.min_rating:
            p.min_rating = prefs.min_rating
            changes.append(f"Minimum MovieLens rating: {prefs.min_rating:.1f}.")
        if prefs.year_min is not None or prefs.year_max is not None:
            p.year_min, p.year_max = prefs.year_min, prefs.year_max
            changes.append(f"Years: {p.year_min or 'any'}-{p.year_max or 'any'}.")
        if prefs.novelty is not None and prefs.novelty != p.novelty:
            p.novelty = prefs.novelty
            changes.append("Leaning toward hidden gems." if prefs.novelty > 0.6 else "Leaning toward popular picks.")
        return changes

    # ------------------------------------------------------------------ core pipeline
    def _query(self, session: Session, anchors: list[int], genres_override: list[str] | None, count: int | None, mood_excl: list[str] | None = None) -> Query:
        p = session.profile
        return Query(
            strategy=p.strategy,
            liked=list(p.liked_ids),
            disliked=list(p.disliked_ids),
            anchors=anchors,
            genres=list(p.genres) if genres_override is None else genres_override,
            excluded_genres=list(dict.fromkeys([*p.excluded_genres, *(mood_excl or [])])),
            min_rating=p.min_rating,
            year_min=p.year_min,
            year_max=p.year_max,
            novelty=p.novelty,
            exclude_ids=set(session.shown_ids),
            k=min(count or p.result_count, self.max_results),
        )

    def _respond(self, session, message, intent, mode, reason, notes, changes, anchors, resolved, count, emit: Emit | None = None) -> ChatResponse:
        genres_override = [] if (intent == "similar" and anchors and not resolved.genres) else None
        mood_excl = [g for g in mood_exclusions(resolved.prefs.mood, self.catalog.all_genres) if g not in session.profile.genres and g not in resolved.genres]
        if mood_excl:
            notes.append(f"Because you asked for a {resolved.prefs.mood} mood, I left out {', '.join(mood_excl)} for this request.")
        if intent == "reject_last" and session.profile.genres:
            notes.append(f"Still staying within {', '.join(session.profile.genres)} - tell me if you want a different genre.")
        _emit(emit, event="step", step="rank", strategy=session.profile.strategy)
        result = self.rec.rank(self._query(session, anchors, genres_override, count, mood_excl))
        if not result.recommendations and session.shown_ids:
            session.shown_ids = []  # nothing new left: allow repeats rather than returning an empty page
            result = self.rec.rank(self._query(session, anchors, genres_override, count, mood_excl))
            if result.recommendations:
                notes.append("I've shown most of the matching movies already, so some may repeat.")
        notes = notes + result.notes
        cards = [self._card(r, session) for r in result.recommendations]
        session.shown_ids += [c.movie_id for c in cards]
        session.last_ids = [c.movie_id for c in cards]
        session.last_cards = [c.model_dump() for c in cards]

        # the picks are final here: send them right away so the UI can show them while the reply is still being written
        _emit(emit, event="cards", intent=intent, cards=[c.model_dump() for c in cards], notes=notes, changes=changes,
              unresolved=resolved.unresolved_titles, strategy_used=result.strategy_used, profile=session.profile.model_dump())
        _emit(emit, event="step", step="write")
        reply, suggestions, llm_reason = self._compose(session, message, intent, cards, notes, anchors, mode)
        if llm_reason:
            reason = reason or llm_reason
        session.history += [Turn(role="user", text=message[:300]), Turn(role="assistant", text=reply[:300])]
        self.sessions.save(session)
        return ChatResponse(
            reply=reply,
            intent=intent,
            recommendations=cards,
            notes=notes,
            suggestions=suggestions,
            profile=session.profile,
            strategy_used=result.strategy_used,
            llm=LLMStatus(mode=mode, reason=reason),
            unresolved_titles=resolved.unresolved_titles,
            changes=changes,
        )

    def _card(self, r: Recommendation, session: Session) -> MovieCard:
        p = session.profile
        feedback = "like" if r.movie_id in p.liked_ids else "dislike" if r.movie_id in p.disliked_ids else None
        d = asdict(r)
        d["reasons"] = [ReasonOut(**x) for x in d["reasons"]]
        return MovieCard(**d, feedback=feedback)

    # ------------------------------------------------------------------ replies
    def _ordinal_target(self, session: Session, ordinal: int | None) -> int | None:
        if ordinal is None or not session.last_ids:
            return None
        idx = len(session.last_ids) - 1 if ordinal == -1 else ordinal - 1
        return session.last_ids[idx] if 0 <= idx < len(session.last_ids) else None

    def _explain(self, session: Session, message: str, prefs: Preferences, mode: str, reason: str | None, emit: Emit | None = None) -> ChatResponse:
        if not session.last_cards:
            return self._simple(session, "I haven't recommended anything yet - ask for a genre or a movie you like and I'll explain each pick.", "explain", mode, reason, suggestions=self._starter_suggestions())
        target = self._ordinal_target(session, prefs.ordinal_reference)
        cards = [c for c in session.last_cards if c["movie_id"] == target] if target else session.last_cards[:3]
        facts = {
            "intent": "explain",
            "recommendations": [{"title": c["title"], "year": c["year"], "reasons": [x["text"] for x in c["reasons"]], "confidence": c["confidence"]} for c in cards],
            "context": [c["title"] for c in session.last_cards],
        }
        reply, llm_reason = None, None
        suggestions: list[str] = []
        _emit(emit, event="step", step="write")
        if mode == "claude":
            try:
                reply, suggestions = self.claude.compose(message, facts)
                allowed = {normalize_text(c["title"]) for c in cards}
                self._reject_strays(reply + " " + " ".join(suggestions), allowed | {normalize_text(t) for t in facts["context"]})
            except LLMUnavailable as exc:
                reply, suggestions = None, []
                llm_reason = exc.reason
        if reply is None:
            reply = " ".join(f"{c['title']}: " + " ".join(x["text"] for x in c["reasons"][:3]) for c in cards)
        suggestions = suggestions or [f"More like {cards[0]['title']}", "Something less mainstream", "Show highly rated ones"]
        return self._simple(session, reply, "explain", mode, reason or llm_reason, suggestions=suggestions, cards=[MovieCard(**c) for c in session.last_cards])

    def _compose(self, session, message, intent, cards, notes, anchors, mode) -> tuple[str, list[str], str | None]:
        if not cards:
            return EMPTY_REPLY, ["Remove my filters", "Show popular movies", "Try a different genre"], None
        facts = {
            "intent": intent,
            "recommendations": [
                {"title": c.title, "year": c.year, "genres": c.genres, "movielens_average_rating": c.mean_rating,
                 "number_of_ratings": c.n_ratings, "reasons": [x.text for x in c.reasons], "confidence": c.confidence}
                for c in cards
            ],
            "context": [self.catalog.get(i).title for i in anchors if self.catalog.get(i)]
            + [self.catalog.get(i).title for i in session.profile.liked_ids[-5:] if self.catalog.get(i)],
            "active_filters": {"genres": session.profile.genres, "excluded_genres": session.profile.excluded_genres,
                               "min_rating": session.profile.min_rating, "years": [session.profile.year_min, session.profile.year_max]},
            "notes": notes,
        }
        if mode == "claude":
            try:
                reply, follow_ups = self.claude.compose(message, facts)
                # recommendation replies may only name movies the USER mentioned; the cards carry everything else
                self._reject_strays(reply + " " + " ".join(follow_ups), {normalize_text(t) for t in facts["context"]})
                top = cards[0]
                why = top.reasons[0].text if top.reasons else ""
                reply = f"{reply.rstrip()} Top pick: {top.title} ({top.year}). {why}".strip()  # from the engine, never from Claude
                return reply, follow_ups or self._follow_ups(cards, anchors), None
            except LLMUnavailable as exc:
                return self._template(cards, anchors, session), self._follow_ups(cards, anchors), f"Reply written locally: {exc.reason}"
        return self._template(cards, anchors, session), self._follow_ups(cards, anchors), None

    def _reject_strays(self, text: str, allowed: set[str]) -> None:
        """Reject a reply that names a catalogue movie outside ``allowed`` (the facts we supplied).

        A movie reference is capitalised; the same letters used as an ordinary lowercase word ("storytelling") or as the
        first word of a sentence are not treated as a title, so common words that happen to be titles don't cause false alarms.
        """
        for m in self.catalog.find_titles_in_text(text):
            if normalize_text(m.title) in allowed:
                continue
            hit = re.search(re.escape(m.title), text, re.I)
            if hit is None or hit.group(0)[:1].islower():
                continue
            if " " not in m.title and (hit.start() == 0 or re.search(r"[.!?:]\s*$", text[: hit.start()])):
                continue
            raise LLMUnavailable(f"Claude named a movie it wasn't asked to discuss ({m.title}).")

    def _template(self, cards: list[MovieCard], anchors: list[int], session: Session) -> str:
        top = cards[0]
        p = session.profile
        if anchors and self.catalog.get(anchors[0]):
            lead = f"Here are {len(cards)} movies similar to {self.catalog.get(anchors[0]).title}."
        elif p.genres:
            lead = f"Here are {len(cards)} {'/'.join(p.genres)} picks for you."
        elif p.liked_ids:
            lead = f"Here are {len(cards)} picks based on what you've liked."
        else:
            lead = f"Here are {len(cards)} well-rated picks to start from."
        why = top.reasons[0].text if top.reasons else ""
        return f"{lead} Top pick: {top.title} ({top.year}). {why}".strip()

    def _follow_ups(self, cards: list[MovieCard], anchors: list[int]) -> list[str]:
        out = [f"More like {cards[0].title}"]
        if len(cards) > 1:
            out.append("Why did you pick the second one?")
        out += ["Show me hidden gems", "Only highly rated ones"]
        return out[:3]

    def _starter_suggestions(self) -> list[str]:
        return ["A lighthearted comedy for tonight", "Underrated science-fiction movies", "I loved Inception and The Prestige"]

    def _simple(self, session: Session, reply: str, intent, mode, reason, suggestions, cards: list[MovieCard] | None = None) -> ChatResponse:
        self.sessions.save(session)
        return ChatResponse(
            reply=reply, intent=intent, recommendations=cards or [], notes=[], suggestions=suggestions,
            profile=session.profile, strategy_used=session.profile.strategy, llm=LLMStatus(mode=mode, reason=reason),
        )

