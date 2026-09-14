#!/usr/bin/env python
"""Check whether selected OpenRouter models accept the configured API key."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


BASE_URL = "https://openrouter.ai/api/v1"
ENV_FILE = Path(__file__).with_name(".env")
MODELS = [
    "openai/gpt-5.6-sol",
    "anthropic/claude-opus-4-8",
    "z-ai/glm-5.2",
    "anthropic/claude-sonnet-5",
    "deepseek/deepseek-v4-pro",
    "google/gemini-3.7-flash",
]


def main() -> int:
    load_dotenv(ENV_FILE)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(
            f"错误：没有在 {ENV_FILE} 中找到 OPENROUTER_API_KEY。",
            file=sys.stderr,
        )
        return 2

    client = OpenAI(
        base_url=BASE_URL,
        api_key=api_key,
        timeout=90.0,
        max_retries=0,
    )

    failures = 0
    for model in MODELS:
        print(f"\nTesting {model} ...", flush=True)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=128,
            )
            content = response.choices[0].message.content
            usage = response.usage
            reasoning_tokens = None
            if usage and usage.completion_tokens_details:
                reasoning_tokens = usage.completion_tokens_details.reasoning_tokens

            print("PASS")
            print("Reply:", repr(content))
            print("Actual model:", response.model)
            print(
                "Tokens:",
                usage.total_tokens if usage is not None else "not reported",
            )
            print(
                "Reasoning tokens:",
                reasoning_tokens if reasoning_tokens is not None else "not reported",
            )
        except Exception as exc:
            failures += 1
            status_code = getattr(exc, "status_code", None)
            print("FAIL")
            if status_code is not None:
                print("HTTP status:", status_code)
            body = getattr(exc, "body", None)
            error_message = None
            if isinstance(body, dict):
                error_message = body.get("message")
            print(f"Error: {error_message or type(exc).__name__}")

    print(f"\nSummary: {len(MODELS) - failures}/{len(MODELS)} models passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
