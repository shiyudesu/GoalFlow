"""LLM 统一客户端 — 基于 litellm 的多提供商支持."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from litellm import acompletion


class LLMClient:
    """LLM 客户端.

    统一封装，支持 OpenAI、Claude、本地模型等。
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """发送聊天请求.

        Args:
            messages: 消息列表，格式 [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大token
            response_format: 如 {"type": "json_object"}

        Returns:
            LLM 回复文本
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await acompletion(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}") from e

    async def chat_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> str:
        """便捷方法：system + user 两轮对话."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.chat(messages, **kwargs)
