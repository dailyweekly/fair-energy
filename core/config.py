"""환경설정 단일 출처.

`.env` 또는 OS 환경변수에서 설정을 로드한다.
정책 04(개인정보·보관)·06(KPI) 관련 기본값을 한 곳에 모은다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Optional[str], default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    """애플리케이션 런타임 설정.

    .env 파일은 python-dotenv가 있으면 자동 로드되고, 없어도 OS 환경변수로 동작한다.
    """

    app_env: str
    demo_mode: bool
    anthropic_api_key: Optional[str]
    openai_api_key: Optional[str]
    app_secret_key: Optional[str]
    database_url: str
    storage_dir: Path
    default_retention_months: int
    enable_llm_ocr: bool
    enable_pdf_export: bool
    enable_admin: bool

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def db_path(self) -> Path:
        """SQLite 파일 경로. database_url이 sqlite:///... 형태일 때만 의미 있다."""
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix):
            raw = url[len(prefix):]
            path = Path(raw)
            if not path.is_absolute():
                path = self.project_root / path
            return path
        raise ValueError(f"Unsupported database_url for db_path: {url}")

    @property
    def originals_dir(self) -> Path:
        return self.storage_dir / "originals"

    @property
    def masked_dir(self) -> Path:
        return self.storage_dir / "masked"

    @property
    def audit_dir(self) -> Path:
        return self.storage_dir / "audit"


def load_config(env: Optional[dict[str, str]] = None) -> AppConfig:
    """환경에서 AppConfig를 로드한다.

    `env`가 주어지면 그 dict를 우선 사용한다(테스트 격리용).
    .env 자동 로드는 부수효과이므로, 테스트에서는 env=주입을 권장.
    """
    if env is None:
        # 선택적 .env 로드 — python-dotenv가 없으면 조용히 건너뛴다.
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        env = dict(os.environ)

    storage_dir = Path(env.get("STORAGE_DIR", "./storage"))
    if not storage_dir.is_absolute():
        storage_dir = Path(__file__).resolve().parent.parent / storage_dir

    return AppConfig(
        app_env=env.get("APP_ENV", "development"),
        demo_mode=_bool(env.get("DEMO_MODE"), default=True),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
        openai_api_key=env.get("OPENAI_API_KEY") or None,
        app_secret_key=env.get("APP_SECRET_KEY") or None,
        database_url=env.get("DATABASE_URL", "sqlite:///fair_energy.db"),
        storage_dir=storage_dir,
        default_retention_months=_int(env.get("DEFAULT_RETENTION_MONTHS"), default=6),
        enable_llm_ocr=_bool(env.get("ENABLE_LLM_OCR"), default=False),
        enable_pdf_export=_bool(env.get("ENABLE_PDF_EXPORT"), default=True),
        enable_admin=_bool(env.get("ENABLE_ADMIN"), default=False),
    )
