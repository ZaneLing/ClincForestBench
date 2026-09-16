#!/usr/bin/env python3
"""Send a minimal chat-completion request to OrcaRouter."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


BASE_URL = "https://api.orcarouter.ai/v1"
MODEL = "qwen/qwen3.8-27b-free"
ENV_FILE = Path(__file__).with_name(".env")


def main() -> int:
    load_dotenv(ENV_FILE)
    api_key = os.environ.get("ORCAROUTER_API_KEY")
    if not api_key:
        print(
            f"错误：没有在 {ENV_FILE} 中找到 ORCAROUTER_API_KEY。",
            file=sys.stderr,
        )
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print(
            "错误：依赖未安装。请执行：python -m pip install -r tools/api_smoke/requirements.txt",
            file=sys.stderr,
        )
        return 3

    client = OpenAI(
        base_url=BASE_URL,
        api_key=api_key,
        timeout=60.0,
        max_retries=0,
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Hello"}],
        )
    except Exception as exc:
        print(f"API 调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    content = response.choices[0].message.content
    print("API 调用成功。模型回复：")
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
