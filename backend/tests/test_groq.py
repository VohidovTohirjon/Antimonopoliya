import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.services.groq import GroqService


class FakeResponse:
    def __init__(self, status_code: int = 200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {
            "choices": [{"message": {"content": "Tekshirilgan javob"}, "finish_reason": "stop"}]
        }
        self.headers = {"x-request-id": "safe-test-id", **(headers or {})}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "xato", request=httpx.Request("POST", "https://api.groq.com"),
                response=httpx.Response(self.status_code),
            )


class FakeClient:
    outcome = FakeResponse()
    last_json = None
    sent_json = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *_args, **kwargs):
        type(self).last_json = kwargs.get("json")
        type(self).sent_json.append(kwargs.get("json"))
        outcome = self.outcome.pop(0) if isinstance(self.outcome, list) else self.outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    FakeClient.sent_json = []

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)


def generate():
    return asyncio.run(GroqService().generate("tizim", "savol"))


def test_groq_success(fake_http):
    FakeClient.outcome = FakeResponse()
    assert generate() == "Tekshirilgan javob"
    assert FakeClient.last_json["max_completion_tokens"] == 3200
    assert "max_tokens" not in FakeClient.last_json
    assert FakeClient.last_json["include_reasoning"] is False
    assert FakeClient.last_json["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    ("code", "expected_status", "expected"),
    [
        (401, 503, "autentifikatsiyasi"),
        (403, 503, "Model ruxsatlarini"),
        (404, 503, "Model ruxsatlarini"),
        (422, 503, "Model ruxsatlarini"),
        (429, 429, "limiti tugagan"),
        (500, 503, "vaqtincha javob olinmadi"),
        (502, 503, "vaqtincha javob olinmadi"),
    ],
)
def test_groq_errors_are_mapped_actionably(fake_http, code, expected_status, expected):
    FakeClient.outcome = FakeResponse(code)
    with pytest.raises(HTTPException) as error:
        generate()
    assert error.value.status_code == expected_status
    assert expected in error.value.detail


def test_groq_timeout_is_explicit(fake_http):
    FakeClient.outcome = httpx.TimeoutException("timeout")
    with pytest.raises(HTTPException) as error:
        generate()
    assert error.value.status_code == 504
    assert "belgilangan vaqtda" in error.value.detail


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"choices": []}, "kutilmagan format"),
        ({"choices": [{"message": {"content": "   "}, "finish_reason": "stop"}]}, "bo‘sh javob"),
        ({"choices": [{"message": {"content": "Yarim gap"}, "finish_reason": "length"}]}, "uzunlik chegarasida uzildi"),
    ],
)
def test_groq_malformed_empty_and_truncated_are_failures(fake_http, body, message):
    FakeClient.outcome = FakeResponse(200, body)
    with pytest.raises(HTTPException) as error:
        generate()
    assert error.value.status_code == 502
    assert message in error.value.detail


def test_rate_limit_immediately_rotates_to_next_model(fake_http):
    service = GroqService()
    FakeClient.outcome = [
        FakeResponse(429, headers={"retry-after": "120"}),
        FakeResponse(200),
    ]
    assert asyncio.run(service.generate("tizim", "savol")) == "Tekshirilgan javob"
    assert [payload["model"] for payload in FakeClient.sent_json] == [
        "openai/gpt-oss-20b", "openai/gpt-oss-120b",
    ]
    assert service.active_model == "openai/gpt-oss-120b"
    service.reset_runtime_state()
    assert service.active_model == "openai/gpt-oss-20b"


def test_structured_output_uses_json_mode_on_non_strict_fallback(fake_http):
    service = GroqService()
    FakeClient.outcome = [
        FakeResponse(429), FakeResponse(429),
        FakeResponse(200, {"choices": [{"message": {"content": '{"answer":"tayyor"}'},
                                        "finish_reason": "stop"}]}),
    ]
    result = asyncio.run(service.generate_structured(
        "tizim", "savol", {"type": "object", "properties": {"answer": {"type": "string"}}},
    ))
    assert result == {"answer": "tayyor"}
    assert FakeClient.sent_json[-1]["model"] == "qwen/qwen3.6-27b"
    assert FakeClient.sent_json[-1]["response_format"] == {"type": "json_object"}
