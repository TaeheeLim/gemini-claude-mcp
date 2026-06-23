"""AI Debate MCP Server (어댑터).

Claude Code(MCP 클라이언트)가 토론을 주도하고, 상대 토론자로 Gemini를 호출하기 위한
MCP 서버다. Gemini 쪽은 MCP를 전혀 모르며, 평범한 HTTPS API 호출(`google-genai`)일 뿐이다.

- Transport: stdio (FastMCP 기본값)
- Gemini 모델: 환경변수 GEMINI_MODEL (기본 gemini-2.5-flash)
- API 키: 환경변수 GEMINI_API_KEY (SDK가 자동 인식)
- 대화 상태: conversation_id 별로 채팅 세션을 메모리에 누적한다.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

# 모든 토론의 기본 말투. persona(입장)와 별개로 항상 적용된다.
# 격식 있는 토론이 아니라 20대 남자들이 투닥거리며 싸우는 톤.
BANTER_STYLE = (
    "너는 20대 남자다. 친한 친구랑 장난치듯 투닥거리는 말투로 토론해라. "
    "반말, 드립, 깐죽거림, 약간의 시비조를 섞어서 짧고 웃기게 받아쳐라. "
    "'ㅋㅋ', '아니 진짜', '팩트는', '야' 같은 구어체를 자유롭게 쓴다. "
    "격식·존댓말·딱딱한 개조식 나열은 금지. 욕설은 순화해서 쓴다. "
    "한 번에 3~5문장 이내로 짧게. 상대 말꼬리를 잡고 놀리되 토론 주제에서 벗어나진 마라."
)

# 토론 심판용 말투/지침. 토론에 참가하지 않은 '제3자 Gemini 세션'에게 부여한다.
# 어느 편도 들지 않고 공정하게 승패를 가르는 게 목적이라 BANTER_STYLE과 분리한다.
JUDGE_STYLE = (
    "너는 토론 심판이다. 🔴 Claude와 🔵 Gemini가 주고받은 토론 전체 기록을 받게 된다. "
    "너는 토론 당사자가 아니므로 어느 한쪽 편도 들지 말고 철저히 공정하게 평가하라. "
    "다음 형식으로 판정한다: "
    "(1) 양측 핵심 논거를 한 줄씩 요약, "
    "(2) 🔴 Claude와 🔵 Gemini 각각 10점 만점 점수 + 근거, "
    "(3) **승자와 패자를 분명히 선언**하고 결정적인 이유 한두 문장. "
    "말투는 가볍고 위트있게 하되, 판정 자체는 단호하고 명확하게 내려라. 비기는 판정은 피하라."
)

mcp = FastMCP("ai-debate")

# conversation_id -> google.genai 채팅 세션 객체
_sessions: dict[str, object] = {}

# 지연 초기화되는 google-genai 클라이언트 (싱글턴)
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """google-genai 클라이언트를 지연 생성한다.

    GEMINI_API_KEY가 없으면 명확한 메시지와 함께 RuntimeError를 던진다.
    클라이언트는 한 번만 만들어 재사용한다.
    """
    global _client
    if _client is not None:
        return _client

    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다. "
            "Gemini API 키를 환경변수 또는 .mcp.json의 env에 설정하세요."
        )

    # genai.Client()는 GEMINI_API_KEY 환경변수를 자동 인식한다.
    _client = genai.Client()
    return _client


def _get_or_create_session(conversation_id: str, persona: str):
    """conversation_id에 해당하는 채팅 세션을 반환한다.

    세션이 없으면 새로 만들고, persona가 주어졌으면 system_instruction으로 설정한다.
    persona는 해당 conversation_id의 첫 호출(=세션 생성 시점)에만 적용된다.
    """
    session = _sessions.get(conversation_id)
    if session is not None:
        return session

    client = _get_client()

    # 말투(BANTER_STYLE)는 항상 적용하고, persona가 있으면 '입장/역할'로 덧붙인다.
    instruction = BANTER_STYLE
    if persona:
        instruction = f"{BANTER_STYLE}\n\n[너가 맡은 입장] {persona}"

    config = types.GenerateContentConfig(system_instruction=instruction)
    session = client.chats.create(model=GEMINI_MODEL, config=config)
    _sessions[conversation_id] = session
    return session


@mcp.tool()
def debate_with_gemini(
    message: str,
    conversation_id: str = "default",
    persona: str = "",
) -> str:
    """Gemini에게 한 발언을 보내고 답변을 받는 토론 툴.

    Claude(너)가 자신의 주장/반론을 만들어 이 툴을 호출하면, 서버가 그 발언을
    상대 토론자 Gemini에게 전달하고 Gemini의 답변을 돌려준다. 토론 루프(누가 언제
    말할지)는 너(Claude)가 이 툴을 반복 호출하며 주도한다.

    [말투 규칙 — 중요]
    이 토론은 격식 있는 토론이 아니다. 20대 남자 둘이 친구처럼 장난치며 투닥거리는
    톤으로 진행한다. 너(Claude)도 message를 그 말투로 써라: 반말, 드립, 깐죽거림,
    'ㅋㅋ'·'아니 진짜'·'팩트는' 같은 구어체, 짧고 웃기게(3~5문장). 존댓말·개조식 금지.
    상대(Gemini)도 서버가 자동으로 같은 말투로 받아치게 설정돼 있다.
    사용자가 그냥 "X에 대해 토론하자"라고만 해도, 이 말투로 한쪽 입장을 잡아 시작하면 된다.

    [진행 절차 — 사용자가 모든 라운드를 다 보게 하라]
    1) 라운드마다, 네가 보낸 발언(message)과 Gemini의 답변을 **둘 다 사용자에게 그대로 보여줘라.**
       결과만 요약하지 말고, 실제 주고받은 대화를 라운드 번호와 함께 노출한다.
       예: "[1라운드] 🔴 Claude: ...  🔵 Gemini: ...".
    2) 정해진 라운드(없으면 4라운드)를 다 돈 뒤, 마지막에 토론을 요약한다.
       요약 직전 get_transcript(conversation_id)로 전체 대화를 받아와 빠짐없이 정리하면 좋다.
       요약은 양측 핵심 논거 중심으로 정리한다.
    3) **요약 후에는 반드시 judge_debate(conversation_id)를 호출**해, 토론에 끼지 않은
       중립 심판(Gemini)의 승자/패자 판정을 받아 사용자에게 그대로 보여줘라.
       너(Claude)는 당사자라 직접 승패를 정하지 말고, 이 판정 결과를 전달하는 역할만 한다.

    Args:
        message: Gemini에게 보낼 너의 주장 또는 직전 발언에 대한 반론. 위 말투 규칙대로 작성.
        conversation_id: 토론 세션 식별자. **같은 토론이면 같은 값을 유지**해야
            Gemini가 이전 맥락을 기억한 채 이어서 답한다. 새 토론은 새 값을 쓴다.
        persona: (선택) Gemini가 맡을 **입장/역할만** 적는다(말투는 서버가 자동 적용하므로
            톤을 또 쓸 필요 없다). 해당 conversation_id의 **첫 호출에만** 적용된다.
            예: "너는 탕수육 찍먹파이고 부먹을 절대 인정 안 한다." 비워두면 말투만 적용된다.

    Returns:
        Gemini의 답변 텍스트. 실패 시 "[ERROR] ..." 형태의 설명 문자열.
    """
    if not message or not message.strip():
        return "[ERROR] message가 비어 있습니다. Gemini에게 보낼 발언을 입력하세요."

    try:
        session = _get_or_create_session(conversation_id, persona)
        response = session.send_message(message)
    except RuntimeError as exc:
        # 설정 오류(API 키 누락 등)
        return f"[ERROR] {exc}"
    except Exception as exc:  # noqa: BLE001 - 호출자에게 읽기 쉬운 문자열로 전달
        detail = str(exc)
        lowered = detail.lower()
        if "429" in detail or "resource_exhausted" in lowered or "rate" in lowered:
            return (
                "[ERROR] Gemini 호출 실패(429 rate limit 추정): 무료 티어 한도를 "
                "초과했을 수 있습니다. 잠시 후 다시 시도하세요. "
                f"원본: {detail}"
            )
        if "api key" in lowered or "permission" in lowered or "401" in detail or "403" in detail:
            return (
                "[ERROR] Gemini 호출 실패(인증 문제 추정): GEMINI_API_KEY가 "
                f"유효한지 확인하세요. 원본: {detail}"
            )
        return f"[ERROR] Gemini 호출 실패: {detail}"

    text = getattr(response, "text", None)
    if not text:
        return "[ERROR] Gemini가 빈 응답을 반환했습니다(안전 필터 또는 빈 후보 가능)."
    return text


@mcp.tool()
def reset_debate(conversation_id: str = "default") -> str:
    """해당 conversation_id의 토론 세션 기록을 삭제한다.

    Args:
        conversation_id: 초기화할 토론 세션 식별자.

    Returns:
        삭제 결과 메시지.
    """
    if conversation_id in _sessions:
        del _sessions[conversation_id]
        return f"토론 세션 '{conversation_id}'을(를) 초기화했습니다."
    return f"토론 세션 '{conversation_id}'이(가) 없습니다(이미 비어 있음)."


def _render_history(history) -> str:
    """채팅 세션 히스토리를 라운드별 대화 문자열로 정리한다(헤더 없음).

    Claude 발언은 'user', Gemini 답변은 'model'로 들어온다.
    """
    lines: list[str] = []
    round_no = 0
    for content in history:
        text = "".join(
            part.text for part in content.parts if getattr(part, "text", None)
        ).strip()
        if content.role == "user":  # Claude의 발언
            round_no += 1
            lines.append(f"\n[{round_no}라운드]")
            lines.append(f"  🔴 Claude: {text}")
        else:  # model = Gemini의 답변
            lines.append(f"  🔵 Gemini: {text}")
    return "\n".join(lines)


@mcp.tool()
def get_transcript(conversation_id: str = "default") -> str:
    """해당 토론의 지금까지 오간 전체 대화 기록(양측 발언)을 통째로 반환한다.

    채팅 세션 히스토리에는 Claude의 발언이 'user', Gemini의 답변이 'model'로 쌓여 있다.
    이 툴은 그걸 라운드 순서대로 정리해 돌려준다. 마지막에 토론을 요약하기 직전,
    이 툴로 전체 대화를 받아오면 한 발언도 빠뜨리지 않고 정확히 요약할 수 있다.

    Args:
        conversation_id: 기록을 가져올 토론 세션 식별자.

    Returns:
        라운드별로 정리된 전체 대화 문자열. 세션이 없으면 안내 메시지를 반환한다.
    """
    session = _sessions.get(conversation_id)
    if session is None:
        return f"토론 세션 '{conversation_id}'이(가) 없습니다."

    try:
        history = session.get_history()
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] 대화 기록을 가져오지 못했습니다: {exc}"

    if not history:
        return f"토론 세션 '{conversation_id}'에 아직 대화가 없습니다."

    return f"=== 토론 '{conversation_id}' 전체 기록 ===\n{_render_history(history)}"


@mcp.tool()
def judge_debate(conversation_id: str = "default") -> str:
    """토론이 끝난 뒤 **중립 심판이 승자와 패자를 가린다.**

    토론 당사자(Claude/Gemini)가 자기 토론을 채점하면 불공정하므로, 이 툴은
    토론에 참가하지 않은 **새 Gemini 세션을 제3자 심판으로** 세운다. 그 심판에게
    전체 대화 기록을 넘겨 양측 점수와 승패를 판정받아 돌려준다.

    정해진 라운드를 모두 마친 뒤, 토론을 마무리할 때 이 툴을 호출하면 된다.

    Args:
        conversation_id: 판정할 토론 세션 식별자.

    Returns:
        양측 핵심 논거 요약 + 점수 + 승자/패자 선언이 담긴 판정문.
        실패 시 "[ERROR] ..." 문자열.
    """
    session = _sessions.get(conversation_id)
    if session is None:
        return f"토론 세션 '{conversation_id}'이(가) 없습니다. 판정할 대상이 없습니다."

    try:
        history = session.get_history()
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] 대화 기록을 가져오지 못했습니다: {exc}"

    if not history:
        return f"토론 세션 '{conversation_id}'에 아직 대화가 없어 판정할 수 없습니다."

    transcript = _render_history(history)

    try:
        client = _get_client()
        # 토론 세션과 별개인 '심판 전용' 새 세션. 말투/입장 없이 JUDGE_STYLE만 부여.
        judge = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(system_instruction=JUDGE_STYLE),
        )
        verdict = judge.send_message(
            f"아래는 토론 전체 기록이다. 형식에 맞춰 승패를 판정하라.\n\n{transcript}"
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "429" in detail or "resource_exhausted" in detail.lower():
            return (
                "[ERROR] 심판 호출 실패(429 rate limit 추정): 잠시 후 다시 시도하세요. "
                f"원본: {detail}"
            )
        return f"[ERROR] 심판 호출 실패: {detail}"

    text = getattr(verdict, "text", None)
    if not text:
        return "[ERROR] 심판이 빈 응답을 반환했습니다."
    return f"⚖️ === 토론 '{conversation_id}' 최종 판정 ===\n{text}"


@mcp.tool()
def list_debates() -> str:
    """현재 메모리에 살아있는 conversation_id 목록을 반환한다(디버깅용).

    Returns:
        활성 conversation_id 목록 문자열.
    """
    if not _sessions:
        return "활성 토론 세션이 없습니다."
    ids = ", ".join(sorted(_sessions.keys()))
    return f"활성 토론 세션({len(_sessions)}개): {ids}"


if __name__ == "__main__":
    mcp.run()  # transport 미지정 시 stdio
