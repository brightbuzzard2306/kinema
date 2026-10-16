"""Run the spelling-correction evaluation and write reports/nlp_spellcheck.json + .md.

    cd backend && .venv/bin/python -m scripts.run_nlp_eval
"""

from __future__ import annotations

import json
import time

from app.catalog import Catalog
from app.config import get_settings
from app.dataset import load_raw
from app.nlp.spell_eval import SYSTEMS, run_nlp_evaluation

LABEL = dict(SYSTEMS)


def fmt_ppl(v: float | None) -> str:
    return "infinite" if v is None or v == float("inf") else f"{v:,.1f}"


def render(r: dict) -> str:
    p = r["perplexity"]
    lines = [
        "# NLP experiment: spelling correction of movie titles",
        "",
        f"Generated: {r['generated_at']} - {r['dataset']}. Every number comes from `python -m scripts.run_nlp_eval` (fixed random seeds).",
        "",
        "## Method",
        "",
        "Noisy channel: choose the word sequence w maximising `sum_i log P(x_i|w_i) + log P(w_i|w_(i-1))`.",
        f"Channel `P(x|w) = p_edit^d` with p_edit = {r['channel']['p_edit']} and Damerau-Levenshtein distance d (max {r['channel']['max_edit_distance']}); candidates come from a BK-tree;",
        f"the language model is a word bigram model with add-k smoothing (k = {r['channel']['bigram_k']}); decoding is Viterbi over the candidate lattice.",
        f"Corpus: {r['corpus']['titles']:,} movie titles ({r['corpus']['title_tokens']:,} tokens) plus {r['corpus']['extra_known_words']:,} extra known words from genres and user tags.",
        "",
        "## Metric definitions",
        "",
        "- **Perplexity**: `exp(-average log P(word | previous word))` on unseen titles; lower is better. One unseen word pair with probability 0 makes it infinite.",
        "- **Word (token) accuracy**: share of test typos where the mistyped word was restored to the right word.",
        "- **Title accuracy**: share where the whole title came out exactly right (never above word accuracy).",
        "- **Wrongly changed (false-correction rate)**: share of already-correct titles that a system altered; lower is better.",
        "",
        "## Language model: perplexity (lower is better)",
        "",
        f"Titles split 80/10/10 into train ({p['n_train']:,}), validation ({p['n_valid']:,}) and test ({p['n_test']:,}); vocabulary {p['vocab']:,} words. k was chosen on the validation titles only.",
        "",
        "| Model | Validation | Test |",
        "|---|---|---|",
    ] + [f"| {row['model']} | {fmt_ppl(row['valid'])} | {fmt_ppl(row['test'])} |" for row in p["rows"]] + [
        "",
        f"Chosen k = {p['chosen_k']:g}, test perplexity {fmt_ppl(p['test_at_chosen_k'])}. The unsmoothed bigram model gives probability 0 to any unseen word pair, so its perplexity is infinite; smoothing fixes that.",
        "",
        "## Correction accuracy",
        "",
        "A typo of 1 or 2 edits is injected into one word (length >= 5) of a title, always producing a non-word. **Token accuracy** = the corrupted word is restored; **title accuracy** = the whole title is restored.",
    ]
    for c in r["correction"]:
        what = "the user types a title that exists in the catalogue (the app's real use)" if c["protocol"] == "seen" else "titles held out from training (word pairs never seen)"
        lines += ["", f"### Protocol `{c['protocol']}`: {what}", "", "| System | 1 edit: token | 1 edit: title | 2 edits: token | 2 edits: title |", "|---|---|---|---|---|"]
        for key, label in SYSTEMS:
            a, b = c["results"]["1_edit"][key], c["results"]["2_edit"][key]
            lines.append(f"| {label} | {a['token_accuracy']:.3f} | {a['title_accuracy']:.3f} | {b['token_accuracy']:.3f} | {b['title_accuracy']:.3f} |")
        lines.append(f"\n{c['results']['1_edit']['items']} test items per column.")
        if "false_correction_rate" in c:
            f = c["false_correction_rate"]
            lines += [
                "",
                f"False corrections on {f['n_clean_titles']} clean held-out titles (the share wrongly changed; unseen words look like typos): "
                f"difflib {f['difflib']:.3f}, edit distance {f['edit']:.3f}, unigram {f['unigram']:.3f}, bigram {f['bigram']:.3f}.",
            ]
    lines += [
        "",
        "## Reading the numbers honestly",
        "",
        "- On titles that exist in the catalogue the bigram + Viterbi corrector clearly beats the library baseline.",
        "- On unseen titles the bigram and unigram systems are within noise of each other (with 300 items each percentage is uncertain by roughly 3-6 points; the website shows 95% Wilson intervals).",
        "- The typo probability (0.02 per edit) is a chosen setting, not learned. The only trained part is the bigram model.",
        "",
        "## Limitations",
        "",
        "- Typos are synthetic (random edits), not typed by real users; real typos cluster on keyboard-neighbour keys.",
        "- Only non-word errors are handled (a typo that spells another real word, such as `form` for `from`, is not detected).",
        "- The language model knows only title word pairs, so it cannot judge ordinary sentence context; the held-out protocol shows the cost.",
        "- Good-Turing smoothing (also in the syllabus) was not implemented; add-k with k chosen on validation data was used.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    s = get_settings()
    catalog = Catalog.build(load_raw(s.dataset_dir))
    t = time.time()
    report = run_nlp_evaluation(catalog)
    s.reports_dir.mkdir(parents=True, exist_ok=True)
    (s.reports_dir / "nlp_spellcheck.json").write_text(json.dumps(report, indent=2))
    (s.reports_dir / "nlp_spellcheck.md").write_text(render(report))
    print(f"done in {time.time() - t:.0f}s -> {s.reports_dir}/nlp_spellcheck.(json|md)")


if __name__ == "__main__":
    main()
