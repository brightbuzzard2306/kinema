"""Deployment safeguards: access code, rate limits, daily Claude budget."""

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.llm import ClaudeService, LLMUnavailable
from app.main import build_state, create_app
from app.protect import DailyBudget, SlidingWindow, codes_match

from .test_nlu_and_llm import GENRES, fake_client, reply, settings_with_key

CODE = "open-sesame-42"
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
        assert c.get(path, headers={"X-Access-Code": CODE}).status_code != 401


def test_chat_and_streams_are_locked_without_the_code(settings):
    with locked_client(settings) as c:
        for path in ("/chat", "/chat/stream", "/recommend", "/recommend/stream", "/compare"):
            r = c.post(path, json={"session_id": SID, "message": "hi"})
            assert r.status_code == 401, path
        ok = c.post("/chat", json={"session_id": SID, "message": "a comedy"}, headers={"X-Access-Code": CODE})
        assert ok.status_code == 200


def test_docs_are_not_public_when_locked(settings):
    with locked_client(settings) as c:
        assert c.get("/docs").status_code in (401, 404)  # not served at all
        assert c.get("/openapi.json").status_code in (401, 404)


def test_verify_endpoint_and_lockout_after_wrong_guesses(settings):
    with locked_client(settings) as c:
        assert c.post("/access/verify", json={"code": CODE}).json() == {"ok": True, "required": True}
        for _ in range(8):
            assert c.post("/access/verify", json={"code": "wrong"}).status_code == 401
        r = c.post("/access/verify", json={"code": CODE})  # even the right code waits once locked out
        assert r.status_code == 429 and r.headers["retry-after"] and r.json()["error"]["code"] == "rate_limited"


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
        h = {"X-Access-Code": CODE}
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
