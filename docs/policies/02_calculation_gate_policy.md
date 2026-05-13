# 02. 검산 게이트 지침 (Calculation Gate Policy)

> 본 문서는 「언제 계산하고 언제 계산을 중단할지」를 규정한다.
> 공정에너지의 핵심 차별점은 「검산을 많이 하는 것」이 아니라 「검산 가능 여부를 정직하게 분류하는 것」이다.

---

## 1. 원칙

> **점수가 높아도 필수 필드가 없으면 계산하지 않는다.**
> **AI가 추출했지만 사용자가 확인하지 않은 값은 계산에 사용하지 않는다.**

이 두 문장은 솔루션의 신뢰성을 결정한다. 무리하게 검산 가능 케이스를 늘리면 KPI4 「Bill Passport 개설률」은 오를 수 있지만 KPI3 「법률평가 오인 표현 검출률 0건」과 G4 「법률 판단 금지어 필터 통과」가 무너진다.

---

## 2. Energy Bill Completeness Score 배점

신청서 v5 「Step 2: Energy Bill Completeness Score」와 일치.

| 자료 | 배점 |
|------|----:|
| 임대차계약서 보유 | 15 |
| 관리비 항목별 내역 보유 | 15 |
| 계량기 사진·검침일 보유 | 15 |
| 한전 원고지서 또는 임대인 제공 원고지서 보유 | 25 |
| 임대인의 세대별 배분 산식 보유 | 20 |
| 납부내역·계좌이체 기록 보유 | 10 |
| **합계** | **100** |

---

## 3. 4구간 차등 기능 (Score Tiers)

| 점수 | 분류 | 가능 기능 |
|------|------|-----------|
| 0~39 | 검산 불가 | 필요 자료 체크리스트만 제공 |
| 40~69 | 근거 요청 필요 | 빈칸형 자료요청 메시지 예시 제공, 검산 미수행 |
| 70~89 | 예비 검산 가능 | 부분 입력값 기반 예비 계산 (오차 가능성 강고지) |
| 90~100 | 공식 산식 비교 가능 | 한전 전기요금 공식 산식 기준 계산 |

추가 분류: **정액 관리비 케이스** — 월세+관리비 정액 패키지 형태로 임차인이 사용량 기반 자료 자체를 보유하지 못한 경우. 점수와 무관하게 계산하지 않으며, 국토부 관리비 세부표시 의무 정책 안내로 한정한다.

---

## 4. 필수 필드 게이트 (Required Field Gate)

점수가 90점 이상이어도 다음 필드 중 하나라도 비어 있으면 **공식 산식 비교를 수행하지 않는다.**

```
- usage_kwh                  사용량 kWh
- billing_start_date         검침 시작일
- billing_end_date           검침 종료일
- user_charged_amount        사용자에게 청구된 금액
- contract_type              계약종별 (사용자 확인 필요)
- allocation_formula         세대별 배분 산식 또는 원고지서
- user_confirmed = True      사용자가 AI 추출값을 직접 확인했다는 플래그
```

점수 게이트(90+)와 필드 게이트 두 조건이 **AND**로 충족될 때만 `OFFICIAL_COMPARISON`으로 분류한다.

점수 게이트만 충족(90+, 필드 누락)되면 `PRELIMINARY_CALCULATION`으로 강등한다.

---

## 5. 사용자 확인 게이트 (User-Confirmed Gate)

OCR/멀티모달 LLM이 추출한 모든 필드는 기본값이 `user_confirmed=False`이다.

`core/tariff_engine.py`는 계산 함수의 첫 단계에서 다음을 검증한다.

```python
if not all(f.user_confirmed for f in required_fields):
    return CalculationResult(
        can_calculate=False,
        warnings=["사용자가 확인하지 않은 AI 추출값이 포함되어 있습니다."],
        neutral_label="확인 요망",
    )
```

이 게이트가 없으면 OCR 오류가 그대로 「공식 산식 차이」로 보고되어 임대인 측 역공 리스크가 발생한다.

---

## 6. 분류 의사결정 트리

```
입력: completeness_score, tariff_input, is_fixed_fee

if is_fixed_fee:
    return FIXED_MANAGEMENT_FEE

if score < 40:
    return NOT_CALCULABLE

if score < 70:
    return NEEDS_BASIS_REQUEST

if score < 90:
    return PRELIMINARY_CALCULATION

# score >= 90
if (usage_kwh and billing_start_date and billing_end_date
    and user_charged_amount and user_confirmed):
    return OFFICIAL_COMPARISON

return PRELIMINARY_CALCULATION  # 점수만 높고 필드 누락
```

---

## 7. 예비 검산(PRELIMINARY)의 책임

예비 검산은 「공식 산식 비교」가 아니다. 다음 문구를 결과 화면과 PDF에 반드시 표시한다.

```
이 결과는 일부 입력값이 누락된 상태에서의 예비 추정입니다.
누락 필드:
  - {누락 항목 1}
  - {누락 항목 2}
누락 필드가 보강된 뒤에는 결과가 달라질 수 있습니다.
본 결과는 공식 산식 비교가 아니므로 분쟁 근거로 사용할 수 없습니다.
```

---

## 8. 케이스 분포 목표 (신청서 v5 기대 성과 반영)

「검산 가능 케이스가 적게 나오는 것」이 솔루션의 본질이다. 다음 분포가 정상이다.

| 분류 | 베타 100명 중 기대 비율 |
|------|----:|
| 0~39점 (검산 불가) | 약 20% |
| 40~69점 (근거 요청 필요) | 약 60% |
| 70~89점 (예비 검산 가능) | 약 15% |
| 90~100점 (공식 산식 비교 가능) | 약 5% |

「공식 산식 비교 가능」 비율을 인위적으로 끌어올리려는 코드 변경은 본 지침 위반이다.

---

## 9. 테스트 기준

`tests/test_classification.py`는 다음을 반드시 통과해야 한다.

- 39점 → NOT_CALCULABLE
- 40점 → NEEDS_BASIS_REQUEST
- 69점 → NEEDS_BASIS_REQUEST
- 70점 → PRELIMINARY_CALCULATION
- 89점 → PRELIMINARY_CALCULATION
- 90점 + 필수 필드 완비 + user_confirmed=True → OFFICIAL_COMPARISON
- 90점 + 필수 필드 누락 → PRELIMINARY_CALCULATION
- 95점 + 필드 완비 + user_confirmed=False → PRELIMINARY_CALCULATION (확인 게이트 차단)
- 정액 관리비 플래그 → FIXED_MANAGEMENT_FEE (점수 무관)
