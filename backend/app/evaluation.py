"""Offline evaluation of the four recommenders on MovieLens (no fabricated numbers).

Protocol
--------
* Per-user temporal split: each user's most recent 20% of ratings (by timestamp) are the
  *test* set; everything earlier is *train*.
* A held-out movie is *relevant* if the user rated it >= RELEVANCE_THRESHOLD (4.0).
* Users are evaluated only if they have >= MIN_TRAIN_RATINGS training ratings and at least
  one relevant test movie.
* Popularity statistics, tag features, item similarities and user signals are built from
  *train only*. Tags a user wrote on a test movie are dropped to avoid leakage.
* A user's query contains only the movies they rated >= 4.0 in train ("liked" signal). Explicit
  dislikes are NOT used here: on validation data they lowered offline accuracy because a 2-star
  movie still tells you what the user watches. The app still honours dislikes (product requirement);
  this protocol simply cannot measure that benefit.
* For every user we rank all movies they have not rated in train (movies with >= MIN_ITEM_TRAIN_RATINGS
  training ratings) and take the top K.
* Hyper-parameters (CF neighbourhood size / damping and the hybrid weights) are chosen on a
  *validation* split carved out of train (never on test).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd

from .catalog import Catalog
from .dataset import RawData
from .engine.recommender import Query, Recommender

RELEVANCE_THRESHOLD = 4.0
DISLIKE_THRESHOLD = 2.0
MIN_TRAIN_RATINGS = 5
MIN_ITEM_TRAIN_RATINGS = 5
TEST_FRACTION = 0.2
VALIDATION_FRACTION = 0.15
DEFAULT_K = 10
METHODS = ("random", "popular", "content", "collaborative", "hybrid")


def temporal_split(ratings: pd.DataFrame, test_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Each user's latest ``test_fraction`` of ratings (by time, ties by movieId) go to test."""
    ordered = ratings.sort_values(["userId", "timestamp", "movieId"]).reset_index(drop=True)
    pos = ordered.groupby("userId").cumcount()
    n = ordered.groupby("userId")["movieId"].transform("size")
    n_test = np.ceil(n * test_fraction).astype(int)
    is_test = pos >= (n - n_test)
    return ordered[~is_test].reset_index(drop=True), ordered[is_test].reset_index(drop=True)


def _dcg(hits: list[int]) -> float:
    return sum(h / math.log2(i + 2) for i, h in enumerate(hits))


def user_metrics(recommended: list[int], relevant: set[int], k: int) -> dict[str, float]:
    top = recommended[:k]
    hits = [1 if m in relevant else 0 for m in top]
    n_hit = sum(hits)
    ideal = _dcg([1] * min(len(relevant), k))
    return {
        "precision": n_hit / k,
        "recall": n_hit / len(relevant),
        "ndcg": _dcg(hits) / ideal if ideal else 0.0,
        "hit_rate": 1.0 if n_hit else 0.0,
    }


def build_user_queries(train: pd.DataFrame, max_likes: int | None = None) -> dict[int, Query]:
    """Each user's training history as a Query: liked = rated >= 4.0, everything seen is excluded.

    ``max_likes`` simulates a user who has only told the system about their first N liked movies
    (the thin-signal regime a brand-new app user is in); seen movies are still excluded.
    """
    queries: dict[int, Query] = {}
    for uid, g in train.sort_values("timestamp").groupby("userId"):
        liked = g.loc[g["rating"] >= RELEVANCE_THRESHOLD, "movieId"].astype(int).tolist()
        queries[int(uid)] = Query(
            liked=liked if max_likes is None else liked[:max_likes],
            exclude_ids=set(g["movieId"].astype(int)),
            novelty=0.0,
            min_ratings=MIN_ITEM_TRAIN_RATINGS,
        )
    return queries


@dataclass
class PreparedSplit:
    """Models trained on one train split, ready to score users (so weights can be swept cheaply)."""

    rec: Recommender
    queries: dict[int, Query]
    relevant: dict[int, set[int]]
    users: list[int]
    all_ids: np.ndarray
    n_test: int
    n_train: int


def prepare_split(
    raw: RawData, train: pd.DataFrame, test: pd.DataFrame, knn: dict, max_likes: int | None = None
) -> PreparedSplit:
    # leakage guard: tags a user wrote on a movie they rated in the test set are removed
    test_pairs = set(zip(test["userId"], test["movieId"]))
    keep = [(u, m) not in test_pairs for u, m in zip(raw.tags["userId"], raw.tags["movieId"])]
    train_raw = RawData(raw.movies, train, raw.tags[keep], raw.links)
    catalog = Catalog.build(train_raw, train)
    rec = Recommender(catalog, train, knn)

    train_counts = train.groupby("userId").size()
    relevant = (
        test[test["rating"] >= RELEVANCE_THRESHOLD]
        .groupby("userId")["movieId"]
        .apply(lambda s: set(s.astype(int)))
        .to_dict()
    )
    queries = build_user_queries(train, max_likes)
    users = sorted(
        u for u in relevant
        if train_counts.get(u, 0) >= MIN_TRAIN_RATINGS and u in queries and (max_likes is None or len(queries[u].liked) >= max_likes)
    )
    all_ids = np.array([m.movie_id for m in catalog.movies if m.n_ratings >= MIN_ITEM_TRAIN_RATINGS])
    return PreparedSplit(rec, queries, relevant, users, all_ids, len(test), len(train))


def score_split(
    prep: PreparedSplit,
    k: int = DEFAULT_K,
    hybrid_weights: dict | None = None,
    methods: tuple[str, ...] = METHODS,
    seed: int = 42,
) -> dict:
    rng = np.random.default_rng(seed)
    per_method: dict[str, list[dict[str, float]]] = {m: [] for m in methods}
    recommended: dict[str, set[int]] = {m: set() for m in methods}
    for uid in prep.users:
        base = prep.queries[uid]
        for method in methods:
            if method == "random":
                pool = np.setdiff1d(prep.all_ids, np.fromiter(base.exclude_ids, dtype=int))
                top = rng.choice(pool, size=k, replace=False).tolist()
            else:
                q = Query(**{**base.__dict__, "strategy": method, "k": k,
                             "weights": hybrid_weights if method == "hybrid" else None})
                top = [r.movie_id for r in prep.rec.rank(q).recommendations]
            per_method[method].append(user_metrics(top, prep.relevant[uid], k))
            recommended[method].update(top)

    metrics = {}
    for method, rows in per_method.items():
        df = pd.DataFrame(rows)
        metrics[method] = {
            **{c: float(df[c].mean()) for c in df.columns},
            **{f"{c}_std": float(df[c].std(ddof=1)) for c in df.columns},
            "catalogue_coverage": len(recommended[method]) / max(1, len(prep.all_ids)),
        }
    paired = {}
    for a, b in (("hybrid", "collaborative"), ("collaborative", "popular"), ("hybrid", "popular"), ("popular", "content")):
        if a in per_method and b in per_method:
            diff = np.array([x["ndcg"] - y["ndcg"] for x, y in zip(per_method[a], per_method[b])])
            se = float(diff.std(ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else float("nan")
            paired[f"{a}_minus_{b}"] = {
                "mean_ndcg_difference": float(diff.mean()),
                "ci95_low": float(diff.mean() - 1.96 * se),
                "ci95_high": float(diff.mean() + 1.96 * se),
                "significant_at_95": bool(abs(diff.mean()) > 1.96 * se),
            }
    return {
        "metrics": metrics,
        "paired_comparisons": paired,
        "n_users_evaluated": len(prep.users),
        "n_test_interactions": prep.n_test,
        "n_relevant_test_interactions": int(sum(len(prep.relevant[u]) for u in prep.users)),
        "n_train_interactions": prep.n_train,
        "n_candidate_items": int(len(prep.all_ids)),
    }


KNN_GRID = [
    {"k": kk, "shrinkage": sh, "damping": 0.5, "similarity": sim}
    for sim, kk, sh in product(("binary", "liked"), (100, 200), (5.0, 20.0))
]
WEIGHT_GRID = [
    {"content": c, "collaborative": cf, "popularity": p}
    for c, cf, p in [
        (0.30, 0.35, 0.35), (0.20, 0.50, 0.30), (0.10, 0.60, 0.30), (0.10, 0.70, 0.20),
        (0.05, 0.80, 0.15), (0.00, 0.85, 0.15), (0.15, 0.75, 0.10), (0.05, 0.90, 0.05),
        (0.00, 1.00, 0.00), (0.10, 0.50, 0.40),
    ]
]


THIN_LIKES = 3
THIN_WEIGHT_GRID = [
    {"content": c, "collaborative": cf, "popularity": p}
    for c, cf, p in [
        (0.0, 1.0, 0.0), (0.1, 0.8, 0.1), (0.2, 0.6, 0.2), (0.3, 0.5, 0.2), (0.4, 0.4, 0.2),
        (0.5, 0.3, 0.2), (0.3, 0.3, 0.4), (0.2, 0.4, 0.4), (0.6, 0.2, 0.2), (0.0, 0.5, 0.5),
    ]
]


def tune_thin_weights(raw: RawData, train: pd.DataFrame, knn: dict, k: int = DEFAULT_K) -> tuple[dict, list[dict]]:
    """Choose hybrid weights for users with only THIN_LIKES liked movies, on the validation split."""
    sub_train, validation = temporal_split(train, VALIDATION_FRACTION)
    prep = prepare_split(raw, sub_train, validation, knn, max_likes=THIN_LIKES)
    log, best, best_ndcg = [], THIN_WEIGHT_GRID[0], -1.0
    for weights in THIN_WEIGHT_GRID:
        ndcg = score_split(prep, k, hybrid_weights=weights, methods=("hybrid",))["metrics"]["hybrid"]["ndcg"]
        log.append({"stage": "thin_hybrid", "weights": weights, "validation_ndcg": ndcg, "n_users": len(prep.users)})
        if ndcg > best_ndcg:
            best, best_ndcg = weights, ndcg
    return best, log


def tune_on_validation(raw: RawData, train: pd.DataFrame, k: int = DEFAULT_K) -> tuple[dict, dict, list[dict]]:
    """Pick CF settings (on the CF recommender alone) then hybrid weights, on a validation split of train."""
    sub_train, validation = temporal_split(train, VALIDATION_FRACTION)
    log: list[dict] = []
    best_knn, best_cf = KNN_GRID[0], -1.0
    for knn in KNN_GRID:
        prep = prepare_split(raw, sub_train, validation, knn)
        ndcg = score_split(prep, k, methods=("collaborative",))["metrics"]["collaborative"]["ndcg"]
        log.append({"stage": "cf", "knn": knn, "validation_ndcg": ndcg})
        if ndcg > best_cf:
            best_knn, best_cf = knn, ndcg
    prep = prepare_split(raw, sub_train, validation, best_knn)
    best_w, best_h = WEIGHT_GRID[0], -1.0
    for weights in WEIGHT_GRID:
        ndcg = score_split(prep, k, hybrid_weights=weights, methods=("hybrid",))["metrics"]["hybrid"]["ndcg"]
        log.append({"stage": "hybrid", "weights": weights, "validation_ndcg": ndcg})
        if ndcg > best_h:
            best_w, best_h = weights, ndcg
    return best_knn, best_w, log


def run_full_evaluation(raw: RawData, k: int = DEFAULT_K, tune: bool = True) -> dict:
    train, test = temporal_split(raw.ratings, TEST_FRACTION)
    if tune:
        knn, weights, log = tune_on_validation(raw, train, k)
    else:
        knn, weights, log = KNN_GRID[0], None, []
    result = score_split(prepare_split(raw, train, test, knn), k, hybrid_weights=weights)

    thin_weights, thin_log = (tune_thin_weights(raw, train, knn, k) if tune else (None, []))
    thin_prep = prepare_split(raw, train, test, knn, max_likes=THIN_LIKES)
    thin = score_split(thin_prep, k, hybrid_weights=thin_weights, methods=("popular", "content", "collaborative", "hybrid"))
    # same users, but the hybrid with the *warm* weights, to show why the thin regime needs its own
    thin_warm = score_split(thin_prep, k, hybrid_weights=weights, methods=("hybrid",))
    thin["metrics"]["hybrid_warm_weights"] = thin_warm["metrics"]["hybrid"]
    thin["max_likes"] = THIN_LIKES
    thin["chosen_weights"] = thin_weights
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "MovieLens ml-latest-small",
        "protocol": {
            "split": f"per-user temporal, latest {int(TEST_FRACTION * 100)}% of each user's ratings held out",
            "relevance": f"held-out rating >= {RELEVANCE_THRESHOLD}",
            "k": k,
            "min_train_ratings_per_user": MIN_TRAIN_RATINGS,
            "min_train_ratings_per_item": MIN_ITEM_TRAIN_RATINGS,
            "seed": 42,
            "validation_fraction_of_train": VALIDATION_FRACTION,
        },
        "chosen_config": {"knn": knn, "hybrid_weights": weights},
        "tuning": log + thin_log,
        "few_likes": thin,
        **result,
    }


def save_report(result: dict, reports_dir) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "evaluation.json").write_text(json.dumps(result, indent=2))
