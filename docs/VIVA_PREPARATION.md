# Viva preparation (read this the night before)

## The 30-second pitch

> "Kinema is a conversational movie recommender built on the MovieLens dataset. You describe what you want in plain English; a language model turns that into structured preferences, but the **movies come from a real hybrid recommender** that combines popularity, content-based filtering and item-item collaborative filtering. Every card explains why it was picked, likes and dislikes change the next results, and I evaluated the algorithms offline with Precision, Recall and NDCG."

## Problem statement & objectives

* **Problem:** choosing a movie is slow; plain search needs you to know a title, and chatbots alone can invent movies or ignore data.
* **Objectives:** (1) implement real recommendation algorithms, (2) handle new users (cold start), (3) make it conversational, (4) make recommendations explainable, (5) evaluate honestly.

## Dataset

MovieLens `ml-latest-small`: **9,742 movies, 100,836 ratings, 610 users**, 3,683 tag applications; ratings 0.5–5. Features used: genres, user tags, title words, rating matrix. Not available: runtime, cast, plot, posters (posters are optional via TMDB).

## What each algorithm does & why it's there

| Algorithm | One-line idea | Why we need it |
|---|---|---|
| Popularity (Bayesian) | Rank by average rating, shrunk toward the global mean for movies with few ratings | Baseline; works for brand-new users |
| Content-based | Recommend movies whose genres/tags/title look like what you liked (TF-IDF + cosine) | Works for new movies; explainable |
| Collaborative (item-item) | Movies liked by the same people are similar | Finds taste patterns metadata can't see |
| Hybrid | Weighted blend of the above, with weights re-distributed when a signal is missing | More robust than any one method |

## Role of Claude vs the engine (very likely question)

* **Claude:** reads your message → JSON of preferences (genres, liked/disliked titles, min rating…); writes the short reply. It runs on the server; the key is never in the browser.
* **Engine:** decides which movies and in what order. Claude never invents a title: every title is looked up in the dataset and unknown ones are dropped; every number in Claude's reply must exist in the data we gave it.
* **No key / failure?** A rule-based parser takes over; recommendations are identical in quality. The UI says "Offline mode" honestly.

## How the pieces answer common behaviours

* **Cold start:** no history → Bayesian popularity + the genres you pick; the onboarding panel (genres + loved movies) builds an initial profile.
* **Likes/dislikes:** a like feeds the taste vector and the collaborative votes; a dislike removes that movie permanently and acts as negative evidence. Repeating a click never double-counts.
* **Explanations:** built from the data (shared genres/tags with a movie you liked; "people who rated X highly also rated this highly"; rating and count). The ✦ sheet shows each signal's normalised score and weight.

## Evaluation (know these numbers)

Protocol: per-user temporal split (latest 20% of each user's ratings held out), relevant = held-out rating ≥ 4, K = 10, **592 users, 9,509 relevant held-out ratings**, tuned on a validation split (never on test).

| Method | Precision@10 | Recall@10 | NDCG@10 | Hit rate@10 |
|---|---|---|---|---|
| Random | 0.0044 | 0.0021 | 0.0046 | 0.039 |
| Popularity | 0.0615 | 0.0510 | 0.0798 | 0.333 |
| Content-based | 0.0074 | 0.0063 | 0.0086 | 0.068 |
| Collaborative | 0.0860 | 0.0751 | 0.1048 | 0.438 |
| **Hybrid** | 0.0840 | 0.0761 | **0.1080** | 0.443 |

* Collaborative beats popularity (**+0.025 NDCG, significant at 95%**). Hybrid ≈ collaborative (**+0.003, not significant**). Say that plainly: "they're statistically comparable."
* Content-based is weakest alone (genres/tags say what a movie *is*, not whether people like it; TF-IDF favours rare, obscure features). Its value is cold start, new movies and explanations.
* New-user test (only 3 liked movies): popularity (0.080) is as good as anything; the few-likes hybrid (0.078) is indistinguishable from the warm weights (0.079). We keep them as a design choice, not a measured gain.
* **Formulas:** Precision = hits/K; Recall = hits/relevant; NDCG = DCG/IDCG with DCG = Σ rel_r / log2(r+1); Hit rate = share of users with ≥ 1 hit.

## Advantages & limitations

**Advantages:** real algorithms, explainable, works without an API key, honest evaluation, privacy-friendly (no accounts), tested (154 backend tests).
**Limitations:** small old dataset (610 users, up to 2018); offline metric is a proxy; popularity bias of MovieLens; no runtime/cast/plot data; content features are thin; dislikes and cold-start aren't measurable offline; a single-process in-memory demo store; hybrid blend between "few likes" and "many likes" isn't separately validated.

## Future improvements

Matrix factorisation (ALS/SVD) or neural CF; richer content (plot embeddings, cast); diversity re-ranking (MMR); online A/B-style feedback; bigger dataset (ml-25m); real accounts and a database.

## 25 likely viva questions

1. **What is a recommender system?** A system that predicts which items a user will like and ranks them, using data about users, items and interactions.
2. **Content-based vs collaborative?** Content-based uses *item attributes* (genres, tags) to find items similar to what you liked; collaborative uses *behaviour of many users* (who liked what) and needs no attributes.
3. **What is item-item CF?** Compute similarity between movies from who liked them; recommend movies most similar to those you liked.
4. **Why item-item and not user-user?** Fewer, more stable items than users in many systems, similarities can be precomputed, and explanations are natural ("because you liked X").
5. **What is TF-IDF?** A weight that is high for terms frequent in one document but rare overall; here a "document" is a movie's genres/tags/title.
6. **What is cosine similarity?** The cosine of the angle between two vectors; 1 = same direction, 0 = nothing shared. It ignores vector length.
7. **Why normalise each feature block before combining?** So tags (many columns) don't overwhelm genres; weights then say how much each block matters.
8. **What is the Bayesian average and why use it?** It pulls averages toward the global mean in proportion to how few ratings a movie has, so one 5★ rating can't top the chart.
9. **How does your hybrid work?** Normalise each component to 0–1, take a weighted average over the components that exist for that movie, and redistribute missing weights.
10. **What is the cold-start problem and how do you handle it?** No data for a new user/item. Popularity + stated genres + onboarding picks for users; content features for new items.
11. **How does a like change recommendations?** It's added to the taste vector and becomes a collaborative vote; liked movies are never re-recommended.
12. **And a dislike?** The movie never returns and acts as negative evidence (−1 collaborative vote, −0.5 in the content centroid).
13. **What does Claude do?** Parses language into preferences and words the reply. It does not rank or choose movies.
14. **Why not let the LLM recommend directly?** It can hallucinate titles, can't be evaluated against held-out data, and isn't reproducible.
15. **What if the API is down or there's no key?** A rule-based parser handles the request; recommendations are unchanged; the UI shows Offline mode.
16. **How do you stop hallucinated titles?** Every title is resolved against the dataset (exact → fuzzy ≥ 0.86); unknown titles are discarded and reported.
17. **How did you evaluate?** Per-user temporal split, relevant = held-out rating ≥ 4, Precision/Recall/NDCG/HitRate @10, tuned on validation, reported with confidence intervals.
18. **Why a temporal split?** It mimics reality (predict the future from the past) and avoids training on future ratings.
19. **What is NDCG?** A ranking metric that rewards placing relevant items higher: DCG of your list divided by the DCG of the perfect list.
20. **Which method won and is it significant?** Hybrid had the highest NDCG (0.108) but is not significantly better than collaborative (0.105); both significantly beat popularity (0.080).
21. **Why is content-based so weak offline?** It recommends things that *look* similar, often obscure ones with no future ratings, while MovieLens users mostly rate popular movies.
22. **What is data leakage and how did you avoid it?** Using test information in training. Popularity, similarities, tags and profiles are built from training ratings only; tags on test movies are removed.
23. **What are the limitations?** Small dataset, offline proxy metric, popularity bias, no runtime/cast data, dislikes and cold start not measured offline.
24. **How would you scale it?** Precompute neighbours in batch, use ANN search/embeddings, a real database and caching; consider matrix factorisation.
25. **How do you keep it explainable?** Each card lists reasons from real data and the ✦ sheet shows every component's score and weight.

## Demo script (3 minutes)

1. Open the home screen → "A lighthearted comedy for tonight" → point out the *mood note* ("left out Horror, War, Crime, Thriller").
2. Hover a card → ✦ **Why this?** → show the score bars. Then **Compare strategies**: point at how Popular is the same list for everyone, Content finds look-alikes, People like you finds what fans rate, and Hybrid blends them (the ×N badges show agreement).
3. Type "I loved Inception and The Prestige. No horror." → show the profile change chips.
4. 👎 a card, then "more like the second one" → show it's not repeated.
5. **Taste** drawer → switch strategy to *Popular* and back; set discovery to *Hidden gems*.
6. **Evaluation** page → explain NDCG and the "are the gaps real?" table.
7. Click the **RS Mini Project** badge → the About card; point at the live status line (it reads *Reading… / Ranking… / Writing…* while a request runs, reflecting real stages, not a fake animation).
8. Mention the Offline-mode badge: the app works without Claude, and say what changes when a key is set.
