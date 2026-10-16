"""A message that is only a movie title (typos allowed) is understood, with or without Claude, and the app says what it read."""

import pytest
from fastapi.testclient import TestClient

from app.main import build_state, create_app
from app.nlu import resolve_preferences
from app.schemas import Preferences

from .test_api import PREFS, make_client_with_claude, text


@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings, build_state(settings))) as c:
        yield c


def chat(c, message, sid):
    r = c.post("/chat", json={"session_id": sid, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_bare_title_detection_unit(client):
    svc = client.app.state.rs.service
    alpha = svc.catalog.resolve_title("alpha story").movie_id
    assert svc._bare_title("alpha story") == (alpha, False)  # exact
    assert svc._bare_title("alpa stroy") == (alpha, True)  # repaired
    assert svc._bare_title("movie alpa stroy") == (alpha, True)  # a leading 'movie' is ignored
    for not_a_title in ("hello", "thanks a lot", "qwerty", "something good tonight", ""):
        assert svc._bare_title(not_a_title) is None


def test_a_bare_title_gives_recommendations_offline(client):
    assert chat(client, "alpha story", "bare-title-0001")["recommendations"]


def test_a_bare_title_with_a_typo_is_repaired_and_the_reading_is_disclosed(client):
    r = chat(client, "alpa stroy", "bare-title-0002")
    assert "Added Alpha Story to your liked movies." in r["changes"]
    assert any("I read" in n and "Alpha Story" in n for n in r["notes"])  # never a silent guess


def test_a_leading_movie_word_is_ignored(client):
    assert "Added Alpha Story to your liked movies." in chat(client, "movie alpa stroy", "bare-title-0003")["changes"]


@pytest.mark.parametrize("message", ["hello", "thanks", "help", "ok", "thank you", "hi there"])
def test_greetings_and_small_talk_are_never_turned_into_a_movie(client, message):
    r = chat(client, message, "smalltalk-0001")
    assert not any("liked movies" in c for c in r["changes"]) and not any("I read" in n for n in r["notes"])


@pytest.mark.parametrize("message", ["qwerty", "something good tonight", "a comedy"])
def test_ordinary_requests_and_gibberish_are_not_hijacked(client, message):
    r = chat(client, message, "ordinary-0001")
    assert not any("I read" in n for n in r["notes"]) and not any("liked movies" in c for c in r["changes"])


def test_a_language_model_that_calls_a_bare_title_small_talk_is_overruled(settings):
    """Live finding: Haiku labelled 'inception' as chit-chat. The rescue does not depend on which model is used."""
    chitchat = {**PREFS, "intent": "chitchat", "genres": [], "count": None}
    with make_client_with_claude(settings, lambda **kw: text(chitchat) if "language-understanding" in kw["system"] else text({"reply": "ok", "follow_ups": []})) as c:
        r = c.post("/chat", json={"session_id": "haiku-case-0001", "message": "alpa stroy"}).json()
    assert r["intent"] == "recommend" and "Added Alpha Story to your liked movies." in r["changes"]
    assert any("I read" in n and "Alpha Story" in n for n in r["notes"])


def test_a_title_inside_a_sentence_is_repaired_too(settings):
    prefs = {**PREFS, "intent": "recommend", "genres": [], "liked_titles": ["alpa stroy"], "count": None}
    with make_client_with_claude(settings, lambda **kw: text(prefs) if "language-understanding" in kw["system"] else text({"reply": "ok", "follow_ups": []})) as c:
        r = c.post("/chat", json={"session_id": "sentence-0001", "message": "I loved alpa stroy"}).json()
    assert "Added Alpha Story to your liked movies." in r["changes"]


def test_rescue_hook_in_resolve_preferences(catalog):
    prefs = Preferences(intent="recommend", liked_titles=["totally unknown thing"])
    plain = resolve_preferences(prefs, catalog)
    assert plain.unresolved_titles == ["totally unknown thing"] and not plain.corrections
    movie = catalog.movies[0]
    rescued = resolve_preferences(Preferences(intent="recommend", liked_titles=["totally unknown thing"]), catalog, rescue=lambda t: movie.movie_id)
    assert rescued.liked_ids == [movie.movie_id] and rescued.corrections == [("totally unknown thing", movie.movie_id)] and not rescued.unresolved_titles
