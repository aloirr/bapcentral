"""
CONTROLE DAS NCC (20/10, Alexandre) - o que o pos-venda escreve no Farol de
NCC para cada nota de credito: o STATUS do "A COMPENSAR" (as sugestoes do
farol - NO TITULO, NO PEDIDO, PROX. COMPRA, CONTATAR - mais SOLICITADO
FINANCEIRO, REEMBOLSADO, FINALIZADO e CANCELADO) e a DT. ULT. MOV. (a data
da ultima movimentacao).

SLA da NCC: 3 dias uteis a partir da ultima movimentacao (sem
movimentacao, da EMISSAO da NCC - decisao do Alexandre em 20/10). Conta
para o SLA todo status que nao seja FINALIZADO ou CANCELADO.

Gravacao: um DIARIO por maquina (so acrescenta linha, nunca altera), em
RELATORIOS\\_NCC\\NCC_<MAQUINA>.csv - como o das autorizacoes. Vale a ultima
linha de cada NCC entre todos os arquivos (o OneDrive nunca briga por um
arquivo so). Mudou o status sem escolher a data: a DT. ULT. MOV. vira o dia
de hoje.
"""
from __future__ import annotations

import csv
import os
import platform
import re
from datetime import date, datetime
from pathlib import Path

PASTA = Path("RELATORIOS") / "_NCC"
SLA_NCC = 3                       # dias uteis
SOLICITADO, REEMBOLSADO = "SOLICITADO FINANCEIRO", "REEMBOLSADO"
FINALIZADO, CANCELADO = "FINALIZADO", "CANCELADO"
STATUS_NOVOS = (SOLICITADO, REEMBOLSADO, FINALIZADO, CANCELADO)
ENCERRADOS = (FINALIZADO, CANCELADO)    # nao contam para o SLA
SLA_NO_PRAZO, SLA_ATRASADO, SLA_ENCERRADO = "NO PRAZO", "ATRASADO", \
    "ENCERRADO"
CAMPOS = ("quando", "maquina", "usuario", "ncc", "status", "dt_mov")


def maquina() -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_",
                  os.environ.get("COMPUTERNAME") or platform.node() or "PC")


def chave(filial, prefixo, num, parcela) -> str:
    """A NCC: filial|prefixo|numero|parcela (o titulo do Protheus)."""
    def t(x):
        return str(x or "").strip()
    return f"{t(filial)}|{t(prefixo)}|{t(num).lstrip('0')}|{t(parcela)}"


def pasta(raiz) -> Path:
    return Path(raiz) / PASTA


def data_de(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def ler(raiz) -> dict:
    """{chave: {"status", "dt_mov" (date ou None), "quando"}} - a ultima
    linha de cada NCC."""
    saida = {}
    p_ = pasta(raiz)
    if not p_.exists():
        return saida
    linhas = []
    for arq in sorted(p_.glob("NCC_*.csv")):
        try:
            with open(arq, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f, delimiter=";"):
                    linhas.append(r)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
    for r in sorted(linhas, key=lambda x: x.get("quando") or ""):
        k = (r.get("ncc") or "").strip()
        if not k:
            continue
        saida[k] = {"status": (r.get("status") or "").strip().upper(),
                    "dt_mov": data_de(r.get("dt_mov")),
                    "quando": r.get("quando") or ""}
    return saida


def gravar(raiz, edicoes: dict, hoje: date | None = None) -> int:
    """edicoes: {chave da NCC: {"status": .., "dt_mov": "dd/mm/aaaa"}}. So
    acrescenta linhas (o diario desta maquina). Status mudado sem data
    escolhida: a data da movimentacao e hoje."""
    if not edicoes:
        return 0
    hoje = hoje or date.today()
    p_ = pasta(raiz)
    p_.mkdir(parents=True, exist_ok=True)
    arq = p_ / f"NCC_{maquina()}.csv"
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
            atual = atuais.get(k) or {}
            status = str(campos.get("status", atual.get("status", ""))
                         or "").strip().upper()
            if "dt_mov" in campos:
                dt = data_de(campos.get("dt_mov"))
            elif "status" in campos:
                dt = hoje
            else:
                dt = atual.get("dt_mov")
            w.writerow({"quando": agora, "maquina": maquina(),
                        "usuario": os.environ.get("USERNAME") or "",
                        "ncc": k, "status": status,
                        "dt_mov": f"{dt:%d/%m/%Y}" if dt else ""})
            n += 1
    return n


def sla(status, dt_mov, emissao, hoje, uteis, mais_uteis):
    """(dias uteis desde a ultima movimentacao, prazo, situacao).
    uteis(a, b) e mais_uteis(d, n) sao os do Contexto (com os feriados)."""
    if str(status or "").upper() in ENCERRADOS:
        return None, None, SLA_ENCERRADO
    base = dt_mov or emissao
    if not base:
        return None, None, ""
    prazo = mais_uteis(base, SLA_NCC)
    dias = uteis(base, hoje)
    return dias, prazo, (SLA_ATRASADO if prazo and hoje > prazo
                         else SLA_NO_PRAZO)
