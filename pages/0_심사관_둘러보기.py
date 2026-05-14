"""0. 심사관·자문위원 둘러보기 — 어떤 문제를 어떻게 푸는지 5분 안내.

일반인도 알 수 있게 「검산」 같은 전문 용어를 쓰지 않고,
Input → 처리 → Output 흐름을 시각화한 페이지.

⚠ 본 페이지는 데모 모드 전제 (시드 데이터 자동 주입).
"""

from __future__ import annotations

import streamlit as st

from core import classification, demo, scoring, ui
from core.auth import require_password
from core.guardrails import is_safe_output, scan_forbidden


require_password()

st.set_page_config(
    page_title="둘러보기 · 공정에너지",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

demo.ensure_demo_session(conn)
ui.inject_theme()


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="background:white;border-radius:16px;padding:28px 28px 22px;
                margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
            <div style="font-size:28px;">🎬</div>
            <div style="font-size:22px;font-weight:700;color:#191F28;
                        letter-spacing:-0.02em;">
                심사관·자문위원 둘러보기 (5분)
            </div>
        </div>
        <div style="font-size:14px;color:#6B7684;line-height:1.65;">
            공정에너지가 <b>어떤 문제를 푸는지</b>,
            <b>어떤 자료를 받아 어떻게 처리하는지</b>,
            <b>실제로 어떤 결과가 나오는지</b>를 차례대로 안내합니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# §1. 어떤 문제를 푸나요?
# ---------------------------------------------------------------------------

st.markdown("## ① 어떤 문제를 푸나요?")

st.markdown(
    """
    <div style="background:#FFF7E5;border-radius:12px;padding:18px 22px;
                margin-bottom:12px;border-left:4px solid #FFCA28;">
        <div style="font-size:14px;font-weight:700;color:#5D4037;margin-bottom:8px;">
            💡 한 줄로
        </div>
        <div style="font-size:15px;color:#5D4037;line-height:1.7;">
            <b>고시원·다세대·반지하에 사는 분이 매달 받는 전기요금이
            한전 공식 요금표대로 정확히 청구된 건지 본인이 직접 확인할 수 없는 문제</b>를 풉니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

prob_cols = st.columns(3)
with prob_cols[0]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:18px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:24px;margin-bottom:8px;">🏠</div>
            <div style="font-size:14px;font-weight:700;color:#191F28;margin-bottom:6px;">
                상황
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.6;">
                고시원·다가구는 한전 계량기 1개로 임대인이 한꺼번에 전기료를 받고,
                세대별로 나눠 임차인에게 다시 청구합니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with prob_cols[1]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:18px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:24px;margin-bottom:8px;">❓</div>
            <div style="font-size:14px;font-weight:700;color:#191F28;margin-bottom:6px;">
                지금의 한계
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.6;">
                그 분배가 맞는지 확인할 도구가 없습니다.
                매달 1~2만원이 잘못 청구돼도 임차인은 알기 어렵습니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with prob_cols[2]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:18px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:24px;margin-bottom:8px;">📊</div>
            <div style="font-size:14px;font-weight:700;color:#191F28;margin-bottom:6px;">
                규모
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.6;">
                2024년 1인 가구 804만 중<br>
                청년 복합위기 가구의 73.3%가 고시원 거주<br>
                (국회입법조사처, 2025)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# §2. 어떤 자료를 받아 무엇을 하나요? (Input → 처리 → Output)
# ---------------------------------------------------------------------------

st.markdown("## ② 어떻게 작동하나요?")
st.caption("사용자가 자료를 올리면 5단계로 처리해서 결과를 보여드립니다.")

flow_cols = st.columns([1, 0.15, 1, 0.15, 1])

with flow_cols[0]:
    st.markdown(
        """
        <div style="background:#F0F6FF;border-radius:12px;padding:18px;
                    border:1px solid #C6DAF8;height:300px;">
            <div style="font-size:11px;color:#1B64DA;font-weight:700;letter-spacing:0.5px;">
                📥 INPUT
            </div>
            <div style="font-size:15px;font-weight:700;color:#191F28;margin:6px 0 10px;">
                사용자가 올리는 자료
            </div>
            <div style="font-size:12px;color:#4E5968;line-height:1.7;">
                ① 임대차계약서<br>
                ② 한전 고지서 또는 임대인이 준 청구서<br>
                ③ 계량기 사진 (검침일 포함)<br>
                ④ 관리비 청구 내역<br>
                ⑤ 납부 영수증·계좌이체 기록
                <br><br>
                <i>또는 AI 사용이 부담스러우면<br>
                숫자만 직접 입력 가능 (수동 모드)</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with flow_cols[1]:
    st.markdown(
        "<div style='font-size:24px;color:#3182F6;text-align:center;margin-top:140px;'>→</div>",
        unsafe_allow_html=True,
    )

with flow_cols[2]:
    st.markdown(
        """
        <div style="background:#FFF;border-radius:12px;padding:18px;
                    border:1px solid #E5E8EB;height:300px;">
            <div style="font-size:11px;color:#6B7684;font-weight:700;letter-spacing:0.5px;">
                ⚙️ 처리
            </div>
            <div style="font-size:15px;font-weight:700;color:#191F28;margin:6px 0 10px;">
                5단계로 분석
            </div>
            <div style="font-size:12px;color:#4E5968;line-height:1.7;">
                <b>1.</b> AI가 자료에서 숫자·날짜 뽑기<br>
                &nbsp;&nbsp;&nbsp;&nbsp;<i>(사용자가 직접 확인·수정)</i><br>
                <b>2.</b> 자료가 충분한지 100점 채점<br>
                <b>3.</b> 점수로 다음 단계 분류<br>
                <b>4.</b> 한전 공식 요금표 기준 계산<br>
                &nbsp;&nbsp;&nbsp;&nbsp;<i>(자료 충분할 때만)</i><br>
                <b>5.</b> 청구액과 비교
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with flow_cols[3]:
    st.markdown(
        "<div style='font-size:24px;color:#3182F6;text-align:center;margin-top:140px;'>→</div>",
        unsafe_allow_html=True,
    )

with flow_cols[4]:
    st.markdown(
        """
        <div style="background:#E8F8EE;border-radius:12px;padding:18px;
                    border:1px solid #B7E4C7;height:300px;">
            <div style="font-size:11px;color:#2D9A4B;font-weight:700;letter-spacing:0.5px;">
                📊 OUTPUT
            </div>
            <div style="font-size:15px;font-weight:700;color:#191F28;margin:6px 0 10px;">
                사용자가 받는 결과
            </div>
            <div style="font-size:12px;color:#4E5968;line-height:1.7;">
                ① 자료 충분도 점수 (100점)<br>
                ② 5종 분류<br>
                &nbsp;&nbsp;&nbsp;&nbsp;검산 불가 / 근거 요청 /<br>
                &nbsp;&nbsp;&nbsp;&nbsp;예비 계산 / 공식 비교 /<br>
                &nbsp;&nbsp;&nbsp;&nbsp;정액 관리비<br>
                ③ 계산 결과 비교<br>
                ④ 임대인에게 보낼 메시지 예시<br>
                ⑤ 자료 요약본 PDF
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# 자료별 점수 안내
st.markdown(
    """
    <div style="background:white;border-radius:12px;padding:18px 22px;
                margin:18px 0;border:1px solid #E5E8EB;">
        <div style="font-size:14px;font-weight:700;color:#191F28;margin-bottom:10px;">
            📊 자료마다 점수가 있습니다 (총 100점)
        </div>
        <div style="font-size:13px;color:#4E5968;line-height:1.8;">
            한전·임대인 청구서 <b style="color:#3182F6;">25점</b> &nbsp;·&nbsp;
            배분 산식 <b style="color:#3182F6;">20점</b> &nbsp;·&nbsp;
            임대차계약서 <b style="color:#3182F6;">15점</b> &nbsp;·&nbsp;
            관리비 내역 <b style="color:#3182F6;">15점</b> &nbsp;·&nbsp;
            계량기 사진 <b style="color:#3182F6;">15점</b> &nbsp;·&nbsp;
            납부 영수증 <b style="color:#3182F6;">10점</b>
            <br><br>
            <span style="color:#8B95A1;font-size:12px;">
            자료가 충분할수록 점수가 높아지고, 가능한 다음 단계가 달라집니다.
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# §3. 실제 결과 미리보기
# ---------------------------------------------------------------------------

st.markdown("## ③ 실제 결과 미리보기")
st.caption("아래는 데모 사용자(5종 자료 모두 입력 완료)의 실제 결과입니다.")

user_id = st.session_state["user_id"]
score = scoring.compute_completeness_score(conn, user_id=user_id)
tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
is_fixed_fee = scoring.detect_fixed_fee(conn, user_id=user_id)
case = classification.classify_case(score, tariff_input, is_fixed_fee=is_fixed_fee)
descriptor = classification.describe_case(case)

mcols = st.columns(3)
mcols[0].metric("자료 충분도", f"{score.total_score}/100")
mcols[1].metric("분류 결과", case.value)
mcols[2].metric(
    "필수 필드", "✅ 모두 확인됨" if tariff_input.user_confirmed else "⚠ 일부 누락",
)

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
    if st.button(
        "📊 점수 상세 화면 보기", use_container_width=True, type="primary",
    ):
        st.switch_page("pages/5_자료완결성점수.py")
with cta_cols[1]:
    if st.button(
        "🎯 분류·결과 화면 보기", use_container_width=True, type="primary",
    ):
        st.switch_page("pages/6_검산결과.py")


# ---------------------------------------------------------------------------
# §4. 표현 안전장치 — 「출력 안 되는 말」 직접 입력해보기
# ---------------------------------------------------------------------------

st.markdown("## ④ 표현 안전장치 — 위험한 말은 자동으로 막아드려요")

st.markdown(
    """
    <div style="background:#FFF7E5;border-radius:12px;padding:16px 20px;
                margin-bottom:14px;border-left:4px solid #FFCA28;">
        <div style="font-size:13px;color:#5D4037;line-height:1.7;">
            <b>이 서비스는 변호사가 아니라 도구</b>이기에,
            「위반」·「환급 가능」·「과다 청구」 같은 법률 단정 표현이 사용자에게 노출되기 전 자동으로 차단됩니다.
            <br><br>
            아래에서 <b>예시를 선택하거나 직접 문장을 입력</b>해 어떤 말이 통과되고 어떤 말이 막히는지 확인해보세요.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 예시 선택지 — ✅ 통과 / ⛔ 차단 라벨을 옵션 텍스트에 직접 포함.
guard_examples = [
    "✅ 통과 예시 — 공식 산식과 큰 차이가 확인되지 않았습니다.",
    "⛔ 차단 예시 — 임대인이 위법한 청구를 했습니다.",
    "⛔ 차단 예시 — 환급 가능합니다.",
    "✅ 통과 예시 — 검침일이 누락되어 추가 자료가 필요합니다.",
    "⛔ 차단 예시 — 법적 조치를 검토하세요.",
    "⛔ 차단 예시 — 과다 청구로 보입니다.",
]

selected = st.selectbox(
    "예시 5개 중 하나를 골라보세요 (또는 아래 박스에서 직접 입력)",
    options=guard_examples,
    index=0,
    help=(
        "선택한 예시 문장이 아래 박스에 자동으로 채워집니다. "
        "직접 다른 문장으로 바꾸면 그 문장의 통과/차단 여부를 확인할 수 있습니다."
    ),
)

# 라벨 부분(✅/⛔ 접두사)을 제거하고 실제 문장만 추출.
example_text = selected.split(" — ", 1)[-1] if " — " in selected else selected

user_input = st.text_area(
    "여기에 문장이 들어갑니다 — 자유롭게 수정하거나 새 문장을 써보세요",
    value=example_text,
    height=90,
    key="guardrail_demo_input",
)

if user_input.strip():
    if is_safe_output(user_input):
        st.success(
            "✅ **통과** — 이 문장은 사용자 화면에 노출됩니다. "
            "정책 표현 범위 안의 중립적 표현입니다."
        )
    else:
        hits = scan_forbidden(user_input)
        examples = []
        for h in hits[:3]:
            examples.append(f"「{h.matched_text}」 — {h.reason}")
        st.error(
            "⛔ **차단** — 이 문장은 사용자 화면에 노출되지 않습니다. "
            "다음 표현이 정책 위반으로 감지되었습니다:\n\n"
            + "\n".join(f"  - {e}" for e in examples)
            + "\n\n_시스템이 `UnsafeOutputError` 예외를 발생시켜 화면 출력 전에 자동 차단합니다._"
        )

st.caption(
    "현재 24개 금지 표현 패턴이 등록되어 있습니다. 자세한 목록은 "
    "[정책 01 §2 출력 표현 지침](https://github.com/dailyweekly/fair-energy/blob/main/docs/policies/01_output_language_policy.md)에서 확인 가능합니다."
)


# ---------------------------------------------------------------------------
# §5. 정책 8종
# ---------------------------------------------------------------------------

st.markdown("## ⑤ 정책 문서 — 코드로 강제되는 8가지 규칙")
st.caption(
    "본 서비스는 코드 안에 8개의 정책 문서를 두고, 각 정책을 코드와 테스트로 강제합니다. "
    "정책이 흔들리면 코드가 작동하지 않게 설계되어 있습니다."
)

policies = [
    ("00", "서비스 범위", "무엇을 하고 무엇을 안 하는지", "00_service_scope_policy.md"),
    ("01", "출력 표현", "위반·환급 등 금지 표현 24종", "01_output_language_policy.md"),
    ("02", "계산 게이트", "자료가 충분할 때만 계산하기", "02_calculation_gate_policy.md"),
    ("03", "요금 엔진", "AI가 아닌 룰 엔진으로 계산", "03_tariff_engine_policy.md"),
    ("04", "개인정보·보관", "원본 암호화·보관기간 선택", "04_privacy_retention_policy.md"),
    ("05", "사용자 안전", "보복 위험 사용자 보호 4단계", "05_user_safety_policy.md"),
    ("06", "PoC 측정", "성과 측정 지표 (KPI 계층)", "06_poc_metrics_policy.md"),
    ("07", "출시 통제", "외부 자문 후 베타 시작", "07_release_control_policy.md"),
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
                    <div style="font-size:11px;color:#8B95A1;letter-spacing:0.5px;margin-bottom:4px;">
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
                        GitHub에서 전문 보기 →
                    </a>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# §6. 두 여정 시각화
# ---------------------------------------------------------------------------

st.markdown("## ⑥ 두 가지 사용 흐름")

journey_cols = st.columns(2)
with journey_cols[0]:
    st.markdown(
        """
        <div style="background:white;border-radius:12px;padding:20px;
                    border:1px solid #E5E8EB;height:100%;">
            <div style="font-size:15px;font-weight:700;color:#191F28;margin-bottom:10px;">
                🧑‍💼 실제 임차인 사용 흐름
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.85;">
                ① 시작·동의·안전 확인<br>
                ② 자료 5종 업로드<br>
                ③ AI 추출값 직접 확인<br>
                ④ 자료 충분도 점수 확인<br>
                ⑤ 결과 분류 확인<br>
                ⑥ (필요 시) 임대인에게 보낼 메시지 예시<br>
                ⑦ 자료 요약본 PDF 다운로드
            </div>
            <div style="margin-top:14px;font-size:12px;color:#8B95A1;
                        padding-top:12px;border-top:1px solid #F2F4F6;">
                소요: 약 5~10분 · 본인 자료 필요
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with journey_cols[1]:
    st.markdown(
        """
        <div style="background:#F0F6FF;border-radius:12px;padding:20px;
                    border:1px solid #C6DAF8;height:100%;">
            <div style="font-size:15px;font-weight:700;color:#1B64DA;margin-bottom:10px;">
                🎬 심사관·자문 둘러보기 흐름 (지금 페이지)
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.85;">
                ① 어떤 문제를 푸나요?<br>
                ② 어떻게 작동하나요? (Input·처리·Output)<br>
                ③ 실제 결과 미리보기<br>
                ④ 표현 안전장치 체험<br>
                ⑤ 정책 8종 확인<br>
                ⑥ 두 사용 흐름 비교<br>
                ⑦ GitHub repo·정책 문서 검토
            </div>
            <div style="margin-top:14px;font-size:12px;color:#1B64DA;
                        padding-top:12px;border-top:1px solid #C6DAF8;">
                소요: 약 5분 · 예시 데이터 자동 제공
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# §7. 외부 자료 + 한계
# ---------------------------------------------------------------------------

st.markdown("## ⑦ 추가 확인")

ext_cols = st.columns(2)
with ext_cols[0]:
    st.link_button(
        "📂 GitHub 저장소 — 코드·정책 전문",
        "https://github.com/dailyweekly/fair-energy",
        use_container_width=True,
    )
with ext_cols[1]:
    st.link_button(
        "📊 KPI 대시보드 (운영자 전용)",
        "/10_KPI_대시보드",
        use_container_width=True,
    )

st.markdown(
    """
    <div style="margin-top:24px;padding:16px 20px;background:#FAFBFC;border-radius:12px;
                font-size:12px;color:#8B95A1;line-height:1.7;">
        <b>본 환경의 한계 사항</b><br>
        본 페이지는 외부 자문(2026-05-13 추정 의견) 기반의 시연용 데모입니다.
        화우 ESG센터(법률)·한전 전기요금 전문가·개인정보 외부 검토·주거 NGO 4그룹의
        실제 자문 결과 수령 후 표현·기능이 일부 조정될 수 있습니다.
        자세한 한계 사항은
        <a href="https://github.com/dailyweekly/fair-energy/blob/main/docs/policies/07_release_control_policy.md" target="_blank"
           style="color:#3182F6;text-decoration:none;font-weight:600;">정책 07 §8</a>
        참조.
    </div>
    """,
    unsafe_allow_html=True,
)
