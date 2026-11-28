"""Apoio dos testes do Farol de Fretes (T-0037): o item da TABELA e o
Contexto fictício do rn.fretes, comuns ao test_T0037_fretes_nucleo e ao
test_T0037_fretes_liquido (RD-0260).

Tudo fictício: pasta temporária (tmp_path), "CLIENTE TESTE", cidades
inventadas, sem CNPJ. O cadastro de transportadoras é gravado só na pasta
temporária.
"""
import json
from datetime import date

import relatorios_nucleo as rn

HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
FILIAIS = {"0101": "FILIAL FICTICIA"}


def item(tipo, cli, nf, valor, dt_nf, dt_ped=None, fil="0101"):
    """Item da TABELA (venda VND, devolução DEV ou pedido em aberto VEA)."""
    return {"tipo": tipo, "cliente": cli, "filial": fil, "nf": nf,
            "serie": "1", "pedido": "P" + nf, "valor": valor, "dt_nf": dt_nf,
            "dt_pedido": dt_ped or dt_nf, "razao": "", "p_tab": 0, "qtd": 1,
            "produto": "", "vend": ""}


def contexto_fretes(tmp_path, itens, clientes, entregas=(), cad=None):
    """Roda o rn.fretes de verdade num Contexto fictício.

    `clientes` = [(cod, nome, cidade, uf)]; `entregas` = linhas do
    acompanhamento do pós-venda; `cad` = cadastro de transportadoras.
    Devolve (resultado do farol, tabela "Notas com frete")."""
    cad = {"pct_padrao": 5, "transportadoras": []} if cad is None else cad
    (tmp_path / "transportadoras_config.json").write_text(
        json.dumps(cad), encoding="utf-8")
    ctx = rn.Contexto(tmp_path, hoje=HOJE, params=dict(PARAMS))
    ctx._b["tabela"] = {"itens": [dict(i) for i in itens], "clientes": {},
                        "filiais": dict(FILIAIS)}
    ctx._b["base"] = {"clientes": [
        {"cod": c, "nome": n, "fantasia": "", "cidade": cid, "uf": uf,
         "segmento": "", "vend": "", "status": "ATIVO"}
        for c, n, cid, uf in clientes], "pessoas": {}}
    ctx._b["posvenda"] = {"existe": True,
                          "entregas": [dict(e) for e in entregas],
                          "devolucoes": []}
    r = rn.fretes(ctx)
    return r, r["tabelas"][0]
