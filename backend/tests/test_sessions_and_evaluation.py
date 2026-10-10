import json

import numpy as np
import pytest

from app.evaluation import (
    PreparedSplit,
    prepare_split,
    score_split,
    temporal_split,
    user_metrics,
)
from app.posters import PosterService
from app.schemas import ProfileUpdate
from app.sessions import SessionStore

GENRES, IDS = {"Sci-Fi", "Comedy"}, {1, 2, 3}


# ------------------------------------------------------------------ sessions & feedback
def test_feedback_is_idempotent_and_exclusive():
    store = SessionStore()
    s = store.get("session-aaaa")
    for _ in range(3):
        SessionStore.apply_feedback(s, 5, "like")
    assert s.profile.liked_ids == [5]  # not triple-counted
    SessionStore.apply_feedback(s, 5, "dislike")
    assert s.profile.liked_ids == [] and s.profile.disliked_ids == [5]
    SessionStore.apply_feedback(s, 5, "clear")
    assert s.profile.disliked_ids == []


def test_sessions_are_isolated():
    store = SessionStore()
    a, b = store.get("session-aaaa"), store.get("session-bbbb")
    SessionStore.apply_feedback(a, 1, "like")
    assert b.profile.liked_ids == []


def test_profile_update_validates_and_resolves_conflicts():
    store = SessionStore()
    s = store.get("session-aaaa")
    store.apply_update(s, ProfileUpdate(genres=["Sci-Fi", "Nonsense"], excluded_genres=["Comedy"], liked_ids=[1, 999]), GENRES, IDS)
    assert s.profile.genres == ["Sci-Fi"] and s.profile.excluded_genres == ["Comedy"] and s.profile.liked_ids == [1]
    store.apply_update(s, ProfileUpdate(excluded_genres=["Sci-Fi"]), GENRES, IDS)
    assert "Sci-Fi" not in s.profile.genres  # an excluded genre can't also be wanted
    store.apply_update(s, ProfileUpdate(min_rating=None), GENRES, IDS)  # explicit null clears
    assert s.profile.min_rating is None


def test_sessions_persist_and_survive_corrupt_file(tmp_path):
    path = tmp_path / "s.json"
    store = SessionStore(path)
    s = store.get("session-aaaa")
    SessionStore.apply_feedback(s, 2, "like")
    store.save(s)
    assert SessionStore(path).get("session-aaaa").profile.liked_ids == [2]
    path.write_text("{ not json")
    assert SessionStore(path).get("session-aaaa").profile.liked_ids == []  # no crash
    path.write_text(json.dumps({"x": {"broken": True}}))
    assert SessionStore(path).get("x").profile.liked_ids == []


def test_reset_clears_history_but_can_keep_profile():
    store = SessionStore()
    s = store.get("session-aaaa")
    SessionStore.apply_feedback(s, 1, "like")
    s.shown_ids = [1, 2]
    store.save(s)
    fresh = store.reset("session-aaaa", keep_profile=True)
    assert fresh.shown_ids == [] and fresh.profile.liked_ids == [1]
    assert store.reset("session-aaaa", keep_profile=False).profile.liked_ids == []


# ------------------------------------------------------------------ evaluation
def test_user_metrics_known_values():
    m = user_metrics([1, 2, 3, 4], {1, 3, 9}, k=4)
    assert m["precision"] == 0.5 and m["recall"] == pytest.approx(2 / 3) and m["hit_rate"] == 1.0
    dcg = 1 / np.log2(2) + 1 / np.log2(4)
    idcg = 1 / np.log2(2) + 1 / np.log2(3) + 1 / np.log2(4)
    assert m["ndcg"] == pytest.approx(dcg / idcg)
    assert user_metrics([7, 8], {1}, k=2) == {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "hit_rate": 0.0}


def test_temporal_split_has_no_leakage(raw):
    train, test = temporal_split(raw.ratings, 0.2)
    assert len(train) + len(test) == len(raw.ratings)
    last_train = train.groupby("userId")["timestamp"].max()
    first_test = test.groupby("userId")["timestamp"].min()
    assert (last_train.loc[first_test.index] <= first_test).all()
    assert not set(zip(train.userId, train.movieId)) & set(zip(test.userId, test.movieId))


def test_evaluation_is_reproducible_and_beats_random(raw):
    train, test = temporal_split(raw.ratings, 0.2)
    knn = {"k": 30, "shrinkage": 2.0, "similarity": "liked"}

    def run():
        prep = prepare_split(raw, train, test, knn)
        return score_split(prep, k=5)

    a, b = run(), run()
    assert a["metrics"] == b["metrics"]
    assert a["n_users_evaluated"] > 0 and a["n_relevant_test_interactions"] > 0
    assert a["metrics"]["collaborative"]["ndcg"] > a["metrics"]["random"]["ndcg"]
    assert set(a["metrics"]) == {"random", "popular", "content", "collaborative", "hybrid"}


def test_evaluation_candidates_never_include_training_items(raw):
    train, test = temporal_split(raw.ratings, 0.2)
    prep: PreparedSplit = prepare_split(raw, train, test, {"k": 30, "shrinkage": 2.0})
    uid = prep.users[0]
    seen = set(train.loc[train.userId == uid, "movieId"])
    top = prep.rec.rank(__import__("app.engine.recommender", fromlist=["Query"]).Query(**{**prep.queries[uid].__dict__, "k": 40}))
    assert not seen & {r.movie_id for r in top.recommendations}


# ------------------------------------------------------------------ posters
def test_posters_disabled_without_key(tmp_path):
    svc = PosterService(None, tmp_path / "p.json")
    assert not svc.enabled and svc.lookup({1: 862}) == {1: None}


def test_posters_fetch_and_cache(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return __import__("httpx").Response(200, json={"poster_path": "/abc.jpg"})

    import httpx

    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = PosterService("key123", tmp_path / "p.json", client)
    assert svc.lookup({1: 862})[1] == "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert svc.lookup({1: 862})[1].endswith("/abc.jpg") and len(calls) == 1  # second lookup served from cache
    assert json.loads((tmp_path / "p.json").read_text())["862"].endswith("/abc.jpg")


def test_poster_errors_are_not_cached(tmp_path):
    import httpx

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    svc = PosterService("key", tmp_path / "p.json", client)
    assert svc.lookup({1: 862}) == {1: None}
    assert "862" not in svc._cache  # transient failure must be retried later
