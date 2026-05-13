# 공정에너지 (Fair Energy) — Energy Bill Passport MVP

> SK이노베이션 AI 임팩트 솔루션 공모전 Track A 출품작.
> 임차인이 자신의 에너지 청구 자료가 검산 가능한 상태인지 확인하고,
> 공식 요금 산식과 비교 가능한 경우에만 계산 근거를 제공하는 인프라.

## 본 서비스가 하지 않는 것

- 법률 자문, 법률 의견, 환급 가능성 판단
- 소장·내용증명·민원 본문 작성
- 임대인의 위법성 단정
- 자동 발송

자세한 내용은 [docs/policies/00_service_scope_policy.md](docs/policies/00_service_scope_policy.md)를 참조하세요.

## 폴더 구조

```
fair_energy/
├── docs/policies/         # 6개 정책 지침 (개발의 출발점)
├── core/                  # 핵심 비즈니스 로직
├── pages/                 # Streamlit 페이지 (Phase 2 이후)
├── data/                  # tariff YAML, procedure docs
├── tests/                 # pytest
├── scripts/               # 데모 데이터, KPI export
├── CLAUDE.md              # Claude Code용 중앙 규칙
└── README.md
```

## 개발 단계 (Phase)

현재 단계: **Phase 4 (사용자 확인 화면)** 진입 전

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 프로젝트 스캐폴딩 | 완료 |
| 지침 | docs/policies + guardrails + classification + safety | 완료 |
| 1 | models + config + db + audit_log (SQLite 8테이블) | 완료 |
| 2 | masking + storage + consent + app.py + pages 1·2·3 | 완료 |
| 3 | prompts + llm_client + extraction_schema + extraction | 완료 |
| 4 | 추출 결과 repo + 자동 추출 + `pages/4_추출값확인.py` | 완료 |
| 5 | `core/scoring.py` + `pages/5_자료완결성점수.py` (6개 배점) | 완료 |
| 6 | 분류 디스크립터 + `pages/6_검산결과.py` + 정액 override | 완료 |
| 중간점검 | 외부 자문 + 정책 07 신설 + 우선순위 재정렬 (2026-05-13) | 완료 |
| 7a | C1·B1·A5 자문 대기 (KEPCO YAML / 국외이전 / 화우 의견서) | 대기 |
| 7b | tariff_engine + YAML + 계산 결과 (자문 후) | 차단 |
| 8 R1 | VERY_HIGH 안전 등급 + RRN 감지 거부 | 완료 |
| 8 R2 | 수동 입력 모드 (외부 LLM 우회 경로) | 완료 |
| 8 R3 | 시각 마스킹 (보수적 텍스트 요약본 방식) | 완료 |
| 8 R4 | 가드레일 정교화 + 동적 출력 회귀 점검 | 완료 |
| 9 | 자료 확인 메시지 예시 + 자료 요약본 PDF + 정적 안내문 (외부 자문 추정 기반) | 완료 |
| 10 | core/metrics + 이벤트 로깅 + 데모/export 스크립트 + 관리자 대시보드 | 완료 |

테스트: **335 passed**

## 진행 현황 (2026-05-13)

**완료**: 0, 지침 단계, 1, 2, 3, 4, 5, 6, 8 (R1~R4), 9, 10
**자문 대기**: 7a (C1·B1·A5), 7b (자문 후 룰 엔진)

코드 가능 작업은 거의 완료. 잔여는 한전 전기요금 전문가 자문(Phase 7b)과 화우 ESG센터 사전 검토 의견서(Phase 9 표현 재검토용).

**한계 사항**: 정책 07 §8 참조 — Phase 9 표현 범위는 외부 자문 추정 의견 기반. 실제 자문 결과로 보완 필요.

## KPI 데모 실행

```bash
python scripts/create_demo_data.py --users 30 --reset --db demo.db
python scripts/export_metrics.py --db demo.db --out reports/demo.csv
# Streamlit에서 ENABLE_ADMIN=true 설정 후 「10 KPI 대시보드」 페이지 접속
```

## 출시 통제 원칙 (Release Control)

> 개발 속도보다 출시 통제력이 경쟁력이다.

- Phase 코드 완료 ≠ 베타 출시 가능
- 자문 미수령 상태에서 그 자문이 차단하는 Phase는 시작하지 않음
- RAG는 MVP에서 제외 (정적 markdown 정보 카드로 대체)
- 「증거 패키지」 명칭 폐기 → 「에너지 청구 자료 요약본」
- 상세: [docs/policies/07_release_control_policy.md](docs/policies/07_release_control_policy.md)

## 빠른 시작 (Quickstart)

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env

# 3. Fernet 키 발급 후 .env의 APP_SECRET_KEY에 붙여넣기
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. 앱 실행 (브라우저: http://localhost:8501)
streamlit run app.py
```

- API 키 없어도 `DEMO_MODE=true` 상태에서 데모 OCR 폴백으로 동작
- 첫 부팅 시 `fair_energy.db`와 `storage/` 하위 폴더가 자동 생성

### KPI 데모 (관리자 대시보드 미리보기)

```bash
# 1. 데모 사용자 30명 생성
python scripts/create_demo_data.py --users 30 --reset --db demo.db

# 2. KPI를 CSV로 export
python scripts/export_metrics.py --db demo.db --out reports/demo.csv

# 3. 관리자 대시보드 활성화 후 앱 재실행
# .env에 ENABLE_ADMIN=true 추가 후
streamlit run app.py
# → 사이드바의 "10 KPI 대시보드" 페이지 접속
```

### 테스트

```bash
python -m pytest             # 335개 통과 기대
python -m pytest -k masking  # 특정 영역만
```

## 문서 안내

| 문서 | 내용 |
|---|---|
| [docs/policies/](docs/policies/) | 8개 정책 (정체성·표현·계산·요금엔진·개인정보·안전·KPI·출시통제) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 로컬·시연·베타 환경별 배포 절차 |
| [docs/BETA_CHECKLIST.md](docs/BETA_CHECKLIST.md) | 베타 100명 모집 직전 충족해야 할 모든 항목 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 운영자·NGO 케이스워커 매뉴얼 + 인시던트 대응 |
| [CLAUDE.md](CLAUDE.md) | 코드 작성 규칙 (개발자·AI) |

## 실행 (Phase 0 이후)

```bash
pip install -r requirements.txt
cp .env.example .env  # 필요한 키 설정
streamlit run app.py
```

API 키가 없어도 `DEMO_MODE=true` 상태에서 앱이 동작합니다.

## 테스트

```bash
pytest -v
```

다음 테스트는 출시 게이트 G4·G6의 직접 통과 조건입니다.

- `tests/test_guardrails.py` — G4 법률 판단 금지어 필터
- `tests/test_classification.py` — 4분류 게이트
- `tests/test_safety.py` — 사용자 안전 체크

## 라이선스·면책

본 결과는 사용자가 업로드하고 직접 확인한 자료를 바탕으로 한 요금 산식 검토 보조 자료입니다.
임대인의 위법성 여부, 환급 가능성, 분쟁 결과는 판단하지 않습니다.
