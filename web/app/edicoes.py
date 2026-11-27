"""T-0021: edição na web dos faróis, só do perfil admin, chegando ao PC pelo robô.

Genérico por (rid, tabela, modulo): Pedidos (autorização), Entregas (a linha), NCC pendentes, Devoluções e
Garantias (com linha nova, T-0023 v2); DDR e Expositores entram acrescentando o lugar em `LUGARES`.

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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .arquivos import acrescentar_linha, gravar_json

MANAUS = ZoneInfo("America/Manaus")
EDITA = ("admin",)                         # decisão do Alexandre (25/11): só o admin, por enquanto
# módulos de gravação do PC (bap_relatorios.Janela.salvar): o robô chama a mesma função
MODULOS = ("autorizacoes", "pos_venda", "ncc", "garantias", "farol", "expositores")
# onde a web aceita `edicao` no pacote: (rid, título da tabela) -> módulo do PC
LUGARES = {
    ("pv_pedidos", "Pedidos"): "autorizacoes",
    ("pl_entregas", "Entregas"): "pos_venda",
    ("pl_entregas", "Pendências dos meses anteriores"): "pos_venda",
    # T-0023 v2 (contrato §10.9.3): Pós-venda
    ("pl_ncc", "NCC pendentes"): "ncc",
    ("pl_devolucoes", "Devoluções"): "pos_venda",
    ("pl_garantias", "Garantias"): "garantias",
}
# lugares com linha nova (`novo`, §10.9.2) e o que a linha nova leva sempre (campo obrigatório do lugar)
LUGARES_NOVO = {("pl_garantias", "Garantias"): ("ticket",)}
MSG_NOVO_VAZIO = "Preencha pelo menos um campo além dos padrões."
RE_CHAVE_NOVA = re.compile(r"^NOVO-[0-9A-F]{8}$")
TIPOS = ("lista", "data", "texto", "numero")
STATUS = ("pendente", "aplicada", "erro")
MSG_ENVIADA = "Edição enviada: aguardando o PC."
MSG_AGUARDA = "Aguardando o PC"
MSG_ERRO = "O PC recusou"
MSG_SEM_CHAVE = "Nota concluída (anterior ao controle de 01/10/2026)."
ERRO_VISIVEL_DIAS = 3                       # a marca "O PC recusou" fica 3 dias (ou até nova edição)
MAX_CAMPOS = 16                             # §10.9.1: eram 10; a Garantia tem 14
MAX_OPCOES = 400
MAX_GRUPOS = 300
MAX_TEXTO = 60                              # sem `max` no campo
MAX_TEXTO_TETO = 600                        # teto do `max` (o número vem do núcleo, `MAX_TEXTO_EDICAO`)
REMOVIDO = "[removido]"
DATA_MIN = date(2020, 1, 1)                 # data livre (§10.9.1): de 01/01/2020 até hoje + 1 ano
RE_CAMPO = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
RE_CHAVE = re.compile(r"^[\w .|/-]{0,80}$")
RE_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# Dado pessoal no texto livre (regra 6, RN-GER-011): UMA cópia dos padrões do bloco `padroes-pessoais` do contrato
# (§10.9.1), que é o do núcleo (`relatorios_nucleo.texto_sem_contato`). Um teste confere as duas contra o bloco.
RE_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
RE_DOC_MEIO = re.compile(r"(?<![\w])(?:\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?![\w])")
RE_DOC_SOLTO = re.compile(r"(?<!\d)(?:\d{14}|\d{11})(?!\d)")
RE_FONE = re.compile(r"(?<![\w])(?:\+?55[\s.\-]?)?(?:\(?\d{2}\)?[\s.\-]?)?9?\d{4}[\s.\-]?\d{4}(?![\w]|,\d)")
RE_VALOR_RS = re.compile(r"(R\$\s*\d[\d.]*(?:,\d+)?)")
RE_PESSOAL = (RE_EMAIL, RE_DOC_MEIO, RE_DOC_SOLTO, RE_FONE)


def tem_pessoal(v: str) -> bool:
    """Há trecho que o núcleo trocaria por "[removido]" (CPF, CNPJ, telefone, e-mail)? O valor em R$ nunca é telefone."""
    partes = RE_VALOR_RS.split(str(v))
    return any(r.search(p) for k, p in enumerate(partes) if k % 2 == 0 for r in RE_PESSOAL)


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _contato(txt) -> bool:
    """Coluna ou rótulo de contato/telefone: nunca vai ao site (P2 A da T-0023; regra 6)."""
    from .render import coluna_fora   # import tardio: render importa visitas, que importa este módulo
    return coluna_fora(txt or "") or "CONTATO" in str(txt or "").upper()


def agora() -> datetime:
    return datetime.now(MANAUS)


def _quando(agora_=None) -> str:
    return (agora_ or agora()).astimezone(MANAUS).strftime("%Y-%m-%d %H:%M:%S")


def _com_status(eds: list[dict], st: dict, confirmado: bool = False) -> list[dict]:
    """Cada item com o status de agora (e, se pedido, a hora da confirmação)."""
    return [dict(r, status=(st.get(r["seq"]) or {}).get("status", "pendente"),
                 **({"confirmado_em": (st.get(r["seq"]) or {}).get("quando", "")} if confirmado else {}))
            for r in eds]


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
    if not isinstance(ed, dict) or set(ed) - {"modulo", "acao", "chaves", "campos", "novo"}:
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
    nv = ed.get("novo")
    if nv is not None and not ((rid, titulo) in LUGARES_NOVO and isinstance(nv, dict) and set(nv) == {"rotulo"}
                               and isinstance(nv["rotulo"], str) and 0 < len(nv["rotulo"]) <= 30):
        return "edicao.novo inválido ou fora dos lugares com linha nova"
    vistos = set()
    for c in cs:
        if not isinstance(c, dict) or set(c) - {"campo", "rotulo", "coluna", "tipo", "opcoes", "caixa",
                                                 "grupos", "grupo_linhas", "linhas", "sugestoes_linhas",
                                                 "max", "multilinha", "padrao"}:
            return "edicao: campo com chave não aceita"
        if not (isinstance(c.get("campo"), str) and RE_CAMPO.match(c["campo"])) or c["campo"] in vistos:
            return "edicao: nome de campo inválido ou repetido"
        if c["campo"].startswith(("contato", "fone", "telefone")):
            return "edicao: o contato do cliente não vai ao site"
        vistos.add(c["campo"])
        if not (isinstance(c.get("rotulo"), str) and 0 < len(c["rotulo"]) <= 60):
            return "edicao: rótulo inválido"
        if c.get("coluna") is not None and c["coluna"] not in nomes_colunas:
            return "edicao: coluna que não está na tabela"
        if _contato(c.get("coluna")) or _contato(c.get("rotulo")):
            return "edicao: o contato do cliente não vai ao site"
        if c.get("tipo") not in TIPOS:
            return "edicao: tipo de campo inválido"
        if not _strs(c.get("opcoes", [])):
            return "edicao: opções inválidas"
        if c.get("caixa") is not None and not isinstance(c["caixa"], bool):
            return "edicao: caixa inválida"
        if c["tipo"] == "data" and not all(RE_DATA_BR.match(x) for x in c.get("opcoes", [])):
            return "edicao: data fora de dd/mm/aaaa"
        mx = c.get("max")
        if mx is not None and not (_int(mx) and 1 <= mx <= MAX_TEXTO_TETO and c["tipo"] in ("texto", "numero")):
            return "edicao: max inválido"
        ml = c.get("multilinha")
        if ml is not None and not (isinstance(ml, bool) and (not ml or (c["tipo"] == "texto" and c.get("caixa") is True))):
            return "edicao: multilinha inválida (só em texto, com caixa)"
        pd = c.get("padrao")
        if pd is not None and not (isinstance(pd, str) and len(pd) <= 80 and not _CTRL.search(pd)
                                   and (c["tipo"] != "data" or pd == "@hoje" or RE_DATA_BR.match(pd))
                                   and (c["tipo"] != "lista" or pd in c.get("opcoes", []))):
            return "edicao: padrao inválido"
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
    if isinstance(v, float) and v == int(v):              # QTD 12.0 mostra 12
        return str(int(v))
    return "" if v is None else str(v)


def _norm_texto(v: str) -> str:
    return v.replace("\r\n", "\n").replace("\r", "\n").strip()


def _texto_form(c: dict, s: str) -> str:
    """Texto do formulário normalizado; sem `caixa`, em maiúsculas (como o PC)."""
    v = _norm_texto(s)
    return v if c.get("caixa") else v.upper()


def _mais_um_ano(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:                                  # 29/02
        return d.replace(year=d.year + 1, day=28)


def hoje_manaus() -> date:
    return agora().date()


def data_max(hoje: date | None = None) -> date:
    """Teto da data livre (§10.9.1): hoje + 1 ano."""
    return _mais_um_ano(hoje or hoje_manaus())


MSG_SEM_NOVO = "Esta tabela não aceita linha nova. Volte ao farol."
TITULO_SEM_NOVO = "Não há linha nova aqui"
MSG_FALHA_FILA = "Não foi possível gravar agora. Tente de novo."


def campo_tela(c: dict, atual: str, ops: list, hoje: date | None = None, **extra) -> dict:
    """O campo como o formulário o desenha (Editar e linha nova, uma conta só): valor, opções, min/max da data e teto."""
    atual_br = br_data(atual) if c["tipo"] == "data" else atual     # volta de um erro: o navegador mandou ISO
    isos = sorted(iso_de_br(x) for x in ops) if c["tipo"] == "data" else []
    data = c["tipo"] == "data"
    return {"campo": c["campo"], "rotulo": c["rotulo"], "tipo": c["tipo"],
            "atual": atual_br, "atual_iso": iso_de_br(atual_br), "opcoes": ops, "sugestao": "", "pendente": None,
            "min": isos[0] if isos else (DATA_MIN.isoformat() if data else ""),
            "max": isos[-1] if isos else (data_max(hoje).isoformat() if data else ""),
            "teto": c.get("max") or MAX_TEXTO, "multilinha": bool(c.get("multilinha")), **extra}


def mostrado(form, c: dict) -> str:
    """O padrão que o formulário mostrou (hidden `p_<campo>`); sem ele, o do pacote."""
    return str(form.get("p_" + c["campo"], c["padrao_txt"]))[:80]


def _checa(c: dict, bruto: str, atual: str, v_atual, hoje: date) -> tuple[str | None, str | None, str]:
    """Um campo. (valor novo no formato do PC | None se não mudou, o valor de hoje, erro)."""
    rot, tipo = c["rotulo"], c["tipo"]
    mx = c.get("max") or MAX_TEXTO
    if len(bruto) > (mx if tipo in ("texto", "numero") else 80) + 100:
        return None, None, f"{rot}: valor inválido."
    if tipo == "texto" and c.get("multilinha"):
        ctrl = _CTRL.search(_norm_texto(bruto).replace("\n", ""))
    else:
        ctrl = _CTRL.search(bruto)
    if ctrl:
        return None, None, f"{rot}: valor inválido."
    ops = c["opcoes_linha"]
    if tipo == "lista":
        v = bruto.strip()
        if v and v not in ops and v != atual:
            return None, None, f"{rot}: escolha uma opção da lista."
    elif tipo == "data":
        v = br_data(bruto.strip()) if bruto.strip() else ""
        if v and not RE_DATA_BR.match(v):
            return None, None, f"{rot}: data inválida."
        if v and ops and v not in ops and v != atual:
            faixa = f" (de {min(ops, key=iso_de_br)} a {max(ops, key=iso_de_br)})"
            return None, None, f"{rot}: data fora das permitidas{faixa}."
        if v and not ops and v != atual:                      # data livre (§10.9.1): existe no calendário, de 2020 até hoje + 1 ano
            try:
                d = date(int(v[6:]), int(v[3:5]), int(v[:2]))
            except ValueError:
                return None, None, f"{rot}: data inválida."
            teto = data_max(hoje)
            if not DATA_MIN <= d <= teto:
                return None, None, f"{rot}: data fora das permitidas (de {DATA_MIN:%d/%m/%Y} até {teto:%d/%m/%Y})."
    elif tipo == "numero":
        try:
            n = numero_br(bruto)
        except ValueError:
            return None, None, (f"{rot}: \"{bruto[:20]}\" não é um valor. Escreva só o número "
                                "(ex.: 278,40) ou deixe vazio.")
        if n is not None and n < 0:
            return None, None, f"{rot}: o valor não pode ser negativo."
        a = None
        try:
            a = numero_br(v_atual)
        except ValueError:
            pass
        if (n is None and a is None) or (n is not None and a is not None and abs(n - a) < 0.005):
            return None, None, ""
        return fmt_numero(n), fmt_numero(a), ""
    else:                                                       # texto livre (a lista só sugere)
        v, ref = _texto_form(c, bruto), _texto_form(c, atual)   # os dois lados no mesmo formato (como o PC)
        if v == ref:
            return None, None, ""                               # regra 1 do texto: sem mudança, o campo não vai
        if REMOVIDO.casefold() in v.casefold():                                       # regra 4: o original do PC nunca é trocado pelo texto limpo
            return None, None, f"{rot}: tire o \"{REMOVIDO}\" e escreva o texto de novo."
        if len(v) > mx:
            return None, None, f"{rot}: até {mx} caracteres."
        if tem_pessoal(v):
            return None, None, f"{rot}: sem CPF, CNPJ, telefone ou e-mail."
        return v, _norm_texto(atual), ""
    if v == atual:
        return None, None, ""
    return v, atual, ""


def valores_do_form(ed: dict, k: int, linha: list, nomes: list[str], form: dict,
                    hoje: date | None = None) -> tuple[dict, dict, str]:
    """(mudou {campo: valor no formato do PC}, antes {campo: valor}, erro). Só o que mudou, como o PC."""
    hoje = hoje or hoje_manaus()
    mudou, antes = {}, {}
    for c in campos_da_linha(ed, k):
        chave = "c_" + c["campo"]
        if chave not in form:
            continue
        v_atual = linha[nomes.index(c["coluna"])] if c.get("coluna") in nomes else None
        v, a, erro = _checa(c, str(form.get(chave, "")), atual_txt(c, v_atual), v_atual, hoje)
        if erro:
            return {}, {}, erro
        if v is not None:
            mudou[c["campo"]], antes[c["campo"]] = v, a
    return mudou, antes, ""


# ------------------------------------------------------------------ 2b. linha nova (§10.9.2)
def padrao_do_campo(c: dict, hoje: date) -> str:
    """O valor inicial do campo na linha nova: `padrao` do pacote; "@hoje" = hoje em Manaus (dd/mm/aaaa)."""
    p = c.get("padrao") or ""
    return f"{hoje:%d/%m/%Y}" if p == "@hoje" else p


def campos_novos(ed: dict, hoje: date | None = None) -> list[dict]:
    """Os campos da linha nova: os que não têm `linhas`, cada um com o `padrao` dele. A web não calcula número."""
    hoje = hoje or hoje_manaus()
    out = []
    for c in ed["campos"]:
        if c.get("linhas") is not None:
            continue
        out.append({**c, "opcoes_linha": list(c.get("opcoes") or []), "sugestao": "",
                    "padrao_txt": padrao_do_campo(c, hoje)})
    return out


def valores_do_novo(ed: dict, form: dict, obrigatorios: tuple[str, ...] = (),
                    hoje: date | None = None) -> tuple[dict, dict, str]:
    """(valores, antes, erro) da linha nova. Vai só o que difere do padrão, mais os `obrigatorios` do lugar.
    `antes` = o padrão que o formulário mostrou, só nos campos obrigatórios (ticket da garantia, §10.9.2)."""
    hoje = hoje or hoje_manaus()
    valores, antes = {}, {}
    campos = campos_novos(ed, hoje)
    for c in campos:
        chave = "c_" + c["campo"]
        if chave not in form:
            continue
        padrao = c["padrao_txt"]
        if c["campo"] in obrigatorios and not RE_CHAVE.match(mostrado(form, c)):
            return {}, {}, f"{c['rotulo']}: valor inválido."
        v_atual = padrao if c["tipo"] != "numero" else (padrao or None)
        v, _a, erro = _checa(c, str(form.get(chave, "")), padrao, v_atual, hoje)
        if erro:
            return {}, {}, erro
        if v is not None:
            valores[c["campo"]] = v
    for nome in obrigatorios:                           # o campo obrigatório não pode ser apagado
        if nome in valores and not valores[nome]:
            rot = next((c["rotulo"] for c in campos if c["campo"] == nome), nome)
            return {}, {}, f"{rot}: obrigatório."
    if not valores:
        return {}, {}, MSG_NOVO_VAZIO
    for nome in obrigatorios:
        c = next((x for x in campos if x["campo"] == nome), None)
        if c is None:
            return {}, {}, f"{nome}: campo obrigatório fora do pacote."
        if nome not in valores:
            v = _texto_form(c, str(form.get("c_" + nome, c["padrao_txt"])))
            if not v:
                return {}, {}, f"{c['rotulo']}: obrigatório."
            valores[nome] = v
        antes[nome] = mostrado(form, c)
    return valores, antes, ""


def chave_nova() -> str:
    """"NOVO-" + 8 hexadecimais maiúsculos (uuid4), §10.9.2."""
    return "NOVO-" + uuid.uuid4().hex[:8].upper()


# ------------------------------------------------------------------ 3. fila do site
class ErroEdicao(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


class Fila:
    """Só acréscimo, fsync. Linha `edicao` (seq novo) ou `status` (ref = seq da edição).
    `estado.json` (gravação atômica): {epoca, ultimo_seq}. O seq nunca é reaproveitado."""

    def __init__(self, dados: Path, subpasta: str = "edicoes", prefixo: str = "EDICOES_WEB"):
        # T-0045: a mesma fila serve às edições e aos lotes de visitas (pasta e prefixo do arquivo mudam)
        self.pasta = Path(dados) / subpasta
        self.prefixo = prefixo
        self._trinco = threading.Lock()

    def _tranca(self):
        from .cobranca import Diario                     # a mesma tranca do diário (thread + flock)
        return Diario._Tranca(self)

    def _arquivos(self) -> list[Path]:
        return sorted(self.pasta.glob(f"{self.prefixo}_????-??.jsonl")) if self.pasta.is_dir() else []

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
        acrescentar_linha(self.pasta / f"{self.prefixo}_{quando[:7]}.jsonl", reg)

    def registrar(self, *, usuario: str, rid: str, tabela: str, modulo: str, chave: str,
                  valores: dict, antes: dict, agora_=None, novo: bool = False) -> dict:
        campos = {"id": str(uuid.uuid4()), "usuario": usuario, "rid": rid, "tabela": tabela,
                  "modulo": modulo, "chave": chave, "valores": valores, "antes": antes}
        if novo:
            campos["novo"] = True                        # §10.9.2: linha nova, chave NOVO-xxxxxxxx
        return self.registrar_item(campos, agora_=agora_)

    def registrar_item(self, campos: dict, antes_de_gravar=None, agora_=None) -> dict:
        """Acrescenta um item (edição ou lote de visitas). `antes_de_gravar(seq)` roda com o seq já reservado e
        antes da linha (o corpo do lote vai ao disco primeiro: linha sem corpo nunca existe)."""
        quando = _quando(agora_)
        with self._tranca():
            e = self._estado()
            e["ultimo_seq"] += 1
            gravar_json(self.pasta / "estado.json", e)   # o seq é gasto antes da linha
            if antes_de_gravar:
                antes_de_gravar(e["ultimo_seq"])
            reg = {"tipo": "edicao", "seq": e["ultimo_seq"], "quando": quando, **campos}
            self._acrescentar(reg, quando)
            return reg

    def itens(self) -> list[dict]:
        """Todos os itens com o status de agora (a tela e a retenção das visitas)."""
        with self._tranca():
            eds, st = self._ler()
        return _com_status(eds, st, confirmado=True)

    # -- API do robô
    def desde(self, desde: int, limite: int = 500) -> dict:
        with self._tranca():
            epoca = self._estado()["epoca"]
            eds, st = self._ler()
        todas = [r for r in _com_status(eds, st) if r["seq"] > desde]
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
        quando = _quando(agora_)
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
            if r.get("rid") != rid:
                continue
            s = st.get(r["seq"]) or {}
            k = (r.get("tabela"), r.get("chave"))
            ant = out.get(k)
            status = s.get("status", "pendente")
            valores = dict(ant["valores"]) if ant and ant["status"] == "pendente" and status == "pendente" else {}
            valores.update(r.get("valores") or {})
            out[k] = {"status": status, "valores": valores, "quando": r.get("quando", ""),
                      "usuario": r.get("usuario", ""), "motivo": s.get("motivo", ""), "em": s.get("quando", "")}
        return out


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


def contagem_novas(sit: dict, tabela: str, recebido_em: str | None, agora_=None) -> dict:
    """As linhas novas desta tabela que ainda não chegaram à tabela: {"pendentes": n, "recusadas": n} (§10.9.2).
    Mesma regra da `marca`: a aplicada segue pendente até chegar um pacote recebido depois da confirmação."""
    n = {"pendentes": 0, "recusadas": 0}
    for (tab, chave), s in (sit or {}).items():
        if tab != tabela or not RE_CHAVE_NOVA.match(str(chave or "")):
            continue
        m = marca(s, recebido_em, agora_)
        if m == "pendente":
            n["pendentes"] += 1
        elif m == "erro":
            n["recusadas"] += 1
    return n
