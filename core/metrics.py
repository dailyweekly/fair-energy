"""KPI 이벤트 로깅 + 지표 계산.

정책 06_poc_metrics_policy.md §4 표준 이벤트 명세 + §2-A 새 KPI 계층 구현.
events 테이블에 한 줄씩 기록되며, KPI 계산은 SQL 집계로 수행한다.

KPI 계층 (정책 06 §2-A, 2026-05-13 외부 자문 반영):
  1차 (주요) — 자료 완결성 점수 개선률
  2차       — 자료요청 메시지 예시 복사율
  3차       — 추가 자료 확보 후 재업로드율
  4차 (보조) — 임대인 답변 자가보고율
  5차 (보조) — 실제 정산 재확인 사례 수
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import db


# ---------------------------------------------------------------------------
# 표준 이벤트 이름 (정책 06 §4)
# ---------------------------------------------------------------------------

EVENT_USER_REGISTERED = "user_registered"
EVENT_CONSENT_COMPLETED = "consent_completed"
EVENT_SAFETY_CHECK_COMPLETED = "safety_check_completed"
EVENT_MANUAL_INPUT_USED = "manual_input_used"
EVENT_DOCUMENT_UPLOADED = "document_uploaded"
EVENT_DOCUMENT_REJECTED_RRN = "document_rejected_rrn"
EVENT_OCR_COMPLETED = "ocr_completed"
EVENT_FIELD_CONFIRMED = "field_confirmed"
EVENT_PASSPORT_CREATED = "passport_created"
EVENT_SCORE_CALCULATED = "score_calculated"
EVENT_CASE_CLASSIFIED = "case_classified"
EVENT_CALCULATION_COMPLETED = "calculation_completed"
EVENT_REQUEST_TEMPLATE_VIEWED = "request_template_viewed"
EVENT_REQUEST_TEMPLATE_COPIED = "request_template_copied"
EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED = "high_risk_template_copy_blocked"
EVENT_SUMMARY_PDF_DOWNLOADED = "summary_pdf_downloaded"
EVENT_USER_RETURNED_NEXT_MONTH = "user_returned_next_month"


ALL_EVENT_NAMES = (
    EVENT_USER_REGISTERED, EVENT_CONSENT_COMPLETED, EVENT_SAFETY_CHECK_COMPLETED,
    EVENT_MANUAL_INPUT_USED, EVENT_DOCUMENT_UPLOADED, EVENT_DOCUMENT_REJECTED_RRN,
    EVENT_OCR_COMPLETED, EVENT_FIELD_CONFIRMED, EVENT_PASSPORT_CREATED,
    EVENT_SCORE_CALCULATED, EVENT_CASE_CLASSIFIED, EVENT_CALCULATION_COMPLETED,
    EVENT_REQUEST_TEMPLATE_VIEWED, EVENT_REQUEST_TEMPLATE_COPIED,
    EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED, EVENT_SUMMARY_PDF_DOWNLOADED,
    EVENT_USER_RETURNED_NEXT_MONTH,
)


# ---------------------------------------------------------------------------
# 이벤트 로깅
# ---------------------------------------------------------------------------


def log_event(
    conn: sqlite3.Connection,
    *,
    event_name: str,
    user_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> str:
    """events 테이블에 한 줄을 기록하고 event_id를 반환.

    `timestamp`가 주어지면 그 값을 사용(테스트용). 미지정 시 현재 UTC.
    `metadata`는 JSON으로 직렬화된다.
    """
    if event_name not in ALL_EVENT_NAMES:
        # 알 수 없는 이벤트라도 거부하지 않고 경고만 — 향후 확장성.
        pass

    event_id = db.new_id()
    md_json = json.dumps(metadata or {}, ensure_ascii=False)
    ts = timestamp or db.utcnow_iso()

    with db.transaction(conn):
        conn.execute(
            "INSERT INTO events (event_id, user_id, timestamp, event_name, "
            "metadata_json) VALUES (?, ?, ?, ?, ?)",
            (event_id, user_id, ts, event_name, md_json),
        )
    return event_id


# ---------------------------------------------------------------------------
# 조회 헬퍼
# ---------------------------------------------------------------------------


def count_events(
    conn: sqlite3.Connection,
    *,
    event_name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> int:
    sql = "SELECT COUNT(*) AS c FROM events WHERE 1=1"
    params: list[Any] = []
    if event_name:
        sql += " AND event_name = ?"
        params.append(event_name)
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    return conn.execute(sql, params).fetchone()["c"]


def distinct_users_with_event(
    conn: sqlite3.Connection,
    *,
    event_name: str,
) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM events "
        "WHERE event_name = ? AND user_id IS NOT NULL",
        (event_name,),
    ).fetchall()
    return {r["user_id"] for r in rows}


def list_events(
    conn: sqlite3.Connection,
    *,
    user_id: Optional[str] = None,
    event_name: Optional[str] = None,
    limit: int = 1000,
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM events WHERE 1=1"
    params: list[Any] = []
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    if event_name:
        sql += " AND event_name = ?"
        params.append(event_name)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    return list(conn.execute(sql, params).fetchall())


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletenessImprovementResult:
    """1차 KPI 결과."""

    user_count: int
    avg_improvement_pct: float    # 평균 개선률 (%)
    median_improvement_pct: float # 중앙값 개선률 (%)
    users_with_improvement: int   # 개선된 사용자 수
    users_with_decline: int       # 점수가 하락한 사용자 수


@dataclass(frozen=True)
class ClassificationDistribution:
    """분류별 사용자/이벤트 수."""

    counts: dict[str, int]
    total: int

    def ratio(self, classification: str) -> float:
        if self.total == 0:
            return 0.0
        return self.counts.get(classification, 0) / self.total


# ---------------------------------------------------------------------------
# KPI 계산 함수들
# ---------------------------------------------------------------------------


def kpi_bill_passport_open_rate(conn: sqlite3.Connection) -> float:
    """Bill Passport 개설률 (정책 06 KPI4).

    passport_created 이벤트가 있는 사용자 수 / user_registered 이벤트가 있는 사용자 수.
    """
    registered = distinct_users_with_event(conn, event_name=EVENT_USER_REGISTERED)
    created = distinct_users_with_event(conn, event_name=EVENT_PASSPORT_CREATED)
    if not registered:
        return 0.0
    return len(created) / len(registered)


def kpi_completeness_improvement(
    conn: sqlite3.Connection,
) -> CompletenessImprovementResult:
    """1차 KPI (정책 06 §2-A): 자료 완결성 점수 개선률.

    각 사용자의 (마지막 score - 첫 score) / 첫 score 평균.
    첫 score가 0인 경우 안전을 위해 분자만 사용(절대 개선치).
    """
    rows = conn.execute(
        """
        SELECT user_id, total_score, created_at
        FROM passport_scores
        WHERE user_id IS NOT NULL
        ORDER BY user_id, created_at
        """,
    ).fetchall()

    by_user: dict[str, list[int]] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], []).append(r["total_score"])

    improvements: list[float] = []
    improved = 0
    declined = 0
    for scores in by_user.values():
        if len(scores) < 2:
            continue
        first, last = scores[0], scores[-1]
        if first == 0:
            improvements.append(float(last))
        else:
            improvements.append((last - first) / first * 100.0)
        if last > first:
            improved += 1
        elif last < first:
            declined += 1

    user_count = len(improvements)
    if user_count == 0:
        return CompletenessImprovementResult(0, 0.0, 0.0, 0, 0)

    avg = sum(improvements) / user_count
    sorted_imp = sorted(improvements)
    median = (
        sorted_imp[user_count // 2]
        if user_count % 2 == 1
        else (sorted_imp[user_count // 2 - 1] + sorted_imp[user_count // 2]) / 2
    )
    return CompletenessImprovementResult(
        user_count=user_count,
        avg_improvement_pct=round(avg, 2),
        median_improvement_pct=round(median, 2),
        users_with_improvement=improved,
        users_with_decline=declined,
    )


def kpi_template_copy_rate(conn: sqlite3.Connection) -> float:
    """2차 KPI: 자료요청 메시지 예시 복사율.

    request_template_copied 사용자 수 /
    case_classified에서 classification='근거 요청 필요'인 사용자 수.
    """
    # 분모: 근거 요청 필요로 분류된 사용자.
    rows = conn.execute(
        """
        SELECT DISTINCT user_id FROM events
        WHERE event_name = ?
          AND user_id IS NOT NULL
          AND metadata_json LIKE '%근거 요청 필요%'
        """,
        (EVENT_CASE_CLASSIFIED,),
    ).fetchall()
    needs_basis_users = {r["user_id"] for r in rows}
    if not needs_basis_users:
        return 0.0

    copied_users = distinct_users_with_event(
        conn, event_name=EVENT_REQUEST_TEMPLATE_COPIED,
    )
    return len(copied_users & needs_basis_users) / len(needs_basis_users)


def kpi_reupload_rate(
    conn: sqlite3.Connection,
    *,
    window_days: int = 30,
) -> float:
    """3차 KPI: 추가 자료 확보 후 재업로드율.

    첫 업로드 후 `window_days`일 이내에 다시 업로드한 사용자 / 첫 업로드 사용자.
    """
    rows = conn.execute(
        """
        SELECT user_id, timestamp FROM events
        WHERE event_name = ? AND user_id IS NOT NULL
        ORDER BY user_id, timestamp
        """,
        (EVENT_DOCUMENT_UPLOADED,),
    ).fetchall()

    by_user: dict[str, list[str]] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], []).append(r["timestamp"])

    if not by_user:
        return 0.0

    reupload_count = 0
    for user_id, timestamps in by_user.items():
        if len(timestamps) < 2:
            continue
        first = datetime.fromisoformat(timestamps[0])
        # 첫 업로드 직후에는 같은 세션의 여러 파일을 모두 카운트하지 않기 위해
        # 24시간 이상 지난 두 번째 업로드를 "재업로드"로 본다.
        for ts in timestamps[1:]:
            t = datetime.fromisoformat(ts)
            delta = t - first
            if timedelta(days=1) < delta <= timedelta(days=window_days):
                reupload_count += 1
                break
    return reupload_count / len(by_user)


def kpi_classification_distribution(
    conn: sqlite3.Connection,
) -> ClassificationDistribution:
    """4분류 + 정액 케이스 분포 (정책 06 §6의 케이스 분포 목표 검증용)."""
    rows = conn.execute(
        """
        SELECT classification, COUNT(DISTINCT user_id) AS c
        FROM calculation_results
        WHERE user_id IS NOT NULL
        GROUP BY classification
        """,
    ).fetchall()
    counts = {r["classification"]: r["c"] for r in rows}

    # passport_scores 기반 백업 — calculation_results가 비어도 분류 분포를 보고하기 위함.
    if not counts:
        # 분류는 추출/점수 기반으로 case_classified 이벤트에서도 추출 가능.
        score_rows = conn.execute(
            """
            SELECT metadata_json, COUNT(DISTINCT user_id) AS c
            FROM events
            WHERE event_name = ? AND user_id IS NOT NULL
            GROUP BY metadata_json
            """,
            (EVENT_CASE_CLASSIFIED,),
        ).fetchall()
        for r in score_rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
                cls = meta.get("classification")
                if cls:
                    counts[cls] = counts.get(cls, 0) + r["c"]
            except (json.JSONDecodeError, TypeError):
                continue

    total = sum(counts.values())
    return ClassificationDistribution(counts=counts, total=total)


def kpi_high_risk_block_count(conn: sqlite3.Connection) -> int:
    """HIGH/VERY_HIGH 등급 사용자의 메시지 복사 차단 이벤트 수.

    안전 설계가 실제로 작동했는지 점검(정책 05 회귀 지표).
    """
    return count_events(
        conn, event_name=EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED,
    )


def kpi_manual_input_share(conn: sqlite3.Connection) -> float:
    """수동 입력 모드 사용 비율 — 외부 LLM 미동의 사용자 추적.

    manual_input_used 사용자 수 / user_registered 사용자 수.
    """
    registered = distinct_users_with_event(conn, event_name=EVENT_USER_REGISTERED)
    manual = distinct_users_with_event(conn, event_name=EVENT_MANUAL_INPUT_USED)
    if not registered:
        return 0.0
    return len(manual) / len(registered)


# ---------------------------------------------------------------------------
# 통합 보고서
# ---------------------------------------------------------------------------


def compute_full_report(conn: sqlite3.Connection) -> dict[str, Any]:
    """모든 KPI를 한 번에 계산하여 dict로 반환 — Streamlit/JSON export용."""
    completeness = kpi_completeness_improvement(conn)
    classification = kpi_classification_distribution(conn)

    return {
        "summary": {
            "total_users_registered": len(
                distinct_users_with_event(conn, event_name=EVENT_USER_REGISTERED),
            ),
            "total_events": count_events(conn),
        },
        "primary_kpis": {
            "1차_완결성_점수_개선률_평균_pct": completeness.avg_improvement_pct,
            "1차_완결성_점수_개선률_중앙값_pct": completeness.median_improvement_pct,
            "1차_개선_사용자수": completeness.users_with_improvement,
            "1차_점수_하락_사용자수": completeness.users_with_decline,
            "1차_분석_대상_사용자수": completeness.user_count,
            "2차_메시지_복사율": round(kpi_template_copy_rate(conn), 4),
            "3차_재업로드율_30일": round(kpi_reupload_rate(conn), 4),
        },
        "secondary_kpis": {
            "Bill_Passport_개설률": round(kpi_bill_passport_open_rate(conn), 4),
            "수동_입력_모드_사용률": round(kpi_manual_input_share(conn), 4),
            "HIGH_VERY_HIGH_차단_횟수": kpi_high_risk_block_count(conn),
        },
        "classification_distribution": {
            "counts": classification.counts,
            "total": classification.total,
        },
    }
