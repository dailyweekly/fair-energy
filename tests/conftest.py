"""공통 pytest fixture.

tmp_path 기반으로 격리된 SQLite DB를 제공한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core import db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """테스트별 임시 SQLite 파일 경로."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    """초기화된 SQLite 연결.

    fixture가 끝날 때 자동 close 한다.
    """
    connection = db.init_db(db_path)
    yield connection
    connection.close()
