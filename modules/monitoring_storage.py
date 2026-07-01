from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable


STATE_ID = "main"
STATE_FILE = Path("data") / "monitoring_state.json"


def empty_monitoring_state() -> dict:
    return {
        "version": 1,
        "schools": {},
        "contacts": {},
        "current": {},
        "incidents": {},
        "events": [],
        "imports": [],
    }


def normalize_monitoring_state(value) -> dict:
    state = empty_monitoring_state()
    if isinstance(value, dict):
        for key in state:
            if key in value and isinstance(value[key], type(state[key])):
                state[key] = deepcopy(value[key])
    state["version"] = 1
    return state


class MonitoringStore:
    def __init__(
        self,
        supabase_request: Callable | None = None,
        supabase_enabled: bool = False,
        table: str = "hub_monitoring_state",
    ):
        self.supabase_request = supabase_request
        self.supabase_enabled = bool(supabase_enabled and supabase_request)
        self.table = table
        self.backend = "local"
        self.last_warning = ""

    def _load_local(self) -> dict:
        if not STATE_FILE.exists():
            return empty_monitoring_state()
        try:
            with STATE_FILE.open("r", encoding="utf-8") as handle:
                return normalize_monitoring_state(json.load(handle))
        except Exception:
            self.last_warning = "O histórico local não pôde ser lido; uma base vazia foi carregada."
            return empty_monitoring_state()

    def _save_local(self, state: dict) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as handle:
            json.dump(
                normalize_monitoring_state(state),
                handle,
                ensure_ascii=False,
                indent=2,
            )

    def load(self) -> dict:
        local_state = self._load_local()
        if not self.supabase_enabled:
            self.backend = "local"
            return local_state

        try:
            rows = self.supabase_request(
                "GET",
                self.table,
                f"?select=payload&id=eq.{STATE_ID}&limit=1",
            )
            if rows:
                remote_state = normalize_monitoring_state(rows[0].get("payload"))
                self._save_local(remote_state)
                self.backend = "supabase"
                return remote_state
            self.backend = "supabase"
            return local_state
        except Exception as exc:
            self.backend = "local"
            self.last_warning = (
                "Supabase indisponível para o monitoramento; usando armazenamento local. "
                f"Detalhe: {exc}"
            )
            return local_state

    def save(self, state: dict) -> tuple[bool, str]:
        normalized = normalize_monitoring_state(state)
        self._save_local(normalized)
        if not self.supabase_enabled:
            self.backend = "local"
            return True, "Histórico salvo localmente."

        try:
            self.supabase_request(
                "POST",
                self.table,
                "?on_conflict=id",
                {
                    "id": STATE_ID,
                    "payload": normalized,
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
                prefer="resolution=merge-duplicates,return=minimal",
            )
            self.backend = "supabase"
            self.last_warning = ""
            return True, "Histórico sincronizado com o Supabase."
        except Exception as exc:
            self.backend = "local"
            self.last_warning = (
                "Alterações preservadas localmente, mas não sincronizadas com o Supabase. "
                f"Detalhe: {exc}"
            )
            return False, self.last_warning
