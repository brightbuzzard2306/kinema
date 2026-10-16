"""Rule-based preference parser + shared validation of NLU output.

The rule parser is the offline fallback and also the reference behaviour that tests pin down.
``resolve_preferences`` is used for BOTH the rule parser and Claude's output: every title is
matched against the real catalogue and every genre against the dataset's genre list, so a
hallucinated title or genre can never reach the recommender.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .catalog import Catalog, normalize_text
from .schemas import Preferences

# phrase -> canonical MovieLens genre(s)
GENRE_SYNONYMS: dict[str, list[str]] = {
    "sci fi": ["Sci-Fi"], "scifi": ["Sci-Fi"], "science fiction": ["Sci-Fi"], "sci-fi": ["Sci-Fi"], "space": ["Sci-Fi"],
    "futuristic": ["Sci-Fi"], "comedy": ["Comedy"], "comedies": ["Comedy"], "funny": ["Comedy"], "hilarious": ["Comedy"],
    "laugh": ["Comedy"], "romcom": ["Romance", "Comedy"], "rom com": ["Romance", "Comedy"],
    "horror": ["Horror"], "scary": ["Horror"], "creepy": ["Horror"], "slasher": ["Horror"], "action": ["Action"],
    "adventure": ["Adventure"], "thriller": ["Thriller"], "thrillers": ["Thriller"], "suspense": ["Thriller"],
    "suspenseful": ["Thriller"], "drama": ["Drama"], "dramas": ["Drama"], "romance": ["Romance"], "romantic": ["Romance"],
    "love story": ["Romance"], "mystery": ["Mystery"], "mysteries": ["Mystery"], "detective": ["Mystery", "Crime"],
    "crime": ["Crime"], "gangster": ["Crime"], "heist": ["Crime"], "fantasy": ["Fantasy"], "magical": ["Fantasy"],
    "animated": ["Animation"], "animation": ["Animation"], "cartoon": ["Animation"], "anime": ["Animation"],
    "kids": ["Children"], "children": ["Children"], "family": ["Children", "Animation"], "documentary": ["Documentary"],
    "documentaries": ["Documentary"], "war": ["War"], "western": ["Western"], "westerns": ["Western"],
    "musical": ["Musical"], "musicals": ["Musical"], "noir": ["Film-Noir"], "film noir": ["Film-Noir"],
}
# moods imply genres softly; they are only used when no explicit genre was given
MOOD_GENRES: dict[str, list[str]] = {
    "lighthearted": ["Comedy"], "light hearted": ["Comedy"], "feel good": ["Comedy", "Romance"], "feelgood": ["Comedy", "Romance"],
    "uplifting": ["Comedy", "Drama"], "heartwarming": ["Drama", "Romance"], "cheerful": ["Comedy"], "fun": ["Comedy", "Adventure"],
    "dark": ["Crime", "Thriller"], "gritty": ["Crime", "Drama"], "mind bending": ["Sci-Fi", "Thriller", "Mystery"],
    "twisty": ["Mystery", "Thriller"], "intense": ["Thriller", "Action"], "emotional": ["Drama"], "tearjerker": ["Drama"],
    "epic": ["Adventure", "War", "Fantasy"], "thought provoking": ["Sci-Fi", "Drama"], "relaxing": ["Comedy", "Romance"],
}
# moods that also imply what to leave out; applied per request (not stored) and always disclosed to the user
MOOD_EXCLUDES: dict[str, list[str]] = {
    "lighthearted": ["Horror", "War", "Crime", "Thriller"], "light hearted": ["Horror", "War", "Crime", "Thriller"],
    "feel good": ["Horror", "War", "Crime", "Thriller"], "feelgood": ["Horror", "War", "Crime", "Thriller"],
    "cheerful": ["Horror", "War", "Crime", "Thriller"], "uplifting": ["Horror", "War"], "heartwarming": ["Horror", "War"],
    "relaxing": ["Horror", "War", "Thriller"], "fun": ["Horror", "War"], "family friendly": ["Horror", "War", "Crime"],
}
# "nothing too violent" etc. -> genres to exclude
VIOLENCE_WORDS = {"violent", "violence", "gore", "gory", "bloody", "brutal", "graphic"}
VIOLENCE_EXCLUDES = ["Horror", "War"]

NEGATORS = {"no", "not", "without", "avoid", "nothing", "except", "skip", "never", "hate", "dont", "don", "isn", "excluding"}
NEG_TITLE_PHRASES = ("didn t like", "did not like", "not a fan of", "can t stand", "hated", "hate", "disliked", "dislike", "boring", "awful", "terrible", "worst")
LIKE_TITLE_PHRASES = ("loved", "love", "enjoyed", "adored", "favorite", "favourite", "liked", "obsessed with")
SIMILAR_PHRASES = ("something like", "similar to", "more like", "just like", "same as", "like")

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "last": -1}


_GENRE_PLURALS = "|".join(sorted({re.escape(k) for k in GENRE_SYNONYMS if " " not in k} | {"comedies", "dramas", "thrillers", "westerns", "musicals", "documentaries", "mysteries"}))


def canonical_genres(names: list[str], all_genres: list[str]) -> list[str]:
    """Map arbitrary genre strings to dataset genres; unknown strings are dropped."""
    lookup = {normalize_text(g): g for g in all_genres}
    out: list[str] = []
    for name in names:
        n = normalize_text(str(name))
        hit = lookup.get(n) or lookup.get(n.replace(" ", ""))
        mapped = [hit] if hit else [g for g in GENRE_SYNONYMS.get(n, []) if g in all_genres]
        for g in mapped:
            if g not in out:
                out.append(g)
    return out


def mood_exclusions(mood: str | None, all_genres: list[str]) -> list[str]:
    """Genres a stated mood implicitly rules out (e.g. lighthearted -> no Horror/War/Crime/Thriller)."""
    if not mood:
        return []
    text = " " + normalize_text(mood) + " "
    out: list[str] = []
    for phrase, genres in MOOD_EXCLUDES.items():
        if f" {phrase} " in text:
            out += [g for g in genres if g in all_genres and g not in out]
    return out


@dataclass
class ResolvedPreferences:
    prefs: Preferences
    genres: list[str] = field(default_factory=list)
    excluded_genres: list[str] = field(default_factory=list)
    liked_ids: list[int] = field(default_factory=list)
    disliked_ids: list[int] = field(default_factory=list)
    anchor_ids: list[int] = field(default_factory=list)
    unresolved_titles: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    corrections: list[tuple[str, int]] = field(default_factory=list)  # (what the user typed, movie it was repaired to)


def resolve_preferences(prefs: Preferences, catalog: Catalog, rescue: "Callable[[str], int | None] | None" = None) -> ResolvedPreferences:
    """Validate and clamp NLU output against the catalogue (the anti-hallucination gate).

    ``rescue`` is an optional second chance for a title that did not match (the spelling corrector): it returns a movie id or None."""
    r = ResolvedPreferences(prefs=prefs)
    r.genres = canonical_genres(prefs.genres, catalog.all_genres)
    r.excluded_genres = [g for g in canonical_genres(prefs.excluded_genres, catalog.all_genres) if g not in r.genres]

    def ids_for(titles: list[str]) -> list[int]:
        found: list[int] = []
        for t in titles:
            match = catalog.resolve_title(str(t)[:120])
            if match is None and rescue is not None:
                repaired = rescue(str(t)[:120])
                if repaired is not None:
                    r.corrections.append((str(t)[:120], repaired))
                    if repaired not in found:
                        found.append(repaired)
                    continue
            if match is None:
                if t not in r.unresolved_titles:
                    r.unresolved_titles.append(str(t)[:120])
            elif match.movie_id not in found:
                found.append(match.movie_id)
        return found

    r.liked_ids = ids_for(prefs.liked_titles)
    r.disliked_ids = ids_for(prefs.disliked_titles)
    r.anchor_ids = [i for i in ids_for(prefs.anchor_titles) if i not in r.liked_ids]
    r.disliked_ids = [i for i in r.disliked_ids if i not in r.liked_ids and i not in r.anchor_ids]

    if prefs.max_runtime_minutes is not None:
        r.unsupported.append("runtime")  # MovieLens has no runtime data; never pretend to filter on it
    if prefs.min_rating is not None:
        prefs.min_rating = float(min(5.0, max(0.5, prefs.min_rating)))
    if prefs.count is not None:
        prefs.count = int(min(12, max(1, prefs.count)))
    if prefs.novelty is not None:
        prefs.novelty = float(min(1.0, max(0.0, prefs.novelty)))
    if prefs.ordinal_reference is not None and not (prefs.ordinal_reference == -1 or 1 <= prefs.ordinal_reference <= 12):
        prefs.ordinal_reference = None
    for attr in ("year_min", "year_max"):
        v = getattr(prefs, attr)
        if v is not None and not (1880 <= v <= 2100):
            setattr(prefs, attr, None)
    return r


# ---------------------------------------------------------------- rule-based parser
def _tokens(text: str) -> list[str]:
    return normalize_text(text).split()


def _find_phrases(tokens: list[str], table: dict[str, list[str]]) -> list[tuple[int, int, list[str]]]:
    """Longest-first phrase matches: (start, end, values)."""
    spans: list[tuple[int, int, list[str]]] = []
    taken = [False] * len(tokens)
    for n in range(4, 0, -1):
        for i in range(len(tokens) - n + 1):
            if any(taken[i : i + n]):
                continue
            key = " ".join(tokens[i : i + n])
            if key in table:
                spans.append((i, i + n, table[key]))
                for j in range(i, i + n):
                    taken[j] = True
    return sorted(spans)


def _intent(text: str, has_titles: bool) -> str:
    t = normalize_text(text)
    if re.search(r"\b(start over|reset|new conversation|clear everything|begin again)\b", t):
        return "reset"
    if re.search(r"\b(what can you do|how do you work|help me understand|how does this work|who are you)\b", t) or t in ("help", "hi help"):
        return "help"
    if re.search(r"\bwhy\b", t) and re.search(r"\b(recommend|suggest|pick|this|that|those|these|first|second|third|one)\b", t):
        return "explain"
    if re.search(r"\bexplain\b", t):
        return "explain"
    if re.search(r"\b(didn t like (those|these|any)|did not like (those|these)|none of (those|these)|not (those|these)|something (else|different)|try (something )?(else|different)|dislike (those|these)|don t like (those|these))\b", t):
        return "reject_last"
    if re.search(r"\b(more like|similar to|something like|like the (first|second|third|fourth|fifth|last))\b", t):
        return "similar"
    if re.fullmatch(r"(hi|hello|hey|thanks|thank you|ok|okay|cool|great|nice)( there)?", t):
        return "chitchat"
    return "recommend"


def parse_with_rules(message: str, catalog: Catalog) -> Preferences:
    """Deterministic parser for common requests. Never calls the network."""
    text = message.strip()
    tokens = _tokens(text)
    low = " " + " ".join(tokens) + " "
    prefs = Preferences()

    # --- titles with sentiment from the words just before each title
    matches = catalog.find_titles_in_text(text)
    for m in re.finditer(r"[\"“']([^\"”']{2,60})[\"”']", text):
        quoted = catalog.resolve_title(m.group(1))
        if quoted and all(quoted.movie_id != x.movie_id for x in matches):
            matches.append(quoted)

    norm_text = " ".join(tokens)
    for match in matches:
        title_norm = normalize_text(match.title)
        pos = norm_text.find(title_norm)
        window = norm_text[max(0, pos - 45) : pos] if pos >= 0 else ""
        # nearest cue wins (cues earlier in the window are overridden by later ones)
        best, kind = -1, "anchor"
        for phrase in NEG_TITLE_PHRASES:
            i = window.rfind(phrase)
            if i > best:
                best, kind = i, "disliked"
        for phrase in LIKE_TITLE_PHRASES:
            i = window.rfind(phrase)
            if i > best:
                best, kind = i, "liked"
        for phrase in SIMILAR_PHRASES:
            i = window.rfind(phrase)
            if i > best and phrase != "like":
                best, kind = i, "anchor"
            elif phrase == "like" and re.search(r"\blike\s*$", window) and i > best:
                best, kind = i, "anchor"
        label = match.title
        {"disliked": prefs.disliked_titles, "liked": prefs.liked_titles, "anchor": prefs.anchor_titles}[kind].append(label)

    # --- genres, exclusions, moods (words inside a recognised title are masked out)
    masked = norm_text
    for match in matches:
        title_norm = normalize_text(match.title)
        masked = masked.replace(title_norm, " ".join("_" * 1 for _ in title_norm.split()))
    tokens = masked.split()
    for start, _end, genres in _find_phrases(tokens, GENRE_SYNONYMS):
        negated = any(t in NEGATORS for t in tokens[max(0, start - 3) : start])
        target = prefs.excluded_genres if negated else prefs.genres
        for g in genres:
            if g not in target:
                target.append(g)
    if VIOLENCE_WORDS & set(tokens):
        negated = any(t in NEGATORS or t in ("less", "too") for t in tokens)
        if negated:
            prefs.excluded_genres.extend(
                g for g in VIOLENCE_EXCLUDES if g not in prefs.excluded_genres and g not in prefs.genres
            )
    prefs.genres = [g for g in prefs.genres if g not in prefs.excluded_genres]

    mood_hits = _find_phrases(tokens, MOOD_GENRES)
    if mood_hits:
        prefs.mood = " ".join(tokens[mood_hits[0][0] : mood_hits[0][1]])
        if not prefs.genres:
            for _s, _e, genres in mood_hits:
                for g in genres:
                    if g not in prefs.genres and g not in prefs.excluded_genres:
                        prefs.genres.append(g)

    # --- numbers: counts, ratings, years, runtime
    count = re.search(r"\b(?:give me|show me|suggest|recommend|top|list|need|want|any)?\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:more\s+)?(?:[a-z]+\s+){0,3}?(?:movies?|films?|recommendations?|suggestions?|picks?|options?|" + _GENRE_PLURALS + r")\b", low)
    if count:
        raw = count.group(1)
        prefs.count = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
    if re.search(r"\b(highly rated|top rated|best rated|well rated|acclaimed|critically acclaimed|best)\b", low):
        prefs.min_rating = 4.0
    stars = re.search(r"\b(?:rated\s+)?(?:above|over|at least|minimum|min)\s+(\d(?:\.\d)?)\s*(?:stars?|\+)?", low)
    if stars:
        value = float(stars.group(1))
        if 0.5 <= value <= 5:
            prefs.min_rating = value
    if re.search(r"\b(underrated|hidden gem|hidden gems|lesser known|obscure|off the beaten|under the radar|deep cut)\b", low):
        prefs.novelty = 0.85
        prefs.min_rating = prefs.min_rating or 3.8
    elif re.search(r"\b(popular|blockbuster|mainstream|famous|well known|crowd pleaser)\b", low):
        prefs.novelty = 0.0
    decade = re.search(r"\b(?:the\s+)?((?:19|20)?\d0)s\b", low)
    if decade:
        d = int(decade.group(1))
        d = d + (1900 if d >= 30 and d < 100 else 2000 if d < 30 else 0)
        if 1900 <= d <= 2010:
            prefs.year_min, prefs.year_max = d, d + 9
    after = re.search(r"\b(?:after|since|from)\s+((?:19|20)\d{2})\b", low)
    if after:
        prefs.year_min = int(after.group(1))
    before = re.search(r"\b(?:before|until|prior to)\s+((?:19|20)\d{2})\b", low)
    if before:
        prefs.year_max = int(before.group(1))
    if prefs.year_min is None and re.search(r"\b(recent|new|latest|modern)\b", low):
        prefs.year_min = 2010
    if prefs.year_max is None and prefs.year_min is None and re.search(r"\b(classic|classics|old school|vintage|old)\b", low):
        prefs.year_max = 1985
    runtime = re.search(r"\b(?:under|less than|shorter than|below|max|within)\s+(\d+(?:\.\d+)?|one|two|three)\s*(hours?|hrs?|minutes?|mins?)\b", low)
    if runtime:
        amount = runtime.group(1)
        value = float(amount) if amount.replace(".", "", 1).isdigit() else float(NUMBER_WORDS[amount])
        prefs.max_runtime_minutes = int(value * 60) if runtime.group(2).startswith(("h")) else int(value)

    # --- ordinal references to previous results
    for word, num in ORDINALS.items():
        if re.search(rf"\b{word}\b\s+(?:one|movie|film|pick|recommendation|suggestion|result)", low) or re.search(rf"\bthe\s+{word}\b", low):
            prefs.ordinal_reference = num
            break
    hashnum = re.search(r"(?:#|number\s+|no\.?\s*)(\d{1,2})\b", text.lower())
    if hashnum and prefs.ordinal_reference is None:
        prefs.ordinal_reference = int(hashnum.group(1))

    has_titles = bool(prefs.liked_titles or prefs.anchor_titles or prefs.disliked_titles)
    prefs.intent = _intent(text, has_titles)
    if prefs.intent == "recommend" and prefs.ordinal_reference and re.search(r"\bmore like\b|\bsimilar\b", low):
        prefs.intent = "similar"
    return prefs
