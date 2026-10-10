# Algorithms, in plain language

Everything here is implemented in `backend/app/engine/` and `backend/app/catalog.py`. Nothing is described that isn't in the code.

## 0. Why an LLM alone is not a recommender

A language model (Claude) can *talk* about movies, but it has no access to our ratings, can't be evaluated against held-out data, may invent titles or facts, and gives different answers each time. A recommender system must rank items using **data about user behaviour**, be **reproducible**, and be **measurable**. So here Claude only (1) turns your sentence into structured preferences and (2) phrases the reply. The ranking comes from the algorithms below, and the reply is rejected if it states a number that the engine didn't produce.

## 1. Popularity baseline (Bayesian average)

Average rating alone is misleading: a movie with one 5★ rating would beat *The Godfather*. We shrink every movie's average toward the global mean `C` with a prior worth `m = 25` ratings:

```
bayes(i) = ( v_i / (v_i + m) ) * R_i  +  ( m / (v_i + m) ) * C
```

* `v_i` = number of ratings of movie i · `R_i` = its mean rating · `C` = mean of all ratings · `m` = 25.

Few ratings → the score stays near `C`; many ratings → it approaches the movie's own mean. This is also the **cold-start fallback**: it needs no information about the user.
The hybrid's *popularity component* is `0.5 * quality + 0.5 * volume` (both min-max normalised), where `volume = log(1 + ratings)`. With the discovery slider `novelty ∈ [0,1]` the volume term flips toward lesser-known movies: `(1 - novelty) * volume + novelty * (1 - volume)`.

## 2. Content-based filtering (TF-IDF + cosine)

Each movie becomes a vector from its **real metadata**: genres, user-written tags (`tags.csv`) and title words.

**TF-IDF** (term frequency–inverse document frequency) weighs a term by how characteristic it is: frequent in this movie, rare across all movies.

```
tfidf(t, d) = tf(t, d) * log( N / df(t) )      (scikit-learn uses a smoothed variant)
```

Three blocks are built separately, each L2-normalised, then weighted **genres 1.0, tags 0.6, title 0.25** and concatenated. Normalising each block first stops the block with the most columns (tags) from drowning out genres.

**Cosine similarity** measures the angle between two vectors (1 = same direction, 0 = nothing in common):

```
cos(a, b) = (a · b) / (‖a‖ ‖b‖)
```

The *taste vector* of a user is built Rocchio-style from their signals:

```
q = centroid(liked, anchors×2)  +  0.6 * genre_query  -  0.5 * centroid(disliked)
score_content(i) = cos(q, movie_i)
```

Explanations use the **actual** shared genres and tags between the candidate and the liked movie it most resembles. Movies without genres or tags are handled (they simply have fewer features).

## 3. Collaborative filtering (item-item)

Idea: *movies that the same people like are similar*, regardless of what the movies are about.

1. Build the user × movie matrix from `ratings.csv`. Our default similarity uses **likes only** (rating ≥ 4.0): each movie is a binary vector "who liked it".
2. **Item-item similarity** is the cosine of two movies' vectors, **shrunk** by support so that two movies sharing just 2 fans can't look identical:

```
sim(i, j) = cos(like_i, like_j) * n_ij / (n_ij + λ)          n_ij = users who liked both, λ = 5 (tuned)
```

3. Keep only each movie's top **K = 200** most similar movies.
4. **Prediction (item-based top-N):** every movie `i` the user has a signal `w_i` for "votes" for its neighbours:

```
score(j) = Σ_i  sim(i, j) * w_i   /   ( Σ_i sim(i, j) + 0.5 )
```

   `w_i = +1` liked, `+1.5` for the "more like this" anchor, `-1` disliked. Movies the user already rated/liked/disliked are excluded.

* **New users:** no signals → the component is *unavailable* and its weight is redistributed (see hybrid). **New movies** with no ratings have no neighbours; the content component still covers them.
* We also implemented and compared mean-centred *adjusted cosine* and an "rated at all" binary similarity; the choice (`liked`, K, λ) was made on a **validation split**, not on the test set. We did **not** implement matrix factorisation or neural methods.

## 4. Hybrid

Four component scores are each **min-max normalised among the eligible candidates** (so their scales are comparable):

| Component | Meaning |
|---|---|
| content | cosine to the user's taste vector |
| collaborative | item-item score above |
| popularity | quality + volume (see §1) |
| preference | share of your requested genres the movie matches |

```
final(j) = Σ_c  w_c * s_c(j)  /  Σ_c w_c        summed over components AVAILABLE for candidate j
```

* **Redistribution:** if a component is unavailable for a candidate (e.g. no collaborative evidence), its weight is dropped from both numerator and denominator, so the remaining components are re-weighted automatically.
* **Weights depend on how much the user told us** (`Recommender.hybrid_base_weights`): no liked movies → *cold-start weights* (quality 0.55, preference 0.30, content 0.15); 1–3 likes → *few-likes weights*; 10+ → *warm weights*; in between a linear blend. The warm and few-likes weights come from `reports/evaluation.md` (tuned on validation data) and are scaled to leave 15% for explicit genre preferences. The blend between regimes is a design choice that was not separately validated.
* **Strategies** (`popular`, `content`, `collaborative`) use a single component and fall back to popularity, with a note, if that component has no evidence.

### Filters and relaxation

Hard constraints: excluded genres, movies already shown/liked/disliked, requested genres. Soft constraints, relaxed *in order and always disclosed*: minimum number of ratings → minimum rating −0.5 → release years → minimum rating −1.0 → minimum rating dropped. Exclusions are never relaxed.

### Confidence indicator

A heuristic, not a probability: `0.5 * n/(n+25) + 0.5 * (share of active signals ≥ 0.5)`, labelled high ≥ 0.62, medium ≥ 0.40, else low. The tooltip shows the numbers behind it.

## 5. Cold start

* **No history:** popularity (Bayesian) combined with stated genres.
* **Onboarding** (hero panel): choose genres and a few loved movies; they become the initial profile (`genres`, `liked_ids`) used by content + collaborative + popularity.
* **Typed requests** ("I loved Inception") do the same through the language layer. No login is needed; the profile lives in a session keyed by a random id in `localStorage`.

## 6. Feedback-based personalisation

* 👍 adds the movie to `liked_ids` (removing it from disliked); 👎 does the reverse; clicking again clears it. The operation is idempotent, so repeated clicks never double-count.
* Liked movies feed the taste vector and the collaborative votes; **disliked movies are never recommended again** and enter as negative evidence (`-1` vote, `-0.5` centroid).
* "I didn't like those" marks the last batch as disliked and shifts the discovery slider toward varied picks.
* Offline note: a 2★ rating still reveals taste, so using dislikes as negatives *lowered* offline accuracy on MovieLens. The offline evaluation therefore uses likes only; the benefit of dislikes is a product behaviour that this protocol can't measure.

## 7. Evaluation metrics

For each evaluated user, take the top K = 10 and compare with their *held-out* movies rated ≥ 4:

```
Precision@K = hits / K              Recall@K = hits / (relevant held-out movies)
DCG@K = Σ_{r=1..K} rel_r / log2(r + 1)      NDCG@K = DCG@K / IDCG@K      (IDCG = DCG of a perfect ranking)
HitRate@K = 1 if hits ≥ 1 else 0, averaged over users
```

Protocol, results and limitations: [`reports/evaluation.md`](../reports/evaluation.md) (regenerate with `python -m scripts.run_evaluation`).
