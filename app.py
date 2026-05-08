import streamlit as st
import requests
import pandas as pd
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO

from modules.daily_report import render_daily_closing_admin, render_daily_report

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
CONFIG_FILE       = "config_contas.json"
CONFIG_PROVEDORES = "config_provedores.json"
BASE_URL          = "https://api.ui.com/v1"

st.set_page_config(
    page_title="Hub Redes — EACE",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root, .stApp {
    --hub-bg: var(--background-color, #f3f6fb);
    --hub-sidebar-bg: var(--secondary-background-color, #ffffff);
    --hub-surface: var(--secondary-background-color, #ffffff);
    --hub-surface-2: var(--background-color, #f8fafc);
    --hub-border: #d7dee9;
    --hub-text: var(--text-color, #111827);
    --hub-muted: color-mix(in srgb, var(--hub-text) 72%, transparent);
    --hub-muted-2: color-mix(in srgb, var(--hub-text) 58%, transparent);
    --hub-log-bg: var(--secondary-background-color, #f8fafc);
    --hub-scroll: #cbd5e1;
    --hub-accent: #ef4444;
    --hub-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    --hub-blue: #2563eb;
    --hub-green: #16a34a;
    --hub-red: #dc2626;
    --hub-yellow: #ca8a04;
    --hub-gray: #6b7280;
    --hub-teal: #0891b2;
    --hub-purple: #7c3aed;
}

@media (prefers-color-scheme: dark) {
    :root, .stApp {
        --hub-bg: #0f1117;
        --hub-sidebar-bg: #161b27;
        --hub-surface: #161b27;
        --hub-surface-2: #0a0d14;
        --hub-border: #273244;
        --hub-text: #f8fafc;
        --hub-muted: #cbd5e1;
        --hub-muted-2: #94a3b8;
        --hub-log-bg: #0a0d14;
        --hub-scroll: #475569;
        --hub-accent: #f87171;
        --hub-shadow: none;
        --hub-blue: #60a5fa;
        --hub-green: #4ade80;
        --hub-red: #f87171;
        --hub-yellow: #facc15;
        --hub-gray: #94a3b8;
        --hub-teal: #22d3ee;
        --hub-purple: #c084fc;
    }
}

html[data-theme="light"], body[data-theme="light"], .stApp[data-theme="light"],
[data-testid="stAppViewContainer"][data-theme="light"], [data-baseweb-theme="light"],
[data-theme="light"] {
    --hub-bg: #f3f6fb;
    --hub-sidebar-bg: #ffffff;
    --hub-surface: #ffffff;
    --hub-surface-2: #f8fafc;
    --hub-border: #d7dee9;
    --hub-text: #111827;
    --hub-muted: #475569;
    --hub-muted-2: #64748b;
    --hub-log-bg: #f8fafc;
    --hub-scroll: #cbd5e1;
    --hub-accent: #ef4444;
    --hub-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    --hub-blue: #2563eb;
    --hub-green: #16a34a;
    --hub-red: #dc2626;
    --hub-yellow: #ca8a04;
    --hub-gray: #6b7280;
    --hub-teal: #0891b2;
    --hub-purple: #7c3aed;
}

html[data-theme="dark"], body[data-theme="dark"], .stApp[data-theme="dark"],
[data-testid="stAppViewContainer"][data-theme="dark"], [data-baseweb-theme="dark"],
[data-theme="dark"], .dark {
    --hub-bg: #0f1117;
    --hub-sidebar-bg: #161b27;
    --hub-surface: #161b27;
    --hub-surface-2: #0a0d14;
    --hub-border: #273244;
    --hub-text: #f8fafc;
    --hub-muted: #cbd5e1;
    --hub-muted-2: #94a3b8;
    --hub-log-bg: #0a0d14;
    --hub-scroll: #475569;
    --hub-accent: #f87171;
    --hub-shadow: none;
    --hub-blue: #60a5fa;
    --hub-green: #4ade80;
    --hub-red: #f87171;
    --hub-yellow: #facc15;
    --hub-gray: #94a3b8;
    --hub-teal: #22d3ee;
    --hub-purple: #c084fc;
}

html, body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: var(--hub-bg) !important;
    color: var(--hub-text) !important;
}

[data-testid="stHeader"] {
    background: var(--hub-bg) !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] > div:first-child {
    background: var(--hub-sidebar-bg) !important;
    border-right: 1px solid var(--hub-border) !important;
}

.block-container { padding-top: 3.4rem !important; max-width: 1400px !important; }
* { word-break: break-word !important; overflow-wrap: break-word !important; }

.saas-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
    margin: 20px 0 24px 0;
}
.saas-grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin: 20px 0 24px 0;
}
.saas-card {
    background: var(--hub-surface);
    border: 1px solid var(--hub-border);
    border-radius: 10px;
    padding: 16px 18px;
    min-width: 0;
    box-shadow: var(--hub-shadow);
}
.saas-card-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--hub-muted);
    margin-bottom: 8px;
    font-family: Inter, sans-serif;
}
.saas-card-value {
    font-size: 28px;
    font-weight: 700;
    font-family: Inter, sans-serif;
    line-height: 1;
}
.saas-card-sub {
    font-size: 11px;
    color: var(--hub-muted-2);
    margin-top: 6px;
    font-family: Inter, sans-serif;
}
.c-blue   { color: var(--hub-blue); }
.c-green  { color: var(--hub-green); }
.c-red    { color: var(--hub-red); }
.c-yellow { color: var(--hub-yellow); }
.c-gray   { color: var(--hub-gray); }
.c-teal   { color: var(--hub-teal); }
.c-purple { color: var(--hub-purple); }

.page-title {
    font-family: Inter, sans-serif;
    font-size: 22px;
    font-weight: 700;
    color: var(--hub-text);
    margin: 0;
    line-height: 1.35;
    min-height: 32px;
    padding-top: 2px;
    overflow: visible;
}
.page-sub {
    font-family: Inter, sans-serif;
    font-size: 12px;
    color: var(--hub-muted);
    margin-top: 3px;
    letter-spacing: 0.5px;
    line-height: 1.35;
}

.sidebar-label {
    font-family: Inter, sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--hub-muted-2);
    margin: 16px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--hub-border);
}

.log-box {
    background: var(--hub-log-bg);
    border: 1px solid var(--hub-border);
    border-radius: 8px;
    padding: 12px 16px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.8;
    max-height: 160px;
    overflow-y: auto;
    margin: 12px 0;
}
.log-ok   { color: #22c55e; }
.log-err  { color: #ef4444; }
.log-info { color: #3b82f6; }

.ts-pill {
    display: inline-block;
    background: var(--hub-surface);
    border: 1px solid var(--hub-border);
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    color: #3b82f6;
    font-family: Inter, sans-serif;
    margin-bottom: 16px;
}

.saas-divider {
    border: none;
    border-top: 1px solid var(--hub-border);
    margin: 20px 0;
}

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--hub-scroll); border-radius: 99px; }

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMetricLabel"],
[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: var(--hub-text) !important;
}

[data-testid="stSidebar"] .sidebar-label {
    color: var(--hub-muted) !important;
}

[data-testid="stSidebar"] [data-baseweb="tag"] span {
    color: #ffffff !important;
}

[data-testid="stTabs"] button {
    color: var(--hub-muted) !important;
}

[data-testid="stTabs"] button p {
    color: var(--hub-muted) !important;
    font-weight: 600;
}

[data-testid="stTabs"] button[aria-selected="true"] p {
    color: var(--hub-accent) !important;
}

[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: var(--hub-accent) !important;
}

h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    color: var(--hub-text);
}

[data-testid="stAlert"] {
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PERSISTÊNCIA
# ═══════════════════════════════════════════════════════════════
def salvar_contas(contas):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(contas, f, indent=2)
    except Exception:
        pass

# Prefixo usado para identificar chaves de conta nos Secrets raiz
_CONTA_PREFIXOS = ("Conta_", "conta_", "CONTA_", "admin")

def carregar_contas():
    """
    Lê as contas dos Streamlit Secrets.
    Suporta quatro formatos:

    Formato 1 — seção [contas] (ideal):
        [contas]
        Conta_AC1 = "chave1"

    Formato 2 — chaves na raiz com prefixo Conta_:
        Conta_AC1 = "chave1"
        admin0    = "chave2"

    Formato 3 — JSON na chave contas_json:
        contas_json = '[{"apelido":"Conta AC1","api_key":"chave1"}]'

    Formato 4 — fallback arquivo local (desenvolvimento).
    """
    # Formato 1: seção [contas]
    try:
        if "contas" in st.secrets:
            sec = st.secrets["contas"]
            resultado = [
                {"apelido": str(k), "api_key": str(v)}
                for k, v in sec.items()
                if str(v).strip()
            ]
            if resultado:
                return resultado
    except Exception:
        pass

    # Formato 2: chaves soltas na raiz que parecem contas Ubiquiti
    # O Streamlit Cloud às vezes não processa seções TOML corretamente
    try:
        todas = dict(st.secrets)
        contas_raiz = []
        chaves_ignorar = {"contas_json"}
        for k, v in todas.items():
            if k in chaves_ignorar:
                continue
            v_str = str(v).strip()
            # Considera conta se: começa com prefixo conhecido OU o valor parece uma API key
            # (string sem espaços com 20+ chars)
            eh_prefixo = any(k.startswith(p) for p in _CONTA_PREFIXOS)
            eh_apikey  = len(v_str) >= 20 and " " not in v_str and isinstance(v, str)
            if eh_prefixo or eh_apikey:
                contas_raiz.append({"apelido": k, "api_key": v_str})
        if contas_raiz:
            return contas_raiz
    except Exception:
        pass

    # Formato 3: JSON na chave contas_json
    try:
        if "contas_json" in st.secrets:
            return json.loads(st.secrets["contas_json"])
    except Exception:
        pass

    # Formato 4: fallback arquivo local
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def salvar_provedores(provs: dict) -> bool:
    try:
        with open(CONFIG_PROVEDORES, "w", encoding="utf-8") as f:
            json.dump(provs, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar provedores: {e}")
        return False

def carregar_provedores() -> dict:
    if os.path.exists(CONFIG_PROVEDORES):
        try:
            with open(CONFIG_PROVEDORES, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

# ═══════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════
for k, v in {
    "contas":            None,
    "provedores":        None,
    "df_resultado":      None,
    "relatorio":         [],
    "ultima_consulta":   None,
    "df_inventario":     None,
    "inv_ultima_coleta": None,
    "daily_report_current": None,
    "daily_report_authenticated": False,
}.items():
    if k not in st.session_state:
        if k == "contas":
            st.session_state[k] = carregar_contas()
        elif k == "provedores":
            st.session_state[k] = carregar_provedores()
        else:
            st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════
# API UBIQUITI
# ═══════════════════════════════════════════════════════════════
def get_paginated_hosts(api_key: str) -> list:
    items, next_token = [], None
    while True:
        params = {"pageSize": 200}
        if next_token:
            params["nextToken"] = next_token
        r = requests.get(
            f"{BASE_URL}/hosts",
            headers={"X-API-KEY": api_key, "Accept": "application/json"},
            params=params, timeout=25
        )
        if r.status_code == 401: raise Exception("Chave inválida (401)")
        if r.status_code == 429: raise Exception("Rate limit (429) — aguarde 1 min")
        if r.status_code != 200: raise Exception(f"Erro HTTP {r.status_code}")
        data       = r.json()
        batch      = data.get("data", [])
        if not batch: break
        items.extend(batch)
        next_token = data.get("nextToken", "")
        if not next_token: break
        time.sleep(0.3)
    return items

def extrair_host(host: dict) -> dict:
    rep    = host.get("reportedState", {})
    nome   = str(rep.get("name", host.get("name", ""))).strip()
    estado = str(rep.get("state", "disconnected")).lower()
    ip     = str(host.get("ipAddress", rep.get("ip", "—"))).strip()
    isp    = "—"
    wans   = rep.get("wans", [])
    if isinstance(wans, list) and wans and isinstance(wans[0], dict):
        isp = wans[0].get("ispInfo", {}).get("name", "—")
    uptime  = "—"
    periods = rep.get("internetIssues5min", {}).get("periods", [])
    if isinstance(periods, list) and periods:
        last = periods[-1]
        if isinstance(last, dict) and last.get("wanUptime") is not None:
            uptime = f"{last['wanUptime']:.1f}%"
    return {"nome": nome, "estado": estado, "ip": ip, "isp": isp, "uptime": uptime}

def buscar_ineps_ubiquiti(api_key: str, apelido: str, ineps: set) -> dict:
    out   = {}
    hosts = get_paginated_hosts(api_key)
    for h in hosts:
        d    = extrair_host(h)
        nome = d["nome"].upper()
        for inep in ineps:
            if str(inep).strip().upper() in nome:
                status_raw = "ONLINE" if d["estado"] == "connected" else "OFFLINE"
                out[str(inep).strip()] = {
                    "Status Rede":     f"UBIQUITI - {status_raw}",
                    "Plataforma":      "UBIQUITI",
                    "Uptime WAN":      d["uptime"],
                    "ISP":             d["isp"],
                    "Conta":           apelido,
                    "IP Externo":      d["ip"],
                    "Nome no Console": d["nome"],
                }
                break
    return out

def coletar_todos_hosts_ubiquiti(contas: list) -> tuple:
    """Retorna TODOS os hosts de todas as contas, sem filtro por INEP."""
    rows  = []
    erros = []
    for c in contas:
        if not c.get("api_key", "").strip():
            continue
        try:
            hosts = get_paginated_hosts(c["api_key"])
            for h in hosts:
                d      = extrair_host(h)
                inep   = extrair_inep_do_nome(d["nome"])
                status = "ONLINE" if d["estado"] == "connected" else "OFFLINE"
                rows.append({
                    "INEP":            inep or "—",
                    "Nome no Console": d["nome"],
                    "Status Rede":     f"UBIQUITI - {status}",
                    "Plataforma":      "UBIQUITI",
                    "Uptime WAN":      d["uptime"],
                    "ISP":             d["isp"],
                    "Conta":           c["apelido"],
                    "IP Externo":      d["ip"],
                })
        except Exception as e:
            erros.append(f"{c['apelido']}: {e}")
    return rows, erros

def coletar_todos_isps_ubiquiti(contas: list) -> tuple:
    isps  = set()
    erros = []
    for c in contas:
        if not c.get("api_key", "").strip():
            continue
        try:
            hosts = get_paginated_hosts(c["api_key"])
            for h in hosts:
                d = extrair_host(h)
                if d["isp"] and d["isp"] not in ("—", ""):
                    isps.add(d["isp"].strip())
        except Exception as e:
            erros.append(f"{c['apelido']}: {e}")
    return isps, erros

def testar_conta(api_key: str):
    try:
        r = requests.get(
            f"{BASE_URL}/hosts",
            headers={"X-API-KEY": api_key}, params={"pageSize": 1}, timeout=10
        )
        if r.status_code == 200:
            return True, f"OK — {len(r.json().get('data', []))} host(s) retornado(s)"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

# ═══════════════════════════════════════════════════════════════
# OMADA — PROCESSAMENTO DO EXPORT
# ═══════════════════════════════════════════════════════════════
def extrair_inep_do_nome(nome: str):
    matches = re.findall(r'\b(\d{8})\b', str(nome))
    return matches[-1] if matches else None

def processar_export_omada(df_omada: pd.DataFrame) -> dict:
    resultado = {}
    df_omada.columns = [str(c).strip().upper() for c in df_omada.columns]
    if "NAME" not in df_omada.columns or "STATUS" not in df_omada.columns:
        return resultado
    for _, row in df_omada.iterrows():
        nome   = str(row.get("NAME", "")).strip()
        status = str(row.get("STATUS", "")).strip().upper()
        inep   = extrair_inep_do_nome(nome)
        if not inep:
            continue
        status_raw = "ONLINE" if status == "ONLINE" else "OFFLINE"
        ip_externo = "—"
        if "IP ADDRESS" in df_omada.columns:
            ips = str(row.get("IP ADDRESS", "")).split(",")
            ip_externo = ips[-1].strip() if ips else "—"
        resultado[inep] = {
            "Status Rede":     f"OMADA - {status_raw}",
            "Plataforma":      "OMADA",
            "Uptime WAN":      "—",
            "ISP":             "—",
            "Conta":           "Omada Cloud",
            "IP Externo":      ip_externo,
            "Nome no Console": nome,
        }
    return resultado

def processar_export_omada_completo(df_omada: pd.DataFrame) -> list:
    """Versão para inventário — retorna lista de todas as linhas, não só cruzadas."""
    rows = []
    df_omada.columns = [str(c).strip().upper() for c in df_omada.columns]
    if "NAME" not in df_omada.columns or "STATUS" not in df_omada.columns:
        return rows
    for _, row in df_omada.iterrows():
        nome   = str(row.get("NAME", "")).strip()
        status = str(row.get("STATUS", "")).strip().upper()
        inep   = extrair_inep_do_nome(nome)
        status_raw = "ONLINE" if status == "ONLINE" else "OFFLINE"
        ip_externo = "—"
        if "IP ADDRESS" in df_omada.columns:
            ips = str(row.get("IP ADDRESS", "")).split(",")
            ip_externo = ips[-1].strip() if ips else "—"
        rows.append({
            "INEP":            inep or "—",
            "Nome no Console": nome,
            "Status Rede":     f"OMADA - {status_raw}",
            "Plataforma":      "OMADA",
            "Uptime WAN":      "—",
            "ISP":             "—",
            "Conta":           "Omada Cloud",
            "IP Externo":      ip_externo,
        })
    return rows

# ═══════════════════════════════════════════════════════════════
# ZYXEL — PROCESSAMENTO DO EXPORT CSV
# ═══════════════════════════════════════════════════════════════
ZYXEL_STATUS_MAP = {
    "OK":                  "ONLINE",
    "DEVICE ALERTED":      "ALERTA",
    "DEVICE OFFLINE":      "OFFLINE",
    "DEVICES UNREACHABLE": "OFFLINE",
    "NO DEVICES":          "SEM DISPOSITIVO",
}

def processar_export_zyxel(df_zyxel: pd.DataFrame) -> dict:
    resultado = {}
    col_map   = {}
    for col in df_zyxel.columns:
        cu = str(col).strip().upper()
        if cu in ("ESTADO", "STATUS"):               col_map["status"]      = col
        elif cu in ("NOME", "NAME"):                  col_map["nome"]        = col
        elif cu in ("DISPOSITIVOS OFFLINE", "OFFLINE DEVICES"): col_map["offline"] = col
        elif cu in ("DISPOSITIVOS", "DEVICES"):       col_map["total_dev"]   = col
        elif cu in ("% OFFLINE", "% OFFLINE DEVICES"):col_map["pct_offline"] = col
    if "status" not in col_map or "nome" not in col_map:
        return resultado
    for _, row in df_zyxel.iterrows():
        nome           = str(row[col_map["nome"]]).strip()
        status_raw     = str(row[col_map["status"]]).strip().upper()
        inep           = extrair_inep_do_nome(nome)
        if not inep: continue
        status_interno = ZYXEL_STATUS_MAP.get(status_raw, "OFFLINE")
        total_dev      = str(row.get(col_map.get("total_dev",  ""), "—")).strip()
        offline_dev    = str(row.get(col_map.get("offline",    ""), "—")).strip()
        pct_offline    = str(row.get(col_map.get("pct_offline",""), "—")).strip()
        resultado[inep] = {
            "Status Rede":       f"ZYXEL - {status_interno}",
            "Plataforma":        "ZYXEL",
            "Uptime WAN":        f"{pct_offline} offline" if pct_offline != "—" else "—",
            "ISP":               "—",
            "Conta":             "Zyxel Nebula",
            "IP Externo":        "—",
            "Nome no Console":   nome,
            "Devices (tot/off)": f"{total_dev} / {offline_dev}",
        }
    return resultado

def processar_export_zyxel_completo(df_zyxel: pd.DataFrame) -> list:
    """Versão para inventário — retorna todas as linhas."""
    rows    = []
    col_map = {}
    for col in df_zyxel.columns:
        cu = str(col).strip().upper()
        if cu in ("ESTADO", "STATUS"):                col_map["status"]      = col
        elif cu in ("NOME", "NAME"):                   col_map["nome"]        = col
        elif cu in ("DISPOSITIVOS OFFLINE", "OFFLINE DEVICES"): col_map["offline"] = col
        elif cu in ("DISPOSITIVOS", "DEVICES"):        col_map["total_dev"]   = col
        elif cu in ("% OFFLINE", "% OFFLINE DEVICES"): col_map["pct_offline"] = col
    if "status" not in col_map or "nome" not in col_map:
        return rows
    for _, row in df_zyxel.iterrows():
        nome           = str(row[col_map["nome"]]).strip()
        status_raw     = str(row[col_map["status"]]).strip().upper()
        inep           = extrair_inep_do_nome(nome)
        status_interno = ZYXEL_STATUS_MAP.get(status_raw, "OFFLINE")
        total_dev      = str(row.get(col_map.get("total_dev",  ""), "—")).strip()
        offline_dev    = str(row.get(col_map.get("offline",    ""), "—")).strip()
        pct_offline    = str(row.get(col_map.get("pct_offline",""), "—")).strip()
        rows.append({
            "INEP":              inep or "—",
            "Nome no Console":   nome,
            "Status Rede":       f"ZYXEL - {status_interno}",
            "Plataforma":        "ZYXEL",
            "Uptime WAN":        f"{pct_offline} offline" if pct_offline != "—" else "—",
            "ISP":               "—",
            "Conta":             "Zyxel Nebula",
            "IP Externo":        "—",
            "Devices (tot/off)": f"{total_dev} / {offline_dev}",
        })
    return rows

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
COR_STATUS = {
    "UBIQUITI - ONLINE":       "background:#052e16; color:#22c55e; font-weight:600",
    "UBIQUITI - OFFLINE":      "background:#2d0a0a; color:#ef4444; font-weight:600",
    "OMADA - ONLINE":          "background:#0a1f2e; color:#38bdf8; font-weight:600",
    "OMADA - OFFLINE":         "background:#2d1a0a; color:#fb923c; font-weight:600",
    "ZYXEL - ONLINE":          "background:#1a0a2e; color:#a855f7; font-weight:600",
    "ZYXEL - OFFLINE":         "background:#2d0a1f; color:#f472b6; font-weight:600",
    "ZYXEL - ALERTA":          "background:#2d2200; color:#facc15; font-weight:600",
    "ZYXEL - SEM DISPOSITIVO": "background:#1a1f2e; color:#6b7280; font-weight:600",
    "NÃO ENCONTRADO":          "background:#1a1f2e; color:#374151; font-weight:600",
}

def cor_status(val):
    return COR_STATUS.get(str(val).strip(), "")

def cor_estado(val):
    if val == "connected":    return "color:#22c55e; font-weight:600"
    if val == "disconnected": return "color:#ef4444; font-weight:600"
    return ""

def to_xlsx(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Resultado")
    return buf.getvalue()

def deduplicar_por_inep(todos: dict) -> dict:
    """
    Recebe dict {inep: dados} já montado e garante que cada INEP
    fique com a entrada de maior qualidade.
    Prioridade: ONLINE > tem ISP > tem IP > tem Uptime.
    INEPs '—' são ignorados (não há como deduplicar sem chave).
    """
    def _score(dados):
        s = 0
        if "ONLINE" in str(dados.get("Status Rede", "")): s += 100
        if str(dados.get("ISP",        "—")) not in ("—", "", "nan"): s += 10
        if str(dados.get("IP Externo", "—")) not in ("—", "", "nan"): s += 5
        if str(dados.get("Uptime WAN", "—")) not in ("—", "", "nan"): s += 1
        return s

    # Agrupa candidatos por INEP
    candidatos: dict[str, list] = {}
    for inep, dados in todos.items():
        candidatos.setdefault(inep, []).append(dados)

    resultado = {}
    for inep, lista in candidatos.items():
        melhor = max(lista, key=_score)
        resultado[inep] = melhor
    return resultado


def deduplicar_df_por_inep(df: pd.DataFrame) -> tuple:
    """
    Versão DataFrame para o Inventário Geral.
    Retorna (df_deduplicado, n_removidos).
    """
    def _score_row(row):
        s = 0
        if "ONLINE" in str(row.get("Status Rede", "")): s += 100
        if str(row.get("ISP",        "—")) not in ("—", "", "nan"): s += 10
        if str(row.get("IP Externo", "—")) not in ("—", "", "nan"): s += 5
        if str(row.get("Uptime WAN", "—")) not in ("—", "", "nan"): s += 1
        return s

    sem_inep = df[df["INEP"] == "—"].copy()
    com_inep = df[df["INEP"] != "—"].copy()
    if not com_inep.empty:
        com_inep["_score"] = com_inep.apply(_score_row, axis=1)
        com_inep = (
            com_inep
            .sort_values("_score", ascending=False)
            .drop_duplicates(subset=["INEP"], keep="first")
            .drop(columns=["_score"])
        )
    antes     = len(df)
    df_result = pd.concat([com_inep, sem_inep], ignore_index=True)
    return df_result, antes - len(df_result)


def mesclar_isps_novos(isps_novos: set) -> int:
    provs = dict(st.session_state.provedores)
    novos = 0
    for isp in isps_novos:
        isp = str(isp).strip()
        if isp and isp not in ("—", "nan", "") and isp not in provs:
            provs[isp] = {"telefone": "", "celular": "", "observacao": ""}
            novos += 1
    if novos > 0:
        st.session_state.provedores = provs
        salvar_provedores(provs)
    return novos

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    # Contas carregadas dos Secrets — sem exposição de chaves na UI
    validas = [c for c in st.session_state.contas if c.get("api_key", "").strip()]

    st.markdown('<div class="sidebar-label">Contas Ubiquiti</div>', unsafe_allow_html=True)
    if validas:
        sel  = st.multiselect(
            "Selecionar contas:",
            [c["apelido"] for c in validas],
            default=[c["apelido"] for c in validas],
            label_visibility="collapsed"
        )
        alvo = [c for c in validas if c["apelido"] in sel]
    else:
        st.warning("Nenhuma conta configurada nos Secrets.")
        alvo = []

        # Diagnóstico — ajuda a identificar problema de formato
        with st.expander("🔍 Diagnóstico Secrets", expanded=True):
            try:
                todas = dict(st.secrets)
                chaves = list(todas.keys())
                st.caption(f"Chaves encontradas: `{chaves}`")
                if "contas" in st.secrets:
                    st.caption(f"✅ Seção [contas] encontrada com {len(dict(st.secrets['contas']))} entradas.")
                else:
                    st.caption("⚠️ Seção [contas] não encontrada — tentando ler chaves soltas na raiz.")
                    candidatas = [k for k in chaves if any(k.startswith(p) for p in _CONTA_PREFIXOS)
                                  or (len(str(todas[k])) >= 20 and " " not in str(todas[k]))]
                    st.caption(f"Chaves candidatas a conta: `{candidatas}`")
                    if candidatas:
                        st.caption(f"✅ {len(candidatas)} conta(s) detectada(s) pelo formato alternativo.")
                    else:
                        st.caption("❌ Nenhuma conta detectada. Use o formato abaixo:")
                        st.code("[contas]\nConta_AC1 = \"sua_chave\"", language="toml")
            except Exception as ex:
                st.caption(f"Erro ao ler Secrets: {ex}")

    render_daily_closing_admin()

    st.markdown('<div class="sidebar-label">Status</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)
    ca.metric("Contas",  len(validas))
    cb.metric("Ativas",  len(alvo))
    if st.session_state.ultima_consulta:
        st.caption(f"Última consulta: {st.session_state.ultima_consulta}")

    st.markdown('<div class="sidebar-label">Provedores</div>', unsafe_allow_html=True)
    st.metric("Cadastrados", len(st.session_state.provedores))

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════
st.markdown(
    '<p class="page-title">Hub Redes — EACE</p>'
    '<p class="page-sub">Monitor de Conectividade · Ubiquiti · Omada · Zyxel · Escolas Brasileiras</p>',
    unsafe_allow_html=True
)
st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
t1, t2, t3, t4, t5, t6, t7 = st.tabs([
    "📄 Relatório Diário",
    "🌐 Inventário Geral",
    "🏢 Provedores",
    "🔍 Busca Manual",
    "🛠️ Raio-X da Conta",
    "🩺 Diagnóstico",
    "ℹ️ Ajuda",
])

# ─────────────────────────────────────────
# ABA 1 - RELATORIO DIARIO
# ─────────────────────────────────────────
with t1:
    render_daily_report(st.session_state.daily_report_current)

# ─────────────────────────────────────────
# ABA 2 - INVENTARIO GERAL
# ─────────────────────────────────────────

# ─────────────────────────────────────────
with t2:
    st.markdown("### 🌐 Inventário Geral de Escolas")
    st.write(
        "Coleta **todas** as escolas de todas as plataformas, independente de chamados abertos. "
        "Ubiquiti é buscado via API. Omada e Zyxel via upload dos exports."
    )

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    # Uploads Omada e Zyxel para o inventário
    col_inv_om, col_inv_zy = st.columns(2)
    with col_inv_om:
        st.caption("🔵 **Omada** — export do portal On Premise Systems")
        inv_omada = st.file_uploader("Export Omada (.xlsx)", type=["xlsx"], key="inv_omada")
        if inv_omada:
            df_inv_om_prev = pd.read_excel(inv_omada)
            inv_omada.seek(0)
            st.caption(f"{len(df_inv_om_prev)} controllers carregados")
    with col_inv_zy:
        st.caption("🟣 **Zyxel** — export CSV do Nebula (Overview → Sites)")
        inv_zyxel = st.file_uploader("Export Zyxel (.csv)", type=["csv"], key="inv_zyxel")
        if inv_zyxel:
            df_inv_zy_prev = pd.read_csv(inv_zyxel)
            inv_zyxel.seek(0)
            st.caption(f"{len(df_inv_zy_prev)} sites carregados")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    col_btn_inv, col_reset_inv, _ = st.columns([2, 2, 4])
    with col_btn_inv:
        if st.button("🔄 Coletar Inventário Completo", type="primary", use_container_width=True):
            if not alvo and not inv_omada and not inv_zyxel:
                st.warning("Configure ao menos uma fonte: conta Ubiquiti, export Omada ou export Zyxel.")
            else:
                todas_linhas = []
                log_inv      = []
                t0           = time.time()

                # ── Ubiquiti — todas as contas em paralelo ──
                if alvo:
                    prog_inv = st.progress(0.0, text="Coletando Ubiquiti...")
                    with ThreadPoolExecutor(max_workers=min(len(alvo), 5)) as ex:
                        futs_inv = {
                            ex.submit(coletar_todos_hosts_ubiquiti, [c]): c["apelido"]
                            for c in alvo
                        }
                        done_inv = 0
                        for fut in as_completed(futs_inv):
                            ap = futs_inv[fut]
                            try:
                                rows_c, erros_c = fut.result()
                                todas_linhas.extend(rows_c)
                                for e in erros_c: log_inv.append(("err", e))
                                log_inv.append(("ok", f"Ubiquiti {ap}: {len(rows_c)} host(s)"))
                            except Exception as e:
                                log_inv.append(("err", f"Ubiquiti {ap}: {e}"))
                            done_inv += 1
                            prog_inv.progress(done_inv / len(alvo), text=f"Ubiquiti {done_inv}/{len(alvo)}...")
                    prog_inv.progress(1.0, text="Ubiquiti concluído.")

                # ── Omada ──
                if inv_omada:
                    try:
                        inv_omada.seek(0)
                        rows_om = processar_export_omada_completo(pd.read_excel(inv_omada))
                        todas_linhas.extend(rows_om)
                        log_inv.append(("ok", f"Omada: {len(rows_om)} controller(s)"))
                    except Exception as e:
                        log_inv.append(("err", f"Omada: {e}"))

                # ── Zyxel ──
                if inv_zyxel:
                    try:
                        inv_zyxel.seek(0)
                        rows_zy = processar_export_zyxel_completo(pd.read_csv(inv_zyxel))
                        todas_linhas.extend(rows_zy)
                        log_inv.append(("ok", f"Zyxel: {len(rows_zy)} site(s)"))
                    except Exception as e:
                        log_inv.append(("err", f"Zyxel: {e}"))

                if todas_linhas:
                    df_inv = pd.DataFrame(todas_linhas)

                    # Deduplicação centralizada
                    df_inv, removidos = deduplicar_df_por_inep(df_inv)
                    if removidos > 0:
                        log_inv.append(("ok", f"Deduplicação: {removidos} duplicata(s) removida(s)"))

                    # Garante ordem das colunas
                    col_order = ["INEP","Nome no Console","Status Rede","Plataforma",
                                 "Uptime WAN","ISP","Conta","IP Externo"]
                    df_inv = df_inv[[c for c in col_order if c in df_inv.columns] +
                                    [c for c in df_inv.columns if c not in col_order]]
                    st.session_state.df_inventario     = df_inv
                    st.session_state.inv_ultima_coleta = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    st.success(f"Inventário coletado em {time.time()-t0:.1f}s — {len(df_inv):,} escola(s) únicas.")

                    # Log
                    html_log = "".join(
                        f'<div class="log-{"ok" if tp=="ok" else "err"}">{"✓" if tp=="ok" else "✗"}  {m}</div>'
                        for tp, m in log_inv
                    )
                    st.markdown(f'<div class="log-box">{html_log}</div>', unsafe_allow_html=True)
                else:
                    st.error("Nenhuma escola coletada. Verifique as fontes.")

    with col_reset_inv:
        if st.button("🗑️ Limpar Inventário", use_container_width=True):
            st.session_state.df_inventario     = None
            st.session_state.inv_ultima_coleta = None
            st.rerun()

    # ── Exibição do inventário ──
    if st.session_state.df_inventario is not None:
        df_inv = st.session_state.df_inventario
        st.markdown(f'<div class="ts-pill">🕐 {st.session_state.inv_ultima_coleta}</div>', unsafe_allow_html=True)

        # Cards
        total_inv   = len(df_inv)
        online_inv  = df_inv["Status Rede"].str.contains("ONLINE",   na=False).sum()
        offline_inv = df_inv["Status Rede"].str.contains("OFFLINE",  na=False).sum()
        n_ubi_inv   = df_inv["Status Rede"].str.contains("UBIQUITI", na=False).sum()
        n_om_inv    = df_inv["Status Rede"].str.contains("OMADA",    na=False).sum()
        n_zy_inv    = df_inv["Status Rede"].str.contains("ZYXEL",    na=False).sum()

        st.markdown(f"""
        <div class="saas-grid">
          <div class="saas-card"><div class="saas-card-label">Total escolas</div>
            <div class="saas-card-value c-blue">{total_inv:,}</div><div class="saas-card-sub">todas as plataformas</div></div>
          <div class="saas-card"><div class="saas-card-label">Online</div>
            <div class="saas-card-value c-green">{online_inv:,}</div>
            <div class="saas-card-sub">{f"{online_inv/total_inv*100:.0f}%" if total_inv else "—"}</div></div>
          <div class="saas-card"><div class="saas-card-label">Offline / Alerta</div>
            <div class="saas-card-value c-red">{offline_inv:,}</div>
            <div class="saas-card-sub">{f"{offline_inv/total_inv*100:.0f}%" if total_inv else "—"}</div></div>
          <div class="saas-card"><div class="saas-card-label">Ubiquiti</div>
            <div class="saas-card-value c-blue">{n_ubi_inv:,}</div><div class="saas-card-sub">hosts</div></div>
          <div class="saas-card"><div class="saas-card-label">Omada</div>
            <div class="saas-card-value c-teal">{n_om_inv:,}</div><div class="saas-card-sub">controllers</div></div>
          <div class="saas-card"><div class="saas-card-label">Zyxel</div>
            <div class="saas-card-value c-purple">{n_zy_inv:,}</div><div class="saas-card-sub">sites</div></div>
        </div>""", unsafe_allow_html=True)

        # Pesquisa e filtros
        with st.expander("⚙️ Filtros e Pesquisa", expanded=True):
            pesq_col, f1_inv, f2_inv, f3_inv = st.columns([2, 1, 1, 1])

            pesq = pesq_col.text_input(
                "🔎 Pesquisar INEP ou nome da escola:",
                placeholder="Ex: 23000066 ou ACARAÚ",
                key="inv_pesq"
            )
            op_plat_inv = sorted(df_inv["Plataforma"].dropna().unique().tolist())
            op_st_inv   = sorted(df_inv["Status Rede"].dropna().unique().tolist())
            op_isp_inv  = sorted([v for v in df_inv["ISP"].dropna().unique().tolist() if v not in ("—","")])

            fp_inv  = f1_inv.multiselect("Plataforma", op_plat_inv, default=[], key="fp_inv")
            fs_inv  = f2_inv.multiselect("Status",     op_st_inv,   default=[], key="fs_inv")
            fi_inv  = f3_inv.multiselect("ISP",        op_isp_inv,  default=[], key="fi_inv")

        df_inv_f = df_inv.copy()

        # Pesquisa textual em INEP e Nome
        if pesq.strip():
            mask = (
                df_inv_f["INEP"].astype(str).str.contains(pesq.strip(), case=False, na=False) |
                df_inv_f["Nome no Console"].astype(str).str.contains(pesq.strip(), case=False, na=False)
            )
            df_inv_f = df_inv_f[mask]

        if fp_inv: df_inv_f = df_inv_f[df_inv_f["Plataforma"].isin(fp_inv)]
        if fs_inv: df_inv_f = df_inv_f[df_inv_f["Status Rede"].isin(fs_inv)]
        if fi_inv: df_inv_f = df_inv_f[df_inv_f["ISP"].isin(fi_inv)]

        st.dataframe(
            df_inv_f.style.map(cor_status, subset=["Status Rede"]),
            use_container_width=True,
            height=520
        )
        st.caption(f"{len(df_inv_f):,} de {len(df_inv):,} escolas exibidas")

        ce1, ce2, _ = st.columns([1, 1, 3])
        ce1.download_button(
            "⬇️ Exportar filtrado",
            to_xlsx(df_inv_f),
            f"inventario_filtrado_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        ce2.download_button(
            "⬇️ Exportar completo",
            to_xlsx(df_inv),
            f"inventario_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Clique em **Coletar Inventário Completo** para carregar todas as escolas.")

# ─────────────────────────────────────────
# ABA 3 — PROVEDORES
# ─────────────────────────────────────────
with t3:
    st.markdown("### Cadastro de Provedores (ISPs)")
    st.write(
        "ISPs detectados via API Ubiquiti são adicionados automaticamente a cada importação. "
        "Edite telefone, celular e observações conforme necessário. "
        "Dados existentes nunca são sobrescritos numa nova importação."
    )
    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    col_sync, col_info = st.columns([2, 4])
    with col_sync:
        if st.button("🔄 Buscar ISPs via API Ubiquiti", type="primary", use_container_width=True):
            validas_sync = [c for c in st.session_state.contas if c["api_key"].strip()]
            if not validas_sync:
                st.error("Nenhuma conta Ubiquiti configurada.")
            else:
                with st.spinner(f"Varrendo {len(validas_sync)} conta(s)..."):
                    isps_api, erros_api = coletar_todos_isps_ubiquiti(validas_sync)
                for e in erros_api: st.warning(f"Erro: {e}")
                novos = mesclar_isps_novos(isps_api)
                if novos > 0:
                    st.success(f"{novos} novo(s) ISP(s) adicionado(s). Total na API: {len(isps_api)}.")
                else:
                    st.info(f"{len(isps_api)} ISP(s) encontrado(s) — nenhum novo.")
                st.session_state.provedores = carregar_provedores()
                st.rerun()
    with col_info:
        st.caption("Varre todos os hosts de todas as contas Ubiquiti e coleta os ISPs. ISPs existentes não são alterados.")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    lista_prov = [
        {"Provedor": isp, "Telefone": d.get("telefone",""), "Celular": d.get("celular",""), "Observação": d.get("observacao","")}
        for isp, d in st.session_state.provedores.items()
    ]
    df_prov = pd.DataFrame(lista_prov) if lista_prov else pd.DataFrame(columns=["Provedor","Telefone","Celular","Observação"])

    edited_df = st.data_editor(
        df_prov, num_rows="dynamic", use_container_width=True, key="editor_provedores",
        column_config={
            "Provedor":   st.column_config.TextColumn("Provedor (Nome Exato)", required=True),
            "Telefone":   st.column_config.TextColumn("Telefone Fixo"),
            "Celular":    st.column_config.TextColumn("Celular / WhatsApp"),
            "Observação": st.column_config.TextColumn("Observação"),
        }
    )

    if st.button("💾 Salvar Alterações", type="primary"):
        novo_dict = {}
        for _, row in edited_df.iterrows():
            nome_prov = str(row.get("Provedor","")).strip()
            if nome_prov and nome_prov.lower() not in ("nan",""):
                novo_dict[nome_prov] = {
                    "telefone":   str(row.get("Telefone",  "")).replace("nan","").strip(),
                    "celular":    str(row.get("Celular",   "")).replace("nan","").strip(),
                    "observacao": str(row.get("Observação","")).replace("nan","").strip(),
                }
        st.session_state.provedores = novo_dict
        ok = salvar_provedores(novo_dict)
        if ok:
            st.session_state.provedores = carregar_provedores()
            st.success(f"Provedores salvos! ({len(st.session_state.provedores)} registros)")
        st.rerun()

# ─────────────────────────────────────────
# ABA 4 — BUSCA MANUAL
# ─────────────────────────────────────────
with t4:
    st.markdown("#### INEPs para consulta")
    col_txt, col_how = st.columns([2, 1])
    with col_txt:
        txt = st.text_area(
            "INEPs (um por linha ou separados por vírgula):",
            height=160, placeholder="13084259\n13051997\n15559556"
        )
    with col_how:
        st.markdown("**Como usar**")
        st.markdown(
            "- Um INEP por linha ou separados por vírgula\n"
            "- Busca em todas as fontes disponíveis\n"
            "- Ubiquiti: contas ativas na barra lateral\n"
            "- Omada/Zyxel: faça upload dos exports abaixo\n"
            "- INEPs não encontrados são listados ao final"
        )

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)
    st.markdown("#### Fontes adicionais (opcional)")

    col_om_bm, col_zy_bm = st.columns(2)
    with col_om_bm:
        st.caption("🔵 **Omada** — export do portal On Premise Systems")
        bm_omada = st.file_uploader("Export Omada (.xlsx)", type=["xlsx"], key="bm_omada")
        if bm_omada:
            df_bm_om = pd.read_excel(bm_omada)
            bm_omada.seek(0)
            st.caption(f"{len(df_bm_om)} controllers carregados")
    with col_zy_bm:
        st.caption("🟣 **Zyxel** — export CSV do Nebula (Overview → Sites)")
        bm_zyxel = st.file_uploader("Export Zyxel (.csv)", type=["csv"], key="bm_zyxel")
        if bm_zyxel:
            df_bm_zy = pd.read_csv(bm_zyxel)
            bm_zyxel.seek(0)
            st.caption(f"{len(df_bm_zy)} sites carregados")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    tem_fonte_bm = alvo or bm_omada or bm_zyxel
    if not tem_fonte_bm:
        st.info("Configure ao menos uma fonte: conta Ubiquiti na barra lateral, ou upload de export Omada/Zyxel.")

    if st.button("🔍 Buscar", type="primary", disabled=not tem_fonte_bm):
        if not txt.strip():
            st.warning("Insira ao menos um INEP.")
        else:
            ineps_m = {i.strip() for i in txt.replace("\n",",").split(",") if i.strip()}
            res_bm, erros = {}, []

            if alvo:
                with st.spinner(f"Consultando Ubiquiti ({len(alvo)} conta(s))..."):
                    for c in alvo:
                        try:
                            res_bm.update(buscar_ineps_ubiquiti(c["api_key"], c["apelido"], ineps_m))
                        except Exception as e:
                            erros.append(f"Ubiquiti {c['apelido']}: {e}")

            if bm_omada:
                try:
                    bm_omada.seek(0)
                    res_om = processar_export_omada(pd.read_excel(bm_omada))
                    for inep, dados in res_om.items():
                        if inep in ineps_m and inep not in res_bm:
                            res_bm[inep] = dados
                except Exception as e:
                    erros.append(f"Omada: {e}")

            if bm_zyxel:
                try:
                    bm_zyxel.seek(0)
                    res_zy = processar_export_zyxel(pd.read_csv(bm_zyxel))
                    for inep, dados in res_zy.items():
                        if inep in ineps_m and inep not in res_bm:
                            res_bm[inep] = dados
                except Exception as e:
                    erros.append(f"Zyxel: {e}")

            for e in erros: st.error(e)

            # Deduplicação: mantém a melhor entrada por INEP
            res_bm = deduplicar_por_inep(res_bm)

            if res_bm:
                dfm = pd.DataFrame.from_dict(res_bm, orient="index").reset_index()
                dfm.rename(columns={"index": "INEP"}, inplace=True)
                col_c1, col_c2, col_c3, col_c4 = st.columns(4)
                col_c1.metric("Encontrados",     len(dfm))
                col_c2.metric("Online",  dfm["Status Rede"].str.contains("ONLINE",  na=False).sum())
                col_c3.metric("Offline", dfm["Status Rede"].str.contains("OFFLINE", na=False).sum())
                col_c4.metric("Não encontrados", len(ineps_m) - len(res_bm))
                st.dataframe(dfm.style.map(cor_status, subset=["Status Rede"]), use_container_width=True)
                nao = ineps_m - set(res_bm.keys())
                if nao:
                    st.warning(f"{len(nao)} não encontrado(s): `{', '.join(sorted(nao))}`")
                st.download_button("⬇️ Exportar resultado", to_xlsx(dfm),
                    f"busca_manual_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.error("Nenhum INEP localizado em nenhuma das fontes consultadas.")

# ─────────────────────────────────────────
# ABA 5 — RAIO-X
# ─────────────────────────────────────────
with t5:
    if not alvo:
        st.warning("Selecione pelo menos uma conta na barra lateral.")
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            conta_rx = st.selectbox("Conta:", [c["apelido"] for c in alvo])
            filtro   = st.text_input("Filtrar por nome/INEP:", placeholder="Ex: FEIJÓ ou 12131229")
            btn      = st.button("🔬 Sondar", type="primary", use_container_width=True)
        with c2:
            if btn:
                key_rx = next(c["api_key"] for c in alvo if c["apelido"] == conta_rx)
                with st.spinner(f"Carregando hosts de '{conta_rx}'..."):
                    try:
                        hosts = get_paginated_hosts(key_rx)
                        rows  = [{"Nome": extrair_host(h)["nome"], "Estado": extrair_host(h)["estado"],
                                  "IP": extrair_host(h)["ip"], "ISP": extrair_host(h)["isp"],
                                  "Uptime": extrair_host(h)["uptime"]} for h in hosts]
                        df_rx = pd.DataFrame(rows)
                        if filtro:
                            df_rx = df_rx[df_rx["Nome"].str.upper().str.contains(filtro.upper(), na=False)]
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Total hosts", len(df_rx))
                        m2.metric("Conectados",  (df_rx["Estado"] == "connected").sum())
                        m3.metric("Offline",     (df_rx["Estado"] == "disconnected").sum())
                        st.dataframe(df_rx.style.map(cor_estado, subset=["Estado"]),
                                     use_container_width=True, height=440)
                        st.download_button("⬇️ Exportar", to_xlsx(df_rx),
                            f"raio_x_{conta_rx}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    except Exception as e:
                        st.error(f"Erro: {e}")
            else:
                st.info("Selecione uma conta e clique em 'Sondar'.")

# ─────────────────────────────────────────
# ABA 6 — DIAGNÓSTICO
# ─────────────────────────────────────────
with t6:
    if not alvo:
        st.warning("Selecione pelo menos uma conta na barra lateral.")
    else:
        if st.button("🩺 Testar Todas as Contas Ubiquiti", type="primary"):
            for c in alvo:
                with st.spinner(f"Testando {c['apelido']}..."):
                    ok, msg = testar_conta(c["api_key"])
                if ok: st.success(f"**{c['apelido']}** — {msg}")
                else:  st.error(f"**{c['apelido']}** — {msg}")

        st.markdown("---")
        st.markdown("**Contas selecionadas:**")
        for c in alvo:
            k    = c["api_key"]
            prev = k[:6] + "•••" + k[-4:] if len(k) > 10 else "⚠️ inválida"
            st.markdown(f"- **{c['apelido']}** — `{prev}`")

        st.markdown("---")
        st.markdown("**Debug — Provedores:**")
        col_d1, col_d2 = st.columns(2)
        col_d1.metric("Na sessão",  len(st.session_state.provedores))
        col_d2.metric("No arquivo", len(carregar_provedores()))
        st.caption(f"Arquivo: `{os.path.abspath(CONFIG_PROVEDORES)}` | Existe: `{os.path.exists(CONFIG_PROVEDORES)}`")
        if st.button("🔄 Recarregar provedores do disco"):
            st.session_state.provedores = carregar_provedores()
            st.success(f"Recarregado: {len(st.session_state.provedores)} provedores.")
            st.rerun()

# ─────────────────────────────────────────
# ABA 7 — AJUDA
# ─────────────────────────────────────────
with t7:
    st.markdown("### Como usar o Hub Redes — EACE")
    st.markdown("""
**Relatório Diário:**
1. Acesse **Área Restrita > Fechamento Diário** na barra lateral
2. Informe a senha da área restrita
3. Preencha os dados operacionais do dia e envie a planilha .xlsx
4. Clique em **Concluir Fechamento**
5. Acesse **Relatório Diário** para visualizar e baixar o relatório

**Inventário Geral:**
- Coleta TODAS as escolas de todas as plataformas, sem depender de chamados
- Ubiquiti: buscado automaticamente via API (todas as contas ativas)
- Omada e Zyxel: faça upload dos exports na aba Inventário
- Campo de pesquisa por INEP ou nome da escola
- Exportação filtrada ou completa em .xlsx

**Como exportar o Zyxel:**
Zyxel Nebula → Overview → aba Sites → ícone de download (CSV) no canto superior direito.

**Como exportar o Omada:**
`use1-omada-cloud.tplinkcloud.com` → On Premise Systems → botão **Export**.

**Legenda de cores:**
- 🟢 UBIQUITI - ONLINE / 🔴 UBIQUITI - OFFLINE
- 🔵 OMADA - ONLINE / 🟠 OMADA - OFFLINE
- 🟣 ZYXEL - ONLINE / 🩷 ZYXEL - OFFLINE / 🟡 ZYXEL - ALERTA
- ⬛ NÃO ENCONTRADO
    """)
