"""
AUTORIZACOES DE VENDA (13/10) - o CODIGO DE AUTORIZACAO e QUEM AUTORIZOU
(ALEXANDRE ou PRICE) de cada pedido, escritos no Farol de Pedidos (ou no
Farol de Saldo) e lidos por todos os farois com detalhe de pedido.

Regra do saldo de desconto (teto 15%):
  - o financeiro da condicao de pagamento (a vista -1,71%, prazo +2,89%...)
    nunca gera nem consome saldo;
  - pedido com desconto comercial ate 15%: a sobra entra no saldo;
  - acima de 15% AUTORIZADO PELO ALEXANDRE: o excesso desconta do saldo;
  - acima de 15% SEM AUTORIZACAO: tambem desconta e fica com a linha
    VERMELHA (de 01/08/2026 em diante) no Farol de Saldo e no Farol de
    Pedidos ate alguem informar quem autorizou;
  - acima de 15% AUTORIZADO PELO PRICE: e o unico que NAO desconta.

Gravacao: um DIARIO por maquina (so acrescenta linha, nunca altera), em
RELATORIOS\\_AUTORIZACOES\\AUTORIZACOES_<MAQUINA>.csv. Vale a ultima linha
de cada pedido entre todos os arquivos (o OneDrive nunca briga por um
arquivo so). O que veio do Protheus (ftAutorizacaoVenda) entra como codigo
inicial; o que foi escrito aqui manda.
"""
from __future__ import annotations

import csv
import os
import platform
import re
from datetime import datetime
from pathlib import Path

PASTA = Path("RELATORIOS") / "_AUTORIZACOES"
QUEM = ("ALEXANDRE", "PRICE")
CAMPOS = ("quando", "maquina", "usuario", "filial", "pedido", "codigo", "por")


def maquina() -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_",
                  os.environ.get("COMPUTERNAME") or platform.node() or "PC")


def chave(filial, pedido) -> str:
    f_ = re.sub(r"\D", "", str(filial or ""))
    p_ = re.sub(r"\D", "", str(pedido or ""))
    return f"{f_}|{p_.zfill(6) if p_ else ''}"


def pasta(raiz) -> Path:
    return Path(raiz) / PASTA


def ler(raiz) -> dict:
    """{chave: {"codigo", "por", "quando"}} - a ultima de cada pedido."""
    saida = {}
    p_ = pasta(raiz)
    if not p_.exists():
        return saida
    linhas = []
    for arq in sorted(p_.glob("AUTORIZACOES_*.csv")):
        try:
            with open(arq, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f, delimiter=";"):
                    linhas.append(r)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
    for r in sorted(linhas, key=lambda x: x.get("quando") or ""):
        k = chave(r.get("filial"), r.get("pedido"))
        por = (r.get("por") or "").strip().upper()
        saida[k] = {"codigo": (r.get("codigo") or "").strip(),
                    "por": por if por in QUEM else "",
                    "quando": r.get("quando") or ""}
    return saida


def gravar(raiz, edicoes: dict) -> int:
    """edicoes: {chave "filial|pedido": {"codigo": .., "por": ..}}. So
    acrescenta linhas (o diario desta maquina)."""
    if not edicoes:
        return 0
    p_ = pasta(raiz)
    p_.mkdir(parents=True, exist_ok=True)
    arq = p_ / f"AUTORIZACOES_{maquina()}.csv"
    novo = not arq.exists()
    atuais = ler(raiz)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    with open(arq, "a", encoding="utf-8-sig" if novo else "utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        for k, campos in edicoes.items():
            fil, _, ped = str(k).partition("|")
            atual = atuais.get(chave(fil, ped)) or {}
            cod = campos.get("codigo", atual.get("codigo", ""))
            por = (campos.get("por", atual.get("por", "")) or "").upper()
            w.writerow({"quando": agora, "maquina": maquina(),
                        "usuario": os.environ.get("USERNAME") or "",
                        "filial": fil, "pedido": ped,
                        "codigo": (cod or "").strip(),
                        "por": por if por in QUEM else ""})
            n += 1
    return n
