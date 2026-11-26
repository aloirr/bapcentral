"""Pacote do robô (parte dado do contrato, §10): validar, guardar, ler."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import cobranca, render, tabelas
from .arquivos import gravar_json

FAROIS = tuple(render.FAROIS)                   # T-0017: forma "farol"
ACEITOS = ("vc_painel",) + FAROIS
PROIBIDAS = ("tabelas", "juntas", "edicao", "editar", "abrir")   # a web é só leitura
ABAS = render.CHAVES_ABAS                      # fonte única
MANAUS = ZoneInfo("America/Manaus")
GUARDAR = 7                                    # RN-POS-003: o Render guarda os 7 últimos


def nome_arquivo(gerado_em: str) -> str:
    """Nome pela hora de Manaus (sem fuso no texto = já Manaus); ValueError se não for ISO."""
    d = datetime.fromisoformat(gerado_em)
    d = d.replace(tzinfo=MANAUS) if d.tzinfo is None else d.astimezone(MANAUS)
    return re.sub(r"[^0-9A-Za-z]", "", d.strftime("%Y%m%dT%H%M%S"))


def _int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _cartao_ok(c) -> bool:
    if not (isinstance(c, dict) and isinstance(c.get("titulo"), str) and isinstance(c.get("valor"), str)):
        return False
    aneis, faixa = c.get("aneis"), c.get("faixa")
    if aneis is not None and not (isinstance(aneis, list) and all(
            isinstance(a, list) and len(a) == 3 for a in aneis)):
        return False
    if faixa is not None and not (isinstance(faixa, list) and all(
            isinstance(f, list) and len(f) == 4 for f in faixa)):
        return False
    e = c.get("estados")
    if e is None:
        return True
    barras = e.get("barras") if isinstance(e, dict) else False
    return barras is None or (isinstance(barras, list) and all(
        isinstance(b, list) and len(b) == 5 for b in barras))


RE_UF = re.compile(r"^[A-Z]{2}$")
MAX_RECORTES = 30


def _recortes_erros(rec) -> str | None:
    """T-0014: visões prontas por estado (opcional). Só formato: o número vem pronto do PC."""
    if rec is None:
        return None
    if not isinstance(rec, dict):
        return "recortes precisa ser objeto"
    ufs = rec.get("uf") or {}
    if not isinstance(ufs, dict) or set(rec) - {"uf"}:
        return "recortes precisa ser {\"uf\": {...}}"
    if len(ufs) > MAX_RECORTES:
        return "recortes demais"
    for uf, v in ufs.items():
        cs = v.get("cartoes") if isinstance(v, dict) else None
        if not RE_UF.match(str(uf)) or not isinstance(cs, list) or not all(_cartao_ok(c) for c in cs):
            return f"recorte {str(uf)[:4]} inválido"
    return None


def _chave_proibida(o, nivel=0) -> str | None:
    """Chave de edição/tabela ou interna (_): o farol da web não carrega nada disso."""
    if nivel > 12:
        return "aninhado demais"
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and (k in PROIBIDAS or k.startswith("_")):
                return k[:20]
            achou = _chave_proibida(v, nivel + 1)
            if achou:
                return achou
    elif isinstance(o, list):
        for v in o:
            achou = _chave_proibida(v, nivel + 1)
            if achou:
                return achou
    return None


def _kpi_ok(k) -> bool:
    if not (isinstance(k, dict) and isinstance(k.get("rotulo"), str) and isinstance(k.get("valor"), str)):
        return False
    ln = k.get("linhas")
    if not (ln is None or (isinstance(ln, list) and all(isinstance(x, list) and len(x) >= 2 for x in ln))):
        return False
    e = k.get("estados")                         # barrinhas por estado no cartão (como o PC)
    if e is None:
        return True
    bs = e.get("barras") if isinstance(e, dict) else False
    return isinstance(bs, list) and len(bs) <= 30 and all(isinstance(b, list) and len(b) == 5 for b in bs)


def _kpis_ok(ks) -> bool:
    return isinstance(ks, list) and len(ks) <= 40 and all(_kpi_ok(k) for k in ks)


def _tabela_ok(b) -> bool:
    """Bloco tabela do farol: só formato; recusa coluna de cliente, CNPJ ou telefone (regra 6)."""
    cols, linhas = b.get("colunas"), b.get("linhas")
    if not (isinstance(cols, list) and 0 < len(cols) <= 20 and isinstance(linhas, list) and len(linhas) <= 500):
        return False
    for c in cols:
        nome = c.get("nome") if isinstance(c, dict) else c
        if not isinstance(nome, str) or render.coluna_proibida(nome):
            return False
    tot = b.get("total")
    return all(isinstance(x, list) for x in linhas) and (tot is None or isinstance(tot, list))


PARCIAIS_RIDS = ("pv_pedidos", "pl_entregas", "vc_visitas")
QUANDOS_PARCIAL = ("acum", "d1", "hoje")
MAX_PNG_B64 = 3_000_000                          # por imagem (a do PC tem uns 100 a 400 KB)


def _parciais_erro(rid: str, p) -> str | None:
    """T-0026: imagens da parcial (PNG em base64, prontas no PC). Só formato: precisa ser PNG de verdade."""
    if p is None:
        return None
    if rid not in PARCIAIS_RIDS:
        return f"{rid}: parciais só em Pedidos, Entregas e Visita"
    if not isinstance(p, dict) or not p or set(p) - set(QUANDOS_PARCIAL):
        return f"{rid}: parciais precisa ser {{acum, d1, hoje}}"
    for q, v in p.items():
        if not (isinstance(v, dict) and set(v) == {"rotulo", "png"} and isinstance(v["rotulo"], str)
                and len(v["rotulo"]) <= 80 and isinstance(v["png"], str) and len(v["png"]) <= MAX_PNG_B64):
            return f"{rid}: parcial {q} inválida"
        try:
            ok = base64.b64decode(v["png"], validate=True)[:8] == b"\x89PNG\r\n\x1a\n"
        except ValueError:
            ok = False
        if not ok:
            return f"{rid}: parcial {q} não é PNG"
    return None


def validar_farol(rid: str, r) -> list[str]:
    """Forma "farol" (T-0017): só formato; kpis e blocos vêm prontos do PC (contrato §8)."""
    if not isinstance(r, dict) or r.get("forma") != "farol":
        return [f"{rid}: forma precisa ser farol"]
    # §10.6 (tabelas e cobranca do pl_inadimplencia) e §10.7 (tabelas dos outros três faróis)
    erros_t = tabelas.validar(rid, r) if rid in tabelas.RIDS else cobranca.validar(rid, r)
    if erros_t:
        return erros_t
    achou = _chave_proibida({k: v for k, v in r.items() if k not in ("tabelas", "cobranca")})
    if achou:
        return [f"{rid}: chave não aceita na web: {achou}"]
    if not isinstance(r.get("titulo"), str):
        return [f"{rid}: titulo ausente"]
    if not _kpis_ok(r.get("kpis")):
        return [f"{rid}: kpis inválidos"]
    bl = (r.get("painel") or {}).get("blocos") if isinstance(r.get("painel"), dict) else None
    if not (isinstance(bl, list) and len(bl) <= 30 and all(isinstance(b, dict) and isinstance(b.get("tipo"), str) for b in bl)):
        return [f"{rid}: painel.blocos inválido"]
    for b in bl:
        if b["tipo"] == "tabela" and not _tabela_ok(b):
            return [f"{rid}: bloco tabela inválido ou com coluna de cliente/CNPJ/telefone"]
    if r.get("kpis_faixa") is not None and not isinstance(r["kpis_faixa"], bool):
        return [f"{rid}: kpis_faixa inválido"]
    ins = r.get("insights_painel")
    if ins is not None and not (isinstance(ins, list) and len(ins) <= 40 and all(
            isinstance(x, list) and len(x) >= 2 and isinstance(x[1], str) for x in ins)):
        return [f"{rid}: insights_painel inválido"]
    av = r.get("avisos")
    if av is not None and not (isinstance(av, list) and all(isinstance(a, str) for a in av)):
        return [f"{rid}: avisos inválidos"]
    if r.get("baixado_em") is not None and not isinstance(r["baixado_em"], str):
        return [f"{rid}: baixado_em inválido"]
    e_par = _parciais_erro(rid, r.get("parciais"))
    if e_par:
        return [e_par]
    rec = r.get("recortes")
    if rec is not None:
        if not isinstance(rec, dict) or len(rec) > MAX_RECORTES:
            return [f"{rid}: recortes inválidos"]
        for uf, v in rec.items():
            if not RE_UF.match(str(uf)) or not isinstance(v, dict) or not _kpis_ok(v.get("kpis")):
                return [f"{rid}: recorte {str(uf)[:4]} inválido"]
    return []


def validar(c) -> list[str]:
    erros: list[str] = []
    if not isinstance(c, dict):
        return ["o corpo precisa ser um objeto JSON"]
    if isinstance(c.get("versao_contrato"), bool) or not isinstance(c.get("versao_contrato"), (int, str)):
        erros.append("versao_contrato ausente")
    ge = c.get("gerado_em")
    try:
        if not isinstance(ge, str) or len(ge) > 40:
            raise ValueError
        datetime.fromisoformat(ge)
        if not nome_arquivo(ge):
            raise ValueError
    except ValueError:
        erros.append("gerado_em precisa ser data ISO 8601")
    if not _int(c.get("ano"), 2000, 2100):
        erros.append("ano inválido")
    if not _int(c.get("mes"), 1, 12):
        erros.append("mes inválido")
    rels = c.get("relatorios")
    if not isinstance(rels, dict) or not rels:
        return erros + ["relatorios ausente"]
    for k, r in rels.items():
        if k not in ACEITOS:
            erros.append(f"relatório não aceito: {str(k)[:40]}")
            continue
        if k in FAROIS:
            erros += validar_farol(k, r)
            continue
        if not isinstance(r, dict) or not isinstance(r.get("titulo"), str):
            erros.append(f"{k}: titulo ausente")
            continue
        abas = r.get("abas")
        if not isinstance(abas, dict):
            erros.append(f"{k}: abas ausente")
            continue
        for chave, visao in ABAS:
            a = abas.get(chave)
            if not isinstance(a, dict) or not isinstance(a.get("titulo"), str):
                erros.append(f"{k}.abas.{chave}: ausente")
                continue
            bl = (a.get("painel") or {}).get("blocos") if isinstance(a.get("painel"), dict) else None
            b = bl[0] if isinstance(bl, list) and bl and isinstance(bl[0], dict) else {}
            d = b.get("dados")
            if b.get("tipo") != "rrm" or b.get("visao") != visao or not isinstance(d, dict):
                erros.append(f"{k}.abas.{chave}: painel.blocos[0] precisa ser rrm/{visao} com dados")
                continue
            if d.get("sub") is not None and not isinstance(d.get("sub"), dict):
                erros.append(f"{k}.abas.{chave}: sub precisa ser objeto")
                continue
            cs = d.get(visao)
            if not isinstance(cs, list) or not cs or not all(_cartao_ok(c) for c in cs):
                erros.append(f"{k}.abas.{chave}: cartões inválidos")
                continue
            er = _recortes_erros(a.get("recortes"))
            if er:
                erros.append(f"{k}.abas.{chave}: {er}")
    return erros[:10]


def _sem_internas(o):
    """Chaves com _ são internas do contrato (§10, item 2): nunca guardadas."""
    if isinstance(o, dict):
        return {k: _sem_internas(v) for k, v in o.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(o, list):
        return [_sem_internas(v) for v in o]
    return o


def _enxuto(corpo: dict) -> dict:
    """Guarda só o que a tela lê: por aba, os cartões da visão, `sub`, `como_ler`, avisos."""
    for rel in corpo["relatorios"].values():
        if rel.get("forma") == "farol":
            continue                                   # farol já vem enxuto do PC
        for chave, visao in ABAS:
            a = rel["abas"][chave]
            d = a["painel"]["blocos"][0]["dados"]
            a["painel"]["blocos"][0]["dados"] = {
                visao: d[visao], "sub": {visao: (d.get("sub") or {}).get(visao, "")},
                "como_ler": d.get("como_ler", ""), "avisos": d.get("avisos", []),
                "ano": d.get("ano"), "mes": d.get("mes")}
            a.pop("diretor", None)
    return corpo


def gravar(dados: Path, corpo: dict, recebido_em: str) -> Path:
    pasta = dados / "pacotes"
    corpo = _enxuto(_sem_internas(corpo))
    corpo["recebido_em"] = recebido_em
    destino = pasta / (nome_arquivo(corpo["gerado_em"]) + ".json")
    gravar_json(destino, corpo)
    for velho in listar(dados)[:-GUARDAR]:
        velho.unlink(missing_ok=True)
    return destino


def listar(dados: Path) -> list[Path]:
    pasta = dados / "pacotes"
    return sorted(pasta.glob("*.json")) if pasta.is_dir() else []


class Ultimo:
    """Lê o pacote mais recente, com cache por (nome, mtime)."""

    def __init__(self, dados: Path):
        self.dados = dados
        self._chave = None
        self._val = None
        self._sha = ""

    def sha(self) -> str:
        """sha256 (hex) do pacote ativo, para o diário da cobrança."""
        self.get()
        return self._sha

    def get(self) -> dict | None:
        arqs = listar(self.dados)
        if not arqs:
            return None
        a = arqs[-1]
        chave = (a.name, a.stat().st_mtime_ns)
        if chave != self._chave:
            bruto = a.read_bytes()
            self._sha = hashlib.sha256(bruto).hexdigest()
            self._val = json.loads(bruto.decode("utf-8"))
            self._chave = chave
        return self._val


_MEMO_SHA: dict = {}


def por_sha(dados: Path, sha: str) -> dict | None:
    """O pacote guardado (entre os 7 últimos) cujo sha256 é `sha`; None se já saiu (§10.6.4)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
        return None
    guardados = listar(dados)
    for velho in [k for k in _MEMO_SHA if k[0] not in {str(a) for a in guardados}]:
        del _MEMO_SHA[velho]                               # só os pacotes ainda guardados
    for a in reversed(guardados):
        chave = (str(a), a.stat().st_mtime_ns)
        if chave not in _MEMO_SHA:
            _MEMO_SHA[chave] = hashlib.sha256(a.read_bytes()).hexdigest()
        if _MEMO_SHA[chave] == sha:
            return json.loads(a.read_text(encoding="utf-8"))
    return None
