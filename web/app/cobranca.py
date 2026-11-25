"""T-0017 (contrato §10.6): tabelas Títulos e Por cliente e a fila "Cobrar no WhatsApp".

Aqui ficam: a validação do pacote (lista fechada de colunas, sem telefone/CNPJ/CPF/e-mail), os
perfis (RN-POS-004), a situação da cobrança (RN-POS-002) e o diário do site (RN-POS-003).
Nenhuma regra de cobrança é decidida aqui: fila, mensagem, número e `ultimo` vêm prontos do PC.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import tabelas
from .arquivos import gravar_json

try:                                    # Render é Linux; sem fcntl só vale o trinco da thread
    import fcntl
except ImportError:                     # pragma: no cover
    fcntl = None

MANAUS = ZoneInfo("America/Manaus")
RID = "pl_inadimplencia"
VE_TABELAS = ("admin", "pos_venda", "gerente")     # RN-POS-004
COBRA = ("admin", "pos_venda")
ABAS = (("resumo", "Resumo"), ("titulos", "Títulos"), ("cliente", "Por cliente"),
        ("cobrar", "Cobrar no WhatsApp"))
ABA_TABELA = {"titulos": "Títulos", "cliente": "Por cliente"}

_OC = ("STATUS PROTHEUS", "SITUAÇÃO PLANNER")      # ocultas no PC: vêm no pacote, a tela não desenha
_T = [("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("FILIAL", "texto"), ("NF", "texto"),
      ("PARC.", "texto"), ("EMISSÃO", "data"), ("VENCIMENTO", "data"), ("DIAS ATRASO", "int"),
      ("CLIENTE", "texto"), ("NOME", "texto"), ("STATUS PROTHEUS", "texto"), ("STATUS", "texto"),
      ("SITUAÇÃO PLANNER", "texto"), ("CIDADE", "texto"), ("UF", "texto"), ("VENDEDOR", "texto"),
      ("SUPERVISOR", "texto"), ("CONDIÇÃO", "texto"), ("VALOR", "moeda"), ("SALDO", "moeda")]
_C = [("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("CLIENTE", "texto"), ("NOME", "texto"),
      ("STATUS PROTHEUS", "texto"), ("STATUS", "texto"), ("SITUAÇÃO PLANNER", "texto"),
      ("CIDADE", "texto"), ("UF", "texto"), ("VENDEDOR", "texto"), ("SUPERVISOR", "texto"),
      ("TÍTULOS VENCIDOS", "int"), ("EM ATRASO", "moeda"), ("MAIOR ATRASO", "int"),
      ("A VENCER", "moeda"), ("PRÓX. VENCIMENTO", "data"), ("LIMITE", "moeda"),
      ("PEDIDO EM ABERTO", "moeda"), ("ÚLTIMA COMPRA", "data")]
COLUNAS = {"Títulos": _T, "Por cliente": _C}        # §10.6.2: PC depois do montar, menos TELEFONE
STATUS_BLOCO = ("STATUS PROTHEUS", "STATUS", "SITUAÇÃO PLANNER")   # opcionais em bloco (3 ou nenhuma)
COLUNAS_CHIP = ("SITUAÇÃO", "FAIXA", "STATUS")                     # `chip`: selo colorido do PC
RE_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")


# Só a ordem na TELA muda (o pacote segue a ordem do PC): cliente, nome e o valor primeiro.
ORDEM_TELA = {"Títulos": ("CLIENTE", "NOME", "SALDO", "VALOR"),
              "Por cliente": ("CLIENTE", "NOME", "EM ATRASO")}


def ordem_tela(titulo: str, cols) -> list[int]:
    nomes = [n for n, _ in cols]
    pri = [nomes.index(n) for n in ORDEM_TELA[titulo] if n in nomes]
    return pri + [k for k in range(len(nomes)) if k not in pri]


def colunas_esperadas(titulo: str, cols) -> list[tuple[str, str]]:
    """A lista do PC; sem as 3 colunas de status só se nenhuma delas veio (qualquer outra mistura recusa)."""
    cheia = COLUNAS[titulo]
    tem = [c.get("nome") for c in cols if isinstance(c, dict) and c.get("nome") in STATUS_BLOCO]
    return cheia if tem else [(n, t) for n, t in cheia if n not in STATUS_BLOCO]


def _chip_ok(chip) -> bool:
    return isinstance(chip, dict) and len(chip) <= 60 and all(
        isinstance(k, str) and len(k) < 60 and isinstance(v, (list, tuple)) and len(v) == 2
        and all(isinstance(x, str) and RE_COR.match(x) for x in v) for k, v in chip.items())
PROIBIDAS_TABELA = {"edicao", "editar", "abrir", "detalhe", "kpis_de", "recortes", "juntas"}
COLUNAS_PROIBIDAS = {"TELEFONE", "CNPJ", "CPF", "E-MAIL", "EMAIL"}
CHAVES_TABELA = {"titulo", "colunas", "linhas", "tons", "total", "filtros"}
CHAVES_ITEM = {"cod", "nome", "nome_msg", "cidade", "uf", "vendedor", "supervisor", "em_atraso",
               "maior", "whatsapp", "aviso", "titulos", "mensagem", "ultimo"}
CHAVES_COBRANCA = {"gerado_em", "web_epoca", "web_ate_seq", "dias_recente", "modelo", "fila"}
MAX_LINHAS = 60000
MAX_FILA = 5000
RE_ZAP = re.compile(r"^55\d{2}\d{8,9}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_QUANDO = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
ACOES = ("ENVIADO", "PULADO")
REPETIDO_S = 60
RETENCAO_DIAS = 30


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ------------------------------------------------------------------ validação do pacote
def _achar_proibida(o, nivel=0) -> str | None:
    if nivel > 8:
        return "aninhado demais"
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and (k in PROIBIDAS_TABELA or k.startswith("_")
                                       or k.startswith("exportar") or k.upper() in COLUNAS_PROIBIDAS):
                return k[:20]
            achou = _achar_proibida(v, nivel + 1)
            if achou:
                return achou
    elif isinstance(o, list):
        for v in o[:50]:
            achou = _achar_proibida(v, nivel + 1) if isinstance(v, (dict, list)) else None
            if achou:
                return achou
    return None


def _celula_ok(v, tipo) -> bool:
    if v is None:
        return True
    if tipo in ("int", "moeda"):
        return _num(v)
    if tipo == "data":
        return isinstance(v, str) and (v == "" or bool(RE_DATA.match(v)))
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _tabela_erro(t, titulo) -> str | None:
    if not isinstance(t, dict) or t.get("titulo") != titulo:
        return f"tabela {titulo}: titulo inesperado"
    achou = _achar_proibida({k: v for k, v in t.items() if k != "linhas"})
    if achou or (set(t) - CHAVES_TABELA):
        return f"tabela {titulo}: chave não aceita: {achou or sorted(set(t) - CHAVES_TABELA)[0][:20]}"
    cols = t.get("colunas")
    if not isinstance(cols, list):
        return f"tabela {titulo}: colunas ausentes"
    nomes = [str(c.get("nome", "")).upper() if isinstance(c, dict) else "" for c in cols]
    if COLUNAS_PROIBIDAS & set(nomes):
        return f"tabela {titulo}: coluna proibida (telefone, CNPJ, CPF ou e-mail)"
    esperado = colunas_esperadas(titulo, cols)
    ok = len(cols) == len(esperado) and all(
        isinstance(c, dict) and c.get("nome") == n and c.get("tipo") == tp
        and (set(c) - {"nome", "tipo", "largura", "oculta", "chip", "larg_fixa"} == set())
        and (c.get("larg_fixa") is None or _int(c.get("larg_fixa")))
        and (c.get("chip") is None or (n in COLUNAS_CHIP and _chip_ok(c["chip"])))
        and (c.get("largura") is None or _int(c.get("largura")))
        and bool(c.get("oculta")) == (n in _OC)            # mesma marca "oculta" do PC
        for c, (n, tp) in zip(cols, esperado))
    if not ok:
        return f"tabela {titulo}: colunas diferentes da lista permitida"
    linhas, tons = t.get("linhas"), t.get("tons")
    if not isinstance(linhas, list) or len(linhas) > MAX_LINHAS:
        return f"tabela {titulo}: linhas inválidas"
    for ln in linhas:
        if not (isinstance(ln, list) and len(ln) == len(esperado)
                and all(_celula_ok(v, tp) for v, (_, tp) in zip(ln, esperado))):
            return f"tabela {titulo}: linha com células inválidas"
    if not (isinstance(tons, list) and len(tons) == len(linhas)
            and all(isinstance(x, str) and len(x) < 20 for x in tons)):
        return f"tabela {titulo}: tons inválidos"
    tot = t.get("total")
    if tot is not None and not (isinstance(tot, list) and len(tot) == len(esperado)
                                and all(_celula_ok(v, tp) for v, (_, tp) in zip(tot, esperado))):
        return f"tabela {titulo}: total inválido"
    nm = {n for n, _ in COLUNAS[titulo]}                # filtro de coluna ausente é ignorado na tela
    fl = t.get("filtros", [])
    if not isinstance(fl, list):
        return f"tabela {titulo}: filtros inválidos"
    for f in fl:
        col = f if isinstance(f, str) else (f.get("coluna") if isinstance(f, dict) else None)
        if col not in nm or (isinstance(f, dict) and set(f) - {"coluna", "padrao", "multi"}):
            return f"tabela {titulo}: filtro fora da lista de colunas"
    return None


def _ultimo_ok(u) -> bool:
    return u is None or (isinstance(u, dict) and set(u) == {"quando", "acao", "origem"}
                         and isinstance(u["quando"], str) and RE_QUANDO.match(u["quando"])
                         and u["acao"] in ACOES and u["origem"] in ("PC", "WEB"))


def _item_erro(it) -> str | None:
    if not isinstance(it, dict) or set(it) != CHAVES_ITEM:
        return "item da fila com chaves diferentes do contrato"
    for k in ("cod", "nome", "nome_msg", "cidade", "uf", "vendedor", "supervisor", "aviso", "mensagem"):
        if not isinstance(it[k], str):
            return f"item da fila: {k} inválido"
    if not it["cod"] or len(it["mensagem"]) > 4000:
        return "item da fila: cod ou mensagem inválidos"
    if not (_num(it["em_atraso"]) and _int(it["maior"])):
        return "item da fila: valores inválidos"
    if it["whatsapp"] != "" and not (isinstance(it["whatsapp"], str) and RE_ZAP.match(it["whatsapp"])):
        return "item da fila: whatsapp inválido"
    ts = it["titulos"]
    if not (isinstance(ts, list) and len(ts) <= 500 and all(
            isinstance(t, dict) and set(t) == {"nf", "parc", "venc", "dias", "saldo"}
            and isinstance(t["nf"], str) and isinstance(t["parc"], str)
            and isinstance(t["venc"], str) and RE_DATA.match(t["venc"])
            and _int(t["dias"]) and _num(t["saldo"]) for t in ts)):
        return "item da fila: titulos inválidos"
    if not _ultimo_ok(it["ultimo"]):
        return "item da fila: ultimo inválido"
    return None


def _iso_ok(v) -> bool:
    try:
        return isinstance(v, str) and len(v) < 40 and bool(datetime.fromisoformat(v))
    except ValueError:
        return False


def _cobranca_erro(c) -> str | None:
    if not isinstance(c, dict) or set(c) != CHAVES_COBRANCA:
        return "cobranca com chaves diferentes do contrato"
    if not _iso_ok(c["gerado_em"]) or not (_int(c["web_ate_seq"]) and c["web_ate_seq"] >= 0):
        return "cobranca: gerado_em ou web_ate_seq inválidos"
    if not (isinstance(c["web_epoca"], str) and len(c["web_epoca"]) <= 64):
        return "cobranca: web_epoca inválida"
    if not (_int(c["dias_recente"]) and 0 < c["dias_recente"] <= 90) or not isinstance(c["modelo"], str):
        return "cobranca: dias_recente ou modelo inválidos"
    fila = c["fila"]
    if not isinstance(fila, list) or len(fila) > MAX_FILA:
        return "cobranca: fila inválida"
    vistos = set()
    for it in fila:
        e = _item_erro(it)
        if e:
            return "cobranca: " + e
        if it["cod"] in vistos:
            return "cobranca: cliente repetido na fila"
        vistos.add(it["cod"])
    return None


def validar(rid: str, r: dict) -> list[str]:
    """Erros de `tabelas` e `cobranca` de um farol (§10.6). Só o pl_inadimplencia pode trazê-las,
    e as duas juntas. Mensagens sem dado pessoal."""
    tem_t, tem_c = "tabelas" in r, "cobranca" in r
    if not (tem_t or tem_c):
        return []
    if rid != RID:
        return [f"{rid}: tabelas e cobranca só no {RID}"]
    if tem_t != tem_c:
        return [f"{rid}: tabelas e cobranca vão juntas"]
    ts = r["tabelas"]
    if not (isinstance(ts, list) and len(ts) == 2):
        return [f"{rid}: tabelas precisa ter Títulos e Por cliente"]
    for t, titulo in zip(ts, COLUNAS):
        e = _tabela_erro(t, titulo)
        if e:
            return [f"{rid}: {e}"]
    e = _cobranca_erro(r["cobranca"])
    return [f"{rid}: {e}"] if e else []


# ------------------------------------------------------------------ telefone (= celular() do PC)
def celular(v) -> str:
    """Mesma regra do `cobranca_whatsapp.celular()`: '55'+DDD+número ou '' (inválido)."""
    for parte in re.split(r"[/;,|]| e ", str(v or "")) or [""]:
        d = re.sub(r"\D", "", parte)
        if d.startswith("55") and len(d) >= 12:
            d = d[2:]
        d = d.lstrip("0")
        if len(d) < 10:
            continue
        ddd, num = d[:2], d[2:]
        if len(num) == 8 and num[0] in "6789":
            num = "9" + num
        if len(set(num[1:])) <= 1:
            return ""
        if len(num) in (8, 9):
            return f"55{ddd}{num}"
    return ""


# ------------------------------------------------------------------ situação (RN-POS-002)
def agora() -> datetime:
    return datetime.now(MANAUS)


FILA_POR_PAGINA = 10


def aviso_curto(aviso: str) -> str:
    """Aviso do `celular()` do PC em frase de ação, curta."""
    a = (aviso or "").lower()
    if not a:
        return ""
    if "sem telefone" in a:
        return "Sem celular: digite um número"
    if "fixo" in a:
        return "Fixo: confira se tem WhatsApp"
    if "repetido" in a:
        return "Número com dígitos repetidos: digite o certo"
    return aviso


def situacao(ultimo: dict | None, dias_recente: int, hoje: date) -> str:
    if not ultimo:
        return ""
    try:
        d = datetime.strptime(ultimo["quando"][:10], "%Y-%m-%d").date()
    except (KeyError, ValueError, TypeError):
        return ""
    if ultimo.get("acao") == "PULADO":
        return "PULADO HOJE" if d == hoje else ""
    if d == hoje:
        return "ENVIADO HOJE"
    if 0 < (hoje - d).days < dias_recente:
        return f"ENVIADO {d:%d/%m}"
    return ""


def ultimo_efetivo(item: dict, extras: list[dict]) -> dict | None:
    """O `ultimo` do pacote mais os registros do diário do site ainda não vistos pelo PC
    (`seq > web_ate_seq`) daquele cliente: vale o de `quando` maior."""
    melhor = item.get("ultimo")
    for r in extras:
        if r["cliente"] == item["cod"] and (not melhor or r["quando"] >= melhor["quando"]):
            melhor = {"quando": r["quando"], "acao": r["acao"], "origem": "WEB"}
    return melhor


# ------------------------------------------------------------------ diário do site (§10.6.5)
class ErroCobranca(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


def _mes_de(nome: str) -> str:
    return nome[len("COBRANCA_WEB_"):len("COBRANCA_WEB_") + 7]


class Diario:
    """`<dados>/cobranca/COBRANCA_WEB_<AAAA-MM>.jsonl`: só acréscimo, fsync, nenhuma linha reescrita.
    `estado.json` (gravação atômica): {epoca, ultimo_seq, confirmado_ate, confirmado_em,
    arquivos{nome:{maior_seq, confirmado_em}}} (§10.6.5). A limpeza é por arquivo de mês fechado,
    30 dias depois da confirmação que cobriu o `maior_seq` dele."""

    def __init__(self, dados: Path):
        self.pasta = Path(dados) / "cobranca"
        self._trinco = threading.Lock()
        self._rec: dict[tuple, tuple] = {}              # (usuario, cliente, acao) -> (t, registro)

    # -- baixo nível
    def _arquivos(self) -> list[Path]:
        return sorted(self.pasta.glob("COBRANCA_WEB_????-??.jsonl")) if self.pasta.is_dir() else []

    def _ler(self) -> list[dict]:
        out = []
        for a in self._arquivos():
            for ln in a.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue                         # linha truncada por queda: ignora
                if isinstance(r, dict) and _int(r.get("seq")):
                    out.append(r)
        out.sort(key=lambda r: r["seq"])
        return out

    def _estado(self) -> dict:
        """Lê o estado; sem `estado.json` cria época nova e começa o seq acima do maior dos jsonl."""
        try:
            e = json.loads((self.pasta / "estado.json").read_text(encoding="utf-8"))
            if isinstance(e, dict) and isinstance(e.get("epoca"), str) and _int(e.get("ultimo_seq")):
                e.setdefault("confirmado_ate", 0)
                e.setdefault("confirmado_em", None)
                e.setdefault("arquivos", {})
                return e
        except (OSError, ValueError):
            pass
        arqs = {}
        for a in self._arquivos():
            seqs = []
            for ln in a.read_text(encoding="utf-8").splitlines():
                try:
                    seqs.append(int(json.loads(ln)["seq"]))
                except (ValueError, KeyError, TypeError):
                    continue
            arqs[a.name] = {"maior_seq": max(seqs or [0]), "confirmado_em": None}
        e = {"epoca": uuid.uuid4().hex,
             "ultimo_seq": max([v["maior_seq"] for v in arqs.values()] or [0]),
             "confirmado_ate": 0, "confirmado_em": None, "arquivos": arqs}
        self._gravar_estado(e)
        return e

    def _gravar_estado(self, e: dict) -> None:
        gravar_json(self.pasta / "estado.json", e)

    class _Tranca:
        def __init__(self, d):
            self.d = d

        def __enter__(self):
            self.d._trinco.acquire()
            self.f = None
            try:
                if fcntl:
                    self.d.pasta.mkdir(parents=True, exist_ok=True)
                    self.f = open(self.d.pasta / ".trava", "a")
                    fcntl.flock(self.f, fcntl.LOCK_EX)
            except BaseException:                       # não deixa o trinco da thread preso
                if self.f:
                    self.f.close()
                self.d._trinco.release()
                raise

        def __exit__(self, *a):
            if self.f:
                fcntl.flock(self.f, fcntl.LOCK_UN)
                self.f.close()
            self.d._trinco.release()

    def _tranca(self):
        return Diario._Tranca(self)

    def limpar(self, agora_=None) -> None:
        """Retenção (§10.6.5): roda em toda confirmação aceita e quando o app sobe."""
        with self._tranca():
            self._limpar(self._estado(), agora_ or agora(), gravar=False)

    def epoca(self) -> str:
        with self._tranca():
            return self._estado()["epoca"]

    # -- registrar
    def registrar(self, *, usuario, cliente, acao, telefone, em_atraso, titulos, pacote_sha,
                  agora_=None) -> tuple[dict, bool]:
        """(registro, repetido). Mesmo usuario+cliente+acao em menos de 60 s devolve o original."""
        agora_ = agora_ or agora()
        with self._tranca():
            chave, t = (usuario, cliente, acao), time.monotonic()
            ant = self._rec.get(chave)
            if ant and t - ant[0] < REPETIDO_S:
                return ant[1], True
            e = self._estado()
            seq = e["ultimo_seq"] + 1
            quando = agora_.astimezone(MANAUS).strftime("%Y-%m-%d %H:%M:%S")
            nome = f"COBRANCA_WEB_{quando[:7]}.jsonl"
            e["ultimo_seq"] = seq
            a = e["arquivos"].setdefault(nome, {"maior_seq": 0, "confirmado_em": None})
            a["maior_seq"], a["confirmado_em"] = seq, None
            self._gravar_estado(e)                   # o seq é gasto antes da linha: nunca reaproveitado
            reg = {"seq": seq, "id": str(uuid.uuid4()), "quando": quando,
                   "usuario": usuario, "cliente": cliente, "telefone": telefone,
                   "em_atraso": float(em_atraso), "titulos": int(titulos), "acao": acao,
                   "pacote_sha": pacote_sha}
            with open(self.pasta / nome, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._rec[chave] = (t, reg)
            self._limpar(e, agora_)
            return reg, False

    # -- API do robô (§10.6.6)
    def desde(self, desde: int, limite: int = 1000) -> dict:
        with self._tranca():
            epoca = self._estado()["epoca"]
            todas = [r for r in self._ler() if r["seq"] > desde]
        linhas = todas[:limite]
        ate = linhas[-1]["seq"] if linhas else desde
        return {"epoca": epoca, "linhas": linhas, "ate_seq": ate, "mais": len(todas) > len(linhas)}

    def confirmar(self, epoca, ate_seq, agora_=None) -> dict:
        if not isinstance(epoca, str) or not _int(ate_seq) or ate_seq < 0:
            raise ErroCobranca(400, "epoca (texto) e ate_seq (inteiro >= 0) são obrigatórios")
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._estado()
            if epoca != e["epoca"]:
                raise ErroCobranca(409, "epoca")
            if ate_seq > e["ultimo_seq"]:
                raise ErroCobranca(409, "ate_seq maior que o último seq gravado")
            if ate_seq > e["confirmado_ate"]:
                e["confirmado_ate"] = ate_seq
                e["confirmado_em"] = agora_.astimezone(MANAUS).strftime("%Y-%m-%d %H:%M:%S")
            self._limpar(e, agora_, gravar=True)
            return {"ok": True, "epoca": e["epoca"], "confirmado_ate": e["confirmado_ate"]}

    # -- retenção ("3 A"), por arquivo de mês fechado (§10.6.5)
    def _limpar(self, e: dict, agora_: datetime, gravar: bool = False) -> None:
        agora_ = agora_.astimezone(MANAUS)
        mes_atual = agora_.strftime("%Y-%m")
        mudou = gravar
        for nome, a in list(e["arquivos"].items()):
            if _mes_de(nome) >= mes_atual:
                continue                              # só mês fechado
            if a["confirmado_em"] is None and e["confirmado_ate"] >= a["maior_seq"]:
                a["confirmado_em"] = agora_.strftime("%Y-%m-%d %H:%M:%S")
                mudou = True
            if a["confirmado_em"] is not None:
                desde = datetime.strptime(a["confirmado_em"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MANAUS)
                if agora_ - desde >= timedelta(days=RETENCAO_DIAS):
                    (self.pasta / nome).unlink(missing_ok=True)
                    del e["arquivos"][nome]
                    mudou = True
        if mudou:
            self._gravar_estado(e)

    def pendentes(self, web_epoca: str, web_ate_seq: int) -> list[dict]:
        """Registros que o PC ainda não viu (§10.6.3): `seq > web_ate_seq` se a época é a atual;
        senão, todos."""
        with self._tranca():
            atual = self._estado()["epoca"]
            return [r for r in self._ler() if web_epoca != atual or r["seq"] > web_ate_seq]


# ------------------------------------------------------------------ registro de acesso
RETENCAO_ACESSO_DIAS = 90


def registrar_acesso(dados: Path, login: str, rid: str, aba: str, acao: str) -> None:
    """Login, rid, aba, ação e hora, em `<dados>/acessos/` (90 dias). Nunca cliente nem telefone."""
    reg = {"quando": agora().strftime("%Y-%m-%d %H:%M:%S"), "login": login, "rid": rid,
           "aba": aba, "acao": acao}
    pasta = Path(dados) / "acessos"
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / f"ACESSO_{reg['quando'][:7]}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    corte = (agora() - timedelta(days=RETENCAO_ACESSO_DIAS + 31)).strftime("%Y-%m")
    for a in pasta.glob("ACESSO_????-??.jsonl"):       # mês que acabou há mais de 90 dias
        if a.name[7:14] < corte:
            a.unlink(missing_ok=True)


# ------------------------------------------------------------------ apresentação das tabelas
def fmt_celula(v, tipo) -> str:
    """Inadimplência: moeda com centavos (a tela de sempre). A regra geral está em `tabelas.fmt_celula`."""
    return tabelas.fmt_celula(v, tipo, centavos=True)


def tabela_para_tela(t: dict, titulo: str, consulta: dict, pagina_tam: int = 100) -> dict:
    """Filtra, ordena e pagina no servidor. `consulta`: f<i> (lista de valores), ord, dir, pag.
    Desde a T-0017 (§10.7) é a tela genérica de `tabelas`, com o mesmo resultado de antes:
    cliente, nome e valor primeiro, moeda com centavos e o total sempre à mostra."""
    cols = colunas_esperadas(titulo, t["colunas"])
    return tabelas.tabela_para_tela(t, consulta, pagina_tam=pagina_tam, ordem_tela=ordem_tela(titulo, cols),
                                    centavos=True, total_sempre=True, vazios_no_fim=False, titulo=titulo)


def fone_bonito(n: str) -> str:
    d = n[2:] if n.startswith("55") else n
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return n
