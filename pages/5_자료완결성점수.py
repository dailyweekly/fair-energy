"""5. 자료 완결성 점수.

업로드·확인된 자료를 기준으로 100점 만점 점수와 검산 가능성 분류를 표시한다.
정책 02 §4 — 점수만으로 검산 가능성이 보장되지 않는다는 점을 사용자에게 명시한다.
"""

from __future__ import annotations

import streamlit as st

from core import classification, redaction, scoring
from core.models import CaseClassification


st.set_page_config(page_title="자료 완결성 점수 · 공정에너지", page_icon="⚡")
st.title("5. 자료 완결성 점수")


# ---------------------------------------------------------------------------
# 가드
# ---------------------------------------------------------------------------

if not st.session_state.get("user_id"):
    st.warning("먼저 시작하기 페이지에서 시작해주세요.")
    st.page_link("pages/1_시작하기.py", label="← 시작하기")
    st.stop()

if not st.session_state.get("consent_id"):
    st.warning("동의가 필요합니다.")
    st.page_link("pages/2_동의_및_안전체크.py", label="← 동의 및 안전 체크")
    st.stop()


from app import conn  # type: ignore[attr-defined]

user_id = st.session_state["user_id"]


# ---------------------------------------------------------------------------
# 점수 계산
# ---------------------------------------------------------------------------

score = scoring.compute_completeness_score(conn, user_id=user_id)
tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
is_fixed_fee = scoring.detect_fixed_fee(conn, user_id=user_id)
case = classification.classify_case(score, tariff_input, is_fixed_fee=is_fixed_fee)


# ---------------------------------------------------------------------------
# 메인 메트릭
# ---------------------------------------------------------------------------

st.metric(
    "Energy Bill Completeness Score",
    f"{score.total_score} / 100",
)

# 분류 배지(중립 표현 유지).
tier_color = {
    CaseClassification.NOT_CALCULABLE: "🔴",
    CaseClassification.NEEDS_BASIS_REQUEST: "🟠",
    CaseClassification.PRELIMINARY_CALCULATION: "🟡",
    CaseClassification.OFFICIAL_COMPARISON: "🟢",
    CaseClassification.FIXED_MANAGEMENT_FEE: "🔵",
}.get(case, "⚪")

st.subheader(f"{tier_color} 분류 결과 — {case.value}")

case_messages = {
    CaseClassification.NOT_CALCULABLE: (
        "현재 자료만으로는 검산할 수 없습니다. "
        "아래 체크리스트의 자료를 추가 확보해주세요."
    ),
    CaseClassification.NEEDS_BASIS_REQUEST: (
        "검산에 필요한 근거 자료가 부족합니다. "
        "임대인에게 보낼 자료요청 메시지 예시(다음 단계)를 검토해보세요."
    ),
    CaseClassification.PRELIMINARY_CALCULATION: (
        "일부 입력값 기반 예비 검산이 가능합니다. "
        "필수 필드가 보강되면 결과가 달라질 수 있습니다."
    ),
    CaseClassification.OFFICIAL_COMPARISON: (
        "공식 산식 기준 검산이 가능합니다. "
        "본 결과는 사용자가 직접 확인한 자료를 기준으로 한 계산이며, "
        "법률 판단이나 환급 가능성 판단이 아닙니다."
    ),
    CaseClassification.FIXED_MANAGEMENT_FEE: (
        "정액 관리비 케이스로 분류되었습니다. "
        "국토부 관리비 세부표시 의무 정책 안내가 별도로 제공됩니다."
    ),
}
st.info(case_messages.get(case, ""))


# ---------------------------------------------------------------------------
# 배점 상세 + 누락 자료
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("배점 상세")

breakdown_rows = [
    ("임대차계약서", score.lease_contract, scoring.SCORE_WEIGHTS["lease_contract"]),
    ("관리비 항목별 내역", score.itemized_fee_notice,
     scoring.SCORE_WEIGHTS["itemized_fee_notice"]),
    ("계량기 사진·검침일", score.meter_photo_with_date,
     scoring.SCORE_WEIGHTS["meter_photo_with_date"]),
    ("한전·임대인 원고지서", score.original_electricity_bill,
     scoring.SCORE_WEIGHTS["original_electricity_bill"]),
    ("세대별 배분 산식", score.allocation_formula,
     scoring.SCORE_WEIGHTS["allocation_formula"]),
    ("납부내역·계좌이체", score.payment_proof,
     scoring.SCORE_WEIGHTS["payment_proof"]),
]

for label, value, weight in breakdown_rows:
    pct = (value / weight) if weight else 0
    st.progress(
        pct,
        text=f"{label}  ·  {value} / {weight}",
    )


if score.missing_items:
    st.markdown("---")
    st.subheader("부족한 자료 체크리스트")
    for item in score.missing_items:
        st.markdown(f"- {item}")


# ---------------------------------------------------------------------------
# 가능한 다음 단계
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("가능한 다음 단계")
for action in score.available_actions:
    st.markdown(f"- {action}")


# ---------------------------------------------------------------------------
# 진단 정보 (TariffInput 상태)
# ---------------------------------------------------------------------------

with st.expander("검산 입력값 진단"):
    st.json({
        "usage_kwh": tariff_input.usage_kwh,
        "billing_start_date": tariff_input.billing_start_date,
        "billing_end_date": tariff_input.billing_end_date,
        "contract_type": tariff_input.contract_type,
        "user_charged_amount": tariff_input.user_charged_amount,
        "allocation_formula": tariff_input.allocation_formula,
        "user_confirmed (all required)": tariff_input.user_confirmed,
        "is_fixed_fee_detected": is_fixed_fee,
    })
    if not tariff_input.user_confirmed:
        st.warning(
            "공식 산식 비교에 필요한 필드 중 사용자 확인이 누락된 항목이 있습니다. "
            "Phase 4 추출값 확인 페이지로 돌아가 누락 필드를 확인해주세요."
        )


# ---------------------------------------------------------------------------
# 스냅샷 저장
# ---------------------------------------------------------------------------

st.markdown("---")
col1, col2, col3 = st.columns(3)
if col1.button("점수 저장", type="primary"):
    from core import metrics

    score_id = scoring.save_score_snapshot(conn, user_id=user_id, score=score)
    st.session_state["latest_score_id"] = score_id
    st.session_state["latest_case"] = case.value

    # 첫 점수 저장이면 passport_created 이벤트, 매번 score_calculated/case_classified.
    is_first = scoring.latest_score(conn, user_id=user_id) is not None and (
        conn.execute(
            "SELECT COUNT(*) AS c FROM passport_scores WHERE user_id = ?",
            (user_id,),
        ).fetchone()["c"] == 1
    )
    if is_first:
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_PASSPORT_CREATED,
            user_id=user_id,
            metadata={"initial_score": score.total_score},
        )
    metrics.log_event(
        conn,
        event_name=metrics.EVENT_SCORE_CALCULATED,
        user_id=user_id,
        metadata={
            "score": score.total_score,
            "missing_count": len(score.missing_items),
        },
    )
    metrics.log_event(
        conn,
        event_name=metrics.EVENT_CASE_CLASSIFIED,
        user_id=user_id,
        metadata={"classification": case.value, "score": score.total_score},
    )
    st.success(f"점수가 저장되었습니다. (score_id: {score_id[:8]}…)")

if col2.button("마스킹본 재생성"):
    from app import app_config  # type: ignore[attr-defined]

    count = redaction.regenerate_all_masked_views(
        conn, user_id=user_id, masked_dir=app_config.masked_dir,
    )
    if count:
        st.success(
            f"{count}건의 문서에 대해 마스킹본을 재생성했습니다. "
            "마스킹본은 사용자 확인 필드만 포함하며, 원본의 시각 정보는 포함하지 않습니다."
        )
    else:
        st.info(
            "재생성 가능한 마스킹본이 없습니다. "
            "확인된 필드가 있고 원본 파일이 있는 문서만 마스킹본이 생성됩니다."
        )

if col3.button("Phase 4로 돌아가 추가 확인"):
    st.switch_page("pages/4_추출값확인.py")

st.caption(
    "Phase 6(분류 UI), Phase 7(전기요금 룰 엔진), "
    "Phase 9(자료요청 메시지 예시·자료 요약본 PDF) 이후 추가 페이지가 연결됩니다."
)
