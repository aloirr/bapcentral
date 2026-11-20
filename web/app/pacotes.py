"""Pacote do robô (parte dado do contrato, §10): validar, guardar, ler."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .arquivos import gravar_json

ACEITOS = ("vc_painel_diretor", "pl_inadimplencia")
GUARDAR = 15


def nome_arquivo(gerado_em: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", gerado_em)[:32]


def _int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


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
        kp = r.get("kpis", [])
        if not isinstance(kp, list) or not all(isinstance(x, dict) and "rotulo" in x for x in kp):
            erros.append(f"{k}: kpis inválidos")
        tb = r.get("tabelas", [])
        if not isinstance(tb, list) or not all(
                isinstance(t, dict) and isinstance(t.get("colunas"), list)
                and isinstance(t.get("linhas"), list)
                and all(isinstance(x, dict) and "nome" in x for x in t["colunas"])
                and all(isinstance(l, list) for l in t["linhas"]) for t in tb):
            erros.append(f"{k}: tabelas inválidas")
        ps = r.get("paineis", [])
        if not isinstance(ps, list) or not all(
                isinstance(p, dict) and isinstance(p.get("titulo"), str)
                and isinstance(p.get("kpis_export", []), list) for p in ps):
            erros.append(f"{k}: paineis inválidos")
    return erros[:10]


def _sem_internas(o):
    """Chaves com _ são internas do contrato (§10.2): nunca guardadas."""
    if isinstance(o, dict):
        return {k: _sem_internas(v) for k, v in o.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(o, list):
        return [_sem_internas(v) for v in o]
    return o


def gravar(dados: Path, corpo: dict, recebido_em: str) -> Path:
    pasta = dados / "pacotes"
    corpo = _sem_internas(corpo)
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
