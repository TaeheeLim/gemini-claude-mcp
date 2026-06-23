# Claude vs Gemini 토론봇

Claude Code랑 Gemini 둘이 한 주제로 티격태격하게 만드는 MCP 서버다.
Claude가 진행도 하고 직접 한쪽 편도 들고, Gemini는 반대편 맡아서 받아친다.
근데 사실 Gemini는 자기가 토론하는 줄도 모름. 그냥 평범한 API 호출 받는 거라.

MCP 공부하려고 만든 거고, 덤으로 AI 둘 싸우는 거 구경하는 게 목적.

## 돌아가는 구조

대충 이런 흐름이다.

```
Claude Code  ──(툴 호출)──>  이 서버  ──(google API)──>  Gemini
     ^                                                      │
     └──────────────────  답변 받아서 다시 반박  <──────────┘
```

왼쪽(Claude↔서버)만 MCP고, 오른쪽(서버↔Gemini)은 그냥 HTTPS다. 끝.

## 깔기

```powershell
cd 프로젝트경로
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Gemini API 키 하나 필요하다. 무료 티어로 충분하고, `GEMINI_API_KEY` 환경변수에 넣으면 됨.
모델 바꾸고 싶으면 `GEMINI_MODEL`(기본 `gemini-2.5-flash`).

## 일단 잘 되나 확인

Gemini 연결부터:

```powershell
$env:GEMINI_API_KEY="네_키"
venv\Scripts\python.exe test_gemini.py
```

뭐라도 답 오면 된 거다.

서버 자체 확인은:

```powershell
mcp dev debate_server.py
```

웹 UI 뜨면 `debate_with_gemini`에 아무 말이나 넣고 호출해본다.

## Claude Code에 붙이기

`.mcp.json.example` 복사해서 `.mcp.json` 만들고 경로/키 채우면 된다.
venv 쓰면 `command`는 꼭 venv 안 python 절대경로여야 함.

```json
{
  "mcpServers": {
    "ai-debate": {
      "command": "~\\python.exe",
      "args": ["~\\debate_server.py"],
      "env": {
        "GEMINI_API_KEY": "네_키",
        "GEMINI_MODEL": "gemini-2.5-flash"
      }
    }
  }
}
```

프로젝트 열면 Claude Code가 "이 서버 연결할래?" 물어본다. 승인하면 됨.
`/mcp`로 연결됐는지 보면 된다.

## 툴 세 개

- **`debate_with_gemini(message, conversation_id, persona)`** — 메인. Gemini한테 한마디 던지고 반박 받는다.
  - `conversation_id`: 같은 토론이면 같은 값 써야 맥락 이어짐. 바꾸면 처음부터 다시.
  - `persona`: Gemini한테 입장 깔아주는 거. 첫 호출에만 먹힌다. (예: "넌 사형제도 찬성 입장이야")
- **`reset_debate(conversation_id)`** — 그 토론 기록 날림.
- **`list_debates()`** — 지금 살아있는 토론 목록. 디버깅용.

## 어떻게 시키냐면

Claude Code한테 그냥 이렇게 말하면 된다:

> ai-debate 툴로 "사형제도 폐지 vs 존치" 토론하자. Gemini한테 존치 입장 주고 너는 폐지 맡아.
> conversation_id는 "death-penalty"로 고정하고 4라운드 한 다음에 양쪽 논거 요약해줘.

## 돈 안 나가게

- Claude Code는 구독 계정으로. (`ANTHROPIC_API_KEY` 깔려있으면 API로 붙어서 돈 나간다. 없는지 확인)
- Gemini는 무료 티어 키.
- 무한 루프 돌리지 말 것. 라운드 수 정해놓고 하자. 안 그럼 둘이 밤새 싸운다.
