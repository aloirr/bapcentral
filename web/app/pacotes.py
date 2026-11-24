"""Pacote do robô (parte dado do contrato, §10): validar, guardar, ler."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import render
from .arquivos import gravar_json

ACEITOS = ("vc_painel",)
ABAS = render.CHAVES_ABAS                      # fonte única
MANAUS = ZoneInfo("America/Manaus")
GUARDAR = 15


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
    """Chaves com _ são internas do contrato (§10.2): nunca guardadas."""
    if isinstance(o, dict):
        return {k: _sem_internas(v) for k, v in o.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(o, list):
        return [_sem_internas(v) for v in o]
    return o


def _enxuto(corpo: dict) -> dict:
    """Guarda só o que a tela lê: por aba, os cartões da visão, `sub`, `como_ler`, avisos."""
    for rel in corpo["relatorios"].values():
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

    def get(self) -> dict | None:
        arqs = listar(self.dados)
        if not arqs:
            return None
        a = arqs[-1]
        chave = (a.name, a.stat().st_mtime_ns)
        if chave != self._chave:
            self._val = json.loads(a.read_text(encoding="utf-8"))
            self._chave = chave
        return self._val
