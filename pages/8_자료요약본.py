"""8. 자료 요약본 PDF 다운로드 (Phase 9 — 2026-05-13 외부 자문 반영).

명칭은 「에너지 청구 자료 요약본」 — 외부 자문 권고에 따라 「증거 패키지」 표현은 사용하지 않는다.
PDF에는 사용자가 직접 확인한 필드만 포함되며, 원본 시각 정보는 들어가지 않는다.
"""

from __future__ import annotations

import streamlit as st

from core import demo, metrics, redaction, summary_pack, ui
from core.auth import require_password


require_password()

st.set_page_config(
    page_title="자료 요약본 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=8, demo_mode=demo.is_demo_mode())

st.title("8. 자료 요약본")


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


from app import app_config, conn  # type: ignore[attr-defined]

user_id = st.session_state["user_id"]


# ---------------------------------------------------------------------------
# 안내
# ---------------------------------------------------------------------------

st.markdown(
    """
**본 PDF는 사용자 보관용 「자료 요약본」입니다.**

- 사용자가 직접 확인한 필드만 포함됩니다.
- 원본 이미지·서명·도장·임대인 정보 등 시각 정보는 포함되지 않습니다.
- 분쟁용 문서가 아닌 본인 보관용입니다.
- 외부 기관에 제출이 필요한 경우 별도 동의 절차가 적용됩니다.
"""
)


# ---------------------------------------------------------------------------
# 마스킹본 사전 점검
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("마스킹본 동기화")

if st.button("마스킹본 일괄 재생성"):
    count = redaction.regenerate_all_masked_views(
        conn, user_id=user_id, masked_dir=app_config.masked_dir,
    )
    if count:
        st.success(f"{count}건의 문서 마스킹본을 갱신했습니다.")
    else:
        st.info("재생성 가능한 마스킹본이 없습니다.")


# ---------------------------------------------------------------------------
# PDF 생성·다운로드
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("자료 요약본 PDF 다운로드")

if "summary_pdf_bytes" not in st.session_state:
    st.session_state["summary_pdf_bytes"] = None

if st.button("PDF 생성", type="primary"):
    try:
        pdf_bytes = summary_pack.build_summary_pdf(conn, user_id=user_id)
        st.session_state["summary_pdf_bytes"] = pdf_bytes
        st.success(f"PDF가 생성되었습니다. 크기: {len(pdf_bytes):,} bytes")
    except Exception as exc:  # pragma: no cover — UI 폴백
        st.error(f"PDF 생성 실패: {exc}")
        st.session_state["summary_pdf_bytes"] = None

if st.session_state["summary_pdf_bytes"]:
    pdf_bytes: bytes = st.session_state["summary_pdf_bytes"]
    filename = summary_pack.suggested_filename(user_id)
    downloaded = st.download_button(
        label="📄 PDF 다운로드",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
    )
    if downloaded:
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_SUMMARY_PDF_DOWNLOADED,
            user_id=user_id,
            metadata={"file_size": len(pdf_bytes)},
        )


# ---------------------------------------------------------------------------
# 한계 사항 명시
# ---------------------------------------------------------------------------

st.markdown("---")
with st.expander("⚠ 본 PDF의 한계 사항", expanded=False):
    st.markdown(
        """
- 본 PDF는 **사용자 보관용 자료 요약본**입니다. 분쟁용 문서가 아닙니다.
- 본 PDF에는 사용자가 직접 확인한 필드만 들어갑니다 — 원본 이미지·source_text(원문 인용)는 포함되지 않습니다.
- 임대인의 위법성 여부·환급 가능성·분쟁 결과는 판단하지 않습니다.
- 외부 기관 제출이 필요한 경우, 기관·문서·목적별 **별도 동의 절차**가 적용됩니다 (정책 04 §7).
- 본 PDF의 표현 범위는 외부 자문(2026-05-13) 추정 의견 기반이며, 화우 ESG센터의 사전 검토 의견서 수령 후 조정될 수 있습니다.
"""
    )

st.caption(
    "본 페이지는 베타 PoC 단계의 기능입니다. "
    "PoC 외부 배포 시에는 G3(마스킹 정확도 200건 라벨링)·G5(화우 의견서) 게이트 통과 후 활성화됩니다."
)
