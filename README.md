# Kiwi AI Short-Form Backend

랜딩 신청을 받아 **AI 제품 홍보 숏폼 제작**으로 넘기는 FastAPI 백엔드.
`beauty-fast-gen-cli` 스킬의 워크플로(분석→프레임→이미지→픽→i2v→나레이션→조립)를
**컷별 플랜 + 휴먼 게이트 API** 로 옮긴 버전이다.

> **현재 운영 상태(MVP):** 실제로 켜두고 쓰는 건 **폼 접수(`POST /leads`) + 운영자 메일 알림**뿐.
> 영상 제작은 당분간 사람이 수동으로 한다. 나머지 제작 엔드포인트는 **나중 연동용으로 완성만 해둔 상태**다.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # 키는 비워둬도 됨(전부 fallback)
uvicorn app.main:app --reload --port 8000
```

Docs: `http://127.0.0.1:8000/docs`

> 키가 하나도 없어도 죽지 않는다. Gemini 없으면 **fallback 플랜**, Higgsfield는 **요청 패키지만**,
> ElevenLabs 없으면 **경고만**, 메일은 **콘솔 로그만** 으로 떨어진다.

## MVP: 폼 → 운영자 메일

프론트 신청 폼이 이 API로 들어온다.

```http
POST /leads
Content-Type: application/json
{ "brand_name": "...", "instagram_url": "...", "email": "...", "reference_url": "(선택)" }
```

리드가 저장되면 **운영자(우리) 메일로 알림**이 간다. `EMAIL_PROVIDER` 로 무료 경로 선택:

| provider | 설명 | 필요 설정 |
| --- | --- | --- |
| `console` (기본) | 발송 안 하고 로그만 | 없음 |
| `smtp` | Gmail 앱 비밀번호 등 (무료) | `NOTIFY_EMAIL`, `SMTP_USER`, `SMTP_PASSWORD` |
| `resend` | Resend API (무료 티어) | `NOTIFY_EMAIL`, `RESEND_API_KEY` |

> 메일 발송 실패는 **리드 저장을 막지 않는다**(경고만 남김). 수신 주소는 `.env` 의 `NOTIFY_EMAIL`.
> `GET /leads`, `GET /leads/{lead_id}` 로 접수 내역 조회.

## 제작 파이프라인 (나중 연동용 — 이미 동작)

```text
POST /jobs (레퍼런스 업로드)
→ Gemini 분석 → 컷별 ProductionPlan (일관성 A/B 제안 + 컷별 image/i2v 프롬프트)
→ §2 컷별 프레임 자동 추출(frames/)
→ §3 이미지 생성 (manual/mcp=패키지만, sdk=실제)
─ 휴먼 게이트 ─
POST /jobs/{id}/consistency   (A | B | mixed 확정 — §1.5)
POST /jobs/{id}/pick          (컷별 베스트 추천, 사람 거부권 — §3.6)
POST /jobs/{id}/propose-i2v   (i2v A/B 제안표 — §5.0)
POST /jobs/{id}/generate-video (확정 A/B로 i2v — §5)
POST /jobs/{id}/narration     (컷별 KO 스크립트 + captions.srt — §7.5)
POST /jobs/{id}/tts           (승인 후 ElevenLabs 음성)
GET  /jobs/{id}               (plan + 산출물 목록)
GET  /jobs/{id}/files/{name}  (plan.json, proposals.json, captions.srt ...)
```

리드에서 바로 시작하려면 `POST /leads/{lead_id}/reference-video` (레퍼런스 파일 업로드).

## Higgsfield provider (연동 지점)

`.env` 의 `HIGGSFIELD_PROVIDER`:

- `manual` (기본): 컷별 이미지/i2v **요청 패키지(JSON)** 만 만들고 사람이 직접 생성.
- `mcp`: beauty-fast-gen **MCP 경로로 위임**하는 핸드오프 패키지를 만든다 → **실제 MCP 호출만 붙이면 됨(드롭인)**.
- `sdk`: `higgsfield-client` 로 백엔드가 직접 생성(크레딧 사용). `HF_KEY` 또는 `HF_API_KEY`+`HF_API_SECRET` 필요.

스킬 규칙 반영: 이미지 컷당 4장(A형은 앵커 먼저→그 job_id를 나머지 reference로),
i2v 시작 프레임 = 픽 이미지 job_id 재사용, **sound on 고정**(음악/보컬은 프롬프트로 억제),
**엔드프레임·립싱크 미사용**, JSON 프롬프트 X(일반 텍스트).

## Environment

`.env.example` 참고. 핵심만:

```dotenv
GEMINI_API_KEY=                  # 없으면 fallback 플랜
HIGGSFIELD_PROVIDER=manual       # manual | mcp | sdk
ELEVENLABS_API_KEY=              # 나레이션 TTS(선택)
EMAIL_PROVIDER=console           # console | smtp | resend
NOTIFY_EMAIL=                    # 폼 신청이 도착할 우리 메일 (나중에 채움)
```

## Notes

- 링크만으로 TikTok/Instagram 영상을 자동 다운로드하는 모듈은 없음(정책·안정성). 레퍼런스는 파일 업로드.
- CapCut 렌더 API는 불확실 → 현재는 `captions.srt` + 컷별 프롬프트/플랜까지. 조립은 CLI 스킬의 `build_capcut_draft.py` 또는 추후 자체 렌더러.
- 입모양 싱크·엔드 프레임은 기본 제외.
