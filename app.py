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

.stApp { background: #0f1117; }

[data-testid="stSidebar"] > div:first-child {
    background: #161b27;
    border-right: 1px solid #1e2535;
}

.block-container { padding-top: 2rem !important; max-width: 1400px !important; }
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
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 10px;
    padding: 16px 18px;
    min-width: 0;
}
.saas-card-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #4b5563;
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
    color: #374151;
    margin-top: 6px;
    font-family: Inter, sans-serif;
}
.c-blue   { color: #3b82f6; }
.c-green  { color: #22c55e; }
.c-red    { color: #ef4444; }
.c-yellow { color: #eab308; }
.c-gray   { color: #6b7280; }
.c-teal   { color: #38bdf8; }
.c-purple { color: #a855f7; }

.page-title {
    font-family: Inter, sans-serif;
    font-size: 22px;
    font-weight: 700;
    color: #f9fafb;
    margin: 0;
}
.page-sub {
    font-family: Inter, sans-serif;
    font-size: 12px;
    color: #4b5563;
    margin-top: 3px;
    letter-spacing: 0.5px;
}

.sidebar-label {
    font-family: Inter, sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #374151;
    margin: 16px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #1e2535;
}

.log-box {
    background: #0a0d14;
    border: 1px solid #1e2535;
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
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    color: #3b82f6;
    font-family: Inter, sans-serif;
    margin-bottom: 16px;
}

.saas-divider {
    border: none;
    border-top: 1px solid #1e2535;
    margin: 20px 0;
}

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1e2535; border-radius: 99px; }
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
    '<p class="page-title">🛰️ Hub Redes — EACE</p>'
    '<p class="page-sub">Monitor de Conectividade · Ubiquiti · Omada · Zyxel · Escolas Brasileiras</p>',
    unsafe_allow_html=True
)
st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
    "📊 Processar Planilha",
    "📋 Chamados",
    "🌐 Inventário Geral",
    "🏢 Provedores",
    "🔍 Busca Manual",
    "🛠️ Raio-X da Conta",
    "🩺 Diagnóstico",
    "ℹ️ Ajuda",
])

# ─────────────────────────────────────────
# ABA 1 — PROCESSAR PLANILHA
# ─────────────────────────────────────────
with t1:
    col_reset, _ = st.columns([2, 5])
    if col_reset.button("🗑️ Resetar Dados de Importação", use_container_width=True):
        st.session_state.df_resultado    = None
        st.session_state.relatorio       = []
        st.session_state.ultima_consulta = None
        st.success("Dados resetados.")
        st.rerun()

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    st.markdown("#### 1. Planilha de Chamados (obrigatória)")
    col_up, col_inf = st.columns([3, 1])
    with col_up:
        arquivo = st.file_uploader(
            "Planilha de chamados (.xlsx) — deve conter coluna INEP",
            type=["xlsx"], key="up_chamados"
        )
    with col_inf:
        if arquivo:
            df_prev = pd.read_excel(arquivo, dtype={"INEP": str})
            arquivo.seek(0)
            n_ineps = df_prev["INEP"].dropna().astype(str).str.replace(r'\.0$','',regex=True).str.strip().nunique()
            st.metric("Chamados", len(df_prev))
            st.metric("INEPs únicos", n_ineps)
        else:
            st.info("Aguardando...")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    st.markdown("#### 2. Export do Omada Cloud (opcional)")
    st.caption("Omada → On Premise Systems → botão **Export** → faça upload aqui.")
    col_om, col_om_inf = st.columns([3, 1])
    with col_om:
        arquivo_omada = st.file_uploader("Export Omada (.xlsx)", type=["xlsx"], key="up_omada")
    with col_om_inf:
        if arquivo_omada:
            df_om_prev = pd.read_excel(arquivo_omada)
            arquivo_omada.seek(0)
            n_on  = (df_om_prev["STATUS"].str.upper() == "ONLINE").sum()  if "STATUS" in df_om_prev.columns else "—"
            n_off = (df_om_prev["STATUS"].str.upper() == "OFFLINE").sum() if "STATUS" in df_om_prev.columns else "—"
            st.metric("Controllers", len(df_om_prev))
            st.metric("Online / Offline", f"{n_on} / {n_off}")
        else:
            st.info("Opcional.")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    st.markdown("#### 3. Export do Zyxel Nebula (opcional)")
    st.caption("Zyxel Nebula → Overview → Sites → ícone de download (CSV) → faça upload aqui.")
    col_zy, col_zy_inf = st.columns([3, 1])
    with col_zy:
        arquivo_zyxel = st.file_uploader("Export Zyxel (.csv)", type=["csv"], key="up_zyxel")
    with col_zy_inf:
        if arquivo_zyxel:
            df_zy_prev = pd.read_csv(arquivo_zyxel)
            arquivo_zyxel.seek(0)
            col_st = next((c for c in df_zy_prev.columns if c.strip().upper() in ("ESTADO","STATUS")), None)
            if col_st:
                n_ok  = (df_zy_prev[col_st].str.upper() == "OK").sum()
                n_off = df_zy_prev[col_st].str.upper().isin(["DEVICE OFFLINE","DEVICES UNREACHABLE"]).sum()
                n_alr = (df_zy_prev[col_st].str.upper() == "DEVICE ALERTED").sum()
                st.metric("Sites", len(df_zy_prev))
                st.metric("OK / Offline", f"{n_ok} / {n_off}")
                if n_alr: st.metric("Em alerta", n_alr)
            else:
                st.metric("Sites", len(df_zy_prev))
        else:
            st.info("Opcional.")

    st.markdown('<hr class="saas-divider">', unsafe_allow_html=True)

    if not arquivo:
        st.info("Faça upload da planilha de chamados para continuar.")
    elif not alvo and not arquivo_omada and not arquivo_zyxel:
        st.warning("Configure ao menos uma fonte: conta Ubiquiti, export Omada ou export Zyxel.")
    else:
        fontes = []
        if alvo:          fontes.append(f"Ubiquiti ({len(alvo)} conta(s))")
        if arquivo_omada: fontes.append("Omada (export)")
        if arquivo_zyxel: fontes.append("Zyxel (export)")
        st.success(f"Fontes prontas: {' + '.join(fontes)}")

        if st.button("🔍 Iniciar Consulta em Massa", type="primary", use_container_width=True):
            df_raw = pd.read_excel(arquivo, dtype={"INEP": str})
            if "INEP" not in df_raw.columns:
                st.error("Coluna 'INEP' não encontrada na planilha!")
                st.stop()

            ineps_set = set(
                df_raw["INEP"].dropna()
                .astype(str).str.replace(r'\.0$','',regex=True).str.strip()
            )
            todos = {}
            log   = []
            t0    = time.time()

            if alvo:
                prog = st.progress(0.0, text="Consultando Ubiquiti...")
                with ThreadPoolExecutor(max_workers=min(len(alvo), 5)) as ex:
                    futs = {ex.submit(buscar_ineps_ubiquiti, c["api_key"], c["apelido"], ineps_set): c["apelido"] for c in alvo}
                    done = 0
                    for fut in as_completed(futs):
                        ap = futs[fut]
                        try:
                            res = fut.result()
                            for inep, dados in res.items():
                                if inep not in todos: todos[inep] = dados
                            isps_novos = {v["ISP"] for v in res.values() if v.get("ISP","—") != "—"}
                            qt = mesclar_isps_novos(isps_novos)
                            log.append(("ok", f"Ubiquiti {ap}: {len(res)} escola(s) | {qt} ISP(s) novo(s)"))
                        except Exception as e:
                            log.append(("err", f"Ubiquiti {ap}: {e}"))
                        done += 1
                        prog.progress(done / len(alvo), text=f"Ubiquiti {done}/{len(alvo)}...")
                prog.progress(1.0, text="Ubiquiti concluído.")

            if arquivo_omada:
                try:
                    arquivo_omada.seek(0)
                    res_om = processar_export_omada(pd.read_excel(arquivo_omada))
                    cruzados = sum(1 for inep, d in res_om.items()
                                   if inep in ineps_set and inep not in todos
                                   and not todos.update({inep: d}))
                    log.append(("ok", f"Omada: {cruzados} escola(s) cruzada(s) de {len(res_om)} controllers"))
                except Exception as e:
                    log.append(("err", f"Omada export: {e}"))

            if arquivo_zyxel:
                try:
                    arquivo_zyxel.seek(0)
                    res_zy = processar_export_zyxel(pd.read_csv(arquivo_zyxel))
                    cruzados_zy = 0
                    for inep, dados in res_zy.items():
                        if inep in ineps_set and inep not in todos:
                            todos[inep] = dados
                            cruzados_zy += 1
                    log.append(("ok", f"Zyxel: {cruzados_zy} escola(s) cruzada(s) de {len(res_zy)} sites"))
                except Exception as e:
                    log.append(("err", f"Zyxel export: {e}"))

            # Deduplicação: mantém a melhor entrada por INEP
            todos = deduplicar_por_inep(todos)

            df_f = df_raw.copy()
            df_f["INEP_K"] = df_f["INEP"].astype(str).str.replace(r'\.0$','',regex=True).str.strip()
            for col, pad in [
                ("Status Rede","NÃO ENCONTRADO"),("Plataforma","—"),("Uptime WAN","—"),
                ("ISP","—"),("Conta","—"),("IP Externo","—"),("Nome no Console","—"),
            ]:
                df_f[col] = df_f["INEP_K"].map(lambda x, c=col, p=pad: todos.get(x, {}).get(c, p))
            df_f.drop(columns=["INEP_K"], inplace=True)

            st.session_state.df_resultado    = df_f
            st.session_state.relatorio       = log
            st.session_state.ultima_consulta = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            st.success(f"Concluído em {time.time()-t0:.1f}s — {len(todos)} escola(s) localizada(s).")
            st.info("Acesse a aba '📋 Chamados' para ver os resultados.")

# ─────────────────────────────────────────
# ABA 2 — CHAMADOS
# ─────────────────────────────────────────
with t2:
    if st.session_state.df_resultado is None:
        st.info("Nenhuma planilha processada ainda. Vá para 'Processar Planilha'.")
    else:
        df = st.session_state.df_resultado
        st.markdown(f'<div class="ts-pill">🕐 {st.session_state.ultima_consulta}</div>', unsafe_allow_html=True)

        if st.session_state.relatorio:
            html = "".join(
                f'<div class="log-{"ok" if tp=="ok" else "err"}">{"✓" if tp=="ok" else "✗"}  {m}</div>'
                for tp, m in st.session_state.relatorio
            )
            st.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)

        total   = len(df)
        online  = df["Status Rede"].str.contains("ONLINE",   na=False).sum()
        offline = df["Status Rede"].str.contains("OFFLINE",  na=False).sum()
        n_ubi   = df["Status Rede"].str.contains("UBIQUITI", na=False).sum()
        n_om    = df["Status Rede"].str.contains("OMADA",    na=False).sum()
        n_zy    = df["Status Rede"].str.contains("ZYXEL",    na=False).sum()

        st.markdown(f"""
        <div class="saas-grid">
          <div class="saas-card"><div class="saas-card-label">Total chamados</div>
            <div class="saas-card-value c-blue">{total}</div><div class="saas-card-sub">planilha importada</div></div>
          <div class="saas-card"><div class="saas-card-label">Online</div>
            <div class="saas-card-value c-green">{online}</div><div class="saas-card-sub">{f"{online/total*100:.0f}%" if total else "—"}</div></div>
          <div class="saas-card"><div class="saas-card-label">Offline / Alerta</div>
            <div class="saas-card-value c-red">{offline}</div><div class="saas-card-sub">{f"{offline/total*100:.0f}%" if total else "—"}</div></div>
          <div class="saas-card"><div class="saas-card-label">Ubiquiti</div>
            <div class="saas-card-value c-blue">{n_ubi}</div><div class="saas-card-sub">identificados</div></div>
          <div class="saas-card"><div class="saas-card-label">Omada</div>
            <div class="saas-card-value c-teal">{n_om}</div><div class="saas-card-sub">identificados</div></div>
          <div class="saas-card"><div class="saas-card-label">Zyxel</div>
            <div class="saas-card-value c-purple">{n_zy}</div><div class="saas-card-sub">identificados</div></div>
        </div>""", unsafe_allow_html=True)

        with st.expander("⚙️ Filtros", expanded=True):
            f1, f2, f3, f4, f5, f6 = st.columns(6)
            op_st   = sorted(df["Status Rede"].dropna().unique().tolist())
            op_plat = sorted(df["Plataforma"].dropna().unique().tolist()) if "Plataforma" in df.columns else []
            op_isp  = sorted([v for v in df["ISP"].dropna().unique().tolist() if v not in ("—","")])
            op_uf   = sorted(df["UF"].dropna().unique().tolist())      if "UF"       in df.columns else []
            op_an   = sorted(df["Analista"].dropna().unique().tolist()) if "Analista" in df.columns else []
            op_co   = sorted(df["Conta"].dropna().unique().tolist())
            fs = f1.multiselect("Status Rede",    op_st,   default=op_st, key="fs_ch")
            fp = f2.multiselect("Plataforma",     op_plat, default=[],    key="fp_ch")
            fi = f3.multiselect("Provedor (ISP)", op_isp,  default=[],    key="fi_ch")
            fu = f4.multiselect("UF",             op_uf,   default=[],    key="fu_ch")
            fa = f5.multiselect("Analista",       op_an,   default=[],    key="fa_ch")
            fc = f6.multiselect("Conta",          op_co,   default=[],    key="fc_ch")

        dff = df[df["Status Rede"].isin(fs)]
        if fp:                               dff = dff[dff["Plataforma"].isin(fp)]
        if fi:                               dff = dff[dff["ISP"].isin(fi)]
        if fu and "UF"       in df.columns:  dff = dff[dff["UF"].isin(fu)]
        if fa and "Analista" in df.columns:  dff = dff[dff["Analista"].isin(fa)]
        if fc:                               dff = dff[dff["Conta"].isin(fc)]

        prio = ["Ticket#","UF","Cidade","Escola","INEP","Analista","Status Rede","Plataforma",
                "Uptime WAN","ISP","Conta","IP Externo","Nome no Console","Dias Abertos (Corridos)"]
        cols = [c for c in prio if c in dff.columns] + [c for c in dff.columns if c not in prio]

        st.dataframe(dff[cols].style.map(cor_status, subset=["Status Rede"]),
                     use_container_width=True, height=500)
        st.caption(f"{len(dff):,} de {len(df):,} chamados exibidos")

        ca, cb, _ = st.columns([1, 1, 3])
        ca.download_button("⬇️ Exportar filtrado", to_xlsx(dff[cols]),
            f"chamados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        cb.download_button("⬇️ Exportar completo", to_xlsx(df[cols]),
            f"chamados_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────
# ABA 3 — INVENTÁRIO GERAL
# ─────────────────────────────────────────
with t3:
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
# ABA 4 — PROVEDORES
# ─────────────────────────────────────────
with t4:
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
# ABA 5 — BUSCA MANUAL
# ─────────────────────────────────────────
with t5:
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
# ABA 6 — RAIO-X
# ─────────────────────────────────────────
with t6:
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
# ABA 7 — DIAGNÓSTICO
# ─────────────────────────────────────────
with t7:
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
# ABA 8 — AJUDA
# ─────────────────────────────────────────
with t8:
    st.markdown("### Como usar o Hub Redes — EACE")
    st.markdown("""
**Fluxo principal (chamados):**
1. Configure as contas Ubiquiti na barra lateral
2. Faça upload da planilha de chamados (.xlsx com coluna INEP)
3. Opcionalmente, faça upload dos exports do Omada e/ou Zyxel
4. Clique em **Iniciar Consulta em Massa**
5. Acesse **Chamados** para filtrar e exportar

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