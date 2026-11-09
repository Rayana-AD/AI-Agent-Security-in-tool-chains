"""OpenAI-compatible DeepSeek / OpenRouter backend for InjecAgent smoke runs."""

from __future__ import annotations

import os


class DeepSeekModel:
    """Drop-in replacement for InjecAgent GPTModel using DeepSeek or OpenRouter."""

    def __init__(self, params):
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.params = params
        self.model_name = params.get("model_name") or "deepseek-chat"

    def prepare_input(self, sys_prompt, user_prompt_filled):
        return [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt_filled},
        ]

    def call_model(self, model_input):
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=model_input,
            temperature=0,
        )
        return completion.choices[0].message.content or ""
