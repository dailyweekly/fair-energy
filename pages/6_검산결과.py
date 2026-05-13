"""6. 검산 결과 — 분류 UI.

자료 완결성 점수와 검산 가능성 분류를 한 화면에 표시한다.
사용자가 정액 관리비 자동 감지 결과를 명시적으로 override 할 수 있다.

Phase 7(룰 엔진) 활성화 전까지는 실제 계산 결과 자리를 placeholder로 둔다.
"""

from __future__ import annotations

import streamlit as st

from core import classification, demo, scoring, ui
from core.auth import require_password
from core.models import CaseClassification
from core.safety import DEFAULT_DISCLAIMER


require_password()

st.set_page_config(
    page_title="검산 결과 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=6, demo_mode=demo.is_demo_mode())

st.title("6. 검산 결과")


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
# 상태 계산
# ---------------------------------------------------------------------------

score = scoring.compute_completeness_score(conn, user_id=user_id)
tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
detected_fixed_fee = scoring.detect_fixed_fee(conn, user_id=user_id)

# Override는 세션에 보관. None = 자동 감지 사용.
OVERRIDE_KEY = "fixed_fee_override"
if OVERRIDE_KEY not in st.session_state:
    st.session_state[OVERRIDE_KEY] = None

effective_fixed_fee = (
    st.session_state[OVERRIDE_KEY]
    if st.session_state[OVERRIDE_KEY] is not None
    else detected_fixed_fee
)

case = classification.classify_case(
    score, tariff_input, is_fixed_fee=effective_fixed_fee
)
descriptor = classification.describe_case(case)


# ---------------------------------------------------------------------------
# 메인 결과 카드
# ---------------------------------------------------------------------------

st.markdown(f"## {descriptor.color_emoji} {descriptor.headline}")
st.info(descriptor.explanation)

m1, m2, m3 = st.columns(3)
m1.metric("자료 완결성 점수", f"{score.total_score} / 100")
m2.metric("분류", case.value)
m3.metric(
    "정액 케이스",
    "예" if effective_fixed_fee else "아니오",
    delta=("자동 감지" if st.session_state[OVERRIDE_KEY] is None else "사용자 지정"),
    delta_color="off",
)


# ---------------------------------------------------------------------------
# 다음 단계
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("가능한 다음 단계")
for action in descriptor.next_actions:
    st.markdown(f"- {action}")


# ---------------------------------------------------------------------------
# OFFICIAL 게이트가 막힌 사유
# ---------------------------------------------------------------------------

blocking = classification.reasons_blocking_official(
    score, tariff_input, is_fixed_fee=effective_fixed_fee
)

if case not in (
    CaseClassification.OFFICIAL_COMPARISON,
    CaseClassification.FIXED_MANAGEMENT_FEE,
) and blocking:
    st.markdown("---")
    st.subheader("공식 산식 비교가 활성화되지 않는 사유")
    for reason in blocking:
        st.markdown(f"- {reason}")


# ---------------------------------------------------------------------------
# 정액 케이스 override 토글
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("케이스 분류 조정")

with st.expander("정액 관리비 케이스 여부를 직접 설정", expanded=False):
    st.markdown(
        f"현재 자동 감지 결과: **{'정액 관리비' if detected_fixed_fee else '비정액'}**"
    )
    st.caption(
        "임대차계약서의 `전기료 별도 여부` 필드를 기반으로 감지합니다. "
        "감지 결과가 실제 상황과 다르면 직접 조정하세요."
    )

    current = st.session_state[OVERRIDE_KEY]
    options = ("자동 감지 사용", "정액 관리비로 분류", "비정액으로 분류")
    if current is None:
        idx = 0
    elif current is True:
        idx = 1
    else:
        idx = 2

    choice = st.radio(
        "분류 결과를 수동으로 조정하시겠습니까?",
        options=options,
        index=idx,
        key="fixed_fee_radio",
    )

    new_override = {options[0]: None, options[1]: True, options[2]: False}[choice]
    if new_override != st.session_state[OVERRIDE_KEY]:
        st.session_state[OVERRIDE_KEY] = new_override
        st.rerun()


# ---------------------------------------------------------------------------
# 부족 자료 (검산 불가/근거 요청 케이스에서 강조)
# ---------------------------------------------------------------------------

if score.missing_items:
    st.markdown("---")
    st.subheader("부족한 자료")
    for item in score.missing_items:
        st.markdown(f"- {item}")


# ---------------------------------------------------------------------------
# Phase 7 룰 엔진 placeholder
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("산식 비교 결과")

if case == CaseClassification.OFFICIAL_COMPARISON:
    st.info(
        "✅ 공식 산식 비교 게이트 통과. "
        "Phase 7 룰 엔진이 활성화되면 한전 공식 요금표 기준 계산값이 여기에 표시됩니다."
    )
elif case == CaseClassification.PRELIMINARY_CALCULATION:
    st.warning(
        "🟡 예비 검산 게이트 통과. "
        "Phase 7 룰 엔진이 활성화되면 부분 입력값 기반 예비 추정값이 여기에 표시됩니다. "
        "누락 필드가 보강되면 결과가 달라질 수 있습니다."
    )
elif case == CaseClassification.FIXED_MANAGEMENT_FEE:
    st.info(
        "🔵 정액 관리비 케이스. 산식 비교는 수행되지 않습니다. "
        "국토부 관리비 세부표시 의무 정책 안내가 별도 페이지로 제공됩니다."
    )
else:
    st.warning(
        "현재 케이스에서는 산식 비교가 수행되지 않습니다. "
        "위의 「부족한 자료」를 확보한 뒤 다시 진행해주세요."
    )


# ---------------------------------------------------------------------------
# 면책 + 다음 페이지 안내
# ---------------------------------------------------------------------------

st.markdown("---")
col_a, col_b = st.columns(2)
if col_a.button("Phase 5 점수 페이지로"):
    st.switch_page("pages/5_자료완결성점수.py")
if col_b.button("Phase 4 추출값 확인으로"):
    st.switch_page("pages/4_추출값확인.py")

with st.expander("법적 면책 (필독)"):
    st.markdown(DEFAULT_DISCLAIMER)

st.caption(
    "Phase 7(전기요금 룰 엔진), Phase 9(메시지 예시·자료 요약본 PDF) 이후 "
    "본 페이지의 placeholder 영역이 실제 결과로 채워집니다."
)
