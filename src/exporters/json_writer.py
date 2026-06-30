"""JSON export helpers with Pydantic-aware serialization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _default(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return str(obj)


def write_json(data: Any, path: str | Path) -> Path:
    """Serialize ``data`` (dict/list/BaseModel) to pretty JSON."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    with dest.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=_default)
    return dest


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)
