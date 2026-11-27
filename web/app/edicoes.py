"""T-0021: edição na web dos faróis, só do perfil admin, chegando ao PC pelo robô.

Genérico por (rid, tabela, modulo): Pedidos (autorização) e Entregas (a linha) hoje; NCC, Garantias,
DDR e Expositores entram acrescentando o lugar em `LUGARES` e o módulo do PC em `MODULOS`.

Três partes:
1. a especificação de edição que vem pronta do PC dentro da tabela (`edicao`), validada aqui
   (`erro_spec`): campos, opções, coluna da tela e a chave de cada linha;
2. o formulário: confere o que a pessoa escolheu contra as opções do pacote (`valores_do_form`);
3. a fila do site (`Fila`): `<dados>/edicoes/EDICOES_WEB_<AAAA-MM>.jsonl`, só acréscimo (como o
   diário da cobrança). O robô lista desde um seq e confirma (aplicada/erro) — a confirmação também
   é uma linha nova. Nada é reescrito.

Nenhuma regra de negócio aqui: quais campos, quais opções e qual a chave vêm do PC; quem grava no
PC é a mesma função da tela do PC, chamada pelo robô.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .arquivos import gravar_json

MANAUS = ZoneInfo("America/Manaus")
EDITA = ("admin",)                         # decisão do Alexandre (25/11): só o admin, por enquanto
# módulos de gravação do PC (bap_relatorios.Janela.salvar): o robô chama a mesma função
MODULOS = ("autorizacoes", "pos_venda", "ncc", "garantias", "farol", "expositores")
# onde a web aceita `edicao` no pacote: (rid, título da tabela) -> módulo do PC
LUGARES = {
    ("pv_pedidos", "Pedidos"): "autorizacoes",
    ("pl_entregas", "Entregas"): "pos_venda",
    ("pl_entregas", "Pendências dos meses anteriores"): "pos_venda",
    ("pl_fretes", "Notas com frete"): "pos_venda",       # T-0037: a mesma linha da aba ENTREGAS (RN-POS-010)
}
# T-0037: lugares que editam a mesma linha do PC: a marca "Aguardando o PC" vale nos dois faróis
# (derivado de LUGARES: mesmo módulo do PC = mesma linha de planilha)
IRMAOS = tuple(frozenset(k for k, m in LUGARES.items() if m == mod)
               for mod in dict.fromkeys(LUGARES.values()))
TIPOS = ("lista", "data", "texto", "numero")
STATUS = ("pendente", "aplicada", "erro")
MSG_ENVIADA = "Edição enviada. Ela chega ao PC na próxima rodada do robô (a cada 30 min)."
MSG_AGUARDA = "Aguardando o PC"
MSG_ERRO = "O PC recusou"
MSG_SEM_CHAVE = "Nota concluída (anterior ao controle de 01/10/2026)."
MSG_SEM_CHAVE_POR_LUGAR = {
    ("pl_fretes", "Notas com frete"): "Sem linha no acompanhamento de entregas. Não dá para editar na web.",
}


def msg_sem_chave(rid: str, tabela: str) -> str:
    return MSG_SEM_CHAVE_POR_LUGAR.get((rid, tabela), MSG_SEM_CHAVE)
ERRO_VISIVEL_DIAS = 3                       # a marca "O PC recusou" fica 3 dias (ou até nova edição)
MAX_CAMPOS = 10
MAX_OPCOES = 400
MAX_GRUPOS = 300
MAX_TEXTO = 60
RE_CAMPO = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
RE_CHAVE = re.compile(r"^[\w .|/-]{0,80}$")
RE_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# texto livre não leva documento, e-mail nem telefone (regra 6)
RE_PESSOAL = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|@|"
                        r"\(?\d{2}\)?\s?9?\d{4}-\d{4}")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def agora() -> datetime:
    return datetime.now(MANAUS)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _strs(v, n=MAX_OPCOES, tam=80) -> bool:
    return isinstance(v, list) and len(v) <= n and all(isinstance(x, str) and len(x) <= tam for x in v)


# ------------------------------------------------------------------ 1. especificação no pacote
def erro_spec(rid: str, titulo: str, ed, nomes_colunas: list[str], n_linhas: int) -> str | None:
    """Erro (sem dado pessoal) da `edicao` de uma tabela, ou None. Lista fechada de chaves."""
    modulo = LUGARES.get((rid, titulo))
    if modulo is None:
        return "edicao fora dos lugares aceitos"
    if not isinstance(ed, dict) or set(ed) - {"modulo", "acao", "chaves", "campos"}:
        return "edicao com chave não aceita"
    if ed.get("modulo") != modulo or modulo not in MODULOS:
        return "edicao com modulo diferente do lugar"
    if ed.get("acao") is not None and not (isinstance(ed["acao"], str) and 0 < len(ed["acao"]) <= 30):
        return "edicao.acao inválida"
    ch = ed.get("chaves")
    if not (isinstance(ch, list) and len(ch) == n_linhas
            and all(isinstance(x, str) and RE_CHAVE.match(x) for x in ch)):
        return "edicao.chaves precisa ter uma chave (texto curto) por linha"
    cs = ed.get("campos")
    if not (isinstance(cs, list) and 0 < len(cs) <= MAX_CAMPOS):
        return "edicao.campos inválidos"
    vistos = set()
    for c in cs:
        if not isinstance(c, dict) or set(c) - {"campo", "rotulo", "coluna", "tipo", "opcoes", "caixa",
                                                 "grupos", "grupo_linhas", "linhas", "sugestoes_linhas"}:
            return "edicao: campo com chave não aceita"
        if not (isinstance(c.get("campo"), str) and RE_CAMPO.match(c["campo"])) or c["campo"] in vistos:
            return "edicao: nome de campo inválido ou repetido"
        vistos.add(c["campo"])
        if not (isinstance(c.get("rotulo"), str) and 0 < len(c["rotulo"]) <= 60):
            return "edicao: rótulo inválido"
        if c.get("coluna") is not None and c["coluna"] not in nomes_colunas:
            return "edicao: coluna que não está na tabela"
        if c.get("tipo") not in TIPOS:
            return "edicao: tipo de campo inválido"
        if not _strs(c.get("opcoes", [])):
            return "edicao: opções inválidas"
        if c.get("caixa") is not None and not isinstance(c["caixa"], bool):
            return "edicao: caixa inválida"
        if c["tipo"] == "data" and not all(RE_DATA_BR.match(x) for x in c.get("opcoes", [])):
            return "edicao: data fora de dd/mm/aaaa"
        gr, gl = c.get("grupos"), c.get("grupo_linhas")
        if (gr is None) != (gl is None):
            return "edicao: grupos e grupo_linhas andam juntos"
        if gr is not None:
            if c["tipo"] != "lista" or not (isinstance(gr, list) and len(gr) <= MAX_GRUPOS
                                            and all(_strs(g) for g in gr)):
                return "edicao: grupos inválidos"
            if not (isinstance(gl, list) and len(gl) == n_linhas
                    and all(_int(i) and -1 <= i < len(gr) for i in gl)):
                return "edicao: grupo_linhas inválido"
        li = c.get("linhas")
        if li is not None and not (isinstance(li, list) and all(_int(i) and 0 <= i < n_linhas for i in li)):
            return "edicao: linhas fora da tabela"
        sg = c.get("sugestoes_linhas")
        if sg is not None and not (c["tipo"] in ("texto", "numero") and _strs(sg, n_linhas, 40)
                                   and len(sg) == n_linhas):
            return "edicao: sugestoes_linhas inválidas"
    return None


def chave_da_linha(ed: dict, k: int) -> str:
    ch = ed.get("chaves") or []
    return ch[k] if 0 <= k < len(ch) else ""


def linha_da_chave(ed: dict, chave: str) -> int | None:
    if not chave:
        return None
    try:
        return (ed.get("chaves") or []).index(chave)
    except ValueError:
        return None


def campos_da_linha(ed: dict, k: int) -> list[dict]:
    """Os campos que valem na linha `k` (como o `so_se` do PC), com as opções dela."""
    out = []
    for c in ed["campos"]:
        if c.get("linhas") is not None and k not in c["linhas"]:
            continue
        ops = list(c.get("opcoes") or [])
        if c.get("grupos") is not None:
            g = c["grupo_linhas"][k]
            ops = list(c["grupos"][g]) if g >= 0 else ops
        sug = (c.get("sugestoes_linhas") or [""] * (k + 1))[k] if c.get("sugestoes_linhas") else ""
        out.append({**c, "opcoes_linha": ops, "sugestao": sug})
    return out


# ------------------------------------------------------------------ 2. formulário
def br_data(v) -> str:
    """Célula da tabela (ISO) ou texto -> dd/mm/aaaa (o formato do PC); "" se vazio."""
    if v in (None, ""):
        return ""
    s = str(v)[:10]
    m = RE_ISO.match(s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(v)


def iso_de_br(s: str) -> str:
    m = RE_DATA_BR.match(s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def numero_br(txt) -> float | None:
    """O valor escrito (R$ 1.234,56 · 278,4 · 278.40) como número; vazio = None; ValueError se não for."""
    if txt is None or isinstance(txt, (int, float)) and not isinstance(txt, bool):
        return None if txt is None else float(txt)
    s = str(txt).strip().upper().replace("R$", "").replace(" ", "")
    if s == "":
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise ValueError(txt)
    return float(s)


def fmt_numero(n: float | None) -> str:
    return "" if n is None else f"{n:.2f}".replace(".", ",")


def atual_txt(c: dict, v) -> str:
    """O valor de hoje do campo, no texto que o formulário mostra (como o PC)."""
    if c["tipo"] == "data":
        return br_data(v)
    if c["tipo"] == "numero":
        try:
            return fmt_numero(numero_br(v))
        except ValueError:
            return ""
    return "" if v is None else str(v)


def valores_do_form(ed: dict, k: int, linha: list, nomes: list[str], form: dict) -> tuple[dict, dict, str]:
    """(mudou {campo: valor no formato do PC}, antes {campo: valor}, erro). Só o que mudou, como o PC."""
    mudou, antes = {}, {}
    for c in campos_da_linha(ed, k):
        chave = "c_" + c["campo"]
        if chave not in form:
            continue
        bruto = str(form.get(chave, ""))
        if len(bruto) > 200 or _CTRL.search(bruto):
            return {}, {}, f"{c['rotulo']}: valor inválido."
        v_atual = linha[nomes.index(c["coluna"])] if c.get("coluna") in nomes else None
        atual = atual_txt(c, v_atual)
        tipo = c["tipo"]
        if tipo == "lista":
            v = bruto.strip()
            if v and v not in c["opcoes_linha"] and v != atual:
                return {}, {}, f"{c['rotulo']}: escolha uma opção da lista."
        elif tipo == "data":
            v = br_data(bruto.strip()) if bruto.strip() else ""
            if v and not RE_DATA_BR.match(v):
                return {}, {}, f"{c['rotulo']}: data inválida."
            if v and v not in c["opcoes_linha"] and v != atual:
                ops = c["opcoes_linha"]
                faixa = f" (de {min(ops, key=iso_de_br)} a {max(ops, key=iso_de_br)})" if ops else ""
                return {}, {}, f"{c['rotulo']}: data fora das permitidas{faixa}."
        elif tipo == "numero":
            try:
                n = numero_br(bruto)
            except ValueError:
                return {}, {}, (f"{c['rotulo']}: \"{bruto[:20]}\" não é um valor. Escreva só o número "
                                "(ex.: 278,40) ou deixe vazio.")
            if n is not None and n < 0:
                return {}, {}, f"{c['rotulo']}: o valor não pode ser negativo."
            a = None
            try:
                a = numero_br(v_atual)
            except ValueError:
                pass
            if (n is None and a is None) or (n is not None and a is not None and abs(n - a) < 0.005):
                continue
            mudou[c["campo"]], antes[c["campo"]] = fmt_numero(n), fmt_numero(a)
            continue
        else:                                           # texto livre (a lista só sugere)
            v = bruto.strip() if c.get("caixa") else bruto.strip().upper()
            if len(v) > MAX_TEXTO:
                return {}, {}, f"{c['rotulo']}: até {MAX_TEXTO} caracteres."
            if RE_PESSOAL.search(v):
                return {}, {}, f"{c['rotulo']}: sem CPF, CNPJ, telefone ou e-mail."
        if v == atual:
            continue
        mudou[c["campo"]], antes[c["campo"]] = v, atual
    return mudou, antes, ""


# ------------------------------------------------------------------ 3. fila do site
class ErroEdicao(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


class Fila:
    """Só acréscimo, fsync. Linha `edicao` (seq novo) ou `status` (ref = seq da edição).
    `estado.json` (gravação atômica): {epoca, ultimo_seq}. O seq nunca é reaproveitado."""

    def __init__(self, dados: Path):
        self.pasta = Path(dados) / "edicoes"
        self._trinco = threading.Lock()

    def _tranca(self):
        from .cobranca import Diario                     # a mesma tranca do diário (thread + flock)
        return Diario._Tranca(self)

    def _arquivos(self) -> list[Path]:
        return sorted(self.pasta.glob("EDICOES_WEB_????-??.jsonl")) if self.pasta.is_dir() else []

    def _ler(self) -> tuple[list[dict], dict]:
        """(edições por seq, {seq: último status})."""
        eds, st = [], {}
        for a in self._arquivos():
            for ln in a.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue                             # linha truncada por queda: ignora
                if not isinstance(r, dict):
                    continue
                if r.get("tipo") == "edicao" and _int(r.get("seq")):
                    eds.append(r)
                elif r.get("tipo") == "status" and _int(r.get("ref")):
                    st[r["ref"]] = r
        eds.sort(key=lambda r: r["seq"])
        return eds, st

    def _estado(self) -> dict:
        try:
            e = json.loads((self.pasta / "estado.json").read_text(encoding="utf-8"))
            if isinstance(e, dict) and isinstance(e.get("epoca"), str) and _int(e.get("ultimo_seq")):
                return e
        except (OSError, ValueError):
            pass
        eds, _ = self._ler()
        e = {"epoca": uuid.uuid4().hex, "ultimo_seq": max([r["seq"] for r in eds] or [0])}
        gravar_json(self.pasta / "estado.json", e)
        return e

    def _acrescentar(self, reg: dict, quando: str) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        with open(self.pasta / f"EDICOES_WEB_{quando[:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def registrar(self, *, usuario: str, rid: str, tabela: str, modulo: str, chave: str,
                  valores: dict, antes: dict, agora_=None) -> dict:
        quando = (agora_ or agora()).astimezone(MANAUS).strftime("%Y-%m-%d %H:%M:%S")
        with self._tranca():
            e = self._estado()
            e["ultimo_seq"] += 1
            gravar_json(self.pasta / "estado.json", e)   # o seq é gasto antes da linha
            reg = {"tipo": "edicao", "seq": e["ultimo_seq"], "id": str(uuid.uuid4()), "quando": quando,
                   "usuario": usuario, "rid": rid, "tabela": tabela, "modulo": modulo, "chave": chave,
                   "valores": valores, "antes": antes}
            self._acrescentar(reg, quando)
            return reg

    # -- API do robô
    def desde(self, desde: int, limite: int = 500) -> dict:
        with self._tranca():
            epoca = self._estado()["epoca"]
            eds, st = self._ler()
        todas = [dict(r, status=(st.get(r["seq"]) or {}).get("status", "pendente"))
                 for r in eds if r["seq"] > desde]
        linhas = todas[:limite]
        ate = linhas[-1]["seq"] if linhas else desde
        return {"epoca": epoca, "linhas": linhas, "ate_seq": ate, "mais": len(todas) > len(linhas)}

    def confirmar(self, epoca, resultados, agora_=None) -> dict:
        if not isinstance(epoca, str) or not isinstance(resultados, list) or len(resultados) > 1000:
            raise ErroEdicao(400, "epoca (texto) e resultados (lista) são obrigatórios")
        for r in resultados:
            if not (isinstance(r, dict) and _int(r.get("seq")) and r.get("status") in ("aplicada", "erro")
                    and isinstance(r.get("motivo", ""), str)):
                raise ErroEdicao(400, "cada resultado precisa de seq (inteiro) e status (aplicada|erro)")
        quando = (agora_ or agora()).astimezone(MANAUS).strftime("%Y-%m-%d %H:%M:%S")
        n = 0
        with self._tranca():
            e = self._estado()
            if epoca != e["epoca"]:
                raise ErroEdicao(409, "epoca")
            eds, st = self._ler()
            existe = {r["seq"] for r in eds}
            for r in resultados:
                if r["seq"] not in existe or r["seq"] in st:
                    continue                              # desconhecido ou já confirmado: idempotente
                reg = {"tipo": "status", "ref": r["seq"], "status": r["status"],
                       "motivo": _CTRL.sub(" ", r.get("motivo") or "")[:120], "quando": quando}
                self._acrescentar(reg, quando)
                st[r["seq"]] = reg
                n += 1
        return {"ok": True, "epoca": epoca, "gravados": n}

    # -- tela
    def situacao(self, rid: str) -> dict:
        """{(tabela, chave): {"status", "valores" (pendentes somados), "quando", "usuario", "motivo", "em"}}
        pela última edição de cada linha."""
        with self._tranca():
            if not self.pasta.is_dir():
                return {}
            eds, st = self._ler()
        out: dict = {}
        for r in eds:
            alvos = self._alvos(rid, r)
            if not alvos:
                continue
            s = st.get(r["seq"]) or {}
            for k in alvos:
                self._junta(out, k, r, s)
        return out

    @staticmethod
    def _alvos(rid: str, r: dict) -> list:
        """Chaves (tabela, chave) em que a edição `r` aparece no farol `rid`: a própria e as dos lugares irmãos."""
        ch, origem = r.get("chave"), (r.get("rid"), r.get("tabela"))
        if r.get("rid") == rid:
            alvos = [(r.get("tabela"), ch)]
        else:
            alvos = []
        for g in IRMAOS:
            if origem in g:
                alvos += [(t, ch) for (rd, t) in g if rd == rid and (t, ch) not in alvos]
        return alvos

    @staticmethod
    def _junta(out: dict, k, r: dict, s: dict) -> None:
        ant = out.get(k)
        status = s.get("status", "pendente")
        valores = dict(ant["valores"]) if ant and ant["status"] == "pendente" and status == "pendente" else {}
        valores.update(r.get("valores") or {})
        out[k] = {"status": status, "valores": valores, "quando": r.get("quando", ""),
                  "usuario": r.get("usuario", ""), "motivo": s.get("motivo", ""), "em": s.get("quando", "")}


def marca(sit: dict | None, recebido_em: str | None, agora_=None) -> str:
    """"pendente" (aguardando o PC), "erro" (o PC recusou) ou "". A aplicada segue "pendente" até chegar
    um pacote recebido depois da confirmação (a tabela ainda mostra o valor antigo)."""
    if not sit:
        return ""
    if sit["status"] == "pendente":
        return "pendente"
    em = sit.get("em") or ""
    rec = _hora_manaus(recebido_em)
    if sit["status"] == "aplicada":
        return "pendente" if (rec is None or rec <= em) else ""
    # erro: fica até a próxima edição da linha ou por ERRO_VISIVEL_DIAS
    limite = ((agora_ or agora()) - timedelta(days=ERRO_VISIVEL_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    return "erro" if em >= limite else ""


def _hora_manaus(iso: str | None) -> str | None:
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    d = d.replace(tzinfo=MANAUS) if d.tzinfo is None else d.astimezone(MANAUS)
    return d.strftime("%Y-%m-%d %H:%M:%S")


def dica(sit: dict | None, ed: dict, m: str, admin: bool) -> str:
    """Texto do title da marca: o que vai ao PC (campos e valores) e, para o admin, o motivo da recusa."""
    if not sit or not m:
        return ""
    rot = {c["campo"]: c["rotulo"] for c in ed.get("campos") or []}
    partes = [f"{rot.get(k, k)}: {v or '(vazio)'}" for k, v in (sit.get("valores") or {}).items()]
    txt = " · ".join(partes)
    if m == "erro" and admin and sit.get("motivo"):
        txt = (txt + " — " if txt else "") + sit["motivo"]
    return txt
