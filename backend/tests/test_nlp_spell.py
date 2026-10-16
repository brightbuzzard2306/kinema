"""NLP Lab: edit distance, BK-tree, bigram LM smoothing, Viterbi correction, and the API."""

import itertools
import math

import pytest
from fastapi.testclient import TestClient

from app.main import build_state, create_app
from app.nlp.spell import START, BigramLM, BKTree, SpellCorrector, edit_distance, tokenize

TITLES = [tokenize(t) for t in [
    "the godfather", "the godfather part two", "gladiator", "inception", "interstellar", "the prestige", "the dark knight",
    "pulp fiction", "forrest gump", "the matrix", "fight club", "good will hunting", "shawshank redemption the",
]]


def test_edit_distance_known_values():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3 and edit_distance("abc", "abc") == 0
    assert edit_distance("teh", "the") == 1  # an adjacent swap is ONE edit (Damerau)
    assert edit_distance("inceptoin", "inception") == 1


def test_edit_distance_is_symmetric():
    for a, b in itertools.product(["flaw", "lawn", "godfather", "godfahter", ""], repeat=2):
        assert edit_distance(a, b) == edit_distance(b, a)


def test_bk_tree_matches_brute_force():
    words = sorted({w for t in TITLES for w in t} | {"incepting", "gladiators", "matrices", "hunting", "hunter"})
    tree = BKTree(words)
    for q in ["inceptoin", "gladiatr", "matirx", "hunt", "zzzz", "godfather"]:
        brute = sorted((w, edit_distance(q, w)) for w in words if edit_distance(q, w) <= 2)
        assert sorted(tree.search(q, 2)) == brute


def test_unsmoothed_bigram_has_infinite_perplexity_on_unseen_pairs_but_smoothing_fixes_it():
    train = [["the", "dark", "knight"], ["the", "godfather"]]
    test = [["the", "godfather", "knight"]]  # ('godfather','knight') was never seen
    assert BigramLM(train, 10, k=0.0).perplexity(test) == math.inf
    assert 1 < BigramLM(train, 10, k=1.0).perplexity(test) < math.inf


def test_smoothed_probabilities_form_a_distribution():
    lm = BigramLM([["a", "b"], ["a", "c"], ["b", "c"]], 3, k=0.5)
    for prev in (START, "a", "b", "c"):
        assert sum(math.exp(lm.logprob(w, prev)) for w in ("a", "b", "c")) == pytest.approx(1.0)


def test_known_words_are_never_changed_and_typos_are_fixed():
    sc = SpellCorrector(TITLES)
    ok = sc.correct(tokenize("the godfather"))
    assert ok["corrected"] == "the godfather" and not ok["changed"]
    fixed = sc.correct(tokenize("the godfahter"))
    assert fixed["corrected"] == "the godfather" and fixed["changed"]
    assert sc.correct(tokenize("inceptoin"))["corrected"] == "inception"


def test_context_decides_between_equally_close_words():
    """'hunter' and 'hunted' are both ONE edit from 'hunteg'. Alone, the more frequent word wins; after 'will' the seen pair 'will hunted' wins."""
    sc = SpellCorrector([["good", "will", "hunted"], ["the", "hunter"], ["hunter"], ["hunter"]], k=0.05)
    assert sc.correct_unigram(["hunteg"]) == ["hunter"]  # no context: the more frequent word
    assert sc.correct(["hunteg"])["corrected"] == "hunter"
    assert sc.correct(["will", "hunteg"])["corrected"] == "will hunted"  # context overrules frequency


def test_word_with_nothing_close_is_left_alone():
    assert SpellCorrector(TITLES).correct(["qqqqqqqq"])["corrected"] == "qqqqqqqq"


def test_lattice_is_reported_for_the_ui():
    step = SpellCorrector(TITLES).correct(["godfahter"])["tokens"][0]
    assert step["known"] is False and step["chosen"] == "godfather"
    assert any(c["word"] == "godfather" and c["distance"] == 1 and c["on_best_path"] for c in step["candidates"])


# ---------------------------------------------------------------- API
@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings, build_state(settings))) as c:
        yield c


def test_nlp_spell_endpoint_corrects_and_finds_the_movie(client):
    r = client.get("/nlp/spell", params={"q": "alpha stroy"})  # the test catalogue has "Alpha Story"
    body = r.json()
    assert r.status_code == 200 and body["corrected"] == "alpha story" and body["changed"]
    assert body["matches"] and body["matches"][0]["title"] == "Alpha Story"
    assert body["tokens"][1]["input"] == "stroy" and body["tokens"][1]["chosen"] == "story"


def test_nlp_spell_endpoint_limits_input(client):
    assert client.get("/nlp/spell", params={"q": "x" * 500}).status_code == 422
    many = " ".join(["alpha"] * 20)  # 119 characters: allowed, but only the first 10 words are processed
    assert len(client.get("/nlp/spell", params={"q": many}).json()["tokens"]) == 10


def test_nlp_report_is_a_clear_404_without_a_run(client):
    assert client.get("/nlp/report").status_code == 404


def test_nlp_routes_are_locked_when_the_site_is_private(settings):
    from pydantic import SecretStr
    s = settings.model_copy(update={"access_code": SecretStr("a-long-test-code")})
    with TestClient(create_app(s, build_state(s))) as c:
        assert c.get("/nlp/spell", params={"q": "alpha"}).status_code == 401
        assert c.get("/nlp/report").status_code == 401
