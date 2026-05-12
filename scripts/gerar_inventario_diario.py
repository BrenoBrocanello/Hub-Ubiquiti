# -*- coding: utf-8 -*-
"""
Gera o inventário diário de escolas Ubiquiti.
Roda automaticamente via GitHub Actions às 08:00 (Brasília).

Estrutura gerada:
  ESTATISTICAS  — resumo geral + por UF
  Geral         — todas as escolas encontradas (INEP, Nome, Status, Conta)
  Escolas não encontradas dash´s — INEPs da lista externa ausentes
  {conta}       — uma aba por conta Ubiquiti
"""

import os
import re
import json
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

APP_TZ = ZoneInfo("America/Sao_Paulo")
BASE_URL = "https://api.ui.com/v1"

OUT_DIR = Path("data/inventarios_diarios")
REF_FILE = Path("data/lista_ineps_referencia.xlsx")

SHEET_NAO_ENC = "Escolas não encontradas dash´s"
_CONTA_PREFIXOS = ("Conta_", "conta_", "CONTA_", "admin", "Admin", "ADMIN")


# ──────────────────────────────────────────────────────────────
# LEITURA DE CONTAS
# ──────────────────────────────────────────────────────────────

def carregar_contas() -> list:
    """
    Prioridade:
    1. CONTAS_JSON env var  (JSON completo)
    2. Variáveis individuais com prefixo Conta_/admin
    3. config_contas.json  (desenvolvimento local)
    """
    raw = os.environ.get("CONTAS_JSON", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass

    contas = []
    for key, value in os.environ.items():
        if any(key.upper().startswith(p.upper()) for p in _CONTA_PREFIXOS) and len(value.strip()) >= 20:
            contas.append({"apelido": key, "api_key": value.strip()})
    if contas:
        return contas

    cfg = Path("config_contas.json")
    if cfg.exists():
        try:
            with open(cfg, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return []


# ──────────────────────────────────────────────────────────────
# API UBIQUITI
# ──────────────────────────────────────────────────────────────

def get_paginated_hosts(api_key: str) -> list:
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    hosts, offset, limit = [], 0, 200
    while True:
        try:
            r = requests.post(
                f"{BASE_URL}/devices/fetch",
                headers=headers,
                json={"filters": {}, "pagination": {"limit": limit, "offset": offset}},
                timeout=30,
            )
            r.raise_for_status()
            page = r.json().get("data", {}).get("devices", [])
            hosts.extend(page)
            if len(page) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"    paginação: {e}")
            break
    return hosts


def extrair_inep(nome: str):
    m = re.findall(r"\b(\d{8})\b", str(nome))
    return m[-1] if m else None


def coletar_conta(conta: dict) -> tuple:
    rows = []
    try:
        for h in get_paginated_hosts(conta["api_key"]):
            nome   = h.get("name", h.get("hostname", "Desconhecido"))
            estado = h.get("state", "unknown")
            inep   = extrair_inep(nome)
            rows.append({
                "INEP":            str(inep) if inep else "—",
                "Nome no Console": nome,
                "Status":          "Online" if estado == "connected" else "Offline",
                "Conta":           conta["apelido"],
            })
    except Exception as e:
        print(f"  ERRO {conta['apelido']}: {e}")
    return rows, conta["apelido"]


# ──────────────────────────────────────────────────────────────
# LISTA DE REFERÊNCIA
# ──────────────────────────────────────────────────────────────

def carregar_ineps_referencia() -> set:
    if not REF_FILE.exists():
        print(f"AVISO: {REF_FILE} não encontrado — aba 'Escolas não encontradas' ficará vazia.")
        return set()
    try:
        df  = pd.read_excel(REF_FILE, dtype=str)
        col = next((c for c in df.columns if "INEP" in c.upper()), df.columns[0])
        ineps = set(df[col].dropna().astype(str).str.strip())
        print(f"Referência: {len(ineps)} INEPs de '{col}'")
        return ineps
    except Exception as e:
        print(f"Erro ao ler referência: {e}")
        return set()


# ──────────────────────────────────────────────────────────────
# UTILITÁRIOS
# ──────────────────────────────────────────────────────────────

def extrair_uf(nome: str) -> str:
    m = re.match(r"^([A-Z]{2})\s", str(nome).strip().upper())
    return m.group(1) if m else "??"


def deduplicar(df: pd.DataFrame) -> pd.DataFrame:
    sem = df[df["INEP"] == "—"].copy()
    com = df[df["INEP"] != "—"].copy()
    if not com.empty:
        com["_pri"] = (com["Status"] == "Online").astype(int)
        com = (com.sort_values("_pri", ascending=False)
                  .drop_duplicates(subset=["INEP"], keep="first")
                  .drop(columns=["_pri"]))
    return pd.concat([com, sem], ignore_index=True)


# ──────────────────────────────────────────────────────────────
# GERAÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────

def gerar_inventario():
    now = datetime.now(APP_TZ)
    print(f"\n{'='*55}")
    print(f"  Inventário Diário — {now.strftime('%d/%m/%Y %H:%M')} (Brasília)")
    print(f"{'='*55}")

    contas = carregar_contas()
    if not contas:
        raise RuntimeError("Nenhuma conta configurada. Verifique CONTAS_JSON ou variáveis de ambiente.")
    print(f"Contas: {[c['apelido'] for c in contas]}\n")

    # Coleta em paralelo
    todas: list      = []
    por_conta: dict  = {}

    with ThreadPoolExecutor(max_workers=min(len(contas), 5)) as ex:
        futs = {ex.submit(coletar_conta, c): c["apelido"] for c in contas}
        for fut in as_completed(futs):
            rows, apelido = fut.result()
            todas.extend(rows)
            por_conta[apelido] = rows
            print(f"  ✓ {apelido}: {len(rows)} host(s)")

    # Geral deduplicado
    col_base = ["INEP", "Nome no Console", "Status", "Conta"]
    df_geral = pd.DataFrame(todas, columns=col_base) if todas else pd.DataFrame(columns=col_base)
    df_geral  = deduplicar(df_geral)
    df_geral["INEP"] = df_geral["INEP"].astype(str).str.strip()

    ineps_encontrados = set(df_geral[df_geral["INEP"] != "—"]["INEP"].unique())

    # Escolas não encontradas
    ineps_ref = carregar_ineps_referencia()
    nao_enc   = sorted(ineps_ref - ineps_encontrados)
    df_nao_enc = pd.DataFrame({"Ordem": range(1, len(nao_enc)+1), "INEP": nao_enc})

    # Totais
    validos = df_geral[df_geral["INEP"] != "—"]
    total   = len(validos)
    online  = (validos["Status"] == "Online").sum()
    offline = (validos["Status"] == "Offline").sum()

    # Por UF
    df_geral["_uf"] = df_geral["Nome no Console"].apply(extrair_uf)
    por_uf = (validos.assign(_uf=validos["Nome no Console"].apply(extrair_uf))
              .groupby("_uf")
              .agg(Total=("INEP","count"),
                   Online=("Status", lambda x:(x=="Online").sum()),
                   Offline=("Status", lambda x:(x=="Offline").sum()))
              .reset_index().rename(columns={"_uf":"UF"})
              .sort_values("Total", ascending=False))
    por_uf["% Online"] = (por_uf["Online"] / por_uf["Total"] * 100).round(2).astype(str) + "%"
    df_geral = df_geral.drop(columns=["_uf"])

    # ESTATISTICAS
    stats = [
        {"Indicador": "Data de Geração",                   "Valor": now.strftime("%d/%m/%Y %H:%M")},
        {"Indicador": "Total de escolas no inventário",     "Valor": total},
        {"Indicador": "Online",                             "Valor": int(online)},
        {"Indicador": "Offline",                            "Valor": int(offline)},
        {"Indicador": "Percentual online",                  "Valor": f"{online/total*100:.2f}%" if total else "—"},
        {"Indicador": "Não encontradas em nenhum dash",     "Valor": len(nao_enc)},
        {"Indicador": "",                                   "Valor": ""},
        {"Indicador": "=== Resumo por UF ===",              "Valor": ""},
    ]
    for _, r in por_uf.iterrows():
        stats.append({
            "Indicador": f"{r['UF']}: {r['Total']} escolas  |  Online: {r['Online']}  |  Offline: {r['Offline']}  |  {r['% Online']}",
            "Valor": "",
        })
    df_stats = pd.DataFrame(stats)

    # Salvar Excel
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nome_arq = OUT_DIR / f"inventario_{now.strftime('%Y-%m-%d')}.xlsx"

    ordem_abas = [c["apelido"] for c in contas]

    with pd.ExcelWriter(nome_arq, engine="openpyxl") as w:
        df_stats.to_excel(w, index=False, sheet_name="ESTATISTICAS")
        df_geral[col_base].to_excel(w, index=False, sheet_name="Geral")
        df_nao_enc.to_excel(w, index=False, sheet_name=SHEET_NAO_ENC)
        for apelido in ordem_abas:
            rows = por_conta.get(apelido, [])
            df_c = pd.DataFrame(rows, columns=col_base) if rows else pd.DataFrame(columns=col_base)
            sname = re.sub(r'[\\/*?:\[\]]', '_', apelido)[:31]
            df_c.to_excel(w, index=False, sheet_name=sname)

    print(f"\nArquivo gerado: {nome_arq}")
    print(f"Total: {total}  |  Online: {online}  |  Offline: {offline}  |  Não encontradas: {len(nao_enc)}")
    return str(nome_arq)


if __name__ == "__main__":
    gerar_inventario()
