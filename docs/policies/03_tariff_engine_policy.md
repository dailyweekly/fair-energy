# 03. 전기요금 룰 엔진 지침 (Tariff Engine Policy)

> 본 문서는 전기요금 계산 모듈의 책임 경계와 데이터 무결성 기준을 정한다.

---

## 1. 핵심 원칙

> **LLM은 요금을 계산하지 않는다.**
> **LLM은 문서에서 필드를 추출할 뿐이다.**
> **전기요금 계산은 `core/tariff_engine.py`의 deterministic rule engine만 수행한다.**

이 분리는 신청서 v5 「AI 활용 설명 — ② 룰 기반 검산 엔진」과 일치한다.
LLM이 계산을 하면 G6 「요금 계산 합성 테스트 100건 완전일치율 99% 이상」을 통과할 수 없다.

---

## 2. 데이터 출처 분리

- **요금표(tariff)**는 YAML 파일로 외부화한다. `data/tariffs/` 아래 위치한다.
- 룰 엔진은 YAML을 읽고 계산만 한다. 단가를 코드에 하드코딩하지 않는다.
- 모든 tariff YAML에는 다음 메타데이터를 반드시 포함한다.

```yaml
version: "demo-2026-01"
source: "DEMO_ONLY_REPLACE_WITH_OFFICIAL_KEPCO_TARIFF"
effective_from: "YYYY-MM-DD"
effective_to: "YYYY-MM-DD"
verified_by: null   # 검증 완료된 경우 사람 이름·기관 기재
```

`source: DEMO_ONLY_*` 또는 `verified_by: null`인 YAML이 로드되면 UI에 다음 경고를 반드시 표시한다.

```
⚠ 데모용 요금표가 사용되고 있습니다. 실제 산식과 다를 수 있습니다.
실증 단계에서는 한전 공식 요금표로 검증한 YAML을 사용해야 합니다.
```

---

## 3. 룰 엔진이 포함해야 할 항목

PoC 단계 한전 전기요금(주택용 저압 우선) 기준.

```
- 계약종별 (주택용 저압·고압·일반용 등)
- 기본요금 (구간별)
- 사용량 요금 (누진제 구간별 단가)
- 기후환경요금 (kWh당)
- 연료비조정단가 (kWh당)
- 부가가치세 (10%)
- 전력산업기반기금 (3.7%)
- 반올림 기준 (최종 청구액 단위)
- 검침 기간 일수 보정 (월말 검침 vs 사용자 청구 기간)
- 세대별 배분 산식 (사용량 기반·면적 기반·인원 기반 등)
```

---

## 4. 계산 함수 시그니처

```python
def calculate_electricity_bill(
    tariff_input: TariffInput,
    tariff: TariffTable,
) -> CalculationResult:
    ...
```

`TariffInput`은 Pydantic 모델로, 사용자 확인 플래그(`user_confirmed`)를 포함한다.
`TariffTable`은 YAML에서 로드된 dict 또는 dataclass.
`CalculationResult`는 다음을 포함한다.

```python
{
  "can_calculate": bool,
  "calculated_amount": int | None,
  "user_charged_amount": int | None,
  "difference_amount": int | None,
  "difference_rate": float | None,
  "formula_breakdown": list[dict],   # 단계별 계산식
  "warnings": list[str],
  "neutral_label": str,              # SAFE_LABELS에서 선택
}
```

---

## 5. 계산 중단 조건 (Hard Stops)

다음 중 하나라도 해당되면 계산하지 않고 `can_calculate=False`를 반환한다.

1. 필수 필드 누락 (검산 게이트 지침 4항)
2. `user_confirmed=False` 필드 존재
3. `is_fixed_fee=True` (정액 관리비 케이스)
4. tariff YAML의 검침 기간이 사용자 청구 기간과 모순
5. 누진제 구간 단가가 음수이거나 결측
6. 사용량 < 0 또는 청구액 < 0

---

## 6. 출력 포맷 (사용자 화면)

검산 가능 케이스의 결과 화면 예시.

```
공식 산식 비교 결과

사용자 청구액              38,000 원
공식 산식 기준 예비 계산액  31,240 원
산식 차이                  6,760 원

계산식:
  기본요금          910 원
  사용량 요금     27,150 원 (245 kWh 누진제)
  기후환경요금      2,205 원
  연료비조정단가     -49 원
  부가가치세        3,022 원
  전력기반기금      1,119 원
  ──────────────────────────
  합계            34,357 원

주의:
이 결과는 사용자가 제공하고 직접 확인한 자료를 기준으로 한 계산입니다.
임대인의 원고지서, 세대별 배분 산식, 검침기간 정보가 다르면 결과가 달라질 수 있습니다.
본 결과는 법률 판단이나 환급 가능성 판단이 아닙니다.
```

「부당」·「환급 가능」·「위반」 표현은 절대 사용하지 않는다.

---

## 7. 테스트 기준

`tests/test_tariff_engine.py`는 다음을 반드시 통과해야 한다.

- 데모 tariff YAML 기준 합성 입력 → 예상값과 일치
- `user_confirmed=False` → can_calculate=False
- 사용량 없음 → can_calculate=False
- 검침 기간 모순 → can_calculate=False
- `source=DEMO_ONLY_*` YAML 로드 시 경고 포함
- 출력 텍스트에 금지어가 포함되지 않음 (guardrails 통과)

신청서 v5 검증 기준 G6 「요금 계산 합성 테스트 100건 통과 (완전일치율 99% 이상)」은 본 모듈 단위 테스트에서 달성한다.

---

## 8. 책임 경계

- 룰 엔진은 「계산 결과」만 반환한다.
- 룰 엔진은 「법률 판단」·「환급 가능성」을 반환하지 않는다.
- 룰 엔진은 「차이가 발생함」을 사실로 보고할 뿐, 「차이의 원인」이 임대인의 잘못이라고 단정하지 않는다.
