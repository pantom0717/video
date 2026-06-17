# Kiwi AI Short-Form Backend

랜딩페이지 신청을 받아 AI 제품 홍보 숏폼 제작 작업으로 넘기는 FastAPI 백엔드입니다.

현재 구조는 안전한 반자동 MVP입니다. 랜딩 폼 접수, 제작 브리프 생성, 레퍼런스 영상 업로드, Gemini 분석, 시작 프레임 캡처, Higgsfield 프롬프트 패키지 생성, 음성 파일 생성까지 동작합니다. Higgsfield 실제 생성은 `run_higgsfield_generation=true`일 때만 실행됩니다.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Docs:

```text
http://127.0.0.1:8000/docs
```

## Landing Flow

프론트엔드 `https://landing-eight-black-83.vercel.app/`의 신청 폼은 이 API로 보내면 됩니다.

```http
POST /leads
Content-Type: application/json
```

```json
{
  "brand_name": "브랜드명",
  "instagram_url": "https://instagram.com/brand",
  "reference_url": "https://www.tiktok.com/@creator/video/123",
  "email": "owner@example.com",
  "product_name": "제품명",
  "target_customer": "타깃 고객",
  "main_benefit": "핵심 소구점"
}
```

응답의 `lead_id`로 상태를 조회합니다.

```http
GET /leads/{lead_id}
GET /leads
```

레퍼런스 영상 파일이 확보되면 리드에 붙여 제작 파이프라인을 실행합니다.

```http
POST /leads/{lead_id}/reference-video
multipart/form-data
  reference_video: file
  start_second: 0.5
  run_higgsfield_generation: false
```

## Production Pipeline

```text
랜딩 폼 제출
→ /leads 접수
→ intake_package.json / production_brief.txt 생성
→ 레퍼런스 영상 업로드
→ Gemini 분석 또는 fallback 분석
→ 시작 프레임 캡처
→ Higgsfield 이미지/영상 프롬프트 생성
→ 선택 시 Higgsfield SDK 실제 생성
→ voiceover.wav 생성
→ CapCut/렌더링용 편집안 생성
```

## Higgsfield Subscription Mode

Higgsfield Cloud API credentials가 있으면 `.env`를 설정합니다.

```dotenv
HIGGSFIELD_PROVIDER=sdk
HF_KEY=your-api-key:your-api-secret
```

또는:

```dotenv
HIGGSFIELD_PROVIDER=sdk
HF_API_KEY=your-api-key
HF_API_SECRET=your-api-secret
```

실제 크레딧을 쓰려면 요청에서 반드시:

```text
run_higgsfield_generation=true
```

를 보내야 합니다.

## Environment

```dotenv
APP_MODE=free
DATA_DIR=data
CORS_ORIGINS=https://landing-eight-black-83.vercel.app,http://localhost:3000,http://127.0.0.1:3000
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
HIGGSFIELD_PROVIDER=manual
HIGGSFIELD_RUN_BY_DEFAULT=false
HIGGSFIELD_IMAGE_MODEL=bytedance/seedream/v4/text-to-image
HIGGSFIELD_VIDEO_MODEL=bytedance/seedance/v1/image-to-video
HIGGSFIELD_IMAGE_COUNT=4
```

## Notes

- 링크만으로 TikTok/Instagram 영상을 자동 다운로드하는 모듈은 아직 넣지 않았습니다. 플랫폼 정책과 안정성 이슈가 있어서, 현재는 레퍼런스 영상 파일 업로드로 제작을 시작합니다.
- CapCut 공식 서버 렌더링 API가 확실하지 않으므로 현재는 편집안과 에셋을 만들고, 추후 자체 `ffmpeg`/Remotion 렌더러를 붙이는 구조가 가장 안정적입니다.
- 입모양 싱크와 엔드 프레임은 기본 제외입니다.
