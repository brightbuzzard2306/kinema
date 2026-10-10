import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.llm import ClaudeService
from app.main import AppState, build_state, create_app

SID = "test-session-0001"


@pytest.fixture()
def client(settings):
    app = create_app(settings, build_state(settings))
    with TestClient(app) as c:
        yield c


def chat(client, message, sid=SID):
    r = client.post("/chat", json={"session_id": sid, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def titles(data):
    return [c["title"] for c in data["recommendations"]]


# ------------------------------------------------------------------ health & basics
def test_health_reports_fallback_without_keys(client):
    h = client.get("/health").json()
    assert h["dataset"]["users"] == 60
    assert h["status"] == "ok" and h["llm"]["enabled"] is False and h["posters"]["enabled"] is False
    assert "key" not in json.dumps(h).lower().replace("keys", "")


def test_meta_and_movie_search(client):
    assert "Sci-Fi" in client.get("/meta").json()["genres"]
    assert client.get("/movies?q=alpha").json()["results"][0]["title"] == "Alpha Story"
    assert client.get("/movies/1").json()["movie_id"] == 1
    assert client.get("/movies/424242").status_code == 404


def test_evaluation_endpoint_without_report_is_a_clear_404(client):
    r = client.get("/evaluation")
    assert r.status_code == 404 and "run_evaluation" in r.json()["error"]["message"]


def test_posters_endpoint_without_tmdb_returns_nulls(client):
    r = client.get("/posters?ids=1,2").json()
    assert r["enabled"] is False and r["posters"] == {"1": None, "2": None}
    assert client.get("/posters?ids=abc").status_code == 422


# ------------------------------------------------------------------ validation & errors
def test_request_validation_is_consistent(client):
    bad = [
        ({"session_id": SID, "message": ""}, 422),
        ({"session_id": "x", "message": "hi"}, 422),
        ({"session_id": "bad id with spaces!", "message": "hi"}, 422),
        ({"session_id": SID, "message": "a" * 2001}, 422),
        ({"session_id": SID}, 422),
    ]
    for body, status in bad:
        r = client.post("/chat", json=body)
        assert r.status_code == status and r.json()["error"]["code"] == "validation_error"


def test_message_longer_than_configured_limit_rejected(client):
    r = client.post("/chat", json={"session_id": SID, "message": "a" * 900})
    assert r.status_code == 422 and "too long" in r.json()["error"]["message"]


def test_feedback_for_unknown_movie_is_404(client):
    r = client.post("/feedback", json={"session_id": SID, "movie_id": 999999, "action": "like"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.post("/feedback", json={"session_id": SID, "movie_id": 1, "action": "love"}).status_code == 422


def test_internal_errors_do_not_leak_details(settings, monkeypatch):
    state = build_state(settings)
    monkeypatch.setattr(state.service, "chat", lambda *a: (_ for _ in ()).throw(RuntimeError("secret internal path /etc/x")))
    with TestClient(create_app(settings, state), raise_server_exceptions=False) as c:
        r = c.post("/chat", json={"session_id": SID, "message": "hi"})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"]["code"] == "internal_error"


def test_cors_allows_only_configured_origin(client):
    ok = client.options("/chat", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    bad = client.options("/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_service_unavailable_when_dataset_missing(settings, tmp_path):
    broken = settings.model_copy(update={"data_dir": tmp_path / "empty"})
    with TestClient(create_app(broken, build_state(broken))) as c:
        assert c.get("/health").json()["status"] == "unavailable"
        r = c.post("/chat", json={"session_id": SID, "message": "hi"})
        assert r.status_code == 503 and "setup_data" in r.json()["error"]["message"]


# ------------------------------------------------------------------ the conversation journey (no API key)
def test_genre_request_returns_real_movies_in_fallback_mode(client):
    d = chat(client, "recommend a sci-fi movie")
    assert d["llm"]["mode"] == "fallback" and "key" in d["llm"]["reason"].lower()
    assert d["recommendations"] and all("Sci-Fi" in c["genres"] for c in d["recommendations"])
    assert len({c["movie_id"] for c in d["recommendations"]}) == len(d["recommendations"])
    assert all(c["reasons"] and c["confidence"] in {"high", "medium", "low"} for c in d["recommendations"])


def test_exclusions_from_chat_are_respected_and_persist(client):
    chat(client, "I like romance but no comedy")
    d = chat(client, "give me something else")
    assert all("Comedy" not in c["genres"] for c in d["recommendations"])
    assert "Comedy" in client.get(f"/sessions/{SID}/profile").json()["excluded_genres"]


def test_no_repeats_across_turns(client):
    a = chat(client, "recommend a sci-fi movie")
    b = chat(client, "more sci-fi")
    assert not {c["movie_id"] for c in a["recommendations"]} & {c["movie_id"] for c in b["recommendations"]}


def test_like_changes_profile_and_following_results(client):
    first = chat(client, "recommend a sci-fi movie")
    liked = first["recommendations"][0]["movie_id"]
    profile = client.post("/feedback", json={"session_id": SID, "movie_id": liked, "action": "like"}).json()
    assert profile["liked_ids"] == [liked]
    client.post("/feedback", json={"session_id": SID, "movie_id": liked, "action": "like"})  # repeat: no double count
    assert client.get(f"/sessions/{SID}/profile").json()["liked_ids"] == [liked]
    d = client.post("/recommend", json={"session_id": SID, "anchor_movie_id": liked}).json()
    assert liked not in [c["movie_id"] for c in d["recommendations"]] and d["recommendations"]
    assert d["intent"] == "similar"


def test_dislike_removes_movie_from_future_results(client):
    first = chat(client, "recommend a romance movie")
    bad = first["recommendations"][0]["movie_id"]
    client.post("/feedback", json={"session_id": SID, "movie_id": bad, "action": "dislike"})
    for _ in range(3):
        d = chat(client, "more romance")
        assert bad not in [c["movie_id"] for c in d["recommendations"]]


def test_explain_uses_the_cards_that_were_shown(client):
    shown = chat(client, "recommend a horror movie")
    d = chat(client, "why did you recommend the second one?")
    assert d["intent"] == "explain" and shown["recommendations"][1]["title"] in d["reply"]
    for reason in shown["recommendations"][1]["reasons"][:1]:
        assert reason["text"].split(".")[0] in d["reply"]


def test_explain_with_nothing_shown_is_graceful(client):
    d = chat(client, "why did you recommend this?")
    assert d["intent"] == "explain" and not d["recommendations"] and "haven't recommended" in d["reply"]


def test_reject_last_marks_dislikes_and_shifts(client):
    first = chat(client, "recommend a sci-fi movie")
    d = chat(client, "I didn't like those. Try something different.")
    ids = {c["movie_id"] for c in first["recommendations"]}
    assert ids <= set(d["profile"]["disliked_ids"]) and not ids & {c["movie_id"] for c in d["recommendations"]}


def test_unknown_title_is_reported_not_invented(client):
    d = chat(client, 'something like "Zzyzx Quantum Banana"')
    assert d["intent"] in {"recommend", "similar"} and all(c["title"] for c in d["recommendations"])


def test_runtime_request_is_honest(client):
    d = chat(client, "a sci-fi movie under two hours")
    assert any("runtime" in n for n in d["notes"])


def test_new_topic_clears_stale_year_and_rating_constraints(client):
    chat(client, "highly rated romance movies from the 90s")
    d = chat(client, "now sci-fi")
    assert d["profile"]["year_min"] is None and d["profile"]["min_rating"] is None


def test_naming_movies_without_genre_clears_genre_focus(client):
    chat(client, "recommend a horror movie")
    d = chat(client, "I loved Alpha Story")
    assert d["profile"]["genres"] == [] and d["profile"]["liked_ids"] == [1]


def test_reset_intent_clears_everything(client):
    chat(client, "I loved Alpha Story")
    d = chat(client, "start over")
    assert d["profile"]["liked_ids"] == [] and d["recommendations"] == []


def test_sessions_do_not_leak_between_users(client):
    chat(client, "I loved Alpha Story", sid="user-aaaaaaaa")
    other = client.get("/sessions/user-bbbbbbbb/profile").json()
    assert other["liked_ids"] == []


def test_profile_put_affects_next_recommendations(client):
    r = client.put(f"/sessions/{SID}/profile", json={"genres": ["Horror"], "strategy": "popular", "novelty": 0.9})
    assert r.status_code == 200 and r.json()["genres"] == ["Horror"]
    d = client.post("/recommend", json={"session_id": SID}).json()
    assert d["recommendations"] and all("Horror" in c["genres"] for c in d["recommendations"])
    assert d["strategy_used"] == "popular"
    assert client.put(f"/sessions/{SID}/profile", json={"novelty": 5}).status_code == 422


def test_session_state_rehydrates_ui(client):
    chat(client, "recommend a sci-fi movie")
    state = client.get(f"/sessions/{SID}").json()
    assert state["last_cards"] and state["history"][0]["role"] == "user"


# ------------------------------------------------------------------ Claude failure -> graceful fallback
def make_client_with_claude(settings, create):
    state = build_state(settings)
    state.service.claude = ClaudeService(settings.model_copy(update={"anthropic_api_key": SecretStr("sk-x")}), SimpleNamespace(messages=SimpleNamespace(create=create)))
    return TestClient(create_app(settings, state))


def text(payload):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(payload))])


PREFS = {"intent": "recommend", "genres": ["Sci-Fi"], "excluded_genres": [], "liked_titles": [], "disliked_titles": [], "anchor_titles": [],
         "ordinal_reference": None, "mood": None, "min_rating": None, "max_runtime_minutes": None, "count": 3, "year_min": None,
         "year_max": None, "novelty": None}


def test_claude_success_path_uses_claude_for_parse_and_reply(settings):
    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        return text({"reply": "Here are some great sci-fi picks.", "follow_ups": ["More like the first", "Hidden gems", "Highly rated"]})

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "something sci-fi please")
    assert d["llm"] == {"mode": "claude", "reason": None} and d["reply"].startswith("Here are some great")
    assert len(d["recommendations"]) == 3 and d["suggestions"] == ["More like the first", "Hidden gems", "Highly rated"]


def test_claude_hallucinated_titles_never_reach_results(settings):
    prefs = {**PREFS, "anchor_titles": ["The Invented Film"], "liked_titles": ["Alpha Story"], "genres": ["Sci-Fi", "Made-Up Genre"]}
    with make_client_with_claude(settings, lambda **kw: text(prefs) if "language-understanding" in kw["system"] else text({"reply": "ok", "follow_ups": []})) as c:
        d = chat(c, "like The Invented Film")
    assert d["unresolved_titles"] == ["The Invented Film"] and d["profile"]["genres"] == ["Sci-Fi"]
    assert d["recommendations"] and all(c["movie_id"] in set(range(1, 41)) for c in d["recommendations"])  # only real catalogue movies


@pytest.mark.parametrize("failure", ["timeout", "malformed", "ratelimit"])
def test_claude_failures_fall_back_and_still_recommend(settings, failure):
    import anthropic
    import httpx

    req = httpx.Request("POST", "https://x")

    def create(**kw):
        if failure == "timeout":
            raise anthropic.APITimeoutError(request=req)
        if failure == "ratelimit":
            raise anthropic.RateLimitError("slow", response=httpx.Response(429, request=req), body=None)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="garbage{")])

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "recommend a romance movie")
    assert d["llm"]["mode"] == "fallback" and d["llm"]["reason"]
    assert d["recommendations"] and all("Romance" in x["genres"] for x in d["recommendations"])
    assert "sk-x" not in json.dumps(d)


def test_claude_parse_ok_but_reply_fails_keeps_cards_and_discloses(settings):
    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        return text({"reply": "It is rated 9.9 stars!", "follow_ups": []})  # ungrounded number -> rejected

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "sci-fi")
    assert d["recommendations"] and "Reply written locally" in d["llm"]["reason"] and "9.9" not in d["reply"]


def test_llm_status_endpoint(settings):
    with TestClient(create_app(settings, build_state(settings))) as c:
        r = c.get("/llm/status").json()
        assert r == {"enabled": False, "ok": False, "reason": "No Anthropic API key configured.", "model": None}

    def create(**kw):
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"ok": True}))])

    with make_client_with_claude(settings, create) as c:
        r = c.get("/llm/status").json()
    assert r["enabled"] and r["ok"] and r["reason"] is None and "sk-x" not in json.dumps(r)


def test_requested_count_applies_to_that_request_only(client):
    assert len(chat(client, "give me 3 sci-fi movies")["recommendations"]) == 3
    assert len(chat(client, "more sci-fi")["recommendations"]) == 6  # back to the default, not stuck at 3


def test_reply_naming_a_movie_outside_the_results_is_replaced(settings):
    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        return text({"reply": "You will love Genreless Oddity, a great pick.", "follow_ups": ["More like Genreless Oddity"]})

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "sci-fi")
    assert d["recommendations"] and "Genreless Oddity" not in d["reply"]  # catalogue movie that was NOT recommended
    assert "wasn't asked to discuss" in d["llm"]["reason"] and d["reply"].startswith("Here are")


def test_unsupported_requests_are_reported_not_ignored(settings):
    prefs = {**PREFS, "unsupported": ["less complicated", "under two hours"]}

    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(prefs)
        return text({"reply": "Here are some picks.", "follow_ups": []})

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "sci-fi but less complicated")
    assert any("less complicated" in n for n in d["notes"])
    assert not any("under two hours" in n for n in d["notes"])  # runtime-like phrases use the dedicated runtime note


def test_unverifiable_claims_about_movies_are_rejected(settings):
    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        return text({"reply": "These are clever, gripping films with no violence.", "follow_ups": []})

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "sci-fi")
    assert d["recommendations"] and "clever" not in d["reply"]
    assert "unverifiable claim" in d["llm"]["reason"] and d["reply"].startswith("Here are")


def test_claude_framing_gets_an_engine_written_top_pick_line(settings):
    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        return text({"reply": "Here is a short sci-fi selection.", "follow_ups": ["More sci-fi", "Hidden gems", "Highly rated"]})

    with make_client_with_claude(settings, create) as c:
        d = chat(c, "sci-fi")
    top = d["recommendations"][0]
    assert d["reply"].startswith("Here is a short sci-fi selection.") and f"Top pick: {top['title']} ({top['year']})." in d["reply"]
    assert d["llm"]["mode"] == "claude"


def test_common_words_that_are_titles_do_not_cause_false_alarms(raw):
    import pandas as pd

    from app.catalog import Catalog
    from app.dataset import RawData
    from app.service import ChatService

    movies = pd.concat([raw.movies, pd.DataFrame([{"movieId": 500, "title": "Storytelling (2001)", "genres": "Drama"}])])
    svc = ChatService.__new__(ChatService)
    svc.catalog = Catalog.build(RawData(movies, raw.ratings, raw.tags, raw.links))
    allowed: set[str] = set()
    svc._reject_strays("These share intricate storytelling and a solid Sci-Fi core.", allowed)  # lowercase ordinary word: fine
    svc._reject_strays("Storytelling like this is rare.", allowed)  # sentence-initial common word: fine
    with pytest.raises(Exception, match="Storytelling"):
        svc._reject_strays("Try Storytelling tonight.", allowed)  # capitalised mid-sentence = a title reference
    svc._reject_strays("Try Storytelling tonight.", {"storytelling"})  # allowed when the user mentioned it


# ------------------------------------------------------------------ strategy comparison
def test_compare_returns_all_four_strategies_without_touching_the_session(client):
    first = chat(client, "recommend a sci-fi movie")
    before = client.get(f"/sessions/{SID}").json()
    r = client.post("/compare", json={"session_id": SID, "count": 4})
    assert r.status_code == 200
    d = r.json()
    assert list(d["columns"]) == ["popular", "content", "collaborative", "hybrid"]
    assert all(1 <= len(c["movies"]) <= 4 for c in d["columns"].values())
    assert d["columns"]["hybrid"]["regime"] in {"cold", "thin", "blend", "warm"}
    assert d["offline_ndcg"] is None  # no evaluation report in the test data dir
    after = client.get(f"/sessions/{SID}").json()
    assert after["profile"] == before["profile"] and after["history"] == before["history"] and after["last_cards"] == before["last_cards"]
    # comparing does not "use up" movies: the same picks can be compared again
    assert client.post("/compare", json={"session_id": SID, "count": 4}).json()["columns"]["popular"]["movies"] == d["columns"]["popular"]["movies"]
    assert first["recommendations"]


def test_compare_respects_exclusions_and_feedback_in_every_column(client):
    chat(client, "I like romance but no horror")
    liked = chat(client, "recommend a romance movie")["recommendations"][0]["movie_id"]
    disliked = chat(client, "more romance")["recommendations"][0]["movie_id"]
    client.post("/feedback", json={"session_id": SID, "movie_id": liked, "action": "like"})
    client.post("/feedback", json={"session_id": SID, "movie_id": disliked, "action": "dislike"})
    d = client.post("/compare", json={"session_id": SID, "count": 8}).json()
    for name, col in d["columns"].items():
        ids = {m["movie_id"] for m in col["movies"]}
        assert liked not in ids and disliked not in ids, name
        assert all("Horror" not in m["genres"] for m in col["movies"]), name
    assert d["signals"]["liked"] == 1 and d["signals"]["disliked"] == 1


def test_compare_cold_start_is_honest_about_fallbacks(client):
    d = client.post("/compare", json={"session_id": "fresh-compare-0001"}).json()
    assert d["columns"]["collaborative"]["strategy_used"] == "popular"  # no taste signal: said so, not faked
    assert any("signal" in n for n in d["columns"]["collaborative"]["notes"])
    assert d["columns"]["hybrid"]["regime"] == "cold" and d["signals"]["liked"] == 0


def test_compare_with_an_anchor_movie_and_validation(client):
    d = client.post("/compare", json={"session_id": SID, "anchor_movie_id": 1, "count": 5}).json()
    assert d["signals"]["liked"] == 1
    assert 1 not in {m["movie_id"] for c in d["columns"].values() for m in c["movies"]}
    assert client.post("/compare", json={"session_id": SID, "anchor_movie_id": 999999}).status_code == 404
    assert client.post("/compare", json={"session_id": SID, "count": 99}).status_code == 422
    assert client.post("/compare", json={"session_id": "x"}).status_code == 422


def test_compare_includes_real_offline_scores_when_a_report_exists(settings):
    (settings.reports_dir).mkdir(parents=True, exist_ok=True)
    metrics = {m: {"ndcg": 0.1 + i / 100} for i, m in enumerate(["popular", "content", "collaborative", "hybrid"])}
    (settings.reports_dir / "evaluation.json").write_text(json.dumps({"metrics": metrics, "chosen_config": {"knn": {"k": 30, "shrinkage": 2.0}, "hybrid_weights": None}}))
    with TestClient(create_app(settings, build_state(settings))) as c:
        d = c.post("/compare", json={"session_id": SID}).json()
    assert d["offline_ndcg"] == {"popular": 0.1, "content": 0.11, "collaborative": 0.12, "hybrid": 0.13}


# ------------------------------------------------------------------ streaming (Server-Sent Events)
def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln and not ln.startswith(":")]
        if not lines:
            continue
        name = next(ln[7:] for ln in lines if ln.startswith("event: "))
        data = json.loads(next(ln[6:] for ln in lines if ln.startswith("data: ")))
        events.append((name, data))
    return events


def stream(client, path, body):
    with client.stream("POST", path, json=body) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert r.headers.get("x-accel-buffering") == "no" and "no-cache" in r.headers["cache-control"]
        return parse_sse("".join(r.iter_text()))


def test_stream_emits_real_milestones_in_order_then_the_full_response(client):
    ev = stream(client, "/chat/stream", {"session_id": SID, "message": "recommend a sci-fi movie"})
    names = [n for n, _ in ev]
    assert names == ["step", "step", "cards", "step", "done"]
    assert [d["step"] for n, d in ev if n == "step"] == ["interpret", "rank", "write"]
    cards = dict(ev)["cards"]
    done = dict(ev)["done"]["response"]
    assert [c["movie_id"] for c in cards["cards"]] == [c["movie_id"] for c in done["recommendations"]]  # picks never change after being sent
    assert cards["profile"]["genres"] == ["Sci-Fi"] and done["reply"] and done["llm"]["mode"] == "fallback"
    assert client.get(f"/sessions/{SID}").json()["last_cards"]  # the turn was saved exactly like /chat


def test_stream_matches_the_non_streaming_endpoint(client):
    # two fresh sessions with the same message: streaming must not change what is recommended or said
    a = dict(stream(client, "/chat/stream", {"session_id": "stream-equiv-aaaa", "message": "recommend a romance movie"}))["done"]["response"]
    b = client.post("/chat", json={"session_id": "stream-equiv-bbbb", "message": "recommend a romance movie"}).json()
    assert [c["movie_id"] for c in a["recommendations"]] == [c["movie_id"] for c in b["recommendations"]]
    assert a["reply"] == b["reply"] and a["intent"] == b["intent"] and a["notes"] == b["notes"]


def test_stream_for_simple_replies_skips_ranking(client):
    ev = stream(client, "/chat/stream", {"session_id": SID, "message": "what can you do?"})
    assert [n for n, _ in ev] == ["step", "done"] and dict(ev)["done"]["response"]["intent"] == "help"


def test_stream_validation_and_errors_happen_before_streaming_starts(client):
    assert client.post("/chat/stream", json={"session_id": SID, "message": ""}).status_code == 422
    assert client.post("/chat/stream", json={"session_id": SID, "message": "a" * 900}).status_code == 422
    r = client.post("/recommend/stream", json={"session_id": SID, "anchor_movie_id": 999999})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_recommend_stream_with_an_anchor(client):
    ev = stream(client, "/recommend/stream", {"session_id": SID, "anchor_movie_id": 1})
    done = dict(ev)["done"]["response"]
    assert done["intent"] == "similar" and 1 not in [c["movie_id"] for c in done["recommendations"]]
    assert [n for n, _ in ev][-2:] == ["step", "done"]


def test_a_failure_inside_the_turn_becomes_one_clean_error_event(settings, monkeypatch):
    state = build_state(settings)
    monkeypatch.setattr(state.service, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret /etc/internal")))
    with TestClient(create_app(settings, state)) as c:
        ev = stream(c, "/chat/stream", {"session_id": SID, "message": "hello there"})
    assert [n for n, _ in ev] == ["error"] and ev[0][1]["status"] == 500
    assert "secret" not in json.dumps(ev) and "done" not in [n for n, _ in ev]


def test_stream_with_claude_still_sends_cards_before_the_reply(settings):
    order = []

    def create(**kw):
        if "language-understanding" in kw["system"]:
            return text(PREFS)
        order.append("compose-called")
        return text({"reply": "A short sci-fi selection.", "follow_ups": ["More", "Hidden gems", "Highly rated"]})

    with make_client_with_claude(settings, create) as c:
        ev = stream(c, "/chat/stream", {"session_id": SID, "message": "sci-fi"})
    names = [n for n, _ in ev]
    assert names.index("cards") < names.index("done") and order == ["compose-called"]
    assert dict(ev)["done"]["response"]["llm"]["mode"] == "claude" and dict(ev)["done"]["response"]["reply"].startswith("A short sci-fi")
