# -*- coding: utf-8 -*-
"""
META DE SALDO - o Analista cadastra, por mes, a meta de SALDO de desconto
de cada UF (BAP Analista > Meta de saldo). Ao salvar, a meta da UF e
dividida entre os vendedores (e somada por supervisor) pelo PESO DE VENDA
de cada um naquela UF nos 3 meses anteriores ao mes da meta.

Fica em meta_saldo_config.json, na pasta dos programas:
    {"2026-10": {"ufs": {"AM": 5000.0, ...},
                 "divisao": [{"uf", "supervisor", "vendedor", "venda3m",
                              "peso", "meta"}],
                 "gerado_em": "04/10/2026 10:30"}}
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARQUIVO = "meta_saldo_config.json"
UFS = ["AM", "RR", "PA", "AP", "MA", "MT"]
SEM_VENDA = "(sem venda nos 3 meses)"


def carregar(raiz=None) -> dict:
    arq = Path(raiz or AQUI) / ARQUIVO
    if not arq.exists():
        return {}
    try:
        return json.loads(arq.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(dados: dict, raiz=None) -> Path:
    arq = Path(raiz or AQUI) / ARQUIVO
    tmp = arq.with_name(f"~{arq.name}")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, arq)
    return arq


def meses_anteriores(comp: str, n=3) -> list:
    ano, mes = int(comp[:4]), int(comp[5:7])
    saida = []
    for _ in range(n):
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
        saida.append(f"{ano}-{mes:02d}")
    return saida


def dividir(ctx, comp: str, ufs: dict) -> list:
    """
    A meta de cada UF repartida pelo peso de venda (R$ faturado, 3 meses
    antes de comp) de cada vendedor nos clientes daquela UF.
    """
    meses = set(meses_anteriores(comp))
    venda = defaultdict(float)              # (uf, vendedor, supervisor)
    # (16/10, Alexandre) SO A EQUIPE: a meta se divide entre os vendedores
    # ATIVOS do Planner (cargo VENDEDOR) - codigo de fora da equipe e
    # supervisor nao recebem meta. UF sem venda da equipe: a linha
    # "(sem venda nos 3 meses)" fica com a meta inteira
    equipe = {str(c) for c, p_ in (ctx.base.get("pessoas") or {}).items()
              if p_.get("cargo") == "VENDEDOR" and p_.get("ativo", True)}
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND" or not it["dt_nf"]:
            continue
        if f"{it['dt_nf'].year}-{it['dt_nf'].month:02d}" not in meses:
            continue
        if equipe and str(it["vend"]) not in equipe:
            continue
        uf = str(ctx.cliente(it["cliente"]).get("uf") or "").upper()
        if uf not in ufs:
            continue
        venda[(uf, ctx.vendedor(it["vend"]),
               ctx.supervisor_de(it["vend"]))] += it["valor"]
    saida = []
    for uf, meta in ufs.items():
        if not meta:
            continue
        da_uf = {k: v for k, v in venda.items() if k[0] == uf and v > 0}
        total = sum(da_uf.values())
        if not total:
            saida.append({"uf": uf, "supervisor": SEM_VENDA,
                          "vendedor": SEM_VENDA, "venda3m": 0.0,
                          "peso": 100.0, "meta": float(meta)})
            continue
        for (_u, vend, sup), v in sorted(da_uf.items(), key=lambda kv: -kv[1]):
            saida.append({"uf": uf, "supervisor": sup, "vendedor": vend,
                          "venda3m": v, "peso": v / total * 100.0,
                          "meta": float(meta) * v / total})
    return saida


def gravar_meta(ctx, comp: str, ufs: dict, raiz=None) -> dict:
    dados = carregar(raiz)
    ufs = {u: float(v) for u, v in ufs.items() if v not in (None, "")}
    dados[comp] = {"ufs": ufs, "divisao": dividir(ctx, comp, ufs),
                   "gerado_em": f"{datetime.now():%d/%m/%Y %H:%M}"}
    salvar(dados, raiz)
    return dados[comp]


def meta_do_mes(comp: str, raiz=None) -> dict:
    return carregar(raiz).get(comp) or {}
