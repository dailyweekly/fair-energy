"""0. 심사관·자문위원 둘러보기 — 5분 시연 + 결과 미리보기 + 정책·가드레일 데모.

비선형 진입. 사용자 플로우(1→2→...)를 따라가지 않아도 솔루션의 핵심을 5분에 파악 가능.

⚠ 본 페이지는 본 솔루션의 **시연용 진입점**으로, 데모 모드가 활성화되어 있을 때
실제 데이터처럼 보이는 시드 데이터를 표시한다.
"""

from __future__ import annotations

import streamlit as st

from core import classification, demo, scoring, ui
from core.auth import require_password
from core.guardrails import (
    UnsafeOutputError,
    is_safe_output,
    scan_forbidden,
)
from core.models import CaseClassification


require_password()

st.set_page_config(
    page_title="둘러보기 · 공정에너지",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

# 데모 시드 자동 주입 (둘러보기는 데모 데이터 전제).
demo.ensure_demo_session(conn)

ui.inject_theme()

# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="background:white;border-radius:16px;padding:28px 28px 24px;
                margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
            <div style="font-size:28px;">🎬</div>
            <div style="font-size:22px;font-weight:700;color:#191F28;
                        letter-spacing:-0.02em;">
                심사관·자문위원 둘러보기
            </div>
        </div>
        <div style="font-size:14px;color:#6B7684;line-height:1.65;">
            공정에너지(Fair Energy)의 핵심 작동 방식과 정책 가드레일을 5분 안에 확인합니다.
            결과 페이지·정책 문서·라이브 가드레일 데모 순으로 안내합니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 1. 솔루션 한눈에
# ---------------------------------------------------------------------------

st.markdown("## 1️⃣ 한 줄로 보는 정체성")

st.markdown(
    """
    <div style="background:#F0F6FF;border-radius:12px;padding:20px 24px;
                margin-bottom:20px;border-left:4px solid #3182F6;">
        <div style="font-size:15px;color:#1B64DA;font-weight:700;margin-bottom:6px;">
            공정에너지는 법률서비스가 아닙니다.
        </div>
        <div style="font-size:14px;color:#4E5968;line-height:1.65;">
            임차인이 전기요금 청구 자료가 <b>검산 가능한 상태인지 진단</b>하고,
            공식 요금 산식과 비교 가능한 경우에만 <b>계산 근거를 제공</b>하는
            「Energy Bill Passport」 인프라입니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

cols = st.columns(3)
cols[0].markdown(
    """
    <div style="background:white;border-radius:12px;padding:16px;border:1px solid #E5E8EB;">
        <div style="font-size:13px;color:#8B95A1;margin-bottom:4px;">대상</div>
        <div style="font-size:14px;font-weight:600;color:#191F28;line-height:1.5;">
            서울·수도권 고시원·다가구 임차인
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
cols[1].markdown(
    """
    <div style="background:white;border-radius:12px;padding:16px;border:1px solid #E5E8EB;">
        <div style="font-size:13px;color:#8B95A1;margin-bottom:4px;">범위</div>
        <div style="font-size:14px;font-weight:600;color:#191F28;line-height:1.5;">
            전기요금만 (PoC)
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
cols[2].markdown(
    """
    <div style="background:white;border-radius:12px;padding:16px;border:1px solid #E5E8EB;">
        <div style="font-size:13px;color:#8B95A1;margin-bottom:4px;">AI 역할</div>
        <div style="font-size:14px;font-weight:600;color:#191F28;line-height:1.5;">
            OCR·점수·룰엔진·메시지 4종만
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 2. 데모 사용자 결과 미리보기
# ---------------------------------------------------------------------------

st.markdown("## 2️⃣ 결과 미리보기 — 데모 사용자 자료 완결성 점수")
st.caption("실제 사용자가 5종 자료를 모두 업로드·확인한 상태의 결과입니다.")

user_id = st.session_state["user_id"]
score = scoring.compute_completeness_score(conn, user_id=user_id)
tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
is_fixed_fee = scoring.detect_fixed_fee(conn, user_id=user_id)
case = classification.classify_case(score, tariff_input, is_fixed_fee=is_fixed_fee)
descriptor = classification.describe_case(case)

mcols = st.columns(3)
mcols[0].metric("자료 완결성 점수", f"{score.total_score}/100")
mcols[1].metric("검산 분류", case.value)
mcols[2].metric("필수 필드 확인", "✅ 모두" if tariff_input.user_confirmed else "⚠ 일부 누락")

st.markdown(
    f"""
    <div style="background:white;border-radius:12px;padding:20px;
                margin:16px 0;border:1px solid #E5E8EB;">
        <div style="font-size:16px;font-weight:700;color:#191F28;margin-bottom:8px;">
            {descriptor.color_emoji} {descriptor.headline}
        </div>
        <div style="font-size:14px;color:#4E5968;line-height:1.65;">
            {descriptor.explanation}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

cta_cols = st.columns(2)
with cta_cols[0]:
    if st.button("📊 점수 상세 보기 (페이지 5)", use_container_width=True, type="primary"):
        st.switch_page("pages/5_자료완결성점수.py")
with cta_cols[1]:
    if st.button("🎯 검산 결과 + 분류 (페이지 6)", use_container_width=True, type="primary"):
        st.switch_page("pages/6_검산결과.py")


# ---------------------------------------------------------------------------
# 3. 가드레일 라이브 데모
# ---------------------------------------------------------------------------

st.markdown("## 3️⃣ 가드레일 라이브 데모 — 정책 01 §2의 24개 패턴")
st.caption(
    "AI 출력·사용자 입력에 금지 표현이 포함되면 자동 차단됩니다. "
    "원하는 문장을 입력해 직접 확인해 보세요."
)

guard_examples = [
    "공식 산식과 큰 차이가 확인되지 않았습니다.",
    "임대인이 위법한 청구를 했습니다.",
    "환급 가능합니다.",
    "검침일이 누락되어 추가 자료가 필요합니다.",
    "법적 조치를 검토하세요.",
]

selected = st.selectbox(
    "예시 선택 또는 직접 입력 (아래 박스에서 수정)",
    options=guard_examples,
    index=0,
)
user_input = st.text_area(
    "검증할 문장",
    value=selected,
    height=80,
    key="guardrail_demo_input",
)

if user_input.strip():
    if is_safe_output(user_input):
        st.success("✅ 통과 — 정책 표현 범위 안의 중립 표현입니다.")
    else:
        hits = scan_forbidden(user_input)
        reasons = ", ".join(f"`{h.matched_text}` ({h.reason})" for h in hits[:3])
        st.error(
            f"⛔ 차단 — 정책 01 §2 금지 표현 검출: {reasons}\n\n"
            "이 표현은 사용자에게 노출되기 전 차단되며 `UnsafeOutputError`로 코드 흐름이 중단됩니다."
        )


# ---------------------------------------------------------------------------
# 4. 정책 8종 카드
# ---------------------------------------------------------------------------

st.markdown("## 4️⃣ 정책 문서 — 코드로 강제되는 8종")
st.caption(
    "본 솔루션은 8개 정책 문서를 코드·테스트로 강제합니다. "
    "GitHub에서 전문 확인 가능합니다."
)

policies = [
    ("00", "서비스 범위", "정체성·MVP 범위·금지 기능", "00_service_scope_policy.md"),
    ("01", "출력 표현", "금지어 24개·허용 표현·면책 문구", "01_output_language_policy.md"),
    ("02", "검산 게이트", "100점 배점·4구간·필수 필드 게이트", "02_calculation_gate_policy.md"),
    ("03", "룰 엔진", "LLM 계산 금지·tariff YAML·DEMO_ONLY 경고", "03_tariff_engine_policy.md"),
    ("04", "개인정보·보관", "원본/마스킹 분리·6/12/36개월·RRN 거부", "04_privacy_retention_policy.md"),
    ("05", "사용자 안전", "4단계 등급(LOW/MED/HIGH/VERY_HIGH)·메시지 차단", "05_user_safety_policy.md"),
    ("06", "PoC 측정", "KPI 1차 평가·이벤트 17종·분포 목표", "06_poc_metrics_policy.md"),
    ("07", "출시 통제", "G1~G6 게이트·자문 의존성·한계 사항", "07_release_control_policy.md"),
]

repo_base = "https://github.com/dailyweekly/fair-energy/blob/main/docs/policies/"

for i in range(0, len(policies), 2):
    cols = st.columns(2)
    for col_idx in range(2):
        if i + col_idx >= len(policies):
            continue
        num, title, desc, filename = policies[i + col_idx]
        with cols[col_idx]:
            st.markdown(
                f"""
                <div style="background:white;border-radius:12px;padding:16px;
                            border:1px solid #E5E8EB;margin-bottom:8px;">
                    <div style="font-size:12px;color:#8B95A1;margin-bottom:4px;">
                        정책 {num}
                    </div>
                    <div style="font-size:15px;font-weight:700;color:#191F28;margin-bottom:6px;">
                        {title}
                    </div>
                    <div style="font-size:13px;color:#4E5968;line-height:1.5;margin-bottom:10px;">
                        {desc}
                    </div>
                    <a href="{repo_base}{filename}" target="_blank"
                       style="font-size:13px;color:#3182F6;text-decoration:none;font-weight:600;">
                        GitHub에서 보기 →
                    </a>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# 5. 사용자 여정 vs 심사관 여정 시각화
# ---------------------------------------------------------------------------

st.markdown("## 5️⃣ 사용자 여정 vs 심사관 여정")

journey_cols = st.columns(2)
with journey_cols[0]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:20px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:15px;font-weight:700;color:#191F28;margin-bottom:10px;">
                🧑‍💼 사용자 여정
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.8;">
                ① 시작·동의<br>
                ② 자료 업로드 (5종)<br>
                ③ AI 추출값 직접 확인<br>
                ④ 자료 완결성 점수 확인<br>
                ⑤ 검산 결과 분류<br>
                ⑥ 자료요청 메시지 (필요시)<br>
                ⑦ 자료 요약본 PDF
            </div>
            <div style="margin-top:14px;font-size:12px;color:#8B95A1;">
                소요: 약 5~10분 · 본인 자료 필요
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with journey_cols[1]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:20px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:15px;font-weight:700;color:#191F28;margin-bottom:10px;">
                🎬 심사관·자문 여정
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.8;">
                ① 정체성 확인 (법률서비스 아님)<br>
                ② 결과 미리보기 (점수·분류)<br>
                ③ 가드레일 라이브 데모<br>
                ④ 정책 8종 확인<br>
                ⑤ 핵심 페이지 둘러보기<br>
                ⑥ KPI 대시보드 (운영자)<br>
                ⑦ GitHub repo 코드 검토
            </div>
            <div style="margin-top:14px;font-size:12px;color:#8B95A1;">
                소요: 약 5분 · 데모 데이터 자동 제공
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 6. 외부 링크
# ---------------------------------------------------------------------------

st.markdown("## 6️⃣ 외부 자료")

ext_cols = st.columns(2)
with ext_cols[0]:
    st.link_button(
        "📂 GitHub 저장소",
        "https://github.com/dailyweekly/fair-energy",
        use_container_width=True,
    )
with ext_cols[1]:
    st.link_button(
        "📊 KPI 대시보드 (관리자)",
        "/10_KPI_대시보드",
        use_container_width=True,
        disabled=False,
    )

st.markdown(
    """
    <div style="margin-top:20px;padding:14px 16px;background:#FAFBFC;border-radius:10px;
                font-size:12px;color:#8B95A1;text-align:center;">
        본 환경은 외부 자문(2026-05-13) 추정 의견 기반의 시연용입니다.
        화우 ESG센터·한전 전기요금 전문가·개인정보·NGO 자문 결과 수령 후 표현·기능이 조정될 수 있습니다.
    </div>
    """,
    unsafe_allow_html=True,
)
