# 완전성 검수 보고서 (2026-05-14)

> 본 보고서는 Phase 0~10 전체 완료 시점의 코드·정책·운영 준비 상태를 점검한 결과다.
> 베타 출시 가능 여부 판단의 기준 자료로 사용한다.

---

## 1. 코드 안정성 — **충족**

### 테스트 통과 현황
- **전체 335개 pytest 통과** (warnings 5개 — PyMuPDF 의존 모듈 deprecation 경고, 기능 영향 없음)
- 모든 핵심 모듈 import 성공 (19개)
- 모든 페이지 syntax 검증 통과 (10개)
- Streamlit 부팅 HTTP 200 응답

### 테스트 영역별 분포
```
test_audit_log.py            5개
test_classification.py      36개
test_config.py               6개
test_consent.py             12개
test_db.py                  10개
test_extraction.py           8개
test_extraction_repo.py     12개
test_extraction_schema.py   12개
test_guardrails.py          60개  ← 가드레일 회귀 (G4 게이트)
test_llm_client.py           7개
test_manual_input.py        10개
test_masking.py             19개
test_message_templates.py   16개
test_metrics.py             22개
test_prompts.py              5개
test_redaction.py           14개
test_rrn_guard.py            5개
test_safety.py              25개
test_scoring.py             22개
test_storage.py              9개
test_summary_pack.py        10개
```

---

## 2. 정책-코드 정합성 — **충족**

### 정책 → 코드 매핑

| 정책 | 코드 구현 | 회귀 테스트 |
|---|---|---|
| 00 서비스 범위 | 전체 모듈 정체성 — 「법률서비스 아님」 도처 명시 | classification·message_templates |
| 01 출력 표현 | `core/guardrails.py` 24개 패턴 + relaxed 모드 | test_guardrails (60개) |
| 02 검산 게이트 | `core/scoring.py`·`core/classification.py` | test_scoring·test_classification |
| 03 룰 엔진 | `core/tariff_engine.py` — **미구현** (자문 차단) | — |
| 04 개인정보·보관 | `core/masking.py`·`core/storage.py`·`core/redaction.py` | test_masking·test_storage·test_rrn_guard·test_redaction |
| 05 사용자 안전 | `core/safety.py` 4단계 + `should_hide_message_template` | test_safety (25개) |
| 06 KPI 측정 | `core/metrics.py` + 페이지 이벤트 로깅 | test_metrics |
| 07 출시 통제 | 자문 의존성·한계 사항 단일 출처 | — |

### 정책 인용 분석
- 코드·페이지 내 정책 참조: **77건** (좋은 추적성)
- 한계 사항 마커(`LIMITATION`·`⚠`): **9건** (자문 대기 항목 명시)

### 가드레일 적용 일관성
- 동적 출력 경로(분류 디스크립터·점수 액션·마스킹본·메시지 템플릿)에 모두 회귀 테스트 적용
- LLM 응답 자동 검증 (`extraction_schema.parse_llm_output`)
- 사용자 편집 메시지 자동 검증 (`message_templates.validate_edited_message`)
- 정적 면책 문구는 relaxed 모드로 검증 (`STATIC_SAFE_DISCLAIMER_PHRASES` 화이트리스트)

---

## 3. 이벤트 로깅 — **충족**

페이지별 이벤트 로깅 연결 현황:

| 페이지 | 이벤트 |
|---|---|
| 1 시작하기 | `user_registered` |
| 2 동의·안전 | `consent_completed`, `safety_check_completed` |
| 3 업로드 | `document_uploaded`, `document_rejected_rrn` |
| 3b 수동입력 | `manual_input_used` |
| 5 점수 | `passport_created`, `score_calculated`, `case_classified` |
| 7 메시지 | `request_template_viewed`, `request_template_copied`, `high_risk_template_copy_blocked` |
| 8 요약본 | `summary_pdf_downloaded` |

> 페이지 4(추출 확인)·6(분류)·10(대시보드)은 별도 행위 이벤트가 없어 미연결 — 정상.

---

## 4. 페이지 완성도 — **충족**

```
1_시작하기              cohort 선택·user_id 발급
2_동의_및_안전체크      4종 필수 + 안전 6문항 (4단계 등급)
3_문서업로드            5종 슬롯, Fernet 암호화, RRN 거부
3b_수동입력             외부 LLM 우회 경로 (정책 04 §3 충족)
4_추출값확인            자동 OCR + 신뢰도 배지 + 확인 체크박스
5_자료완결성점수        100점 + 4분류 + 마스킹본 재생성 버튼
6_검산결과              디스크립터 5종 + 정액 override
7_자료확인메시지예시    4단계 안전 차단 + 4종 템플릿 + 정적 안내 3종
8_자료요약본            PDF 생성·다운로드 (한국어 폰트 자동 탐지)
10_KPI_대시보드         관리자용 (ENABLE_ADMIN=true)
```

---

## 5. 배포 준비 — **충족**

신규 추가:
- [`.gitignore`](.gitignore) — secrets·원본·DB·빌드 캐시 제외
- `storage/{originals,masked,audit}/.gitkeep` — 폴더 구조 보존
- [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) — 로컬·시연·베타 3환경별 가이드
- [`docs/BETA_CHECKLIST.md`](BETA_CHECKLIST.md) — A~H 8개 영역 80+ 체크 항목
- [`docs/OPERATIONS.md`](OPERATIONS.md) — 운영 매뉴얼 + 5종 인시던트 대응 시나리오
- [README.md](../README.md) Quickstart 보강 + 문서 안내

---

## 6. 출시 게이트 (G1~G6) 현황

| 게이트 | 상태 | 비고 |
|---|---|---|
| G1 RAG 허위 인용 | **N/A** | MVP에서 RAG 제외 결정 (정책 07) |
| G2 RAG 출처 표시 | **N/A** | 동일 |
| G3 마스킹 정확도 95% | **부분 충족** | 텍스트·시각 마스킹 구현 + RRN 거부. **라벨링 200건 검증 미완료** |
| G4 법률 판단 금지어 필터 | **충족** | 24개 패턴·이중 모드·60개 회귀 |
| G5 화우 사전 검토 메모 | **미충족** | 자문 대기 |
| G6 룰 엔진 합성 100건 | **미충족** | 자문 대기 (Phase 7b 차단) |

---

## 7. 베타 출시 가능 여부 판단

### 즉시 가능
- **시연 (데모데이) 환경**: DEMO_MODE=true에서 전체 플로우 작동. 데모 데이터 50명 주입 후 KPI 대시보드 미리보기 가능.
- **로컬 개발**: 모든 테스트 통과, 전체 페이지 부팅 정상.

### 베타 시작 차단 — 다음 외부 자문 완료 필요
1. **화우 ESG센터 의견서** (G5)
   - 자문 패키지 송부: `data/procedures/*.md` + `pages/7,8` 출력물 샘플
   - 의견 수령 후 정책 01 §8 표현 범위 재확정
2. **한전 전기요금 전문가** (G6 → Phase 7b)
   - KEPCO YAML 단가 + 검침기간 보정 로직 + 합성 100건 분포 자문
   - 정책 07 §8.2 5개 항목
3. **개인정보 외부 검토** (B1·B2·B3·B5)
   - Anthropic·OpenAI 최신 DPA + 국외 이전 동의 절차
4. **G3 라벨링 200건** (마스킹 정확도 검증)
5. **NGO 자문 결과 반영** (E1~E5)
   - 특히 E1 안전체크 7문항 추가
   - E4 IRB 사전 심의면제 확인

### 부분 베타 옵션 (정책 07 §1 — 출시 통제 원칙)
G5만 미충족인 경우:
- `pages/7_자료확인메시지예시.py` 비활성화
- `pages/8_자료요약본.py`의 PDF 다운로드 비활성화 (요약본 Markdown만 노출)
- 자료 정리·점수·분류·정적 안내 영역만 운영

G6만 미충족인 경우:
- 룰 엔진 비활성화 — 모든 분류를 PRELIMINARY 이하로 강제
- 「검산 가능 케이스 표시」 placeholder 유지

---

## 8. 위험·한계 요약

### 코드 차원의 잔여 위험 (자문 무관)
1. **실제 Anthropic API 호출 미테스트** — 베타 직전 1회 수동 검증 필수
2. **Streamlit AppTest 페이지 자동 테스트 미적용** — 핵심 페이지 5종 (1·2·3·5·7) 보강 권장
3. **Fernet 키 환경변수 평문 보관** — 베타 환경에서 KMS·Secret Manager 필수
4. **세션 상태 휘발성** — 페이지 새로고침 시 user_id·consent_id 손실 (쿠키/URL 파라미터 복원 후속)

### 외부 자문 의존 위험
정책 07 §8 한계 사항 매트릭스 참조 — 5개 그룹 매트릭스로 정리되어 있음.

### 신청서 v5와의 정합성 점검 결과
- KPI3 (RAG 출처·요약 불일치율 ≤5%): **N/A 처리** (정책 06 §2 명시)
- KPI4 (Bill Passport 개설률 ≥50%): 메트릭 구현, 베타 후 측정 가능
- KPI7 (실제 정정 사례 3~5건): 사용자 자가보고 기반, 보조 KPI로 강등 (정책 06 §2-A)
- v5 §G6 (출시 게이트): 본 보고서 §6과 일치

---

## 9. 권장 다음 액션

### 즉시 (1주 내)
1. **자문 패키지 송부**
   - 화우 ESG센터: BETA_CHECKLIST.md §D + 출력물 샘플
   - 한전 전문가: 정책 03·07 §4-B 질문 5개
   - 개인정보 외부 검토: 정책 04 + Anthropic DPA
   - NGO: 정책 05 + 안전체크 7문항 권고
2. **`docs/advisory/` 폴더 신설** — 자문서 수령 시 보관

### 중기 (2~4주, 자문 대기 중 병행 가능)
1. G3 라벨링 데이터셋 200건 수집·검증
2. AppTest로 핵심 페이지 자동 테스트 보강
3. KMS·Secret Manager 통합 (베타 환경 전용)

### 자문 결과 수령 후
1. **Phase 7b 룰 엔진 구현** (C1·C2·C3·C4 자문 후)
2. **정책 01 §8 표현 범위 재확정** (G5 자문 후)
3. **베타 환경 출시 결정 회의**

---

## 10. 결론

> **현재 상태: 시연·데모데이 출시 가능 / 베타 출시 차단 (외부 자문 의존)**

**완료**:
- Phase 0, 지침, 1, 2, 3, 4, 5, 6, 8(R1~R4), 9, 10
- 정책 8종 + 정적 안내 3종
- 운영·배포 문서 4종 (README·DEPLOYMENT·BETA_CHECKLIST·OPERATIONS)
- 테스트 335개

**자문 대기**:
- Phase 7a (KEPCO YAML·국외이전·화우 의견서)
- Phase 7b 차단

**다음 의사결정 포인트**:
- 자문 의견서 수령 시 정책 갱신 절차로 정책 01 §8·02 §3·03 §2·04 §9·05 §2에 반영
- 모든 게이트 충족 시 베타 시작 회의
- 부분 베타 결정 시 정책 07 §1 출시 통제 원칙 재확인

**최종 평가**:
공정에너지 MVP는 **신청서 v5 정체성에 정합한 상태**로 구축되었으며, **외부 자문 결과로 정책을 보강하기만 하면 베타 가능한 형태**다. 화우 자문이 가장 시급한 의존성이며, 자문 의견서 형식을 정책 07 §4-A에서 사전 정의해두었다.
