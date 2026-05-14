"""SQLite 저장소 — 스키마 정의와 연결 헬퍼.

정책 04(개인정보·보관)와 06(KPI)에서 요구하는 데이터를 담는다.
원본 경로(`original_path`)와 마스킹 경로(`masked_path`)는 별도 컬럼으로 분리한다.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

SCHEMA: list[str] = [
    # 1. users — 최소 식별 필드만. 이름·전화·이메일 미수집.
    # cohort='demo' — 시연·심사관 데모 모드 자동 시드 사용자(정책 06 §부록).
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id      TEXT PRIMARY KEY,
        cohort       TEXT NOT NULL DEFAULT 'general'
                     CHECK (cohort IN ('ngo', 'general', 'admin', 'demo')),
        locale       TEXT NOT NULL DEFAULT 'ko',
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    )
    """,
    # 2. consents — 동의 항목별로 별도 컬럼(묶음 동의 금지).
    """
    CREATE TABLE IF NOT EXISTS consents (
        consent_id                  TEXT PRIMARY KEY,
        user_id                     TEXT NOT NULL,
        consent_service             INTEGER NOT NULL CHECK (consent_service IN (0, 1)),
        consent_personal_info       INTEGER NOT NULL CHECK (consent_personal_info IN (0, 1)),
        consent_ai_processing       INTEGER NOT NULL CHECK (consent_ai_processing IN (0, 1)),
        consent_storage_months      INTEGER NOT NULL CHECK (consent_storage_months IN (6, 12, 36)),
        consent_ngo_share           INTEGER NOT NULL DEFAULT 0 CHECK (consent_ngo_share IN (0, 1)),
        consent_external_submission INTEGER NOT NULL DEFAULT 0
                                    CHECK (consent_external_submission IN (0, 1)),
        external_target             TEXT,  -- 외부 제출 동의 시 기관·문서 범위·목적 JSON
        created_at                  TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )
    """,
    # 3. documents — 원본·마스킹본 경로 분리.
    # original_path는 만료 파기 후 NULL로 비워지므로 nullable(정책 04 §6).
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id      TEXT PRIMARY KEY,
        user_id          TEXT NOT NULL,
        document_type    TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        original_path    TEXT,           -- 암호화 원본 파일 경로(만료 후 NULL)
        masked_path      TEXT,           -- 마스킹된 표시용 사본 경로
        file_hash        TEXT,
        size_bytes       INTEGER,
        retention_until  TEXT NOT NULL,  -- 보관 만료일 (사용자 선택 6/12/36개월)
        purged_at        TEXT,           -- 만료 파기 시각 (audit)
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )
    """,
    # 4. extracted_fields — OCR 추출 필드. user_confirmed가 계산 게이트.
    """
    CREATE TABLE IF NOT EXISTS extracted_fields (
        field_id                  TEXT PRIMARY KEY,
        document_id               TEXT NOT NULL,
        key                       TEXT NOT NULL,
        label                     TEXT NOT NULL,
        value                     TEXT,
        unit                      TEXT,
        confidence                REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        source_text               TEXT,
        needs_user_confirmation   INTEGER NOT NULL DEFAULT 1
                                  CHECK (needs_user_confirmation IN (0, 1)),
        user_confirmed            INTEGER NOT NULL DEFAULT 0
                                  CHECK (user_confirmed IN (0, 1)),
        created_at                TEXT NOT NULL,
        updated_at                TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE
    )
    """,
    # 5. passport_scores — 자료 완결성 점수 스냅샷.
    """
    CREATE TABLE IF NOT EXISTS passport_scores (
        score_id                  TEXT PRIMARY KEY,
        user_id                   TEXT NOT NULL,
        lease_contract            INTEGER NOT NULL DEFAULT 0,
        itemized_fee_notice       INTEGER NOT NULL DEFAULT 0,
        meter_photo_with_date     INTEGER NOT NULL DEFAULT 0,
        original_electricity_bill INTEGER NOT NULL DEFAULT 0,
        allocation_formula        INTEGER NOT NULL DEFAULT 0,
        payment_proof             INTEGER NOT NULL DEFAULT 0,
        total_score               INTEGER NOT NULL CHECK (total_score BETWEEN 0 AND 100),
        missing_items_json        TEXT,
        created_at                TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )
    """,
    # 6. calculation_results — 룰 엔진 결과.
    """
    CREATE TABLE IF NOT EXISTS calculation_results (
        calc_id                 TEXT PRIMARY KEY,
        user_id                 TEXT NOT NULL,
        classification          TEXT NOT NULL,  -- CaseClassification.value
        can_calculate           INTEGER NOT NULL CHECK (can_calculate IN (0, 1)),
        calculated_amount       INTEGER,
        user_charged_amount     INTEGER,
        difference_amount       INTEGER,
        difference_rate         REAL,
        formula_breakdown_json  TEXT,
        warnings_json           TEXT,
        neutral_label           TEXT NOT NULL,
        tariff_version          TEXT,  -- 사용된 tariff YAML version
        created_at              TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )
    """,
    # 7. audit_logs — 접근 로그(정책 04 §10).
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        log_id          TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        actor           TEXT NOT NULL,        -- user_id | 'system' | 'ngo_worker' | 'admin'
        action          TEXT NOT NULL
                        CHECK (action IN ('upload','view','download','delete','export',
                                          'confirm_field','calculate','classify','event')),
        object_id       TEXT,
        object_type     TEXT
                        CHECK (object_type IN ('original','masked','score','calc','event','user','document')
                               OR object_type IS NULL),
        consent_basis   TEXT  -- 외부 제출 등 동의가 필요한 경우 consent_id
    )
    """,
    # 8. events — KPI 측정용 이벤트(정책 06 §4).
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id      TEXT PRIMARY KEY,
        user_id       TEXT,
        timestamp     TEXT NOT NULL,
        event_name    TEXT NOT NULL,
        metadata_json TEXT
    )
    """,
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_consents_user      ON consents (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_user     ON documents (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_retention ON documents (retention_until)",
    "CREATE INDEX IF NOT EXISTS idx_fields_document    ON extracted_fields (document_id)",
    "CREATE INDEX IF NOT EXISTS idx_scores_user        ON passport_scores (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_calc_user          ON calculation_results (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_time         ON audit_logs (timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_actor        ON audit_logs (actor, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_events_user_time   ON events (user_id, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_events_name        ON events (event_name, timestamp)",
]


TABLE_NAMES: tuple[str, ...] = (
    "users",
    "consents",
    "documents",
    "extracted_fields",
    "passport_scores",
    "calculation_results",
    "audit_logs",
    "events",
)


# ---------------------------------------------------------------------------
# 연결 헬퍼
# ---------------------------------------------------------------------------


def utcnow_iso() -> str:
    """ISO8601 UTC. 모든 timestamp 컬럼은 이 포맷으로 통일한다."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


def connect(db_path: Path | str) -> sqlite3.Connection:
    """외래키 제약과 Row factory를 활성화한 연결을 반환한다.

    `check_same_thread=False`로 멀티스레드 환경(Streamlit Cloud) 호환.
    SQLite 자체는 직렬화된 쓰기를 보장하므로 PoC 트래픽에서 안전.
    베타 본격 단계에서는 PostgreSQL로 마이그레이션 권장 (정책 06 부록).
    """
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL 모드로 동시 읽기 안정성 향상 (Streamlit 멀티세션 호환).
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """간단한 트랜잭션 컨텍스트 매니저."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_legacy_schema_if_needed(db_path: Path) -> None:
    """구 스키마(cohort 'demo' 미지원 등) 감지 시 DB 파일 삭제.

    PoC 한정 — 데이터 휘발성 전제. 베타 본격 단계에서는 ALTER TABLE
    기반 정식 마이그레이션 또는 PostgreSQL 전환 필요.
    """
    if not db_path.exists():
        return
    try:
        tmp = sqlite3.connect(db_path)
        row = tmp.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='users'"
        ).fetchone()
        tmp.close()
        if row and row[0] and "'demo'" not in row[0]:
            # 구 스키마 — 신 스키마로 재생성 위해 삭제.
            db_path.unlink()
    except sqlite3.Error:
        # 깨진 DB라면 동일하게 폐기.
        try:
            db_path.unlink()
        except OSError:
            pass


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """DB 파일이 없으면 생성하고, 모든 테이블·인덱스를 보장한다.

    구 스키마(cohort='demo' 미지원 등) 감지 시 DB 파일을 폐기하고 재생성한다.
    PoC 환경의 데이터 휘발성 전제이며, 베타 본격 환경에서는 별도 마이그레이션 절차 필요.
    """
    path = Path(db_path)
    _migrate_legacy_schema_if_needed(path)
    conn = connect(path)
    with transaction(conn):
        for ddl in SCHEMA:
            conn.execute(ddl)
        for ddl in INDEXES:
            conn.execute(ddl)
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


# ---------------------------------------------------------------------------
# 작은 INSERT 헬퍼 — Phase 2 이후 storage/consent 모듈이 호출
# ---------------------------------------------------------------------------


def insert_user(conn: sqlite3.Connection, *, cohort: str = "general",
                locale: str = "ko") -> str:
    """새 사용자를 만들고 user_id를 반환."""
    user_id = new_id()
    now = utcnow_iso()
    with transaction(conn):
        conn.execute(
            "INSERT INTO users (user_id, cohort, locale, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, cohort, locale, now, now),
        )
    return user_id


def insert_consent(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    consent_service: bool,
    consent_personal_info: bool,
    consent_ai_processing: bool,
    consent_storage_months: int,
    consent_ngo_share: bool = False,
    consent_external_submission: bool = False,
    external_target: Optional[str] = None,
) -> str:
    """동의 한 건을 기록하고 consent_id를 반환."""
    if consent_storage_months not in (6, 12, 36):
        raise ValueError("consent_storage_months must be one of 6, 12, 36")
    consent_id = new_id()
    with transaction(conn):
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
                int(consent_service), int(consent_personal_info),
                int(consent_ai_processing),
                consent_storage_months,
                int(consent_ngo_share), int(consent_external_submission),
                external_target, utcnow_iso(),
            ),
        )
    return consent_id
