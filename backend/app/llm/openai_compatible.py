import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings


class LLMError(RuntimeError):
    pass


class OpenAICompatibleChatModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        base_url = self.settings.active_llm_base_url.rstrip("/")
        model_id = self.settings.active_llm_model
        api_key = self.settings.active_llm_api_key
        if not base_url or not model_id:
            raise LLMError("回答模型尚未配置")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": self.settings.llm_max_tokens if max_tokens is None else max_tokens,
        }
        timeout = httpx.Timeout(
            connect=15,
            read=self.settings.llm_timeout_seconds,
            write=30,
            pool=15,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise LLMError(f"回答模型请求失败（{response.status_code}）：{body[:300]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event: dict[str, Any] = json.loads(raw)
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        content = choices[0].get("delta", {}).get("content")
                        if isinstance(content, str) and content:
                            yield content
                    except (ValueError, TypeError, AttributeError):
                        continue

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0,
    ) -> str:
        parts = []
        async for content in self.stream(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            parts.append(content)
        return "".join(parts)
