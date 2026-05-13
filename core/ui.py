"""토스 스타일 UI 컴포넌트 (Streamlit Cloud 호환).

- 좌측 사이드바 숨김
- 상단 헤더 카드 + 진행 도트
- 페이지 직접 이동 버튼 (expander 내부)
- 토스 컬러 팔레트 + 둥근 카드 + 부드러운 그림자
"""

from __future__ import annotations

from typing import Optional

import streamlit as st


# ---------------------------------------------------------------------------
# 페이지 메타 — 진행 도트·이동 버튼에서 공유
# ---------------------------------------------------------------------------

PAGE_MAP: list[tuple[int, str, str, str]] = [
    # (번호, 라벨, 경로, 아이콘)
    (1, "시작", "pages/1_시작하기.py", "🚀"),
    (2, "동의·안전", "pages/2_동의_및_안전체크.py", "🛡️"),
    (3, "업로드", "pages/3_문서업로드.py", "📤"),
    (4, "확인", "pages/4_추출값확인.py", "✅"),
    (5, "점수", "pages/5_자료완결성점수.py", "📊"),
    (6, "분류", "pages/6_검산결과.py", "🎯"),
    (7, "메시지", "pages/7_자료확인메시지예시.py", "💬"),
    (8, "요약본", "pages/8_자료요약본.py", "📄"),
]


# ---------------------------------------------------------------------------
# CSS — 토스 스타일
# ---------------------------------------------------------------------------

TOSS_THEME_CSS = """
<style>
/* 폰트 — Pretendard 우선, 시스템 sans-serif 폴백 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

html, body, [class*="css"] {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont,
                 'Apple SD Gothic Neo', sans-serif !important;
    color: #191F28 !important;
    letter-spacing: -0.01em;
}

.stApp {
    background-color: #F9FAFB !important;
}

/* 사이드바·햄버거 메뉴 숨김 */
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="collapsedControl"],
section[data-testid="stSidebarUserContent"] {
    display: none !important;
}

/* Streamlit 상단 헤더 — 깔끔히 */
header[data-testid="stHeader"] {
    background-color: transparent !important;
    height: 0 !important;
}

/* 메인 콘텐츠 — 가운데 정렬, 최대 폭 */
.main .block-container {
    max-width: 880px !important;
    padding-top: 32px !important;
    padding-bottom: 80px !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
}

/* 제목 */
h1 {
    font-size: 28px !important;
    font-weight: 700 !important;
    color: #191F28 !important;
    letter-spacing: -0.02em !important;
    margin-top: 8px !important;
}
h2 {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #191F28 !important;
    margin-top: 32px !important;
}
h3 {
    font-size: 18px !important;
    font-weight: 600 !important;
    color: #191F28 !important;
    margin-top: 24px !important;
}

/* 기본 텍스트 */
p, div[data-testid="stMarkdownContainer"] {
    color: #4E5968;
    font-size: 15px;
    line-height: 1.65;
}

.stCaption, [data-testid="stCaptionContainer"] {
    color: #8B95A1 !important;
    font-size: 13px !important;
}

/* 카드 컨테이너 — st.container(border=True) */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: white !important;
    border-radius: 16px !important;
    padding: 24px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    border: 1px solid #E5E8EB !important;
    margin-bottom: 12px !important;
}

/* 버튼 — 토스 블루 */
.stButton > button {
    border-radius: 12px !important;
    padding: 12px 20px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    border: none !important;
    transition: all 0.15s ease !important;
    height: auto !important;
    min-height: 44px !important;
}

.stButton > button[kind="primary"] {
    background-color: #3182F6 !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #1B64DA !important;
    transform: translateY(-1px);
}

.stButton > button[kind="secondary"] {
    background-color: #F2F4F6 !important;
    color: #191F28 !important;
    border: 1px solid #E5E8EB !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: #E5E8EB !important;
}

/* 폼 입력 */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stDateInput input,
.stSelectbox > div > div {
    border-radius: 12px !important;
    border: 1px solid #E5E8EB !important;
    padding: 14px 16px !important;
    font-size: 15px !important;
    background-color: white !important;
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border-color: #3182F6 !important;
    box-shadow: 0 0 0 3px rgba(49, 130, 246, 0.12) !important;
    outline: none !important;
}

/* 메트릭 카드 */
[data-testid="stMetric"] {
    background: white;
    border-radius: 12px;
    padding: 18px;
    border: 1px solid #E5E8EB;
}
[data-testid="stMetricLabel"] {
    color: #6B7684 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    color: #191F28 !important;
    font-size: 26px !important;
    font-weight: 700 !important;
}

/* 알림 박스 */
.stAlert {
    border-radius: 12px !important;
    border: none !important;
    padding: 16px 20px !important;
}
[data-baseweb="notification"][kind="info"] {
    background-color: #F0F6FF !important;
    color: #1B64DA !important;
}
[data-baseweb="notification"][kind="warning"] {
    background-color: #FFF7E5 !important;
    color: #B86E00 !important;
}
[data-baseweb="notification"][kind="error"] {
    background-color: #FFE8EC !important;
    color: #D63F4A !important;
}
[data-baseweb="notification"][kind="success"] {
    background-color: #E8F8EE !important;
    color: #2D9A4B !important;
}

/* 진행 바 */
.stProgress > div > div {
    background-color: #3182F6 !important;
    border-radius: 4px !important;
}
.stProgress > div {
    background-color: #E5E8EB !important;
    border-radius: 4px !important;
}

/* 체크박스 */
.stCheckbox [data-baseweb="checkbox"] > div:first-child {
    border-radius: 6px !important;
}

/* 페이지 탭 버튼 (커스텀 nav) */
.nav-tabs-wrap {
    display: flex;
    gap: 4px;
    overflow-x: auto;
    padding: 4px 0;
    margin-bottom: 24px;
}

/* expander */
.streamlit-expanderHeader {
    background-color: white !important;
    border-radius: 12px !important;
    border: 1px solid #E5E8EB !important;
    font-weight: 600 !important;
}

/* 사이드바 햄버거 메뉴(우상단 ⋮) */
button[kind="header"] {
    display: none !important;
}

/* 데모 배너 */
.demo-banner {
    background: linear-gradient(135deg, #FFE57F 0%, #FFCA28 100%);
    color: #5D4037;
    padding: 10px 16px;
    border-radius: 10px;
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 16px;
    text-align: center;
}
</style>
"""


# ---------------------------------------------------------------------------
# 컴포넌트
# ---------------------------------------------------------------------------


def inject_theme() -> None:
    """페이지 진입 시 한 번 호출 — 토스 스타일 CSS 주입."""
    st.markdown(TOSS_THEME_CSS, unsafe_allow_html=True)


def _progress_dots_html(current: int, total: int = 8) -> str:
    dots = []
    for i in range(1, total + 1):
        active = i <= current
        color = "#3182F6" if active else "#E5E8EB"
        dots.append(
            f'<span style="display:inline-block;width:8px;height:8px;'
            f'border-radius:50%;background:{color};margin:0 3px;"></span>'
        )
    return "".join(dots)


def render_header(
    *, current_page_num: int, demo_mode: bool = False,
) -> None:
    """페이지 최상단 상단 헤더 카드.

    - 좌측: 공정에너지 로고 + 부제
    - 우측: 진행 도트 + 현재 번호
    - 데모 모드 배너 (해당 시)
    """
    if demo_mode:
        st.markdown(
            '<div class="demo-banner">'
            "🎬 데모 모드 — 시연용 자동 데이터입니다. 실제 사용자 데이터가 아닙니다."
            "</div>",
            unsafe_allow_html=True,
        )

    dots = _progress_dots_html(current_page_num)
    st.markdown(
        f"""
        <div style="background:white;border-radius:16px;padding:20px 24px;
                    margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                    border:1px solid #E5E8EB;">
            <div style="display:flex;align-items:center;justify-content:space-between;
                        flex-wrap:wrap;gap:16px;">
                <div>
                    <div style="font-size:22px;font-weight:700;color:#191F28;
                                letter-spacing:-0.02em;">
                        ⚡ 공정에너지
                    </div>
                    <div style="font-size:13px;color:#6B7684;margin-top:4px;">
                        Energy Bill Passport · 임차인 전기요금 검산 가능성 진단
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:12px;color:#8B95A1;margin-bottom:6px;">
                        진행 {current_page_num} / 8
                    </div>
                    <div>{dots}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_jumper(current_page_num: int) -> None:
    """페이지 직접 이동 expander — 데모·시연 시 자유 진입용."""
    with st.expander("📋 다른 페이지로 이동", expanded=False):
        # 2행 x 4열 배치.
        for row in range(2):
            cols = st.columns(4)
            for col_idx, col in enumerate(cols):
                idx = row * 4 + col_idx
                if idx >= len(PAGE_MAP):
                    continue
                page_num, label, target, icon = PAGE_MAP[idx]
                is_current = (page_num == current_page_num)
                with col:
                    if st.button(
                        f"{icon} {page_num}. {label}",
                        key=f"jump_{page_num}",
                        use_container_width=True,
                        type="primary" if is_current else "secondary",
                        disabled=is_current,
                    ):
                        st.switch_page(target)


def render_footer_nav(
    *,
    current_page_num: int,
    show_prev: bool = True,
    show_next: bool = True,
    next_label: Optional[str] = None,
    next_disabled: bool = False,
) -> None:
    """페이지 하단 이전/다음 네비게이션."""
    st.markdown("<div style='margin-top:32px;'></div>", unsafe_allow_html=True)
    cols = st.columns([1, 1])

    # 이전.
    prev_num = current_page_num - 1
    if show_prev and prev_num >= 1:
        prev_meta = next(
            (m for m in PAGE_MAP if m[0] == prev_num), None,
        )
        if prev_meta:
            with cols[0]:
                if st.button(
                    f"← {prev_meta[1]}",
                    key=f"prev_{current_page_num}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.switch_page(prev_meta[2])
    else:
        cols[0].empty()

    # 다음.
    next_num = current_page_num + 1
    if show_next and next_num <= len(PAGE_MAP):
        next_meta = next(
            (m for m in PAGE_MAP if m[0] == next_num), None,
        )
        if next_meta:
            label = next_label or f"{next_meta[1]} →"
            with cols[1]:
                if st.button(
                    label,
                    key=f"next_{current_page_num}",
                    use_container_width=True,
                    type="primary",
                    disabled=next_disabled,
                ):
                    st.switch_page(next_meta[2])
    else:
        cols[1].empty()


def render_chrome(current_page_num: int, *, demo_mode: bool = False) -> None:
    """페이지 진입 시 한 번 호출 — 테마 + 헤더 + 페이지 점퍼."""
    inject_theme()
    render_header(current_page_num=current_page_num, demo_mode=demo_mode)
    render_page_jumper(current_page_num=current_page_num)
