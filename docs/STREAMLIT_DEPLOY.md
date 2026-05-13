# Streamlit Community Cloud 배포 가이드

> 본 문서는 GitHub private repo(`dailyweekly/fair-energy`)를 Streamlit Community Cloud에 배포하여
> **외부 도메인 + 비밀번호 접근 제한** 환경을 만드는 절차를 정리한다.
> 심사위원·NGO·자문위원 등 제한 인원만 접속 가능한 베타 환경 구축용.

---

## 1. 사전 준비

### 1-1. 필요한 것
- GitHub 계정 (`dailyweekly`) — repo `fair-energy` private 상태
- Streamlit Community Cloud 계정 (https://share.streamlit.io)
- 강한 비밀번호 1개 (외부 접근용)

### 1-2. 비밀번호 생성
```bash
# Python으로 무작위 32자 비밀번호 생성
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

발급된 비밀번호는 안전한 곳에 보관 (1Password·Bitwarden 권장). 잃어버리면 Streamlit Secrets UI에서 재설정.

---

## 2. 배포 절차 (1~5분)

### Step 1 — Streamlit Community Cloud 로그인
1. https://share.streamlit.io 접속
2. GitHub 계정으로 로그인 (`dailyweekly`)
3. **Authorize Streamlit** — Streamlit이 GitHub repo 목록을 읽을 권한 부여

### Step 2 — 새 앱 등록
1. **New app** 클릭
2. Repository: `dailyweekly/fair-energy` 선택
3. Branch: `main`
4. Main file path: `app.py`
5. App URL: 원하는 subdomain 입력 (예: `fair-energy-beta`)
   - 최종 URL: `https://fair-energy-beta.streamlit.app`
6. **Advanced settings** 열기:
   - Python version: `3.11`
   - Secrets: 다음 줄을 그대로 붙여넣기 (Step 4 참조)

### Step 3 — Deploy 클릭
- 처음 배포 시 약 2~3분 소요 (의존성 설치)
- 진행 상황은 우측 로그 패널에서 확인

### Step 4 — Secrets 등록

배포 후 또는 Advanced settings에서 다음을 등록:

```toml
# Streamlit Cloud Settings → Secrets 에 그대로 붙여넣기

app_access_password = "여기에-Step1-2에서-생성한-비밀번호-붙여넣기"

deployment_label = "beta-demo"

# (선택) Fernet 키 — 본 환경에서 데이터를 영속 저장하지 않으므로 신경 안 써도 됨
# app_secret_key = "..."

# (선택) Anthropic API 키 — OCR 활성화 시
# anthropic_api_key = "sk-ant-..."
```

> Streamlit Community Cloud는 데이터 영속성이 제한적입니다. 베타 사용자 본격 모집은 별도 서버 권장 (DEPLOYMENT.md 참조).
> 본 환경은 **시연·자문위원 접근**용으로만 사용하세요.

### Step 5 — 접속 확인
1. 배포된 URL 접속 (예: `https://fair-energy-beta.streamlit.app`)
2. 🔒 비밀번호 입력 화면이 보여야 함
3. 비밀번호 입력 후 시작하기 페이지가 나오면 성공

---

## 3. 비밀번호 공유

### 권장 방식
- 자문위원·심사위원·NGO 케이스워커별로 **별도 메신저 채널**에서 1:1로 전달
- 비밀번호를 GitHub·이메일 본문에 직접 적지 않음 (메타데이터로 남을 수 있음)
- 1Password Share·Bitwarden Send 등 만료 가능한 링크 권장

### 회수가 필요한 경우
1. Streamlit Cloud Settings → Secrets 에서 새 비밀번호로 교체
2. 잠시 후 자동 재배포
3. 새 비밀번호를 활성 사용자에게 재공유

### 단일 비밀번호의 한계
- 누가 접속했는지 식별 불가능
- 비밀번호가 유출되면 전체 회수 필요
- 향후 베타 본격 단계에서는 **역할별 코드** 또는 **OAuth**로 전환 권장

---

## 4. 운영 중 점검

### 매주
- Streamlit Cloud Settings → **Manage app** → Logs 에서 에러 확인
- audit_logs 테이블에 비정상 접근 시도 없는지 (KPI 대시보드 페이지에서 확인)

### 비밀번호 회전
- 1~2개월에 1회 권장
- Streamlit Cloud Secrets UI에서만 변경 (코드 수정 불필요)
- 변경 즉시 기존 세션은 모두 무효화 (사용자 재로그인 필요)

---

## 5. 보안 한계 (LIMITATION)

### 본 인증 게이트가 보호하는 것
- 일반 인터넷 사용자의 무작위 접근 차단
- 검색엔진 색인 차단 (자동 차단되며 robots.txt 추가 권장)
- 비밀번호 부여 받지 않은 사용자 접근 차단

### 본 인증 게이트가 보호하지 않는 것
- **비밀번호를 알면 누구든 접근 가능** — 신원 확인 X
- **세션 만료 미구현** — 브라우저 닫기 전까지 인증 유지
- **brute force rate limit 미구현** — 무한 시도 가능 (PoC 단계 수용)
- **로그아웃 기능 미구현** — 브라우저 세션 초기화로 수동 로그아웃
- **Streamlit Community Cloud의 컨테이너 정책** — Streamlit·Snowflake가 정책상 운영자.
  - 코드는 GitHub repo 내용만, secrets는 Streamlit Cloud UI에만 저장됨.
  - 진짜 민감 운영 데이터는 **본 환경에 올리지 말 것**.

### 베타 본격 단계 (사용자 모집 100명)에서 추가로 필요한 것
- 자체 서버 (Render·VPS) + KMS 기반 secrets
- 역할별 코드 + audit 식별
- 세션 만료 + brute force rate limit
- 정책 04 §10 audit_log 운영 매뉴얼 적용

---

## 6. robots.txt 추가 권장 (선택)

검색엔진이 비밀번호 페이지를 색인하지 않도록 차단.

**옵션 1 (권장)**: Streamlit Community Cloud는 자동으로 `User-agent: *` `Disallow: /` 제공.
별도 작업 불필요.

**옵션 2**: `static/robots.txt` 추가 + Streamlit이 정적 파일로 제공하도록 설정.
PoC 단계에서는 옵션 1로 충분.

---

## 7. 트러블슈팅

### "ModuleNotFoundError: No module named 'core'" 에러
- `Main file path`가 `app.py`로 정확히 지정되었는지 확인
- requirements.txt 에 빠진 패키지 없는지 확인

### 비밀번호 입력 화면이 안 보임
- Secrets 에 `app_access_password` 값이 비어 있을 가능성
- Streamlit Cloud Settings → Secrets 확인
- 값이 채워졌으면 Manage app → Reboot

### 비밀번호 입력 후 다시 비밀번호 화면이 보임
- 브라우저가 쿠키 차단 모드일 가능성
- 시크릿 모드에서 다시 시도

### 한국어가 ▢ ▢ ▢ 로 깨짐
- Streamlit Community Cloud 컨테이너에 한국어 폰트 누락
- `requirements.txt`에 폰트 패키지 추가 또는 PDF 한정 이슈
- UI 한국어는 정상 (브라우저 폰트 사용)

### PDF 다운로드 한국어 깨짐
- `core/summary_pack.py`는 시스템 한국어 폰트 탐지 후 폴백 처리
- Streamlit Cloud 컨테이너에는 `fonts-nanum` 패키지가 보통 포함되어 있음
- 없으면 `packages.txt` (apt-get 패키지 목록) 추가 — 본 repo의 `.streamlit/packages.txt` 참조

---

## 8. 빠른 명령 모음

```bash
# 로컬에서 secrets 테스트
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml 편집 (vim 또는 메모장)
streamlit run app.py
# 브라우저에서 비밀번호 화면 확인

# Streamlit Cloud 재배포 강제 (코드 push 후 자동이지만 수동 트리거)
# → Streamlit Cloud Settings → Reboot app

# 로컬 인증 우회 (개발 시)
unset APP_ACCESS_PASSWORD  # .env 임시 비활성
streamlit run app.py
```
