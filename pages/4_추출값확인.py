"""4. 추출값 확인.

AI가 추출한 필드를 사용자가 직접 검토·수정하고 「확인」 체크를 한다.
정책 02 §5 — user_confirmed=True가 된 필드만 이후 계산에 사용된다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import demo, extraction, storage, ui
from core.auth import require_password
from core.llm_client import get_llm_client


require_password()

st.set_page_config(
    page_title="추출값 확인 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=4, demo_mode=demo.is_demo_mode())

st.title("4. 추출값 확인")


# ---------------------------------------------------------------------------
# 가드
# ---------------------------------------------------------------------------

if not st.session_state.get("user_id"):
    st.warning("먼저 '시작하기' 페이지에서 시작해주세요.")
    st.page_link("pages/1_시작하기.py", label="← 시작하기")
    st.stop()

if not st.session_state.get("consent_id"):
    st.warning("동의가 필요합니다.")
    st.page_link("pages/2_동의_및_안전체크.py", label="← 동의 및 안전 체크")
    st.stop()


# ---------------------------------------------------------------------------
# 자원 캐시
# ---------------------------------------------------------------------------


@st.cache_resource
def _get_storage() -> storage.DocumentStorage:
    from app import app_config  # type: ignore[attr-defined]

    key = storage.load_or_generate_key(
        app_config.app_secret_key,
        allow_generate=app_config.demo_mode,
    )
    return storage.DocumentStorage(
        key=key,
        originals_dir=app_config.originals_dir,
        masked_dir=app_config.masked_dir,
    )


@st.cache_resource
def _get_llm():
    from app import app_config  # type: ignore[attr-defined]

    return get_llm_client(app_config)


# ---------------------------------------------------------------------------
# 미추출 문서 자동 처리
# ---------------------------------------------------------------------------

from app import conn  # type: ignore[attr-defined]

user_id = st.session_state["user_id"]

pending = extraction.find_documents_pending_extraction(conn, user_id=user_id)

if pending:
    with st.spinner(f"{len(pending)}건의 문서를 AI가 분석하고 있습니다..."):
        new_count = extraction.auto_extract_pending(
            conn,
            user_id=user_id,
            llm_client=_get_llm(),
            storage=_get_storage(),
        )
    if new_count:
        st.success(f"{new_count}건의 문서 분석이 완료되었습니다.")
        st.rerun()


# ---------------------------------------------------------------------------
# 결과 표시
# ---------------------------------------------------------------------------

docs = extraction.list_user_documents_with_fields(conn, user_id=user_id)

if not docs:
    st.info("업로드된 문서가 없습니다. 먼저 문서를 업로드해주세요.")
    st.page_link("pages/3_문서업로드.py", label="← 문서 업로드")
    st.stop()

st.markdown(
    "AI가 추출한 값을 검토하고, 정확하면 **확인** 체크박스를 눌러주세요.\n\n"
    "확인되지 않은 값은 이후 검산 단계에서 사용되지 않습니다 (정책 02 §5)."
)

status = extraction.confirmation_status(conn, user_id=user_id)
prog_col1, prog_col2, prog_col3 = st.columns(3)
prog_col1.metric("전체 필드", status["total"])
prog_col2.metric("확인 완료", status["confirmed"])
prog_col3.metric("저신뢰도 (수정 필요)", status["low_confidence"])

st.markdown("---")


for entry in docs:
    doc = entry["document"]
    fields = entry["fields"]

    with st.container(border=True):
        st.markdown(f"**{doc['original_filename']}**  ·  `{doc['document_type']}`")

        if not fields:
            st.warning("이 문서에서 추출된 필드가 없습니다. (문서 유형을 확인하거나 다시 업로드해주세요)")
            continue

        with st.form(f"doc_form_{doc['document_id']}"):
            new_values: dict[str, str] = {}
            confirm_flags: dict[str, bool] = {}

            for field in fields:
                col_value, col_meta, col_check = st.columns([3, 2, 1])

                with col_value:
                    label = field["label"] or field["key"]
                    if field["unit"]:
                        label += f" ({field['unit']})"
                    new_values[field["field_id"]] = st.text_input(
                        label,
                        value=field["value"] or "",
                        key=f"val_{field['field_id']}",
                    )
                    if field["source_text"]:
                        st.caption(f"원문: \"{field['source_text']}\"")

                with col_meta:
                    confidence = field["confidence"]
                    if confidence < 0.7:
                        st.markdown(f"🔴 **수정 필요**\n\n신뢰도 {confidence:.0%}")
                    elif confidence < 0.9:
                        st.markdown(f"🟡 검토 권장\n\n신뢰도 {confidence:.0%}")
                    else:
                        st.markdown(f"🟢 신뢰도 {confidence:.0%}")

                with col_check:
                    confirm_flags[field["field_id"]] = st.checkbox(
                        "확인",
                        value=bool(field["user_confirmed"]),
                        key=f"conf_{field['field_id']}",
                    )

            colA, colB = st.columns([1, 1])
            saved = colA.form_submit_button("저장 + 확인", type="primary")
            confirm_all = colB.form_submit_button("모두 확인 (검토 후)")

            if saved or confirm_all:
                # 1) 값 업데이트
                for fid, val in new_values.items():
                    extraction.update_field_value(conn, field_id=fid, value=val)

                # 2) 확인 플래그
                if confirm_all:
                    extraction.confirm_fields_bulk(
                        conn,
                        field_ids=[f["field_id"] for f in fields],
                        confirmed=True,
                    )
                else:
                    for fid, flag in confirm_flags.items():
                        extraction.confirm_field(
                            conn, field_id=fid, confirmed=flag
                        )

                st.success("저장되었습니다.")
                st.rerun()


# ---------------------------------------------------------------------------
# 다음 단계
# ---------------------------------------------------------------------------

st.markdown("---")
final = extraction.confirmation_status(conn, user_id=user_id)
if final["all_confirmed"]:
    st.success(
        "모든 필드가 확인되었습니다. 다음 단계(자료 완결성 점수)로 진행하세요."
    )
else:
    st.info(
        f"확인 진행도: {final['confirmed']} / {final['total']} · "
        "다음 단계는 모든 필드가 확인된 뒤 활성화됩니다."
    )

st.caption("Phase 5(자료 완결성 점수) 이후 페이지가 구현되면 자동으로 연결됩니다.")
