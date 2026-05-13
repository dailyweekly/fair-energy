"""동의 처리 — 정책 04 §3.

각 동의 항목은 묶음 동의가 아니라 별도 체크박스로 수집되어야 한다.
서비스 이용·개인정보 수집·AI 처리·보관기간은 필수, NGO 공유와 외부 제출은 선택.
외부 제출은 건별·기관별 별도 동의가 필요하므로 본 모듈에서 별도 함수로 분리한다.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import db


class ConsentValidationError(ValueError):
    """필수 동의가 누락되었거나 값이 허용 범위를 벗어났을 때."""


VALID_STORAGE_MONTHS = (6, 12, 36)


@dataclass(frozen=True)
class ConsentRequest:
    """UI에서 받은 동의 입력."""

    consent_service: bool
    consent_personal_info: bool
    consent_ai_processing: bool
    consent_storage_months: int
    consent_ngo_share: bool = False


def _validate(request: ConsentRequest) -> None:
    if not request.consent_service:
        raise ConsentValidationError("서비스 이용 동의가 필요합니다.")
    if not request.consent_personal_info:
        raise ConsentValidationError("개인정보 수집·이용 동의가 필요합니다.")
    if not request.consent_ai_processing:
        raise ConsentValidationError(
            "AI 외부 API 처리 동의가 필요합니다. 동의하지 않는 경우 수동 입력 모드를 이용해주세요."
        )
    if request.consent_storage_months not in VALID_STORAGE_MONTHS:
        raise ConsentValidationError(
            f"보관기간은 {VALID_STORAGE_MONTHS} 중 하나여야 합니다."
        )


def record_consent(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    request: ConsentRequest,
) -> str:
    """동의 한 건을 audit_trail 가능한 형태로 저장하고 consent_id 반환."""
    _validate(request)
    return db.insert_consent(
        conn,
        user_id=user_id,
        consent_service=request.consent_service,
        consent_personal_info=request.consent_personal_info,
        consent_ai_processing=request.consent_ai_processing,
        consent_storage_months=request.consent_storage_months,
        consent_ngo_share=request.consent_ngo_share,
    )


@dataclass(frozen=True)
class ExternalSubmissionRequest:
    """외부 제출 건별 동의 입력 (정책 04 §7)."""

    target_organization: str       # 예: "주택임대차분쟁조정위"
    document_scope: tuple[str, ...]  # 제출할 document_id 목록
    purpose: str                   # 제출 목적


def record_external_submission_consent(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    request: ExternalSubmissionRequest,
    consent_storage_months: int,
) -> str:
    """외부 제출은 기관·문서·목적을 명시한 별도 동의로 기록한다."""
    if not request.target_organization.strip():
        raise ConsentValidationError("제출 대상 기관을 입력해야 합니다.")
    if not request.document_scope:
        raise ConsentValidationError("제출 대상 문서를 1건 이상 지정해야 합니다.")
    if not request.purpose.strip():
        raise ConsentValidationError("제출 목적을 입력해야 합니다.")

    external_target = json.dumps(
        {
            "organization": request.target_organization,
            "documents": list(request.document_scope),
            "purpose": request.purpose,
        },
        ensure_ascii=False,
    )

    consent_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO consents (
                consent_id, user_id,
                consent_service, consent_personal_info, consent_ai_processing,
                consent_storage_months, consent_ngo_share, consent_external_submission,
                external_target, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                consent_id, user_id,
                1, 1, 1, consent_storage_months, 0, 1,
                external_target, db.utcnow_iso(),
            ),
        )
    return consent_id


# ---------------------------------------------------------------------------
# 보관기간 계산 — storage 모듈이 사용
# ---------------------------------------------------------------------------


def retention_deadline(
    months: int,
    *,
    now: Optional[datetime] = None,
) -> datetime:
    if months not in VALID_STORAGE_MONTHS:
        raise ConsentValidationError("보관기간은 6, 12, 36개월 중 하나여야 합니다.")
    base = now or datetime.now(timezone.utc)
    return base + timedelta(days=30 * months)


def is_expiring_soon(
    deadline: datetime,
    *,
    now: Optional[datetime] = None,
    warning_days: int = 30,
) -> bool:
    """만료 30일 전 알림용 (정책 04 §6)."""
    current = now or datetime.now(timezone.utc)
    return 0 < (deadline - current).total_seconds() <= warning_days * 86400


def latest_consent(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM consents WHERE user_id = ? AND consent_external_submission = 0 "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
