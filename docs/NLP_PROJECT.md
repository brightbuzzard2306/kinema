# NLP mini project: spelling correction of movie titles (inside Kinema)

Course: Natural Language Processing (DJS23SPC302 / DJS23SPC302L). The NLP work lives in the **NLP Lab** page (`/nlp`) of the Kinema web app and in `backend/app/nlp/`.
It reuses the recommender's catalogue (9,742 MovieLens titles and the user tags) as its text corpus.

## What it does
You type a movie title with mistakes ("shawshenk redemtion"); the model returns the intended title ("shawshank redemption") and the movies it matches.
The page shows the whole **candidate lattice** (every candidate word, its edit distance and its Viterbi score) so the algorithm can be explained step by step.

## It is also used inside the chat
The same corrector now repairs what you type in the Kinema chat (added after a live test where `jordfather` and `inception` were ignored):
- **A message that is only a movie title** ("jordfather", "inceptoin") is treated as "I liked that movie", whatever the language model labelled it. Claude models are inconsistent on lone words, so the rescue does not depend on which model runs, and it also works with no Claude at all.
- **A mistyped title inside a sentence** ("I loved inceptoin") is repaired when the normal title matching fails.
- The app always says what it did ("I read “jordfather” as The Godfather (1972)"), accepts only a near-exact catalogue title after correction, and never turns greetings ("hello", "thanks", "help") or gibberish into a movie.
Code: `ChatService._bare_title` / `_repair_title` in `backend/app/service.py`, tests in `backend/tests/test_nlp_chat.py`.

## Syllabus coverage
| Syllabus topic | Where it is used | Written from scratch? |
|---|---|---|
| Unit 2: tokenization, normalisation | `tokenize()` (lowercase, strip accents/punctuation) | yes |
| Unit 2: corpus, frequency counts | unigram/bigram counts over 9,742 titles + tag words | yes |
| Unit 3: edit distance, regular text processing | Damerau-Levenshtein distance (insert, delete, substitute, adjacent swap) | yes |
| Unit 3: n-grams, Laplace / add-k smoothing | `BigramLM` with add-k smoothing | yes |
| Unit 3: evaluating n-grams, perplexity | train/validation/test perplexity table; chosen k on validation data | yes |
| Unit 4: Viterbi (as used for HMM POS tagging) | Viterbi decoding over the candidate lattice (hidden state = intended word, observation = typed word) | yes |
| Library baseline | Python `difflib` closest match | library |
| Suggested experiment | "Spell Check, Autocorrect" | covered |

Not covered (could be added next): POS tagging with an HMM, NER, chunking, WordNet/Lesk word sense disambiguation, Good-Turing smoothing, CYK parsing, coreference.

## The algorithm (explain it in this order)
1. **Tokenize** the typed text.
2. **Candidates:** a **BK-tree** (a tree keyed by edit distance) returns every vocabulary word within 2 edits (1 edit for words of 4 letters or fewer). The triangle inequality prunes most of the tree.
   A word that is already in the vocabulary is its own only candidate (non-word error model).
3. **Channel model:** `P(typed | word) = 0.02 ^ distance`. Each edit is a rare event.
4. **Language model:** word **bigram** with add-k smoothing, `P(w | prev) = (count(prev,w) + k) / (count(prev) + k * V)`, k = 0.05 chosen on validation titles.
5. **Viterbi:** choose the sequence maximising `sum_i [ log P(x_i | w_i) + log P(w_i | w_(i-1)) ]`. It is the same dynamic programme as HMM POS tagging.

## Results (from `reports/nlp_spellcheck.md`, regenerate with `cd backend && .venv/bin/python -m scripts.run_nlp_eval`)
- **Perplexity (test titles):** bigram without smoothing is **infinite** (one unseen word pair gives probability 0); add-k smoothing gives 2,268 at k = 0.05; add-1 unigram 1,778.
  The bigram is *not* better than the unigram: title word pairs are sparse, so most probability mass goes to smoothing.
- **Titles that exist in the catalogue (the app's real use), 300 items per cell, 1 edit / 2 edits, token accuracy:**
  difflib 88.3% / 56.7%; edit distance only 89.3% / 57.7%; channel + unigram 92.7% / 66.3%; **channel + bigram + Viterbi 100% / 83.7%**.
- **Held-out titles (word pairs never seen):** the bigram's advantage mostly disappears (90.3% vs unigram 91.7% at 1 edit; 63.3% vs 64.0% at 2 edits). Say this honestly: the context model helps because it has seen the title.
- **Over-correction:** on clean held-out titles, difflib wrongly changes 32.0% and the bigram system 27.7%, because words missing from training look like typos.

## Likely viva questions
- **What is the noisy channel model?** The typed word is the intended word passed through a noisy channel; we choose the word that maximises `P(word) * P(typed | word)` (Bayes' rule).
- **Why Damerau-Levenshtein?** Most human typos are one insertion, deletion, substitution or adjacent swap; counting a swap as one edit models them better than plain Levenshtein.
- **Why a BK-tree?** Comparing a typo with all ~9,000 words per query is slow. The triangle inequality of the edit distance lets the tree skip whole branches.
- **Why smoothing?** An unsmoothed bigram gives probability 0 to unseen pairs, so the perplexity is infinite and a path through that pair can never win. Add-k moves a little probability mass to unseen pairs.
- **How did you choose k?** On a validation split of the titles, never on the test titles (k = 0.05).
- **What is perplexity?** `exp(-1/N * sum log P(w_i | w_(i-1)))`: the average branching factor the model is "confused" by; lower is better.
- **Why is the bigram perplexity higher than the unigram?** Titles are short and varied, so most word pairs occur once or never; the bigram estimates are sparse. Interpolating with the unigram (not implemented) would fix this.
- **Where does Viterbi come in?** Choosing words one at a time is greedy; Viterbi finds the best whole sequence in O(n * c^2) over n positions and c candidates per position.
- **How is this like HMM POS tagging?** Hidden state = intended word (instead of POS tag), observation = typed word, transition = bigram, emission = channel model.
- **Limitations?** Typos are synthetic; only non-word errors are handled (`forest gump` is left alone because *forest* is a real word); no Good-Turing; the language model knows title word pairs only.
- **Which of Good-Turing and Laplace did you use?** Laplace / add-k.

## Where the code is
`backend/app/nlp/spell.py` (algorithms), `backend/app/nlp/spell_eval.py` (evaluation), `backend/scripts/run_nlp_eval.py`, `backend/tests/test_nlp_spell.py` (13 tests),
API `GET /nlp/spell?q=` and `GET /nlp/report`, page `frontend/src/app/nlp/page.tsx`.
