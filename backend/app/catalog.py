"""Movie catalog: cleaned metadata, rating statistics and title resolution.

``stats`` are computed from whatever ratings frame is passed in, so the evaluation
pipeline can build a catalog from *training* ratings only (no test leakage).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from .dataset import RawData

NO_GENRES = "(no genres listed)"
# MovieLens lists "IMAX" as a genre but it is a screening format, not a genre; we drop it.
NOT_GENRES = frozenset({NO_GENRES, "IMAX"})
_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
_PAREN_RE = re.compile(r"\(([^()]*)\)")
_ARTICLES = ("The", "A", "An", "Les", "Le", "La", "L'", "Das", "Der", "Die", "El", "Il")

# Bayesian prior strength: how many "average" ratings a movie starts with.
BAYES_PRIOR_VOTES = 25


def normalize_text(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace (used for title matching)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fix_article(title: str) -> str:
    """'Dark Knight, The' -> 'The Dark Knight'."""
    for art in _ARTICLES:
        suffix = f", {art}"
        if title.endswith(suffix):
            joined = f"{art}{'' if art.endswith(chr(39)) else ' '}{title[: -len(suffix)]}"
            return joined
    return title


def parse_title(raw: str) -> tuple[str, int | None, list[str]]:
    """Return (display_title, year, aliases) from a MovieLens title string."""
    raw = raw.strip()
    year = None
    m = _YEAR_RE.search(raw)
    if m:
        year = int(m.group(1))
        raw = raw[: m.start()].strip()
    aliases: list[str] = []
    for alt in _PAREN_RE.findall(raw):
        alt = alt.strip()
        if alt.lower().startswith("a.k.a."):
            alt = alt[6:].strip()
        if alt:
            aliases.append(_fix_article(alt))
    primary = _PAREN_RE.sub("", raw).strip()
    return _fix_article(primary), year, aliases


@dataclass(frozen=True)
class Movie:
    movie_id: int
    title: str
    year: int | None
    genres: tuple[str, ...]
    n_ratings: int
    mean_rating: float | None
    bayes_rating: float
    tmdb_id: int | None = None
    imdb_id: str | None = None


@dataclass
class TitleMatch:
    movie_id: int
    title: str
    year: int | None
    score: float


@dataclass
class Catalog:
    movies: list[Movie]
    index_by_id: dict[int, int]
    tags_text: list[str]
    global_mean: float
    all_genres: list[str]
    _title_index: dict[str, list[int]] = field(default_factory=dict, repr=False)
    _title_keys: list[str] = field(default_factory=list, repr=False)

    # ---------- construction ----------
    @classmethod
    def build(cls, raw: RawData, ratings: pd.DataFrame | None = None) -> "Catalog":
        ratings = raw.ratings if ratings is None else ratings
        stats = ratings.groupby("movieId")["rating"].agg(["count", "mean"])
        global_mean = float(ratings["rating"].mean())

        tag_map: dict[int, list[str]] = {}
        if not raw.tags.empty:
            cleaned = raw.tags.dropna(subset=["tag"]).copy()
            cleaned["tag"] = cleaned["tag"].astype(str).str.lower().str.strip()
            for mid, group in cleaned.groupby("movieId")["tag"]:
                tag_map[int(mid)] = sorted(set(group))

        links = raw.links.set_index("movieId") if not raw.links.empty else pd.DataFrame()

        movies: list[Movie] = []
        tags_text: list[str] = []
        title_index: dict[str, list[int]] = {}
        genre_set: set[str] = set()

        for pos, row in enumerate(raw.movies.itertuples(index=False)):
            mid = int(row.movieId)
            title, year, aliases = parse_title(str(row.title))
            genres = tuple(g for g in str(row.genres).split("|") if g and g not in NOT_GENRES)
            genre_set.update(genres)
            n = int(stats["count"].get(mid, 0))
            mean = float(stats["mean"].get(mid)) if n else None
            bayes = (
                (n / (n + BAYES_PRIOR_VOTES)) * mean + (BAYES_PRIOR_VOTES / (n + BAYES_PRIOR_VOTES)) * global_mean
                if n
                else global_mean
            )
            tmdb_id = imdb_id = None
            if mid in links.index:
                t = links.at[mid, "tmdbId"]
                i = links.at[mid, "imdbId"]
                tmdb_id = int(t) if pd.notna(t) else None
                imdb_id = f"{int(i):07d}" if pd.notna(i) else None
            movies.append(Movie(mid, title, year, genres, n, mean, bayes, tmdb_id, imdb_id))
            tags_text.append(" | ".join(tag_map.get(mid, [])))
            for name in [title, *aliases]:
                key = normalize_text(name)
                if key:
                    title_index.setdefault(key, []).append(pos)

        catalog = cls(
            movies=movies,
            index_by_id={m.movie_id: i for i, m in enumerate(movies)},
            tags_text=tags_text,
            global_mean=global_mean,
            all_genres=sorted(genre_set),
            _title_index=title_index,
            _title_keys=list(title_index.keys()),
        )
        return catalog

    # ---------- lookups ----------
    def __len__(self) -> int:
        return len(self.movies)

    def get(self, movie_id: int) -> Movie | None:
        idx = self.index_by_id.get(movie_id)
        return None if idx is None else self.movies[idx]

    def array(self, attr: str) -> np.ndarray:
        return np.array([getattr(m, attr) for m in self.movies])

    def tags_of(self, idx: int, limit: int = 8) -> list[str]:
        text = self.tags_text[idx]
        return [t for t in text.split(" | ") if t][:limit]

    # ---------- title resolution ----------
    def resolve_title(self, query: str, year_hint: int | None = None, min_score: float = 0.86) -> TitleMatch | None:
        """Map free text to a real dataset movie, or None. Never invents a movie."""
        q = normalize_text(query)
        if not q:
            return None
        year_in_query = re.search(r"\b(19|20)\d{2}\b", query)
        if year_in_query and year_hint is None:
            year_hint = int(year_in_query.group(0))
            q = normalize_text(query.replace(year_in_query.group(0), ""))
            if not q:
                return None

        candidates = self._title_index.get(q)
        score = 1.0
        if not candidates:
            # try with a leading article dropped, then fuzzy matching on the whole key space
            for art in ("the ", "a ", "an "):
                if q.startswith(art) and q[len(art):] in self._title_index:
                    candidates, score = self._title_index[q[len(art):]], 0.98
                    break
                if (art + q) in self._title_index:
                    candidates, score = self._title_index[art + q], 0.98
                    break
        if not candidates:
            best_key, best = None, 0.0
            first = q[:1]
            for key in self._title_keys:
                if abs(len(key) - len(q)) > max(4, len(q) // 3):
                    continue
                if first and key[:1] != first and not key.startswith(("the ", "a ")):
                    continue
                ratio = SequenceMatcher(None, q, key).ratio()
                if ratio > best:
                    best_key, best = key, ratio
            if best_key is None or best < min_score:
                return None
            candidates, score = self._title_index[best_key], best

        def rank(pos: int) -> tuple[int, int]:
            m = self.movies[pos]
            year_penalty = 0 if (year_hint is None or m.year == year_hint) else 1
            return (year_penalty, -m.n_ratings)

        best_pos = min(candidates, key=rank)
        movie = self.movies[best_pos]
        if year_hint is not None and movie.year != year_hint and len(candidates) > 1:
            score -= 0.05
        return TitleMatch(movie.movie_id, movie.title, movie.year, float(score))

    def find_titles_in_text(self, text: str, max_ngram: int = 7) -> list[TitleMatch]:
        """Greedy longest-first exact scan for titles inside a sentence (for rule-based NLU)."""
        tokens = normalize_text(text).split()
        found: list[TitleMatch] = []
        used = [False] * len(tokens)
        for n in range(min(max_ngram, len(tokens)), 0, -1):
            for start in range(0, len(tokens) - n + 1):
                if any(used[start : start + n]):
                    continue
                key = " ".join(tokens[start : start + n])
                if n == 1 and (len(key) < 6 or key in _AMBIGUOUS_ONE_WORD):
                    continue
                if n == 2 and len(key) < 7:
                    continue
                if key in self._title_index:
                    movie = self.movies[min(self._title_index[key], key=lambda p: -self.movies[p].n_ratings)]
                    found.append(TitleMatch(movie.movie_id, movie.title, movie.year, 1.0))
                    for k in range(start, start + n):
                        used[k] = True
        return found


# One-word titles that are also ordinary words in requests ("something", "different"...).
_AMBIGUOUS_ONE_WORD = frozenset(
    "something nothing anything everything someone movies movie films film recommend recommendation "
    "recommendations similar different really thriller thrillers comedy comedies horror action drama "
    "dramas romance romantic mystery fantasy western documentary animation children family adventure "
    "science fiction crime musical lighthearted underrated popular classic classics tonight weekend "
    "second first third fourth fifth these those please anyway because another people friends friend "
    "together forever america american english french german".split()
)
