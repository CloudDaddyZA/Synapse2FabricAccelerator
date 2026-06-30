"""CSV export helper (used for Power BI datasets and indexes)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_csv(rows: list[dict[str, Any]], path: str | Path, headers: list[str] | None = None) -> Path:
    """Write list-of-dicts rows to CSV. Missing keys are blank."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cols = headers or (list(rows[0].keys()) if rows else [])
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in cols})
    return dest
