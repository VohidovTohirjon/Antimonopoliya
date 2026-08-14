import json
import logging
import time

import httpx
from fastapi import HTTPException, status

from ..config import get_settings

logger = logging.getLogger(__name__)
STRICT_SCHEMA_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


class GroqService:
    """Priority-ordered Groq model pool with per-model rate-limit cooldowns."""

    def __init__(self):
        self._cooldown_until: dict[str, float] = {}
        self._last_model_used: str | None = None

    @property
    def active_model(self) -> str | None:
        now = time.monotonic()
        return next(
            (model for model in get_settings().groq_model_list
             if self._cooldown_until.get(model, 0) <= now),
            None,
        )

    def reset_runtime_state(self) -> None:
        """Clear transient cooldowns; useful for diagnostics and isolated tests."""
        self._cooldown_until.clear()
        self._last_model_used = None

    def _cool_down(self, model: str, seconds: float) -> None:
        self._cooldown_until[model] = max(
            self._cooldown_until.get(model, 0), time.monotonic() + max(seconds, 1),
        )

    @staticmethod
    def _retry_after(response: httpx.Response, default: float = 60.0) -> float:
        try:
            return min(max(float(response.headers.get("retry-after", default)), 1), 86_400)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _payload(model: str, system: str, user: str, temperature: float,
                 max_tokens: int, response_schema: dict | None) -> dict:
        user_content = user
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if model.startswith("openai/gpt-oss-"):
            payload.update({"include_reasoning": False, "reasoning_effort": "low"})
        elif model.startswith("qwen/"):
            payload["reasoning_effort"] = "none"
        if response_schema and model in STRICT_SCHEMA_MODELS:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "raqobat_structured_result",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        elif response_schema:
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][1]["content"] = (
                user_content
                + "\n\nFaqat JSON obyekt qaytaring. Quyidagi JSON sxemaga qat’iy rioya qiling:\n"
                + json.dumps(response_schema, ensure_ascii=False)
            )
        return payload

    async def generate(self, system: str, user: str, *, temperature: float = 0.15,
                       response_schema: dict | None = None,
                       request_type: str | None = None,
                       _excluded_models: set[str] | None = None) -> str:
        settings = get_settings()
        models = settings.groq_model_list
        diagnostic_type = request_type or ("structured" if response_schema else "text")
        if settings.groq_force_unavailable:
            logger.warning(
                "AI provider request_type=%s model_call=0 provider_status=forced_unavailable",
                diagnostic_type,
            )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "AI xizmati diagnostika rejimida vaqtincha o‘chirilgan",
            )
        if not settings.groq_api_key or not models:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Groq API sozlanmagan. Administratorga murojaat qiling",
            )

        now = time.monotonic()
        excluded = _excluded_models or set()
        candidates = [
            model for model in models
            if model not in excluded and self._cooldown_until.get(model, 0) <= now
        ]
        if not candidates:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Barcha AI modellarining vaqtinchalik limiti tugagan. Birozdan so‘ng qayta urinib ko‘ring",
            )

        saw_rate_limit = saw_timeout = saw_model_error = False
        last_output_error: str | None = None
        for model_index, model in enumerate(candidates, start=1):
            payload = self._payload(
                model, system, user, temperature, settings.groq_max_tokens, response_schema,
            )
            started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                        json=payload,
                    )
                request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                if response.status_code == 401:
                    logger.error("Groq authentication failure status=401 request_id=%s", request_id)
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "AI xizmati autentifikatsiyasi noto‘g‘ri sozlangan. Administratorga murojaat qiling",
                    )
                if response.status_code == 429:
                    saw_rate_limit = True
                    cooldown = self._retry_after(response)
                    self._cool_down(model, cooldown)
                    logger.warning(
                        "Groq model failover reason=rate_limit model=%s cooldown_seconds=%s "
                        "request_id=%s next_model=%s",
                        model, round(cooldown), request_id,
                        candidates[model_index] if model_index < len(candidates) else None,
                    )
                    continue
                if response.status_code == 403:
                    saw_model_error = True
                    self._cool_down(model, 3600)
                    logger.warning(
                        "Groq model failover reason=permission model=%s request_id=%s",
                        model, request_id,
                    )
                    continue
                if response.status_code in {400, 404, 422}:
                    saw_model_error = True
                    self._cool_down(model, 300)
                    logger.warning(
                        "Groq model failover reason=model_or_format status=%s model=%s request_id=%s",
                        response.status_code, model, request_id,
                    )
                    continue
                if response.status_code >= 500:
                    self._cool_down(model, 5)
                    logger.warning(
                        "Groq model failover reason=provider status=%s model=%s request_id=%s",
                        response.status_code, model, request_id,
                    )
                    continue
                if 400 <= response.status_code < 500:
                    self._cool_down(model, 60)
                    continue
                response.raise_for_status()
                try:
                    body = response.json()
                    choice = body["choices"][0]
                    content = choice["message"]["content"].strip()
                    finish_reason = choice.get("finish_reason")
                except (KeyError, IndexError, TypeError, ValueError):
                    last_output_error = "AI xizmati kutilmagan formatda javob qaytardi"
                    self._cool_down(model, 5)
                    continue
                if not content:
                    last_output_error = "AI xizmati bo‘sh javob qaytardi"
                    self._cool_down(model, 5)
                    continue
                if finish_reason == "length":
                    last_output_error = "AI javobi uzunlik chegarasida uzildi. Savolni qisqartirib qayta urinib ko‘ring"
                    self._cool_down(model, 5)
                    continue
                usage = body.get("usage") if isinstance(body, dict) else None
                self._last_model_used = model
                logger.info(
                    "AI provider request_type=%s model_call=%s provider_status=ok model=%s "
                    "input_tokens=%s output_tokens=%s request_id=%s elapsed_ms=%s",
                    diagnostic_type, model_index, model,
                    usage.get("prompt_tokens") if isinstance(usage, dict) else None,
                    usage.get("completion_tokens") if isinstance(usage, dict) else None,
                    request_id, round((time.monotonic() - started) * 1000),
                )
                return content
            except HTTPException:
                raise
            except httpx.TimeoutException:
                saw_timeout = True
                self._cool_down(model, 5)
                logger.warning("Groq model failover reason=timeout model=%s", model)
            except httpx.HTTPError as exc:
                self._cool_down(model, 5)
                logger.warning(
                    "Groq model failover reason=connection model=%s error_type=%s",
                    model, type(exc).__name__,
                )

        if last_output_error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, last_output_error)
        if saw_rate_limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Barcha mavjud AI modellarining vaqtinchalik limiti tugagan. Birozdan so‘ng qayta urinib ko‘ring",
            )
        if saw_timeout:
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "AI modellari belgilangan vaqtda javob bermadi. Qayta urinib ko‘ring",
            )
        if saw_model_error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Groq hisobida sozlangan AI modellaridan foydalanib bo‘lmadi. Model ruxsatlarini tekshiring",
            )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI xizmatidan vaqtincha javob olinmadi. Qayta urinib ko‘ring",
        )

    async def generate_structured(self, system: str, user: str, schema: dict) -> dict:
        tried: set[str] = set()
        for _ in get_settings().groq_model_list:
            content = await self.generate(
                system, user, temperature=0.0, response_schema=schema,
                request_type="structured", _excluded_models=tried,
            )
            if self._last_model_used:
                tried.add(self._last_model_used)
            try:
                value = json.loads(content)
            except (TypeError, ValueError):
                logger.warning(
                    "Groq structured failover reason=invalid_json model=%s",
                    self._last_model_used,
                )
                continue
            if isinstance(value, dict):
                return value
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI modellari tuzilmali javob formatiga rioya qilmadi",
        )


groq = GroqService()
