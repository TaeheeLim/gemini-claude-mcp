# AI Debate MCP Server

## 1. 프로젝트 목적

Claude Code(MCP 클라이언트)가 토론을 주도하고, 상대편 토론자로 **Gemini**를 호출하는
**MCP 서버**를 만든다. 목적은 두 가지다.

1. MCP 서버의 핵심 개념(client/server, tool, stdio transport)을 직접 구현하며 학습한다.
2. Claude ↔ Gemini가 한 주제를 놓고 가볍게 토론하는 모습을 본다.

**이 저장소가 만드는 것은 "Gemini를 MCP 툴로 감싼 어댑터 서버"다.** Gemini 쪽은 MCP를
전혀 모르며, 평범한 HTTPS API 호출일 뿐이다. 토론 루프(누가 언제 말할지)는 Claude Code가
이 서버의 툴을 반복 호출하면서 주도한다.

## 2. 아키텍처 (A안)

```
Claude Code (MCP 클라이언트, 토론 주도자)
      │  ① 툴 호출 (stdio / JSON-RPC, SDK가 처리)
      ▼
이 MCP 서버 (어댑터)
      │  ② google-genai SDK로 Gemini 호출 (HTTPS)
      ▼
Gemini API (무료 티어, 상대 토론자)
```

- Claude Code가 자기 주장을 만들어 `debate_with_gemini` 툴을 호출한다.
- 서버가 그 발언을 Gemini에 전달하고, Gemini의 답변을 툴 반환값으로 돌려준다.
- Claude Code가 그 답변을 읽고 반박을 만들어 다시 툴을 호출한다 → 라운드 반복.

## 3. 기술 스택 / 버전 (반드시 이 조합)

| 항목 | 사용 | 비고 |
|---|---|---|
| 언어 | Python 3.10 이상 | MCP 파이썬 SDK 최소 요구 버전 |
| MCP 서버 SDK | `mcp[cli]` (공식) | `from mcp.server.fastmcp import FastMCP` |
| Gemini SDK | `google-genai` (공식, GA) | `from google import genai` |
| Transport | **stdio** | `mcp.run()` 기본값 |
| Gemini 모델 | 환경변수 `GEMINI_MODEL`, 기본 `gemini-2.5-flash` | 무료 티어 모델 |
| API 키 | 환경변수 `GEMINI_API_KEY` | SDK가 자동 인식 |

## 4. 핵심 설계 결정 (반드시 준수)

1. **공식 SDK만 사용한다.** Gemini는 신형 `google-genai`(`from google import genai`)를
   쓴다. 레거시 `google-generativeai`(`import google.generativeai`)는 **절대 쓰지 말 것.**
   MCP 서버는 raw JSON-RPC를 직접 다루지 말고 `FastMCP` 고수준 API를 쓴다.
2. **stdio transport 단일 구성.** HTTP/SSE 서버, 인증, 외부 노출은 구현하지 않는다.
   로컬 개인용이다.
3. **API 키는 코드/저장소에 하드코딩 금지.** 오직 환경변수에서만 읽는다.
4. **대화는 conversation_id 별로 메모리에 누적한다.** 같은 conversation_id로 호출하면
   Gemini가 이전 맥락을 기억한 채 답하도록 멀티턴 세션을 유지한다.
5. **툴 docstring은 "AI 호출자가 읽는 설명"이다.** Claude Code는 docstring을 보고 툴 사용법을
   판단하므로, 인자 의미와 사용 시점을 명확히 한국어/영어로 기술한다.
6. **Gemini 호출 실패가 서버를 죽이면 안 된다.** 예외는 잡아서 읽기 쉬운 에러 문자열을
   반환한다(특히 인증 실패, 429 rate limit).
7. **단일 파일로 단순하게.** 과한 추상화/클래스 계층 없이 한 파일에 담는다.

## 5. 만들 파일

```
ai-debate-mcp/
├── debate_server.py     # 메인 MCP 서버 (구현 대상)
├── test_gemini.py       # (이미 존재) Gemini 단독 연결 테스트
├── requirements.txt     # mcp[cli], google-genai
├── .mcp.json.example    # Claude Code 등록용 템플릿 (실제 .mcp.json은 gitignore)
├── .gitignore           # venv/, .env, .mcp.json, __pycache__/
└── README.md            # 설치·실행·등록·토론 방법 요약
```

## 6. MCP 툴 명세

### `debate_with_gemini(message, conversation_id="default", persona="") -> str`
- **역할:** Gemini에게 한 발언을 보내고 답변을 받는다.
- **message:** Gemini에게 보낼 Claude의 주장/반론.
- **conversation_id:** 토론 세션 식별자. 같은 토론은 같은 값을 유지해야 맥락이 이어진다.
- **persona:** (선택, 해당 conversation_id의 첫 호출에만 적용) Gemini가 맡을 입장/역할.
  내부적으로 채팅 세션의 system_instruction으로 설정한다.
- **반환:** Gemini의 답변 텍스트. 실패 시 `"[ERROR] ..."` 형태의 설명 문자열.
- **동작:** conversation_id에 해당하는 채팅 세션이 없으면 새로 만들고(persona가 있으면
  system_instruction으로 설정), 있으면 기존 세션에 이어서 보낸다.

### `reset_debate(conversation_id="default") -> str`
- 해당 conversation_id의 세션 기록을 삭제하고 결과 메시지를 반환한다.

### `list_debates() -> str` (선택 구현)
- 현재 메모리에 살아있는 conversation_id 목록을 반환한다(디버깅용).

## 7. SDK 사용 패턴 (참고 — 이 형태를 따를 것)

아래는 공식 문서 기준 정식 사용법이다. 학습 데이터의 옛 패턴 대신 반드시 이 형태를 쓴다.

**Gemini (google-genai) — 멀티턴 채팅 세션:**
```python
from google import genai
from google.genai import types

client = genai.Client()  # GEMINI_API_KEY 환경변수 자동 인식

# 세션 생성 (persona를 system_instruction으로)
chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(system_instruction="당신은 ...의 입장이다."),
)

# 한 턴 전송 → 답변. 세션이 user/model 히스토리를 자동 관리한다.
response = chat.send_message("상대의 주장: ...")
print(response.text)
```
> A안에서는 Gemini가 한쪽(Claude)만 상대하므로, Claude의 발언이 자동으로 `user`,
> Gemini 답변이 `model`로 기록된다. B안처럼 역할을 수동 매핑할 필요가 없다.

**MCP 서버 (FastMCP) — stdio:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-debate")

@mcp.tool()
def debate_with_gemini(message: str, conversation_id: str = "default", persona: str = "") -> str:
    """(여기 docstring이 곧 툴 설명이 된다 — 위 6번 명세 내용을 기술)"""
    ...

if __name__ == "__main__":
    mcp.run()  # transport 미지정 시 stdio
```

## 8. 에러 처리

- `GEMINI_API_KEY` 미설정: 서버 기동 시 또는 첫 호출 시 명확한 메시지로 안내.
- Gemini 호출 예외: `try/except`로 잡아 `"[ERROR] Gemini 호출 실패: {사유}"` 반환.
- 429(rate limit): 무료 티어 한도 초과 가능성을 안내하는 문구를 반환하고, 호출자가
  잠시 후 재시도하도록 유도(서버가 자동 무한 재시도하지 않는다).

## 9. 구현 작업 순서

1. `requirements.txt` 작성 후 의존성 설치 확인.
2. `debate_server.py`에 FastMCP 인스턴스 + 두 툴(`debate_with_gemini`, `reset_debate`) 구현.
3. conversation_id → 채팅 세션 딕셔너리로 멀티턴 상태 관리.
4. 에러 처리 추가.
5. `mcp dev debate_server.py`로 MCP Inspector를 띄워 툴이 노출되고 호출되는지 단독 검증.
6. `.mcp.json.example`, `.gitignore`, `README.md` 작성.

## 10. 단독 테스트 (Claude Code 등록 전)

```
mcp dev debate_server.py
```
- MCP Inspector(웹 UI)가 뜨면 `debate_with_gemini`에 임의의 message를 넣어 호출한다.
- Gemini 답변이 반환되면 서버는 정상. 여기까지 통과한 뒤에 Claude Code에 등록한다.

## 11. Claude Code 등록 (.mcp.json)

프로젝트 루트에 `.mcp.json`을 둔다(아래는 `.mcp.json.example` 내용, Windows 기준).
**venv를 쓰는 경우 `command`는 반드시 venv 안의 python 절대경로**여야 한다
(`venv\Scripts\activate` 후 `where python` 맨 위 경로).

```json
{
  "mcpServers": {
    "ai-debate": {
      "command": "C:\\경로\\ai-debate-mcp\\venv\\Scripts\\python.exe",
      "args": ["C:\\경로\\ai-debate-mcp\\debate_server.py"],
      "env": {
        "GEMINI_API_KEY": "발급받은_키",
        "GEMINI_MODEL": "gemini-2.5-flash"
      }
    }
  }
}
```
- 시스템 환경변수에 `GEMINI_API_KEY`가 이미 설정돼 있으면 `env`에서 생략 가능.
- 등록 후 Claude Code에서 `/mcp`로 연결을, `claude mcp list`로 등록을 확인한다.

## 12. 토론 실행 방법

Claude Code 세션에서 다음과 같이 지시한다(예시):

> `ai-debate`의 `debate_with_gemini` 툴로 "Spring 3.2 레거시 유지 vs 최신 업그레이드"를
> 주제로 Gemini와 토론하자. 첫 호출에 persona로 Gemini에게 "업그레이드 반대 입장"을 주고,
> 너는 찬성 입장을 맡아라. conversation_id는 "spring-debate"로 고정하고, 5라운드 주고받은 뒤
> 양측 핵심 논거를 요약해라.

## 13. 비용 0 유지 조건 (중요)

- **Claude Code는 구독 계정으로 로그인해 사용한다.** 시스템에 `ANTHROPIC_API_KEY`가 설정돼
  있으면 Claude Code가 구독 대신 API로 붙어 토큰당 과금되므로, 이 환경변수가 없는지 확인한다.
- **Gemini는 무료 티어 프로젝트(결제 비활성)**의 키만 사용한다.
- 자동 무한 루프 금지. 토론은 항상 라운드 수를 정해 실행한다.

## 14. 하지 말 것

- 레거시 `google-generativeai` 사용 금지.
- API 키 하드코딩·커밋 금지(`.mcp.json`, `.env`는 gitignore).
- HTTP/SSE transport, 인증, 외부 배포 구현 금지(범위 밖).
- 헤드리스 자동 실행(`claude -p`)으로 토론 루프 무한 가동 금지.

## 15. 코딩 규칙

- 타입 힌트와 명확한 docstring을 단다(툴 docstring은 특히 중요 — 6번 명세 반영).
- 단일 파일, 최소 의존성, 과한 추상화 지양.
- 버전·동작은 공식 문서(MCP Python SDK, google-genai) 기준으로 구현한다.
- 모델명 등 자주 바뀌는 값은 하드코딩하지 말고 환경변수로 받는다.
