"""Offline evaluation of the spelling corrector (perplexity of the language models, correction accuracy against a library baseline)."""

from __future__ import annotations

import difflib
import math
import random
import string
from datetime import datetime, timezone

from ..catalog import Catalog
from .spell import START, BigramLM, SpellCorrector, tokenize

LETTERS = string.ascii_lowercase
K_GRID = (1.0, 0.5, 0.1, 0.05, 0.01, 0.005)


def build_corpus(catalog: Catalog) -> tuple[list[list[str]], set[str]]:
    """Titles as token lists, plus extra known words (genres and every word users wrote in tags) so normal English words are not 'corrected'."""
    titles = [t for t in (tokenize(m.title) for m in catalog.movies) if t]
    extra = {w for g in catalog.all_genres for w in tokenize(g)}
    for tags in catalog.tags_text:
        for tag in tags.split(" | "):
            extra.update(tokenize(tag))
    return titles, extra


def _unigram_perplexity(lm: BigramLM, sentences: list[list[str]]) -> float:
    logp, n = 0.0, 0
    for s in sentences:
        for w in s:
            logp += lm.unigram_logprob(w)
            n += 1
    return math.exp(-logp / n)


def perplexity_experiment(titles: list[list[str]], extra: set[str], seed: int = 7) -> dict:
    rng = random.Random(seed)
    shuffled = titles[:]
    rng.shuffle(shuffled)
    n = len(shuffled)
    train, valid, test = shuffled[: int(0.8 * n)], shuffled[int(0.8 * n): int(0.9 * n)], shuffled[int(0.9 * n):]
    vocab = {w for t in train for w in t} | extra
    rows = [{"model": "unigram, add-1 (Laplace)", "k": 1.0, "valid": _unigram_perplexity(BigramLM(train, len(vocab), 1.0), valid), "test": _unigram_perplexity(BigramLM(train, len(vocab), 1.0), test)}]
    rows.append({"model": "bigram, no smoothing (MLE)", "k": 0.0, "valid": BigramLM(train, len(vocab), 0.0).perplexity(valid), "test": BigramLM(train, len(vocab), 0.0).perplexity(test)})
    for k in K_GRID:
        lm = BigramLM(train, len(vocab), k)
        rows.append({"model": f"bigram, add-k (k={k:g})", "k": k, "valid": lm.perplexity(valid), "test": lm.perplexity(test)})
    smoothed = [r for r in rows if r["model"].startswith("bigram, add-k")]
    best = min(smoothed, key=lambda r: r["valid"])  # k chosen on the validation titles only, never on the test titles
    for r in rows:  # JSON has no Infinity: store "infinite" as null (the UI and the markdown report show it as infinite)
        for key in ("valid", "test"):
            if r[key] == math.inf:
                r[key] = None
    return {"n_train": len(train), "n_valid": len(valid), "n_test": len(test), "vocab": len(vocab), "rows": rows, "chosen_k": best["k"], "test_at_chosen_k": best["test"]}


# ----------------------------------------------------------------------------- synthetic typos
def make_typo(word: str, rng: random.Random, edits: int = 1) -> str:
    w = word
    for _ in range(edits):
        op = rng.choice(["delete", "insert", "substitute", "transpose"])
        i = rng.randrange(len(w))
        if op == "delete" and len(w) > 3:
            w = w[:i] + w[i + 1:]
        elif op == "insert":
            w = w[:i] + rng.choice(LETTERS) + w[i:]
        elif op == "transpose" and len(w) > 2:
            i = rng.randrange(len(w) - 1)
            w = w[:i] + w[i + 1] + w[i] + w[i + 2:]
        else:
            w = w[:i] + rng.choice([c for c in LETTERS if c != w[i]]) + w[i + 1:]
    return w


def _difflib_baseline(tokens: list[str], vocab: set[str], vocab_list: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if t in vocab:
            out.append(t)
        else:
            m = difflib.get_close_matches(t, vocab_list, n=1, cutoff=0.75)
            out.append(m[0] if m else t)
    return out


SYSTEMS = [
    ("none", "No correction"),
    ("difflib", "difflib closest match (library baseline)"),
    ("edit", "Edit distance only (BK-tree, from scratch)"),
    ("unigram", "Noisy channel + unigram prior"),
    ("bigram", "Noisy channel + bigram LM + Viterbi"),
]


def correction_experiment(titles: list[list[str]], extra: set[str], protocol: str, n_items: int = 300, seed: int = 11, k: float = 0.05) -> dict:
    rng = random.Random(seed)
    if protocol == "held-out":
        shuffled = titles[:]
        random.Random(seed).shuffle(shuffled)
        cut = int(0.8 * len(shuffled))
        train, pool = shuffled[:cut], shuffled[cut:]
    else:  # "seen": the user types a title that exists in the catalogue (the realistic use in the app)
        train, pool = titles, titles
    corrector = SpellCorrector(train, extra, k=k)
    vocab_list = sorted(corrector.vocab)
    results: dict = {}
    for edits in (1, 2):
        hits = {s: {"token": 0, "title": 0} for s, _ in SYSTEMS}
        items, tries = 0, 0
        order = pool[:]
        rng.shuffle(order)
        for title in order:
            if items >= n_items:
                break
            eligible = [i for i, w in enumerate(title) if len(w) >= 5 and w.isalpha() and w in corrector.vocab]
            if len(title) < 2 or not eligible:
                continue
            pos = rng.choice(eligible)
            typo = None
            for _ in range(10):
                cand = make_typo(title[pos], rng, edits)
                if cand != title[pos] and cand not in corrector.vocab:  # a non-word error: the only kind this model targets
                    typo = cand
                    break
            if typo is None:
                continue
            typed = title[:pos] + [typo] + title[pos + 1:]
            outputs = {
                "none": typed,
                "difflib": _difflib_baseline(typed, corrector.vocab, vocab_list),
                "edit": corrector.correct_edit_distance_only(typed),
                "unigram": corrector.correct_unigram(typed),
                "bigram": corrector.correct(typed)["corrected"].split(),
            }
            items += 1
            for s, out in outputs.items():
                hits[s]["token"] += int(len(out) > pos and out[pos] == title[pos])
                hits[s]["title"] += int(out == title)
        results[f"{edits}_edit"] = {"items": items, **{s: {"token_accuracy": hits[s]["token"] / items, "title_accuracy": hits[s]["title"] / items} for s in hits}}
    out = {"protocol": protocol, "n_train_titles": len(train), "results": results}
    if protocol == "held-out":  # how often does each system wrongly change a CLEAN title (unseen words look like typos)
        clean = [t for t in pool if len(t) >= 1][:n_items]
        out["false_correction_rate"] = {
            "difflib": sum(_difflib_baseline(t, corrector.vocab, vocab_list) != t for t in clean) / len(clean),
            "edit": sum(corrector.correct_edit_distance_only(t) != t for t in clean) / len(clean),
            "unigram": sum(corrector.correct_unigram(t) != t for t in clean) / len(clean),
            "bigram": sum(corrector.correct(t)["corrected"].split() != t for t in clean) / len(clean),
            "n_clean_titles": len(clean),
        }
    return out


def run_nlp_evaluation(catalog: Catalog) -> dict:
    titles, extra = build_corpus(catalog)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "MovieLens ml-latest-small titles + tags",
        "corpus": {"titles": len(titles), "title_tokens": sum(len(t) for t in titles), "extra_known_words": len(extra)},
        "channel": {"p_edit": 0.02, "max_edit_distance": 2, "bigram_k": 0.05},
        "perplexity": perplexity_experiment(titles, extra),
        "correction": [correction_experiment(titles, extra, "seen"), correction_experiment(titles, extra, "held-out")],
    }
