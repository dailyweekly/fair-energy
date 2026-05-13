"""KPI 메트릭 회귀 테스트.

정책 06_poc_metrics_policy.md의 KPI 계층 산출 정확도를 검증한다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core import db, metrics


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _user(conn: sqlite3.Connection) -> str:
    return db.insert_user(conn)


def _ts(offset_days: int = 0) -> str:
    """과거/현재 ISO8601 타임스탬프."""
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat(
        timespec="seconds"
    )


def _insert_score(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    total: int,
    created_at: str | None = None,
) -> None:
    score_id = db.new_id()
    now = created_at or db.utcnow_iso()
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO passport_scores (
                score_id, user_id, total_score, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (score_id, user_id, total, now),
        )


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def test_log_event_creates_row(conn: sqlite3.Connection) -> None:
    user_id = _user(conn)
    event_id = metrics.log_event(
        conn,
        event_name=metrics.EVENT_USER_REGISTERED,
        user_id=user_id,
        metadata={"cohort": "ngo"},
    )
    row = conn.execute(
        "SELECT * FROM events WHERE event_id = ?", (event_id,),
    ).fetchone()
    assert row is not None
    assert row["event_name"] == "user_registered"
    md = json.loads(row["metadata_json"])
    assert md == {"cohort": "ngo"}


def test_log_event_handles_no_user_id(conn: sqlite3.Connection) -> None:
    """user_id=None인 시스템 이벤트(예: 잡)도 기록 가능."""
    event_id = metrics.log_event(
        conn, event_name="system_test_event", user_id=None,
    )
    row = conn.execute(
        "SELECT user_id FROM events WHERE event_id = ?", (event_id,),
    ).fetchone()
    assert row["user_id"] is None


def test_count_events_filters(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u1)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u2)
    metrics.log_event(conn, event_name=metrics.EVENT_PASSPORT_CREATED, user_id=u1)

    assert metrics.count_events(conn, event_name=metrics.EVENT_USER_REGISTERED) == 2
    assert metrics.count_events(conn, event_name=metrics.EVENT_PASSPORT_CREATED) == 1
    assert metrics.count_events(conn, user_id=u1) == 2


def test_distinct_users_with_event(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    # 같은 사용자가 두 번 이벤트를 일으켜도 중복 제거.
    metrics.log_event(conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u1)
    metrics.log_event(conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u1)
    metrics.log_event(conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u2)

    users = metrics.distinct_users_with_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED,
    )
    assert users == {u1, u2}


# ---------------------------------------------------------------------------
# Bill Passport 개설률
# ---------------------------------------------------------------------------


def test_passport_open_rate_zero_when_no_users(conn: sqlite3.Connection) -> None:
    assert metrics.kpi_bill_passport_open_rate(conn) == 0.0


def test_passport_open_rate_full(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    for u in (u1, u2):
        metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u)
        metrics.log_event(conn, event_name=metrics.EVENT_PASSPORT_CREATED, user_id=u)
    assert metrics.kpi_bill_passport_open_rate(conn) == 1.0


def test_passport_open_rate_half(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u1)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u2)
    metrics.log_event(conn, event_name=metrics.EVENT_PASSPORT_CREATED, user_id=u1)
    assert metrics.kpi_bill_passport_open_rate(conn) == 0.5


# ---------------------------------------------------------------------------
# 1차 KPI: 완결성 개선률
# ---------------------------------------------------------------------------


def test_completeness_improvement_empty(conn: sqlite3.Connection) -> None:
    result = metrics.kpi_completeness_improvement(conn)
    assert result.user_count == 0
    assert result.avg_improvement_pct == 0.0


def test_completeness_improvement_single_user_50pct_gain(
    conn: sqlite3.Connection,
) -> None:
    u = _user(conn)
    _insert_score(conn, u, total=40, created_at=_ts(-10))
    _insert_score(conn, u, total=60, created_at=_ts(0))
    result = metrics.kpi_completeness_improvement(conn)
    # (60-40)/40 * 100 = 50%
    assert result.user_count == 1
    assert result.avg_improvement_pct == 50.0
    assert result.users_with_improvement == 1


def test_completeness_improvement_decline_counted(conn: sqlite3.Connection) -> None:
    u = _user(conn)
    _insert_score(conn, u, total=80, created_at=_ts(-10))
    _insert_score(conn, u, total=60, created_at=_ts(0))
    result = metrics.kpi_completeness_improvement(conn)
    # (60-80)/80 * 100 = -25%
    assert result.avg_improvement_pct == -25.0
    assert result.users_with_decline == 1


def test_completeness_improvement_first_zero_falls_back_to_absolute(
    conn: sqlite3.Connection,
) -> None:
    """첫 점수가 0이면 절대 개선치로 폴백."""
    u = _user(conn)
    _insert_score(conn, u, total=0, created_at=_ts(-10))
    _insert_score(conn, u, total=50, created_at=_ts(0))
    result = metrics.kpi_completeness_improvement(conn)
    assert result.user_count == 1
    assert result.avg_improvement_pct == 50.0  # 절대 50점 개선


def test_completeness_improvement_single_score_excluded(
    conn: sqlite3.Connection,
) -> None:
    """점수 스냅샷이 1개뿐인 사용자는 개선률 계산에서 제외."""
    u = _user(conn)
    _insert_score(conn, u, total=50)
    result = metrics.kpi_completeness_improvement(conn)
    assert result.user_count == 0


# ---------------------------------------------------------------------------
# 2차 KPI: 메시지 복사율
# ---------------------------------------------------------------------------


def _classify_user_as_needs_basis(conn: sqlite3.Connection, user_id: str) -> None:
    metrics.log_event(
        conn,
        event_name=metrics.EVENT_CASE_CLASSIFIED,
        user_id=user_id,
        metadata={"classification": "근거 요청 필요"},
    )


def test_template_copy_rate_zero_when_no_basis_users(
    conn: sqlite3.Connection,
) -> None:
    assert metrics.kpi_template_copy_rate(conn) == 0.0


def test_template_copy_rate_partial(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    _classify_user_as_needs_basis(conn, u1)
    _classify_user_as_needs_basis(conn, u2)
    metrics.log_event(
        conn, event_name=metrics.EVENT_REQUEST_TEMPLATE_COPIED, user_id=u1,
    )
    assert metrics.kpi_template_copy_rate(conn) == 0.5


def test_template_copy_rate_ignores_non_basis_users(conn: sqlite3.Connection) -> None:
    """근거 요청 필요로 분류 안 된 사용자의 복사는 무시."""
    u1 = _user(conn)
    # u1은 다른 분류로 분류됨.
    metrics.log_event(
        conn, event_name=metrics.EVENT_CASE_CLASSIFIED, user_id=u1,
        metadata={"classification": "공식 산식 비교 가능"},
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_REQUEST_TEMPLATE_COPIED, user_id=u1,
    )
    # 분모(근거 요청 필요)가 0이므로 0.0.
    assert metrics.kpi_template_copy_rate(conn) == 0.0


# ---------------------------------------------------------------------------
# 3차 KPI: 재업로드율
# ---------------------------------------------------------------------------


def test_reupload_rate_counts_only_after_one_day(conn: sqlite3.Connection) -> None:
    """같은 세션에 여러 업로드는 카운트 안 함 (24시간 이상 지나야 재업로드)."""
    u = _user(conn)
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u,
        timestamp=_ts(-5),
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u,
        timestamp=_ts(-5),  # 같은 시점 — 같은 세션.
    )
    rate = metrics.kpi_reupload_rate(conn, window_days=30)
    assert rate == 0.0


def test_reupload_rate_after_one_day(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    # u1: 첫 업로드 후 5일 뒤 재업로드 — 카운트.
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u1,
        timestamp=_ts(-10),
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u1,
        timestamp=_ts(-5),
    )
    # u2: 단일 업로드 — 미카운트.
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u2,
        timestamp=_ts(-5),
    )
    rate = metrics.kpi_reupload_rate(conn, window_days=30)
    # 2명 중 1명 재업로드 = 0.5
    assert rate == 0.5


def test_reupload_rate_excludes_outside_window(conn: sqlite3.Connection) -> None:
    """30일 윈도우 외 재업로드는 제외."""
    u = _user(conn)
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u,
        timestamp=_ts(-100),  # 100일 전.
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED, user_id=u,
        timestamp=_ts(0),     # 오늘.
    )
    rate = metrics.kpi_reupload_rate(conn, window_days=30)
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 분류 분포
# ---------------------------------------------------------------------------


def test_classification_distribution_from_events(conn: sqlite3.Connection) -> None:
    u1, u2, u3 = _user(conn), _user(conn), _user(conn)
    metrics.log_event(
        conn, event_name=metrics.EVENT_CASE_CLASSIFIED, user_id=u1,
        metadata={"classification": "공식 산식 비교 가능"},
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_CASE_CLASSIFIED, user_id=u2,
        metadata={"classification": "근거 요청 필요"},
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_CASE_CLASSIFIED, user_id=u3,
        metadata={"classification": "근거 요청 필요"},
    )

    dist = metrics.kpi_classification_distribution(conn)
    assert dist.total == 3
    assert dist.counts["근거 요청 필요"] == 2
    assert dist.counts["공식 산식 비교 가능"] == 1
    assert dist.ratio("근거 요청 필요") == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# 안전·수동 입력 보조 KPI
# ---------------------------------------------------------------------------


def test_high_risk_block_count(conn: sqlite3.Connection) -> None:
    u = _user(conn)
    metrics.log_event(
        conn, event_name=metrics.EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED, user_id=u,
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED, user_id=u,
    )
    assert metrics.kpi_high_risk_block_count(conn) == 2


def test_manual_input_share(conn: sqlite3.Connection) -> None:
    u1, u2 = _user(conn), _user(conn)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u1)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u2)
    metrics.log_event(conn, event_name=metrics.EVENT_MANUAL_INPUT_USED, user_id=u1)
    assert metrics.kpi_manual_input_share(conn) == 0.5


# ---------------------------------------------------------------------------
# 통합 리포트
# ---------------------------------------------------------------------------


def test_full_report_structure(conn: sqlite3.Connection) -> None:
    u = _user(conn)
    metrics.log_event(conn, event_name=metrics.EVENT_USER_REGISTERED, user_id=u)
    _insert_score(conn, u, total=30, created_at=_ts(-5))
    _insert_score(conn, u, total=60, created_at=_ts(0))

    report = metrics.compute_full_report(conn)
    assert "summary" in report
    assert "primary_kpis" in report
    assert "secondary_kpis" in report
    assert "classification_distribution" in report
    assert report["summary"]["total_users_registered"] == 1
    assert report["primary_kpis"]["1차_완결성_점수_개선률_평균_pct"] == 100.0
