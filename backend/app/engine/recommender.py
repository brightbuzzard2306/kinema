"""Hybrid recommender: filtering, score fusion, graceful relaxation and grounded reasons.

Component scores (each min-max normalised over the eligible candidates, so scales are comparable):

* content       - cosine similarity of the TF-IDF movie vector to the user's taste vector
* collaborative - item-item CF score from the user's liked/disliked movies (or ratings)
* popularity    - Bayesian-average quality blended with rating volume (flipped for discovery)
* preference    - fraction of the requested genres the movie matches

The final score is a weighted average over the components that are *available for that
candidate*; weights of unavailable components are redistributed automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from scipy import sparse

from ..catalog import Catalog
from .collaborative import ItemKNN
from .content import ContentModel

Strategy = Literal["hybrid", "popular", "content", "collaborative"]
STRATEGIES: tuple[str, ...] = ("hybrid", "popular", "content", "collaborative")

COMPONENTS = ("content", "collaborative", "popularity", "preference")
DEFAULT_WEIGHTS = {"content": 0.30, "collaborative": 0.35, "popularity": 0.15, "preference": 0.20}
STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "hybrid": DEFAULT_WEIGHTS,
    "popular": {"popularity": 1.0},
    "content": {"content": 0.85, "preference": 0.15},
    "collaborative": {"collaborative": 1.0},
}

# Hybrid weights depend on how much the user has told us (number of liked + "more like" movies):
#   0 signals          -> cold-start weights (quality + stated genres)
#   1..THIN_MAX        -> "few likes" weights (tuned on validation data, see reports/evaluation.md)
#   THIN_MAX..WARM_MIN -> linear blend between few-likes and warm weights (a design choice, not separately validated)
#   >= WARM_MIN        -> warm weights (tuned on validation data)
COLD_WEIGHTS = {"popularity": 0.55, "preference": 0.30, "content": 0.15}
THIN_DEFAULT = {"content": 0.30, "collaborative": 0.30, "popularity": 0.25, "preference": 0.15}
THIN_MAX_SIGNALS = 3
WARM_MIN_SIGNALS = 10

LIKED_CF_WEIGHT = 1.0
ANCHOR_CF_WEIGHT = 1.5
DISLIKED_CF_WEIGHT = -1.0


@dataclass
class Query:
    strategy: str = "hybrid"
    liked: list[int] = field(default_factory=list)
    disliked: list[int] = field(default_factory=list)
    anchors: list[int] = field(default_factory=list)  # "more like this" targets (strong positive)
    genres: list[str] = field(default_factory=list)
    excluded_genres: list[str] = field(default_factory=list)
    min_rating: float | None = None
    year_min: int | None = None
    year_max: int | None = None
    novelty: float = 0.3  # 0 = mainstream, 1 = discovery
    exclude_ids: set[int] = field(default_factory=set)
    k: int = 6
    min_ratings: int = 10
    weights: dict[str, float] | None = None


@dataclass
class Reason:
    kind: str  # genre | content | collaborative | popularity | discovery
    text: str


@dataclass
class Recommendation:
    movie_id: int
    title: str
    year: int | None
    genres: list[str]
    mean_rating: float | None
    n_ratings: int
    score: float
    components: dict[str, float | None]
    weights_used: dict[str, float]
    reasons: list[Reason]
    confidence: str
    confidence_basis: str
    tmdb_id: int | None = None
    imdb_id: str | None = None


@dataclass
class RankResult:
    recommendations: list[Recommendation]
    notes: list[str]
    strategy_used: str
    n_candidates: int
    regime: str = "custom"  # cold | thin | blend | warm | custom


def _minmax(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Min-max normalise over the masked values (lower bound = 1st percentile, upper = max)."""
    out = np.zeros_like(values, dtype=float)
    pool = values[mask]
    if pool.size == 0:
        return out
    lo, hi = (np.percentile(pool, 1) if pool.size > 20 else pool.min()), pool.max()
    if hi - lo < 1e-12:
        out[mask] = 0.5
        return out
    out[mask] = np.clip((pool - lo) / (hi - lo), 0, 1)
    return out


class Recommender:
    """Holds the three trained models for one ratings snapshot and answers ``Query`` objects."""

    def __init__(
        self,
        catalog: Catalog,
        ratings: pd.DataFrame,
        knn_params: dict | None = None,
        hybrid_weights: dict[str, float] | None = None,
        thin_weights: dict[str, float] | None = None,
    ) -> None:
        self.catalog = catalog
        self.strategy_weights = {**STRATEGY_WEIGHTS, "hybrid": dict(hybrid_weights or DEFAULT_WEIGHTS)}
        self.thin_weights = dict(thin_weights or THIN_DEFAULT)
        self.content = ContentModel(catalog)
        self.knn = ItemKNN(ratings, catalog.index_by_id, **(knn_params or {}))
        self._n = len(catalog)
        self._n_ratings = catalog.array("n_ratings").astype(float)
        self._mean = np.array([m.mean_rating if m.mean_rating is not None else np.nan for m in catalog.movies])
        self._bayes = catalog.array("bayes_rating").astype(float)
        self._year = np.array([m.year if m.year else np.nan for m in catalog.movies], dtype=float)
        self._genre_sets = [set(m.genres) for m in catalog.movies]

    def hybrid_base_weights(self, n_signals: int) -> tuple[dict[str, float], str]:
        """Hybrid component weights for a user who has given ``n_signals`` liked / anchor movies."""
        warm = self.strategy_weights["hybrid"]
        if n_signals <= 0:
            return dict(COLD_WEIGHTS), "cold"
        if n_signals <= THIN_MAX_SIGNALS:
            return dict(self.thin_weights), "thin"
        if n_signals >= WARM_MIN_SIGNALS:
            return dict(warm), "warm"
        lam = (n_signals - THIN_MAX_SIGNALS) / (WARM_MIN_SIGNALS - THIN_MAX_SIGNALS)
        blended = {c: lam * warm.get(c, 0.0) + (1 - lam) * self.thin_weights.get(c, 0.0) for c in COMPONENTS}
        return blended, "blend"

    # ------------------------------------------------------------------ filters
    def _eligible(self, q: Query, relax: int) -> np.ndarray:
        """Boolean mask of allowed candidates. ``relax`` loosens soft filters stage by stage.

        Never relaxed: excluded genres, excluded/seen movies and requested genres.
        Stages: 1 lower rating-count floor, 2 min rating -0.5, 3 drop year range, 4 min rating -1.0, 5 drop min rating.
        """
        mask = np.ones(self._n, dtype=bool)
        idx_of = self.catalog.index_by_id
        for mid in q.exclude_ids | set(q.liked) | set(q.disliked) | set(q.anchors):
            if mid in idx_of:
                mask[idx_of[mid]] = False
        if q.excluded_genres:
            banned = set(q.excluded_genres)
            mask &= np.array([not (g & banned) for g in self._genre_sets])
        mask &= self._n_ratings >= (q.min_ratings if relax < 1 else max(3, q.min_ratings // 3))
        if q.min_rating is not None and relax < 5:
            delta = 0.0 if relax < 2 else 0.5 if relax < 4 else 1.0
            mask &= np.nan_to_num(self._mean, nan=0.0) >= q.min_rating - delta
        if relax < 3:
            if q.year_min is not None:
                mask &= np.nan_to_num(self._year, nan=0) >= q.year_min
            if q.year_max is not None:
                mask &= np.nan_to_num(self._year, nan=9999) <= q.year_max
        if q.genres:
            wanted = set(q.genres)
            mask &= np.array([bool(g & wanted) for g in self._genre_sets])
        return mask

    # ------------------------------------------------------------------ scoring
    def _collab_signals(self, q: Query) -> dict[int, float]:
        idx_of = self.catalog.index_by_id
        signals: dict[int, float] = {}
        for mid in q.liked:
            if mid in idx_of:
                signals[idx_of[mid]] = LIKED_CF_WEIGHT
        for mid in q.anchors:
            if mid in idx_of:
                signals[idx_of[mid]] = ANCHOR_CF_WEIGHT
        for mid in q.disliked:
            if mid in idx_of:
                signals[idx_of[mid]] = DISLIKED_CF_WEIGHT
        return signals

    def _taste_vector(self, q: Query) -> sparse.csr_matrix | None:
        idx_of = self.catalog.index_by_id
        pos = {idx_of[m]: 1.0 for m in q.liked if m in idx_of}
        pos.update({idx_of[m]: 2.0 for m in q.anchors if m in idx_of})
        neg = {idx_of[m]: 1.0 for m in q.disliked if m in idx_of}
        return self.content.profile_vector(pos, neg, q.genres)

    def rank(self, q: Query) -> RankResult:
        notes: list[str] = []
        strategy = q.strategy if q.strategy in STRATEGIES else "hybrid"
        k = max(1, min(q.k, 50))

        # relax soft filters stage by stage until we can fill k slots (never exclusions / genres)
        stage_notes = {
            1: "Few movies passed every filter, so I lowered the minimum rating-count requirement.",
            2: "I loosened the minimum MovieLens rating by half a star to find enough matches.",
            3: "I widened the release-year range to find enough matches.",
            4: "I loosened the minimum MovieLens rating by a full star to find enough matches.",
            5: "Nothing reached that MovieLens rating, so I ignored the minimum rating and kept everything else.",
        }
        applicable = [1] + ([2] if q.min_rating is not None else []) + (
            [3] if (q.year_min is not None or q.year_max is not None) else []
        ) + ([4, 5] if q.min_rating is not None else [])
        mask, chosen = self._eligible(q, 0), 0
        for stage in applicable:
            if mask.sum() >= k:
                break
            mask, chosen = self._eligible(q, stage), stage
        notes.extend(stage_notes[s] for s in applicable if s <= chosen and chosen > 0)
        if mask.sum() == 0:
            return RankResult([], notes + ["No movies match those filters. Try loosening the years or removing a genre exclusion."], strategy, 0)
        if mask.sum() < k:
            notes.append(f"Only {int(mask.sum())} movies in the catalogue match all of your filters.")

        # --- raw component scores over all items
        taste = self._taste_vector(q)
        content_raw = self.content.scores(taste) if taste is not None else np.zeros(self._n)
        signals = self._collab_signals(q)
        cf_raw, cf_support, cf_avail = self.knn.predict(signals)
        content_avail = np.full(self._n, taste is not None)

        pref_raw = np.zeros(self._n)
        pref_avail = np.zeros(self._n, dtype=bool)
        if q.genres:
            wanted = set(q.genres)
            pref_raw = np.array([len(g & wanted) / len(wanted) for g in self._genre_sets])
            pref_avail[:] = True

        quality = _minmax(self._bayes, mask)
        volume = _minmax(np.log1p(self._n_ratings), mask)
        nov = float(np.clip(q.novelty, 0, 1))
        popularity = 0.5 * quality + 0.5 * ((1 - nov) * volume + nov * (1 - volume))
        popularity[~mask] = 0

        norm = {
            "content": _minmax(content_raw, mask & content_avail),
            "collaborative": _minmax(cf_raw, mask & cf_avail),
            "popularity": popularity,
            "preference": pref_raw,
        }
        avail = {
            "content": content_avail,
            "collaborative": cf_avail,
            "popularity": np.ones(self._n, dtype=bool),
            "preference": pref_avail,
        }

        # --- choose weights (strategy first, then caller override)
        if q.weights:
            base, regime = dict(q.weights), "custom"
        elif strategy == "hybrid":
            n_pos = len({m for m in (*q.liked, *q.anchors) if m in self.catalog.index_by_id})
            base, regime = self.hybrid_base_weights(n_pos)
        else:
            base, regime = dict(self.strategy_weights[strategy]), "custom"
        if strategy == "hybrid" and nov > 0.5:
            base["popularity"] = base.get("popularity", 0.0) * 0.5  # discovery mode relies less on blockbusters
        usable = {c: w for c, w in base.items() if w > 0 and avail[c][mask].any()}
        if not usable:
            strategy_used = "popular"
            usable = {"popularity": 1.0}
            notes.append("I didn't have enough taste signal for that strategy yet, so I ranked by quality and popularity.")
        elif strategy in ("content", "collaborative") and set(usable) == {"preference"}:
            usable = {"popularity": 1.0}
            notes.append("I didn't have enough taste signal for that strategy yet, so I ranked by quality and popularity.")
            strategy_used = "popular"
        else:
            strategy_used = strategy

        weighted = np.zeros(self._n)
        total_w = np.zeros(self._n)
        for comp, w in usable.items():
            a = avail[comp] & mask
            weighted[a] += w * norm[comp][a]
            total_w[a] += w
        with np.errstate(invalid="ignore", divide="ignore"):
            final = np.where(total_w > 0, weighted / total_w, 0.0)
        final[~mask] = -1.0
        # tiny quality tie-breaker so equal scores prefer the better-rated movie
        final = np.where(mask, final + 1e-6 * self._bayes, final)

        order = np.argsort(-final, kind="stable")[:k]
        order = [int(i) for i in order if mask[i]]
        recs = [
            self._build_recommendation(
                i, q, float(final[i]), norm, avail, usable, signals, cf_support, mask
            )
            for i in order
        ]
        return RankResult(recs, notes, strategy_used, int(mask.sum()), regime)

    # ------------------------------------------------------------------ explanations
    def _build_recommendation(
        self,
        i: int,
        q: Query,
        score: float,
        norm: dict[str, np.ndarray],
        avail: dict[str, np.ndarray],
        usable: dict[str, float],
        signals: dict[int, float],
        cf_support: np.ndarray,
        mask: np.ndarray,
    ) -> Recommendation:
        movie = self.catalog.movies[i]
        idx_of = self.catalog.index_by_id
        comps: dict[str, float | None] = {
            c: (round(float(norm[c][i]), 3) if (c in usable and avail[c][i]) else None) for c in COMPONENTS
        }
        total = sum(w for c, w in usable.items() if avail[c][i]) or 1.0
        weights_used = {c: round(w / total, 3) for c, w in usable.items() if avail[c][i]}
        reasons: list[Reason] = []

        # genre preference
        if q.genres:
            hit = [g for g in movie.genres if g in q.genres]
            if hit:
                reasons.append(Reason("genre", f"Matches your genres: {', '.join(hit)}."))

        # content similarity to specific movies the user liked / anchored on
        refs = [idx_of[m] for m in (q.anchors or q.liked) if m in idx_of]
        if refs and "content" in weights_used:
            sims = [(r, float(self.content.matrix[i].multiply(self.content.matrix[r]).sum())) for r in refs]
            ref, sim = max(sims, key=lambda p: p[1])
            if sim >= 0.15:
                shared = self.content.shared_features(i, ref)
                bits = []
                if shared["genres"]:
                    bits.append("genres " + "/".join(shared["genres"][:3]))
                if shared["tags"]:
                    bits.append("tags " + ", ".join(shared["tags"]))
                detail = f" (shared {'; '.join(bits)})" if bits else ""
                reasons.append(
                    Reason("content", f"Similar in content to {self.catalog.movies[ref].title}{detail}.")
                )

        # collaborative evidence from actual rating patterns
        if "collaborative" in weights_used and signals:
            neigh = self.knn.top_neighbours(i, signals, limit=2)
            if neigh:
                names = " and ".join(self.catalog.movies[n].title for n, _ in neigh)
                reasons.append(
                    Reason(
                        "collaborative",
                        f"People who rated {names} highly also rated this one highly "
                        f"(item similarity {neigh[0][1]:.2f}).",
                    )
                )

        # quality / discovery evidence straight from MovieLens
        if movie.mean_rating is not None:
            if q.novelty > 0.6 and movie.n_ratings < 60:
                reasons.append(
                    Reason(
                        "discovery",
                        f"Lesser-known pick: {movie.mean_rating:.1f}/5 average from only {movie.n_ratings} MovieLens ratings.",
                    )
                )
            else:
                reasons.append(
                    Reason(
                        "popularity",
                        f"Rated {movie.mean_rating:.1f}/5 on average by {movie.n_ratings} MovieLens users.",
                    )
                )

        # confidence: how much rating evidence exists AND how many active signals agree
        active = [v for v in comps.values() if v is not None]
        agree = sum(1 for v in active if v >= 0.5) / len(active) if active else 0.0
        volume_conf = movie.n_ratings / (movie.n_ratings + 25)
        conf_score = 0.5 * volume_conf + 0.5 * agree
        label = "high" if conf_score >= 0.62 else "medium" if conf_score >= 0.4 else "low"
        basis = f"{movie.n_ratings} ratings; {sum(1 for v in active if v >= 0.5)} of {len(active)} signals strongly agree"

        return Recommendation(
            movie_id=movie.movie_id,
            title=movie.title,
            year=movie.year,
            genres=list(movie.genres),
            mean_rating=round(movie.mean_rating, 2) if movie.mean_rating is not None else None,
            n_ratings=movie.n_ratings,
            score=round(score, 4),
            components=comps,
            weights_used=weights_used,
            reasons=reasons,
            confidence=label,
            confidence_basis=basis,
            tmdb_id=movie.tmdb_id,
            imdb_id=movie.imdb_id,
        )

    # ------------------------------------------------------------------ raw scores (evaluation)
    def score_all(self, q: Query) -> np.ndarray:
        """Final scores for *every* movie without top-k truncation (used by the evaluator)."""
        result = self.rank(Query(**{**q.__dict__, "k": self._n}))
        out = np.full(self._n, -np.inf)
        for r in result.recommendations:
            out[self.catalog.index_by_id[r.movie_id]] = r.score
        return out
