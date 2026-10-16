# NLP experiment: spelling correction of movie titles

Generated: 2026-10-16T04:15:21+00:00 - MovieLens ml-latest-small titles + tags. Every number comes from `python -m scripts.run_nlp_eval` (fixed random seeds).

## Method

Noisy channel: choose the word sequence w maximising `sum_i log P(x_i|w_i) + log P(w_i|w_(i-1))`.
Channel `P(x|w) = p_edit^d` with p_edit = 0.02 and Damerau-Levenshtein distance d (max 2); candidates come from a BK-tree;
the language model is a word bigram model with add-k smoothing (k = 0.05); decoding is Viterbi over the candidate lattice.
Corpus: 9,742 movie titles (29,019 tokens) plus 1,757 extra known words from genres and user tags.

## Metric definitions

- **Perplexity**: `exp(-average log P(word | previous word))` on unseen titles; lower is better. One unseen word pair with probability 0 makes it infinite.
- **Word (token) accuracy**: share of test typos where the mistyped word was restored to the right word.
- **Title accuracy**: share where the whole title came out exactly right (never above word accuracy).
- **Wrongly changed (false-correction rate)**: share of already-correct titles that a system altered; lower is better.

## Language model: perplexity (lower is better)

Titles split 80/10/10 into train (7,793), validation (974) and test (975); vocabulary 7,527 words. k was chosen on the validation titles only.

| Model | Validation | Test |
|---|---|---|
| unigram, add-1 (Laplace) | 1,761.7 | 1,777.7 |
| bigram, no smoothing (MLE) | infinite | infinite |
| bigram, add-k (k=1) | 2,898.7 | 3,026.0 |
| bigram, add-k (k=0.5) | 2,593.1 | 2,706.0 |
| bigram, add-k (k=0.1) | 2,227.6 | 2,316.0 |
| bigram, add-k (k=0.05) | 2,186.4 | 2,267.9 |
| bigram, add-k (k=0.01) | 2,309.2 | 2,383.5 |
| bigram, add-k (k=0.005) | 2,467.7 | 2,543.5 |

Chosen k = 0.05, test perplexity 2,267.9. The unsmoothed bigram model gives probability 0 to any unseen word pair, so its perplexity is infinite; smoothing fixes that.

## Correction accuracy

A typo of 1 or 2 edits is injected into one word (length >= 5) of a title, always producing a non-word. **Token accuracy** = the corrupted word is restored; **title accuracy** = the whole title is restored.

### Protocol `seen`: the user types a title that exists in the catalogue (the app's real use)

| System | 1 edit: token | 1 edit: title | 2 edits: token | 2 edits: title |
|---|---|---|---|---|
| No correction | 0.000 | 0.000 | 0.000 | 0.000 |
| difflib closest match (library baseline) | 0.883 | 0.883 | 0.567 | 0.567 |
| Edit distance only (BK-tree, from scratch) | 0.893 | 0.893 | 0.577 | 0.577 |
| Noisy channel + unigram prior | 0.927 | 0.927 | 0.663 | 0.663 |
| Noisy channel + bigram LM + Viterbi | 1.000 | 1.000 | 0.837 | 0.837 |

300 test items per column.

### Protocol `held-out`: titles held out from training (word pairs never seen)

| System | 1 edit: token | 1 edit: title | 2 edits: token | 2 edits: title |
|---|---|---|---|---|
| No correction | 0.000 | 0.000 | 0.000 | 0.000 |
| difflib closest match (library baseline) | 0.873 | 0.633 | 0.537 | 0.393 |
| Edit distance only (BK-tree, from scratch) | 0.853 | 0.640 | 0.567 | 0.467 |
| Noisy channel + unigram prior | 0.917 | 0.680 | 0.640 | 0.513 |
| Noisy channel + bigram LM + Viterbi | 0.903 | 0.670 | 0.633 | 0.523 |

300 test items per column.

False corrections on 300 clean held-out titles (the share wrongly changed; unseen words look like typos): difflib 0.320, edit distance 0.273, unigram 0.273, bigram 0.277.

## Reading the numbers honestly

- On titles that exist in the catalogue the bigram + Viterbi corrector clearly beats the library baseline.
- On unseen titles the bigram and unigram systems are within noise of each other (with 300 items each percentage is uncertain by roughly 3-6 points; the website shows 95% Wilson intervals).
- The typo probability (0.02 per edit) is a chosen setting, not learned. The only trained part is the bigram model.

## Limitations

- Typos are synthetic (random edits), not typed by real users; real typos cluster on keyboard-neighbour keys.
- Only non-word errors are handled (a typo that spells another real word, such as `form` for `from`, is not detected).
- The language model knows only title word pairs, so it cannot judge ordinary sentence context; the held-out protocol shows the cost.
- Good-Turing smoothing (also in the syllabus) was not implemented; add-k with k chosen on validation data was used.
