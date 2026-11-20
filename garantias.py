"""
GARANTIAS (14/10) - o acompanhamento das garantias do Pos-venda (Farol de
Garantias). Cada garantia e um TICKET; a assistente edita na tela (duplo
clique no Farol de Garantias): status, resultado da analise, retorno do
cliente, pendencias, cliente, produto, quantidade, contato.

    STATUS ............ ABERTO, EM TRATATIVA, FINALIZADA, CANCELADA
    RESULTADO ANALISE . PENDENTE, PROCEDENTE, IMPROCEDENTE
    DT. FECHAMENTO .... o prazo: DT. SOLICITACAO + 15 dias uteis; a
                        assistente pode editar na garantia (06/11)
    SLA ATUAL ......... dias da solicitacao ate hoje (finalizada/cancelada:
                        ate a data em que fechou - para de contar)
    PRAZO ............. ATRASADA (aberta depois da DT. FECHAMENTO), NO
                        PRAZO, FECHADA (no prazo: verde; depois da DT.
                        FECHAMENTO: verde-oliva)

TICKET editavel (06/11): a troca do numero e uma linha do diario (campo
"ticket", valor = o numero novo) - a leitura segue a garantia pelo numero
novo dali em diante; nada do que ja foi gravado e alterado.

Gravacao: um DIARIO por maquina (so acrescenta linha, nunca altera), em
RELATORIOS\\_GARANTIAS\\GARANTIAS_<MAQUINA>.csv - uma linha por campo
alterado (quando; maquina; usuario; ticket; campo; valor). Vale a ultima
de cada campo entre todos os arquivos (o OneDrive nunca briga por um
arquivo so). A planilha antiga (ANALISE BAP) entrou uma vez so, pelo
GARANTIAS_IMPORTACAO.csv.
"""
from __future__ import annotations

import csv
import os
import platform
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path("RELATORIOS") / "_GARANTIAS"
CAMPO_TICKET = "ticket"      # (06/11) a linha que troca o numero do ticket
STATUS = ("ABERTO", "EM TRATATIVA", "FINALIZADA", "CANCELADA")
FECHADOS = ("FINALIZADA", "CANCELADA")
RESULTADOS = ("PENDENTE", "PROCEDENTE", "IMPROCEDENTE")
PRAZO_DIAS = 30          # (ate 05/11) o prazo antigo, em dias corridos
# (06/11, Alexandre) "troque DT. PREVISTA para DT. FECHAMENTO (15 uteis a
# partir da abertura por padrao, mas pode ser editado)"
PRAZO_UTEIS = 15
AVISO_UTEIS = 3          # faltando ate 3 dias uteis: o SLA fica amarelo
CAMPOS_CSV = ("quando", "maquina", "usuario", "ticket", "campo", "valor")
# os campos de uma garantia (o que a tela edita)
CAMPOS = ("dt_solicitacao", "cod_cliente", "cliente", "cod_produto",
          "descricao", "qtd", "contato_nome", "contato_fone", "status",
          "resultado", "reclamacao", "pendencias", "retorno_cliente",
          "dt_retorno", "observacao", "dt_fechamento", "origem",
          "dt_prazo",
          "cli_fantasia", "cli_endereco", "cli_bairro", "cli_cidade",
          "cli_uf", "cli_telefone", "cli_vendedor", "cli_supervisor")
# (14/10, Alexandre) o CADASTRO do cliente editavel na garantia: vale o
# da garantia; em branco, o da base de clientes (a base nao muda - ela vem
# do Protheus; a correcao fica no diario da garantia)
CAMPOS_CLIENTE = (("cli_fantasia", "Fantasia"), ("cli_endereco", "Endereço"),
                  ("cli_bairro", "Bairro"), ("cli_cidade", "Cidade"),
                  ("cli_uf", "UF"), ("cli_telefone", "Telefone (cadastro)"),
                  ("cli_vendedor", "Vendedor"),
                  ("cli_supervisor", "Supervisor"))


def cadastro(g, base: dict) -> dict:
    """{cli_*: valor} - o da garantia; em branco, o da base."""
    return {k: texto(g.get(k)) or texto(base.get(k))
            for k, _ in CAMPOS_CLIENTE}


def maquina() -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_",
                  os.environ.get("COMPUTERNAME") or platform.node() or "PC")


def pasta(raiz) -> Path:
    return Path(raiz) / PASTA


def texto(v) -> str:
    return "" if v is None else str(v).strip()


def norm(v) -> str:
    t = unicodedata.normalize("NFKD", texto(v)).encode(
        "ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def data(v):
    """date de 'dd/mm/aaaa', 'aaaa-mm-dd', date ou datetime."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = texto(v)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except ValueError:
            continue
    return None


def fone(v) -> str:
    """(92) 98187-5642 a partir dos digitos; o que nao parece telefone
    fica como veio."""
    d = re.sub(r"\D", "", texto(v))
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return texto(v)


# ---------------------------------------------------------------- leitura
def ler(raiz) -> dict:
    """{ticket: {campo: valor, ..., "_alterada": quando}} - a ultima linha de
    cada campo entre todos os diarios."""
    p_ = pasta(raiz)
    linhas = []
    if p_.exists():
        for arq in sorted(p_.glob("GARANTIAS_*.csv")):
            try:
                with open(arq, encoding="utf-8-sig", newline="") as f:
                    linhas.extend(csv.DictReader(f, delimiter=";"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
    saida = {}
    for r in sorted(linhas, key=lambda x: x.get("quando") or ""):
        t = texto(r.get("ticket"))
        c = texto(r.get("campo"))
        if t and c == CAMPO_TICKET:
            # (06/11) troca do numero: a garantia passa a ser a do numero
            # novo (o que ja havia no numero novo fica por baixo)
            novo = texto(r.get("valor"))
            if novo and novo != t and t in saida:
                g = saida.pop(t)
                antes = saida.pop(novo, {})
                g = {**antes, **g, "ticket": novo,
                     "_ticket_antes": (g.get("_ticket_antes") or [])
                     + [t]}
                g["_alterada"] = r.get("quando") or ""
                g["_por"] = r.get("usuario") or ""
                saida[novo] = g
            continue
        if not t or c not in CAMPOS:
            continue
        g = saida.setdefault(t, {"ticket": t})
        g[c] = r.get("valor") or ""
        g["_alterada"] = r.get("quando") or ""
        g["_por"] = r.get("usuario") or ""
    return saida


def somar_uteis(inicio, dias, fer=()):
    """inicio + dias uteis (sem sabado, domingo e feriado)."""
    d, n = inicio, 0
    while n < dias:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            n += 1
    return d


def uteis_entre(de, ate, fer=()) -> int:
    """Dias uteis depois de 'de' ate 'ate' (inclusive); negativo se ja
    passou."""
    if ate < de:
        return -uteis_entre(ate, de, fer)
    n, d = 0, de
    while d < ate:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            n += 1
    return n


def prazo_padrao(inicio, fer=()):
    """(06/11) a DT. FECHAMENTO de quem nao editou: 15 dias uteis."""
    return somar_uteis(inicio, PRAZO_UTEIS, fer) if inicio else None


def situacao(g, hoje=None, fer=()) -> dict:
    """DT. FECHAMENTO (o prazo), SLA ATUAL, ATRASADA e, na fechada, se
    fechou no prazo. (06/11) o prazo e a DT. FECHAMENTO editada na garantia
    ou, em branco, a solicitacao + 15 dias uteis."""
    hoje = hoje or date.today()
    ini = data(g.get("dt_solicitacao"))
    prev = data(g.get("dt_prazo")) or prazo_padrao(ini, fer)
    fechada = texto(g.get("status")).upper() in FECHADOS
    fim = (data(g.get("dt_fechamento")) or hoje) if fechada else hoje
    sla = (fim - ini).days if ini else None
    atrasada = bool(prev and not fechada and hoje > prev)
    no_prazo = bool(fechada and (prev is None or fim <= prev))
    if fechada:
        tom = "cinza"                   # o SLA parou de contar
        chave = "FECHADA NO PRAZO" if no_prazo else "FECHADA COM ATRASO"
    elif atrasada:
        tom, chave = "alerta", "ATRASADA"
    else:
        falta = uteis_entre(hoje, prev, fer) if prev else None
        tom = "atencao" if falta is not None and falta <= AVISO_UTEIS \
            else "ok"
        chave = "NO PRAZO"
    return {"inicio": ini, "prevista": prev, "sla": sla, "fechada": fechada,
            "atrasada": atrasada, "no_prazo": no_prazo, "tom_sla": tom,
            "chave_prazo": chave, "fim": fim if fechada else None,
            "prazo_editado": bool(data(g.get("dt_prazo")))}


# ---------------------------------------------------------------- gravacao
def gravar(raiz, ticket, campos: dict, arquivo=None, agora=None) -> int:
    """So acrescenta: uma linha por campo que mudou. STATUS finalizada ou
    cancelada sem data de fechamento ganha a data de hoje."""
    atual = ler(raiz).get(texto(ticket), {})
    campos = dict(campos)
    st = texto(campos.get("status", atual.get("status"))).upper()
    if st in FECHADOS and not texto(campos.get(
            "dt_fechamento", atual.get("dt_fechamento"))):
        campos["dt_fechamento"] = (agora or datetime.now()).strftime(
            "%d/%m/%Y")
    if st and st not in FECHADOS and texto(atual.get("dt_fechamento")):
        campos.setdefault("dt_fechamento", "")     # reaberta
    mudou = {k: texto(v) for k, v in campos.items()
             if k in CAMPOS and texto(v) != texto(atual.get(k))}
    if not mudou:
        return 0
    _anexar(raiz, ticket, mudou, arquivo, agora)
    return len(mudou)


def renomear(raiz, antigo, novo, arquivo=None, agora=None) -> str:
    """(06/11) troca o numero do ticket. Devolve "" (feito) ou o motivo de
    nao trocar (vazio, igual, ja existe outra garantia com esse numero)."""
    antigo, novo = texto(antigo), texto(novo)
    if not novo:
        return "o ticket não pode ficar em branco"
    if re.search(r"[;\r\n]", novo):
        return "o ticket não pode ter ; nem quebra de linha"
    if novo == antigo:
        return ""
    dados = ler(raiz)
    if novo in dados:
        return f"já existe a garantia {novo}"
    if not antigo:                      # garantia nova: so a validacao
        return ""
    if antigo not in dados:
        return f"a garantia {antigo} não existe"
    _anexar(raiz, antigo, {CAMPO_TICKET: novo}, arquivo, agora)
    return ""


def _anexar(raiz, ticket, mudou: dict, arquivo=None, agora=None):
    """Acrescenta as linhas (campo, valor) no diario desta maquina."""
    p_ = pasta(raiz)
    p_.mkdir(parents=True, exist_ok=True)
    arq = p_ / (arquivo or f"GARANTIAS_{maquina()}.csv")
    novo = not arq.exists()
    quando = (agora or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with open(arq, "a", encoding="utf-8-sig" if novo else "utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, delimiter=";")
        if novo:
            w.writeheader()
        for k, v in mudou.items():
            w.writerow({"quando": quando, "maquina": maquina(),
                        "usuario": os.environ.get("USERNAME") or "",
                        "ticket": texto(ticket), "campo": k, "valor": v})


def novo_ticket(raiz) -> str:
    """G-0001, G-0002... (os tickets do site seguem com o numero deles)."""
    usados = [int(m.group(1)) for t in ler(raiz)
              for m in [re.fullmatch(r"G-(\d+)", t)] if m]
    return f"G-{(max(usados) + 1) if usados else 1:04d}"


# ---------------------------------------------------------------- importacao
STATUS_DA_PLANILHA = {"FINALIZADO": "FINALIZADA", "FINALIZADA": "FINALIZADA",
                      "CANCELADO": "CANCELADA", "CANCELADA": "CANCELADA",
                      "ABERTO": "ABERTO", "NOVO": "ABERTO"}


def _qtd(v) -> str:
    m = re.search(r"(\d+)", texto(v))
    return m.group(1) if m else ""


def _entrada_retorno(v):
    """'DATA DE ENTRADA - 12/08/2026 as 14:08  RETORNO - 13/08/2026 ...'."""
    t = texto(v)
    ent = re.search(r"ENTRADA\D*(\d{2}/\d{2}/\d{4})", t, re.I)
    ret = re.search(r"RETORNO\D*(\d{2}/\d{2}/\d{4})", t, re.I)
    return (ent.group(1) if ent else ""), (ret.group(1) if ret else "")


def ler_planilha_analise(arq) -> list:
    """A planilha ANALISE BAP (ticket, data, cliente, reclamacao, o que foi
    pedido sem retorno, obs, quant, contato, status) -> garantias."""
    from openpyxl import load_workbook                  # noqa: PLC0415
    wb = load_workbook(arq, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    saida = []
    for r in ws.iter_rows(values_only=True):
        r = list(r) + [None] * 9
        if not re.fullmatch(r"\d{4,}", texto(r[0]).split(".")[0]):
            continue
        ent, ret = _entrada_retorno(r[1])
        st_pl = norm(r[8])
        status = STATUS_DA_PLANILHA.get(st_pl, "EM TRATATIVA" if st_pl
                                        else "ABERTO")
        saida.append({
            "ticket": texto(r[0]).split(".")[0], "dt_solicitacao": ent,
            "dt_retorno": ret, "cliente": texto(r[2]),
            "reclamacao": texto(r[3]), "pendencias": texto(r[4]),
            "observacao": " · ".join(x for x in (
                texto(r[5]), f"Status na planilha: {texto(r[8])}"
                if texto(r[8]) else "") if x),
            "qtd": _qtd(r[6]), "contato_nome": texto(r[2]),
            "contato_fone": fone(r[7]), "status": status,
            "resultado": "PENDENTE",
            "dt_fechamento": ret if status in FECHADOS else "",
            "origem": "PLANILHA ANALISE BAP"})
    wb.close()
    return saida


SUFIXOS = {"LTDA", "ME", "EPP", "EIRELI", "SA", "S A", "MEI"}


def nome_canonico(v) -> str:
    """O nome para comparar com a base: sem acento, sem o CNPJ/numero do
    MEI na frente, sem LTDA/ME/EPP/EIRELI no fim e sem o plural
    (SERVICOS = SERVICO)."""
    toks = norm(v).split()
    while toks and re.fullmatch(r"[\d]+", toks[0]):
        toks.pop(0)
    while toks and toks[-1] in SUFIXOS:
        toks.pop()
    return " ".join(t[:-1] if len(t) > 3 and t.endswith("S") else t
                    for t in toks)


def contato_da_base(c) -> tuple:
    """(nome, telefone) do campo CONTATO da base ('NOME · (98) 9...')."""
    t = texto(c.get("contato"))
    if " · " in t:
        n_, f_ = t.split(" · ", 1)
        return n_.strip(), f_.strip()
    return ("", t) if re.search(r"\d{4}", t) else (t, "")


def casar_clientes(garantias: list, clientes: list) -> int:
    """(14/10, Alexandre) O CLIENTE pelo NOME da planilha na nossa base
    (razao social ou fantasia): igual, ou igual sem LTDA/ME/EPP, sem o
    CNPJ do MEI e sem plural. So vale quando acha UM cliente. Achou: o
    CONTATO (nome + telefone) passa a ser o da base; o telefone do ticket
    fica na observacao."""
    por_nome = {}
    for c in clientes:
        for n_ in {nome_canonico(c.get("nome")),
                   nome_canonico(c.get("fantasia"))}:
            if n_:
                por_nome.setdefault(n_, {})[c["cod"]] = c
    n = 0
    for g in garantias:
        if g.get("cod_cliente"):
            continue
        cand = por_nome.get(nome_canonico(g.get("cliente")), {})
        if len(cand) != 1:
            continue
        cod, c = next(iter(cand.items()))
        g["cod_cliente"] = cod
        nome_b, fone_b = contato_da_base(c)
        if nome_b or fone_b:
            tk_ = " ".join(x for x in (texto(g.get("contato_nome")),
                                       texto(g.get("contato_fone"))) if x)
            g["contato_nome"] = nome_b or texto(g.get("contato_nome"))
            g["contato_fone"] = fone_b or texto(g.get("contato_fone"))
            if tk_:
                g["observacao"] = " · ".join(x for x in (
                    texto(g.get("observacao")),
                    f"Contato do ticket: {tk_}") if x)
        n += 1
    return n


def importar(raiz, garantias: list, agora=None) -> int:
    """Grava no GARANTIAS_IMPORTACAO.csv so os tickets que ainda nao
    existem (rodar de novo nao duplica nem desfaz o que foi editado)."""
    existentes = ler(raiz)
    n = 0
    for g in garantias:
        if g["ticket"] in existentes:
            continue
        gravar(raiz, g["ticket"], {k: v for k, v in g.items()
                                   if k in CAMPOS},
               arquivo="GARANTIAS_IMPORTACAO.csv", agora=agora)
        n += 1
    return n
