from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


HISTORY_DIR = Path("data") / "fechamentos_diarios"
CURRENT_FILE = HISTORY_DIR / "_fechamento_atual.json"


def _json_default(value: Any):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def ensure_history_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def save_daily_closing(closing: dict) -> Path:
    ensure_history_dir()
    report_date = str(closing.get("report_date", datetime.now().date())).replace("/", "-")
    generated_at = datetime.now().strftime("%H%M%S")
    target = HISTORY_DIR / f"{report_date}_{generated_at}.json"
    payload = dict(closing)
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    payload["history_path"] = str(target)
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
    with CURRENT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
    return target


def load_current_daily_closing() -> dict | None:
    ensure_history_dir()
    if not CURRENT_FILE.exists():
        return None
    try:
        with CURRENT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_current_daily_closing() -> None:
    ensure_history_dir()
    try:
        CURRENT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def delete_daily_closing(path_value: str | Path | None) -> bool:
    if not path_value:
        clear_current_daily_closing()
        return True

    ensure_history_dir()
    try:
        target = Path(path_value).resolve()
        history_root = HISTORY_DIR.resolve()
        if history_root not in target.parents or target.name.startswith("_") or target.suffix.lower() != ".json":
            return False

        current = load_current_daily_closing()
        target_str = str(Path(path_value))
        if current and (
            current.get("history_path") == target_str
            or Path(str(current.get("history_path", ""))).name == target.name
            or (
                current.get("report_date") == _read_json_field(target, "report_date")
                and current.get("saved_at") == _read_json_field(target, "saved_at")
            )
        ):
            clear_current_daily_closing()

        target.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _read_json_field(path: Path, field: str):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f).get(field)
    except Exception:
        return None


def list_daily_closings() -> list[dict]:
    ensure_history_dir()
    closings = []
    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        if path.name.startswith("_"):
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            closings.append(
                {
                    "label": f"{data.get('report_date', 'sem-data')} - {data.get('responsible', 'sem responsável')}",
                    "path": str(path),
                    "data": data,
                }
            )
        except Exception:
            continue
    return closings
