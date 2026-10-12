"""Deployment safeguards: access code, rate limits, daily Claude budget."""

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.llm import ClaudeService, LLMUnavailable
from app.main import build_state, create_app
from app.protect import DailyBudget, SlidingWindow, codes_match, derive_token

from .test_nlu_and_llm import GENRES, fake_client, reply, settings_with_key

CODE = "open-sesame-42"
TOKEN = derive_token(CODE)  # what the browser sends after /access/verify accepted the code
SID = "protect-session-01"


def locked_client(settings, **overrides):
    s = settings.model_copy(update={"access_code": SecretStr(CODE), **overrides})
    return TestClient(create_app(s, build_state(s)))


# ------------------------------------------------------------------ access code
def test_health_is_open_and_says_a_code_is_required(settings):
    with locked_client(settings) as c:
        body = c.get("/health").json()
        assert body["access"] == {"required": True}
        assert c.head("/health").status_code == 200  # uptime monitors


def test_open_by_default_for_local_development(settings):
    with TestClient(create_app(settings, build_state(settings))) as c:
        assert c.get("/health").json()["access"] == {"required": False}
        assert c.get("/meta").status_code == 200


@pytest.mark.parametrize("path", ["/meta", "/movies", "/evaluation", f"/sessions/{SID}", "/llm/status"])
def test_protected_routes_need_the_code(settings, path):
    with locked_client(settings) as c:
        r = c.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "access_denied"
        assert c.get(path, headers={"X-Access-Code": "nope"}).status_code == 401
        assert c.get(path, headers={"X-Access-Code": TOKEN}).status_code != 401
        assert c.get(path, headers={"X-Access-Code": CODE}).status_code == 401  # the raw code is NOT accepted: guessing it is only possible on /access/verify


def test_chat_and_streams_are_locked_without_the_code(settings):
    with locked_client(settings) as c:
        for path in ("/chat", "/chat/stream", "/recommend", "/recommend/stream", "/compare"):
            r = c.post(path, json={"session_id": SID, "message": "hi"})
            assert r.status_code == 401, path
        ok = c.post("/chat", json={"session_id": SID, "message": "a comedy"}, headers={"X-Access-Code": TOKEN})
        assert ok.status_code == 200


def test_docs_are_not_public_when_locked(settings):
    with locked_client(settings) as c:
        assert c.get("/docs").status_code in (401, 404)  # not served at all
        assert c.get("/openapi.json").status_code in (401, 404)


def test_verify_endpoint_and_lockout_after_wrong_guesses(settings):
    with locked_client(settings) as c:
        ok = c.post("/access/verify", json={"code": CODE}).json()
        assert ok == {"ok": True, "required": True, "token": TOKEN} and CODE not in str(ok)
        assert c.get("/meta", headers={"X-Access-Code": ok["token"]}).status_code == 200  # the token the server hands out really works
        for _ in range(8):
            assert c.post("/access/verify", json={"code": "wrong"}).status_code == 401
        r = c.post("/access/verify", json={"code": CODE})  # even the right code waits once locked out
        assert r.status_code == 429 and r.headers["retry-after"] and r.json()["error"]["code"] == "rate_limited"


def test_forging_forwarded_for_cannot_dodge_the_guess_limit(settings):
    """Regression for the live finding: a different X-Forwarded-For per guess used to give every guess a fresh allowance."""
    with locked_client(settings) as c:
        codes = [c.post("/access/verify", json={"code": f"guess{i}"}, headers={"X-Forwarded-For": f"203.0.113.{i}, 198.51.100.7"}).status_code for i in range(12)]
        assert codes[:8] == [401] * 8 and set(codes[8:]) == {429}  # same real visitor (the last entry): locked after 8


def test_sitewide_cap_stops_a_distributed_guesser(settings):
    with locked_client(settings) as c:
        codes = [c.post("/access/verify", json={"code": f"g{i}"}, headers={"CF-Connecting-IP": f"192.0.2.{i % 250}"}).status_code for i in range(70)]
        assert codes[:60] == [401] * 60 and set(codes[60:]) == {429}  # 60 wrong guesses from 'many' visitors, then everyone waits
        assert c.post("/access/verify", json={"code": CODE}, headers={"CF-Connecting-IP": "192.0.2.250"}).status_code == 429


def test_guessing_through_normal_routes_gets_nowhere(settings):
    with locked_client(settings) as c:
        results = {c.get("/meta", headers={"X-Access-Code": g}).status_code for g in ([CODE] + [f"guess{i}" for i in range(50)])}
        assert results == {401}  # not even the real code works there, so there is nothing to brute-force


def test_visitor_bucket_ignores_the_forgeable_start_of_forwarded_for(settings):
    with locked_client(settings, rate_heavy_per_min=2) as c:
        h = {"X-Access-Code": TOKEN}
        body = {"session_id": SID, "message": "a comedy"}
        sent = [c.post("/chat", json=body, headers={**h, "X-Forwarded-For": f"10.0.0.{i}, 198.51.100.9"}).status_code for i in range(4)]
        assert sent == [200, 200, 429, 429]
        other = c.post("/chat", json=body, headers={**h, "X-Forwarded-For": "10.0.0.1, 198.51.100.10"})  # genuinely another visitor
        assert other.status_code == 200
        cdn = c.post("/chat", json=body, headers={**h, "X-Forwarded-For": "198.51.100.9", "CF-Connecting-IP": "203.0.113.200"})  # the CDN's own header wins
        assert cdn.status_code == 200


def test_oversized_bodies_are_refused_before_any_processing(settings):
    with locked_client(settings) as c:
        big = b'{"session_id":"aaaaaaaaaaaa","message":"' + b"a" * (300 * 1024) + b'"}'
        for headers in ({}, {"X-Access-Code": TOKEN}):  # a stranger and an authorised visitor alike
            r = c.post("/chat", content=big, headers={"content-type": "application/json", **headers})
            assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
        small = c.post("/chat", json={"session_id": SID, "message": "a comedy"}, headers={"X-Access-Code": TOKEN})
        assert small.status_code == 200


def test_chunked_upload_without_a_declared_size_is_cut_off_too(settings):
    with locked_client(settings) as c:
        def pieces():
            for _ in range(40):
                yield b"a" * 8192  # 320 KB, streamed with no Content-Length
        r = c.post("/chat", content=pieces(), headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_api_responses_carry_browser_protection_headers(settings):
    with locked_client(settings) as c:
        for r in (c.get("/health"), c.get("/meta", headers={"X-Access-Code": TOKEN}), c.get("/meta")):
            assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
            assert r.headers["referrer-policy"] == "no-referrer" and "max-age" in r.headers["strict-transport-security"]
            assert r.headers["cache-control"] == "no-store"
        with c.stream("POST", "/chat/stream", json={"session_id": SID, "message": "a comedy"}, headers={"X-Access-Code": TOKEN}) as s:
            assert "no-cache" in s.headers["cache-control"]  # the stream keeps its own caching rule


def test_reading_a_session_never_creates_one(settings):
    with locked_client(settings) as c:
        store = c.app.state.rs.service.sessions
        before = len(store._sessions)
        h = {"X-Access-Code": TOKEN}
        for i in range(25):
            assert c.get(f"/sessions/stranger-{i:08d}", headers=h).json()["last_cards"] == []
            assert c.get(f"/sessions/stranger-{i:08d}/profile", headers=h).status_code == 200
        assert len(store._sessions) == before


def test_hosted_copy_refuses_to_start_without_an_access_code(settings, monkeypatch):
    monkeypatch.setenv("RENDER", "true")  # Render sets this on every hosted service
    with pytest.raises(RuntimeError, match="ACCESS_CODE"):
        create_app(settings, build_state(settings))
    create_app(settings.model_copy(update={"access_code": SecretStr(CODE)}), build_state(settings))  # fine with a code
    create_app(settings.model_copy(update={"allow_public": True}), build_state(settings))  # or open on purpose


def test_cors_preflight_allows_the_access_header_and_every_listed_origin(settings):
    s = settings.model_copy(update={"frontend_origin": "https://kinema.co.in, https://www.kinema.co.in/"})
    with TestClient(create_app(s, build_state(s))) as c:
        for origin in ("https://kinema.co.in", "https://www.kinema.co.in"):
            r = c.options("/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-access-code,content-type"})
            assert r.headers["access-control-allow-origin"] == origin
            assert "x-access-code" in r.headers["access-control-allow-headers"].lower()
        bad = c.options("/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in bad.headers


def test_codes_match_is_exact():
    assert codes_match("abc", "abc") and not codes_match("abc", "abd") and not codes_match("", "abc")


# ------------------------------------------------------------------ rate limits
def test_chat_is_rate_limited_per_visitor_and_recovers_in_shape(settings):
    with locked_client(settings, rate_heavy_per_min=2) as c:
        h = {"X-Access-Code": TOKEN}
        body = {"session_id": SID, "message": "a comedy"}
        assert c.post("/chat", json=body, headers=h).status_code == 200
        assert c.post("/chat", json=body, headers=h).status_code == 200
        r = c.post("/chat", json=body, headers=h)
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
        assert c.get("/meta", headers=h).status_code == 200  # cheap routes have their own, larger allowance
        other = c.post("/chat", json=body, headers={**h, "X-Forwarded-For": "203.0.113.9"})  # a different visitor
        assert other.status_code == 200


def test_sliding_window_forgets_old_hits():
    w = SlidingWindow(2, window=0.2)
    assert w.hit("a")[0] and w.hit("a")[0]
    ok, wait = w.hit("a")
    assert not ok and wait >= 1
    time.sleep(0.25)
    assert w.hit("a")[0]


# ------------------------------------------------------------------ daily Claude budget
def test_daily_budget_counts_then_refuses_and_zero_means_unlimited():
    b = DailyBudget(2)
    assert b.take() and b.take() and not b.take()
    assert all(DailyBudget(0).take() for _ in range(50))


def test_claude_calls_stop_at_the_daily_budget_and_the_app_falls_back(settings):
    calls = []

    def create(**kw):
        calls.append(1)
        return reply('{"ok": true}')

    svc = ClaudeService(settings_with_key(), fake_client(create), budget=DailyBudget(1))
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    assert svc._call_json("s", "u", schema, 16) == {"ok": True}
    with pytest.raises(LLMUnavailable, match="allowance"):
        svc._call_json("s", "u", schema, 16)
    assert len(calls) == 1  # the second request never reached Anthropic
