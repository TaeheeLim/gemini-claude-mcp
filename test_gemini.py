"""Gemini 단독 연결 테스트.

MCP와 무관하게 google-genai SDK + GEMINI_API_KEY 조합이 동작하는지만 확인한다.
실행: python test_gemini.py
"""

import os
import sys

from google import genai
from google.genai import types


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("[FAIL] GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        return 1

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"[INFO] 모델: {model}")

    try:
        client = genai.Client()
        chat = client.chats.create(
            model=model,
            config=types.GenerateContentConfig(
                system_instruction="너는 간결하게 한국어로 답하는 토론 상대다."
            ),
        )
        response = chat.send_message("한 문장으로 자기소개를 해줘.")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Gemini 호출 실패: {exc}")
        return 1

    print("[OK] Gemini 응답:")
    print(response.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
