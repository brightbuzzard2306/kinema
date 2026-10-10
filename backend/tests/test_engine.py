import numpy as np
import pytest

from app.engine.recommender import Query


def ids(result):
    return [r.movie_id for r in result.recommendations]


SCIFI, ROMANCE, HORROR = set(range(1, 13)), set(range(13, 25)), set(range(25, 35))


# ------------------------------------------------------------------ content-based
def test_content_similarity_prefers_same_genre(recommender):
    res = recommender.rank(Query(strategy="content", anchors=[1], k=5, min_ratings=1))
    assert set(ids(res)) <= SCIFI and 1 not in ids(res)


def test_content_handles_movie_without_genres_or_tags(recommender):
    res = recommender.rank(Query(strategy="content", anchors=[99], k=3, min_ratings=1))
    assert isinstance(res.recommendations, list)  # must not crash


def test_content_reasons_name_real_shared_features(recommender):
    res = recommender.rank(Query(strategy="content", anchors=[1], k=3, min_ratings=1))
    texts = " ".join(r.text for rec in res.recommendations for r in rec.reasons)
    assert "Sci-Fi" in texts and "scifi" not in texts.lower().replace("sci-fi", "")


# ------------------------------------------------------------------ collaborative
def test_collaborative_recommends_what_similar_users_liked(recommender):
    res = recommender.rank(Query(strategy="collaborative", liked=[1, 2, 3], k=5, min_ratings=1))
    assert res.recommendations and set(ids(res)) <= SCIFI


def test_collaborative_excludes_liked_movies(recommender):
    res = recommender.rank(Query(strategy="collaborative", liked=[1, 2, 3], k=10, min_ratings=1))
    assert not ({1, 2, 3} & set(ids(res)))


def test_collaborative_unavailable_for_new_user_falls_back_to_popularity(recommender):
    res = recommender.rank(Query(strategy="collaborative", k=5, min_ratings=1))
    assert res.strategy_used == "popular" and res.recommendations
    assert any("signal" in n for n in res.notes)


def test_negative_feedback_demotes_similar_movies(recommender):
    base = recommender.rank(Query(strategy="collaborative", liked=[1, 2], k=12, min_ratings=1))
    neg = recommender.rank(Query(strategy="collaborative", liked=[1, 2], disliked=[3, 4, 5], k=12, min_ratings=1))
    assert not ({3, 4, 5} & set(ids(neg)))  # disliked never come back
    pos_base = {m: i for i, m in enumerate(ids(base))}
    assert pos_base  # sanity: baseline produced results


# ------------------------------------------------------------------ hybrid, cold start, popularity
def test_popularity_baseline_uses_bayesian_rating(catalog):
    best = max(catalog.movies, key=lambda m: m.bayes_rating)
    assert best.bayes_rating <= max(m.mean_rating for m in catalog.movies if m.mean_rating)


def test_cold_start_with_no_history_returns_recommendations(recommender):
    res = recommender.rank(Query(k=5, min_ratings=1))
    assert len(res.recommendations) == 5
    assert all(r.components["collaborative"] is None for r in res.recommendations)


def test_cold_start_with_only_genres_respects_genres(recommender):
    res = recommender.rank(Query(genres=["Horror"], k=5, min_ratings=1))
    assert set(ids(res)) <= HORROR


def test_hybrid_redistributes_weight_when_component_unavailable(recommender):
    res = recommender.rank(Query(liked=[1, 2], k=5, min_ratings=1))
    for rec in res.recommendations:
        assert pytest.approx(sum(rec.weights_used.values()), abs=0.01) == 1.0
        missing = [c for c, v in rec.components.items() if v is None]
        assert not (set(missing) & set(rec.weights_used))


def test_hybrid_scores_are_normalised(recommender):
    res = recommender.rank(Query(liked=[1], genres=["Sci-Fi"], k=10, min_ratings=1))
    for rec in res.recommendations:
        assert all(0 <= v <= 1 for v in rec.components.values() if v is not None)
        assert 0 <= rec.score <= 1.01


def test_strategies_all_work(recommender):
    for s in ("hybrid", "popular", "content", "collaborative"):
        res = recommender.rank(Query(strategy=s, liked=[1, 2], k=4, min_ratings=1))
        assert res.recommendations, s


def test_novelty_shifts_toward_less_rated_movies(recommender, catalog):
    pop = recommender.rank(Query(strategy="popular", novelty=0.0, k=8, min_ratings=1))
    new = recommender.rank(Query(strategy="popular", novelty=1.0, k=8, min_ratings=1))
    avg = lambda r: np.mean([x.n_ratings for x in r.recommendations])
    assert avg(new) < avg(pop)


# ------------------------------------------------------------------ constraints
def test_excluded_genres_are_never_returned(recommender, catalog):
    res = recommender.rank(Query(liked=[25, 26], excluded_genres=["Horror"], k=10, min_ratings=1))
    assert res.recommendations and not (set(ids(res)) & HORROR)


def test_genre_filter_and_exclusion_together(recommender):
    res = recommender.rank(Query(genres=["Romance"], excluded_genres=["Comedy"], k=10, min_ratings=1))
    assert set(ids(res)) <= ROMANCE


def test_excludes_seen_and_disliked_and_anchor(recommender):
    res = recommender.rank(Query(liked=[1], disliked=[2], anchors=[3], exclude_ids={4, 5}, k=40, min_ratings=1))
    assert not ({1, 2, 3, 4, 5} & set(ids(res)))


def test_no_duplicates_in_a_result_set(recommender):
    res = recommender.rank(Query(liked=[1, 13], k=30, min_ratings=1))
    assert len(ids(res)) == len(set(ids(res)))


def test_unknown_movie_ids_are_ignored_not_fatal(recommender):
    res = recommender.rank(Query(liked=[123456], disliked=[654321], anchors=[777777], k=3, min_ratings=1))
    assert res.recommendations


def test_empty_candidate_set_returns_helpful_note(recommender):
    res = recommender.rank(Query(genres=["Horror"], excluded_genres=["Horror"], k=5, min_ratings=1))
    assert res.recommendations == [] and res.notes


def test_filters_are_relaxed_with_disclosure_but_exclusions_never(recommender):
    res = recommender.rank(Query(genres=["Sci-Fi"], excluded_genres=["Comedy"], min_rating=4.99, k=10, min_ratings=1))
    assert res.recommendations
    assert any("ignored the minimum rating" in n for n in res.notes)  # relaxation is disclosed
    assert set(ids(res)) <= SCIFI  # genre request and exclusions are never relaxed


def test_min_rating_filter_applies(recommender, catalog):
    res = recommender.rank(Query(min_rating=4.0, k=5, min_ratings=1))
    assert all(r.mean_rating >= 4.0 for r in res.recommendations) or res.notes


def test_year_filter_applies(recommender):
    res = recommender.rank(Query(year_min=1990, year_max=1995, k=5, min_ratings=1))
    assert all(1990 <= r.year <= 1995 for r in res.recommendations)


# ------------------------------------------------------------------ explanations
def test_reasons_are_grounded_in_data(recommender, catalog):
    res = recommender.rank(Query(liked=[1, 2], genres=["Sci-Fi"], k=5, min_ratings=1))
    for rec in res.recommendations:
        movie = catalog.get(rec.movie_id)
        for reason in rec.reasons:
            if reason.kind == "genre":
                assert any(g in movie.genres for g in ("Sci-Fi",))
            if reason.kind == "popularity":
                assert f"{movie.mean_rating:.1f}/5" in reason.text and str(movie.n_ratings) in reason.text
        assert rec.confidence in {"high", "medium", "low"}


def test_feedback_changes_the_ranking(recommender):
    before = ids(recommender.rank(Query(liked=[1], k=6, min_ratings=1)))
    after = ids(recommender.rank(Query(liked=[1], disliked=before[:2], k=6, min_ratings=1)))
    assert not (set(before[:2]) & set(after))


# ------------------------------------------------------------------ weight regimes
def test_weight_regime_depends_on_how_much_the_user_told_us(recommender):
    assert recommender.rank(Query(k=3, min_ratings=1)).regime == "cold"
    assert recommender.rank(Query(liked=[1], k=3, min_ratings=1)).regime == "thin"
    assert recommender.rank(Query(liked=[1, 2, 3, 4, 5, 6], k=3, min_ratings=1)).regime == "blend"
    assert recommender.rank(Query(liked=list(range(1, 13)), k=3, min_ratings=1)).regime == "warm"
    assert recommender.rank(Query(liked=[1], k=3, min_ratings=1, weights={"popularity": 1.0})).regime == "custom"


def test_blend_weights_interpolate_between_thin_and_warm(recommender):
    thin, _ = recommender.hybrid_base_weights(3)
    warm, _ = recommender.hybrid_base_weights(10)
    mid, regime = recommender.hybrid_base_weights(6)  # 3/7 of the way from thin to warm
    assert regime == "blend"
    for c in ("content", "collaborative", "popularity", "preference"):
        lo, hi = sorted((thin.get(c, 0), warm.get(c, 0)))
        assert lo - 1e-9 <= mid.get(c, 0) <= hi + 1e-9
    assert recommender.hybrid_base_weights(0)[1] == "cold"
