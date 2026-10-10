import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.config import Settings
from app.llm import ClaudeService, LLMUnavailable, _numbers_grounded, preferences_schema
from app.nlu import canonical_genres, mood_exclusions, parse_with_rules, resolve_preferences
from app.schemas import Preferences


# ------------------------------------------------------------------ rule-based fallback parser
def test_rules_extract_genre_and_mood(catalog):
    p = parse_with_rules("I want a lighthearted comedy for tonight", catalog)
    assert p.genres == ["Comedy"] and p.mood == "lighthearted" and p.intent == "recommend"


def test_rules_extract_exclusions_and_violence(catalog):
    p = parse_with_rules("No horror and nothing too violent", catalog)
    assert "Horror" in p.excluded_genres and "War" in p.excluded_genres and not p.genres


def test_requested_genre_beats_violence_exclusion(catalog):
    p = parse_with_rules("scary movies but not too gory", catalog)
    assert p.genres == ["Horror"] and "Horror" not in p.excluded_genres


def test_rules_titles_sentiment(catalog):
    p = parse_with_rules("I loved Alpha Story but hated Bravo Story", catalog)
    assert p.liked_titles == ["Alpha Story"] and p.disliked_titles == ["Bravo Story"]


def test_rules_anchor_and_ordinal(catalog):
    assert parse_with_rules("something like Alpha Story", catalog).anchor_titles == ["Alpha Story"]
    p = parse_with_rules("Show me more like the second movie", catalog)
    assert p.intent == "similar" and p.ordinal_reference == 2


def test_rules_numbers(catalog):
    p = parse_with_rules("give me 3 romantic movies from the 90s", catalog)
    assert (p.count, p.genres, p.year_min, p.year_max) == (3, ["Romance"], 1990, 1999)
    q = parse_with_rules("underrated science fiction", catalog)
    assert q.novelty and q.novelty > 0.6 and q.genres == ["Sci-Fi"]
    assert parse_with_rules("a highly rated thriller", catalog).min_rating == 4.0


def test_rules_count_with_genre_plural(catalog):
    assert parse_with_rules("give me 12 comedies", catalog).count == 12
    assert parse_with_rules("show me five great sci-fi films", catalog).count == 5
    assert parse_with_rules("3 thrillers please", catalog).count == 3


def test_rules_intents(catalog):
    assert parse_with_rules("why did you recommend this?", catalog).intent == "explain"
    assert parse_with_rules("I didn't like those. Try something different.", catalog).intent == "reject_last"
    assert parse_with_rules("start over", catalog).intent == "reset"
    assert parse_with_rules("what can you do?", catalog).intent == "help"


def test_runtime_is_flagged_unsupported_not_faked(catalog):
    p = parse_with_rules("a thriller under two hours", catalog)
    assert p.max_runtime_minutes == 120
    assert resolve_preferences(p, catalog).unsupported == ["runtime"]


def test_resolver_drops_hallucinated_titles_and_genres(catalog):
    prefs = Preferences(liked_titles=["Alpha Story", "The Imaginary Movie 9"], genres=["Sci-Fi", "Space Opera 3000"], novelty=7, count=99)
    r = resolve_preferences(prefs, catalog)
    assert r.liked_ids == [1] and r.unresolved_titles == ["The Imaginary Movie 9"]
    assert r.genres == ["Sci-Fi"]
    assert prefs.novelty == 1.0 and prefs.count == 12  # clamped


def test_canonical_genres_and_mood_helpers(catalog):
    assert canonical_genres(["sci fi", "comedies", "nonsense"], catalog.all_genres) == ["Sci-Fi", "Comedy"]
    assert "Horror" in mood_exclusions("lighthearted and fun", ["Horror", "War", "Crime", "Thriller"])
    assert mood_exclusions(None, []) == []


# ------------------------------------------------------------------ Claude service failure handling
def settings_with_key(key="sk-test") -> Settings:
    return Settings(_env_file=None, anthropic_api_key=key)


def fake_client(create):
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def reply(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


GENRES = ["Comedy", "Horror"]
REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_missing_key_means_unavailable_not_crash():
    svc = ClaudeService(Settings(_env_file=None, anthropic_api_key=None))
    assert not svc.enabled
    with pytest.raises(LLMUnavailable, match="No Anthropic API key"):
        svc.parse("hi", GENRES, "")


def test_parse_success_validates_into_preferences():
    payload = json.dumps({"intent": "recommend", "genres": ["Comedy"], "excluded_genres": [], "liked_titles": [], "disliked_titles": [],
                          "anchor_titles": [], "ordinal_reference": None, "mood": None, "min_rating": None,
                          "max_runtime_minutes": None, "count": 4, "year_min": None, "year_max": None, "novelty": None})
    svc = ClaudeService(settings_with_key(), fake_client(lambda **kw: reply(payload)))
    prefs = svc.parse("a comedy", GENRES, "")
    assert prefs.genres == ["Comedy"] and prefs.count == 4


def test_request_uses_structured_output_and_low_effort():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return reply(json.dumps({"reply": "ok", "follow_ups": []}))

    ClaudeService(settings_with_key(), fake_client(create)).compose("hi", {"x": 1})
    assert seen["output_config"]["format"]["type"] == "json_schema" and seen["output_config"]["effort"] == "low"  # default model supports effort
    assert "<message>" in seen["messages"][0]["content"]  # user text is delimited as data


@pytest.mark.parametrize(
    "exc, expected",
    [
        (anthropic.APITimeoutError(request=REQ), "timed out"),
        (anthropic.RateLimitError("slow", response=httpx.Response(429, request=REQ), body=None), "rate-limited"),
        (anthropic.AuthenticationError("bad", response=httpx.Response(401, request=REQ), body=None), "rejected"),
        (anthropic.APIConnectionError(request=REQ), "Could not reach"),
        (anthropic.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None), "500"),
    ],
)
def test_api_errors_map_to_safe_reasons(exc, expected):
    def create(**kw):
        raise exc

    svc = ClaudeService(settings_with_key(), fake_client(create))
    with pytest.raises(LLMUnavailable) as info:
        svc.parse("x", GENRES, "")
    assert expected in info.value.reason and "sk-test" not in info.value.reason


@pytest.mark.parametrize("bad", ["not json at all", "[1,2,3]", json.dumps({"intent": "dance"}), ""])
def test_malformed_model_output_is_rejected(bad):
    svc = ClaudeService(settings_with_key(), fake_client(lambda **kw: reply(bad)))
    with pytest.raises(LLMUnavailable, match="malformed"):
        svc.parse("x", GENRES, "")


def test_refusal_and_truncation_are_unavailable():
    for stop in ("refusal", "max_tokens"):
        svc = ClaudeService(settings_with_key(), fake_client(lambda **kw: reply("{}", stop)))
        with pytest.raises(LLMUnavailable):
            svc.compose("x", {})


def test_ungrounded_numbers_in_reply_are_rejected():
    facts = {"rating": 4.2, "n": 215}
    assert _numbers_grounded("Rated 4.2 by 215 people", json.dumps(facts))
    assert not _numbers_grounded("Rated 4.9 by 215 people", json.dumps(facts))
    svc = ClaudeService(settings_with_key(), fake_client(lambda **kw: reply(json.dumps({"reply": "It has 9.9 stars.", "follow_ups": []}))))
    with pytest.raises(LLMUnavailable, match="ungrounded"):
        svc.compose("x", facts)


def test_schema_constrains_genres_to_dataset_enum():
    schema = preferences_schema(["Comedy"])
    assert schema["properties"]["genres"]["items"]["enum"] == ["Comedy"] and schema["additionalProperties"] is False


def test_workspace_header_is_sent_only_when_configured(monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr("app.llm.anthropic.Anthropic", Fake)
    ClaudeService(Settings(_env_file=None, anthropic_api_key="sk-x", anthropic_workspace_id="wrkspc_123"))._get_client()
    assert seen["default_headers"] == {"anthropic-workspace-id": "wrkspc_123"}
    seen.clear()
    ClaudeService(Settings(_env_file=None, anthropic_api_key="sk-x"))._get_client()
    assert seen["default_headers"] is None


def test_api_400_explains_the_workspace_problem_in_plain_words():
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "This API key is not scoped to a workspace, so ..."}}

    def create(**kw):
        raise anthropic.BadRequestError("bad", response=httpx.Response(400, request=REQ, json=body), body=body)

    svc = ClaudeService(settings_with_key(), fake_client(create))
    with pytest.raises(LLMUnavailable) as info:
        svc.parse("x", GENRES, "")
    assert "ANTHROPIC_WORKSPACE_ID" in info.value.reason and "sk-test" not in info.value.reason


def test_check_reports_ok_and_failure_with_caching():
    calls = []

    def ok(**kw):
        calls.append(1)
        return reply(json.dumps({"ok": True}))

    svc = ClaudeService(settings_with_key(), fake_client(ok))
    assert svc.check() == (True, None) and svc.check() == (True, None) and len(calls) == 1  # cached

    def boom(**kw):
        raise anthropic.APITimeoutError(request=REQ)

    bad = ClaudeService(settings_with_key(), fake_client(boom))
    ok_flag, reason = bad.check()
    assert ok_flag is False and "timed out" in reason
    assert ClaudeService(Settings(_env_file=None, anthropic_api_key=None)).enabled is False


def test_config_errors_are_not_retried_on_every_message():
    calls = []
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "key is not scoped to a workspace"}}

    def create(**kw):
        calls.append(1)
        raise anthropic.BadRequestError("bad", response=httpx.Response(400, request=REQ, json=body), body=body)

    svc = ClaudeService(settings_with_key(), fake_client(create))
    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            svc.parse("x", GENRES, "")
    assert len(calls) == 1  # later calls fail fast without touching the network

    timeouts = []

    def flaky(**kw):
        timeouts.append(1)
        raise anthropic.APITimeoutError(request=REQ)

    svc2 = ClaudeService(settings_with_key(), fake_client(flaky))
    for _ in range(2):
        with pytest.raises(LLMUnavailable):
            svc2.parse("x", GENRES, "")
    assert len(timeouts) == 2  # transient errors are retried next time


def test_effort_is_only_sent_to_models_that_support_it():
    from app.llm import supports_effort

    assert supports_effort("claude-opus-5-5") and supports_effort("claude-sonnet-5-5") and supports_effort("claude-sonnet-4-6")
    assert not supports_effort("claude-haiku-4-5") and not supports_effort("claude-haiku-4-5-20251001") and not supports_effort("claude-sonnet-4-5")

    seen = {}

    def create(**kw):
        seen.update(kw)
        return reply(json.dumps({"ok": True}))

    haiku = Settings(_env_file=None, anthropic_api_key="sk-x", claude_model="claude-haiku-4-5")
    ClaudeService(haiku, fake_client(create)).check()
    assert "effort" not in seen["output_config"] and seen["output_config"]["format"]["type"] == "json_schema"
