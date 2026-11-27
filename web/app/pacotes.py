"""Pacote do robô (parte dado do contrato, §10): validar, guardar, ler."""
from __future__ import annotations

import base64
import gzip
import os
import shutil
import time
import zlib
from collections import OrderedDict
import hashlib
import json
import logging
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
# T-0021: CSVs de importação no Protheus (reversa de loja / separação de CD), mandados pelo robô
RE_CSV = re.compile(r"^\d{6}_\d{1,4}_[A-Z0-9]{1,30}_(BAPReversaLoja|BAPSeparacaoCD)\.csv$")
MAX_CSVS, MAX_CSV_BYTES, MAX_CSVS_TOTAL = 60, 200_000, 1_500_000
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



def _csvs_erro(rid: str, c) -> str | None:
    """T-0021: lista de {nome, conteudo}; nome no padrão do robô, texto UTF-8, tetos de tamanho. Só em Pedidos."""
    if c is None:
        return None
    if rid != "pv_pedidos":
        return f"{rid}: csvs_protheus só no Farol de Pedidos"
    if not isinstance(c, list) or len(c) > MAX_CSVS:
        return f"{rid}: csvs_protheus inválido"
    total, nomes = 0, set()
    for x in c:
        if not (isinstance(x, dict) and set(x) == {"nome", "conteudo"} and isinstance(x["nome"], str)
                and isinstance(x["conteudo"], str) and RE_CSV.match(x["nome"]) and x["nome"] not in nomes):
            return f"{rid}: csvs_protheus com item inválido"
        n = len(x["conteudo"].encode("utf-8"))
        total += n
        if n > MAX_CSV_BYTES or total > MAX_CSVS_TOTAL or "\x00" in x["conteudo"]:
            return f"{rid}: csvs_protheus grande demais"
        nomes.add(x["nome"])
    return None


def _painel_erro(rid: str, painel) -> str | None:
    """Blocos do painel (farol, aba do Painel Executivo, recorte por estado): só formato."""
    bl = painel.get("blocos") if isinstance(painel, dict) else None
    if not (isinstance(bl, list) and len(bl) <= 30 and all(isinstance(b, dict) and isinstance(b.get("tipo"), str) for b in bl)):
        return f"{rid}: painel.blocos inválido"
    for b in bl:
        if b["tipo"] == "tabela" and not _tabela_ok(b):
            return f"{rid}: bloco tabela inválido ou com coluna de cliente/CNPJ/telefone"
        if b["tipo"] == "placar" and not (isinstance(b.get("cartoes"), list) and len(b["cartoes"]) <= 30 and all(
                isinstance(c, dict) and isinstance(c.get("farol"), str) for c in b["cartoes"])):
            return f"{rid}: bloco placar inválido"
    return None


def _corpo_erro(rid: str, c, com_tabelas: bool = False) -> str | None:
    """T-0022: `kpis` + `painel` (+ `insights_painel`, + `tabelas` no Farol de Metas) de uma aba do Painel Executivo
    ou de um recorte por estado. Chave de edição ou interna nunca entra."""
    if not isinstance(c, dict):
        return f"{rid}: recorte inválido"
    extras = {"kpis", "painel", "insights_painel", "titulo", "so_bap", "avisos", "recortes"} | ({"tabelas"} if com_tabelas else set())
    if set(c) - extras:
        return f"{rid}: chave não aceita: {sorted(set(c) - extras)[0][:20]}"
    achou = _chave_proibida({k: v for k, v in c.items() if k not in ("recortes", "tabelas")})
    if achou:
        return f"{rid}: chave não aceita na web: {achou}"
    if not _kpis_ok(c.get("kpis")):
        return f"{rid}: kpis inválidos"
    erro = _painel_erro(rid, c.get("painel"))
    if erro:
        return erro
    ins = c.get("insights_painel")
    if ins is not None and not (isinstance(ins, list) and len(ins) <= 40 and all(
            isinstance(x, list) and len(x) >= 2 and isinstance(x[1], str) for x in ins)):
        return f"{rid}: insights_painel inválido"
    return None


def _recortes_meta_erro(rid: str, rec) -> str | None:
    """Recortes por estado do Farol de Metas: cada estado leva cartões, painel e as abas de tabela dele."""
    if not isinstance(rec, dict) or len(rec) > MAX_RECORTES:
        return f"{rid}: recortes inválidos"
    for uf, v in rec.items():
        if not RE_UF.match(str(uf)):
            return f"{rid}: recorte {str(uf)[:4]} inválido"
        erro = _corpo_erro(f"{rid}.{uf}", v, com_tabelas=True)
        if erro:
            return erro
        if "tabelas" in v:
            er = tabelas.validar(rid, {"tabelas": v["tabelas"]})
            if er:
                return f"{rid}.{uf}: {er[0]}"
    return None


def _paineis_erros(k: str, ps) -> list[str]:
    """T-0022: `paineis` do vc_painel = as 9 abas de painel, na forma do farol."""
    if not isinstance(ps, dict):
        return [f"{k}: paineis precisa ser objeto"]
    validos = dict(render.PAINEIS)
    for chave, a in ps.items():
        if chave not in validos:
            return [f"{k}.paineis: aba não aceita: {str(chave)[:20]}"]
        if not (isinstance(a, dict) and isinstance(a.get("titulo"), str)):
            return [f"{k}.paineis.{chave}: titulo ausente"]
        erro = _corpo_erro(f"{k}.paineis.{chave}", a)
        if erro:
            return [erro]
        if a.get("so_bap") is not None and not isinstance(a["so_bap"], bool):
            return [f"{k}.paineis.{chave}: so_bap inválido"]
        av = a.get("avisos")
        if av is not None and not (isinstance(av, list) and all(isinstance(x, str) for x in av)):
            return [f"{k}.paineis.{chave}: avisos inválidos"]
        rec = a.get("recortes")
        if rec is not None:
            if not isinstance(rec, dict) or len(rec) > MAX_RECORTES:
                return [f"{k}.paineis.{chave}: recortes inválidos"]
            for uf, v in rec.items():
                erro = _corpo_erro(f"{k}.paineis.{chave}.{str(uf)[:4]}", v)
                if not RE_UF.match(str(uf)) or erro:
                    return [erro or f"{k}.paineis.{chave}: recorte {str(uf)[:4]} inválido"]
    return []


def validar_farol(rid: str, r) -> list[str]:
    """Forma "farol" (T-0017): só formato; kpis e blocos vêm prontos do PC (contrato §8)."""
    if not isinstance(r, dict) or r.get("forma") != "farol":
        return [f"{rid}: forma precisa ser farol"]
    # §10.6 (tabelas e cobranca do pl_inadimplencia) e §10.7 (tabelas dos outros três faróis)
    erros_t = tabelas.validar(rid, r) if rid in tabelas.RIDS else cobranca.validar(rid, r)
    if erros_t:
        return erros_t
    achou = _chave_proibida({k: v for k, v in r.items()
                             if k not in ("tabelas", "cobranca") and not (rid == "vc_meta" and k == "recortes")})
    if achou:
        return [f"{rid}: chave não aceita na web: {achou}"]
    if not isinstance(r.get("titulo"), str):
        return [f"{rid}: titulo ausente"]
    if not _kpis_ok(r.get("kpis")):
        return [f"{rid}: kpis inválidos"]
    erro = _painel_erro(rid, r.get("painel"))
    if erro:
        return [erro]
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
    e_par = _parciais_erro(rid, r.get("parciais")) or _csvs_erro(rid, r.get("csvs_protheus"))
    if e_par:
        return [e_par]
    rec = r.get("recortes")
    if rec is not None and rid == "vc_meta":
        erro = _recortes_meta_erro(rid, rec)
        return [erro] if erro else []
    if rec is not None:
        if not isinstance(rec, dict) or len(rec) > MAX_RECORTES:
            return [f"{rid}: recortes inválidos"]
        for uf, v in rec.items():
            if not RE_UF.match(str(uf)) or not isinstance(v, dict) or not _kpis_ok(v.get("kpis")):
                return [f"{rid}: recorte {str(uf)[:4]} inválido"]
    return []


def validar_topo(c) -> list[str]:
    """T-0035: o topo do pacote (versao_contrato, gerado_em, ano, mes); vale nos formatos 1 e 2."""
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
    return erros


def validar_relatorio(k, r) -> list[str]:
    """T-0035: a regra de um relatório do pacote (o corpo do laço do formato 1), farol a farol."""
    if k not in ACEITOS:
        return [f"relatório não aceito: {str(k)[:40]}"]
    if k in FAROIS:
        return validar_farol(k, r)
    erros: list[str] = []
    if not isinstance(r, dict) or not isinstance(r.get("titulo"), str):
        return [f"{k}: titulo ausente"]
    abas = r.get("abas")
    if not isinstance(abas, dict):
        return [f"{k}: abas ausente"]
    for chave, visao in ABAS:
        a = abas.get(chave)
        if a is None and chave in render.ABAS_OPCIONAIS:
            continue                       # T-0022: robô antigo, sem a aba por dia útil
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
    if r.get("paineis") is not None:
        erros += _paineis_erros(k, r["paineis"])
    return erros


def validar(c) -> list[str]:
    """Formato 1: o pacote inteiro = o topo mais cada relatório (mesmo corte de 10 erros)."""
    if not isinstance(c, dict):
        return ["o corpo precisa ser um objeto JSON"]
    erros = validar_topo(c)
    rels = c.get("relatorios")
    if not isinstance(rels, dict) or not rels:
        return erros + ["relatorios ausente"]
    for k, r in rels.items():
        erros += validar_relatorio(k, r)
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
            a = rel["abas"].get(chave)
            if a is None:
                continue
            d = a["painel"]["blocos"][0]["dados"]
            a["painel"]["blocos"][0]["dados"] = {
                visao: d[visao], "sub": {visao: (d.get("sub") or {}).get(visao, "")},
                "como_ler": d.get("como_ler", ""), "avisos": d.get("avisos", []),
                "ano": d.get("ano"), "mes": d.get("mes")}
            a.pop("diretor", None)
    return corpo


# ---------------------------------------------------------------------------------------------
# T-0035 (ADR 0003, contrato §10.8): um arquivo por farol e um índice; a web lê do disco sob demanda
# ---------------------------------------------------------------------------------------------
RE_LOTE = re.compile(r"^\d{8}T\d{6}$")
RE_SHA = re.compile(r"^[0-9a-f]{64}$")
MB = 1024 * 1024
FAROL_GZ_MAX = 24 * MB            # corpo comprimido
FAROL_CORPO_MAX = 24 * MB         # corpo descomprimido (farol + anexos)
FAROL_JSON_MAX = 10 * MB          # o JSON do farol sem os anexos (config: BAP_WEB_FAROL_MAX_MB)
LOTE_FAROIS_MAX = 60
CACHE_FAROIS_MB = 96              # orçamento estimado do LRU (config: BAP_WEB_CACHE_MB)
CUSTO_POR_BYTE = 6                # custo estimado do farol na memória = bytes do JSON × 6 (ADR 0003, §4.5)
RECEBENDO_MAX = 3                 # lotes ao mesmo tempo em _recebendo
RECEBENDO_HORAS = 2
HERDA_HORAS = 26                  # §4.4: o farol herdado só vale até 26 h
FORMATOS = [1, 2]
log = logging.getLogger("bap_web")


class ErroPacote(Exception):
    """Recusa com o status e o corpo da resposta (sem dado pessoal)."""

    def __init__(self, status: int, corpo: dict):
        super().__init__(corpo.get("erro", ""))
        self.status, self.corpo = status, corpo


def json_compacto(o) -> bytes:
    return json.dumps(o, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _pasta(dados: Path) -> Path:
    return dados / "pacotes"


def _recebendo(dados: Path) -> Path:
    return _pasta(dados) / "_recebendo"


def lotes(dados: Path) -> list[str]:
    """Nomes dos lotes fechados (pasta com indice.json), do mais velho ao mais novo."""
    p = _pasta(dados)
    if not p.is_dir():
        return []
    return sorted(d.name for d in p.iterdir() if RE_LOTE.fullmatch(d.name) and (d / "indice.json").is_file())


def listar(dados: Path) -> list[Path]:
    """Pacotes do formato 1 ainda no disco (herança da web antiga); só saem pela retenção."""
    p = _pasta(dados)
    return sorted(p.glob("*.json")) if p.is_dir() else []


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
            a = rel["abas"].get(chave)
            if a is None:
                continue
            d = a["painel"]["blocos"][0]["dados"]
            a["painel"]["blocos"][0]["dados"] = {
                visao: d[visao], "sub": {visao: (d.get("sub") or {}).get(visao, "")},
                "como_ler": d.get("como_ler", ""), "avisos": d.get("avisos", []),
                "ano": d.get("ano"), "mes": d.get("mes")}
            a.pop("diretor", None)
    return corpo


def _gravar_bytes(caminho: Path, dados: bytes) -> None:
    """Gravação atômica de bytes (tmp + fsync + os.replace)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(f".tmp-{os.getpid()}-{caminho.name}")
    try:
        with open(tmp, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, caminho)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def descomprimir(bruto: bytes, maximo: int) -> bytes:
    """gzip com teto de saída (defesa contra bomba): passou do `maximo` = 413; gzip quebrado = 422."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    saida, resto, total = [], bruto, 0
    try:
        while resto:
            parte = d.decompress(resto, maximo + 1 - total)
            total += len(parte)
            if total > maximo:
                raise ErroPacote(413, {"erro": "farol grande demais"})
            saida.append(parte)
            resto = d.unconsumed_tail
        parte = d.flush()
    except zlib.error as e:
        raise ErroPacote(422, {"erro": "gzip inválido"}) from e
    if total + len(parte) > maximo:
        raise ErroPacote(413, {"erro": "farol grande demais"})
    if not d.eof:
        raise ErroPacote(422, {"erro": "gzip inválido"})
    saida.append(parte)
    return b"".join(saida)


def guardar_farol(dados: Path, lote: str, rid: str, farol: dict, sha: str,
                  json_max: int = FAROL_JSON_MAX) -> dict:
    """Guarda um farol já validado em `_recebendo/<lote>/`: o farol sem anexos em `<rid>.json.gz`,
    as parciais em PNG e os CSVs em arquivos próprios. Devolve a entrada do índice (§10.8.2).
    Sobrescreve o mesmo `rid` do mesmo lote (nova tentativa do robô)."""
    pasta = _recebendo(dados) / lote
    pars = farol.pop("parciais", None)
    csvs = farol.pop("csvs_protheus", None)
    corpo = json_compacto(farol)
    if len(corpo) > json_max:
        raise ErroPacote(413, {"erro": "farol grande demais"})
    gz = gzip.compress(corpo, 6, mtime=0)
    _gravar_bytes(pasta / f"{rid}.json.gz", gz)
    anexos: dict = {}
    for q, v in (pars or {}).items():
        nome = f"{rid}.parcial-{q}.png"
        _gravar_bytes(pasta / nome, base64.b64decode(v["png"], validate=True))
        anexos.setdefault("parciais", {})[q] = nome
        anexos.setdefault("rotulos", {})[q] = v["rotulo"]
    if csvs is not None:
        nome = f"{rid}.csvs.json.gz"
        _gravar_bytes(pasta / nome, gzip.compress(json_compacto(csvs), 6, mtime=0))
        anexos["csvs"] = nome
    ent = {"arquivo": f"{rid}.json.gz", "sha256": sha, "bytes_gz": len(gz), "bytes_json": len(corpo),
           "titulo": farol.get("titulo"), "baixado_em": farol.get("baixado_em"), "herdado_de": None}
    if anexos:
        ent["anexos"] = anexos
    _gravar_bytes(pasta / f"{rid}.meta.json", json_compacto(ent))
    _limpar_recebendo(dados)
    return ent


def preparar_farol(rid: str, farol) -> dict:
    """Passos comuns ao formato 1 e ao 2 depois da validação: tira a aba com documento e as chaves
    internas, e deixa o Painel enxuto. Devolve o farol pronto para `guardar_farol`."""
    corpo = {"relatorios": {rid: farol}}
    fora = tabelas.tirar_abas_com_documento(corpo)
    if fora:
        log.warning("abas fora do pacote por CPF/CNPJ em célula: %d", len(fora))
    return _enxuto(_sem_internas(corpo))["relatorios"][rid]


def receber_farol(dados: Path, lote: str, rid: str, bruto: bytes, sha: str,
                  json_max: int = FAROL_JSON_MAX) -> dict:
    """§10.8.3: corpo já descomprimido (`bruto`) e o sha informado. Levanta ErroPacote com o status certo."""
    if hashlib.sha256(bruto).hexdigest() != sha:
        raise ErroPacote(422, {"erro": "sha256"})
    try:
        farol = json.loads(bruto.decode("utf-8"))
    except (ValueError, RecursionError) as e:
        raise ErroPacote(422, {"erro": "JSON inválido"}) from e
    erros = validar_relatorio(rid, farol)
    if erros:
        raise ErroPacote(422, {"erro": "esquema inválido", "detalhes": erros[:10]})
    return guardar_farol(dados, lote, rid, preparar_farol(rid, farol), sha, json_max)


def _limpar_recebendo(dados: Path) -> None:
    """Lote em recebimento com mais de 2 h sai; no máximo 3 ao mesmo tempo (o mais velho sai)."""
    p = _recebendo(dados)
    if not p.is_dir():
        return
    pastas = sorted((d for d in p.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime)
    agora = time.time()
    vivas = []
    for d in pastas:
        if agora - d.stat().st_mtime > RECEBENDO_HORAS * 3600:
            shutil.rmtree(d, ignore_errors=True)
        else:
            vivas.append(d)
    for d in vivas[:-RECEBENDO_MAX]:
        shutil.rmtree(d, ignore_errors=True)
    try:
        p.rmdir()                                  # vazia: some (nada além de lotes em pacotes/)
    except OSError:
        pass


def retencao(dados: Path) -> None:
    """Os `GUARDAR` lotes mais novos (RN-POS-003), contando junto os pacotes do formato 1, pelo nome."""
    p = _pasta(dados)
    nomes = set(lotes(dados)) | {a.stem for a in listar(dados)}
    for velho in sorted(nomes)[:-GUARDAR]:
        shutil.rmtree(p / velho, ignore_errors=True)
        (p / f"{velho}.json").unlink(missing_ok=True)


def _ler_indice(dados: Path, lote: str) -> dict | None:
    try:
        return json.loads((_pasta(dados) / lote / "indice.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _como_manaus(iso: str) -> datetime:
    d = datetime.fromisoformat(iso)
    return d.replace(tzinfo=MANAUS) if d.tzinfo is None else d.astimezone(MANAUS)


def _herdar(dados: Path, de: str, ent: dict, destino: Path) -> dict:
    """Copia o farol (e os anexos) do lote vigente para a pasta nova: hard link, com cópia de reserva."""
    origem = _pasta(dados) / de
    an = ent.get("anexos") or {}
    arqs = [ent["arquivo"]] + list((an.get("parciais") or {}).values()) + ([an["csvs"]] if an.get("csvs") else [])
    destino.mkdir(parents=True, exist_ok=True)
    for a in arqs:
        try:
            os.link(origem / a, destino / a)
        except OSError:
            shutil.copy2(origem / a, destino / a)
    novo = dict(ent)
    novo["herdado_de"] = ent.get("herdado_de") or de
    return novo


def fechar(dados: Path, lote: str, topo, farois, manter, recebido_em: str,
           origem: str = "por_farol", agora: datetime | None = None) -> dict:
    """§10.8.4: confere o topo e os faróis, aplica o `manter`, grava o índice e move a pasta do lote.
    Levanta ErroPacote (400, 409, 422). `farois` = {rid: sha256}; `manter` = [rid] ou None."""
    if not RE_LOTE.fullmatch(lote or ""):
        raise ErroPacote(400, {"erro": "lote inválido"})
    erros = validar_topo(topo)
    if not erros and nome_arquivo(topo["gerado_em"]) != lote:
        erros = ["gerado_em não bate com o lote"]
    if erros:
        raise ErroPacote(422, {"erro": "esquema inválido", "detalhes": erros[:10]})
    if (_pasta(dados) / lote / "indice.json").is_file():          # fechar repetido = mesma resposta
        fs = (_ler_indice(dados, lote) or {}).get("farois") or {}
        return {"ok": True, "lote": lote, "farois": len(fs),
                "herdados": sorted(r for r, e in fs.items() if e.get("herdado_de")),
                "vigente": (lotes(dados) or [""])[-1] == lote}
    if (not isinstance(farois, dict) or not (1 <= len(farois) <= LOTE_FAROIS_MAX)
            or not (manter is None or (isinstance(manter, list) and all(isinstance(m, str) for m in manter)))
            or not all(isinstance(v, str) and RE_SHA.fullmatch(v) for v in farois.values())
            or any(r not in ACEITOS for r in list(farois) + list(manter or []))):
        raise ErroPacote(400, {"erro": "corpo fora do formato"})
    pasta = _recebendo(dados) / lote
    metas, faltam = {}, []
    for rid, sha in farois.items():
        try:
            m = json.loads((pasta / f"{rid}.meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            m = None
        if not m or m.get("sha256") != sha:
            faltam.append(rid)
        else:
            metas[rid] = m
    if faltam:
        raise ErroPacote(409, {"erro": "faltam", "farois": sorted(faltam)})
    agora = agora or datetime.now(MANAUS)
    herdados: list[str] = []
    vig = (lotes(dados) or [None])[-1]
    ind_vig = _ler_indice(dados, vig) if vig else None
    for rid in manter or []:
        e = ((ind_vig or {}).get("farois") or {}).get(rid)
        if rid in metas or not e:
            continue
        try:
            idade = agora - _como_manaus(e["gerado_em"])
        except (KeyError, ValueError):
            continue
        if idade.total_seconds() > HERDA_HORAS * 3600:
            continue                                              # velho demais: o farol fica fora
        metas[rid] = _herdar(dados, vig, e, pasta)
        herdados.append(rid)
    pasta.mkdir(parents=True, exist_ok=True)
    for f in list(pasta.iterdir()):                               # só o que o índice lista fica
        if f.name.endswith(".meta.json") or f.name.split(".")[0] not in metas:
            f.unlink(missing_ok=True)
    out = {}
    for rid, m in metas.items():
        out[rid] = m if m.get("herdado_de") else {**m, "gerado_em": topo["gerado_em"], "recebido_em": recebido_em}
    gravar_json(pasta / "indice.json", {
        "formato": 2, "lote": lote, "origem": origem, "versao_contrato": topo["versao_contrato"],
        "gerado_em": topo["gerado_em"], "ano": topo["ano"], "mes": topo["mes"],
        "recebido_em": recebido_em, "farois": out})
    try:
        os.replace(pasta, _pasta(dados) / lote)
    except OSError:                                                # destino já existe (corrida): vale o primeiro
        shutil.rmtree(pasta, ignore_errors=True)
    retencao(dados)
    _limpar_recebendo(dados)
    return {"ok": True, "lote": lote, "farois": len(out), "herdados": sorted(herdados),
            "vigente": (lotes(dados) or [""])[-1] == lote}


def gravar(dados: Path, corpo: dict, recebido_em: str, origem: str = "inteiro") -> Path:
    """Formato 1 (ou conversão do disco antigo): divide o pacote inteiro num lote, com as mesmas funções do
    envio por farol. O `corpo` já foi validado. Devolve a pasta do lote."""
    lote = nome_arquivo(corpo["gerado_em"])
    topo = {k: corpo[k] for k in ("versao_contrato", "gerado_em", "ano", "mes")}
    shutil.rmtree(_recebendo(dados) / lote, ignore_errors=True)
    shutil.rmtree(_pasta(dados) / lote, ignore_errors=True)       # o formato 1 repetido substitui o lote
    farois = {}
    for rid, farol in corpo["relatorios"].items():
        farol = preparar_farol(rid, farol)
        sha = hashlib.sha256(json_compacto(farol)).hexdigest()
        guardar_farol(dados, lote, rid, farol, sha, json_max=1 << 60)
        farois[rid] = sha
    fechar(dados, lote, topo, farois, None, recebido_em, origem=origem)
    return _pasta(dados) / lote


def converter_legado(dados: Path) -> bool:
    """Partida sobre um disco do formato 1: sem lote e com `pacotes/*.json`, converte só o mais novo."""
    arqs = listar(dados)
    if lotes(dados) or not arqs:
        return False
    corpo = json.loads(arqs[-1].read_text(encoding="utf-8"))
    gravar(dados, corpo, corpo.get("recebido_em") or datetime.now(MANAUS).isoformat(timespec="seconds"),
           origem="convertido")
    return True


class Indice:
    """O índice do lote vigente na memória (alguns KB) e o farol lido do disco sob demanda, com cache LRU
    de orçamento estimado (`bytes_json × 6`). A chave do cache é (lote, rid, sha256)."""

    def __init__(self, dados: Path, cache_mb: float = CACHE_FAROIS_MB):
        self.dados = dados
        self.orcamento = int(cache_mb * MB)
        self._chave = None
        self._ind: dict | None = None
        self._cache: OrderedDict = OrderedDict()      # (lote, rid, sha) -> (farol, custo)
        self._custo = 0

    # --- índice
    def indice(self) -> dict | None:
        ls = lotes(self.dados)
        if not ls:
            self._chave, self._ind = None, None
            return None
        arq = _pasta(self.dados) / ls[-1] / "indice.json"
        chave = (ls[-1], arq.stat().st_mtime_ns)
        if chave != self._chave:
            self._ind = _ler_indice(self.dados, ls[-1])
            self._chave = chave
        return self._ind

    def entrada(self, rid: str) -> dict | None:
        return ((self.indice() or {}).get("farois") or {}).get(rid)

    def sha(self, rid: str) -> str:
        return (self.entrada(rid) or {}).get("sha256", "")

    def recebido_em(self, rid: str) -> str | None:
        return (self.entrada(rid) or {}).get("recebido_em")

    def gerado_em(self, rid: str) -> str | None:
        return (self.entrada(rid) or {}).get("gerado_em")

    # --- farol sob demanda
    def farol(self, rid: str) -> dict | None:
        ind, e = self.indice(), self.entrada(rid)
        if not ind or not e:
            return None
        chave = (ind["lote"], rid, e["sha256"])
        if chave in self._cache:
            self._cache.move_to_end(chave)
            return self._cache[chave][0]
        try:
            with gzip.open(_pasta(self.dados) / ind["lote"] / e["arquivo"], "rb") as f:
                farol = json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError):
            return None
        custo = int(e.get("bytes_json") or 0) * CUSTO_POR_BYTE
        if custo <= self.orcamento:                   # maior que o orçamento sozinho: lido e não guardado
            for k in [k for k in self._cache if k[1] == rid]:       # a versão velha do mesmo farol sai
                self._custo -= self._cache.pop(k)[1]
            self._cache[chave] = (farol, custo)
            self._custo += custo
            while self._custo > self.orcamento and len(self._cache) > 1:
                self._custo -= self._cache.popitem(last=False)[1][1]
        return farol

    def esvaziar(self) -> None:
        """Antes do formato 1 (corpo grande): baixa o pico de memória."""
        self._cache.clear()
        self._custo = 0

    def cache(self) -> tuple[float, int]:
        return self._custo / MB, len(self._cache)

    # --- anexos (servidos do disco)
    def anexo(self, rid: str, nome: str) -> Path | None:
        ind, e = self.indice(), self.entrada(rid)
        if not ind or not e or not nome:
            return None
        an = e.get("anexos") or {}
        ok = nome in (an.get("parciais") or {}).values() or nome == an.get("csvs")
        p = _pasta(self.dados) / ind["lote"] / nome
        return p if ok and p.is_file() else None

    def parciais(self, rid: str) -> dict:
        """{quando: {"rotulo", "arquivo"(Path)}} das parciais do farol."""
        an = (self.entrada(rid) or {}).get("anexos") or {}
        out = {}
        for q, nome in (an.get("parciais") or {}).items():
            p = self.anexo(rid, nome)
            if p:
                out[q] = {"rotulo": (an.get("rotulos") or {}).get(q, ""), "arquivo": p}
        return out

    def csvs(self, rid: str) -> list[dict]:
        """[{nome, conteudo}] dos CSVs do Protheus do farol (lidos do disco; até 1,5 MB)."""
        p = self.anexo(rid, ((self.entrada(rid) or {}).get("anexos") or {}).get("csvs") or "")
        if not p:
            return []
        try:
            with gzip.open(p, "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError):
            return []


def por_sha(dados: Path, rid: str, sha: str) -> dict | None:
    """O farol `rid` com esse sha256 entre os lotes guardados (só ele é aberto); None se já saiu (§10.6.4)."""
    if not RE_SHA.fullmatch(sha or ""):
        return None
    for lote in reversed(lotes(dados)):
        e = ((_ler_indice(dados, lote) or {}).get("farois") or {}).get(rid)
        if e and e.get("sha256") == sha:
            try:
                with gzip.open(_pasta(dados) / lote / e["arquivo"], "rb") as f:
                    return json.loads(f.read().decode("utf-8"))
            except (OSError, ValueError):
                return None
    return None


def memoria(indice: Indice) -> dict:
    """§4.6: o que o processo usa, da biblioteca padrão; None onde o sistema não informa."""
    rss = pico = limite = None
    try:
        for linha in Path("/proc/self/status").read_text().splitlines():
            if linha.startswith("VmRSS:"):
                rss = round(int(linha.split()[1]) / 1024, 1)
            elif linha.startswith("VmHWM:"):           # pico do próprio processo (o ru_maxrss herda o do lançador)
                pico = round(int(linha.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    if pico is None:                                   # fora do Linux: reserva
        try:
            import resource
            pico = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except (ImportError, OSError, ValueError):
            pass
    try:
        txt = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        limite = round(int(txt) / MB, 1) if txt.isdigit() else None
    except (OSError, ValueError):
        pass
    cmb, cn = indice.cache()
    return {"rss_mb": rss, "pico_mb": pico, "limite_mb": limite, "cache_mb": round(cmb, 1), "cache_farois": cn}
