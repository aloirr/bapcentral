# -*- coding: utf-8 -*-
"""
CONFERENCIA DA SOLICITACAO_BAP - so relatorio, nao altera nada.

Compara o que ja foi solicitado (aba DETALHADO_PEDIDO) com a demanda em aberto
do ftPedidos e aponta:

  * EXCESSO   - o pedido tem mais unidades solicitadas do que pediu
  * FATURADO  - o pedido saiu como VND; a SEP pode ser cancelada
  * EXCLUIDO  - o pedido sumiu do ftPedidos
  * PROMETIDO ALEM DO ESTOQUE - a filial tem menos saldo do que ja prometeu

Uso:
    python conferir_solicitacao.py [SOLICITACAO_BAP.xlsx] [TABELA_BAP.xlsx]

Sem argumentos, usa os arquivos da pasta onde o bap_automation.py esta.
"""
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass
from pathlib import Path

import bap_automation as bap


def carregar(caminho_solicitacao: Path, caminho_tabela: Path) -> dict:
    historico = bap.ler_historico_solicitacao(caminho_solicitacao)
    df, contexto = bap.montar_solicitacao(caminho_tabela, historico)
    return {"historico": historico, "contexto": contexto, "novas": df}


def relatorio(caminho_solicitacao: Path, caminho_tabela: Path) -> int:
    print("=" * 74)
    print("CONFERENCIA DA SOLICITACAO_BAP")
    print("=" * 74)
    print(f"solicitacao : {caminho_solicitacao}")
    print(f"tabela      : {caminho_tabela}\n")

    dados = carregar(caminho_solicitacao, caminho_tabela)
    historico = dados["historico"]
    situacao = dados["contexto"].get("situacao", {})
    demanda_por_item = dados["contexto"].get("demanda_por_item", {})

    # ------------------------------------------------- 1. excesso por pedido
    por_item: dict[tuple, dict] = {}
    for linha in historico["linhas"]:
        if linha["sem_estoque"]:
            continue
        registro = por_item.setdefault(linha["item"], {
            "cidade": linha["cidade"], "pedido": linha["pedido"],
            "produto": linha["produto"], "solicitado": 0.0, "origens": {}})
        registro["solicitado"] += linha["quantidade"]
        registro["origens"][linha["origem"]] = \
            registro["origens"].get(linha["origem"], 0.0) + linha["quantidade"]

    excessos = []
    for item, registro in por_item.items():
        demanda = demanda_por_item.get(item)
        if demanda is None:
            continue                    # pedido nao esta mais em aberto
        if registro["solicitado"] > demanda + 1e-6:
            excessos.append({**registro, "demanda": demanda,
                             "excesso": registro["solicitado"] - demanda})

    print("-" * 74)
    print(f"1. PEDIDOS COM MAIS UNIDADES SOLICITADAS DO QUE A DEMANDA: {len(excessos)}")
    print("-" * 74)
    if not excessos:
        print("   nenhum. \\o/\n")
    else:
        excessos.sort(key=lambda e: -e["excesso"])
        print(f"   {'PEDIDO':<10} {'CIDADE':<12} {'PRODUTO':<30} "
              f"{'PEDIU':>8} {'SOLIC.':>8} {'EXCESSO':>9}")
        for caso in excessos:
            print(f"   {caso['pedido']:<10} {caso['cidade'][:12]:<12} "
                  f"{caso['produto'][:30]:<30} {caso['demanda']:>8.0f} "
                  f"{caso['solicitado']:>8.0f} {caso['excesso']:>9.0f}")
            detalhe = ", ".join(f"{o or '-'}={q:.0f}"
                                for o, q in sorted(caso["origens"].items()))
            print(f"   {'':<10} origens: {detalhe}")
        total = sum(c["excesso"] for c in excessos)
        print(f"\n   TOTAL EM EXCESSO: {total:.0f} unidades "
              f"em {len(excessos)} item(ns) de pedido.\n")

    # ------------------------------------------ 2. pedidos que ja se foram
    fechados = []
    for item, registro in por_item.items():
        estado = situacao.get(item, bap.SITUACAO_EXCLUIDO)
        if estado != bap.SITUACAO_ABERTO:
            fechados.append({**registro, "situacao": estado})

    print("-" * 74)
    print(f"2. LINHAS DE PEDIDOS QUE NAO ESTAO MAIS EM ABERTO: {len(fechados)}")
    print("-" * 74)
    if not fechados:
        print("   nenhuma.\n")
    else:
        faturados = [f for f in fechados if f["situacao"] == bap.SITUACAO_FATURADO]
        excluidos = [f for f in fechados if f["situacao"] == bap.SITUACAO_EXCLUIDO]
        print(f"   {len(faturados)} FATURADO(s) e {len(excluidos)} EXCLUIDO(s).")
        print("   Sao SEPs que provavelmente podem ser canceladas.\n")
        for caso in sorted(fechados, key=lambda c: (c["situacao"], c["pedido"]))[:25]:
            print(f"   {caso['situacao']:<10} pedido {caso['pedido']:<10} "
                  f"{caso['cidade'][:12]:<12} {caso['produto'][:30]:<30} "
                  f"{caso['solicitado']:>7.0f}")
        if len(fechados) > 25:
            print(f"   ... e mais {len(fechados) - 25}.")
        print()

    # ------------------------------------- 3. o que a proxima rodada faria
    novas = dados["novas"]
    print("-" * 74)
    print("3. O QUE A PROXIMA RODADA GERARIA, COM AS REGRAS NOVAS")
    print("-" * 74)
    if novas.empty:
        print("   nada: todo pedido em aberto ja esta atendido.\n")
    else:
        com_origem = novas[novas["COLETAR_EM"] != bap.STATUS_SEM_ORIGEM]
        sem_origem = novas[novas["COLETAR_EM"] == bap.STATUS_SEM_ORIGEM]
        print(f"   {len(com_origem)} linha(s) de coleta "
              f"({com_origem['QUANTIDADE'].sum():.0f} unidades)")
        print(f"   {len(sem_origem)} linha(s) SEM ESTOQUE "
              f"({sem_origem['QUANTIDADE'].sum():.0f} unidades)")
    conferidos = dados["contexto"].get("excessos", [])
    criados = [c for c in conferidos if not c.get("herdado")]
    print(f"   trava de conferencia: "
          f"{'OK - nenhum excesso novo' if not criados else str(len(criados)) + ' EXCESSO(S) NOVO(S)'}"
          f" | {len(conferidos) - len(criados)} herdado(s) do arquivo atual\n")

    print("=" * 74)
    print("Nada foi alterado. Este script so le.")
    print("=" * 74)
    return 1 if excessos else 0


if __name__ == "__main__":
    # os Excel do dia a dia moram na RELATORIOS
    pasta = bap.PASTA_RELATORIOS
    solicitacao = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        pasta / bap.ARQUIVO_SOLICITACAO
    tabela = Path(sys.argv[2]) if len(sys.argv) > 2 else pasta / bap.NOME_PLANILHA
    for arquivo in (solicitacao, tabela):
        if not arquivo.exists():
            print(f"nao achei: {arquivo}")
            raise SystemExit(2)
    raise SystemExit(relatorio(solicitacao, tabela))
