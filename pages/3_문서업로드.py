"""3. 문서 업로드 — 5종 슬롯.

업로드되는 모든 파일은 Fernet 암호화되어 originals/에 저장된다(정책 04 §1·§5).
사용자가 AI OCR 처리에 동의하지 않은 경우 수동 입력 모드 안내만 표시한다.
"""

from __future__ import annotations

import streamlit as st

from core import demo, storage, ui
from core.auth import require_password
from core.models import DocumentType


require_password()

st.set_page_config(
    page_title="문서 업로드 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=3, demo_mode=demo.is_demo_mode())

st.title("3. 문서 업로드")


# ---------------------------------------------------------------------------
# 가드: 동의·안전 체크 완료 여부
# ---------------------------------------------------------------------------

if not st.session_state.get("consent_id"):
    st.warning("먼저 동의를 완료해주세요.")
    st.page_link("pages/2_동의_및_안전체크.py", label="← 동의 및 안전 체크")
    st.stop()


# ---------------------------------------------------------------------------
# 스토리지 초기화 (지연 로딩)
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


SLOT_DEFINITIONS = [
    (DocumentType.LEASE_CONTRACT, "임대차계약서",
     "임대인·임차인 정보와 관리비 조항 확인용", ["pdf", "png", "jpg", "jpeg", "docx"]),
    (DocumentType.MANAGEMENT_FEE_NOTICE, "관리비/전기료 청구 내역",
     "임대인이 매월 청구한 내역", ["pdf", "png", "jpg", "jpeg"]),
    (DocumentType.ELECTRICITY_BILL, "한전 고지서 또는 임대인 제공 원고지서",
     "공식 산식 비교에 사용", ["pdf", "png", "jpg", "jpeg"]),
    (DocumentType.METER_PHOTO, "계량기 사진 (검침일 포함)",
     "사용량 확인용", ["png", "jpg", "jpeg"]),
    (DocumentType.PAYMENT_PROOF, "납부내역·계좌이체 기록",
     "실제 청구·납부 금액 확인", ["pdf", "png", "jpg", "jpeg"]),
]


# 동의된 보관기간을 DB에서 조회.
@st.cache_data(ttl=30)
def _resolve_retention_months(consent_id: str) -> int:
    from app import conn  # type: ignore[attr-defined]

    row = conn.execute(
        "SELECT consent_storage_months FROM consents WHERE consent_id = ?",
        (consent_id,),
    ).fetchone()
    return int(row["consent_storage_months"]) if row else 6


retention_months = _resolve_retention_months(st.session_state["consent_id"])
st.caption(
    f"선택한 보관기간: **{retention_months}개월** "
    "· 만료일 도래 시 원본은 자동 파기됩니다."
)

st.markdown("---")
st.markdown(
    "각 슬롯에 해당 자료를 업로드하세요. 모든 파일은 업로드 즉시 암호화되어 저장됩니다. "
    "민감정보는 표시용 사본에서 마스킹됩니다."
)


# ---------------------------------------------------------------------------
# 5종 업로드 슬롯
# ---------------------------------------------------------------------------

uploaded_ids: list[str] = []

for doc_type, label, hint, exts in SLOT_DEFINITIONS:
    with st.container(border=True):
        st.markdown(f"**{label}**  ·  {hint}")
        uploaded = st.file_uploader(
            label,
            type=exts,
            key=f"upload_{doc_type.value}",
            label_visibility="collapsed",
        )
        if uploaded is not None:
            payload = uploaded.read()
            if len(payload) == 0:
                st.error("파일이 비어 있습니다.")
                continue

            try:
                from app import conn  # type: ignore[attr-defined]
                from core import metrics, storage as _storage_mod

                store = _get_storage()
                stored = store.save_document(
                    conn,
                    user_id=st.session_state["user_id"],
                    document_type=doc_type.value,
                    original_filename=uploaded.name,
                    original_bytes=payload,
                    retention_months=retention_months,
                )
                uploaded_ids.append(stored.document_id)
                metrics.log_event(
                    conn,
                    event_name=metrics.EVENT_DOCUMENT_UPLOADED,
                    user_id=st.session_state["user_id"],
                    metadata={
                        "document_type": doc_type.value,
                        "file_size": stored.size_bytes,
                    },
                )
                st.success(
                    f"저장 완료. document_id: `{stored.document_id[:8]}…` · "
                    f"크기: {stored.size_bytes:,} bytes"
                )
            except _storage_mod.RRNDetectedError as exc:
                metrics.log_event(
                    conn,
                    event_name=metrics.EVENT_DOCUMENT_REJECTED_RRN,
                    user_id=st.session_state["user_id"],
                    metadata={"document_type": doc_type.value},
                )
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover — UI 폴백
                st.error(f"업로드 실패: {exc}")


if uploaded_ids:
    st.session_state["uploaded_documents"].extend(uploaded_ids)
    st.markdown("---")
    st.info(
        "이번 세션에 업로드된 문서: "
        f"{len(st.session_state['uploaded_documents'])}건"
    )
    st.markdown(
        "다음 단계는 Phase 3(OCR 추출)부터 구현됩니다. "
        "현재 단계에서는 업로드와 암호화 저장까지만 동작합니다."
    )
