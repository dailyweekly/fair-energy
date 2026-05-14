# 공정에너지 개발 규칙 (Claude Code Master Rules)

본 파일은 공정에너지(Fair Energy) — Energy Bill Passport MVP 프로젝트의 중앙 규칙 파일이다.
모든 LLM·개발자가 이 프로젝트에서 코드를 수정할 때 본 파일을 먼저 읽고 따른다.

상세 정책은 `docs/policies/` 아래 6개 문서에 있다. 본 파일은 그 요약과 코드 작성 시 점검 사항이다.

---

## 1. 서비스 정체성 (Identity)

공정에너지는 법률서비스가 아니다.
공정에너지는 임차인의 에너지 청구 자료가 검산 가능한 상태인지 진단하고,
공식 요금 산식과 비교 가능한 경우에만 계산 근거를 제공하는 **Energy Bill Passport 인프라**다.

상세: `docs/policies/00_service_scope_policy.md`

---

## 2. 1차 MVP 범위 (Scope Lock)

- 대상: 서울·수도권에서 **한전이 아닌 임대인이 전기요금을 분배 청구**하는 임차인(대표 주거 형태: 고시원·다가구·일부 원룸·반지하). 한전 명의 청구서를 본인이 직접 받는 다세대(공동주택)·아파트 거주자는 제외.
- 영역: **전기요금만**
- 채널: Streamlit 웹앱
- 데이터: SQLite
- AI: 멀티모달 LLM은 OCR/필드 추출만
- 계산: Python 룰 엔진만 (LLM 금지)

도시가스·수도·관리비 전체·다국어·카카오톡·마이데이터·B2G 어드민은 후속 단계.

---

## 3. 절대 원칙 (Hard Constraints)

1. AI는 법률평가, 승패판단, 환급 가능성 판단, 소장, 내용증명, 민원 본문 작성을 **절대** 수행하지 않는다.
2. AI는 문서 구조화·필드 추출·자료 완결성 점수·공개 절차 안내 보조만 수행한다.
3. 요금 계산은 LLM이 하지 않는다. `core/tariff_engine.py`의 deterministic rule engine만 수행한다.
4. 필수 필드가 부족하면 계산하지 않고 「근거 요청 필요」 또는 「검산 불가」로 분류한다.
5. 사용자가 확인하지 않은 AI 추출값(`user_confirmed=False`)은 계산에 사용하지 않는다.
6. 「위반」·「불법」·「부당청구」·「환급 가능」·「승소」·「고소」·「신고하세요」·「소장」·「내용증명」 표현은 출력 금지.
7. 모든 결과는 「산식 일치」·「산식 차이」·「근거 부족」·「확인 요망」·「추가 자료 필요」 등 중립 표현으로만.
8. 임대인 개인정보는 표시용 사본에서 반드시 마스킹한다. 제3자 제공 금지.
9. 도시가스·수도·관리비 전체는 MVP 범위 외.
10. 분쟁 단계에서는 화우 ESG센터·공익변호사·법률구조공단으로 직접 연결한다. AI 사건검토 후 변호사 연결 구조 배제.

---

## 4. 출력 표현 규칙

### 금지 표현
위반, 불법, 부당청구, 부당 부과, 사기, 가스라이팅, 환급 가능, 돌려받을 수 있, 받을 수 있습니다, 승소, 고소, 고발, 신고하세요, 소송하세요, 소장, 내용증명, 법적으로 문제, 임대인이 잘못, 임대인이 위법, 로봇 변호사

### 허용 표현
산식 차이, 산식 일치, 근거 부족, 확인 요망, 추가 자료 필요, 검산 불가, 근거 요청 필요, 예비 검산 가능, 공식 산식 비교 가능, 정산 재확인 필요, 정액 관리비 케이스

상세: `docs/policies/01_output_language_policy.md`

---

## 5. 검산 가능성 분류

| 점수 | 분류 | 가능 기능 |
|------|------|-----------|
| 0~39 | `NOT_CALCULABLE` | 체크리스트만 |
| 40~69 | `NEEDS_BASIS_REQUEST` | 빈칸형 메시지 예시 |
| 70~89 | `PRELIMINARY_CALCULATION` | 예비 계산 (오차 강고지) |
| 90~100 + 필수 필드 + user_confirmed | `OFFICIAL_COMPARISON` | 공식 산식 비교 |
| 정액 관리비 | `FIXED_MANAGEMENT_FEE` | 정책 안내만 |

상세: `docs/policies/02_calculation_gate_policy.md`

---

## 6. 코드 작성 시 점검 사항

새 함수/모듈을 작성할 때 다음을 자체 점검한다.

- [ ] 이 코드가 법률 판단을 출력하지 않는가?
- [ ] 이 코드가 사용자가 확인하지 않은 AI 값을 계산에 쓰지 않는가?
- [ ] 사용자에게 노출되는 텍스트가 `core/guardrails.assert_safe_output()`을 통과하는가?
- [ ] 임대인 식별정보가 마스킹 없이 노출되지 않는가?
- [ ] HIGH 위험 안전 신호가 있을 때 분쟁 행동을 권유하지 않는가?
- [ ] tariff 계산이 LLM이 아닌 `core/tariff_engine.py`에서만 수행되는가?

---

## 7. 테스트 원칙

다음 테스트는 항상 통과해야 한다(출시 게이트 G4·G6 직결).

- `tests/test_guardrails.py` — 금지어 필터
- `tests/test_classification.py` — 4분류 + 정액 케이스
- `tests/test_safety.py` — 안전 체크
- `tests/test_masking.py` — 개인정보 마스킹 (Phase 2에서 구현)
- `tests/test_tariff_engine.py` — 합성 100건 (Phase 7에서 구현)

---

## 8. 정책 변경 시

`docs/policies/`의 정책 변경은 단순 코드 수정과 다른 절차를 따른다.

1. 변경 사유와 영향 범위를 PR description에 명시한다.
2. 대응되는 테스트를 함께 변경한다.
3. 변호사법 경계(00_service_scope_policy의 5항)에 영향이 있으면 화우 ESG센터 자문을 추가로 받는다.

---

## 9. 개발 Phase 진행 순서

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 프로젝트 스캐폴딩, requirements, README | 완료 |
| 지침 단계 | docs/policies + core/guardrails + core/classification + core/safety | 완료 |
| 1 | core/models + core/config + core/db (SQLite) + core/audit_log | 완료 |
| 2 | core/masking + core/storage + core/consent + app.py + pages 1·2·3 | 완료 |
| 3 | core/prompts + core/llm_client + core/extraction_schema + core/extraction | 완료 |
| 4 | 추출 결과 repo + pages/4_추출값확인.py (auto_extract + confirm) | 완료 |
| 5 | core/scoring.py + pages/5_자료완결성점수.py (6개 배점 + 분류 표시) | 완료 |
| 6 | classification 디스크립터 + pages/6_검산결과.py + 정액 override | 완료 |
| 중간점검 | 외부 자문(2026-05-13) + 정책 07 신설 + 우선순위 재정렬 | 완료 |
| 7a | C1·B1·A5 자문 대기 (KEPCO YAML / 국외이전 / 화우 의견서) | 대기 |
| 7b | core/tariff_engine.py + tariff YAML + 룰 엔진 계산 (자문 후) | 차단 |
| 8 Round 1 | VERY_HIGH 안전 등급 + RRN 감지 거부 (정책 04·05 보강) | 완료 |
| 8 Round 2 | 수동 입력 모드 (외부 LLM 우회 경로, pages/3b_수동입력.py) | 완료 |
| 8 Round 3 | 시각 마스킹 (텍스트 요약본 재생성 방식, D8 해소) | 완료 |
| 8 Round 4 | 부정 문맥 가드레일(relaxed) + 동적 출력 회귀 점검 | 완료 |
| Phase 8 전체 | 시각 마스킹 + 안전 강화 + 우회 경로 + 가드레일 통합 | 완료 |
| 9 | 자료 확인 메시지 예시 + 자료 요약본 PDF + 정적 안내문 | 완료 (G5 자문 후 표현 재조정 가능) |
| 10 | core/metrics + 페이지 이벤트 연결 + 데모 데이터·KPI export 스크립트 + 관리자 대시보드 | 완료 |
| 9 | 자료요청 메시지 예시 + 자료 요약본 PDF (G5 통과 + Round 3 후) | 차단 |
| 10 | KPI metrics + 데모 데이터 + NGO 자문 결과 반영 | 마지막 |
| 4 | 사용자 확인 화면 |  |
| 5 | Energy Bill Completeness Score |  |
| 6 | 4분류 UI |  |
| 7 | tariff_engine + YAML |  |
| 8 | 전체 가드레일 적용 |  |
| 9 | 메시지 예시 + 자료 요약본 PDF |  |
| 10 | KPI metrics + 데모 데이터 |  |

각 Phase는 pytest 통과 후 다음으로 넘어간다.

## 10. 현재 DB 스키마 (Phase 1·2 적용)

8개 테이블: `users`, `consents`, `documents`, `extracted_fields`, `passport_scores`,
`calculation_results`, `audit_logs`, `events`.

- 원본 경로(`documents.original_path`)와 마스킹 경로(`documents.masked_path`)는 컬럼 분리.
- `documents.original_path`는 만료 파기 후 NULL로 비워지며 `documents.purged_at`에 시각 기록.
- `extracted_fields.user_confirmed` 기본값 0 — 사용자가 확인하기 전 계산에 사용 금지(정책 02 §5).
- `consents.consent_storage_months`는 6/12/36만 허용(CHECK + Python 양쪽).
- `audit_logs.object_type='original'`은 `consent_basis` 없이는 기록 불가(`audit_log.log_audit` 보호).

## 11. Storage 키 관리 (Phase 2)

- 환경변수 `APP_SECRET_KEY`에 Fernet 키를 둔다 (`Fernet.generate_key()`로 발급).
- `DEMO_MODE=true`에서는 키가 없으면 1회용 키가 생성되지만, 다시 복호화할 수 없으므로
  실 데이터에는 절대 사용하지 않는다.
- 잘못된 키로 복호화 시도 시 `StorageKeyError`를 발생시킨다.

## 12. LLM 추출 파이프라인 (Phase 3)

- 시스템 프롬프트(`core/prompts.OCR_SYSTEM_PROMPT`)는 정책 01 §5의 5개 필수 문구를 반드시 포함.
  변경 시 `tests/test_prompts.py`가 회귀 차단한다.
- LLM 출력 검증은 `core/extraction_schema.parse_llm_output()` 단일 진입점.
  코드펜스 제거 → JSON 파싱 → Pydantic 검증 → summary/warnings 가드레일 스캔 순서.
- `core/llm_client.get_llm_client(config)`는 `DEMO_MODE=true` 또는 키 부재 시 자동으로 `DemoLLMClient` 폴백.
  실 API 호출(`AnthropicLLMClient`)은 키가 있을 때만 활성화.
- `core/extraction.extract_document()`가 추출하면 모든 필드는 `user_confirmed=False`.
  confidence < 0.7 필드는 `needs_user_confirmation=True`로 강제(정책 02 §5와 일관).

## 13. 추출 결과 확인 파이프라인 (Phase 4)

- `core/extraction.find_documents_pending_extraction()`은 추출되지 않은 문서만 반환.
  파기된 문서(`original_path IS NULL`)는 제외 → 만료 후 재추출 방지.
- `auto_extract_pending()`은 idempotent하다 — 같은 사용자에 두 번 호출해도 두 번째는 0건 처리.
- 값 수정(`update_field_value`)만으로는 `user_confirmed`가 자동 True로 바뀌지 않는다.
  사용자가 「확인」 체크박스를 명시적으로 누른 경우에만 `confirm_field()`가 호출되어 1로 전이.
- `confirmation_status()`는 다음 Phase의 자료 완결성 점수 계산 게이트에서 사용된다.

## 14. 자료 완결성 점수 (Phase 5)

- 배점은 `core/scoring.SCORE_WEIGHTS` 단일 출처. 합이 100임을 import 타임 assert로 회귀 차단.
- 「계량기 사진·검침일 보유」는 METER_PHOTO 업로드만으로는 0점.
  사용자가 `photo_date` 또는 `meter_reading`을 확인해야 +15점 부여.
- 「세대별 배분 산식 보유」는 어떤 문서에든 `allocation_method`/`allocation_formula`/`household_count` 키의
  confirmed 필드가 있어야 +20점. `미기재`·`없음`·`""` 등은 의미 없음 처리.
- `build_tariff_input()`은 confirmed 필드만 사용해 `TariffInput`을 만든다. 모든 필수 키가
  confirmed면 `user_confirmed=True`로 전이되어 `classify_case`의 OFFICIAL 게이트가 열림.
- `detect_fixed_fee()`는 LEASE_CONTRACT의 `electricity_separate=='포함'`(confirmed)만 신호로 사용.
  미확인 상태에서는 절대 정액 케이스로 분류하지 않음(보수적 처리).

## 15. 분류 UI와 디스크립터 (Phase 6)

- 5종 분류별 디스크립터(`core/classification.CASE_DESCRIPTORS`)는 사용자 노출 문구의 단일 출처.
  변경 시 `tests/test_classification.py`의 가드레일 회귀가 즉시 차단한다.
- 「환급 가능성」「안내받을 수 있습니다」 같은 부정 문맥 표현도 가드레일을 통과하지 못한다 —
  부정 문맥이라도 패턴 자체를 사용하지 않는 것이 원칙.
- 정액 관리비 케이스는 자동 감지가 기본이지만, Phase 6 페이지에서 사용자가 명시적으로 override 가능.
  override는 `st.session_state["fixed_fee_override"]`에 보관(None=자동, True=정액, False=비정액).
- `reasons_blocking_official()`은 OFFICIAL 게이트를 막는 모든 사유를 한국어로 반환한다.
  UI는 이 목록을 그대로 사용자에게 노출해 "무엇을 더 해야 하는지" 안내한다.

## 16. 출시 통제 우선 원칙 (2026-05-13 외부 자문 반영)

- **개발 속도보다 출시 통제력이 경쟁력이다.** Phase 7~10 코드 완료 ≠ 베타 출시 가능.
- 자문 미수령 상태에서 그 자문이 차단하는 Phase는 **시작하지 않는다.**
  - Phase 7b(룰 엔진 구현) ← C1·C4 자문 후 시작
  - Phase 9(메시지 예시·요약본 PDF) ← G5(화우 의견서) + Phase 8 Round 3 redaction 후 시작
- **명명 규약**: 「증거 패키지」 표현 절대 사용 금지. **「에너지 청구 자료 요약본」** 표기. 가드레일 패턴으로도 차단.
- **RAG 제외**: G1·G2 게이트는 RAG 미사용으로 N/A. 기관 절차 안내는 정적 markdown 정보 카드(`data/procedures/`)로 제공.
- **신규 금지어 6종** (2026-05-13 추가): 과다 청구, 반환 요구, 법적 조치, 보상 가능, 부당 이득, 증거 패키지.
- 상세는 `docs/policies/07_release_control_policy.md`.

## 17. 안전 등급 4단계 (Phase 8 Round 1)

- SafetyLevel: **LOW / MEDIUM / HIGH / VERY_HIGH** (2026-05-13 신설).
- **HIGH**: 메시지 본문 표시되되 「복사」 버튼 비활성 — `should_block_message_copy()=True`.
- **VERY_HIGH**: 메시지 본문 자체 숨김 — `should_hide_message_template()=True`. 주거상담기관·여성긴급전화·법률구조공단 우선 노출.
- VERY_HIGH 트리거: 폭언/협박(3번) + 4·5·6번 중 1개 이상, 또는 4개 이상 yes.
- 기존 `should_block_message_template` 함수는 `should_block_message_copy`의 별칭으로 유지(하위 호환).

## 18. 주민등록번호 처리 (Phase 8 Round 1)

- 텍스트 추출 가능한 파일(.txt·.md·.csv): `storage.save_document(scan_text_for_rrn=True)`가 사전 스캔.
  RRN 감지 시 `RRNDetectedError` 발생, 사용자에게 "가린 후 재업로드" 안내.
- 이미지·PDF: OCR 단계의 `pii_detected[type='resident_registration_number']`로 후속 감지.
- 정책 04 §9 — **마스킹 후 보관보다 업로드 거부가 PoC 단계 안전 기본값**.

## 19. 수동 입력 모드 (Phase 8 Round 2)

- `pages/3b_수동입력.py` — 외부 LLM API에 원본을 송신하지 않는 경로.
- `extraction.create_manual_document()` — `original_path=NULL` 문서 생성 + 모든 필드 `user_confirmed=True`·`confidence=1.0`.
- AI OCR 처리 동의를 하지 않은 사용자도 자료 완결성 점수·예비 검산까지 도달 가능.
- 정책 04 §3 「AI 외부 API 처리 동의 미동의 시 수동 입력 모드 이용 가능」을 코드로 충족.

## 20. 시각 마스킹 — 보수적 텍스트 요약본 방식 (Phase 8 Round 3)

- 원본 이미지·PDF의 픽셀 단위 redact를 시도하지 않는다.
  대신 사용자 확인된 필드만으로 **Markdown 텍스트 요약본**을 재생성한다.
- 구현: `core/redaction.py`의 `build_text_summary()`·`regenerate_masked_view()`·`regenerate_all_masked_views()`.
- 마스킹본은 `storage/masked/{user_id}/{document_id}.md`.
- 포함되지 않는 정보: `source_text`(원문 인용), 원본 이미지, 임대인 식별정보.
- 수동 입력 문서(`original_path IS NULL`)는 마스킹본을 생성하지 않는다(원본이 없음).
- Phase 5 페이지에 「마스킹본 재생성」버튼 제공.
- Phase 9 자료 요약본 PDF는 본 Markdown을 PyMuPDF로 렌더링하는 것이 후속 계획.
- 보조 유틸 `heavy_blur_image()` — 가우시안 블러 폴백(MVP 미사용, Phase 9 이후 특수 케이스).

## 21. 가드레일 정교화 (Phase 8 Round 4)

- **엄격 모드** `is_safe_output()`·`assert_safe_output()` — 동적 LLM/사용자 출력에 사용.
- **완화 모드** `is_safe_output_relaxed()`·`assert_safe_output_relaxed()` — 정적 면책 문구·정책 인용에 사용.
  - `STATIC_SAFE_DISCLAIMER_PHRASES` 화이트리스트로 부정 문맥의 안전 표현을 어휘 일치로 허용.
  - 화이트리스트 phrase는 **그 자체가 엄격 모드에서 차단되어야** 함(우회 방지).
- **면제 대상**: OCR 시스템 프롬프트는 LLM 입력이므로 가드레일 검증 대상이 아님(정책 01 §6.3).
- **회귀 차단**: 분류 디스크립터·점수 액션·마스킹본·면책 문구·`SAFE_LABELS` 모두 자동 회귀 테스트로 차단.

## 22-PRE. 메시지 예시 + 자료 요약본 (Phase 9)

- `core/message_templates.py` — 4종 템플릿(기본 자료 확인 / 배분 산식 / 검침일 / 정산 재확인) + 자동 채움 2종(`address`, `billing_period`) + 편집 후 가드레일 검증(`validate_edited_message`).
- `pages/7_자료확인메시지예시.py` — 4단계 안전 차단(LOW/MEDIUM/HIGH/VERY_HIGH) + 분류별 적용 가능 템플릿만 표시 + 복사 박스.
- `core/summary_pack.py` — PyMuPDF로 자료 요약본 PDF 생성. 시스템 한국어 폰트(`malgun.ttf` 등) 자동 탐지. source_text는 절대 포함되지 않음.
- `pages/8_자료요약본.py` — PDF 생성·다운로드 + 마스킹본 사전 재생성.
- `data/procedures/*.md` — 정적 안내문 3종(KEPCO·임대차분쟁조정위·법률구조공단). RAG 미사용.
- 안전 함수 추가: `requires_two_step_confirmation()` (HIGH 등급용).

**한계 사항**: 본 Phase는 외부 자문 의견(2026-05-13) **추정 의견 기반**. 화우 ESG센터의 실제 사전 검토 의견서(G5) 수령 후 표현이 조정될 수 있다. 상세는 `docs/policies/07_release_control_policy.md` §8.

## 22. KPI 메트릭 인프라 (Phase 10)

- `core/metrics.py` — 표준 이벤트 17종 상수 + `log_event()` 단일 진입점 + 7개 KPI 계산 함수 + `compute_full_report()`.
- 이벤트 로깅 연결 위치(현재):
  - `pages/1_시작하기.py` → `user_registered`
  - `pages/2_동의_및_안전체크.py` → `consent_completed`, `safety_check_completed`
  - `pages/3_문서업로드.py` → `document_uploaded`, `document_rejected_rrn`
  - `pages/3b_수동입력.py` → `manual_input_used`
  - `pages/5_자료완결성점수.py` → `passport_created`(첫 점수), `score_calculated`, `case_classified`
  - Phase 9 페이지 추가 시 `request_template_viewed`·`request_template_copied` 등 연결 예정.
- **KPI 계층** (정책 06 §2-A):
  - 1차: 자료 완결성 점수 개선률 (사용자 본인이 통제 가능한 행동 신호)
  - 2차: 메시지 복사율 (근거 요청 필요 케이스 중)
  - 3차: 재업로드율 (30일 윈도우, 24시간 이상 간격 카운트)
  - 보조: Bill Passport 개설률, 수동 입력 사용률, HIGH/VERY_HIGH 차단 횟수, 분류 분포
- **스크립트**:
  - `scripts/create_demo_data.py --users N --reset` — 정책 06 §6 기대 분포 기반 데모 데이터 생성.
  - `scripts/export_metrics.py --out path.csv` — KPI를 CSV·JSON으로 export.
- **대시보드**: `pages/10_KPI_대시보드.py` — `ENABLE_ADMIN=true`일 때만 노출. 익명·집계 통계만.
