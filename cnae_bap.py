# -*- coding: utf-8 -*-
"""
CNAE E SEGMENTO DOS CLIENTES BAP.

Duas coisas, usadas pelo BAP Tools a cada rodada:

  1) atualizar_cache(tabela)  - le os CNPJs da aba dClientesBap da
     TABELA_BAP e consulta na Receita (APIs publicas gratuitas) SO os que
     ainda nao tem CNAE no cache. O cache e o MESMO do app da pasta
     "Consulta CNAE" (Consulta CNAE\\cache_cnae.json): o que um consulta o
     outro ja aproveita. Tem limite de tempo por rodada: o que nao couber
     fica para a proxima, e a rodada nunca trava por causa da internet.

  2) Contexto().classificar(...) - o base_cliente.py chama para cada
     cliente e grava na BASE_CLIENTE as colunas:
         CNAE_PRINCIPAL, CNAE_DESCRICAO, CNAES_SECUNDARIOS,
         SITUACAO_RECEITA, SEGMENTO, SUBSEGMENTO, SEGMENTO_ORIGEM
     So le o cache - nao vai a internet.

O SEGMENTO (8, fixos) sai da tabela de apoio SEGMENTACAO_BAP.xlsx, na
raiz da pasta, ao lado dos .py. Ela nasce sozinha com as regras de fabrica
e dali em diante quem manda e ela:
    REGRAS_CNAE    prefixo do CNAE -> segmento e subsegmento (o prefixo mais
                   comprido que bater ganha: 4520-0/04 ganha de 4520)
    AJUSTE_MANUAL  COD_CLIENTE + LOJA -> segmento escolhido a mao. Ganha de
                   tudo e nunca e sobrescrito.
    SEGMENTOS      os 8 segmentos e o que e cada um

A ORDEM DA DECISAO (a coluna SEGMENTO_ORIGEM diz qual valeu):
    1. AJUSTE MANUAL            um dos 8, ou EXCLUIR
    2. CNAE PRINCIPAL
       - oficina (4520) que TAMBEM trabalha com pneu (venda, alinhamento,
         borracharia) no CNAE secundario vira AUTOCENTER
    3. CNAE SECUNDARIO          o primeiro que der segmento automotivo
    4. EXCLUIDO                 CPF, sem CNPJ, sem CNAE, CNAE fora dos 8 -
                                sai da BASE_CLIENTE e vai para a aba
                                EXCLUIDOS (com o motivo e uma sugestao de
                                segmento pelo nome, para o ajuste manual)

Sem caminho absoluto: tudo e relativo a pasta deste arquivo.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PASTA_CNAE = AQUI / "SISTEMA BAP" / "Consulta CNAE"
ARQ_CACHE = PASTA_CNAE / "cache_cnae.json"
ARQ_SEGMENTACAO = AQUI / "SEGMENTACAO_BAP.xlsx"

COLUNAS = ["CNAE_PRINCIPAL", "CNAE_DESCRICAO", "CNAES_SECUNDARIOS",
           "SITUACAO_RECEITA", "SEGMENTO", "SUBSEGMENTO", "SEGMENTO_ORIGEM"]
LARGURAS = [11, 40, 50, 12, 24, 30, 16]

# por rodada do BAP Tools: o que passar disso fica para a proxima
LIMITE_CONSULTAS = 150
LIMITE_SEGUNDOS = 240
PAUSA = 1.2                  # entre consultas - as APIs sao gratuitas
TIMEOUT = 15
TENTAR_ERRO_DE_NOVO_DIAS = 3  # CNPJ que falhou so volta a ser consultado depois

# ---------------------------------------------------------------------------
# OS 8 SEGMENTOS (decididos pelo Alexandre em 03/10/2026)
# ---------------------------------------------------------------------------
# So existem estes oito. Quem nao cabe em nenhum (CPF, sem CNAE, consumidor
# final, CNAE fora do automotivo e da industria) SAI da BASE_CLIENTE e vai
# para a aba EXCLUIDOS - e fica fora de rota, meta e oportunidade.
AUTOPECAS = "AUTOPEÇAS"
MOTOPECAS = "MOTOPEÇAS"
DISTRIBUIDOR = "DISTRIBUIDOR DE BATERIAS"
AUTOCENTER = "AUTOCENTER"
OFICINA = "OFICINA MECÂNICA"
POSTO = "POSTO E TROCA DE ÓLEO"
FROTISTA = "FROTISTA/REVENDEDOR"
INDUSTRIA = "INDÚSTRIA"
EXCLUIR = "EXCLUIR"            # so na AJUSTE_MANUAL: tira o cliente da base
OUTROS = EXCLUIR               # compatibilidade com o codigo antigo

SEGMENTOS = [
    (AUTOPECAS, "Loja de peças para carro e caminhão (varejo).",
     "Linha completa: suspensão, freio, filtros, velas, baterias, lubrificantes"),
    (MOTOPECAS, "Loja de peças de moto, oficina de moto e bicicletaria que vende peça de moto.",
     "Pneus e câmaras de moto, óleo 4T, vela, filtro, relação, aerossóis"),
    (DISTRIBUIDOR, "Atacado e representante automotivo: baterias, peças, pneus e lubrificantes. Compra para revender a outra loja.",
     "Volume: baterias, lubrificantes em tambor, linha completa"),
    (AUTOCENTER, "Serviço + venda com pneu: loja de pneus, alinhamento/balanceamento, borracharia, e a oficina que também trabalha com pneu.",
     "Pneus, baterias, suspensão, freio, lubrificantes, filtros"),
    (OFICINA, "Oficina sem pneu no CNAE: mecânica, auto elétrica, funilaria, acessórios, retífica de motores.",
     "Freio, suspensão, rolamentos, correias, elétrica, baterias"),
    (POSTO, "Posto de combustível, troca de óleo/lava-jato e varejo de lubrificantes.",
     "Lubrificantes, filtros, aditivo, palhetas, aerossóis"),
    (FROTISTA, "Frota própria ou revenda de veículo: transportadora, locadora, revenda de carro/moto, motofrete, transporte fluvial e de passageiros.",
     "Linha pesada, baterias 150-220Ah, óleo 15W40 em tambor, filtros"),
    (INDUSTRIA, "Indústria (CNAE de fabricação, divisões 10 a 33) - frota, empilhadeira, gerador e manutenção própria.",
     "Baterias, lubrificantes industriais e de frota, filtros"),
]
NOMES_SEGMENTOS = [s[0] for s in SEGMENTOS]

# (prefixo do CNAE, segmento, subsegmento) - o prefixo mais comprido ganha.
# CNAE que nao bate em nenhuma linha = EXCLUIDO.
REGRAS_PADRAO = [
    # AUTOPECAS
    ("4530-7/03", AUTOPECAS, "VAREJO DE PEÇAS NOVAS"),
    ("4530-7/04", AUTOPECAS, "PEÇAS USADAS"),
    ("4530", AUTOPECAS, "PEÇAS (OUTROS)"),
    # MOTOPECAS
    ("4541-2/06", MOTOPECAS, "VAREJO DE PEÇAS DE MOTO"),
    ("4541-2/07", MOTOPECAS, "PEÇAS USADAS DE MOTO"),
    ("4541", MOTOPECAS, "MOTO (OUTROS)"),
    ("4543-9", MOTOPECAS, "OFICINA DE MOTO"),
    ("4763-6/03", MOTOPECAS, "BICICLETARIA E PEÇAS"),
    # DISTRIBUIDOR DE BATERIAS (todo o atacado automotivo)
    ("4530-7/01", DISTRIBUIDOR, "ATACADO DE PEÇAS E BATERIAS"),
    ("4530-7/02", DISTRIBUIDOR, "ATACADO DE PNEUS"),
    ("4530-7/06", DISTRIBUIDOR, "REPRESENTANTE DE PEÇAS"),
    ("4541-2/02", DISTRIBUIDOR, "ATACADO DE PEÇAS DE MOTO"),
    ("4542-1", DISTRIBUIDOR, "REPRESENTANTE DE MOTO"),
    ("4681-8/05", DISTRIBUIDOR, "ATACADO DE LUBRIFICANTES"),
    # AUTOCENTER
    ("4520-0/04", AUTOCENTER, "ALINHAMENTO E BALANCEAMENTO"),
    ("4520-0/06", AUTOCENTER, "BORRACHARIA"),
    ("4530-7/05", AUTOCENTER, "PNEUS (VAREJO)"),
    # OFICINA
    ("4520-0/01", OFICINA, "MECÂNICA"),
    ("4520-0/02", OFICINA, "FUNILARIA E PINTURA"),
    ("4520-0/03", OFICINA, "AUTO ELÉTRICA"),
    ("4520-0/07", OFICINA, "ACESSÓRIOS / SOM / AR"),
    ("4520-0/08", OFICINA, "CAPOTARIA"),
    ("4520", OFICINA, "SERVIÇO AUTOMOTIVO (OUTROS)"),
    ("2950-6", OFICINA, "RETÍFICA DE MOTORES"),
    ("3314-7/01", OFICINA, "MOTORES E MÁQUINAS"),
    # POSTO E TROCA DE OLEO
    ("4731-8", POSTO, "POSTO DE COMBUSTÍVEL"),
    ("4732-6", POSTO, "VAREJO DE LUBRIFICANTES"),
    ("4520-0/05", POSTO, "TROCA DE ÓLEO / LAVA-JATO"),
    # FROTISTA / REVENDEDOR
    ("4511-1", FROTISTA, "REVENDA DE VEÍCULOS"),
    ("4512-9", FROTISTA, "REPRESENTANTE DE VEÍCULOS"),
    ("4541-2/01", FROTISTA, "REVENDA DE MOTOS (ATACADO)"),
    ("4541-2/03", FROTISTA, "REVENDA DE MOTOS NOVAS"),
    ("4541-2/04", FROTISTA, "REVENDA DE MOTOS USADAS"),
    ("4930", FROTISTA, "TRANSPORTADORA"),
    ("492", FROTISTA, "TRANSPORTE DE PASSAGEIROS"),
    ("50", FROTISTA, "TRANSPORTE FLUVIAL"),
    ("5320-2/02", FROTISTA, "MOTOFRETE / ENTREGA"),
    ("7711", FROTISTA, "LOCADORA DE VEÍCULOS"),
    ("7719", FROTISTA, "LOCADORA (OUTROS VEÍCULOS)"),
    # INDUSTRIA - as divisoes 10 a 33 do CNAE (Secao C, industria de
    # transformacao). 35 a 39 (energia, agua, residuos) NAO entram.
    ("1", INDUSTRIA, "INDÚSTRIA (DIVISÕES 10-19)"),
    ("2", INDUSTRIA, "INDÚSTRIA (DIVISÕES 20-29)"),
    ("30", INDUSTRIA, "INDÚSTRIA (OUTROS EQUIP. DE TRANSPORTE)"),
    ("31", INDUSTRIA, "INDÚSTRIA (MÓVEIS)"),
    ("32", INDUSTRIA, "INDÚSTRIA (DIVERSOS)"),
    ("33", INDUSTRIA, "INDÚSTRIA (MANUTENÇÃO DE MÁQUINAS)"),
]

# oficina que tambem trabalha com PNEU (venda, alinhamento ou borracharia no
# CNAE secundario) = AUTOCENTER. So "mecanica + venda de pecas" continua
# OFICINA: quase toda oficina tem 4530-7/03 de secundario.
VIRA_AUTOCENTER = ("4530-7/05", "4520-0/04", "4520-0/06")

# O NOME do cliente NAO decide o segmento (o CNAE e a regra). Ele so vira
# uma SUGESTAO na aba EXCLUIDOS, para quem for fazer o AJUSTE_MANUAL.
PALAVRAS_NOME = [
    (r"(DISTRIBUID|ATACAD).*(PE[CÇ]|AUTO|LUBRI|PNEU|BATER)"
     r"|(PE[CÇ]AS|AUTO|LUBRI|PNEU|BATER).*(DISTRIBUID|ATACAD)", DISTRIBUIDOR),
    (r"\bMOTO|MOTOPE[CÇ]|\bBIKE|BICICLET", MOTOPECAS),
    (r"AUTO ?CENTER|PNEU|BORRACHAR|ALINHA|\bRODAS\b", AUTOCENTER),
    (r"AUTO ?PE[CÇ]|\bPE[CÇ]AS\b|\bPEAS\b", AUTOPECAS),
    (r"TRANSPORT|LOG[IÍ]STIC|LOCADORA|LOCA[CÇ][AÃ]O|VE[IÍ]CULOS|NAVEGA", FROTISTA),
    (r"\bPOSTO\b|COMBUST|LUBRI|TROCA DE [OÓ]LEO|\bOLEO\b|LAVA ?JATO", POSTO),
    (r"OFICINA|MEC[AÂ]NIC|AUTO ?EL[EÉ]TRIC|RET[IÍ]FICA|AUTOMOT|\bAUTO\b|"
     r"\bCAR\b|AUTO ?CAR|REPARO|ESCAPAMENTO|GARAGEM", OFICINA),
    (r"IND[UÚ]STRIA|INDL\b|FABRICA", INDUSTRIA),
]


# ---------------------------------------------------------------------------
# documento
# ---------------------------------------------------------------------------
def so_digitos(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", str(v))


def cnpj_valido(s: str) -> bool:
    if len(s) != 14 or len(set(s)) == 1:
        return False
    d = [int(c) for c in s]
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    r = sum(a * b for a, b in zip(d[:12], p1)) % 11
    dv1 = 0 if r < 2 else 11 - r
    r = sum(a * b for a, b in zip(d[:13], [6] + p1)) % 11
    dv2 = 0 if r < 2 else 11 - r
    return d[12] == dv1 and d[13] == dv2


def cpf_valido(s: str) -> bool:
    if len(s) != 11 or len(set(s)) == 1:
        return False
    d = [int(c) for c in s]
    dv1 = sum(a * b for a, b in zip(d[:9], range(10, 1, -1))) * 10 % 11 % 10
    dv2 = sum(a * b for a, b in zip(d[:10], range(11, 1, -1))) * 10 % 11 % 10
    return d[9] == dv1 and d[10] == dv2


def tipo_documento(v) -> tuple[str, str]:
    """('00000000000191', 'CNPJ') | (cpf, 'CPF') | ('', 'SEM DOCUMENTO') ..."""
    s = so_digitos(v)
    if not s:
        return "", "SEM DOCUMENTO"
    if len(s) <= 11 and cpf_valido(s.zfill(11)):
        return s.zfill(11), "CPF"
    if cnpj_valido(s.zfill(14)):
        return s.zfill(14), "CNPJ"
    return s, "DOCUMENTO INVALIDO"


def fmt_cnae(c) -> str:
    c = re.sub(r"\D", "", str(c or "")).zfill(7)
    return f"{c[:4]}-{c[4]}/{c[5:]}" if c.strip("0") else ""


def _sem_acento(s) -> str:
    s = "" if s is None else str(s)
    return "".join(ch for ch in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(ch)).upper()


# ---------------------------------------------------------------------------
# cache e consulta na Receita
# ---------------------------------------------------------------------------
def ler_cache(caminho: Path = ARQ_CACHE) -> dict:
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gravar_cache(cache: dict, caminho: Path = ARQ_CACHE) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)


def _get_json(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "consulta-cnae-bap/2.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def _brasilapi(cnpj):
    j = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": j.get("nome_fantasia"),
        "SITUACAO_RF": j.get("descricao_situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(j.get("cnae_fiscal")),
        "CNAE_PRINCIPAL_DESC": j.get("cnae_fiscal_descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("codigo")), x.get("descricao"))
                              for x in (j.get("cnaes_secundarios") or [])
                              if x.get("codigo")],
        "MUNICIPIO_RF": j.get("municipio"), "UF_RF": j.get("uf"),
        "FONTE": "BrasilAPI",
    }


def _minhareceita(cnpj):
    j = _get_json(f"https://minhareceita.org/{cnpj}")
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": j.get("nome_fantasia"),
        "SITUACAO_RF": j.get("descricao_situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(j.get("cnae_fiscal")),
        "CNAE_PRINCIPAL_DESC": j.get("cnae_fiscal_descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("codigo")), x.get("descricao"))
                              for x in (j.get("cnaes_secundarios") or [])
                              if x.get("codigo")],
        "MUNICIPIO_RF": j.get("municipio"), "UF_RF": j.get("uf"),
        "FONTE": "MinhaReceita",
    }


def _cnpjws(cnpj):
    j = _get_json(f"https://publica.cnpj.ws/cnpj/{cnpj}")
    est = j.get("estabelecimento") or {}
    ap = est.get("atividade_principal") or {}
    return {
        "RAZAO_SOCIAL_RF": j.get("razao_social"),
        "NOME_FANTASIA_RF": est.get("nome_fantasia"),
        "SITUACAO_RF": est.get("situacao_cadastral"),
        "CNAE_PRINCIPAL": fmt_cnae(ap.get("subclasse") or ap.get("id")),
        "CNAE_PRINCIPAL_DESC": ap.get("descricao"),
        "CNAES_SECUNDARIOS": [(fmt_cnae(x.get("subclasse") or x.get("id")),
                               x.get("descricao"))
                              for x in (est.get("atividades_secundarias") or [])],
        "MUNICIPIO_RF": (est.get("cidade") or {}).get("nome"),
        "UF_RF": (est.get("estado") or {}).get("sigla"),
        "FONTE": "CNPJ.ws",
    }


FONTES = (_brasilapi, _minhareceita, _cnpjws)


def consultar(cnpj: str) -> dict:
    erros = []
    for fonte in FONTES:
        try:
            r = fonte(cnpj)
            if r.get("CNAE_PRINCIPAL"):
                return r
            erros.append(f"{r.get('FONTE')}: sem CNAE")
        except urllib.error.HTTPError as e:
            erros.append(f"{fonte.__name__.strip('_')} {e.code}")
        except Exception as e:                   # noqa: BLE001 - tenta a proxima
            erros.append(f"{fonte.__name__.strip('_')} {type(e).__name__}")
    return {"ERRO": " | ".join(erros), "FONTE": "",
            "QUANDO": datetime.now().strftime("%Y-%m-%d %H:%M")}


def _precisa_consultar(info: dict | None, hoje: datetime) -> bool:
    if not info:
        return True
    if "ERRO" not in info:
        return False
    quando = info.get("QUANDO")
    if not quando:
        return True
    try:
        return hoje - datetime.strptime(quando, "%Y-%m-%d %H:%M") >= \
            timedelta(days=TENTAR_ERRO_DE_NOVO_DIAS)
    except ValueError:
        return True


def cnpjs_da_tabela(caminho_tabela) -> list[str]:
    """Os CNPJs validos da dClientesBap, sem repetir."""
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    try:
        if "dClientesBap" not in wb.sheetnames:
            return []
        it = wb["dClientesBap"].iter_rows(values_only=True)
        cab = [str(c or "").strip() for c in next(it)]
        i = next((cab.index(n) for n in ("A1_CGC", "A1_CNPJ", "CGC", "CNPJ")
                  if n in cab), None)
        if i is None:
            return []
        saida = set()
        for r in it:
            if i < len(r):
                num, tipo = tipo_documento(r[i])
                if tipo == "CNPJ":
                    saida.add(num)
        return sorted(saida)
    finally:
        wb.close()


def atualizar_cache(cnpjs, log=None, limite=LIMITE_CONSULTAS,
                    limite_segundos=LIMITE_SEGUNDOS, consulta=None,
                    caminho_cache: Path = ARQ_CACHE, pausa: float = PAUSA) -> dict:
    """
    Consulta so o que falta. Devolve o resumo da rodada:
      {"faltavam": n, "consultados": n, "achados": n, "erros": n,
       "ficou_para_depois": n, "sem_internet": bool}
    """
    def aviso(msg):
        if log:
            log.info(msg)
    consulta = consulta or consultar
    cache = ler_cache(caminho_cache)
    hoje = datetime.now()
    faltam = [c for c in dict.fromkeys(cnpjs) if _precisa_consultar(cache.get(c), hoje)]
    res = {"faltavam": len(faltam), "consultados": 0, "achados": 0,
           "erros": 0, "ficou_para_depois": 0, "sem_internet": False}
    if not faltam:
        aviso("  CNAE: todos os clientes ja tem CNAE no cache.")
        return res
    aviso(f"  CNAE: {len(faltam)} CNPJ(s) sem CNAE - consultando "
          f"(ate {limite} ou {limite_segundos}s nesta rodada)...")
    comeco = time.monotonic()
    erros_seguidos = 0
    for n, cnpj in enumerate(faltam, start=1):
        if n > limite or time.monotonic() - comeco > limite_segundos:
            break
        info = consulta(cnpj)
        cache[cnpj] = info
        res["consultados"] += 1
        if "ERRO" in info:
            res["erros"] += 1
            erros_seguidos += 1
        else:
            res["achados"] += 1
            erros_seguidos = 0
        if res["consultados"] % 20 == 0:
            gravar_cache(cache, caminho_cache)
        # 5 falhas seguidas em TODAS as fontes = sem internet / bloqueado
        if erros_seguidos >= 5 and res["achados"] == 0:
            res["sem_internet"] = True
            aviso("  CNAE: as 3 fontes falharam 5 vezes seguidas - sem acesso "
                  "a internet ou bloqueado pela rede. Tento na proxima rodada.")
            break
        if pausa:
            time.sleep(pausa)
    res["ficou_para_depois"] = len(faltam) - res["consultados"]
    gravar_cache(cache, caminho_cache)
    aviso(f"  CNAE: {res['achados']} achado(s), {res['erros']} falha(s), "
          f"{res['ficou_para_depois']} para a proxima rodada.")
    return res


# ---------------------------------------------------------------------------
# a tabela de apoio SEGMENTACAO_BAP.xlsx
# ---------------------------------------------------------------------------
def criar_tabela_segmentacao(caminho: Path = ARQ_SEGMENTACAO,
                             ajustes: list | None = None) -> Path:
    """
    Cria (ou recria) a SEGMENTACAO_BAP.xlsx. `ajustes` sao as linhas da
    AJUSTE_MANUAL a preservar (COD, LOJA, SEGMENTO, SUBSEGMENTO, MOTIVO,
    QUEM, DATA).
    """
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    from openpyxl.worksheet.datavalidation import DataValidation  # noqa: PLC0415

    cab_fill = PatternFill("solid", fgColor="1F4E79")
    cab_font = Font(bold=True, color="FFFFFF", size=9)
    wb = Workbook()
    ws = wb.active
    ws.title = "SEGMENTOS"
    ws.append(["SEGMENTO", "QUEM É", "O QUE MAIS COMPRA"])
    for seg in SEGMENTOS:
        ws.append(list(seg))
    ws.append([])
    ws.append(["Fora destes 8 = EXCLUÍDO: sai da BASE_CLIENTE e vai para a aba "
               "EXCLUIDOS (CPF, sem CNAE, consumidor final, CNAE fora do "
               "automotivo e da indústria)."])
    for c, w in zip("ABC", (26, 95, 60)):
        ws.column_dimensions[c].width = w
    for cel in ws[1]:
        cel.fill, cel.font = cab_fill, cab_font
    for linha in ws.iter_rows(min_row=2):
        for cel in linha:
            cel.alignment = Alignment(wrap_text=True, vertical="top")

    wr = wb.create_sheet("REGRAS_CNAE")
    wr.append(["PREFIXO_CNAE", "SEGMENTO", "SUBSEGMENTO"])
    for r in REGRAS_PADRAO:
        wr.append(list(r))
    for c, w in zip("ABC", (14, 26, 40)):
        wr.column_dimensions[c].width = w
    for cel in wr[1]:
        cel.fill, cel.font = cab_fill, cab_font
    lista = '"' + ",".join(NOMES_SEGMENTOS) + '"'
    dv = DataValidation(type="list", formula1=lista, allow_blank=True)
    wr.add_data_validation(dv)
    dv.add("B2:B500")

    wa = wb.create_sheet("AJUSTE_MANUAL")
    wa.append(["COD_CLIENTE", "LOJA", "SEGMENTO", "SUBSEGMENTO", "MOTIVO",
               "QUEM", "DATA"])
    for linha in ajustes or []:
        wa.append(list(linha))
    for c, w in zip("ABCDEFG", (12, 6, 26, 30, 44, 14, 11)):
        wa.column_dimensions[c].width = w
    for cel in wa[1]:
        cel.fill, cel.font = cab_fill, cab_font
    lista_aj = '"' + ",".join(NOMES_SEGMENTOS + [EXCLUIR]) + '"'
    dv2 = DataValidation(type="list", formula1=lista_aj, allow_blank=True)
    wa.add_data_validation(dv2)
    dv2.add("C2:C5000")

    wl = wb.create_sheet("Leia-me")
    texto = [
        "SEGMENTAÇÃO DOS CLIENTES BAP",
        "",
        "São 8 segmentos (aba SEGMENTOS). O BAP Tools grava SEGMENTO, SUBSEGMENTO e SEGMENTO_ORIGEM na BASE_CLIENTE a cada rodada.",
        "O CNAE é a regra. Ordem: 1) AJUSTE_MANUAL  2) CNAE principal  3) CNAE secundário (só segmento automotivo).",
        "Oficina (4520) que tem pneu, alinhamento ou borracharia no CNAE secundário vira AUTOCENTER.",
        "Quem não cai em nenhum dos 8 SAI da BASE_CLIENTE e vai para a aba EXCLUIDOS: fica fora de rota, meta e oportunidade.",
        "",
        "REGRAS_CNAE: o prefixo mais comprido que bater ganha (4520-0/04 ganha de 4520). Pode acrescentar e mudar linhas.",
        "AJUSTE_MANUAL: COD_CLIENTE (com ou sem zeros) + LOJA (em branco = todas as lojas). Ganha de tudo.",
        "  - SEGMENTO = um dos 8: põe o cliente na base nesse segmento (serve para o CPF que compra para revender).",
        "  - SEGMENTO = EXCLUIR: tira o cliente da base mesmo com CNAE (empresa do grupo, cadastro errado...).",
        "A aba EXCLUIDOS da BASE_CLIENTE traz o MOTIVO e uma SUGESTÃO de segmento pelo nome - é dali que sai o ajuste.",
        "Mudou aqui, vale na próxima rodada do BAP Tools.",
    ]
    for i, t in enumerate(texto, start=1):
        wl.cell(i, 1, t).font = Font(bold=(i == 1), size=12 if i == 1 else 10,
                                     color="1F4E79" if i == 1 else "000000")
    wl.column_dimensions["A"].width = 120
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# nomes antigos (de antes dos 8 segmentos) -> nomes de hoje
_NOMES_ANTIGOS = {"DISTRIBUIDOR": DISTRIBUIDOR, "OUTROS": EXCLUIR,
                  "INDUSTRIA": INDUSTRIA}


def migrar_tabela_segmentacao(caminho: Path = ARQ_SEGMENTACAO) -> bool:
    """
    A tabela feita antes dos 8 segmentos (sem INDUSTRIA, com OUTROS e
    DISTRIBUIDOR) e refeita com as regras novas - os AJUSTES MANUAIS ficam,
    com o nome do segmento traduzido. Devolve True se refez.
    """
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    caminho = Path(caminho)
    if not caminho.exists():
        return False
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        segs = set()
        if "SEGMENTOS" in wb.sheetnames:
            segs = {_sem_acento(r[0]) for r in wb["SEGMENTOS"].iter_rows(
                min_row=2, values_only=True) if r and r[0]}
        if _sem_acento(INDUSTRIA) in segs and _sem_acento("OUTROS") not in segs:
            return False                              # ja esta no formato novo
        ajustes = []
        if "AJUSTE_MANUAL" in wb.sheetnames:
            for r in wb["AJUSTE_MANUAL"].iter_rows(min_row=2, values_only=True):
                if r and r[0] not in (None, "") and len(r) > 2 and r[2]:
                    linha = list(r[:7]) + [None] * (7 - len(r[:7]))
                    seg = _sem_acento(linha[2]).strip()
                    linha[2] = _NOMES_ANTIGOS.get(seg, linha[2])
                    ajustes.append(linha)
    finally:
        wb.close()
    criar_tabela_segmentacao(caminho, ajustes)
    return True


def _ler_tabela_segmentacao(caminho: Path):
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    regras, ajustes = [], {}
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        if "REGRAS_CNAE" in wb.sheetnames:
            for r in list(wb["REGRAS_CNAE"].iter_rows(min_row=2, values_only=True)):
                if r and r[0] and len(r) > 1 and r[1]:
                    regras.append((str(r[0]).strip(), str(r[1]).strip().upper(),
                                   str(r[2] or "").strip().upper()))
        if "AJUSTE_MANUAL" in wb.sheetnames:
            for r in wb["AJUSTE_MANUAL"].iter_rows(min_row=2, values_only=True):
                if r and r[0] not in (None, "") and len(r) > 2 and r[2]:
                    cod = so_digitos(r[0]).zfill(6)
                    loja = so_digitos(r[1]).zfill(2) if r[1] not in (None, "") else ""
                    ajustes[(cod, loja)] = (str(r[2]).strip().upper(),
                                            str(r[3] or "").strip().upper(),
                                            str(r[4] or "").strip())
    finally:
        wb.close()
    return regras, ajustes


class Contexto:
    """Cache + regras + ajustes, lidos UMA vez por base gerada."""

    def __init__(self, caminho_cache: Path = ARQ_CACHE,
                 caminho_segmentacao: Path = ARQ_SEGMENTACAO,
                 criar_tabela: bool = True):
        self.cache = ler_cache(caminho_cache)
        self.aviso = ""
        regras, ajustes = list(REGRAS_PADRAO), {}
        caminho_segmentacao = Path(caminho_segmentacao)
        try:
            if criar_tabela:
                if not caminho_segmentacao.exists():
                    criar_tabela_segmentacao(caminho_segmentacao)
                elif migrar_tabela_segmentacao(caminho_segmentacao):
                    self.aviso = (f"{caminho_segmentacao.name} refeita com os 8 "
                                  f"segmentos (os ajustes manuais ficaram).")
            if caminho_segmentacao.exists():
                lidas, ajustes = _ler_tabela_segmentacao(caminho_segmentacao)
                if lidas:
                    regras = lidas
        except Exception as erro:                   # noqa: BLE001
            self.aviso = (f"Nao consegui ler a {caminho_segmentacao.name} "
                          f"({erro}) - usei as regras de fabrica.")
        self.nome_oficial = {_sem_acento(n): n for n in NOMES_SEGMENTOS}
        self.nome_oficial[_sem_acento(EXCLUIR)] = EXCLUIR
        for antigo, novo in _NOMES_ANTIGOS.items():
            self.nome_oficial.setdefault(antigo, novo)
        # segmento escrito fora dos 8 = a regra nao classifica (EXCLUIDO)
        self.regras = sorted(
            [(p, self.nome_oficial.get(_sem_acento(s), EXCLUIR), sub)
             for p, s, sub in regras],
            key=lambda x: -len(x[0]))
        self.ajustes = {k: (self.nome_oficial.get(_sem_acento(v[0]), EXCLUIR),
                            v[1], v[2] if len(v) > 2 else "")
                        for k, v in ajustes.items()}
        self._palavras = [(re.compile(p), s) for p, s in PALAVRAS_NOME]

    def regra(self, cnae: str):
        if not cnae:
            return None
        for prefixo, seg, sub in self.regras:
            if cnae.startswith(prefixo):
                return seg, sub
        return None

    def sugestao_pelo_nome(self, nome="", fantasia="") -> str:
        alvo = _sem_acento(f"{nome} {fantasia}")
        for padrao, seg in self._palavras:
            if padrao.search(alvo):
                return seg
        return ""

    def decidir(self, cod, loja, documento, nome="", fantasia="") -> dict:
        """
        Tudo sobre o cliente:
          as 7 colunas (COLUNAS) + EXCLUIDO (bool) + MOTIVO_EXCLUSAO +
          SEGMENTO_SUGERIDO (pelo nome, so para quem foi excluido)
        """
        cod6 = so_digitos(cod).zfill(6)
        loja2 = so_digitos(loja).zfill(2) if so_digitos(loja) else ""
        num, tipo = tipo_documento(documento)
        info = self.cache.get(num, {}) if tipo == "CNPJ" else {}
        tem_cnae = bool(info) and "ERRO" not in info and bool(info.get("CNAE_PRINCIPAL"))
        principal = info.get("CNAE_PRINCIPAL", "") if tem_cnae else ""
        secundarios = [tuple(x) for x in info.get("CNAES_SECUNDARIOS", [])] if tem_cnae else []
        d = {
            "CNAE_PRINCIPAL": principal,
            "CNAE_DESCRICAO": (info.get("CNAE_PRINCIPAL_DESC") or "") if tem_cnae else "",
            "CNAES_SECUNDARIOS": "; ".join(f"{c} {x}" for c, x in secundarios)[:1000],
            "SITUACAO_RECEITA": (str(info.get("SITUACAO_RF") or "").upper() if tem_cnae else
                                 {"CPF": "PESSOA FÍSICA", "SEM DOCUMENTO": "SEM DOCUMENTO",
                                  "DOCUMENTO INVALIDO": "CNPJ INVÁLIDO"}.get(
                                      tipo, "CNPJ NÃO CONSULTADO" if tipo == "CNPJ" else "")),
            "SEGMENTO": "", "SUBSEGMENTO": "", "SEGMENTO_ORIGEM": "",
            "EXCLUIDO": False, "MOTIVO_EXCLUSAO": "", "SEGMENTO_SUGERIDO": "",
        }

        def dentro(seg, sub, origem):
            d.update(SEGMENTO=seg, SUBSEGMENTO=sub, SEGMENTO_ORIGEM=origem)
            return d

        def fora(motivo):
            d.update(EXCLUIDO=True, MOTIVO_EXCLUSAO=motivo,
                     SEGMENTO_ORIGEM="EXCLUÍDO",
                     SEGMENTO_SUGERIDO=self.sugestao_pelo_nome(nome, fantasia))
            return d

        # 1) ajuste manual
        aj = self.ajustes.get((cod6, loja2)) or self.ajustes.get((cod6, ""))
        if aj:
            if aj[0] == EXCLUIR:
                return fora("AJUSTE MANUAL: EXCLUIR" + (f" ({aj[2]})" if aj[2] else ""))
            return dentro(aj[0], aj[1] or "AJUSTE MANUAL", "AJUSTE MANUAL")
        # sem CNAE nao tem como classificar
        if tipo == "CPF":
            return fora("CPF - pessoa física / consumidor final")
        if tipo == "SEM DOCUMENTO":
            return fora("Sem CNPJ no cadastro")
        if tipo == "DOCUMENTO INVALIDO":
            return fora("CNPJ inválido no cadastro")
        if not tem_cnae:
            return fora("CNPJ ainda sem CNAE (consulta na próxima rodada)"
                        if not info else "CNAE não encontrado na Receita")
        # 2) CNAE principal
        r = self.regra(principal)
        if r and r[0] != EXCLUIR:
            if r[0] == OFICINA and any(c.startswith(VIRA_AUTOCENTER) for c, _ in secundarios):
                return dentro(AUTOCENTER, "OFICINA COM PNEU/ALINHAMENTO", "CNAE PRINCIPAL")
            return dentro(r[0], r[1], "CNAE PRINCIPAL")
        # 3) CNAE secundario - so segmento AUTOMOTIVO (industria so pelo
        #    principal: mercadinho que fabrica gelo nao e industria)
        for c, _x in secundarios:
            r2 = self.regra(c)
            if r2 and r2[0] not in (EXCLUIR, INDUSTRIA):
                return dentro(r2[0], r2[1], "CNAE SECUNDÁRIO")
        return fora(f"CNAE fora dos 8 segmentos: {principal} "
                    f"{(d['CNAE_DESCRICAO'] or '')[:60]}".strip())

    def classificar(self, cod, loja, documento, nome="", fantasia="") -> list:
        """As 7 colunas, na ordem de COLUNAS (SEGMENTO vazio = excluido)."""
        d = self.decidir(cod, loja, documento, nome, fantasia)
        return [d[c] for c in COLUNAS]
