# 06. PoC 측정 지침 (PoC Metrics Policy)

> 본 문서는 신청서 v5 KPI·출시 게이트의 측정 방법과 이벤트 로그 표준을 정한다.

---

## 1. 출시 게이트 (Release Gates) — 베타 출시 절대 조건

다음 게이트를 만족하지 못하면 베타를 시작할 수 없다. KPI가 아니다.

| 게이트 | 내용 | 측정 방법 |
|--------|------|-----------|
| G1 | RAG 허위 법령·판례 인용 0건 | RAG 응답 100건 샘플링 수동 검수 |
| G2 | RAG 응답 출처 표시율 100% | 자동 로그 분석 |
| G3 | 임대인 식별정보 자동 마스킹 정확도 ≥95% | 라벨링 데이터 200건 비교 |
| G4 | 법률 판단 금지어 필터 구현·통과 | `tests/test_guardrails.py` 전체 통과 |
| G5 | 화우 변호사법 사전 검토 메모 확보 | 의견서 PDF 보관 |
| G6 | 요금 계산 합성 테스트 100건 완전일치율 ≥99% | `tests/test_tariff_engine.py` |

`scripts/check_release_gates.py`를 만들어 베타 출시 직전 자동 검증한다(MVP 외 추가 작업).

---

## 2. 정량 KPI (베타 100명 기준 보수적 현실값) — v5 신청서 정합

| KPI | 목표값 |
|-----|-------:|
| KPI1 — OCR 필드 추출 정확도 | ≥90% |
| KPI2-합성 — 룰 엔진 합성 테스트 완전일치율 | ≥99% |
| KPI2-실제 — 실제 사용자 문서 데이터 해석 오류 수정률 | ≤20% |
| KPI3 — 법률평가 오인 표현 검출률 | 0건 (G4 가드레일) |
| KPI4 — Bill Passport 개설률 | ≥50% |
| KPI5-NGO — 3개월 업로드 지속률 (NGO 동행군) | ≥30% |
| KPI5-일반 — 3개월 업로드 지속률 (일반군) | ≥10~15% |
| KPI6-발송 — 산식 공개 요청 메시지 발송률 | ≥50% (근거 요청 케이스 중) |
| KPI6-반응 — 임대인 반응율 (자가보고) | 보조 지표(2026-05-13) |
| KPI6-답변 — 공식 답변·산식 공개·재정산 수령률 | 보조 지표(2026-05-13) |
| KPI7 — 실제 정정·산식 공개·재정산 확인 건수 | 3~5건 |

※ v5 신청서의 KPI3(RAG 출처·요약 불일치율 ≤5%)은 정책 07 결정에 따라 RAG 미사용으로 N/A.

## 2-A. PoC 1차 평가 KPI 계층 (2026-05-13 외부 자문 반영)

베타 100명의 PoC 성과를 평가할 때 **사용자가 검산 가능한 상태에 가까워졌는지**를 1차 평가로 둔다.
임대인 응답 등 외부 변수에 의존하는 지표는 보조로 강등한다.

| 순위 | KPI | 측정 방법 | 목표 |
|---:|---|---|---:|
| 1차 | **자료 완결성 점수 개선률** | (마지막 score - 첫 score) / 첫 score | 평균 ≥ 30% |
| 2차 | **자료요청 메시지 예시 복사율** | request_template_copied / classification=NEEDS_BASIS_REQUEST 사용자 | ≥ 50% |
| 3차 | **추가 자료 확보 후 재업로드율** | 첫 업로드 후 30일 내 재업로드 사용자 / 전체 사용자 | ≥ 25% |
| 4차 | **임대인 답변 자가보고율 (보조)** | KPI6-답변과 동일 | 10~15% |
| 5차 | **실제 정산 재확인 사례 수 (보조)** | KPI7과 동일 | 3~5건 |

### 1차 KPI 우선 이유

"임대인이 답했다"는 사용자 자가보고 외 객관 측정이 어렵고, 임대인 측 변수가 크다.
"자료 완결성 점수 개선률"은 **사용자 본인이 통제 가능한 행동 신호**이며,
서비스 가치(검산 가능 상태 도달)와 직접 정렬된다.

`scoring.compute_completeness_score()`를 첫 진입 시점과 마지막 활동 시점에 모두 기록하여 차이를 계산한다.
이를 위해 `passport_scores` 테이블이 동일 사용자의 다회 스냅샷을 보관하는 구조가 이미 준비되어 있다.

---

## 3. 정성 지표

- 사용자 권리 인식 변화 (사전·사후 5점 척도 10문항) — 향상 ≥0.5점
- 화우 자문 결과의 변호사법 리스크 평가
- NGO 케이스워크 도구 사용성 (NPS)
- B2B2C 무상 PoC 도입 의향서 ≥2건

---

## 4. 이벤트 로그 스키마

`core/metrics.py`의 `log_event()`로 단일 기록.

```python
{
  "event_id": "uuid4",
  "user_id": "uuid4",
  "timestamp": "ISO8601",
  "event_name": "...",
  "metadata": {...}
}
```

### 표준 이벤트 명세

| event_name | 발생 시점 | 필수 metadata |
|------------|-----------|---------------|
| user_registered | 사용자 가입 완료 | cohort (`ngo`/`general`) |
| consent_completed | 동의·안전 체크 완료 | safety_level |
| safety_check_completed | 안전 체크 응답 저장 | safety_level |
| manual_input_used | 사용자가 OCR 거부 후 수동 입력 모드 사용 | (2026-05-13 추가) |
| document_uploaded | 문서 업로드 | document_type, file_size |
| document_rejected_rrn | 주민번호 감지로 업로드 거부 | (2026-05-13 추가) |
| ocr_completed | LLM OCR 완료 | document_id, field_count, avg_confidence |
| field_confirmed | 사용자가 필드 확인 완료 | document_id, confirmed_count |
| passport_created | 첫 Bill Passport 생성 | initial_score |
| score_calculated | 자료 완결성 점수 산정 | score, missing_items |
| case_classified | 4분류 결과 | classification |
| calculation_completed | 룰 엔진 계산 완료 | can_calculate, difference_amount |
| request_template_viewed | 자료요청 메시지 예시 조회 | safety_level |
| request_template_copied | 자료요청 메시지 복사 | safety_level |
| high_risk_template_copy_blocked | HIGH/VERY HIGH 등급 차단 | safety_signals |
| summary_pdf_downloaded | **에너지 청구 자료 요약본** PDF 다운로드 | (구 evidence_pack_downloaded, 2026-05-13 명칭 변경) |
| user_returned_next_month | 다음 달 재업로드 | months_since_first_upload |

---

## 5. KPI 계산식

```
Bill Passport 개설률
= passport_created 사용자 수 / user_registered 사용자 수

업로드 지속률 (3개월)
= 3개월 연속 document_uploaded 사용자 수 / passport_created 사용자 수

코호트별 분리: cohort=ngo / cohort=general

산식 공개 요청 메시지 복사율
= request_template_copied 사용자 수 / classification=NEEDS_BASIS_REQUEST 사용자 수

검산 가능 비율
= classification=OFFICIAL_COMPARISON 케이스 수 / 전체 case_classified

검산 불가율
= classification=NOT_CALCULABLE 케이스 수 / 전체 case_classified
```

---

## 6. 케이스 분포 기대값 (정상 분포)

| 분류 | 베타 100명 중 기대 비율 |
|------|----:|
| 0~39점 (검산 불가) | 약 20% |
| 40~69점 (근거 요청 필요) | 약 60% |
| 70~89점 (예비 검산 가능) | 약 15% |
| 90~100점 (공식 산식 비교 가능) | 약 5% |
| 정액 관리비 케이스 (점수 무관) | 약 10건 |

검산 가능 비율을 인위적으로 끌어올리려는 코드 변경은 02_calculation_gate_policy 위반이다.

---

## 7. 보고

`scripts/export_metrics.py`로 분기별 KPI를 CSV로 export한다.
PoC 종료 시 검증 보고서에 본 문서의 KPI별 실측값과 목표값을 비교 표로 정리한다.

---

## 8. 테스트 기준

이벤트 로그 자체에 대한 단위 테스트는 후속 단계로 이연한다.
MVP에서는 `log_event()` 호출이 예외 없이 통과하고 이벤트 파일에 한 줄씩 기록되는지만 확인한다.
