# -*- coding: utf-8 -*-
"""
CONSULTA CNAE PELO CNPJ - clientes BAP
--------------------------------------
Le a BASE_CLIENTE_NOVA.xlsx (ou BASE_CLIENTE.xlsx) na MESMA pasta deste script, pega o CNPJ de cada cliente/loja
e consulta a Receita Federal via APIs publicas gratuitas:
    1) BrasilAPI        https://brasilapi.com.br/api/cnpj/v1/{cnpj}
    2) Minha Receita    https://minhareceita.org/{cnpj}
    3) CNPJ.ws publica  https://publica.cnpj.ws/cnpj/{cnpj}   (limite 3/min)

Gera CNAE_CLIENTES_BAP.xlsx na mesma pasta (uma linha por COD_CLIENTE + LOJA), com CNAE principal, secundarios,
situacao cadastral e o SEGMENTO BAP sugerido. Nao altera a base de clientes.

Pode interromper e rodar de novo: o que ja foi consultado fica no cache
(cache_cnae.json) e nao e consultado outra vez.

Requisitos: pip install pandas openpyxl requests
"""
import json, re, sys, time
from pathlib import Path

import pandas as pd
import requests

PASTA = Path(__file__).resolve().parent          # nunca caminho absoluto
# usa BASE_CLIENTE_NOVA.xlsx se existir; senao BASE_CLIENTE.xlsx
ARQ_BASE = next((PASTA / n for n in ("BASE_CLIENTE_NOVA.xlsx", "BASE_CLIENTE.xlsx") if (PASTA / n).exists()),
                PASTA / "BASE_CLIENTE_NOVA.xlsx")
ARQ_SAIDA = PASTA / "CNAE_CLIENTES_BAP.xlsx"
ARQ_CACHE = PASTA / "cache_cnae.json"

PAUSA_ENTRE_CONSULTAS = 1.2     # segundos (seja gentil com as APIs gratuitas)
TIMEOUT = 20
COLUNAS_CNPJ_BASE = ["CNPJ", "A1_CGC", "CGC", "CNPJ_CPF", "CPF_CNPJ"]  # se um dia a base trouxer o CNPJ


# ---------------------------------------------------------------- CNPJ
def so_digitos(v):
    if pd.isna(v):
        return ""
    if isinstance(v, float):
        v = int(v)
    return re.sub(r"\D", "", str(v))


def cnpj_valido(s):
    if len(s) != 14 or len(set(s)) == 1:
        return False
    d = [int(c) for c in s]
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    r = sum(a * b for a, b in zip(d[:12], p1)) % 11
    dv1 = 0 if r < 2 else 11 - r
    r = sum(a * b for a, b in zip(d[:13], p2)) % 11
    dv2 = 0 if r < 2 else 11 - r
    return d[12] == dv1 and d[13] == dv2


def cpf_valido(s):
    if len(s) != 11 or len(set(s)) == 1:
        return False
    d = [int(c) for c in s]
    dv1 = sum(a * b for a, b in zip(d[:9], range(10, 1, -1))) * 10 % 11 % 10
    dv2 = sum(a * b for a, b in zip(d[:10], range(11, 1, -1))) * 10 % 11 % 10
    return d[9] == dv1 and d[10] == dv2


def classificar_documento(v):
    """O Excel perde os zeros a esquerda: tenta CNPJ (14) e CPF (11)."""
    s = so_digitos(v)
    if not s:
        return "", "SEM DOCUMENTO"
    # ate 11 digitos e CPF valido -> CPF (um CPF com zeros a esquerda pode "passar" no DV de CNPJ por acaso)
    if len(s) <= 11 and cpf_valido(s.zfill(11)):
        return s.zfill(11), "CPF"
    if cnpj_valido(s.zfill(14)):
        return s.zfill(14), "CNPJ"
    return s, "DOCUMENTO INVALIDO"


def fmt_cnpj(s):
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def fmt_cnae(c):
    c = re.sub(r"\D", "", str(c or "")).zfill(7)
    return f"{c[:4]}-{c[4]}/{c[5:]}" if c.strip("0") else ""


# ---------------------------------------------------------------- APIs
def _brasilapi(cnpj, sessao):
    r = sessao.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"BrasilAPI {r.status_code}")
    j = r.json()
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": j.get("nome_fantasia"),
        "SITUACAO_RF": j.get("descricao_situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(j.get("cnae_fiscal")),
        "CNAE_PRINCIPAL_DESC": j.get("cnae_fiscal_descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("codigo")), x.get("descricao")) for x in (j.get("cnaes_secundarios") or []) if x.get("codigo")],
        "MUNICIPIO_RF": j.get("municipio"), "UF_RF": j.get("uf"),
        "FONTE": "BrasilAPI",
    }


def _minhareceita(cnpj, sessao):
    r = sessao.get(f"https://minhareceita.org/{cnpj}", timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"MinhaReceita {r.status_code}")
    j = r.json()
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": j.get("nome_fantasia"),
        "SITUACAO_RF": j.get("descricao_situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(j.get("cnae_fiscal")),
        "CNAE_PRINCIPAL_DESC": j.get("cnae_fiscal_descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("codigo")), x.get("descricao")) for x in (j.get("cnaes_secundarios") or []) if x.get("codigo")],
        "MUNICIPIO_RF": j.get("municipio"), "UF_RF": j.get("uf"),
        "FONTE": "MinhaReceita",
    }


def _cnpjws(cnpj, sessao):
    r = sessao.get(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=TIMEOUT)
    if r.status_code == 429:
        time.sleep(21)                                   # limite de 3 consultas/minuto
        r = sessao.get(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"CNPJ.ws {r.status_code}")
    j = r.json()
    est = j.get("estabelecimento") or {}
    ap = est.get("atividade_principal") or {}
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": est.get("nome_fantasia"),
        "SITUACAO_RF": est.get("situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(ap.get("subclasse") or ap.get("id")),
        "CNAE_PRINCIPAL_DESC": ap.get("descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("subclasse") or x.get("id")), x.get("descricao")) for x in (est.get("atividades_secundarias") or [])],
        "MUNICIPIO_RF": (est.get("cidade") or {}).get("nome"), "UF_RF": (est.get("estado") or {}).get("sigla"),
        "FONTE": "CNPJ.ws",
    }


def consultar(cnpj, sessao):
    erros = []
    for f in (_brasilapi, _minhareceita, _cnpjws):
        try:
            return f(cnpj, sessao)
        except Exception as e:                            # tenta a proxima fonte
            erros.append(str(e))
    return {"ERRO": " | ".join(erros), "FONTE": ""}


# ---------------------------------------------------------------- segmento BAP
# Ordem importa: a primeira regra que bater define o segmento.
REGRAS_SEGMENTO = [
    ("4541-2", "MOTO PECAS / REVENDA MOTO",
     "Pneus moto + camaras, oleo 4T (10W30 PROACTIVE210, 20W50 4T PROACTIVE), vela VEL7525, filtro FAR6365, fluido FLU15002, aerossois AER"),
    ("4543-9", "OFICINA DE MOTO",
     "Oleo 4T, pneus moto + camaras, vela VEL7525, aerossois AER12000/12001/12002, fluido FLU15002"),
    ("4763-6/03", "BICICLETA / MOTO PECAS",
     "Pneus moto + camaras, oleo 4T, vela VEL7525 (confirmar se vende moto)"),
    ("4530-7/01", "ATACADO DE PECAS",
     "Linha completa em volume: baterias, lubrificantes em tambor, suspensao, freio, filtros"),
    ("4530-7/02", "ATACADO DE PNEUS",
     "Pneus moto + camaras; baterias; lubrificantes"),
    ("4530-7/05", "PNEUS E CAMARAS",
     "Pneus moto + camaras (CAR/CAL), rodas de aco ROD, baterias"),
    ("4530-7/03", "AUTO PECAS (VAREJO)",
     "Suspensao (AMT, KAC/KAP, BIE, PIV), direcao (TER, TAX), freio (PAF, SFR, CIL), filtros (FLU, FAR, FAC, FCB), velas VEL, baterias, lubrificantes"),
    ("4530-7/04", "AUTO PECAS USADAS",
     "Giro rapido: baterias, lubrificantes, filtros, aerossois"),
    ("4520-0/05", "TROCA DE OLEO / LUBRIFICACAO",
     "Lubrificantes PROACTIVE (e tambores TB200), filtros FLU/FAR/FAC/FCB, aditivo RAD, fluido FLU15002"),
    ("4732-6", "COMERCIO DE LUBRIFICANTES",
     "Lubrificantes PROACTIVE e SHIFTEASE, filtros, aditivo RAD"),
    ("4520-0/03", "AUTO ELETRICA",
     "Baterias (TF, LP, EFB, MX), velas e cabos CV, eletroventiladores ELE, bomba de combustivel BCE, sensores INT"),
    ("4520-0/0", "OFICINA MECANICA",
     "Freio (PAF, SFR), suspensao (AMT, KAC, BIE, PIV), rolamentos ROL, kit correia KCD, filtros, oleo, aditivo"),
    ("4731-8", "POSTO DE COMBUSTIVEL",
     "Lubrificantes, filtros, aditivo RAD, palhetas KF, aerossois"),
    ("49", "TRANSPORTE / FROTA",
     "Linha pesada: cuicas CFR, servo SCE, cruzetas CRU, rodas ROD, baterias 150-220Ah, oleo 15W40 tambor, filtros FSE/FCB"),
    ("01", "AGRO",
     "Oleo hidraulico 68 EFFITECH, filtros FHD/FSE, baterias pesadas, cruzetas CRU"),
]


# O SEGMENTO oficial (8 no maximo) e o do cnae_bap.py, na pasta de cima - o
# mesmo que o BAP Tools grava na BASE_CLIENTE. As regras acima so valem se
# ele nao estiver la.
sys.path.insert(0, str(PASTA.parent))
try:
    import cnae_bap as _cnae
    _CTX = _cnae.Contexto(caminho_cache=ARQ_CACHE,
                          caminho_segmentacao=PASTA.parent / "SEGMENTACAO_BAP.xlsx")
    _COMPRA = {s[0]: s[-1] for s in _cnae.SEGMENTOS}
except Exception:                                   # noqa: BLE001
    _CTX = None


def segmento_oficial(r, num, principal, secundarios):
    if _CTX is None:
        return segmento(principal, secundarios)
    d = _CTX.decidir(r.COD_CLIENTE, getattr(r, "LOJA", ""), num,
                     r.NOME_CLIENTE, r.NOME_FANTASIA)
    if d["EXCLUIDO"]:
        return (f"EXCLUIDO | {d['MOTIVO_EXCLUSAO']}",
                f"sugestao pelo nome: {d['SEGMENTO_SUGERIDO'] or '-'}", "EXCLUIDO")
    return f"{d['SEGMENTO']} | {d['SUBSEGMENTO']}", _COMPRA.get(d["SEGMENTO"], ""), \
        d["SEGMENTO_ORIGEM"]


def segmento(principal, secundarios):
    todos = [principal] + [c for c, _ in secundarios]
    # 1) pelo CNAE principal; 2) se nao bater, pelos secundarios
    for lista in ([principal], todos):
        for prefixo, seg, fam in REGRAS_SEGMENTO:
            if any(c and c.startswith(prefixo) for c in lista):
                return seg, fam, ("principal" if lista == [principal] else "secundario")
    return "FORA DO SEGMENTO AUTOMOTIVO", "Avaliar: CNAE nao e de pecas/servicos automotivos", ""


# ---------------------------------------------------------------- principal
def carregar_documentos():
    xl = pd.ExcelFile(ARQ_BASE)
    base = pd.read_excel(xl, sheet_name="BASE_CLIENTE")
    col = next((c for c in COLUNAS_CNPJ_BASE if c in base.columns), None)
    # reserva: CNPJ que vem nas notas, por COD_CLIENTE (usado so se a linha da base estiver sem documento)
    docs_hist = {}
    for aba in ("HIST_POR_NF", "HIST_DETALHADO"):
        if aba in xl.sheet_names:
            h = pd.read_excel(xl, sheet_name=aba, usecols=["COD CLIENTE", "CNPJ"])
            for cod, doc in h.dropna().drop_duplicates().itertuples(index=False):
                docs_hist.setdefault(int(cod), doc)
    return base, docs_hist, col


def documento_da_linha(r, col, docs_hist):
    doc = getattr(r, col) if col else None
    if doc is None or pd.isna(doc) or not so_digitos(doc):
        doc = docs_hist.get(int(r.COD_CLIENTE))
    return classificar_documento(doc) if doc is not None else ("", "SEM DOCUMENTO")


def main():
    if not ARQ_BASE.exists():
        sys.exit(f"Nao encontrei {ARQ_BASE.name} na pasta {PASTA}")
    base, docs_hist, col = carregar_documentos()
    docs = [documento_da_linha(r, col, docs_hist) for r in base.itertuples(index=False)]
    print(f"Base {ARQ_BASE.name}: {len(base)} linhas (COD+LOJA) | coluna de CNPJ: {col or 'nao tem - uso o das notas'}")

    cache = json.loads(ARQ_CACHE.read_text(encoding="utf-8")) if ARQ_CACHE.exists() else {}
    sessao = requests.Session()
    sessao.headers["User-Agent"] = "consulta-cnae-bap/1.0"

    a_consultar = []
    for num, tipo in docs:
        if tipo == "CNPJ" and (num not in cache or "ERRO" in cache[num]):  # erro de antes: tenta de novo
            a_consultar.append(num)
    a_consultar = sorted(set(a_consultar))
    resolvidos = sum(1 for v in cache.values() if "ERRO" not in v)
    print(f"CNPJs para consultar: {len(a_consultar)} | ja resolvidos no cache: {resolvidos}")
    if a_consultar:
        print(f"Tempo estimado: ~{len(a_consultar) * (PAUSA_ENTRE_CONSULTAS + 0.5) / 60:.0f} min")

    for i, cnpj in enumerate(a_consultar, 1):
        cache[cnpj] = consultar(cnpj, sessao)
        ok = "OK " if "ERRO" not in cache[cnpj] else "ERR"
        print(f"[{i}/{len(a_consultar)}] {ok} {fmt_cnpj(cnpj)} {cache[cnpj].get('CNAE_PRINCIPAL', '')} {cache[cnpj].get('FONTE', '')}")
        if i % 20 == 0:
            ARQ_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSA_ENTRE_CONSULTAS)
    ARQ_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if _CTX is not None:
        _CTX.cache = cache                  # o segmento ja ve o que acabou de chegar

    # ---- monta a saida (uma linha por COD_CLIENTE + LOJA da base)
    dup_key = base.groupby(["COD_CLIENTE", "LOJA"]).size().to_dict() if "LOJA" in base.columns else {}
    linhas = []
    for r, (num, tipo) in zip(base.itertuples(index=False), docs):
        cod = int(r.COD_CLIENTE)
        reg = {"COD_CLIENTE": cod, "LOJA": getattr(r, "LOJA", ""), "NOME_CLIENTE": r.NOME_CLIENTE, "NOME_FANTASIA": r.NOME_FANTASIA,
               "UF": r.UF, "CIDADE": r.CIDADE, "STATUS_CLIENTE": r.STATUS_CLIENTE, "CURVA_RECEITA": r.CURVA_RECEITA,
               "TIPO_DOC": tipo, "CNPJ": fmt_cnpj(num) if tipo == "CNPJ" else ("CPF" if tipo == "CPF" else "")}
        reg["COD_LOJA_DUPLICADO"] = "SIM" if dup_key.get((cod, reg["LOJA"]), 0) > 1 else ""
        info = cache.get(num, {}) if tipo == "CNPJ" else {}
        if tipo == "CNPJ" and "ERRO" not in info and info:
            sec = [tuple(x) for x in info.get("CNAES_SECUNDARIOS", [])]
            seg, fam, origem = segmento_oficial(r, num, info.get("CNAE_PRINCIPAL", ""), sec)
            reg.update({"RAZAO_SOCIAL_RF": info.get("RAZAO_SOCIAL_RF"), "NOME_FANTASIA_RF": info.get("NOME_FANTASIA_RF"),
                        "SITUACAO_RF": info.get("SITUACAO_RF"),
                        "CNAE_PRINCIPAL": info.get("CNAE_PRINCIPAL"), "CNAE_PRINCIPAL_DESC": info.get("CNAE_PRINCIPAL_DESC"),
                        "CNAES_SECUNDARIOS": "; ".join(f"{c} {d}" for c, d in sec),
                        "SEGMENTO_BAP": seg, "SEGMENTO_DEFINIDO_POR": origem, "FAMILIAS_SUGERIDAS": fam,
                        "FONTE": info.get("FONTE"), "OBS": ""})
        else:
            motivo = {"CPF": "Pessoa fisica (CPF) - nao tem CNAE",
                      "SEM DOCUMENTO": "Sem CNPJ/CPF no cadastro - completar no Protheus",
                      "DOCUMENTO INVALIDO": "CNPJ com digito invalido - conferir cadastro"}.get(tipo, info.get("ERRO", "Falha na consulta - rode de novo"))
            reg.update({"OBS": motivo})
        linhas.append(reg)

    out = pd.DataFrame(linhas)
    ordem = ["COD_CLIENTE", "LOJA", "NOME_CLIENTE", "NOME_FANTASIA", "UF", "CIDADE", "STATUS_CLIENTE", "CURVA_RECEITA",
             "TIPO_DOC", "CNPJ", "RAZAO_SOCIAL_RF", "NOME_FANTASIA_RF", "SITUACAO_RF", "CNAE_PRINCIPAL",
             "CNAE_PRINCIPAL_DESC", "CNAES_SECUNDARIOS", "SEGMENTO_BAP", "SEGMENTO_DEFINIDO_POR",
             "FAMILIAS_SUGERIDAS", "FONTE", "COD_LOJA_DUPLICADO", "OBS"]
    out = out.reindex(columns=ordem)

    resumo = (out[out.SEGMENTO_BAP.notna()].groupby("SEGMENTO_BAP").size()
              .sort_values(ascending=False).rename("CLIENTES").reset_index())
    with pd.ExcelWriter(ARQ_SAIDA, engine="openpyxl") as w:
        out.to_excel(w, sheet_name="CNAE_CLIENTES", index=False)
        resumo.to_excel(w, sheet_name="RESUMO_SEGMENTO", index=False)
        ws = w.sheets["CNAE_CLIENTES"]
        ws.freeze_panes = "D2"
        ws.auto_filter.ref = ws.dimensions
        larg = {"A": 11, "B": 6, "C": 36, "D": 24, "E": 5, "F": 18, "G": 15, "H": 8, "I": 11, "J": 20, "K": 36, "L": 24,
                "M": 11, "N": 11, "O": 45, "P": 70, "Q": 28, "R": 12, "S": 70, "T": 13, "U": 11, "V": 45}
        for c, v in larg.items():
            ws.column_dimensions[c].width = v
        w.sheets["RESUMO_SEGMENTO"].column_dimensions["A"].width = 32

    achados = out.CNAE_PRINCIPAL.notna().sum()
    print(f"\nPronto: {ARQ_SAIDA.name} | CNAE encontrado para {achados} de {len(out)} linhas (COD+LOJA)")
    print(out.TIPO_DOC.value_counts().to_string())


if __name__ == "__main__":
    main()
