"""3b. 수동 입력 모드 (외부 LLM 미사용 경로).

2026-05-13 외부 자문 반영 — AI OCR 처리에 동의하지 않는 사용자가
사용량·청구액·검침기간 등을 직접 입력해 자료 완결성 점수와 예비 검산까지
도달할 수 있도록 한다. 외부 LLM API에 원본이 송신되지 않는다.

생성되는 문서는 `documents.original_path=NULL`이며, 모든 필드는
`user_confirmed=True`로 저장된다(사용자가 직접 타이핑했으므로).
"""

from __future__ import annotations

import streamlit as st

from core import extraction
from core.models import DocumentType


st.set_page_config(page_title="수동 입력 · 공정에너지", page_icon="⚡")
st.title("3b. 수동 입력 모드")


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


# ---------------------------------------------------------------------------
# 안내
# ---------------------------------------------------------------------------

st.markdown(
    """
**외부 LLM에 원본을 보내지 않는 경로입니다.**

AI OCR 처리에 동의하지 않으셨거나, 고지서·계약서를 외부 API에 업로드하는 것이
부담스러우신 경우 이 페이지에서 **사용량·청구액·검침기간 등을 직접 입력**할 수 있습니다.

직접 입력한 값은 자료 완결성 점수와 검산 가능성 분류에 그대로 사용되며,
외부 API(Anthropic·OpenAI)에 송신되지 않습니다.
"""
)


# ---------------------------------------------------------------------------
# 입력 폼
# ---------------------------------------------------------------------------

from app import conn  # type: ignore[attr-defined]

user_id = st.session_state["user_id"]

st.markdown("---")
st.subheader("전기요금 정보")

with st.form("manual_electricity"):
    usage_kwh = st.number_input(
        "사용량 (kWh)",
        min_value=0.0, step=1.0, format="%.1f",
        help="고지서에 기재된 당월 사용량을 입력하세요.",
    )

    col_start, col_end = st.columns(2)
    billing_start = col_start.date_input(
        "검침 시작일",
        value=None,
        help="고지서에 기재된 검침 시작일.",
    )
    billing_end = col_end.date_input(
        "검침 종료일",
        value=None,
        help="고지서에 기재된 검침 종료일.",
    )

    contract_type = st.selectbox(
        "계약종별",
        options=["주택용 저압", "주택용 고압", "일반용", "기타/확실하지 않음"],
        help="고지서의 「계약종별」 또는 「요금적용전력」 항목 확인.",
    )

    total_amount = st.number_input(
        "사용자에게 청구된 금액 (원)",
        min_value=0, step=100, format="%d",
        help="임대인 또는 한전이 실제로 청구한 금액.",
    )

    allocation = st.text_input(
        "세대별 배분 산식 (선택)",
        placeholder="예: 사용량 기반 / 면적 기반 / 미기재",
        help="임대인이 안내한 배분 방식. 모르면 「미기재」.",
    )

    st.markdown("---")
    submitted = st.form_submit_button("저장", type="primary")

if submitted:
    if usage_kwh <= 0 or total_amount <= 0 or billing_start is None or billing_end is None:
        st.error(
            "사용량·검침기간·청구금액은 필수 입력값입니다. "
            "확실하지 않으면 비워두지 말고 고지서를 다시 확인해주세요."
        )
    elif billing_start >= billing_end:
        st.error("검침 시작일이 종료일보다 이후일 수 없습니다.")
    else:
        fields = {
            "usage_kwh": str(usage_kwh),
            "billing_start_date": billing_start.isoformat(),
            "billing_end_date": billing_end.isoformat(),
            "contract_type": contract_type,
            "total_amount": str(total_amount),
        }
        if allocation.strip():
            fields["allocation_method"] = allocation.strip()

        document_id, inserted_ids = extraction.create_manual_document(
            conn,
            user_id=user_id,
            document_type=DocumentType.ELECTRICITY_BILL.value,
            fields=fields,
            field_labels={
                "usage_kwh": "사용량",
                "billing_start_date": "검침 시작일",
                "billing_end_date": "검침 종료일",
                "contract_type": "계약종별",
                "total_amount": "청구액",
                "allocation_method": "세대별 배분 산식",
            },
            field_units={
                "usage_kwh": "kWh",
                "total_amount": "KRW",
            },
        )

        from core import metrics

        metrics.log_event(
            conn,
            event_name=metrics.EVENT_MANUAL_INPUT_USED,
            user_id=user_id,
            metadata={
                "field_count": len(inserted_ids),
                "document_type": DocumentType.ELECTRICITY_BILL.value,
            },
        )

        st.success(
            f"수동 입력 자료가 저장되었습니다. "
            f"({len(inserted_ids)}개 필드, document_id: `{document_id[:8]}…`)"
        )
        st.markdown(
            "직접 입력한 값은 이미 「확인 완료」 상태로 저장되어, "
            "이후 점수 산정·분류·검산에 바로 사용됩니다."
        )
        st.page_link("pages/5_자료완결성점수.py", label="자료 완결성 점수 페이지로 →")


st.markdown("---")
st.caption(
    "본 페이지에서 입력한 값은 외부 API(Anthropic·OpenAI)에 송신되지 않습니다. "
    "원본 고지서·계약서를 업로드하고 싶으시면 「3. 문서 업로드」 페이지를 이용해주세요."
)
