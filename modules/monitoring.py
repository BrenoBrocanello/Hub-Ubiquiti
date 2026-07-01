from __future__ import annotations

import hashlib
import hmac
import html
import re
import unicodedata
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from modules.monitoring_storage import MonitoringStore, normalize_monitoring_state


APP_TZ = ZoneInfo("America/Sao_Paulo")
SLA_HOURS = 4
DEFAULT_PASSWORD_SHA256 = "a6dab8696c40b89878dbe68f22572145b27ad266b3ae3a1e7ab4092ce0c3522f"
ACTIVE_STATUSES = {"OFFLINE", "DEGRADED", "ALERTA", "SEM_DISPOSITIVO"}
MONTHS_EN = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
STATUS_LABELS = {
    "OFFLINE": "Offline total",
    "DEGRADED": "Degradada",
    "ALERTA": "Alerta",
    "SEM_DISPOSITIVO": "Sem dispositivos",
    "ONLINE": "Online",
}
WORKFLOW_OPTIONS = [
    "Sem chamado",
    "Chamado aberto",
    "Gestor contatado",
    "Aguardando resposta",
]


def _now() -> datetime:
    return datetime.now(APP_TZ)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(APP_TZ).isoformat(timespec="seconds")


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=APP_TZ)
        return parsed.astimezone(APP_TZ)
    except (TypeError, ValueError):
        return None


def _clean(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalized(value) -> str:
    text = unicodedata.normalize("NFKD", _clean(value))
    return "".join(char for char in text if not unicodedata.combining(char)).upper()


def _extract_inep(value) -> str:
    match = re.search(r"(?<!\d)(\d{8})(?!\d)", _clean(value))
    return match.group(1) if match else ""


def _infer_uf(inep: str, name: str = "") -> str:
    if str(inep).startswith("35"):
        return "SP"
    if str(inep).startswith("23"):
        return "CE"
    match = re.match(r"^\s*([A-Za-z]{2})\b", _clean(name))
    return match.group(1).upper() if match else ""


def _infer_city(name: str, inep: str, uf: str) -> str:
    text = _clean(name)
    if uf and text.upper().startswith(f"{uf} "):
        text = text[len(uf):].strip()
    text = re.sub(rf"\s*[-–—]\s*{re.escape(inep)}\s*$", "", text).strip()
    text = re.sub(rf"\s+{re.escape(inep)}\s*$", "", text).strip()
    return text


def _classify_description(description: str) -> tuple[bool, str]:
    value = _normalized(description)
    if "INVIABILIDADE" in value:
        return True, "Inviabilidade de link"
    if "RENEGOCIACAO" in value:
        return True, "Renegociação de link"
    if value == "OBRAS":
        return True, "Obras"
    if "OBRA" in value or "REFORMA" in value:
        return False, "Atenção: escola em obras/reforma"
    return False, ""


def _parse_omada_last_uptime(status: str) -> datetime | None:
    match = re.search(
        r"Last Uptime:\s*([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+"
        r"(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)",
        status,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    month = MONTHS_EN.get(match.group(1).upper())
    if not month:
        return None
    hour = int(match.group(4))
    marker = match.group(7).upper()
    if marker == "PM" and hour != 12:
        hour += 12
    if marker == "AM" and hour == 12:
        hour = 0
    try:
        return datetime(
            int(match.group(3)),
            month,
            int(match.group(2)),
            hour,
            int(match.group(5)),
            int(match.group(6)),
            tzinfo=APP_TZ,
        )
    except ValueError:
        return None


def _number(value) -> int:
    text = re.sub(r"[^\d-]", "", _clean(value))
    try:
        return int(text)
    except ValueError:
        return 0


def parse_omada_export(df: pd.DataFrame, imported_at: datetime | None = None) -> tuple[list[dict], dict]:
    imported_at = imported_at or _now()
    source = df.copy()
    source.columns = [_normalized(column) for column in source.columns]
    required = {"NAME", "STATUS"}
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Export Omada inválido: faltam as colunas {', '.join(sorted(missing))}.")

    observations = []
    ignored = []
    for _, row in source.iterrows():
        name = _clean(row.get("NAME"))
        inep = _extract_inep(name)
        uf = _infer_uf(inep, name)
        if not inep or uf not in {"SP", "CE"}:
            if not inep:
                ignored.append(name or "(sem nome)")
            continue
        raw_status = _clean(row.get("STATUS"))
        normalized_status = _normalized(raw_status)
        status = "ONLINE" if normalized_status == "ONLINE" else "OFFLINE"
        last_uptime = _parse_omada_last_uptime(raw_status) if status == "OFFLINE" else None
        description = _clean(row.get("DESCRIPTION"))
        exception, exception_reason = _classify_description(description)
        observations.append(
            {
                "inep": inep,
                "uf": uf,
                "municipality": _infer_city(name, inep, uf),
                "source_id": "OMADA",
                "platform": "OMADA",
                "source_name": name,
                "status": status,
                "raw_status": raw_status,
                "offline_since": _iso(last_uptime) if last_uptime else (
                    _iso(imported_at) if status == "OFFLINE" else ""
                ),
                "time_source": "Omada Last Uptime" if last_uptime else "Primeira detecção",
                "description": description,
                "exception": exception,
                "exception_reason": exception_reason,
                "total_devices": None,
                "offline_devices": None,
                "offline_percent": None,
            }
        )
    return observations, {"total": len(source), "accepted": len(observations), "ignored": ignored}


def parse_zyxel_export(df: pd.DataFrame, imported_at: datetime | None = None) -> tuple[list[dict], dict]:
    imported_at = imported_at or _now()
    source = df.copy()
    columns = {_normalized(column): column for column in source.columns}

    def find(*names):
        return next((columns[name] for name in names if name in columns), None)

    status_col = find("ESTADO", "STATUS")
    name_col = find("NOME", "NAME")
    if not status_col or not name_col:
        raise ValueError("Export Zyxel inválido: as colunas Estado/Status e Nome/Name são obrigatórias.")

    offline_col = find("DISPOSITIVOS OFFLINE", "OFFLINE DEVICES")
    total_col = find("DISPOSITIVOS", "DEVICES")
    percent_col = find("% OFFLINE", "% OFFLINE DEVICES")
    tags_col = find("MARCADORES", "TAGS")
    observations = []
    ignored = []

    for _, row in source.iterrows():
        name = _clean(row.get(name_col))
        inep = _extract_inep(name)
        uf = _infer_uf(inep, name)
        if not inep or uf not in {"SP", "CE"}:
            if not inep:
                ignored.append(name or "(sem nome)")
            continue

        raw_status = _clean(row.get(status_col))
        normalized_status = _normalized(raw_status)
        total = _number(row.get(total_col)) if total_col else 0
        offline = _number(row.get(offline_col)) if offline_col else 0
        percent_text = _clean(row.get(percent_col)) if percent_col else ""
        percent_match = re.search(r"(\d+(?:[.,]\d+)?)", percent_text)
        percent = float(percent_match.group(1).replace(",", ".")) if percent_match else None

        if normalized_status == "OK":
            status = "ONLINE"
        elif normalized_status == "NO DEVICES" or total <= 0:
            status = "SEM_DISPOSITIVO"
        elif normalized_status == "DEVICES UNREACHABLE" or (total > 0 and offline >= total):
            status = "OFFLINE"
        elif offline > 0:
            status = "DEGRADED"
        else:
            status = "ALERTA"

        description = _clean(row.get(tags_col)) if tags_col else ""
        exception, exception_reason = _classify_description(description)
        observations.append(
            {
                "inep": inep,
                "uf": uf,
                "municipality": _infer_city(name, inep, uf),
                "source_id": "ZYXEL",
                "platform": "ZYXEL",
                "source_name": name,
                "status": status,
                "raw_status": raw_status,
                "offline_since": _iso(imported_at) if status == "OFFLINE" else "",
                "time_source": "Primeira detecção" if status == "OFFLINE" else "",
                "description": description,
                "exception": exception,
                "exception_reason": exception_reason,
                "total_devices": total,
                "offline_devices": offline,
                "offline_percent": percent,
            }
        )
    return observations, {"total": len(source), "accepted": len(observations), "ignored": ignored}


def parse_ubiquiti_rows(rows: list[dict], imported_at: datetime | None = None) -> dict[str, list[dict]]:
    imported_at = imported_at or _now()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        inep = _extract_inep(row.get("INEP") or row.get("Nome no Console"))
        uf = _infer_uf(inep, row.get("Nome no Console", ""))
        if not inep or uf not in {"SP", "CE"}:
            continue
        source_id = f"UBIQUITI:{_clean(row.get('Conta')) or 'Conta'}"
        raw_status = _clean(row.get("Status Rede"))
        status = "ONLINE" if "ONLINE" in raw_status.upper() else "OFFLINE"
        last_seen = _clean(row.get("Último Sinal"))
        parsed_last_seen = None
        if last_seen and last_seen != "—":
            try:
                parsed_last_seen = datetime.strptime(last_seen, "%d/%m/%Y %H:%M").replace(tzinfo=APP_TZ)
            except ValueError:
                parsed_last_seen = None
        name = _clean(row.get("Nome no Console"))
        grouped.setdefault(source_id, []).append(
            {
                "inep": inep,
                "uf": uf,
                "municipality": _infer_city(name, inep, uf),
                "source_id": source_id,
                "platform": "UBIQUITI",
                "source_name": name,
                "status": status,
                "raw_status": raw_status,
                "offline_since": _iso(parsed_last_seen) if parsed_last_seen else (
                    _iso(imported_at) if status == "OFFLINE" else ""
                ),
                "time_source": "Ubiquiti último sinal" if parsed_last_seen else (
                    "Primeira detecção" if status == "OFFLINE" else ""
                ),
                "description": _clean(row.get("Conta")),
                "exception": False,
                "exception_reason": "",
                "total_devices": None,
                "offline_devices": None,
                "offline_percent": None,
            }
        )
    return grouped


def _event(state: dict, event_type: str, actor: str, **details) -> None:
    state["events"].append(
        {
            "id": uuid4().hex,
            "at": _iso(),
            "type": event_type,
            "actor": actor or "usuário",
            **details,
        }
    )
    state["events"] = state["events"][-2500:]


def _new_incident(state: dict, observation: dict, actor: str) -> str:
    incident_id = uuid4().hex
    opened_at = observation.get("offline_since") or _iso()
    state["incidents"][incident_id] = {
        "id": incident_id,
        "inep": observation["inep"],
        "source_id": observation["source_id"],
        "platform": observation["platform"],
        "status": observation["status"],
        "opened_at": opened_at,
        "closed_at": "",
        "workflow": "Sem chamado",
        "ticket_number": "",
        "ticket_opened_at": "",
        "notes": "",
        "last_contact_at": "",
        "created_by": actor,
        "updated_at": _iso(),
    }
    _event(
        state,
        "incident_opened",
        actor,
        inep=observation["inep"],
        source_id=observation["source_id"],
        incident_id=incident_id,
        status=observation["status"],
    )
    return incident_id


def apply_source_snapshot(
    state_value: dict,
    source_id: str,
    observations: list[dict],
    actor: str,
    imported_at: datetime | None = None,
    metadata: dict | None = None,
) -> dict:
    state = normalize_monitoring_state(state_value)
    imported_at = imported_at or _now()
    imported_iso = _iso(imported_at)
    seen_keys = set()

    for observation in observations:
        observation = dict(observation)
        observation["source_id"] = source_id
        inep = observation["inep"]
        key = f"{source_id}:{inep}"
        seen_keys.add(key)
        school = state["schools"].setdefault(
            inep,
            {
                "inep": inep,
                "name": "",
                "uf": observation.get("uf", ""),
                "municipality": observation.get("municipality", ""),
                "region": "Sudeste" if observation.get("uf") == "SP" else "Nordeste",
                "updated_at": imported_iso,
            },
        )
        if not school.get("uf"):
            school["uf"] = observation.get("uf", "")
        if not school.get("municipality"):
            school["municipality"] = observation.get("municipality", "")
        school["updated_at"] = imported_iso

        previous = state["current"].get(key, {})
        previous_incident = state["incidents"].get(previous.get("incident_id", ""))
        status = observation["status"]
        incident_id = previous.get("incident_id", "")

        # Zyxel não informa quando a queda começou. Enquanto a escola continuar
        # offline, preserve a primeira detecção em vez de reiniciar o SLA a cada upload.
        if (
            status == "OFFLINE"
            and previous.get("status") == "OFFLINE"
            and observation.get("time_source") == "Primeira detecção"
            and previous.get("offline_since")
        ):
            observation["offline_since"] = previous["offline_since"]
            observation["time_source"] = previous.get("time_source", "Primeira detecção")

        if status == "ONLINE":
            if previous_incident and not previous_incident.get("closed_at"):
                previous_incident["closed_at"] = imported_iso
                previous_incident["status"] = "RECUPERADA"
                previous_incident["updated_at"] = imported_iso
                _event(
                    state,
                    "incident_closed",
                    actor,
                    inep=inep,
                    source_id=source_id,
                    incident_id=incident_id,
                )
            incident_id = ""
        else:
            should_create = not previous_incident or bool(previous_incident.get("closed_at"))
            old_start = _parse_iso(previous.get("offline_since"))
            new_start = _parse_iso(observation.get("offline_since"))
            if (
                not should_create
                and previous.get("status") == "OFFLINE"
                and status == "OFFLINE"
                and old_start
                and new_start
                and (new_start - old_start).total_seconds() > 300
                and observation.get("time_source") != "Primeira detecção"
            ):
                previous_incident["closed_at"] = observation["offline_since"]
                previous_incident["status"] = "RECUPERADA_INFERIDA"
                previous_incident["updated_at"] = imported_iso
                should_create = True
            if should_create:
                incident_id = _new_incident(state, observation, actor)
                previous_incident = state["incidents"][incident_id]
            if previous_incident:
                previous_incident["status"] = status
                previous_incident["updated_at"] = imported_iso

        state["current"][key] = {
            **observation,
            "incident_id": incident_id,
            "observed_at": imported_iso,
            "stale": False,
        }

    for key, record in state["current"].items():
        if record.get("source_id") == source_id and key not in seen_keys:
            record["stale"] = True

    import_entry = {
        "id": uuid4().hex,
        "at": imported_iso,
        "source_id": source_id,
        "actor": actor,
        "records": len(observations),
        "ignored": len((metadata or {}).get("ignored", [])),
        "total": (metadata or {}).get("total", len(observations)),
        "ignored_examples": (metadata or {}).get("ignored", [])[:10],
    }
    state["imports"].append(import_entry)
    state["imports"] = state["imports"][-500:]
    _event(state, "source_imported", actor, source_id=source_id, records=len(observations))
    return state


def _record_age(record: dict, now: datetime | None = None) -> float | None:
    if record.get("status") != "OFFLINE":
        return None
    start = _parse_iso(record.get("offline_since"))
    if not start:
        return None
    return max(0.0, ((now or _now()) - start).total_seconds() / 3600)


def _format_duration(hours: float | None) -> str:
    if hours is None:
        return "tempo desconhecido"
    total_minutes = max(0, int(hours * 60))
    days, remainder = divmod(total_minutes, 1440)
    hour, minute = divmod(remainder, 60)
    if days:
        return f"{days}d {hour:02d}h"
    return f"{hour:02d}h {minute:02d}min"


def _incident_for(state: dict, record: dict) -> dict:
    return state["incidents"].get(record.get("incident_id", ""), {})


def _conflicting_ineps(state: dict) -> set[str]:
    grouped: dict[str, set[str]] = {}
    for record in state["current"].values():
        if record.get("stale"):
            continue
        grouped.setdefault(record.get("inep", ""), set()).add(record.get("status", ""))
    return {
        inep for inep, statuses in grouped.items()
        if "ONLINE" in statuses and "OFFLINE" in statuses
    }


def _priority(state: dict, record: dict) -> tuple:
    incident = _incident_for(state, record)
    age = _record_age(record)
    workflow = incident.get("workflow", "Sem chamado")
    if record.get("stale"):
        band = 9
    elif record.get("exception"):
        band = 8
    elif record.get("status") == "OFFLINE" and (age or 0) >= SLA_HOURS and workflow == "Sem chamado":
        band = 0
    elif record.get("status") == "OFFLINE" and workflow == "Sem chamado":
        band = 1
    elif record.get("status") == "OFFLINE":
        band = 2
    elif record.get("status") == "DEGRADED":
        band = 3
    elif record.get("status") == "ALERTA":
        band = 4
    else:
        band = 5
    start = _parse_iso(record.get("offline_since"))
    return band, start or _now(), record.get("inep", "")


def _phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) in {10, 11}:
        digits = f"55{digits}"
    return digits


def _message(school: dict) -> str:
    return (
        "Olá, tudo bem? Me chamo Breno, sou analista da Q13 no projeto Aprender Conectado.\n\n"
        f"Você trabalha na escola INEP: {school.get('inep', '')}\n"
        f"Nome: {school.get('name') or 'Não cadastrado'}\n"
        f"Região: {school.get('region', '')}\n"
        f"Estado: {school.get('uf', '')}\n"
        f"Município: {school.get('municipality', '')}\n\n?"
    )


def _whatsapp_url(contact: dict, school: dict) -> str:
    number = _phone(contact.get("phone", ""))
    return f"https://wa.me/{number}?text={quote(_message(school))}" if number else ""


def _password_valid(candidate: str, configured_password: str) -> bool:
    if configured_password:
        return hmac.compare_digest(str(candidate), str(configured_password))
    candidate_hash = hashlib.sha256(str(candidate).encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate_hash, DEFAULT_PASSWORD_SHA256)


def _save_state(store: MonitoringStore, state: dict) -> None:
    st.session_state.monitoring_state = state
    ok, message = store.save(state)
    st.session_state.monitoring_backend = store.backend
    if ok:
        st.toast(message, icon="✅")
    else:
        st.warning(message)


def _render_access_gate(configured_password: str) -> bool:
    if st.session_state.get("monitoring_authenticated"):
        return True
    st.markdown("### 🔐 Central de Monitoramento")
    st.caption("Área operacional protegida. Informe a senha do módulo para continuar.")
    with st.form("monitoring_login_form"):
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        if _password_valid(password, configured_password):
            st.session_state.monitoring_authenticated = True
            st.rerun()
        st.error("Senha inválida.")
    return False


def _render_imports(
    state: dict,
    store: MonitoringStore,
    actor: str,
    ubiquiti_accounts: list,
    collect_ubiquiti,
) -> None:
    flash = st.session_state.pop("monitoring_update_flash", None)
    if flash:
        st.success(flash.get("message", "Monitoramento atualizado."))
        if flash.get("warnings"):
            st.warning(" | ".join(flash["warnings"]))

    with st.expander("🔄 Atualizar monitoramento", expanded=True):
        st.markdown(
            "**1. Selecione os exports mais recentes.** Ao atualizar, o Hub também consulta "
            "automaticamente todas as contas Ubiquiti configuradas no Hub e mantém "
            "somente as escolas de SP e CE."
        )
        col_omada, col_zyxel = st.columns(2)
        with col_omada:
            omada_file = st.file_uploader(
                "Omada (.xlsx)",
                type=["xlsx"],
                key="monitoring_omada_upload",
                help="Export Organization List do Omada.",
            )
        with col_zyxel:
            zyxel_file = st.file_uploader(
                "Zyxel (.csv)",
                type=["csv"],
                key="monitoring_zyxel_upload",
                help="Export Overview > Sites do Zyxel Nebula.",
            )

        st.caption(
            "Você pode atualizar apenas um export, mas o ideal é enviar os dois juntos. "
            "Ubiquiti não precisa de arquivo nem de um botão separado."
        )
        if st.button(
            "Atualizar monitoramento",
            type="primary",
            use_container_width=True,
            disabled=not (omada_file or zyxel_file),
        ):
            new_state = state
            summaries = []
            warnings = []
            updated_any = False
            with st.status("Atualizando as fontes...", expanded=True) as status_box:
                if omada_file:
                    status_box.write("Lendo o export Omada...")
                    try:
                        omada_file.seek(0)
                        observations, metadata = parse_omada_export(pd.read_excel(omada_file))
                        new_state = apply_source_snapshot(
                            new_state, "OMADA", observations, actor, metadata=metadata
                        )
                        summaries.append(f"Omada: {len(observations)} escolas")
                        updated_any = True
                    except Exception as exc:
                        warnings.append(f"Omada não atualizado: {exc}")
                if zyxel_file:
                    status_box.write("Lendo o export Zyxel...")
                    try:
                        zyxel_file.seek(0)
                        observations, metadata = parse_zyxel_export(pd.read_csv(zyxel_file))
                        new_state = apply_source_snapshot(
                            new_state, "ZYXEL", observations, actor, metadata=metadata
                        )
                        summaries.append(f"Zyxel: {len(observations)} escolas")
                        updated_any = True
                    except Exception as exc:
                        warnings.append(f"Zyxel não atualizado: {exc}")

                status_box.write("Consultando Ubiquiti automaticamente...")
                if ubiquiti_accounts:
                    try:
                        rows, api_errors = collect_ubiquiti(ubiquiti_accounts)
                        grouped = parse_ubiquiti_rows(rows)
                        for source_id, observations in grouped.items():
                            new_state = apply_source_snapshot(
                                new_state,
                                source_id,
                                observations,
                                actor,
                                metadata={"total": len(observations), "ignored": []},
                            )
                        ubiquiti_total = sum(len(items) for items in grouped.values())
                        summaries.append(f"Ubiquiti: {ubiquiti_total} escolas")
                        updated_any = True
                        if api_errors:
                            warnings.append(
                                "Algumas contas Ubiquiti falharam: " + " | ".join(api_errors)
                            )
                    except Exception as exc:
                        warnings.append(f"Ubiquiti não atualizado: {exc}")
                else:
                    warnings.append(
                        "Nenhuma conta Ubiquiti está configurada no Hub."
                    )

                if updated_any:
                    status_box.update(label="Atualização concluída", state="complete")
                    _save_state(store, new_state)
                    st.session_state.monitoring_update_flash = {
                        "message": "Monitoramento atualizado — " + " · ".join(summaries),
                        "warnings": warnings,
                    }
                    st.rerun()
                else:
                    status_box.update(label="Nenhuma fonte pôde ser atualizada", state="error")
                    st.error(" | ".join(warnings))


def _latest_imports(state: dict) -> dict[str, dict]:
    latest = {}
    for item in state["imports"]:
        source = item.get("source_id", "")
        if source not in latest or item.get("at", "") > latest[source].get("at", ""):
            latest[source] = item
    return latest


def _render_freshness(state: dict) -> None:
    latest = _latest_imports(state)
    if not latest:
        st.info(
            "Comece selecionando os exports Omada/Zyxel e clique em "
            "**Atualizar monitoramento**. O Ubiquiti será consultado automaticamente."
        )
        return
    parts = []
    stale_sources = []
    now = _now()
    for source, item in sorted(latest.items()):
        when = _parse_iso(item.get("at"))
        age = (now - when).total_seconds() / 3600 if when else 999
        label = when.strftime("%d/%m %H:%M") if when else "desconhecido"
        parts.append(f"**{source}** {label}")
        if age > 1:
            stale_sources.append(source)
    st.caption("Últimas atualizações: " + " · ".join(parts))
    if stale_sources:
        st.warning(
            "Dados com mais de 1 hora: " + ", ".join(stale_sources) +
            ". Atualize antes de tomar decisões de SLA."
        )


def _render_metrics(state: dict, records: list[dict]) -> None:
    critical = 0
    within = 0
    ticketed = 0
    degraded = 0
    for record in records:
        if record.get("stale") or record.get("exception"):
            continue
        incident = _incident_for(state, record)
        if record.get("status") == "OFFLINE":
            if incident.get("workflow", "Sem chamado") != "Sem chamado":
                ticketed += 1
            elif (_record_age(record) or 0) >= SLA_HOURS:
                critical += 1
            else:
                within += 1
        elif record.get("status") == "DEGRADED":
            degraded += 1
    columns = st.columns(4)
    columns[0].metric("SLA vencido", critical)
    columns[1].metric("Dentro do SLA", within)
    columns[2].metric("Em atendimento", ticketed)
    columns[3].metric("Degradadas", degraded)


def _record_title(state: dict, record: dict) -> tuple[str, dict]:
    school = state["schools"].get(record.get("inep"), {})
    title = school.get("name") or record.get("source_name") or f"INEP {record.get('inep')}"
    return title, school


def _render_record_card(
    state: dict,
    store: MonitoringStore,
    record: dict,
    actor: str,
    conflicts: set[str],
) -> None:
    incident = _incident_for(state, record)
    title, school = _record_title(state, record)
    age = _record_age(record)
    sla_expired = age is not None and age >= SLA_HOURS
    workflow = incident.get("workflow", "Sem chamado")
    if record.get("stale"):
        accent, badge = "#64748b", "DADO DESATUALIZADO"
    elif record.get("exception"):
        accent, badge = "#64748b", "EXCEÇÃO"
    elif record.get("status") == "OFFLINE" and sla_expired and workflow == "Sem chamado":
        accent, badge = "#dc2626", "AÇÃO IMEDIATA"
    elif record.get("status") == "OFFLINE":
        accent, badge = "#ea580c", "OFFLINE"
    elif record.get("status") == "DEGRADED":
        accent, badge = "#ca8a04", "DEGRADADA"
    elif record.get("status") == "ALERTA":
        accent, badge = "#7c3aed", "ALERTA"
    else:
        accent, badge = "#64748b", "SEM DISPOSITIVOS"

    with st.container(border=True):
        st.markdown(
            f"""
            <div style="border-left:5px solid {accent};padding-left:12px;margin-bottom:8px">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:start">
                <div>
                  <div style="font-size:1.03rem;font-weight:750">{html.escape(title)}</div>
                  <div style="opacity:.72;font-size:.86rem">
                    INEP {html.escape(record.get('inep', ''))} ·
                    {html.escape(record.get('uf', ''))} ·
                    {html.escape(record.get('platform', ''))}
                  </div>
                </div>
                <span style="background:{accent};color:white;border-radius:999px;
                  padding:4px 9px;font-size:.7rem;font-weight:800;white-space:nowrap">
                  {badge}
                </span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        detail_cols = st.columns(3)
        detail_cols[0].caption("Situação")
        detail_cols[0].write(STATUS_LABELS.get(record.get("status"), record.get("status")))
        detail_cols[1].caption("Indisponibilidade")
        detail_cols[1].write(_format_duration(age) if age is not None else "Não aplicável")
        detail_cols[2].caption("Fluxo")
        detail_cols[2].write(workflow)

        if record.get("offline_since"):
            started = _parse_iso(record.get("offline_since"))
            source = record.get("time_source", "")
            if started:
                st.caption(f"Desde {started.strftime('%d/%m/%Y %H:%M')} · {source}")
        if record.get("total_devices") is not None:
            st.caption(
                f"Dispositivos offline: {record.get('offline_devices', 0)}/"
                f"{record.get('total_devices', 0)}"
            )
        if record.get("description"):
            st.caption(f"Classificação da fonte: {record.get('description')}")
        if record.get("exception_reason"):
            st.info(record.get("exception_reason"))
        if record.get("inep") in conflicts:
            st.warning("Conflito de fontes: esta escola também aparece online em outra plataforma.")
        if incident.get("ticket_number"):
            st.success(f"Chamado {incident['ticket_number']} · {workflow}")

        contact = state["contacts"].get(record.get("inep"), {})
        whatsapp_url = _whatsapp_url(contact, school)
        if whatsapp_url:
            st.link_button(
                "💬 Abrir WhatsApp do gestor",
                whatsapp_url,
                use_container_width=True,
            )
        else:
            st.button(
                "Cadastre o gestor para habilitar o WhatsApp",
                disabled=True,
                use_container_width=True,
                key=f"wa_disabled_{record.get('source_id')}_{record.get('inep')}",
            )

        with st.expander("✏️ Registrar chamado, gestor ou observação"):
            with st.form(f"monitoring_action_{record.get('source_id')}_{record.get('inep')}"):
                name = st.text_input("Nome oficial da escola", value=school.get("name", ""))
                municipality = st.text_input(
                    "Município",
                    value=school.get("municipality", ""),
                )
                manager_name = st.text_input(
                    "Nome do gestor",
                    value=contact.get("manager_name", ""),
                )
                phone = st.text_input(
                    "WhatsApp do gestor",
                    value=contact.get("phone", ""),
                    placeholder="Ex.: 11999999999",
                )
                workflow_index = (
                    WORKFLOW_OPTIONS.index(workflow) if workflow in WORKFLOW_OPTIONS else 0
                )
                selected_workflow = st.selectbox(
                    "Etapa do atendimento",
                    WORKFLOW_OPTIONS,
                    index=workflow_index,
                )
                ticket = st.text_input(
                    "Número do chamado",
                    value=incident.get("ticket_number", ""),
                )
                notes = st.text_area(
                    "Observações",
                    value=incident.get("notes", ""),
                    height=80,
                )
                submitted = st.form_submit_button("Salvar alterações", type="primary")
            if submitted:
                school.update(
                    {
                        "name": _clean(name),
                        "municipality": _clean(municipality),
                        "updated_at": _iso(),
                    }
                )
                state["schools"][record["inep"]] = school
                state["contacts"][record["inep"]] = {
                    "inep": record["inep"],
                    "manager_name": _clean(manager_name),
                    "phone": _phone(phone),
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
                if incident:
                    old_workflow = incident.get("workflow", "Sem chamado")
                    incident["workflow"] = selected_workflow
                    incident["ticket_number"] = _clean(ticket)
                    incident["notes"] = _clean(notes)
                    incident["updated_at"] = _iso()
                    if ticket and not incident.get("ticket_opened_at"):
                        incident["ticket_opened_at"] = _iso()
                    if selected_workflow in {"Gestor contatado", "Aguardando resposta"}:
                        incident["last_contact_at"] = _iso()
                    if old_workflow != selected_workflow:
                        _event(
                            state,
                            "workflow_changed",
                            actor,
                            inep=record["inep"],
                            incident_id=incident.get("id"),
                            from_status=old_workflow,
                            to_status=selected_workflow,
                        )
                _event(state, "record_updated", actor, inep=record["inep"])
                _save_state(store, state)
                st.rerun()


def _render_queue(state: dict, store: MonitoringStore, actor: str) -> None:
    records = [
        record for record in state["current"].values()
        if record.get("status") in ACTIVE_STATUSES
    ]
    conflicts = _conflicting_ineps(state)
    _render_metrics(state, records)

    st.markdown("#### O que precisa da sua atenção")
    view = st.radio(
        "Visão da fila",
        [
            "Ação necessária",
            "Em atendimento",
            "Outros sinais",
            "Exceções",
            "Tudo",
        ],
        horizontal=True,
        label_visibility="collapsed",
        key="monitoring_queue_view",
    )
    view_help = {
        "Ação necessária": (
            "Escolas totalmente offline e ainda sem chamado. As mais antigas aparecem primeiro."
        ),
        "Em atendimento": (
            "Ocorrências que já possuem chamado ou contato em andamento."
        ),
        "Outros sinais": (
            "Degradações parciais, alertas e escolas sem dispositivos. Não entram no SLA principal."
        ),
        "Exceções": (
            "Obras, renegociação, inviabilidade ou dados que desapareceram do último export."
        ),
        "Tudo": "Todas as ocorrências abertas, ainda ordenadas por prioridade.",
    }
    st.caption(view_help[view])

    filter_cols = st.columns([2, 1, 1])
    search = filter_cols[0].text_input(
        "Buscar",
        placeholder="INEP, escola ou município...",
        key="monitoring_search",
    )
    uf_filter = filter_cols[1].multiselect("UF", ["SP", "CE"], default=["SP", "CE"])
    platform_options = sorted({record.get("platform", "") for record in records})
    platform_filter = filter_cols[2].multiselect(
        "Plataforma",
        platform_options,
        default=platform_options,
    )

    filtered = []
    for record in records:
        incident = _incident_for(state, record)
        workflow = incident.get("workflow", "Sem chamado")
        is_exception = bool(record.get("exception") or record.get("stale"))
        if view == "Ação necessária" and not (
            record.get("status") == "OFFLINE"
            and workflow == "Sem chamado"
            and not is_exception
        ):
            continue
        if view == "Em atendimento" and not (
            record.get("status") == "OFFLINE"
            and workflow != "Sem chamado"
            and not is_exception
        ):
            continue
        if view == "Outros sinais" and not (
            record.get("status") in {"DEGRADED", "ALERTA", "SEM_DISPOSITIVO"}
            and not is_exception
        ):
            continue
        if view == "Exceções" and not is_exception:
            continue

        school = state["schools"].get(record.get("inep"), {})
        haystack = " ".join(
            [
                record.get("inep", ""),
                record.get("source_name", ""),
                school.get("name", ""),
                school.get("municipality", ""),
            ]
        ).upper()
        if search and search.upper() not in haystack:
            continue
        if record.get("uf") not in uf_filter:
            continue
        if record.get("platform") not in platform_filter:
            continue
        filtered.append(record)

    filtered.sort(key=lambda record: _priority(state, record))
    st.caption(f"{len(filtered)} ocorrência(s) nesta visão.")
    if not filtered:
        if view == "Ação necessária":
            st.success("Nenhuma escola offline está aguardando abertura de chamado.")
        else:
            st.info("Nenhuma ocorrência corresponde a esta visão e aos filtros atuais.")
        return

    columns = st.columns(2)
    for index, record in enumerate(filtered):
        with columns[index % 2]:
            _render_record_card(state, store, record, actor, conflicts)


def _render_bulk_contacts(state: dict, store: MonitoringStore, actor: str) -> None:
    records = [
        record for record in state["current"].values()
        if record.get("status") == "OFFLINE" and not record.get("stale")
    ]
    options = {}
    for record in sorted(records, key=lambda item: _priority(state, item)):
        school = state["schools"].get(record["inep"], {})
        label = (
            f"{record['inep']} · {school.get('name') or record.get('source_name')} · "
            f"{record.get('platform')}"
        )
        options[label] = record
    selected = st.multiselect(
        "Selecione as escolas para contato",
        list(options),
        key="monitoring_bulk_selection",
    )
    if not selected:
        st.info("Selecione escolas para montar a fila de WhatsApp.")
        return

    st.warning(
        "O WhatsApp Web exige confirmação humana. Abra e envie uma conversa por vez para "
        "evitar contatos incorretos."
    )
    for position, label in enumerate(selected, 1):
        record = options[label]
        school = state["schools"].get(record["inep"], {})
        contact = state["contacts"].get(record["inep"], {})
        with st.container(border=True):
            st.write(f"**{position}. {label}**")
            if not school.get("name"):
                st.caption("Cadastre o nome oficial da escola antes de enviar.")
            url = _whatsapp_url(contact, school)
            col_link, col_done = st.columns(2)
            if url:
                col_link.link_button("Abrir conversa", url, use_container_width=True)
            else:
                col_link.button(
                    "Telefone não cadastrado",
                    disabled=True,
                    use_container_width=True,
                    key=f"bulk_missing_{record['source_id']}_{record['inep']}",
                )
            if col_done.button(
                "Marcar como contatado",
                use_container_width=True,
                key=f"bulk_done_{record['source_id']}_{record['inep']}",
            ):
                incident = _incident_for(state, record)
                if incident:
                    incident["workflow"] = "Gestor contatado"
                    incident["last_contact_at"] = _iso()
                    incident["updated_at"] = _iso()
                    _event(
                        state,
                        "manager_contacted",
                        actor,
                        inep=record["inep"],
                        incident_id=incident.get("id"),
                    )
                    _save_state(store, state)
                    st.rerun()


def _render_history(state: dict) -> None:
    incident_rows = []
    for incident in state["incidents"].values():
        school = state["schools"].get(incident.get("inep"), {})
        incident_rows.append(
            {
                "INEP": incident.get("inep"),
                "Escola": school.get("name", ""),
                "Plataforma": incident.get("platform"),
                "Início": incident.get("opened_at"),
                "Encerramento": incident.get("closed_at"),
                "Situação": incident.get("status"),
                "Fluxo": incident.get("workflow"),
                "Chamado": incident.get("ticket_number"),
            }
        )
    if incident_rows:
        st.dataframe(
            pd.DataFrame(incident_rows).sort_values("Início", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("O histórico será preenchido após a primeira atualização das fontes.")

    st.markdown("#### Contatos cadastrados")
    contact_rows = []
    for inep, contact in state["contacts"].items():
        school = state["schools"].get(inep, {})
        contact_rows.append(
            {
                "INEP": inep,
                "Escola": school.get("name", ""),
                "Gestor": contact.get("manager_name", ""),
                "Telefone": contact.get("phone", ""),
                "Atualizado em": contact.get("updated_at", ""),
            }
        )
    if contact_rows:
        st.dataframe(pd.DataFrame(contact_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum gestor cadastrado.")


def _render_quality(state: dict) -> None:
    conflicts = _conflicting_ineps(state)
    stale = [record for record in state["current"].values() if record.get("stale")]
    latest = list(reversed(state["imports"][-20:]))
    metrics = st.columns(3)
    metrics[0].metric("Conflitos de fontes", len(conflicts))
    metrics[1].metric("Registros desatualizados", len(stale))
    metrics[2].metric(
        "Linhas ignoradas",
        sum(int(item.get("ignored", 0)) for item in latest),
    )
    if conflicts:
        st.warning("INEPs online e offline simultaneamente: " + ", ".join(sorted(conflicts)))
    if stale:
        st.caption(
            "Registros ausentes no último arquivo da respectiva fonte: " +
            ", ".join(sorted({record.get("inep", "") for record in stale}))
        )
    if latest:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": item.get("at"),
                        "Fonte": item.get("source_id"),
                        "Registros SP/CE": item.get("records"),
                        "Ignorados": item.get("ignored"),
                        "Responsável": item.get("actor"),
                    }
                    for item in latest
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_monitoring(
    ubiquiti_accounts: list,
    collect_ubiquiti,
    actor: str,
    configured_password: str = "",
    supabase_request=None,
    supabase_enabled: bool = False,
    supabase_table: str = "hub_monitoring_state",
) -> None:
    if not _render_access_gate(configured_password):
        return

    store = MonitoringStore(
        supabase_request=supabase_request,
        supabase_enabled=supabase_enabled,
        table=supabase_table,
    )
    if "monitoring_state" not in st.session_state:
        st.session_state.monitoring_state = store.load()
        st.session_state.monitoring_backend = store.backend
        st.session_state.monitoring_store_warning = store.last_warning
    state = st.session_state.monitoring_state

    title_col, action_col = st.columns([5, 1])
    with title_col:
        st.markdown("### 📡 Central de Monitoramento")
        st.caption(
            "Veja primeiro quem precisa de ação, registre o chamado e depois contate o gestor."
        )
    with action_col:
        if st.button("Sair do módulo", use_container_width=True):
            st.session_state.monitoring_authenticated = False
            st.rerun()

    warning = st.session_state.pop("monitoring_store_warning", "")
    if warning:
        st.warning(warning)
    backend = st.session_state.get("monitoring_backend", "local")
    if backend == "local":
        st.caption("Armazenamento atual: local. Configure a tabela do Supabase para persistência em nuvem.")
    else:
        st.caption("Armazenamento atual: Supabase sincronizado.")

    st.info(
        "**Fluxo rápido:** 1️⃣ envie os exports · 2️⃣ atualize as três plataformas · "
        "3️⃣ atenda a fila da ocorrência mais antiga para a mais recente"
    )
    _render_imports(state, store, actor, ubiquiti_accounts, collect_ubiquiti)
    _render_freshness(state)
    queue_tab, bulk_tab, history_tab, quality_tab = st.tabs(
        ["🚨 Fila de prioridade", "💬 WhatsApp em lote", "🗂️ Histórico", "⚠️ Pendências dos dados"]
    )
    with queue_tab:
        _render_queue(state, store, actor)
    with bulk_tab:
        _render_bulk_contacts(state, store, actor)
    with history_tab:
        _render_history(state)
    with quality_tab:
        _render_quality(state)
