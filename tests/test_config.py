"""core/config.py 환경 로딩 테스트."""

from __future__ import annotations

from pathlib import Path

from core import config


def test_defaults_when_env_empty() -> None:
    cfg = config.load_config(env={})
    assert cfg.app_env == "development"
    assert cfg.demo_mode is True
    assert cfg.default_retention_months == 6
    assert cfg.enable_llm_ocr is False
    assert cfg.enable_pdf_export is True
    assert cfg.anthropic_api_key is None


def test_demo_mode_false() -> None:
    cfg = config.load_config(env={"DEMO_MODE": "false"})
    assert cfg.demo_mode is False


def test_retention_months_parsed() -> None:
    cfg = config.load_config(env={"DEFAULT_RETENTION_MONTHS": "12"})
    assert cfg.default_retention_months == 12


def test_invalid_retention_falls_back() -> None:
    cfg = config.load_config(env={"DEFAULT_RETENTION_MONTHS": "garbage"})
    assert cfg.default_retention_months == 6  # 폴백


def test_storage_dir_resolves_relative_to_project_root() -> None:
    cfg = config.load_config(env={"STORAGE_DIR": "./storage"})
    assert cfg.storage_dir.is_absolute()
    assert cfg.storage_dir.name == "storage"


def test_db_path_extracted_from_sqlite_url(tmp_path: Path) -> None:
    db_file = tmp_path / "fair_energy.db"
    cfg = config.load_config(env={"DATABASE_URL": f"sqlite:///{db_file}"})
    assert cfg.db_path == db_file
