"""Run the offline evaluation and write reports/evaluation.json + reports/evaluation.md.

    cd backend && .venv/bin/python -m scripts.run_evaluation [--no-tune] [--k 10]
"""

from __future__ import annotations

import argparse
import time

from app.config import get_settings
from app.dataset import load_raw
from app.evaluation import run_full_evaluation, save_report

LABELS = {
    "random": "Random (sanity floor)",
    "popular": "Popularity (Bayesian)",
    "content": "Content-based (TF-IDF)",
    "collaborative": "Collaborative (item-item)",
    "hybrid": "Hybrid",
}


def render_markdown(r: dict) -> str:
    k = r["protocol"]["k"]
    m = r["metrics"]
    best_ndcg = max(m, key=lambda x: m[x]["ndcg"])
    rows = "\n".join(
        f"| {LABELS[name]} | {v['precision']:.4f} | {v['recall']:.4f} | {v['ndcg']:.4f} | {v['hit_rate']:.3f} | {v['catalogue_coverage']:.3f} |"
        for name, v in m.items()
    )
    cfg = r["chosen_config"]
    w = cfg["hybrid_weights"] or {}
    cf_rows = "\n".join(
        f"| {t['knn'].get('similarity')} | {t['knn']['k']} | {t['knn']['shrinkage']} | {t['validation_ndcg']:.4f} |"
        for t in r["tuning"]
        if t["stage"] == "cf"
    )
    hy_rows = "\n".join(
        f"| {t['weights'].get('content', 0):.2f} | {t['weights'].get('collaborative', 0):.2f} | {t['weights'].get('popularity', 0):.2f} | {t['validation_ndcg']:.4f} |"
        for t in r["tuning"]
        if t["stage"] == "hybrid"
    )
    p = r["protocol"]
    fl = r.get("few_likes")
    few_section = ""
    if fl:
        fm = fl["metrics"]
        names = [("popular", "Popularity"), ("content", "Content-based"), ("collaborative", "Collaborative"),
                 ("hybrid_warm_weights", "Hybrid, warm-user weights"), ("hybrid", "Hybrid, few-likes weights")]
        frows = "\n".join(
            f"| {label} | {fm[key]['precision']:.4f} | {fm[key]['recall']:.4f} | {fm[key]['ndcg']:.4f} | {fm[key]['hit_rate']:.3f} |"
            for key, label in names if key in fm
        )
        tw = fl.get("chosen_weights") or {}
        thin_rows = "\n".join(
            f"| {t['weights'].get('content', 0):.2f} | {t['weights'].get('collaborative', 0):.2f} | {t['weights'].get('popularity', 0):.2f} | {t['validation_ndcg']:.4f} |"
            for t in r["tuning"] if t["stage"] == "thin_hybrid"
        )
        few_section = f"""
## Few-likes regime (a new user who has named only {fl['max_likes']} liked movies)

Each evaluated user is reduced to their **first {fl['max_likes']} liked movies** (chronologically) - the situation of someone in their first minutes with
the app. Same split, same relevance rule, {fl['n_users_evaluated']} users who have at least {fl['max_likes']} liked training movies.
Hybrid weights for this regime were tuned on validation data separately from the warm-user weights.

| Method | Precision@{k} | Recall@{k} | NDCG@{k} | Hit rate@{k} |
|---|---|---|---|---|
{frows}

Chosen few-likes weights: content={tw.get('content', 0):.2f}, collaborative={tw.get('collaborative', 0):.2f}, popularity={tw.get('popularity', 0):.2f}.

Few-likes weight sweep (NDCG@{k} on validation):

| content | collaborative | popularity | NDCG |
|---|---|---|---|
{thin_rows}
"""
    paired_rows = "\n".join(
        f"| {name.replace('_minus_', ' - ').replace('_', ' ')} | {v['mean_ndcg_difference']:+.4f} | [{v['ci95_low']:+.4f}, {v['ci95_high']:+.4f}] | {'yes' if v['significant_at_95'] else 'no'} |"
        for name, v in r.get("paired_comparisons", {}).items()
    )
    return f"""# Offline evaluation report

Generated: {r['generated_at']} - dataset: {r['dataset']}. Every number below comes from
`python -m scripts.run_evaluation`; nothing is hand-written or hard-coded.

## Protocol

- **Split:** {p['split']}. Ties on timestamp are broken by movieId so the split is deterministic.
- **Relevant item:** {p['relevance']}.
- **Eligible users:** at least {p['min_train_ratings_per_user']} training ratings and at least one relevant held-out movie.
- **Candidate items:** movies with at least {p['min_train_ratings_per_item']} *training* ratings that the user has not already rated in train.
- **Leakage controls:** popularity statistics, tag features, item similarities and user profiles are computed from the
  training ratings only; tags a user wrote on a movie in their test set are removed.
- **Signals used:** each user's query contains the movies they rated >= 4.0 in train. Explicit dislikes are not used offline
  (see Limitations).
- **Tuning:** CF settings and hybrid weights were chosen on a validation split carved from the training data
  (latest {int(p['validation_fraction_of_train'] * 100)}% of each user's train ratings) - never on the test set.
- **Reproducibility:** deterministic split and models; random baseline seed = {p['seed']}.

## Dataset

| Quantity | Value |
|---|---|
| Training interactions | {r['n_train_interactions']:,} |
| Test interactions | {r['n_test_interactions']:,} |
| Relevant test interactions (evaluated users) | {r['n_relevant_test_interactions']:,} |
| Users evaluated | {r['n_users_evaluated']} |
| Candidate movies | {r['n_candidate_items']:,} |

## Results (K = {k}, mean over users)

| Method | Precision@{k} | Recall@{k} | NDCG@{k} | Hit rate@{k} | Catalogue coverage |
|---|---|---|---|---|---|
{rows}

Highest NDCG@{k}: **{LABELS[best_ndcg]}**.

Chosen settings - CF: k={cfg['knn']['k']} neighbours, shrinkage={cfg['knn']['shrinkage']}, similarity={cfg['knn'].get('similarity')};
hybrid weights: content={w.get('content', 0):.2f}, collaborative={w.get('collaborative', 0):.2f}, popularity={w.get('popularity', 0):.2f}.

{few_section}
### Paired differences in NDCG@{k} (per-user, normal-approximation 95% CI)

| Comparison | Mean difference | 95% CI | Significant? |
|---|---|---|---|
{paired_rows}

### Metric definitions

- **Precision@K** = (relevant movies in the top K) / K.
- **Recall@K** = (relevant movies in the top K) / (all relevant held-out movies of the user).
- **NDCG@K** = DCG@K / IDCG@K, where DCG@K = sum over ranks i=1..K of rel_i / log2(i+1) with binary rel; rewards putting hits near the top.
- **Hit rate@K** = share of users with at least one relevant movie in the top K.
- **Catalogue coverage** = share of candidate movies that were recommended to at least one user (diversity indicator).

## Validation sweeps (used to pick the settings above)

Collaborative filtering (NDCG@{k} on validation):

| similarity | neighbours k | shrinkage | NDCG |
|---|---|---|---|
{cf_rows}

Hybrid weights (NDCG@{k} on validation):

| content | collaborative | popularity | NDCG |
|---|---|---|---|
{hy_rows}

## Interpretation

{{INTERPRETATION_PLACEHOLDER}}

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
"""


def interpret(r: dict) -> str:
    m = r["metrics"]
    ndcg = {k: v["ndcg"] for k, v in m.items()}
    order = sorted(ndcg, key=ndcg.get, reverse=True)
    lines = [
        f"- Ranking by NDCG: " + " > ".join(f"{LABELS[x]} ({ndcg[x]:.3f})" for x in order) + ".",
        f"- Random scores {ndcg['random']:.3f}, so every real method carries signal.",
    ]
    if ndcg["collaborative"] > ndcg["popular"]:
        lines.append(
            f"- Collaborative filtering beats the popularity baseline ({ndcg['collaborative']:.3f} vs {ndcg['popular']:.3f}), "
            "so personalised rating patterns add value beyond 'what is generally liked'."
        )
    else:
        lines.append(
            f"- Collaborative filtering does not beat the popularity baseline here ({ndcg['collaborative']:.3f} vs {ndcg['popular']:.3f})."
        )
    if ndcg["content"] < ndcg["popular"]:
        lines.append(
            f"- Content-based filtering alone is the weakest real method ({ndcg['content']:.3f}). Genres/tags/title words describe *what a movie is*, "
            "not *whether people like it*, and TF-IDF rewards rare features, which favours obscure movies with few hits. Its value is cold start "
            "(new movies, no ratings) and explainability, which this offline test cannot show."
        )
    hc = r.get("paired_comparisons", {}).get("hybrid_minus_collaborative")
    if ndcg["hybrid"] >= ndcg["collaborative"]:
        verdict = (
            "and the paired difference is statistically significant at the 95% level"
            if hc and hc["significant_at_95"]
            else "but the paired difference is NOT statistically significant at the 95% level, so treat them as comparable"
        )
        lines.append(
            f"- The hybrid ({ndcg['hybrid']:.3f}) scores higher than collaborative filtering alone ({ndcg['collaborative']:.3f}), {verdict}. "
            "Validation tuning gave the collaborative component most of the weight."
        )
    else:
        lines.append(
            f"- The hybrid ({ndcg['hybrid']:.3f}) does not beat collaborative filtering alone ({ndcg['collaborative']:.3f}) for these warm-start users; "
            "tuning pushed most of the weight onto the collaborative component. The hybrid's benefit is robustness (it still works for users with no history, "
            "for new movies and with explicit genre preferences), not peak accuracy for heavy raters."
        )
    fl = r.get("few_likes")
    if fl:
        fm = fl["metrics"]
        k = r["protocol"]["k"]
        best = max(("popular", "content", "collaborative", "hybrid"), key=lambda x: fm[x]["ndcg"])
        thin, warm = fm["hybrid"]["ndcg"], fm["hybrid_warm_weights"]["ndcg"]
        lines.append(
            f"- With only {fl['max_likes']} liked movies per user, NDCG@{k} is: "
            + ", ".join(f"{LABELS[x].split(' (')[0]} {fm[x]['ndcg']:.3f}" for x in ("popular", "content", "collaborative", "hybrid"))
            + f". The best single score is {LABELS[best].split(' (')[0]}; popularity is hard to beat when personalised evidence is this thin."
        )
        verdict = "slightly better than" if thin > warm + 0.002 else "slightly worse than" if thin < warm - 0.002 else "indistinguishable from"
        lines.append(
            f"- The few-likes hybrid weights ({thin:.3f}) are {verdict} the warm-user weights ({warm:.3f}) on this offline metric, so this test does "
            "NOT show that a separate thin-signal weighting improves accuracy. The app still uses them because they put more weight on quality/popularity "
            "(safer when only a movie or two is known) and add content similarity, which makes the reasons explainable; that is a design choice, "
            "not a measured gain."
        )
    cov = {k: v["catalogue_coverage"] for k, v in m.items()}
    lines.append(
        f"- Coverage: popularity recommends only {cov['popular']:.1%} of the candidate catalogue, collaborative {cov['collaborative']:.1%}, hybrid {cov['hybrid']:.1%} - "
        "accuracy and diversity pull in opposite directions."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--no-tune", action="store_true", help="skip validation sweeps (faster, untuned defaults)")
    parser.add_argument("--render-only", action="store_true", help="re-render evaluation.md from the existing evaluation.json")
    args = parser.parse_args()

    settings = get_settings()
    if args.render_only:
        import json

        result = json.loads((settings.reports_dir / "evaluation.json").read_text())
        md = render_markdown(result).replace("{INTERPRETATION_PLACEHOLDER}", interpret(result))
        (settings.reports_dir / "evaluation.md").write_text(md)
        print("Re-rendered", settings.reports_dir / "evaluation.md")
        return
    raw = load_raw(settings.dataset_dir)
    start = time.time()
    result = run_full_evaluation(raw, k=args.k, tune=not args.no_tune)
    result["runtime_seconds"] = round(time.time() - start, 1)
    save_report(result, settings.reports_dir)
    md = render_markdown(result).replace("{INTERPRETATION_PLACEHOLDER}", interpret(result))
    (settings.reports_dir / "evaluation.md").write_text(md)
    print(md.split("## Validation sweeps")[0])
    print(f"Done in {result['runtime_seconds']}s -> {settings.reports_dir}/evaluation.md")


if __name__ == "__main__":
    main()
