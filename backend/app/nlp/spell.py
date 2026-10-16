"""Spelling correction for movie titles, written from scratch (NLP syllabus: Unit 2 tokenization, Unit 3 edit distance / n-grams /
smoothing / perplexity, Unit 4 Viterbi decoding).

The model is the classic *noisy channel*: the user typed x, the intended word is w, so we pick the sequence of words w_1..w_n that maximises

    sum_i [ log P(x_i | w_i)  +  log P(w_i | w_(i-1)) ]
         channel (typo model)     bigram language model (add-k smoothing)

Channel:   P(x | w) = p_edit ** d(x, w)        d = Damerau-Levenshtein edit distance (insert, delete, substitute, transpose)
Candidates are found with a BK-tree (a metric tree), so only a small part of the vocabulary is ever compared.
Decoding is a Viterbi pass over the lattice of candidates per position: the same dynamic programme an HMM POS tagger uses
(hidden state = intended word, observation = typed word).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from ..catalog import normalize_text

START = "<s>"
MAX_TOKENS = 10


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents and punctuation, split on whitespace (the same normalisation the title index uses)."""
    return normalize_text(text).split()


# ----------------------------------------------------------------------------- edit distance
def edit_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (optimal string alignment) distance: insert, delete, substitute, swap two adjacent letters."""
    la, lb = len(a), len(b)
    if abs(la - lb) > max(la, lb):
        return max(la, lb)
    prev2: list[int] = []
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


class BKTree:
    """Burkhard-Keller tree: finds every word within distance r of a query by pruning with the triangle inequality."""

    def __init__(self, words: Iterable[str]) -> None:
        self.root: tuple[str, dict[int, tuple]] | None = None
        for w in words:
            self.add(w)

    def add(self, word: str) -> None:
        if self.root is None:
            self.root = (word, {})
            return
        node = self.root
        while True:
            d = edit_distance(word, node[0])
            if d == 0:
                return
            if d in node[1]:
                node = node[1][d]
            else:
                node[1][d] = (word, {})
                return

    def search(self, word: str, radius: int) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []
        stack = [self.root] if self.root else []
        while stack:
            w, children = stack.pop()
            d = edit_distance(word, w)
            if d <= radius:
                found.append((w, d))
            for dist, child in children.items():
                if d - radius <= dist <= d + radius:  # triangle inequality: nothing outside this band can be close enough
                    stack.append(child)
        return found


# ----------------------------------------------------------------------------- language model
class BigramLM:
    """Word bigram model with add-k smoothing (k = 1 is Laplace). Sentences are lists of tokens; <s> marks the start."""

    def __init__(self, sentences: Iterable[list[str]], vocab_size: int, k: float = 0.05) -> None:
        self.k, self.V = k, max(1, vocab_size)
        self.unigram: Counter[str] = Counter()
        self.bigram: Counter[tuple[str, str]] = Counter()
        self.context: Counter[str] = Counter()
        for s in sentences:
            prev = START
            for w in s:
                self.unigram[w] += 1
                self.bigram[(prev, w)] += 1
                self.context[prev] += 1
                prev = w
        self.total = sum(self.unigram.values())

    def logprob(self, word: str, prev: str) -> float:
        """log P(word | prev). With k = 0 this is the maximum-likelihood estimate (log 0 = -inf for unseen bigrams)."""
        num = self.bigram[(prev, word)] + self.k
        den = self.context[prev] + self.k * self.V
        return math.log(num / den) if num > 0 and den > 0 else float("-inf")

    def unigram_logprob(self, word: str) -> float:
        return math.log((self.unigram[word] + self.k) / (self.total + self.k * self.V))

    def perplexity(self, sentences: Iterable[list[str]]) -> float:
        """exp( -(1/N) * sum log P(w_i | w_(i-1)) ) over all test tokens. Infinite as soon as one bigram has probability 0."""
        logp, n = 0.0, 0
        for s in sentences:
            prev = START
            for w in s:
                lp = self.logprob(w, prev)
                if lp == float("-inf"):
                    return float("inf")
                logp += lp
                n += 1
                prev = w
        return math.exp(-logp / n) if n else float("inf")


# ----------------------------------------------------------------------------- the corrector
class SpellCorrector:
    def __init__(self, titles: list[list[str]], extra_words: Iterable[str] = (), k: float = 0.05, p_edit: float = 0.02) -> None:
        self.p_edit = p_edit
        words = Counter(w for t in titles for w in t)
        self.extra = {w for w in extra_words if w}
        self.vocab = set(words) | self.extra
        self.lm = BigramLM(titles, len(self.vocab), k)
        self.tree = BKTree(sorted(self.vocab))
        self._cache: dict[str, list[tuple[str, int]]] = {}

    # candidate words for one typed token: itself when it is a known word, otherwise every vocabulary word within a small edit distance
    def candidates(self, token: str) -> list[tuple[str, int]]:
        if token in self.vocab:
            return [(token, 0)]
        if token not in self._cache:
            radius = 1 if len(token) <= 4 else 2  # short words are too ambiguous to trust two edits
            self._cache[token] = sorted(self.tree.search(token, radius), key=lambda c: (c[1], c[0]))[:25]
        return self._cache[token]

    def channel_logp(self, distance: int) -> float:
        return distance * math.log(self.p_edit)

    # ---- three systems of increasing strength (also used in the evaluation)
    def correct_edit_distance_only(self, tokens: list[str]) -> list[str]:
        out = []
        for t in tokens:
            c = self.candidates(t)
            out.append(c[0][0] if c else t)
        return out

    def correct_unigram(self, tokens: list[str]) -> list[str]:
        out = []
        for t in tokens:
            c = self.candidates(t)
            out.append(max(c, key=lambda wd: self.channel_logp(wd[1]) + self.lm.unigram_logprob(wd[0]))[0] if c else t)
        return out

    def correct(self, tokens: list[str]) -> dict:
        """Viterbi decoding of the best word sequence; also returns the per-position lattice so a UI can show the work."""
        tokens = tokens[:MAX_TOKENS]
        lattice = [self.candidates(t) or [(t, 0)] for t in tokens]  # nothing close: keep the typed word
        # delta[i][j] = best log score of any path that ends in candidate j at position i
        delta: list[list[float]] = []
        back: list[list[int]] = []
        for i, cands in enumerate(lattice):
            scores, ptrs = [], []
            for w, d in cands:
                emit = self.channel_logp(d)
                if i == 0:
                    scores.append(emit + self.lm.logprob(w, START))
                    ptrs.append(-1)
                else:
                    best, arg = float("-inf"), 0
                    for pj, (pw, _) in enumerate(lattice[i - 1]):
                        s = delta[i - 1][pj] + self.lm.logprob(w, pw)
                        if s > best:
                            best, arg = s, pj
                    scores.append(emit + best)
                    ptrs.append(arg)
            delta.append(scores)
            back.append(ptrs)
        path: list[int] = []
        if lattice:
            j = max(range(len(lattice[-1])), key=lambda x: delta[-1][x])
            for i in range(len(lattice) - 1, -1, -1):
                path.append(j)
                j = back[i][j]
            path.reverse()
        chosen = [lattice[i][j][0] for i, j in enumerate(path)]
        steps = []
        for i, t in enumerate(tokens):
            steps.append(
                {
                    "input": t,
                    "known": t in self.vocab,
                    "chosen": chosen[i],
                    "candidates": [
                        {"word": w, "distance": d, "channel": round(self.channel_logp(d), 3), "best_path_score": round(delta[i][j], 3), "on_best_path": j == path[i]}
                        for j, (w, d) in enumerate(lattice[i])
                    ][:8],
                }
            )
        return {"tokens": steps, "corrected": " ".join(chosen), "changed": chosen != tokens}
