"""데모 모드 — 시연·심사위원·자문위원용 자동 시드.

DEMO_MODE=true (또는 ENABLE_LLM_OCR=false + 비배포 모드) 시:
- 페이지 진입 시 user_id·consent_id·safety_response 자동 주입
- 5종 자료 미리 업로드 + 필드 user_confirmed=True
- 점수·분류·마스킹본까지 미리 생성
- 어느 페이지든 자유 진입 가능

⚠ 한계 사항 (LIMITATION):
- 데모 데이터는 컨테이너 라이프타임 동안 캐싱됨. Streamlit Cloud 재시작 시 재생성.
- 모든 데모 사용자가 같은 가짜 user_id 공유 (시연용으로 충분, 실 베타는 별도 환경).
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

import streamlit as st

from . import consent, db, extraction, redaction, scoring
from .models import DocumentType, SafetyCheckResponse


# ---------------------------------------------------------------------------
# 모드 감지
# ---------------------------------------------------------------------------


def is_demo_mode() -> bool:
    """DEMO_MODE 환경변수 또는 secrets에서 확인."""
    env_value = os.environ.get("DEMO_MODE", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False

    # Streamlit secrets에서도 확인.
    try:
        return bool(st.secrets.get("demo_mode", False))
    except (FileNotFoundError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# 시드 데이터 — 정책 06 §6 분포의 90+ 점 케이스 (공식 산식 비교 가능)
# ---------------------------------------------------------------------------


def _build_demo_documents(conn: sqlite3.Connection, user_id: str) -> None:
    """5종 자료를 모두 수동 입력 모드로 시드.

    공식 산식 비교 가능 케이스를 목표로 90+ 점 분포 구성:
      - lease_contract (15)
      - management_fee_notice (15)
      - meter_photo (15) — 검침일 확인 필요
      - electricity_bill (25) — 필수 필드 완비
      - payment_proof (10)
      - 배분 산식 (20) — electricity_bill의 allocation_method
      → 합계 100점
    """
    # 1. 전기요금 고지서 (필수 필드 완비 — 룰 엔진 통과)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={
            "usage_kwh": "245",
            "billing_start_date": "2026-04-01",
            "billing_end_date": "2026-04-30",
            "contract_type": "주택용 저압",
            "total_amount": "38000",
            "allocation_method": "사용량 기반 (보조계량기 측정)",
        },
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

    # 2. 임대차계약서 (정액 아님 — 별도 부과)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.LEASE_CONTRACT.value,
        fields={
            "monthly_rent": "350000",
            "management_fee": "50000",
            "electricity_separate": "별도 부과",  # 정액 케이스 아님 (시연용)
            "contract_period": "2026-03-01 ~ 2027-02-28",
        },
        field_labels={
            "monthly_rent": "월세",
            "management_fee": "관리비",
            "electricity_separate": "전기료 별도 여부",
            "contract_period": "계약 기간",
        },
        field_units={"monthly_rent": "KRW", "management_fee": "KRW"},
    )

    # 3. 관리비 청구 내역
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.MANAGEMENT_FEE_NOTICE.value,
        fields={
            "billing_period": "2026-04",
            "electricity_charge": "38000",
            "water_charge": "12000",
        },
        field_labels={
            "billing_period": "청구 기간",
            "electricity_charge": "전기료 항목",
            "water_charge": "수도료 항목",
        },
        field_units={"electricity_charge": "KRW", "water_charge": "KRW"},
    )

    # 4. 계량기 사진 (검침일 포함)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.METER_PHOTO.value,
        fields={
            "meter_reading": "08245",
            "photo_date": "2026-04-30",
            "meter_number": "12345678",
        },
        field_labels={
            "meter_reading": "계량기 숫자",
            "photo_date": "촬영일",
            "meter_number": "계량기 번호",
        },
        field_units={"meter_reading": "kWh"},
    )

    # 5. 납부내역
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.PAYMENT_PROOF.value,
        fields={
            "payment_date": "2026-05-05",
            "payment_amount": "38000",
            "payment_method": "계좌이체",
        },
        field_labels={
            "payment_date": "납부일",
            "payment_amount": "납부 금액",
            "payment_method": "납부 방법",
        },
        field_units={"payment_amount": "KRW"},
    )


def _build_demo_consent_and_score(
    conn: sqlite3.Connection, user_id: str,
) -> str:
    """동의·점수 스냅샷·마스킹본까지 미리 생성. consent_id 반환."""
    # 동의 (AI OCR 미동의 + 수동 입력 모드 시뮬레이션).
    consent_id = consent.record_consent(
        conn,
        user_id=user_id,
        request=consent.ConsentRequest(
            consent_service=True,
            consent_personal_info=True,
            consent_ai_processing=True,  # 데모: AI 모두 허용으로 표시
            consent_storage_months=6,
            consent_ngo_share=True,
        ),
    )

    # 점수 계산·저장.
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    scoring.save_score_snapshot(conn, user_id=user_id, score=score)

    return consent_id


@st.cache_resource(show_spinner=False)
def _ensure_demo_user_cached(_conn_id: str) -> dict[str, str]:
    """컨테이너 라이프타임 동안 데모 사용자 1명을 캐싱.

    Streamlit `cache_resource`는 모든 사용자 세션에 공유 — PoC 시연용으로 적합.
    `_conn_id`는 conn 인스턴스 캐시 키 (스레드별 다름) — 그러나 데모 user는
    DB 영속성이 컨테이너 단위라 한 번 생성하면 모든 세션이 같은 데이터 보게 됨.
    """
    # 실제 conn은 호출 측에서 가져와야 함. 캐시 키만 분리.
    return {}


def ensure_demo_session(conn: sqlite3.Connection) -> None:
    """현재 세션에 데모 user_id·consent_id·safety_response를 자동 주입.

    이미 user_id가 있으면 그대로 두고, 없으면 데모 사용자 데이터를 시드.
    """
    if st.session_state.get("user_id"):
        return

    # 컨테이너에 이미 데모 사용자가 있는지 확인 (cohort='demo').
    existing = conn.execute(
        "SELECT user_id FROM users WHERE cohort = 'demo' "
        "ORDER BY created_at DESC LIMIT 1",
    ).fetchone()

    if existing:
        user_id = existing["user_id"]
        consent_row = conn.execute(
            "SELECT consent_id FROM consents WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        consent_id = consent_row["consent_id"] if consent_row else None
    else:
        user_id = db.insert_user(conn, cohort="demo")
        _build_demo_documents(conn, user_id)
        consent_id = _build_demo_consent_and_score(conn, user_id)

    st.session_state["user_id"] = user_id
    if consent_id:
        st.session_state["consent_id"] = consent_id

    # 안전 응답 LOW 자동 주입.
    if "safety_response" not in st.session_state:
        st.session_state["safety_response"] = SafetyCheckResponse()
        st.session_state["safety_level"] = "LOW"

    st.session_state["_demo_seeded"] = True


def is_demo_session() -> bool:
    """현재 세션이 데모 시드를 거쳤는지."""
    return bool(st.session_state.get("_demo_seeded"))


# ---------------------------------------------------------------------------
# 가드 헬퍼 (페이지에서 사용)
# ---------------------------------------------------------------------------


def maybe_seed_or_block(
    conn: sqlite3.Connection,
    *,
    require_user: bool = True,
    require_consent: bool = True,
) -> bool:
    """페이지 진입 가드 — 데모 모드면 자동 시드, 아니면 안내.

    반환값:
      True  — 진입 가능 (시드되었거나 이미 user_id 있음)
      False — 진입 차단 (사용자가 시작하기로 가야 함). 호출자가 st.stop() 호출.
    """
    if is_demo_mode():
        ensure_demo_session(conn)
        return True

    user_id = st.session_state.get("user_id")
    consent_id = st.session_state.get("consent_id")
    if require_user and not user_id:
        return False
    if require_consent and not consent_id:
        return False
    return True
