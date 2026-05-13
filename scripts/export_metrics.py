"""KPI export 스크립트 — Phase 10.

events·passport_scores를 기반으로 KPI 요약을 CSV·JSON으로 출력.
PoC 분기별 보고서 작성·심사위원 제출용.

실행:
  python scripts/export_metrics.py [--out reports/2026Q2.csv] [--format csv|json]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config, db, metrics  # noqa: E402


def export_to_csv(report: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["section", "kpi", "value"])

        for section in ("summary", "primary_kpis", "secondary_kpis"):
            for k, v in report[section].items():
                writer.writerow([section, k, v])

        # 분류 분포는 별도 영역.
        dist = report["classification_distribution"]
        for cls, c in dist["counts"].items():
            ratio = c / dist["total"] if dist["total"] else 0.0
            writer.writerow([
                "classification_distribution",
                f"{cls}",
                f"{c} ({ratio:.1%})",
            ])
        writer.writerow([
            "classification_distribution",
            "total",
            dist["total"],
        ])

        # 메타.
        writer.writerow([
            "meta", "generated_at",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ])


def export_to_json(report: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **report,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        },
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KPI report.")
    parser.add_argument(
        "--out", type=str, default="reports/kpi_report.csv",
        help="Output file path (default: reports/kpi_report.csv).",
    )
    parser.add_argument(
        "--format", choices=["csv", "json"], default=None,
        help="Output format. Auto-detected from extension if unspecified.",
    )
    parser.add_argument(
        "--db", type=str, default=None, help="Override DB path.",
    )
    parser.add_argument(
        "--print-only", action="store_true",
        help="Print to stdout without writing a file.",
    )
    args = parser.parse_args()

    cfg = config.load_config()
    db_path = Path(args.db) if args.db else cfg.db_path
    conn = db.init_db(db_path)

    report = metrics.compute_full_report(conn)

    if args.print_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lstrip(".")
    if fmt == "json":
        export_to_json(report, out_path)
    elif fmt == "csv":
        export_to_csv(report, out_path)
    else:
        parser.error(f"Unsupported format: {fmt}")

    print(f"[done] wrote {out_path}")


if __name__ == "__main__":
    main()
