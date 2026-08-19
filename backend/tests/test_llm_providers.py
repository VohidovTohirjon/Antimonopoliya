"""Provider abstraction over an OpenAI-compatible chat-completions API.

Everything here runs against a mocked OpenAI-compatible server: no GPU, no vLLM
process and no real model are required. The same transport serves a self-hosted
vLLM endpoint and Groq, so both are exercised through the same class.
"""

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.services.llm import (LlmRouter, OpenAICompatibleProvider, ProviderProfile,
                              groq_profile_for_tests, local_profile_for_tests, llm)

LOCAL_URL = "http://llm-server.internal:8000/v1"
LOCAL_MODEL = "openai/gpt-oss-20b"


# --- mocked OpenAI-compatible server ------------------------------------------

class FakeResponse:
    def __init__(self, status_code: int = 200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {
            "choices": [{"message": {"content": "Tekshirilgan javob"}, "finish_reason": "stop"}]
        }
        self.headers = {"x-request-id": "safe-test-id", **(headers or {})}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "xato", request=httpx.Request("POST", "http://fake"),
                response=httpx.Response(self.status_code),
            )


def models_response(*model_ids: str) -> FakeResponse:
    return FakeResponse(200, {"object": "list", "data": [{"id": name} for name in model_ids]})


class FakeServer:
    """Records every request so tests can assert URL, auth and payload shape."""

    post_outcome = FakeResponse()
    get_outcome = models_response(LOCAL_MODEL)
    posts: list[dict] = []
    gets: list[dict] = []

    def __init__(self, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    @staticmethod
    def _next(outcome):
        value = outcome.pop(0) if isinstance(outcome, list) else outcome
        if isinstance(value, Exception):
            raise value
        return value

    async def post(self, url, **kwargs):
        type(self).posts.append({"url": url, "json": kwargs.get("json"),
                                 "headers": kwargs.get("headers") or {}})
        return self._next(type(self).post_outcome)

    async def get(self, url, **kwargs):
        type(self).gets.append({"url": url, "headers": kwargs.get("headers") or {}})
        return self._next(type(self).get_outcome)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeServer)
    FakeServer.posts = []
    FakeServer.gets = []
    FakeServer.post_outcome = FakeResponse()
    FakeServer.get_outcome = models_response(LOCAL_MODEL)
    return FakeServer


@pytest.fixture(autouse=True)
def isolated_settings():
    """Settings are cached; provider tests mutate the environment around them."""
    get_settings.cache_clear()
    llm._providers.clear()
    yield
    get_settings.cache_clear()
    llm._providers.clear()


def local_profile(**overrides) -> ProviderProfile:
    base = ProviderProfile(
        name="local", label="Lokal LLM server", base_url=LOCAL_URL, api_key="",
        models=(LOCAL_MODEL,), timeout_seconds=30.0, max_tokens=3200,
        requires_api_key=False, max_tokens_field="max_tokens",
        send_groq_reasoning_hints=False, strict_schema_models=frozenset({LOCAL_MODEL}),
        degrade_schema_on_rejection=True,
    )
    return ProviderProfile(**{**vars(base), **overrides})


def run(coro):
    return asyncio.run(coro)


# --- local (vLLM) provider ----------------------------------------------------

def test_local_provider_calls_the_configured_endpoint_with_openai_payload(server):
    provider = OpenAICompatibleProvider(local_profile())
    assert run(provider.generate("tizim", "savol")) == "Tekshirilgan javob"
    sent = server.posts[-1]
    assert sent["url"] == f"{LOCAL_URL}/chat/completions"
    payload = sent["json"]
    assert payload["model"] == LOCAL_MODEL
    assert payload["max_tokens"] == 3200
    # Groq-only switches must never be sent to a plain vLLM server.
    assert "max_completion_tokens" not in payload
    assert "include_reasoning" not in payload
    assert "reasoning_effort" not in payload
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]


def test_local_provider_sends_low_reasoning_effort_by_default(server, monkeypatch):
    """gpt-oss decodes far fewer tokens at low reasoning effort."""
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_MODEL", LOCAL_MODEL)
    get_settings.cache_clear()
    assert get_settings().local_llm_reasoning_effort == "low"
    provider = OpenAICompatibleProvider(local_profile_for_tests())
    run(provider.generate("tizim", "savol"))
    assert server.posts[-1]["json"]["reasoning_effort"] == "low"
    # Reasoning is never surfaced: only `content` is read back.
    assert "include_reasoning" not in server.posts[-1]["json"]


def test_reasoning_effort_is_configurable_for_later_tuning(server, monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_REASONING_EFFORT", "medium")
    get_settings.cache_clear()
    provider = OpenAICompatibleProvider(local_profile_for_tests())
    run(provider.generate("tizim", "savol"))
    assert server.posts[-1]["json"]["reasoning_effort"] == "medium"

    # An empty value omits the field entirely for servers that reject it.
    monkeypatch.setenv("LOCAL_LLM_REASONING_EFFORT", "")
    get_settings.cache_clear()
    provider = OpenAICompatibleProvider(local_profile_for_tests())
    run(provider.generate("tizim", "savol"))
    assert "reasoning_effort" not in server.posts[-1]["json"]


def test_reasoning_content_is_never_returned_to_the_caller(server):
    """A gpt-oss server may return reasoning alongside the answer; only content is used."""
    server.post_outcome = FakeResponse(200, {"choices": [{
        "message": {"content": "Yakuniy javob", "reasoning_content": "MAXFIY_FIKRLASH_ZANJIRI"},
        "finish_reason": "stop"}]})
    provider = OpenAICompatibleProvider(local_profile())
    assert run(provider.generate("tizim", "savol")) == "Yakuniy javob"


def test_request_specific_token_budget_overrides_the_profile_default(server):
    provider = OpenAICompatibleProvider(local_profile())
    run(provider.generate("tizim", "savol", max_tokens=512))
    assert server.posts[-1]["json"]["max_tokens"] == 512
    run(provider.generate("tizim", "savol"))
    assert server.posts[-1]["json"]["max_tokens"] == 3200


def test_local_provider_without_api_key_sends_no_authorization_header(server):
    provider = OpenAICompatibleProvider(local_profile())
    run(provider.generate("tizim", "savol"))
    assert "Authorization" not in server.posts[-1]["headers"]


def test_local_provider_sends_bearer_token_when_the_server_requires_one(server):
    provider = OpenAICompatibleProvider(local_profile(api_key="internal-token"))
    run(provider.generate("tizim", "savol"))
    assert server.posts[-1]["headers"]["Authorization"] == "Bearer internal-token"


def test_local_provider_is_unconfigured_without_a_base_url():
    assert OpenAICompatibleProvider(local_profile(base_url="")).configured is False
    # A local server legitimately runs without a token.
    assert OpenAICompatibleProvider(local_profile(api_key="")).configured is True


def test_local_provider_uses_strict_json_schema_when_supported(server):
    server.post_outcome = FakeResponse(200, {
        "choices": [{"message": {"content": '{"answer":"tayyor"}'}, "finish_reason": "stop"}]})
    provider = OpenAICompatibleProvider(local_profile())
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    assert run(provider.generate_structured("tizim", "savol", schema)) == {"answer": "tayyor"}
    response_format = server.posts[-1]["json"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema


def test_single_model_server_degrades_to_json_object_when_schema_is_rejected(server):
    """A vLLM build without json_schema support must not fail the whole request."""
    server.post_outcome = [
        FakeResponse(400),
        FakeResponse(200, {"choices": [{"message": {"content": '{"answer":"tayyor"}'},
                                        "finish_reason": "stop"}]}),
    ]
    provider = OpenAICompatibleProvider(local_profile())
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    assert run(provider.generate_structured("tizim", "savol", schema)) == {"answer": "tayyor"}
    assert server.posts[0]["json"]["response_format"]["type"] == "json_schema"
    retry = server.posts[1]["json"]
    assert retry["response_format"] == {"type": "json_object"}
    # The schema is restated in the prompt so the model still has the contract.
    assert json.dumps(schema, ensure_ascii=False) in retry["messages"][1]["content"]


def test_local_provider_error_mapping_matches_the_shared_contract(server):
    provider = OpenAICompatibleProvider(local_profile())
    for code, expected_status, fragment in (
        (401, 503, "autentifikatsiyasi"),
        (403, 503, "Model ruxsatlarini"),
        (429, 429, "limiti tugagan"),
        (500, 503, "vaqtincha javob olinmadi"),
    ):
        provider.reset_runtime_state()
        server.post_outcome = FakeResponse(code)
        with pytest.raises(HTTPException) as error:
            run(provider.generate("tizim", "savol"))
        assert error.value.status_code == expected_status
        assert fragment in error.value.detail


def test_local_provider_timeout_and_malformed_output_are_explicit(server):
    provider = OpenAICompatibleProvider(local_profile())
    server.post_outcome = httpx.TimeoutException("timeout")
    with pytest.raises(HTTPException) as error:
        run(provider.generate("tizim", "savol"))
    assert error.value.status_code == 504

    for body, message in (
        ({"choices": []}, "kutilmagan format"),
        ({"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]}, "bo‘sh javob"),
        ({"choices": [{"message": {"content": "Yarim"}, "finish_reason": "length"}]},
         "uzunlik chegarasida uzildi"),
    ):
        provider.reset_runtime_state()
        server.post_outcome = FakeResponse(200, body)
        with pytest.raises(HTTPException) as error:
            run(provider.generate("tizim", "savol"))
        assert error.value.status_code == 502
        assert message in error.value.detail


# --- health probe -------------------------------------------------------------

@pytest.mark.parametrize("outcome,state,reachable,loaded", [
    (models_response(LOCAL_MODEL), "ready", True, True),
    (models_response("some/other-model"), "model_missing", True, False),
    (FakeResponse(401), "unauthorized", False, False),
    (FakeResponse(503), "unreachable", False, False),
    (httpx.ConnectError("refused"), "unreachable", False, False),
])
def test_probe_distinguishes_reachability_from_model_loaded(server, outcome, state,
                                                            reachable, loaded):
    server.get_outcome = outcome
    provider = OpenAICompatibleProvider(local_profile())
    health = run(provider.probe())
    assert health.state == state
    assert health.reachable is reachable
    assert health.model_loaded is loaded
    if server.gets:
        assert server.gets[-1]["url"] == f"{LOCAL_URL}/models"


def test_probe_reports_not_configured_without_touching_the_network(server):
    provider = OpenAICompatibleProvider(local_profile(base_url=""))
    health = run(provider.probe())
    assert health.state == "not_configured"
    assert health.reachable is False
    assert server.gets == []


def test_health_output_never_exposes_urls_or_credentials(server, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "super-secret-token")
    monkeypatch.setenv("LOCAL_LLM_MODEL", LOCAL_MODEL)
    get_settings.cache_clear()
    router = LlmRouter()
    report = run(router.health())
    serialised = json.dumps([vars(item) for item in report], ensure_ascii=False)
    assert "super-secret-token" not in serialised
    assert "llm-server.internal" not in serialised
    assert LOCAL_URL not in serialised


# --- router ------------------------------------------------------------------

def configure_local(monkeypatch, *, fallback: bool = False, groq_key: str = "groq-key"):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_MODEL", LOCAL_MODEL)
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", groq_key)
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "true" if fallback else "false")
    get_settings.cache_clear()
    return LlmRouter()


def test_local_is_primary_and_groq_is_not_used_without_explicit_fallback(server, monkeypatch):
    router = configure_local(monkeypatch, fallback=False)
    profiles = router.profiles()
    assert [profile.name for profile in profiles] == ["local"]
    assert router.provider_name == "local"
    assert run(router.generate("tizim", "savol")) == "Tekshirilgan javob"
    assert all(post["url"].startswith(LOCAL_URL) for post in server.posts)
    assert not any("groq.com" in post["url"] for post in server.posts)


def test_enabled_fallback_reaches_groq_only_after_the_local_server_fails(server, monkeypatch):
    router = configure_local(monkeypatch, fallback=True)
    assert [profile.name for profile in router.profiles()] == ["local", "groq"]
    server.post_outcome = [FakeResponse(503), FakeResponse(200)]
    assert run(router.generate("tizim", "savol")) == "Tekshirilgan javob"
    assert server.posts[0]["url"].startswith(LOCAL_URL)
    assert "api.groq.com" in server.posts[-1]["url"]


def test_local_failure_without_fallback_surfaces_the_error(server, monkeypatch):
    router = configure_local(monkeypatch, fallback=False)
    server.post_outcome = FakeResponse(503)
    with pytest.raises(HTTPException) as error:
        run(router.generate("tizim", "savol"))
    assert error.value.status_code == 503
    assert not any("groq.com" in post["url"] for post in server.posts)


def test_groq_stays_primary_when_provider_is_not_local(server, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    router = LlmRouter()
    assert router.provider_name == "groq"
    run(router.generate("tizim", "savol"))
    assert "api.groq.com" in server.posts[-1]["url"]


def test_forced_unavailable_blocks_every_provider(server, monkeypatch):
    router = configure_local(monkeypatch)
    monkeypatch.setenv("LLM_FORCE_UNAVAILABLE", "true")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as error:
        run(router.generate("tizim", "savol"))
    assert error.value.status_code == 503
    assert "diagnostika rejimida" in error.value.detail
    assert server.posts == []


def test_router_reports_unconfigured_provider_without_calling_out(server, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    router = LlmRouter()
    assert router.configured is False
    with pytest.raises(HTTPException) as error:
        run(router.generate("tizim", "savol"))
    assert error.value.status_code == 503
    assert "sozlanmagan" in error.value.detail
    assert server.posts == []


# --- groq profile still behaves as before -------------------------------------

def test_groq_profile_keeps_its_payload_quirks_and_model_rotation(server, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    # The suite pins GROQ_MODEL; clear it so the declared pool order applies here.
    monkeypatch.setenv("GROQ_MODEL", "")
    get_settings.cache_clear()
    provider = OpenAICompatibleProvider(groq_profile_for_tests())
    server.post_outcome = [FakeResponse(429, headers={"retry-after": "120"}), FakeResponse(200)]
    assert run(provider.generate("tizim", "savol")) == "Tekshirilgan javob"
    assert [post["json"]["model"] for post in server.posts] == [
        "openai/gpt-oss-120b", "qwen/qwen3.6-27b",
    ]
    first = server.posts[0]["json"]
    assert first["max_completion_tokens"] == 3200 and "max_tokens" not in first
    assert first["include_reasoning"] is False and first["reasoning_effort"] == "low"
    assert server.posts[1]["json"]["reasoning_effort"] == "none"
    assert provider.active_model == "qwen/qwen3.6-27b"
    provider.reset_runtime_state()
    assert provider.active_model == "openai/gpt-oss-120b"


# --- diagnostics surface ------------------------------------------------------

def configure_app_for_local(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_MODEL", LOCAL_MODEL)
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "super-secret-token")
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    llm._providers.clear()


@pytest.mark.parametrize("outcome,state,reachable,loaded", [
    (models_response(LOCAL_MODEL), "ready", True, True),
    (models_response("other/model"), "model_missing", True, False),
    (httpx.ConnectError("refused"), "unreachable", False, False),
    (FakeResponse(401), "unauthorized", False, False),
])
def test_admin_diagnostics_distinguish_backend_server_and_model(
        client, admin_headers, server, monkeypatch, outcome, state, reachable, loaded):
    configure_app_for_local(monkeypatch)
    server.get_outcome = outcome
    response = client.get("/api/system/status", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    # 1. application backend available — the endpoint answered at all
    assert body["api"] == "ready"
    assert body["llm_provider"] == "local"
    assert body["llm_fallback_enabled"] is False
    primary = body["llm_providers"][0]
    assert primary["role"] == "primary" and primary["name"] == "local"
    # 2. server reachable  3. model loaded  4. provider unavailable
    assert primary["state"] == state
    assert primary["reachable"] is reachable
    assert primary["model_loaded"] is loaded


def test_admin_diagnostics_never_return_the_endpoint_or_token(
        client, admin_headers, server, monkeypatch):
    configure_app_for_local(monkeypatch)
    body = client.get("/api/system/status", headers=admin_headers).text
    assert "super-secret-token" not in body
    assert "llm-server.internal" not in body
    assert LOCAL_URL not in body
    assert "/v1" not in body


def test_employee_readiness_exposes_no_provider_internals(
        client, xodim_headers, server, monkeypatch):
    configure_app_for_local(monkeypatch)
    response = client.get("/api/ai/readiness", headers=xodim_headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"legal_ready", "general_ready", "status", "message"}
    assert body["general_ready"] is True
    serialised = response.text
    for secret in ("super-secret-token", "llm-server.internal", LOCAL_URL, LOCAL_MODEL,
                   "vllm", "groq"):
        assert secret.lower() not in serialised.lower()
    # The technical diagnostics endpoint stays administrator-only.
    assert client.get("/api/system/status", headers=xodim_headers).status_code == 403


def test_local_profile_is_built_from_environment(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("LOCAL_LLM_MODEL", LOCAL_MODEL)
    monkeypatch.setenv("LOCAL_LLM_MODELS", "extra/model-a")
    get_settings.cache_clear()
    profile = local_profile_for_tests()
    assert profile.base_url == LOCAL_URL
    assert profile.models == (LOCAL_MODEL, "extra/model-a")
    assert profile.max_tokens_field == "max_tokens"
    assert profile.send_groq_reasoning_hints is False
    assert profile.requires_api_key is False
