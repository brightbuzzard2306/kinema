# Offline evaluation report

Generated: 2026-10-09T08:07:49+00:00 - dataset: MovieLens ml-latest-small. Every number below comes from
`python -m scripts.run_evaluation`; nothing is hand-written or hard-coded.

## Protocol

- **Split:** per-user temporal, latest 20% of each user's ratings held out. Ties on timestamp are broken by movieId so the split is deterministic.
- **Relevant item:** held-out rating >= 4.0.
- **Eligible users:** at least 5 training ratings and at least one relevant held-out movie.
- **Candidate items:** movies with at least 5 *training* ratings that the user has not already rated in train.
- **Leakage controls:** popularity statistics, tag features, item similarities and user profiles are computed from the
  training ratings only; tags a user wrote on a movie in their test set are removed.
- **Signals used:** each user's query contains the movies they rated >= 4.0 in train. Explicit dislikes are not used offline
  (see Limitations).
- **Tuning:** CF settings and hybrid weights were chosen on a validation split carved from the training data
  (latest 15% of each user's train ratings) - never on the test set.
- **Reproducibility:** deterministic split and models; random baseline seed = 42.

## Dataset

| Quantity | Value |
|---|---|
| Training interactions | 80,419 |
| Test interactions | 20,417 |
| Relevant test interactions (evaluated users) | 9,509 |
| Users evaluated | 592 |
| Candidate movies | 3,034 |

## Results (K = 10, mean over users)

| Method | Precision@10 | Recall@10 | NDCG@10 | Hit rate@10 | Catalogue coverage |
|---|---|---|---|---|---|
| Random (sanity floor) | 0.0044 | 0.0021 | 0.0046 | 0.039 | 0.850 |
| Popularity (Bayesian) | 0.0615 | 0.0510 | 0.0798 | 0.333 | 0.026 |
| Content-based (TF-IDF) | 0.0074 | 0.0063 | 0.0086 | 0.068 | 0.244 |
| Collaborative (item-item) | 0.0860 | 0.0751 | 0.1048 | 0.438 | 0.081 |
| Hybrid | 0.0840 | 0.0761 | 0.1080 | 0.443 | 0.082 |

Highest NDCG@10: **Hybrid**.

Chosen settings - CF: k=200 neighbours, shrinkage=5.0, similarity=liked;
hybrid weights: content=0.05, collaborative=0.90, popularity=0.05.


## Few-likes regime (a new user who has named only 3 liked movies)

Each evaluated user is reduced to their **first 3 liked movies** (chronologically) - the situation of someone in their first minutes with
the app. Same split, same relevance rule, 589 users who have at least 3 liked training movies.
Hybrid weights for this regime were tuned on validation data separately from the warm-user weights.

| Method | Precision@10 | Recall@10 | NDCG@10 | Hit rate@10 |
|---|---|---|---|---|
| Popularity | 0.0618 | 0.0512 | 0.0802 | 0.334 |
| Content-based | 0.0095 | 0.0050 | 0.0107 | 0.088 |
| Collaborative | 0.0591 | 0.0582 | 0.0782 | 0.345 |
| Hybrid, warm-user weights | 0.0601 | 0.0584 | 0.0790 | 0.357 |
| Hybrid, few-likes weights | 0.0626 | 0.0537 | 0.0777 | 0.346 |

Chosen few-likes weights: content=0.20, collaborative=0.40, popularity=0.40.

Few-likes weight sweep (NDCG@10 on validation):

| content | collaborative | popularity | NDCG |
|---|---|---|---|
| 0.00 | 1.00 | 0.00 | 0.0743 |
| 0.10 | 0.80 | 0.10 | 0.0761 |
| 0.20 | 0.60 | 0.20 | 0.0736 |
| 0.30 | 0.50 | 0.20 | 0.0618 |
| 0.40 | 0.40 | 0.20 | 0.0447 |
| 0.50 | 0.30 | 0.20 | 0.0323 |
| 0.30 | 0.30 | 0.40 | 0.0670 |
| 0.20 | 0.40 | 0.40 | 0.0773 |
| 0.60 | 0.20 | 0.20 | 0.0252 |
| 0.00 | 0.50 | 0.50 | 0.0764 |

### Paired differences in NDCG@10 (per-user, normal-approximation 95% CI)

| Comparison | Mean difference | 95% CI | Significant? |
|---|---|---|---|
| hybrid - collaborative | +0.0031 | [-0.0032, +0.0094] | no |
| collaborative - popular | +0.0251 | [+0.0143, +0.0359] | yes |
| hybrid - popular | +0.0282 | [+0.0171, +0.0393] | yes |
| popular - content | +0.0712 | [+0.0594, +0.0829] | yes |

### Metric definitions

- **Precision@K** = (relevant movies in the top K) / K.
- **Recall@K** = (relevant movies in the top K) / (all relevant held-out movies of the user).
- **NDCG@K** = DCG@K / IDCG@K, where DCG@K = sum over ranks i=1..K of rel_i / log2(i+1) with binary rel; rewards putting hits near the top.
- **Hit rate@K** = share of users with at least one relevant movie in the top K.
- **Catalogue coverage** = share of candidate movies that were recommended to at least one user (diversity indicator).

## Validation sweeps (used to pick the settings above)

Collaborative filtering (NDCG@10 on validation):

| similarity | neighbours k | shrinkage | NDCG |
|---|---|---|---|
| binary | 100 | 5.0 | 0.1015 |
| binary | 100 | 20.0 | 0.1088 |
| binary | 200 | 5.0 | 0.0999 |
| binary | 200 | 20.0 | 0.1094 |
| liked | 100 | 5.0 | 0.1075 |
| liked | 100 | 20.0 | 0.1064 |
| liked | 200 | 5.0 | 0.1121 |
| liked | 200 | 20.0 | 0.1095 |

Hybrid weights (NDCG@10 on validation):

| content | collaborative | popularity | NDCG |
|---|---|---|---|
| 0.30 | 0.35 | 0.35 | 0.0831 |
| 0.20 | 0.50 | 0.30 | 0.0938 |
| 0.10 | 0.60 | 0.30 | 0.0980 |
| 0.10 | 0.70 | 0.20 | 0.1015 |
| 0.05 | 0.80 | 0.15 | 0.1060 |
| 0.00 | 0.85 | 0.15 | 0.0992 |
| 0.15 | 0.75 | 0.10 | 0.1047 |
| 0.05 | 0.90 | 0.05 | 0.1158 |
| 0.00 | 1.00 | 0.00 | 0.1121 |
| 0.10 | 0.50 | 0.40 | 0.0932 |

## Interpretation

- Ranking by NDCG: Hybrid (0.108) > Collaborative (item-item) (0.105) > Popularity (Bayesian) (0.080) > Content-based (TF-IDF) (0.009) > Random (sanity floor) (0.005).
- Random scores 0.005, so every real method carries signal.
- Collaborative filtering beats the popularity baseline (0.105 vs 0.080), so personalised rating patterns add value beyond 'what is generally liked'.
- Content-based filtering alone is the weakest real method (0.009). Genres/tags/title words describe *what a movie is*, not *whether people like it*, and TF-IDF rewards rare features, which favours obscure movies with few hits. Its value is cold start (new movies, no ratings) and explainability, which this offline test cannot show.
- The hybrid (0.108) scores higher than collaborative filtering alone (0.105), but the paired difference is NOT statistically significant at the 95% level, so treat them as comparable. Validation tuning gave the collaborative component most of the weight.
- With only 3 liked movies per user, NDCG@10 is: Popularity 0.080, Content-based 0.011, Collaborative 0.078, Hybrid 0.078. The best single score is Popularity; popularity is hard to beat when personalised evidence is this thin.
- The few-likes hybrid weights (0.078) are indistinguishable from the warm-user weights (0.079) on this offline metric, so this test does NOT show that a separate thin-signal weighting improves accuracy. The app still uses them because they put more weight on quality/popularity (safer when only a movie or two is known) and add content similarity, which makes the reasons explainable; that is a design choice, not a measured gain.
- Coverage: popularity recommends only 2.6% of the candidate catalogue, collaborative 8.1%, hybrid 8.2% - accuracy and diversity pull in opposite directions.

## Limitations

- **Small, old dataset:** 610 users and about 9.7k movies; confidence intervals are wide (see `*_std` in `evaluation.json`).
- **Offline relevance is a proxy:** a held-out rating >= 4 means "the user watched and liked it", not "this recommendation would have been
  the best possible". Movies the user would have loved but never rated count as misses.
- **Popularity is strong on MovieLens:** users mostly rate movies that are already widely rated, so predicting popular movies scores well.
- **Per-user temporal split leaks the global timeline:** other users' later ratings are in training. A single global time cut would avoid
  that but leaves too few users with both history and future data in this dataset.
- **Dislikes are not validated offline:** when used as a negative signal they reduced offline accuracy (a 2-star rating still reveals taste).
  The app keeps them because users expect "I didn't like this" to demote similar movies; that benefit is a product behaviour, not an offline metric.
- **Cold-start users are not evaluated here:** the protocol requires training history. The onboarding flow is tested functionally, not by these metrics.
- **Content features are limited:** only genres, user-written tags and title words are available (no plot text, cast or director).
