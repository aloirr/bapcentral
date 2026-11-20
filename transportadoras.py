# -*- coding: utf-8 -*-
"""
TRANSPORTADORAS - o cadastro que o Analista Comercial mantem no BAP Analista
(painel "Lista de transportadoras").

Cada transportadora: NOME (obrigatorio), CONTATO, CNPJ, % DO FRETE e onde
ela atua (UFs e cidades das 6 UFs da BAP). Fica em transportadoras_config.json,
na pasta dos programas (caminho sempre relativo a esta pasta).

Regra de "atua":
    * cidade marcada ............ atende so as cidades marcadas daquela UF
    * UF marcada sem cidade ..... atende a UF inteira
    * nada marcado .............. atende todo lugar

A lista que a assistente ve na ENTREGA/FRETE vem daqui: primeiro as que
atuam na cidade do cliente; se nenhuma atuar, todas.
VLR FRETE = VLR NF x % do frete da transportadora escolhida (sem
transportadora, ou sem % cadastrado, vale o % padrao - 5%).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARQUIVO = "transportadoras_config.json"
UFS = ("AM", "RR", "PA", "AP", "MA", "MT")
PCT_PADRAO = 5.0


def _norm(txt) -> str:
    try:
        import geografia                                 # noqa: PLC0415
        return geografia.normalizar(txt or "")
    except Exception:                                    # noqa: BLE001
        return str(txt or "").strip().upper()


def caminho(raiz=None) -> Path:
    return Path(raiz or AQUI) / ARQUIVO


def _vazio() -> dict:
    return {"pct_padrao": PCT_PADRAO, "transportadoras": []}


def _semente(raiz) -> dict:
    """Primeira vez: comeca com as transportadoras que ja eram usadas (so o
    nome) para a lista da assistente nao nascer vazia."""
    dados = _vazio()
    try:
        import pos_venda                                 # noqa: PLC0415
        arq = Path(raiz) / "RELATORIOS" / "ACOMPANHAMENTO_POS_VENDA.xlsx"
        nomes = pos_venda.transportadoras_antigas(arq)
    except Exception:                                    # noqa: BLE001
        nomes = []
    for n in nomes:
        dados["transportadoras"].append(novo(n))
    return dados


def novo(nome="", contato="", cnpj="", pct=None, ufs=(), cidades=(),
         frete_minimo=None, minimo_ate=None, pct_cidades=None) -> dict:
    """(23/10) frete_minimo: o FRETE MINIMO em R$; minimo_ate: o VALOR DA
    NOTA (R$) ate o qual o minimo e cobrado (30/10: automatico).
    (30/10, Alexandre) pct_cidades: {"UF|CIDADE": %} - o % do frete daquela
    cidade nesta transportadora (vazio = o % da transportadora)."""
    return {"nome": str(nome or "").strip().upper(), "contato": contato or "",
            "cnpj": cnpj or "", "pct_frete": pct, "ufs": list(ufs),
            "cidades": list(cidades), "frete_minimo": frete_minimo,
            "minimo_ate": minimo_ate,
            "pct_cidades": {k: float(v) for k, v in
                            (pct_cidades or {}).items()
                            if v not in (None, "")}}


def carregar(raiz=None) -> dict:
    arq = caminho(raiz)
    if not arq.exists():
        dados = _semente(raiz or AQUI)
        try:
            salvar(dados, raiz)
        except OSError:
            pass
        return dados
    try:
        dados = json.loads(arq.read_text("utf-8"))
    except (OSError, ValueError):
        return _vazio()
    dados.setdefault("pct_padrao", PCT_PADRAO)
    dados.setdefault("transportadoras", [])
    for t in dados["transportadoras"]:
        for k, v in novo().items():
            t.setdefault(k, v)
    return dados


def salvar(dados: dict, raiz=None) -> Path:
    arq = caminho(raiz)
    nomes = [t["nome"] for t in dados.get("transportadoras", [])]
    if any(not n for n in nomes):
        raise ValueError("Toda transportadora precisa de NOME.")
    if len(set(nomes)) != len(nomes):
        raise ValueError("Há duas transportadoras com o mesmo nome.")
    dados["transportadoras"].sort(key=lambda t: t["nome"])
    tmp = arq.with_name(f"~{arq.name}")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, arq)
    return arq


def nomes(dados: dict) -> list:
    return [t["nome"] for t in dados.get("transportadoras", [])]


def atua(t: dict, uf: str, cidade: str) -> bool:
    ufs, cidades = t.get("ufs") or [], t.get("cidades") or []
    if not ufs and not cidades:
        return True
    uf, cid = str(uf or "").strip().upper(), _norm(cidade)
    da_uf = [c for c in cidades if c.split("|")[0] == uf]
    if da_uf:
        return f"{uf}|{cid}" in {f"{c.split('|')[0]}|{_norm(c.split('|')[-1])}"
                                  for c in da_uf}
    return uf in ufs


def opcoes_para(dados: dict, uf: str, cidade: str) -> list:
    """As que atuam na cidade; se nenhuma, todas."""
    todas = nomes(dados)
    aqui = [t["nome"] for t in dados.get("transportadoras", [])
            if atua(t, uf, cidade)]
    return aqui or todas


def pct_de(dados: dict, nome: str) -> float:
    for t in dados.get("transportadoras", []):
        if t["nome"] == str(nome or "").strip().upper():
            if t.get("pct_frete") not in (None, ""):
                return float(t["pct_frete"])
            break
    return float(dados.get("pct_padrao") or PCT_PADRAO)


def pct_da_cidade(t: dict, uf, cidade):
    """(30/10) o % do frete cadastrado para a cidade (None = nao tem)."""
    pc = (t or {}).get("pct_cidades") or {}
    if not pc or not cidade:
        return None
    alvo = f"{str(uf or '').strip().upper()}|{_norm(cidade)}"
    for k, v in pc.items():
        u_, c_ = (k.split("|") + [""])[:2]
        if f"{u_}|{_norm(c_)}" == alvo or (not uf and _norm(c_) ==
                                            _norm(cidade)):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def pct_para(dados: dict, nome: str, uf=None, cidade=None) -> float:
    """O % do frete da nota: o da cidade (se a transportadora tem), senao o
    da transportadora, senao o padrao."""
    p_ = pct_da_cidade(_transp(dados, nome), uf, cidade)
    return p_ if p_ is not None else pct_de(dados, nome)


def _transp(dados: dict, nome: str):
    return next((t for t in dados.get("transportadoras", [])
                 if t["nome"] == str(nome or "").strip().upper()), None)


def minimo_ate_auto(frete_minimo, pct) -> float | None:
    """(30/10, Alexandre) o "aciona o minimo" e AUTOMATICO: a nota em que o
    % da transportadora da exatamente o frete minimo (minimo / %). Abaixo
    dela o % fica menor que o minimo e o minimo e cobrado. Ex.: minimo
    R$ 150 a 4,5% -> NF ate R$ 3.333,33."""
    try:
        fmin, pct = float(frete_minimo), float(pct)
    except (TypeError, ValueError):
        return None
    if fmin <= 0 or pct <= 0:
        return None
    return round(fmin / (pct / 100.0), 2)


def frete_estimado(dados: dict, nome: str, vlr_nf, uf=None,
                   cidade=None) -> float:
    """(23/10, Alexandre) o FRETE ESTIMADO da nota: VLR NF x % da
    transportadora. (30/10, Alexandre) com FRETE MINIMO cadastrado, vale o
    minimo sempre que o % da nota der menos que ele (= o maior entre o % e
    o minimo; o "aciona o minimo" e so a conta minimo / %). Com a cidade
    da nota: o % da cidade quando a transportadora tem (30/10)."""
    vlr = float(vlr_nf or 0)
    est = vlr * pct_para(dados, nome, uf, cidade) / 100.0
    t = _transp(dados, nome) or {}
    fmin = t.get("frete_minimo")
    if fmin in (None, "") or not vlr:
        return est
    return max(est, float(fmin))


def texto_minimo(t: dict, pct_padrao=None) -> str:
    """O resumo do frete minimo para a lista ("R$ 150 (NF até R$ 3.333,33)");
    o "ate" e automatico: minimo / % (30/10)."""
    fmin = t.get("frete_minimo")
    if fmin in (None, ""):
        return "—"
    def r(v):
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(
            ".", ",").replace("X", ".").replace(",00", "")
    pct = t.get("pct_frete")
    if pct in (None, ""):
        pct = pct_padrao if pct_padrao not in (None, "") else PCT_PADRAO
    ate = minimo_ate_auto(fmin, pct)
    return r(fmin) + (f" (NF até {r(ate)})" if ate is not None else "")


def cidades_da_uf(uf: str) -> list:
    """Os municipios da UF (tabela do IBGE que o Planner ja usa)."""
    try:
        import geografia                                 # noqa: PLC0415
        return sorted(c for u, c in geografia.CIDADES if u == uf)
    except Exception:                                    # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# (10/10) SLA DE ENTREGA - BAP Analista › Entrega › Parametros
#   por FILIAL: SLA ENTREGA LOCAL (cidade onde a BAP entrega sem frete) e
#               SLA ENTREGA FRETE (o resto), em dias uteis;
#   por CIDADE (opcional): um SLA so para ela.
# Vale a CIDADE cadastrada; sem ela, o da FILIAL onde ela esta (local ou
# frete). Nada cadastrado: a regra antiga (3 dias uteis; interior 5).
# Guardado no mesmo transportadoras_config.json, na chave "sla".
# ---------------------------------------------------------------------------
SLA_LOCAL_PADRAO, SLA_FRETE_PADRAO = 3, 5
FILIAL_DA_UF = {"AM": "MANAUS", "RR": "BOA VISTA", "PA": "BELÉM",
                "AP": "MACAPÁ", "MA": "SÃO LUIS", "MT": "MATOGROSSO"}
FILIAIS = tuple(FILIAL_DA_UF.values())


def sla_vazio() -> dict:
    return {"filiais": {}, "cidades": {}}


def sla_de_dados(dados: dict) -> dict:
    s = dict(sla_vazio(), **(dados.get("sla") or {}))
    s["filiais"] = {_norm(k): v for k, v in (s.get("filiais") or {}).items()}
    s["cidades"] = {k: v for k, v in (s.get("cidades") or {}).items()}
    return s


def ler_sla(raiz=None) -> dict:
    """So LE (nao cria o arquivo): o que esta cadastrado, ou vazio."""
    arq = caminho(raiz)
    try:
        return sla_de_dados(json.loads(arq.read_text("utf-8")))
    except (OSError, ValueError):
        return sla_vazio()


def salvar_sla(sla: dict, raiz=None) -> Path:
    dados = carregar(raiz)
    dados["sla"] = {"filiais": dict(sla.get("filiais") or {}),
                    "cidades": dict(sla.get("cidades") or {})}
    return salvar(dados, raiz)


def e_frete(cidade) -> bool:
    try:
        import bap_dados as bd                           # noqa: PLC0415
        return bd.e_frete(cidade)
    except Exception:                                    # noqa: BLE001
        return _norm(cidade) not in {"MANAUS", "BOA VISTA", "BELEM",
                                     "SANTAREM", "SAO LUIS", "CUIABA",
                                     "VARZEA GRANDE"}


def chave_cidade(uf, cidade) -> str:
    return f"{str(uf or '').strip().upper()}|{_norm(cidade)}"


def sla_de(sla: dict, uf, cidade, filial=None, frete=None):
    """(dias uteis, origem) do SLA de entrega da cidade: "cidade", "filial"
    ou (None, "padrao") quando nada foi cadastrado para ela."""
    n = (sla.get("cidades") or {}).get(chave_cidade(uf, cidade))
    if n not in (None, ""):
        return int(n), "cidade"
    fil = _norm(filial) or _norm(FILIAL_DA_UF.get(str(uf or "").upper(), ""))
    f = (sla.get("filiais") or {}).get(fil) or {}
    frete = e_frete(cidade) if frete is None else frete
    v = f.get("frete" if frete else "local")
    if v not in (None, ""):
        return int(v), "filial"
    return None, "padrao"


def sla_ou_padrao(sla: dict, uf, cidade, filial=None, frete=None) -> int:
    n, _o = sla_de(sla, uf, cidade, filial, frete)
    if n is not None:
        return n
    frete = e_frete(cidade) if frete is None else frete
    return SLA_FRETE_PADRAO if frete else SLA_LOCAL_PADRAO


def texto_sla(sla: dict) -> str:
    """O resumo para o subtitulo dos farois."""
    if not sla.get("filiais") and not sla.get("cidades"):
        return (f"SLA de entrega: {SLA_LOCAL_PADRAO} dias úteis · frete "
                f"{SLA_FRETE_PADRAO}")
    n_c = len(sla.get("cidades") or {})
    return ("SLA de entrega por filial" + (f" e {n_c} cidade(s)" if n_c
                                           else "")
            + " (BAP Analista › Entrega)")
