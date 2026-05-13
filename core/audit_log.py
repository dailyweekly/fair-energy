"""접근 로그(audit log) 모듈.

정책 04 §10에 따라 누가·언제·어떤 객체에 접근했는지 기록한다.
원본 접근(`object_type='original'`)은 사용자 본인 재동의(consent_basis) 없이는
호출되면 안 된다 — 호출 측에서 검증한다.
"""

from __future__ import annotations

import sqlite3
from typing import Literal, Optional

from . import db


Action = Literal[
    "upload", "view", "download", "delete", "export",
    "confirm_field", "calculate", "classify", "event",
]
ObjectType = Literal["original", "masked", "score", "calc", "event", "user", "document"]


class ConsentRequiredError(PermissionError):
    """원본 접근 시 consent_basis가 누락되었을 때."""


def log_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: Action,
    object_id: Optional[str] = None,
    object_type: Optional[ObjectType] = None,
    consent_basis: Optional[str] = None,
) -> str:
    """접근 기록 한 줄을 audit_logs에 INSERT 한다.

    원본(`object_type='original'`)을 다룰 때는 `consent_basis`가 반드시 있어야 한다.
    """
    if object_type == "original" and not consent_basis:
        raise ConsentRequiredError(
            "Access to 'original' requires consent_basis (consent_id)."
        )

    log_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO audit_logs (
                log_id, timestamp, actor, action,
                object_id, object_type, consent_basis
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id, db.utcnow_iso(), actor, action,
                object_id, object_type, consent_basis,
            ),
        )
    return log_id


def recent_logs(
    conn: sqlite3.Connection,
    *,
    actor: Optional[str] = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """간단 조회 헬퍼 — 관리자용 진단에서 사용."""
    if actor is not None:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE actor = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (actor, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return list(rows)
