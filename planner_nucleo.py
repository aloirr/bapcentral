# -*- coding: utf-8 -*-
"""
Motor da roteirizacao BAP.

Nao tem tela aqui: e so leitura da BASE_CLIENTE, contas e geracao do Excel
da rota. Quem desenha a janela e o bap_planner.py.

O estado do usuario mora em um unico JSON (planner_config.json):
    - zonas          (id, nome, uf, vendedor, visitas_por_dia, frequencia)
    - pessoas        (cargo, cod_protheus, cod_maxima, nome, uf_base,
                      cidade_base, responde_a) - gerente, supervisor e
                      vendedor na mesma lista
    - areas          {chave_da_area: id_da_zona}   <- o que o usuario move
    - mes            "2026-10"
    - feriados       ["2026-10-12", ...]
    - parametros     (dias de churn, usar sabado, etc.)

A "area" e a menor unidade que muda de zona: em Manaus e o bairro, no resto
do Brasil e a cidade. Isso e o que permite dizer "tira Castanhal da zona de
Belem" ou "passa o Japiim da zona Sul para a Leste" sem tocar em cliente.
"""
from __future__ import annotations

import calendar
import datetime as dt
import gzip
import hashlib
import json
import math
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from copy import copy
from pathlib import Path

from openpyxl import Workbook, load_workbook
try:  # leitura rapida com cache (sem o arquivo: openpyxl)
    from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
except ImportError:
    from openpyxl import load_workbook  # noqa: PLC0415
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import geografia as geo
import zonas_padrao as zp

VERSAO = "1.0"

CURVAS = ["S", "A", "B", "C", "Z"]
MESES_JANELA = 3            # a mesma janela usada na curva do base_cliente.py
SEM_ZONA = "(SEM ZONA)"     # onde cai o cliente que ainda nao tem zona
# a SITUACAO do cliente pelos dias sem compra. (06/10) quem passa do corte
# e CHURN 90+ - INATIVO e so o cliente inativado a mao (aba Base cliente)
STATUS = ["ATIVO", "CHURN 30", "CHURN 60", "CHURN 90", "CHURN 90+",
          "NUNCA COMPROU"]
SITUACAO_90 = "CHURN 90+"
DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

PARAMETROS_PADRAO = {
    # curva pela media mensal dos ultimos 3 meses de faturamento
    "curva_s": 20000.0,
    "curva_a": 10000.0,
    "curva_b": 5000.0,
    "curva_c": 1.0,
    "meses_curva": 3,
    # escada de churn, em dias sem comprar
    "churn_30": 30,
    "churn_60": 60,
    "churn_90": 90,
    "inativo": 90,          # acima disso e CHURN 90+ (regra do Alexandre)
    # rota
    # faturamento do resumo gerencial
    "meses_faturamento": 6,  # a janela do FAT. M6M
    "dias_comprante": 90,    # COMPRANTES = comprou nos ultimos N dias
    # rota - (18/10, Alexandre) TETO EM VIGOR: 12 por dia e 6 na sexta (as
    # metas de visita foram feitas com esses numeros; o 15/8 foi cancelado)
    "visitas_por_dia": 12,
    # SEXTA-FEIRA E DIA DE PROSPECCAO (06/10): o teto da sexta e este, nao o
    # visitas_por_dia (0 = a sexta segue o teto normal)
    "visitas_sexta": 12,           # (03/11) sexta normal, 12 (era 6)
    # (17/10, Alexandre) A CIDADE BASE NO COMECO DO MES: nos N primeiros
    # dias uteis o vendedor so roda a cidade base dele (cadastro, aba 2) e
    # as cidades ate raio_base_km dela (0 = so a cidade). 0 dias = sem regra
    "dias_cidade_base": 10,
    "raio_base_km": 50,
    # (17/10) VISITA SEMANAL: os TOP N clientes do vendedor (faturamento
    # dos ultimos 6 meses) e os clientes COM LIMITE de credito. Semanal de verdade so para
    # o vendedor da CAPITAL (carteira a ate raio_capital_km da capital);
    # para quem viaja eles so passam na frente da fila
    "top_semanal": 30,
    "raio_capital_km": 50,
    # QUANTAS VISITAS CADA CLIENTE RECEBE nao e mais escolha: vem da
    # CURVA, no automatico (S semanal, A semana sim semana nao, B e C
    # quinzenal, Z uma visita se sobrar espaco). Ver plano_da_curva().
    # SABADO - duas coisas diferentes, e nenhuma delas se liga/desliga por
    # zona:
    #   ULTIMO SABADO   todo vendedor trabalha, sempre, todo mes, com o
    #                   mesmo teto de visitas_por_dia dos dias uteis. Nao
    #                   ha chave para isso: e regra fixa da BAP.
    #   excedentes_no_sabado  o PRIMEIRO sabado vira DEPOSITO: o dia util
    #                   enche ate o teto e todo o excedente e visitado uma
    #                   vez la, sem limite de quantos cabem
    "excedentes_no_sabado": False,
    # a BASE_CLIENTE e gerada AQUI, nao mais no BAP Automation: ao abrir, se a
    # TABELA_BAP estiver mais nova que a BASE_CLIENTE, o planner regera
    "atualizar_base_ao_abrir": True,
    # (15/10, Alexandre) VENDEDOR PADRAO: o A1_VEND do cliente que NAO entra
    # no Planner (sem vendedor na zona/segmento, cadeira vaga/provisoria ou
    # inativado na aba Base cliente) no .json da base do Protheus - vai com
    # este codigo (e o supervisor_padrao). (20/10) e vai ATIVO, como todos
    "vendedor_padrao": "000000",
    # (15/10) e o SUPERVISOR desse cliente no .json
    "supervisor_padrao": "000037",
    # (21/10, Alexandre) VENDEDOR DO INTERIOR: 6 clientes por dia numa
    # cidade do interior e o teto normal (12) no dia da cidade base. Vale
    # na rota automatica e no calendario da Rota por cidade (0 = sem regra)
    "teto_interior": 6,
    # (21/10, Alexandre) CADASTROS EM LOTE: os clientes com A1_DTCAD num
    # destes dias (o lote lancado no Protheus em 16/10) NAO contam como
    # visita em relatorio nenhum (Farol de Visita, Parcial, Farol de Metas,
    # RV). Continuam como cadastro na base.
    "datas_cadastro_lote_fora": ["2026-10-16"],
    # (22/10, Alexandre) JORNADA DE TRABALHO do vendedor: segunda a sexta,
    # das 07:30 as 18:00 (segunda a quinta) e as 17:00 na sexta; a JORNADA
    # LIQUIDA (do 1o ao ultimo cliente, dentro do expediente) tem de dar
    # pelo menos 08:00. Vale no Farol de Visita e na Parcial Visitas (nao
    # mexe na rota)
    "jornada_inicio": "07:30",
    "jornada_fim": "18:00",
    "jornada_fim_sexta": "17:00",
    "jornada_liquida": "08:00",
    # (22/10, Alexandre) INTERVALO DE ALMOCO maximo: do fim da ultima visita
    # da manha ao inicio da 1a da tarde (acima disso, o dia fica vermelho)
    "jornada_almoco_max": "01:30",
    # (22/10, Alexandre) PROSPECCAO (Microsoft Forms): a visita a cliente
    # fora da base registrada no formulario conta como visita (fora de
    # rota), no dia do ENVIO. O Excel de respostas do Forms (vazio = acha
    # sozinho no OneDrive ou em RELATORIOS\Visitas\PROSPECCAO). Nao mexe
    # na rota
    "arquivo_prospeccao_forms": "",
}

# as chaves que NAO mudam a rota (nao entram na assinatura dos parametros)
PARAMETROS_FORA_DA_ROTA = ("vendedor_padrao", "supervisor_padrao",
                           "jornada_inicio", "jornada_fim",
                           "jornada_fim_sexta", "jornada_liquida",
                           "jornada_almoco_max", "arquivo_prospeccao_forms")


def _hhmm_seg(txt, padrao):
    """'07:30' -> segundos desde a meia-noite."""
    import re as _re                                    # noqa: PLC0415
    m = _re.match(r"^\s*(\d{1,2})[:hH.](\d{2})\s*$", str(txt or ""))
    if not m:
        m = _re.match(r"^\s*(\d{1,2})[:hH.](\d{2})\s*$", padrao)
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 3600 + mi * 60


def jornada_de_trabalho(cfg=None) -> dict:
    """(22/10, Alexandre) {inicio, fim (seg a qui), fim_sexta, liquida} em
    segundos, do Planner (Parametros > JORNADA DE TRABALHO)."""
    par = dict(PARAMETROS_PADRAO)
    par.update(((cfg or {}).get("parametros") or {}))
    P = PARAMETROS_PADRAO
    return {"inicio": _hhmm_seg(par.get("jornada_inicio"),
                                P["jornada_inicio"]),
            "fim": _hhmm_seg(par.get("jornada_fim"), P["jornada_fim"]),
            "fim_sexta": _hhmm_seg(par.get("jornada_fim_sexta"),
                                   P["jornada_fim_sexta"]),
            "liquida": _hhmm_seg(par.get("jornada_liquida"),
                                 P["jornada_liquida"]),
            "almoco_max": _hhmm_seg(par.get("jornada_almoco_max"),
                                    P["jornada_almoco_max"])}


# ==========================================================================
# utilidades
# ==========================================================================
def norm(valor) -> str:
    return zp.normalizar(valor)


def texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def numero(valor) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def data_de(valor):
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    s = texto(valor)
    if not s:
        return None
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
              "%d-%m-%y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s[:19], f).date()
        except ValueError:
            pass
    return None


def pct(parte, total) -> float:
    return (parte / total * 100.0) if total else 0.0


# ==========================================================================
# calendario
# ==========================================================================
def dias_do_mes(mes: str, feriados=(), com_sabado=False):
    """
    '2026-10' -> lista de dias uteis do mes.
    Devolve [(data, nome_do_dia, semana_do_mes, e_sabado)].
    Semana 1 = primeira semana que tem dia util.
    """
    ano, m = (int(x) for x in mes.split("-")[:2])
    fer = {data_de(f) for f in feriados}
    fer.discard(None)
    saida = []
    semana = 0
    ultima_segunda = None
    for dia in range(1, calendar.monthrange(ano, m)[1] + 1):
        d = dt.date(ano, m, dia)
        wd = d.weekday()                      # 0=segunda .. 6=domingo
        if wd == 6 or d in fer:
            continue
        if wd == 5 and not com_sabado:
            continue
        segunda = d - dt.timedelta(days=wd)
        if segunda != ultima_segunda:
            ultima_segunda = segunda
            semana += 1
        saida.append((d, DIAS_PT[wd], semana, wd == 5))
    return saida


def dias_uteis(mes: str, feriados=()) -> int:
    """Dias uteis 'de verdade' (sem sabado) - e a base do clientes/dia."""
    return sum(1 for _, _, _, sab in dias_do_mes(mes, feriados, True) if not sab)


# ==========================================================================
# configuracao
# ==========================================================================
def codigo_livre(usados: set, uf: str) -> str:
    """
    Codigo da zona: Z-<UF>-<NN>. Z-AM-01, Z-AM-02, Z-PA-01...
    Zona sem UF (A DEFINIR, FORA DE ROTA) usa XX: Z-XX-01.
    """
    uf = (norm(uf) or "XX").replace("-", "")[:2] or "XX"
    if uf in ("", "--"):
        uf = "XX"
    n = 1
    while f"Z-{uf}-{n:02d}" in usados:
        n += 1
    return f"Z-{uf}-{n:02d}"


def atribuir_codigos(cfg: dict) -> int:
    """
    Garante um codigo para toda zona. Codigo ja dado NUNCA muda - e ele que
    aparece no cadastro do vendedor e nos relatorios, entao trocar quebraria
    a comparacao de um mes para o outro.
    """
    usados = {z.get("codigo") for z in cfg["zonas"] if z.get("codigo")}
    novos = 0
    for z in cfg["zonas"]:
        if not z.get("codigo"):
            z["codigo"] = codigo_livre(usados, z.get("uf", ""))
            usados.add(z["codigo"])
            novos += 1
    return novos


# --------------------------------------------------------------------------
# CADASTRO DE PESSOAS - gerente, supervisor e vendedor na mesma lista.
# A hierarquia e um campo so: "responde_a" guarda o codigo Protheus de quem
# esta acima. Vendedor responde a supervisor; supervisor responde a gerente.
# --------------------------------------------------------------------------
CARGOS = ["GERENTE", "SUPERVISOR", "VENDEDOR"]

# OS 8 SEGMENTOS DE CLIENTE (a BASE_CLIENTE so traz estes - quem nao cabe
# vai para a aba EXCLUIDOS). Vem do cnae_bap.py; a lista fixa e a reserva
# para quando o modulo nao estiver na pasta.
try:
    import cnae_bap as _cnae                      # noqa: E402
    SEGMENTOS = list(_cnae.NOMES_SEGMENTOS)
except Exception:                                 # noqa: BLE001
    SEGMENTOS = ["AUTOPEÇAS", "MOTOPEÇAS", "DISTRIBUIDOR DE BATERIAS",
                 "AUTOCENTER", "OFICINA MECÂNICA", "POSTO E TROCA DE ÓLEO",
                 "FROTISTA/REVENDEDOR", "INDÚSTRIA"]
SEM_SEGMENTO = "(SEM SEGMENTO)"


def segmento_do_cliente(c: dict) -> str:
    return texto(c.get("SEGMENTO")).upper() or SEM_SEGMENTO
CODIGO_PROVISORIO = 901     # de onde partem os codigos provisorios

UF_BASE = ["AM", "RR", "AP", "PA", "MA", "MT"]
CIDADES_BASE = {
    "AM": ["MANAUS"],
    "RR": ["BOA VISTA"],
    "AP": ["MACAPA"],
    "PA": ["BELEM", "SANTAREM", "PARAUAPEBAS"],
    "MA": ["SAO LUIS", "IMPERATRIZ"],
    "MT": ["CUIABA"],
}


def cidades_da_uf(uf: str, clientes=None) -> list:
    """As cidades da UF para a CIDADE BASE do vendedor. (17/10) Com a base
    de clientes: todas as cidades dos clientes daquela UF, em ordem
    alfabetica (mais as cidades-base de sempre)."""
    uf = norm(uf)
    fixas = list(CIDADES_BASE.get(uf, []))
    if not clientes:
        return fixas
    da_base = {norm(c.get("CIDADE")) for c in clientes
               if norm(c.get("UF")) == uf and norm(c.get("CIDADE"))}
    return sorted(da_base | set(fixas))


# ==========================================================================
# (18/10, Alexandre) DATA DE ADMISSAO no cadastro da pessoa. Dela sai o MES
# DE CASA de cada mes (1 = o mes da admissao) e a PROPORCAO do primeiro mes
# (dias uteis desde a admissao / dias uteis do mes) - melhor do que
# escrever o mes de casa a mao todo mes. A rota do mes da admissao comeca no
# dia dela.
# (20/10, Alexandre) Com a data de admissao, o MES DE CASA e automatico (so
# informativo na tela) - e vale JA EM OUTUBRO/26 (as metas fixas de outubro
# foram refeitas por ela). Os meses de antes de outubro ficam como estavam.
# Sem data de admissao: o mes de casa escrito.
# ==========================================================================
CASA_PELA_ADMISSAO_DESDE = "2026-10"


def data_admissao(pessoa) -> dt.date | None:
    """A data de admissao do cadastro ('AAAA-MM-DD' ou 'DD/MM/AAAA')."""
    v = (pessoa or {}).get("data_admissao")
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = texto(v)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        a, mm, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
        if not m:
            return None
        d, mm, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return dt.date(a, mm, d)
    except ValueError:
        return None


def casa_pela_admissao(mes: str) -> bool:
    """O mes (AAAA-MM) ja usa a data de admissao (out/26 em diante)."""
    return texto(mes)[:7] >= CASA_PELA_ADMISSAO_DESDE


def mes_de_casa_no_mes(pessoa, mes: str) -> int:
    """O mes de casa da pessoa no mes AAAA-MM (1 = mes da admissao).
    Antes de out/26 ou sem data de admissao: o mes de casa escrito.
    Admitido depois do mes: 0."""
    adm = data_admissao(pessoa)
    if adm is not None and casa_pela_admissao(mes):
        try:
            a, m = int(mes[:4]), int(mes[5:7])
        except ValueError:
            return 0
        n = (a * 12 + m) - (adm.year * 12 + adm.month) + 1
        return n if n >= 1 else 0
    try:
        n = int(float(str((pessoa or {}).get("meses_de_casa") or 0)
                      .replace(",", ".")))
    except ValueError:
        return 0
    return max(n, 0)


def fracao_do_mes(pessoa, mes: str, feriados=()) -> float:
    """A parte do mes que a pessoa trabalha: no mes da admissao, os dias
    uteis (seg a sex, sem feriado) desde ela / os dias uteis do mes; nos
    outros meses (e antes de out/26), 1."""
    adm = data_admissao(pessoa)
    if adm is None or not casa_pela_admissao(mes) or \
            f"{adm:%Y-%m}" != texto(mes)[:7]:
        return 1.0
    fer = {texto(f)[:10] for f in feriados or ()}
    a, m = adm.year, adm.month
    uteis = [dt.date(a, m, d) for d in range(1, calendar.monthrange(a, m)[1]
                                              + 1)
             if dt.date(a, m, d).weekday() < 5
             and dt.date(a, m, d).isoformat() not in fer]
    if not uteis:
        return 1.0
    return sum(1 for d in uteis if d >= adm) / len(uteis)


def normalizar_pessoas(cfg: dict) -> None:
    """
    Converte o cadastro antigo (vendedores + supervisores separados) para a
    lista unica de pessoas. Roda em toda abertura e nao perde nada:
      - cada vendedor vira uma pessoa com cargo VENDEDOR
      - cada supervisor vira uma pessoa com cargo SUPERVISOR
      - o vinculo vendedor->supervisor, que era por NOME, vira responde_a
        com o codigo Protheus do supervisor
    """
    pessoas = list(cfg.get("pessoas") or [])
    ja = {texto(p.get("cod_protheus")) for p in pessoas}

    # supervisores antigos: lista de nomes ou de {codigo, nome}
    de_nome = {}
    for s in cfg.get("supervisores") or []:
        nome = texto(s if isinstance(s, str) else s.get("nome"))
        if not nome:
            continue
        cod = texto((s or {}).get("codigo")) if isinstance(s, dict) else ""
        de_nome[nome] = cod
        if cod and cod in ja:
            continue
        if any(norm(p.get("nome")) == norm(nome) for p in pessoas):
            continue
        pessoas.append({"cod_protheus": cod, "cod_maxima": "", "nome": nome,
                        "cargo": "SUPERVISOR", "uf_base": "", "cidade_base": "",
                        "responde_a": "", "ativo": True})

    for v in cfg.get("vendedores") or []:
        cod = texto(v.get("codigo"))
        if not cod or cod in ja:
            continue
        # o supervisor antigo era so um NOME. Guardo o nome aqui e resolvo
        # para codigo la embaixo, DEPOIS que todo mundo tiver codigo - senao
        # o supervisor provisorio ainda nao existe e o vinculo se perde.
        pessoas.append({"cod_protheus": cod, "cod_maxima": "",
                        "nome": texto(v.get("nome")), "cargo": "VENDEDOR",
                        "uf_base": "", "cidade_base": "", "responde_a": "",
                        "_chefe_nome": texto(v.get("supervisor")),
                        "ativo": bool(v.get("ativo", True))})
        ja.add(cod)

    # limpa e garante os campos
    saida, vistos = [], set()
    for p in pessoas:
        nome = texto(p.get("nome"))
        if not nome:
            continue
        cargo = norm(p.get("cargo")) or "VENDEDOR"
        if cargo not in CARGOS:
            cargo = "VENDEDOR"
        cod = texto(p.get("cod_protheus"))
        if cod and cod in vistos:
            continue
        if cod:
            vistos.add(cod)
        registro = {
            "cod_protheus": cod,
            "cod_maxima": texto(p.get("cod_maxima")),
            "nome": nome,
            "cargo": cargo,
            "uf_base": norm(p.get("uf_base")),
            "cidade_base": norm(p.get("cidade_base")),
            "responde_a": texto(p.get("responde_a")),
            # VENDEDOR DO INTERIOR: a rota dele e montada por CIDADE - um
            # dia, uma cidade so, ate o teto de visitas por dia
            "interior": bool(p.get("interior", False)),
            # CONTABILIZAR PARA A META DO SUPERVISOR: o vendedor VAGO
            # (a zona existe, os clientes existem, mas nao ha ninguem na
            # cadeira) tem meta - ela e da carteira, nao da pessoa - mas
            # NAO entra na soma do supervisor, senao a equipe recebe meta
            # de quem nao esta la para vender.
            "conta_supervisor": bool(p.get("conta_supervisor", True)),
            "ativo": bool(p.get("ativo", True)),
            "provisorio": bool(p.get("provisorio", False)),
        }
        # o E-MAIL do cadastro (o Farol de Metas manda a parcial para ele).
        # Antes esta limpeza o jogava fora a cada abertura do Planner.
        if texto(p.get("email")):
            registro["email"] = texto(p["email"]).strip().lower()
        # O MES DE CASA (1 = primeiro mes): a meta de quem esta chegando
        # sai da tabela do Gerador de Meta (aba 1)
        try:
            casa = int(float(str(p.get("meses_de_casa") or 0)
                             .replace(",", ".")))
        except ValueError:
            casa = 0
        if casa > 0:
            registro["meses_de_casa"] = casa
        adm = data_admissao(p)
        if adm is not None:
            registro["data_admissao"] = adm.isoformat()
        if p.get("_chefe_nome"):
            registro["_chefe_nome"] = texto(p["_chefe_nome"])
        # AS ZONAS QUE O SUPERVISOR ATENDE (ids de zona): nao mexem na rota
        # nem na carteira - o Gerador de Meta soma no resultado dele os
        # clientes delas que nao sao de um vendedor dele
        if cargo == "SUPERVISOR" and p.get("zonas_supervisor"):
            registro["zonas_supervisor"] = [texto(z) for z in
                                            p["zonas_supervisor"] if texto(z)]
        saida.append(registro)

    # Quem ficou sem codigo Protheus ganha um PROVISORIO. Tem de ser NUMERO,
    # porque e assim que ele sai no PLANNER; comeca em 901 para nao esbarrar
    # nos codigos de verdade (que hoje vao ate 41). A marca provisorio=True
    # faz a linha aparecer em amarelo no cadastro, pedindo o codigo real.
    n = CODIGO_PROVISORIO
    for p in saida:
        if not p["cod_protheus"]:
            while str(n) in vistos:
                n += 1
            p["cod_protheus"] = str(n)
            p["provisorio"] = True
            vistos.add(p["cod_protheus"])

    # agora que todo mundo tem codigo, resolve o vinculo que veio por NOME.
    # Chefe tem de ser supervisor/gerente: quem acumula os dois papeis (a Lais
    # e supervisora E tem carteira) apareceria duas vezes, e o vinculo tem de
    # cair no registro de SUPERVISOR, nao no de vendedor.
    por_nome = {norm(p["nome"]): p["cod_protheus"] for p in saida
                if p["cargo"] == "VENDEDOR"}
    por_nome.update({norm(p["nome"]): p["cod_protheus"] for p in saida
                     if p["cargo"] != "VENDEDOR"})
    for p in saida:
        nome_chefe = p.pop("_chefe_nome", "")
        if nome_chefe and not p["responde_a"]:
            p["responde_a"] = por_nome.get(norm(nome_chefe), "")

    # responde_a que aponta para quem nao existe mais fica em branco
    validos = {p["cod_protheus"] for p in saida}
    for p in saida:
        if p["responde_a"] not in validos or p["responde_a"] == p["cod_protheus"]:
            p["responde_a"] = ""

    # MIGRACAO DE UMA VEZ SO. Antes de existir o campo ATIVO/INATIVO, a
    # cadeira em aberto era escrita no NOME: "VAGO (ZONA INTERIOR)". Na
    # primeira abertura depois da atualizacao essa gente nasce INATIVA -
    # que e o que ela sempre foi. Dali em diante a marca e do cadastro:
    # o programa nao mexe mais nela, nem se o nome continuar VAGO.
    if not cfg.get("vago_virou_inativo"):
        for p in saida:
            if p["cargo"] == "VENDEDOR" and norm(p["nome"]).startswith("VAGO"):
                p["ativo"] = False
        cfg["vago_virou_inativo"] = True

    cfg["pessoas"] = saida
    cfg.pop("vendedores", None)
    cfg.pop("supervisores", None)


def pessoas_do_cargo(cfg: dict, cargo: str) -> list:
    return [p for p in cfg.get("pessoas") or [] if p["cargo"] == cargo]


def vendedores(cfg: dict) -> list:
    return pessoas_do_cargo(cfg, "VENDEDOR")


def supervisores(cfg: dict) -> list:
    return pessoas_do_cargo(cfg, "SUPERVISOR")


def pessoa_por_codigo(cfg: dict, cod: str) -> dict:
    cod = texto(cod)
    for p in cfg.get("pessoas") or []:
        if p["cod_protheus"] == cod:
            return p
    return {}


def vendedor_e_supervisor(cfg: dict, cod, loja, uf, cidade, bairro,
                          segmento) -> tuple:
    """(07/10) Para a BASE_CLIENTE do BAP Tools: ((cod, nome) do vendedor,
    (cod, nome) do supervisor) que o PLANNER da a esse cliente - a mesma
    conta do ler_base_cliente + vendedor_do_cliente (excecao do analitico,
    senao quem atende o segmento na zona do bairro)."""
    cod6 = texto(cod).zfill(6)
    loja = texto(loja)
    bairro_limpo = zp.normalizar(texto(bairro)) or "(SEM BAIRRO)"
    cli = {"CHAVE_CLIENTE": f"{cod6}-{loja or '00'}",
           "AREA": chave_de_area(norm(uf), norm(cidade), bairro_limpo),
           "SEGMENTO": texto(segmento).upper()}
    v = texto(vendedor_do_cliente(cfg, cli))
    return pessoa_e_chefe(cfg, v)


def pessoa_e_chefe(cfg: dict, cod) -> tuple:
    """((cod, nome) da pessoa, (cod, nome) do supervisor dela) pelo
    cadastro do Planner. Codigo que o Planner nao conhece: so o codigo."""
    cod = texto(cod)
    if not cod:
        return ("", ""), ("", "")
    p = pessoa_por_codigo(cfg, cod) or pessoa_por_codigo(cfg, cod.zfill(6))
    sup = chefe_de(cfg, p.get("cod_protheus", "")) if p else {}
    if sup.get("cargo") != "SUPERVISOR":
        sup = {}
    return ((cod, texto(p.get("nome"))),
            (texto(sup.get("cod_protheus")), texto(sup.get("nome"))))


def chefe_de(cfg: dict, cod: str) -> dict:
    """Quem esta acima: do vendedor devolve o supervisor, e assim por diante."""
    p = pessoa_por_codigo(cfg, cod)
    return pessoa_por_codigo(cfg, p.get("responde_a", "")) if p else {}


def nome_supervisor(cfg: dict, cod_vendedor: str) -> str:
    return chefe_de(cfg, cod_vendedor).get("nome", "")


def vendedor_do_interior(cfg: dict, cod_vendedor: str) -> bool:
    """
    O vendedor esta marcado como DO INTERIOR na aba 2? Se estiver, a rota
    dele e montada por CIDADE: cada dia tem uma cidade so, ate o teto de
    visitas por dia. E a diferenca entre rodar bairro a bairro dentro de
    Manaus e viajar para uma cidade e passar o dia la.
    """
    return bool(pessoa_por_codigo(cfg, cod_vendedor).get("interior", False))


def conta_para_o_supervisor(cfg: dict, cod_vendedor: str) -> bool:
    """
    A meta deste vendedor entra na soma do supervisor dele? De fabrica
    SIM. Vira NAO no cadastro (aba 2) para o vendedor VAGO: a carteira
    dele continua com meta - ela e dos clientes - mas o supervisor nao
    responde por ela enquanto ninguem ocupar a cadeira.
    """
    if not cod_vendedor:
        return False
    pessoa = pessoa_por_codigo(cfg, cod_vendedor)
    if not pessoa:
        return True
    return bool(pessoa.get("conta_supervisor", True))


def pessoa_ativa(cfg: dict, cod: str) -> bool:
    """
    A pessoa esta ATIVA no cadastro (aba 2)? De fabrica sim.

    INATIVO e a cadeira VAGA: a zona existe, os clientes existem e a rota
    continua saindo - o que muda e a CONTAGEM. Vendedor inativo nao entra
    em QTD VDE, nao divide o QTD CLI/VDE e a zona dele conta como ZONA
    S/ VDE no gerencial. E assim que a vaga em aberto aparece como vaga,
    em vez de virar um vendedor a mais na base.
    """
    if not cod:
        return False
    pessoa = pessoa_por_codigo(cfg, cod)
    if not pessoa:
        # codigo que aparece na base e nao esta no cadastro: conta como
        # ativo, senao um faturamento de ontem sumiria da conta
        return True
    return bool(pessoa.get("ativo", True))


def vendedores_ativos(cfg: dict) -> list:
    return [p for p in vendedores(cfg) if p.get("ativo", True)]


def gerente_de(cfg: dict, cod_vendedor: str) -> dict:
    """
    Sobe a hierarquia ate achar um GERENTE. Se o vendedor responde direto
    ao gerente, ja acha no primeiro salto; se responde ao supervisor, acha
    no segundo. Para em 4 saltos para nao girar se alguem se ligar errado.
    """
    visto, atual = set(), texto(cod_vendedor)
    for _ in range(4):
        p = chefe_de(cfg, atual)
        if not p or p["cod_protheus"] in visto:
            return {}
        if p["cargo"] == "GERENTE":
            return p
        visto.add(p["cod_protheus"])
        atual = p["cod_protheus"]
    return {}


def nome_gerente(cfg: dict, cod_vendedor: str) -> str:
    return gerente_de(cfg, cod_vendedor).get("nome", "")


def codigo_supervisor(cfg: dict, cod_vendedor: str):
    """Codigo do supervisor EM NUMERO, para o PLANNER."""
    cod = chefe_de(cfg, cod_vendedor).get("cod_protheus", "")
    try:
        return int(cod)
    except (TypeError, ValueError):
        return None


def codigo_excel(cod):
    """
    Como o codigo vai para a planilha. A regra do Alexandre: o que foi
    digitado no cadastro e o que sai.
        "000015" -> texto "000015"  (o zero da frente e do codigo)
        "8"      -> numero 8        (sem zero, vai como numero mesmo)
        ""       -> vazio
    """
    c = texto(cod)
    if not c:
        return None
    if c.isdigit() and not c.startswith("0"):
        return int(c)
    return c


def rotulo_pessoa(p: dict) -> str:
    return f"{p.get('cod_protheus','')} - {p.get('nome','')}".strip(" -")


def config_nova(mes: str = None) -> dict:
    hoje = dt.date.today()
    if not mes:
        mes = f"{hoje.year:04d}-{hoje.month:02d}"
    base = {
        "versao": VERSAO,
        "mes": mes,
        "feriados": [],
        "parametros": dict(PARAMETROS_PADRAO),
        "pessoas": [],
        # O planner abre VAZIO. As zonas sao cadastradas na aba 3 ou
        # vem prontas ao importar um PLANNER.
        "zonas": [],
        "areas": {},
        # excecoes por CLIENTE, feitas na aba 4: {chave: {zona, vendedor}}.
        # Elas valem mais que a zona do bairro e mais que o vendedor da zona.
        "excecoes": {},
    }
    base = _com_codigos(base)
    return base


def _com_codigos(cfg: dict) -> dict:
    atribuir_codigos(cfg)
    normalizar_pessoas(cfg)
    for z in cfg["zonas"]:
        z.setdefault("visitas_por_dia", 0)
        # As zonas nao guardam mais chave de sabado: o ultimo sabado do mes
        # e sempre trabalhado (regra fixa) e o deposito e o parametro da
        # aba 5. "usar_sabado" nao existe mais em lugar nenhum.
        z.pop("usar_sabado", None)
        if z.get("excedentes_no_sabado") is False:
            z.pop("excedentes_no_sabado", None)
    normalizar_atendimento(cfg)
    return cfg


# E-MAIL DE CADA COLABORADOR (o Farol de Metas manda a parcial para ele).
# Pre-cadastro de out/2026: quem ainda nao tem e-mail recebe o daqui,
# casado pelo nome (primeiro nome + um sobrenome do e-mail; sem o
# sobrenome no nome, so o primeiro nome se ele for unico). O que estiver
# gravado na pessoa sempre manda.
EMAILS_PADRAO = (
    "denylson.costa@bapautoparts.com.br",
    "lais.maciel@bapautoparts.com.br",
    "francisco.conceicao@bapautoparts.com.br",
    "alexandre.guerreiro@bapautoparts.com.br",
    "jocimar.guimaraes@bapautoparts.com.br",
    "paulo.filho@bapautoparts.com.br",
    "fayga.souza@bapautoparts.com.br",
    "rodrigo.lopes@bapautoparts.com.br",
    "edson.nascimento@bapautoparts.com.br",
    "thiago.gomes@bapautoparts.com.br",
    "paulo.ubiratan@bapautoparts.com.br",
    "anderson.silva@bapautoparts.com.br",
    "leandro.silva@bapautoparts.com.br",
)
EMAIL_VALIDO = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def email_valido(email) -> bool:
    return bool(EMAIL_VALIDO.match(texto(email).strip()))


def _pessoa_do_email(pessoas, email):
    """A pessoa de 'nome.sobrenome@...' (ou None se nao der para saber)."""
    local = email.split("@")[0].lower()
    partes = [norm(x) for x in re.split(r"[._-]", local) if x]
    if not partes:
        return None

    def tokens(p):
        return norm(p.get("nome")).split()
    primeiro = [p for p in pessoas if tokens(p)[:1] == partes[:1]]
    com_sobrenome = [p for p in primeiro
                     if any(x in tokens(p)[1:] for x in partes[1:])]
    if len(com_sobrenome) == 1:
        return com_sobrenome[0]
    # so pelo primeiro nome quando NENHUM outro e-mail da lista tem o mesmo
    # primeiro nome (paulo.filho nao pode cair no Paulo Ubiratan so porque
    # o Paulo Augusto ainda nao estava no cadastro daquele mes)
    xara = sum(1 for e in EMAILS_PADRAO
               if re.split(r"[._-]", e.split("@")[0].lower())[0] ==
               local.split(".")[0])
    if not com_sobrenome and len(primeiro) == 1 and xara == 1:
        return primeiro[0]
    return None


def preencher_emails(cfg) -> int:
    """Poe o e-mail do pre-cadastro em quem ainda nao tem. Devolve quantos.
    Roda ate o Planner gravar uma vez (marca emails_preenchidos): depois
    disso, e-mail apagado na tela continua apagado."""
    if cfg.get("emails_preenchidos"):
        return 0
    cfg["emails_preenchidos"] = True
    pessoas = cfg.get("pessoas") or []
    n = 0
    for email in EMAILS_PADRAO:
        if any(texto(p.get("email")).lower() == email for p in pessoas):
            continue
        p = _pessoa_do_email(pessoas, email)
        if p is not None and not texto(p.get("email")):
            p["email"] = email
            n += 1
    return n


def propagar_email(raiz, cod, email, codigos_antigos=()) -> int:
    """
    O E-MAIL E DA PESSOA, NAO DO MES: gravou no cadastro (em qualquer mes),
    vale no planner_config.json da pasta e em todos os meses do
    PLANNER_MESES - e o Farol de Metas ja envia para o novo, sem Recalcular
    Planner. Mexe so no campo email daquela pessoa. Devolve quantos
    arquivos mudaram.
    """
    raiz = Path(raiz)
    arquivos = [raiz / "planner_config.json"] + sorted(
        (raiz / "SISTEMA BAP" / "PLANNER_MESES").glob("planner_config_*.json"))
    alvo = {texto(cod)} | {texto(c) for c in codigos_antigos if c}
    mudou = 0
    for arq in arquivos:
        if not arq.exists():
            continue
        try:
            with open(arq, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            continue
        trocou = False
        for p in cfg.get("pessoas") or []:
            if texto(p.get("cod_protheus")) in alvo and \
                    texto(p.get("email")) != texto(email):
                p["email"] = texto(email)
                trocou = True
        if trocou:
            tmp = arq.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            tmp.replace(arq)
            mudou += 1
    return mudou


def carregar_config(caminho) -> dict:
    caminho = Path(caminho)
    if not caminho.exists():
        return config_nova()
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    base = config_nova(cfg.get("mes"))
    for chave, valor in base.items():
        cfg.setdefault(chave, valor)
    p = dict(PARAMETROS_PADRAO)
    p.update(cfg.get("parametros") or {})
    # chaves que deixaram de existir e saem do arquivo para nao dar a
    # impressao de que ainda mandam: a frequencia virou automatica (vem da
    # curva) e o "usar sabado" virou regra fixa (o ULTIMO sabado do mes e
    # sempre trabalhado)
    for morta in ("frequencia", "quinzenal_comprante", "usar_sabado"):
        p.pop(morta, None)
    cfg["parametros"] = p
    atribuir_codigos(cfg)
    normalizar_pessoas(cfg)
    for z in cfg["zonas"]:
        z.setdefault("visitas_por_dia", 0)
        # As zonas nao guardam mais chave de sabado: o ultimo sabado do mes
        # e sempre trabalhado (regra fixa) e o deposito e o parametro da
        # aba 5. "usar_sabado" nao existe mais em lugar nenhum.
        z.pop("usar_sabado", None)
        if z.get("excedentes_no_sabado") is False:
            z.pop("excedentes_no_sabado", None)
    normalizar_atendimento(cfg)
    preencher_emails(cfg)
    emails_de_outros_meses(cfg, caminho)
    return cfg


def emails_de_outros_meses(cfg, caminho) -> int:
    """Quem esta sem e-mail neste arquivo pega o da mesma pessoa (mesmo
    codigo Protheus) no planner_config.json da pasta ou em outro mes: o
    e-mail e do colaborador, nao do mes. Devolve quantos preencheu."""
    caminho = Path(caminho)
    raiz = caminho.parent.parent.parent if caminho.parent.name == "PLANNER_MESES" \
        else caminho.parent
    faltam = [p for p in cfg.get("pessoas") or [] if not texto(p.get("email"))]
    if not faltam:
        return 0
    conhecidos = {}
    arquivos = [raiz / "planner_config.json"] + sorted(
        (raiz / "SISTEMA BAP" / "PLANNER_MESES").glob("planner_config_*.json"), reverse=True)
    for arq in arquivos:
        if not arq.exists() or arq.resolve() == caminho.resolve():
            continue
        try:
            with open(arq, encoding="utf-8") as f:
                outro = json.load(f)
        except (OSError, ValueError):
            continue
        for p in outro.get("pessoas") or []:
            cod, email = texto(p.get("cod_protheus")), texto(p.get("email"))
            if cod and email and cod not in conhecidos:
                conhecidos[cod] = email.strip().lower()
    n = 0
    for p in faltam:
        email = conhecidos.get(texto(p.get("cod_protheus")))
        if email:
            p["email"] = email
            n += 1
    return n


def gravar_config(cfg: dict, caminho):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp.replace(caminho)


# ==========================================================================
# leitura da BASE_CLIENTE
# ==========================================================================
COLUNAS_BASE = {
    "COD_CLIENTE": ["COD_CLIENTE", "CODIGO DO CLIENTE", "CODIGO_CLIENTE", "A1_COD"],
    "LOJA": ["LOJA", "A1_LOJA"],
    "NOME_CLIENTE": ["NOME_CLIENTE", "NOME DO CLIENTE", "A1_NOME", "RAZAO SOCIAL"],
    "NOME_FANTASIA": ["NOME_FANTASIA", "NOME FANTASIA", "A1_NREDUZ",
                      "A1_NOMREDUZ", "FANTASIA"],
    "UF": ["UF", "A1_EST", "ESTADO"],
    "CIDADE": ["CIDADE", "A1_MUN", "MUNICIPIO"],
    "BAIRRO": ["BAIRRO", "A1_BAIRRO"],
    "ENDERECO": ["ENDERECO", "ENDEREÇO", "A1_END"],
    "NUMERO": ["NUMERO", "NÚMERO", "NUMERO_ENDERECO"],
    "LIMITE_DISPONIVEL": ["LIMITE_DISPONIVEL", "LIMITE DISPONIVEL",
                          "LIMITE DISPONÍVEL", "SALDO DISPONIVEL"],
    "LIMITE_APROVADO": ["LIMITE_APROVADO", "LIMITE APROVADO", "LIMITE"],
    "VALOR_EM_ATRASO": ["VALOR_EM_ATRASO", "VALOR EM ATRASO", "VALOR  EM ATRASO"],
    "DIAS_ATRASO": ["DIAS_ATRASO", "DIAS EM ATRASO"],
    "CURVA_RECEITA": ["CURVA_RECEITA", "CURVA DE RECEITA", "CURVA"],
    "RECEITA_PERIODO": ["RECEITA_PERIODO", "RECEITA 3M", "RECEITA_3M"],
    "RECEITA_6M": ["RECEITA_6M", "RECEITA 6M", "FAT_6M", "FAT 6M"],
    "RECEITA_ACUMULADA": ["RECEITA_ACUMULADA", "RECEITA ACUMULADA",
                          "FAT_ACUMULADO"],
    "MEDIA_MENSAL": ["MEDIA_MENSAL", "MEDIA MENSAL", "MÉDIA MENSAL",
                     "FAT_M3M", "FAT M3M"],
    "MEDIA_MENSAL_6M": ["MEDIA_MENSAL_6M", "MEDIA MENSAL 6M", "FAT_M6M",
                        "FAT M6M"],
    "RECEITA_PERIODO_ANTERIOR": ["RECEITA_PERIODO_ANTERIOR",
                                 "RECEITA PERIODO ANTERIOR"],
    "MEDIA_MENSAL_ANTERIOR": ["MEDIA_MENSAL_ANTERIOR", "MEDIA MENSAL ANTERIOR",
                              "FAT_M3M_ANTERIOR", "FAT M3M ANTERIOR"],
    "STATUS_CLIENTE": ["STATUS_CLIENTE", "STATUS DO CLIENTE", "STATUS"],
    # (10/11) o ATIVO/INATIVO do cadastro do Protheus (BASE_CLIENTE)
    "STATUS_PROTHEUS": ["STATUS_PROTHEUS", "STATUS PROTHEUS"],
    "DIAS_SEM_COMPRA": ["DIAS_SEM_COMPRA", "DIAS SEM COMPRA"],
    "ULTIMA_COMPRA": ["ULTIMA_COMPRA", "ULTIMA COMPRA", "ÚLTIMA COMPRA"],
    "COD_ULTIMO_VENDEDOR": ["COD_ULTIMO_VENDEDOR", "CODIGO DO ULTIMO VENDEDOR",
                            "ULTIMO VENDEDOR", "COD_VENDEDOR"],
    "CONTATO": ["CONTATO", "A1_CONTATO"],
    "DDD": ["DDD", "A1_DDD"],
    "LATITUDE": ["LATITUDE", "LAT"],
    "LONGITUDE": ["LONGITUDE", "LON", "LNG"],
    "TELEFONE": ["TELEFONE", "A1_TEL", "FONE"],
    "SEGMENTO": ["SEGMENTO"],
    "SUBSEGMENTO": ["SUBSEGMENTO"],
}


def _mapear_colunas(cabecalho):
    achou = {}
    limpo = {norm(c): i for i, c in enumerate(cabecalho) if c}
    for destino, apelidos in COLUNAS_BASE.items():
        for a in apelidos:
            if norm(a) in limpo:
                achou[destino] = limpo[norm(a)]
                break
    return achou


# --------------------------------------------------------------------------
# O CACHE DA BASE_CLIENTE
# --------------------------------------------------------------------------
# Abrir a BASE_CLIENTE.xlsx custa ~0,9 s para 4,4 mil clientes - e o unico
# lugar do PLANNER onde o tempo se sente, e ele e pago em TODA abertura e em
# todo recarregamento. O openpyxl gasta esse tempo montando um objeto por
# celula; nao ha como pedir menos.
#
# Entao a leitura fica guardada num arquivo compacto, ao lado do temporario
# do Windows (NAO na pasta do OneDrive, para nao sincronizar lixo). A chave
# e o tamanho + a data do .xlsx: mudou a planilha, o cache e ignorado e
# refeito. Ele nunca e a fonte da verdade - se der qualquer problema para
# ler, o programa le o Excel como sempre fez.
PASTA_CACHE = Path(tempfile.gettempdir()) / "BAP_TOOLS_cache"
VERSAO_CACHE = 9          # sobe quando o formato do dicionario do cliente muda
#                           (8 = 03/11: COMPRA_BATERIA, do HIST_DETALHADO)


def _so_digitos(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", texto(v))


def telefone_de(ddd, tel) -> str:
    """O telefone da base num formato so: (92) 98187-5642. O DDD perde o
    zero da frente; o numero que ja traz o DDD nao o repete; numero de
    mentira (9999999, 0000000) fica vazio."""
    d, t = _so_digitos(ddd).lstrip("0"), _so_digitos(tel)
    if not t or len(set(t)) == 1 or len(t) < 7:
        return ""
    if len(t) in (10, 11) and (not d or t.startswith(d)):
        d, t = t[:2], t[2:]
    if len(d) == 3:                     # "929" + 95350640: o 9 do celular
        d, t = d[:2], (d[2] + t if len(t) == 8 else t)
    if len(t) == 9:
        t = f"{t[:5]}-{t[5:]}"
    elif len(t) == 8:
        t = f"{t[:4]}-{t[4:]}"
    return f"({d[-2:]}) {t}" if d else t


def contato_do_cliente(c: dict) -> str:
    """CONTATO (TELEFONE) para a rota e os farois: o nome do contato e o
    telefone da base, sem repetir o que for igual."""
    nome = texto(c.get("CONTATO") or c.get("contato"))
    tel = texto(c.get("TELEFONE") or c.get("telefone"))
    if nome and tel and _so_digitos(nome) and \
            _so_digitos(nome)[-8:] == _so_digitos(tel)[-8:]:
        nome = ""                       # o contato e o proprio telefone
    return " · ".join(x for x in (nome, tel) if x)


def _arquivo_de_cache(caminho: Path) -> Path:
    marca = f"{caminho.resolve()}|{VERSAO_CACHE}"
    nome = hashlib.md5(marca.encode("utf-8")).hexdigest()[:16]
    return PASTA_CACHE / f"base_{nome}.json.gz"


def _assinatura(caminho: Path) -> str:
    st = caminho.stat()
    return f"{st.st_size}|{int(st.st_mtime)}|{VERSAO_CACHE}"


def _ler_do_cache(caminho: Path):
    arq = _arquivo_de_cache(caminho)
    if not arq.exists():
        return None
    try:
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            dados = json.load(f)
        if dados.get("assinatura") != _assinatura(caminho):
            return None
        for c in dados["clientes"]:
            if c["ULTIMA_COMPRA"]:
                c["ULTIMA_COMPRA"] = dt.date.fromisoformat(c["ULTIMA_COMPRA"])
        return dados["clientes"]
    except (OSError, EOFError, ValueError, KeyError):
        # EOFError e o cache PELA METADE: o programa foi fechado (ou o
        # micro dormiu) no meio da gravacao e o .gz ficou truncado. Sem
        # ele nesta lista, o erro subia ate a tela como "Compressed file
        # ended before the end-of-stream marker was reached" toda vez que
        # a base era lida, e so apagando um arquivo temporario que
        # ninguem sabe que existe. Cache e conforto: quando esta ruim,
        # le-se o Excel e pronto.
        try:
            arq.unlink()          # o pedaco ruim nao volta a atrapalhar
        except OSError:
            pass
        return None


def _gravar_no_cache(caminho: Path, clientes: list) -> None:
    try:
        PASTA_CACHE.mkdir(parents=True, exist_ok=True)
        magros = [{**c, "ULTIMA_COMPRA": c["ULTIMA_COMPRA"].isoformat()
                   if c["ULTIMA_COMPRA"] else None} for c in clientes]
        with gzip.open(_arquivo_de_cache(caminho), "wt", encoding="utf-8") as f:
            json.dump({"assinatura": _assinatura(caminho),
                       "clientes": magros}, f, ensure_ascii=False)
    except (OSError, TypeError, ValueError):
        pass                      # cache e conforto, nunca obrigacao


def _coordenadas_dos_clientes(clientes, caminho) -> None:
    """LATITUDE/LONGITUDE do COORDENADAS_CLIENTES.json (ao lado da base),
    para o Planner ja usar o que foi geocodificado depois da BASE_CLIENTE
    ser gerada (botao Atualizar coordenadas)."""
    try:
        import geocodificar                             # noqa: PLC0415
        arq = geocodificar.caminho(caminho)
        if arq.exists():
            geocodificar.completar(clientes, arq)
    except Exception:                                   # noqa: BLE001
        pass                    # sem o arquivo: centro do bairro
    # (15/10) quem ainda nao tem ponto: o endereco mais proximo (vizinho da
    # mesma rua / clientes do bairro), so para roteirizar
    try:
        geo.aproximar_pontos(clientes)
    except Exception:                                   # noqa: BLE001
        pass


def ler_base_cliente(caminho, usar_cache: bool = True) -> list[dict]:
    """
    Le a BASE_CLIENTE.xlsx gerada pelo BAP Tools.

    Quando a planilha nao mudou desde a ultima leitura, vem do cache (ver
    acima) - de ~0,9 s para ~0,1 s. `usar_cache=False` forca a leitura do
    Excel, e e o que os testes usam.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"BASE_CLIENTE nao encontrada: {caminho}")
    if usar_cache:
        guardados = _ler_do_cache(caminho)
        if guardados is not None:
            _coordenadas_dos_clientes(guardados, caminho)
            return guardados
    wb = load_workbook(caminho, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    cab = list(next(it))
    col = _mapear_colunas(cab)
    if "COD_CLIENTE" not in col:
        wb.close()
        raise ValueError("A BASE_CLIENTE nao tem a coluna do codigo do cliente.")

    def pega(linha, nome, padrao=None):
        i = col.get(nome)
        return linha[i] if i is not None and i < len(linha) else padrao

    clientes = []
    for r in it:
        cod = texto(pega(r, "COD_CLIENTE"))
        if not cod:
            continue
        uf = norm(pega(r, "UF"))
        cidade = norm(pega(r, "CIDADE"))
        bairro = texto(pega(r, "BAIRRO"))
        bairro_limpo = zp.normalizar(bairro) or "(SEM BAIRRO)"
        chave = chave_de_area(uf, cidade, bairro_limpo)
        rotulo = f"{uf} / {cidade} / {bairro_limpo}"
        loja = texto(pega(r, "LOJA"))
        clientes.append({
            # a mesma rede aparece com varias lojas, cada uma num endereco
            # diferente - a visita e por loja, nao por codigo
            "CHAVE_CLIENTE": f"{cod.zfill(6)}-{loja or '00'}",
            "COD_CLIENTE": cod.zfill(6),
            "LOJA": loja,
            "NOME_CLIENTE": texto(pega(r, "NOME_CLIENTE")),
            "NOME_FANTASIA": texto(pega(r, "NOME_FANTASIA")),
            "UF": uf,
            "CIDADE": cidade,
            "BAIRRO": bairro_limpo,
            "ENDERECO": texto(pega(r, "ENDERECO")),
            "NUMERO": texto(pega(r, "NUMERO")),
            "CONTATO": texto(pega(r, "CONTATO")),
            # o telefone da BASE_CLIENTE (DDD + TELEFONE): (92) 3237-3321
            "TELEFONE": telefone_de(pega(r, "DDD"), pega(r, "TELEFONE")),
            # (06/10) o ponto do endereco no mapa (geocodificar.py)
            "LATITUDE": pega(r, "LATITUDE"),
            "LONGITUDE": pega(r, "LONGITUDE"),
            "LIMITE_DISPONIVEL": numero(pega(r, "LIMITE_DISPONIVEL")),
            "LIMITE_APROVADO": numero(pega(r, "LIMITE_APROVADO")),
            "VALOR_EM_ATRASO": numero(pega(r, "VALOR_EM_ATRASO")),
            "DIAS_ATRASO": numero(pega(r, "DIAS_ATRASO")),
            "CURVA_RECEITA": (texto(pega(r, "CURVA_RECEITA")) or "Z").upper()[-1],
            # SOMA da janela
            "RECEITA_PERIODO": numero(pega(r, "RECEITA_PERIODO")),
            "RECEITA_6M": numero(pega(r, "RECEITA_6M",
                                     pega(r, "RECEITA_PERIODO"))),
            # MEDIA MENSAL - e SO ISTO que pode se chamar M3M e M6M.
            # Base antiga, sem a coluna da media, tem a media calculada
            # aqui a partir da soma e da janela da aba 6.
            "MEDIA_MENSAL": numero(pega(r, "MEDIA_MENSAL")),
            "MEDIA_MENSAL_6M": numero(pega(r, "MEDIA_MENSAL_6M")),
            # a janela ANTERIOR: e a comparacao dela com a atual que diz
            # se o cliente esta crescendo ou caindo
            "RECEITA_PERIODO_ANTERIOR": numero(
                pega(r, "RECEITA_PERIODO_ANTERIOR")),
            "MEDIA_MENSAL_ANTERIOR": numero(pega(r, "MEDIA_MENSAL_ANTERIOR")),
            "RECEITA_ACUMULADA": numero(pega(r, "RECEITA_ACUMULADA")),
            "STATUS_CLIENTE": (texto(pega(r, "STATUS_CLIENTE")) or "NUNCA COMPROU").upper(),
            # (10/11) INATIVO no Protheus: sai da rota (base antiga, sem a
            # coluna, = ATIVO)
            "STATUS_PROTHEUS": (texto(pega(r, "STATUS_PROTHEUS"))
                                or "ATIVO").upper(),
            # um dos 8 segmentos (vazio so em base antiga, sem a coluna)
            "SEGMENTO": texto(pega(r, "SEGMENTO")).upper(),
            "SUBSEGMENTO": texto(pega(r, "SUBSEGMENTO")).upper(),
            "DIAS_SEM_COMPRA": pega(r, "DIAS_SEM_COMPRA"),
            "ULTIMA_COMPRA": data_de(pega(r, "ULTIMA_COMPRA")),
            "COD_ULTIMO_VENDEDOR": texto(pega(r, "COD_ULTIMO_VENDEDOR")),
            "AREA": chave,
            "AREA_ROTULO": rotulo,
        })
    # (03/11) DIA FOCO: quem comprou BATERIA (aba HIST_DETALHADO da base)
    bat = _compradores_de_bateria(wb)
    for c in clientes:
        c["COMPRA_BATERIA"] = "SIM" if c["COD_CLIENTE"] in bat else ""
    wb.close()
    _coordenadas_dos_clientes(clientes, caminho)
    if usar_cache:
        _gravar_no_cache(caminho, clientes)
    return clientes


def _compradores_de_bateria(wb) -> set:
    """(03/11) Os codigos de cliente (6 digitos) com nota de BATERIA na
    aba HIST_DETALHADO da BASE_CLIENTE (o historico que o BAP Tools grava).
    Sem a aba: vazio (o foco fica so pelo segmento)."""
    if "HIST_DETALHADO" not in wb.sheetnames:
        return set()
    try:
        it = wb["HIST_DETALHADO"].iter_rows(values_only=True)
        cab = [norm(x) for x in next(it)]
        i_c, i_d = cab.index("COD CLIENTE"), cab.index("DESCRICAO PRODUTO")
    except (StopIteration, ValueError):
        return set()
    saida = set()
    for r in it:
        if len(r) > max(i_c, i_d) and norm(r[i_d]).startswith("BATERIA"):
            cod = texto(r[i_c])
            if cod:
                saida.add(cod.zfill(6))
    return saida


def chave_de_area(uf, cidade, bairro) -> str:
    """A menor unidade de roteirizacao: UF | CIDADE | BAIRRO."""
    return f"{norm(uf)}|{norm(cidade)}|{norm(bairro) or '(SEM BAIRRO)'}"


def migrar_areas_antigas(cfg: dict, clientes: list[dict]) -> int:
    """
    A lotacao antiga era por CIDADE ("PA|CASTANHAL"); a de agora e por
    BAIRRO ("PA|CASTANHAL|CENTRO"). Quem ja tinha zona cadastrada nao pode
    perder o trabalho: cada chave antiga vira a chave de TODOS os bairros
    daquela cidade. Bairro que ja tem dono proprio nao e mexido.
    Devolve quantas chaves antigas foram convertidas.
    """
    antigas = [c for c in cfg.get("areas", {}) if c.count("|") == 1]
    if not antigas:
        return 0
    por_cidade = defaultdict(list)
    for c in clientes:
        uf, _, resto = c["AREA"].partition("|")
        cidade = resto.split("|")[0]
        por_cidade[f"{uf}|{cidade}"].append(c["AREA"])
    for chave in antigas:
        zona = cfg["areas"].pop(chave)
        for nova in por_cidade.get(chave, []):
            cfg["areas"].setdefault(nova, zona)
    return len(antigas)


def sincronizar_areas(cfg: dict, clientes: list[dict]) -> int:
    """
    Conta quantas areas da base ainda nao pertencem a zona nenhuma.
    Nao inventa zona para ninguem: quem manda e o cadastro da aba 3.
    """
    return len({c["AREA"] for c in clientes if not cfg["areas"].get(c["AREA"])})


# --------------------------------------------------------------------------
# CLIENTE INATIVO (06/10): inativado a mao na aba Base cliente do Planner.
# Sai da rota (o Planner e refeito sem ele). (20/10, Alexandre) No .json da
# base de clientes do Protheus TODO cliente vai ATIVO: o inativado vai com
# o VENDEDOR e o SUPERVISOR PADRAO (ninguem da equipe ve).
#     cfg["clientes_inativos"] = {CHAVE_CLIENTE: {"em": "2026-10-06"}}
# --------------------------------------------------------------------------
def clientes_inativos(cfg: dict) -> dict:
    return cfg.get("clientes_inativos") or {}


def inativo_no_protheus(cliente) -> bool:
    """(10/11, Alexandre) o cliente INATIVO no cadastro do Protheus
    (STATUS_PROTHEUS da BASE_CLIENTE = A1_MSBLQL bloqueado)."""
    return not isinstance(cliente, str) and \
        texto(cliente.get("STATUS_PROTHEUS")).upper() == "INATIVO"


def cliente_inativo(cfg: dict, cliente) -> bool:
    """INATIVO = inativado a mao na aba Base cliente OU (10/11) inativo no
    Protheus: nos dois casos sai da rota do vendedor."""
    if inativo_no_protheus(cliente):
        return True
    chave = cliente if isinstance(cliente, str) else \
        cliente.get("CHAVE_CLIENTE")
    return chave in clientes_inativos(cfg)


def inativar_clientes(cfg: dict, chaves, inativo=True, quando=None) -> int:
    """Inativa (ou reativa) os clientes. Devolve quantos mudaram."""
    todos = cfg.setdefault("clientes_inativos", {})
    quando = (quando or dt.date.today()).isoformat()
    n = 0
    for ch in chaves:
        if inativo and ch not in todos:
            todos[ch] = {"em": quando}
            n += 1
        elif not inativo and ch in todos:
            todos.pop(ch)
            n += 1
    if not todos:
        cfg.pop("clientes_inativos", None)
    return n


def excecao_do_cliente(cfg: dict, cliente: dict) -> dict:
    return (cfg.get("excecoes") or {}).get(cliente["CHAVE_CLIENTE"]) or {}


# --------------------------------------------------------------------------
# A ZONA VIRTUAL DO ESTADO - onde nenhum cliente se perde
# --------------------------------------------------------------------------
# Todo bairro que ainda nao foi posto em nenhuma zona cai na zona virtual
# da UF dele: Z-AM-100, Z-PA-100, Z-RR-100... Assim o cliente continua na
# base, aparece no resumo, no PLANNER e na meta - so nao entra em rota,
# porque a zona virtual nao tem vendedor. E um estacionamento, nao um
# sumidouro: a lista de zonas mostra quantos estao la esperando.
SUFIXO_SEM_ZONA = "100"


def id_da_zona_virtual(uf: str) -> str:
    return f"Z-{(uf or 'XX').strip().upper()}-{SUFIXO_SEM_ZONA}"


def e_zona_virtual(zona) -> bool:
    """A zona virtual e a que termina em -100 - ninguem a cadastra a mao."""
    cod = zona.get("codigo", "") if isinstance(zona, dict) else str(zona or "")
    return cod.endswith(f"-{SUFIXO_SEM_ZONA}")


def zonas_virtuais(cfg: dict, clientes: list) -> list:
    """
    As zonas virtuais que fazem sentido AGORA: uma por UF que ainda tem
    bairro sem dono. Elas NAO sao gravadas no cadastro - sao montadas na
    hora, so para o cliente orfao ficar visivel e contado. Some sozinha
    quando o ultimo bairro daquela UF ganha zona.
    """
    orfaos = defaultdict(int)
    for c in clientes:
        if not cfg["areas"].get(c["AREA"]):
            orfaos[(c.get("UF") or "XX").strip().upper()] += 1
    return [{"id": id_da_zona_virtual(uf), "codigo": id_da_zona_virtual(uf),
             "nome": f"{uf} - SEM ZONA (bairros ainda sem dono)",
             "uf": uf, "vendedor": "", "visitas_por_dia": 0,
             "frequencia": 0, "virtual": True, "clientes": quantos}
            for uf, quantos in sorted(orfaos.items())]


def zona_do_cliente(cfg: dict, cliente: dict) -> str:
    """
    A zona do cliente. Vale primeiro a excecao feita no analitico; depois
    a zona do bairro dele; e, se ninguem o adotou, a ZONA VIRTUAL da UF
    dele (Z-UF-100), para que nenhum cliente fique fora da conta.
    """
    forcada = excecao_do_cliente(cfg, cliente).get("zona")
    if forcada:
        return forcada
    return cfg["areas"].get(cliente["AREA"], "")


def zona_para_mostrar(cfg: dict, cliente: dict) -> str:
    """
    A zona do cliente PARA APARECER nos quadros - resumo, PLANNER, meta.

    E a mesma de zona_do_cliente(), com uma diferenca: quem ainda nao foi
    adotado por zona nenhuma nao vira "(SEM ZONA)", vira a ZONA VIRTUAL da
    UF dele - Z-AM-100, Z-PA-100... Ele fica estacionado ali, visivel e
    contado, ate alguem por o bairro dele numa zona de verdade.

    A ROTA nao usa esta funcao: zona virtual nao tem vendedor e nao
    roteiriza ninguem. Ela e um estacionamento, nao uma zona.
    """
    return (zona_do_cliente(cfg, cliente)
            or id_da_zona_virtual(cliente.get("UF") or "XX"))


def bairros_sem_zona(cfg: dict, clientes: list) -> list:
    """Os trios (uf, cidade, bairro) que ainda nao estao em zona nenhuma."""
    fora = {}
    for c in clientes:
        if not cfg["areas"].get(c["AREA"]):
            fora[(c["UF"], c["CIDADE"], c["BAIRRO"])] = 1
    return sorted(fora)


def sugerir_zonas(cfg: dict, clientes: list, limite_km: float = 8.0) -> dict:
    """
    Para cada bairro SEM ZONA, propoe a zona de um bairro que ja tem dono:

      1) O IRMAO - o bairro da mesma cidade com o mesmo nome canonico.
         "CIDADE NOVA 1", "CIDADE NOVA I" e "CJ CIDADE NOVA II" sao o
         mesmo lugar que "CIDADE NOVA": herdam a zona dela.
      2) O VIZINHO - nao havendo irmao, o bairro da mesma cidade que fica
         MAIS PERTO pela coordenada, ate `limite_km` quilometros.

    Devolve {chave_da_area: (zona_id, por_que)}. Nao muda nada sozinho:
    quem aplica e o botao da tela.
    """
    donos = cfg.get("areas") or {}
    com_zona = []
    zona_do_trio = {}
    for c in clientes:
        zid = donos.get(c["AREA"])
        if zid:
            trio = (c["UF"], c["CIDADE"], c["BAIRRO"])
            if trio not in zona_do_trio:
                zona_do_trio[trio] = zid
                com_zona.append(trio)

    sugestao = {}
    for uf, cidade, bairro in bairros_sem_zona(cfg, clientes):
        chave = chave_de_area(uf, cidade, bairro)
        irmaos = geo.irmaos_do_bairro(uf, cidade, bairro, com_zona)
        if irmaos:
            votos = Counter(zona_do_trio[t] for t in irmaos)
            zid, _ = votos.most_common(1)[0]
            sugestao[chave] = (zid, f"mesmo bairro que "
                                    f"{irmaos[0][2]} (nome igual)")
            continue
        perto, km = geo.bairro_mais_perto(uf, cidade, bairro, com_zona)
        if perto and km is not None and km <= limite_km:
            sugestao[chave] = (zona_do_trio[perto],
                               f"vizinho de {perto[2]} ({km:.1f} km)")
    return sugestao


def aplicar_sugestoes(cfg: dict, sugestao: dict) -> int:
    """Poe de pe o que sugerir_zonas() propos. Devolve quantos entraram."""
    n = 0
    for chave, (zid, _) in sugestao.items():
        if not cfg["areas"].get(chave):
            cfg["areas"][chave] = zid
            n += 1
    return n


# --------------------------------------------------------------------------
# QUEM ATENDE A ZONA: vendedor + SEGMENTOS
# --------------------------------------------------------------------------
# A zona pode ter MAIS DE UM vendedor, cada um com os seus segmentos:
#     zona["atendimento"] = [{"vendedor": "000015", "segmentos": ["AUTOPEÇAS"]},
#                            {"vendedor": "000021", "segmentos": []}]
# "segmentos" vazio = TODOS os segmentos que ninguem mais pegou na zona.
# A regra: o mesmo segmento nao pode ter dois vendedores na mesma zona (e
# so um pode ficar com "todos").
# zona["vendedor"] continua existindo: e o TITULAR (quem tem "todos", ou o
# primeiro) - e o que as telas antigas e o resumo por zona mostram.
def _seg_norm(s) -> str:
    return norm(s)


def atendimento_da_zona(z: dict) -> list:
    at = z.get("atendimento")
    if not isinstance(at, list):
        v = texto(z.get("vendedor"))
        at = [{"vendedor": v, "segmentos": []}] if v else []
        z["atendimento"] = at
    return at


def _sincronizar_titular(z: dict) -> None:
    at = [{"vendedor": texto(a.get("vendedor")),
           "segmentos": [s for s in (a.get("segmentos") or []) if s]}
          for a in atendimento_da_zona(z) if texto(a.get("vendedor"))]
    z["atendimento"] = at
    titular = next((a for a in at if not a["segmentos"]), at[0] if at else None)
    z["vendedor"] = titular["vendedor"] if titular else ""


def normalizar_atendimento(cfg: dict) -> None:
    for z in cfg.get("zonas") or []:
        _sincronizar_titular(z)


def vendedores_da_zona(z: dict) -> list:
    return [a["vendedor"] for a in atendimento_da_zona(z) if a.get("vendedor")]


def zonas_da_equipe(cfg: dict, cod_supervisor: str) -> set:
    """Ids das zonas dos vendedores ATIVOS do supervisor - por padrao sao
    as zonas dele (as cadastradas na ficha dele somam a estas)."""
    cod = texto(cod_supervisor)
    if not cod:
        return set()
    equipe = {p["cod_protheus"] for p in cfg.get("pessoas") or []
              if p.get("cargo") == "VENDEDOR" and p.get("ativo") is not False
              and texto(p.get("responde_a")) == cod}
    return {z["id"] for z in cfg.get("zonas") or []
            if equipe & set(vendedores_da_zona(z))}


def supervisor_da_zona(cfg: dict, zona_id, exceto: str = "") -> dict:
    """(08/10) A zona tem UM supervisor so: o supervisor ATIVO (menos o
    `exceto`) que ja tem a zona - pela equipe (vendedor dele atende a
    zona) ou cadastrada na ficha dele. {} se nenhum."""
    for p in cfg.get("pessoas") or []:
        if p.get("cargo") != "SUPERVISOR" or p.get("ativo") is False:
            continue
        cod = texto(p.get("cod_protheus"))
        if not cod or cod == texto(exceto):
            continue
        if zona_id in zonas_da_equipe(cfg, cod) or zona_id in {
                texto(z) for z in p.get("zonas_supervisor") or []}:
            return p
    return {}


def conflitos_de_zona_supervisor(cfg: dict, cod: str, zona_ids) -> list:
    """As zonas que o supervisor `cod` quer e ja sao de outro supervisor:
    ["Z-MT-01 ... ja e de SUPERVISOR MT (VAGO)"]."""
    por_id = {z["id"]: z for z in cfg.get("zonas") or []}
    saida = []
    for zid in sorted(zona_ids, key=lambda i: (por_id.get(i) or {}).get(
            "codigo") or i):
        dono = supervisor_da_zona(cfg, zid, exceto=cod)
        if dono:
            z = por_id.get(zid) or {}
            saida.append(f"{z.get('codigo') or zid} {z.get('nome', '')} "
                         f"- já é de {texto(dono.get('nome'))}")
    return saida


def segmentos_na_zona(z: dict, cod: str):
    """Os segmentos do vendedor na zona ([] = todos); None se nao atende."""
    for a in atendimento_da_zona(z):
        if a.get("vendedor") == cod:
            return list(a.get("segmentos") or [])
    return None


def zonas_do_vendedor(cfg: dict, cod: str) -> list:
    return [z for z in cfg["zonas"] if cod and cod in vendedores_da_zona(z)]


def rotulo_segmentos(segmentos) -> str:
    return ", ".join(segmentos) if segmentos else "TODOS"


def vendedor_da_zona_para(z: dict, segmento: str) -> str:
    """Quem atende, nesta zona, o cliente deste segmento."""
    at = atendimento_da_zona(z)
    alvo = _seg_norm(segmento)
    for a in at:
        if a.get("segmentos") and alvo in {_seg_norm(s) for s in a["segmentos"]}:
            return a["vendedor"]
    for a in at:
        if not a.get("segmentos"):
            return a["vendedor"]
    return ""


def segmentos_sem_vendedor(z: dict) -> list:
    """Os segmentos que ninguem atende nesta zona (vazio se alguem tem TODOS)."""
    at = atendimento_da_zona(z)
    if not at or any(not a.get("segmentos") for a in at):
        return [] if at else list(SEGMENTOS)
    cobertos = {_seg_norm(s) for a in at for s in a["segmentos"]}
    return [s for s in SEGMENTOS if _seg_norm(s) not in cobertos]


def conflitos_de_atendimento(cfg: dict, cod: str, zona_ids, segmentos,
                             ignorar=()) -> list:
    """
    O que impede o vendedor `cod` de atender estas zonas com estes
    segmentos: outro vendedor ja tem o mesmo segmento na zona (ou os dois
    ficariam com TODOS). Lista vazia = pode gravar.
    """
    nomes = {p["cod_protheus"]: p.get("nome", "") for p in cfg.get("pessoas") or []}
    meus = {_seg_norm(s) for s in segmentos or []}
    msgs = []
    for z in cfg["zonas"]:
        if z["id"] not in set(zona_ids):
            continue
        for a in atendimento_da_zona(z):
            if a.get("vendedor") == cod or a.get("vendedor") in set(ignorar):
                continue
            outros = {_seg_norm(s) for s in a.get("segmentos") or []}
            quem = f"{a['vendedor']} {nomes.get(a['vendedor'], '')}".strip()
            if not meus and not outros:
                msgs.append(f"{z.get('codigo', z['id'])}: {quem} ja atende TODOS "
                            f"os segmentos - escolha os segmentos deste vendedor")
            elif meus & outros:
                comuns = [s for s in SEGMENTOS if _seg_norm(s) in meus & outros]
                msgs.append(f"{z.get('codigo', z['id'])}: {', '.join(comuns)} "
                            f"ja e de {quem}")
    return msgs


def definir_atendimento(cfg: dict, cod: str, zona_ids, segmentos) -> None:
    """O vendedor `cod` atende ESTAS zonas com ESTES segmentos (e sai das outras)."""
    zona_ids = set(zona_ids)
    segmentos = [s for s in SEGMENTOS if _seg_norm(s) in
                 {_seg_norm(x) for x in segmentos or []}]
    for z in cfg["zonas"]:
        at = [a for a in atendimento_da_zona(z) if a.get("vendedor") != cod]
        if z["id"] in zona_ids:
            at.append({"vendedor": cod, "segmentos": list(segmentos)})
        z["atendimento"] = at
        _sincronizar_titular(z)


def trocar_codigo_no_atendimento(cfg: dict, antigo: str, novo: str) -> None:
    for z in cfg["zonas"]:
        for a in atendimento_da_zona(z):
            if a.get("vendedor") == antigo:
                a["vendedor"] = novo
        _sincronizar_titular(z)


def tirar_vendedor_das_zonas(cfg: dict, cod: str) -> None:
    definir_atendimento(cfg, cod, set(), [])


def vendedor_do_cliente(cfg: dict, cliente: dict, zonas=None) -> str:
    """
    O vendedor do cliente: a excecao do analitico, se houver, senao quem
    atende o SEGMENTO dele na zona dele.
    """
    forcado = excecao_do_cliente(cfg, cliente).get("vendedor")
    if forcado:
        return forcado
    zid = zona_do_cliente(cfg, cliente)
    if not zid:
        return ""
    if zonas is None:
        zonas = {z["id"]: z for z in cfg["zonas"]}
    z = zonas.get(zid)
    if not z:
        return ""
    return vendedor_da_zona_para(z, cliente.get("SEGMENTO", ""))


def marcar_excecao(cfg: dict, chaves, zona=None, vendedor=None,
                   semana=None, dia=None) -> int:
    """
    Grava (ou apaga) a excecao de um ou varios clientes: a zona, o
    vendedor, a semana e o dia que voce marcou a mao no analitico.
    Valor "" apaga aquele campo; None nao mexe nele. Semana e dia sao
    excludentes - marcar um limpa o outro.
    Devolve quantos clientes ficaram com alguma excecao.
    """
    excecoes = cfg.setdefault("excecoes", {})
    for chave in chaves:
        reg = dict(excecoes.get(chave) or {})
        for campo, valor in (("zona", zona), ("vendedor", vendedor),
                             ("semana", semana), ("dia", dia)):
            if valor is None:
                continue
            if valor == "" or valor is False:
                reg.pop(campo, None)
            else:
                reg[campo] = valor
        if reg.get("dia"):
            reg.pop("semana", None)          # o dia e mais especifico
        if reg:
            excecoes[chave] = reg
        else:
            excecoes.pop(chave, None)
    return len(excecoes)


def limpar_excecoes(cfg: dict, clientes=None) -> int:
    """
    Tira do arquivo as excecoes que nao apontam mais para lugar nenhum:
    zona que foi excluida, vendedor que saiu do cadastro, cliente que nao
    esta mais na base. Devolve quantas sairam.
    """
    excecoes = cfg.get("excecoes") or {}
    if not excecoes:
        return 0
    zonas = {z["id"] for z in cfg["zonas"]}
    pessoas = {p["cod_protheus"] for p in cfg.get("pessoas") or []}
    vivos = {c["CHAVE_CLIENTE"] for c in clientes} if clientes else None
    antes = len(excecoes)
    for chave, reg in list(excecoes.items()):
        if vivos is not None and chave not in vivos:
            excecoes.pop(chave)
            continue
        if reg.get("zona") and reg["zona"] not in zonas:
            reg.pop("zona")
        if reg.get("vendedor") and reg["vendedor"] not in pessoas:
            reg.pop("vendedor")
        if reg.get("dia") and not (1 <= int(reg["dia"]) <= 31):
            reg.pop("dia")
        if reg.get("semana") and not (1 <= int(reg["semana"]) <= 6):
            reg.pop("semana")
        if not reg:
            excecoes.pop(chave)
    return antes - len(excecoes)


def areas_da_zona(cfg: dict, zona_id: str) -> list:
    return sorted(c for c, z in cfg["areas"].items() if z == zona_id)


def aplicar_area(cfg: dict, chaves, zona_id: str) -> None:
    """Uma area pertence a UMA zona: entrar numa e sair da anterior."""
    for chave in chaves:
        if zona_id:
            cfg["areas"][chave] = zona_id
        else:
            cfg["areas"].pop(chave, None)


def curva_de(media: float, par: dict) -> str:
    if media >= par.get("curva_s", 20000):
        return "S"
    if media >= par.get("curva_a", 10000):
        return "A"
    if media >= par.get("curva_b", 5000):
        return "B"
    if media >= par.get("curva_c", 1):
        return "C"
    return "Z"


def status_de(dias, par: dict) -> str:
    if dias is None:
        return "NUNCA COMPROU"
    if dias <= par.get("churn_30", 30):
        return "ATIVO"
    if dias <= par.get("churn_60", 60):
        return "CHURN 30"
    if dias <= par.get("churn_90", 90):
        return "CHURN 60"
    if dias <= par.get("inativo", 90):
        return "CHURN 90"
    return SITUACAO_90


def aplicar_parametros(cfg: dict, clientes: list) -> None:
    """
    Recalcula curva e status de cada cliente com os parametros da aba
    PARAMETROS. Nao precisa refazer a BASE_CLIENTE: o que muda e so o
    corte, e a receita e os dias sem compra ja estao na base.
    """
    par = cfg.get("parametros") or {}
    meses = max(1, int(par.get("meses_curva", MESES_JANELA) or 1))
    meses6 = max(1, int(par.get("meses_faturamento", 6) or 6))
    for c in clientes:
        # TODO "MxM" no BAP e MEDIA MENSAL, nunca soma da janela: o M3M e a
        # receita dos 3 meses dividida por 3, e o M6M a dos 6 dividida por
        # 6. O M3M ANTERIOR e a media dos 3 meses de ANTES - e a comparacao
        # dos dois que diz se o cliente esta crescendo ou caindo.
        media = c["RECEITA_PERIODO"] / meses
        c["MEDIA_MENSAL"] = round(media, 2)
        c["MEDIA_MENSAL_6M"] = round(c.get("RECEITA_6M", 0.0) / meses6, 2)
        c["MEDIA_MENSAL_ANTERIOR"] = round(
            c.get("RECEITA_PERIODO_ANTERIOR", 0.0) / meses, 2)
        c["CURVA_RECEITA"] = curva_de(max(0.0, media), par)
        c["STATUS_CLIENTE"] = status_de(c.get("DIAS_SEM_COMPRA"), par)


# ==========================================================================
# indicadores
# ==========================================================================
def _bloco_vazio():
    return {
        "clientes": 0, "cidades": set(), "bairros": set(), "areas": set(),
        # quem atende: entram os codigos/ids, para contar QTD VDE e QTD ZONAS
        "vendedores": set(), "zonas": set(), "supervisores": set(),
        # QTD VDE conta so quem esta ATIVO no cadastro: a cadeira VAGA
        # (vendedor inativo) nao e um vendedor na base. "vendedores"
        # continua com todo mundo porque e dele que sai a carga da rota -
        # a rota do VAGO sai do mesmo jeito.
        "vendedores_ativos": set(),
        # as zonas que tem alguem ATIVO na cadeira. O resto (sem vendedor
        # nenhum ou com vendedor inativo) e ZONA S/ VDE.
        "zonas_com_vde": set(),
        "curva": Counter(), "status": Counter(),
        "com_limite": 0, "limite_disponivel": 0.0,
        "inadimplentes": 0, "valor_atraso": 0.0,
        "receita_periodo": 0.0, "receita_6m": 0.0, "receita_acumulada": 0.0,
        "compradores": 0, "compradores_historico": 0, "comprantes": 0,
        # a rota: visitas do mes e em quantos dias elas cabem
        "visitas": 0, "dias_agenda": 0,
        # (07/10) as visitas da ROTA sem o 1o sabado (o deposito do
        # excedente): o indicador de visitas em dias uteis
        "visitas_uteis": 0,
        # AS DUAS BASES DE CLIENTE:
        #   base_visita   quem o vendedor visita na SEMANA (dias uteis mais
        #                 o ultimo sabado) - e sobre ela que a meta e feita
        #   "clientes"    a carteira inteira, com os excedentes que caem no
        #                 sabado-deposito
        "base_visita": 0,
        # o teto de visitas/dia que vale para a linha. Quando a linha
        # junta zonas de tetos diferentes, vale o MENOR - e ele que
        # aperta primeiro.
        "capacidade": 0,
    }


def _somar(bloco, c, contexto=None):
    """
    Soma um cliente no bloco. `contexto` traz de quem ele e:
        {"vendedor": cod, "zona": zid, "supervisor": nome,
         "visitas": n, "dias_agenda": n, "comprante": bool}
    """
    ctx = contexto or {}
    bloco["clientes"] += 1
    bloco["cidades"].add(f"{c['UF']}|{c['CIDADE']}")
    bloco["bairros"].add(f"{c['UF']}|{c['CIDADE']}|{c['BAIRRO']}")
    bloco["areas"].add(c["AREA"])
    if ctx.get("vendedor"):
        bloco["vendedores"].add(ctx["vendedor"])
        if ctx.get("vendedor_ativo", True):
            bloco["vendedores_ativos"].add(ctx["vendedor"])
    if ctx.get("zona"):
        bloco["zonas"].add(ctx["zona"])
        if ctx.get("vendedor") and ctx.get("vendedor_ativo", True):
            bloco["zonas_com_vde"].add(ctx["zona"])
    if ctx.get("supervisor"):
        bloco["supervisores"].add(ctx["supervisor"])
    bloco["visitas"] += ctx.get("visitas", 1)
    bloco["visitas_uteis"] += ctx.get("visitas_uteis", 0)
    if not ctx.get("so_deposito"):
        bloco["base_visita"] += 1
    cap = ctx.get("capacidade") or 0
    if cap:
        bloco["capacidade"] = min(bloco["capacidade"] or cap, cap)
    # o vendedor atende varias zonas nos MESMOS dias: o denominador do
    # CLI/DIA e a maior agenda entre as zonas dele, nao a soma delas
    bloco["dias_agenda"] = max(bloco["dias_agenda"], ctx.get("dias_agenda", 0))
    bloco["curva"][c["CURVA_RECEITA"] if c["CURVA_RECEITA"] in CURVAS else "Z"] += 1
    bloco["status"][c["STATUS_CLIENTE"]] += 1
    if c["LIMITE_APROVADO"] > 0 or c["LIMITE_DISPONIVEL"] > 0:
        bloco["com_limite"] += 1
    bloco["limite_disponivel"] += c["LIMITE_DISPONIVEL"]
    if c["VALOR_EM_ATRASO"] > 0:
        bloco["inadimplentes"] += 1
        bloco["valor_atraso"] += c["VALOR_EM_ATRASO"]
    bloco["receita_periodo"] += c["RECEITA_PERIODO"]
    bloco["receita_6m"] += c.get("RECEITA_6M", c["RECEITA_PERIODO"])
    bloco["receita_acumulada"] += c["RECEITA_ACUMULADA"]
    if c["RECEITA_PERIODO"] > 0:
        bloco["compradores"] += 1
    if c["RECEITA_ACUMULADA"] > 0:
        bloco["compradores_historico"] += 1
    if ctx.get("comprante"):
        bloco["comprantes"] += 1


def cargas_da_rota(linhas: list, deposito=None) -> dict:
    """
    Quantas visitas cada dia recebeu NA ROTA que acabou de ser montada,
    POR ZONA e POR VENDEDOR. E daqui que sai o CLI/DIA do gerencial -
    assim a tela mostra exatamente o que o PLANNER vai trazer.
        util   - a carga de um dia de agenda (dia util OU o ultimo sabado,
                 que e dia de rota normal)
        sabado - a carga do sabado-DEPOSITO (0 quando ele nao e usado)

    Os dois recortes existem porque NAO DA PARA SOMAR ZONA: o vendedor que
    atende duas zonas nao roda as duas no mesmo dia - ele reparte o mes
    entre elas. Somar 8,7 de uma com 10,2 da outra daria 18,9 visitas num
    dia que na verdade tem 12. O CLI/DIA do vendedor sai daqui, do recorte
    dele, ja com as duas zonas juntas na mesma agenda.

    deposito = a data do sabado do deposito. Sem ela, todo sabado conta
    como dia de agenda comum.
    """
    def _novo():
        return {"uteis": Counter(), "sabados": Counter()}

    porzona = defaultdict(_novo)
    porvend = defaultdict(_novo)
    for r in linhas:
        deposito_aqui = deposito is not None and r["DATA"] == deposito
        for alvo in (porzona[r["ZONA_ID"]], porvend[r["COD_VENDEDOR"]]):
            if deposito_aqui:
                alvo["sabados"][r["DATA"]] += 1
            else:
                alvo["uteis"][r["DATA"]] += 1

    def _fechar_carga(dados):
        u, sb = dados["uteis"], dados["sabados"]
        todos = list(u.values()) + list(sb.values())
        return {
            "util": round(sum(u.values()) / len(u), 1) if u else 0.0,
            "sabado": round(sum(sb.values()) / len(sb), 1) if sb else 0.0,
            # so os dias de AGENDA: o sabado do deposito nao e dia de
            # agenda, e destino de excedente
            "dias": len(u),
            "dias_deposito": len(sb),
            # o pior dia: e ele que denuncia quando a carteira nao coube e a
            # rota teve de passar do teto
            "pico": max(todos) if todos else 0,
        }

    return {"zona": {k: _fechar_carga(v) for k, v in porzona.items()},
            "vendedor": {k: _fechar_carga(v) for k, v in porvend.items()}}


def _fechar(bloco, du, visitas_dia_config=0, frequencia=1, meses=3,
            meses_fat=6, cargas=None, zona_unica=None):
    clientes = bloco["clientes"]
    visitas = bloco["visitas"] or clientes * max(1, frequencia)
    # CLI/DIA exato: as visitas do mes divididas pelos dias que a rota
    # daquela zona/vendedor realmente usa (com o ultimo sabado, sempre;
    # sem o sabado do deposito, que nao e dia de agenda).
    #
    # DE ONDE SAI A CARGA, por recorte:
    #   ZONA ...... a carga da propria zona
    #   VENDEDOR .. a carga DELE, com as zonas dele ja juntas na mesma
    #               agenda. NAO e a soma das zonas: ele nao roda duas zonas
    #               no mesmo dia, reparte o mes entre elas. Somar 8,7 de
    #               uma com 10,2 da outra dava 18,9 num dia que tem 12.
    #   o resto ... a soma dos vendedores do bloco - supervisor, gerente,
    #               UF, cidade e BAP TOTAL sao varias pessoas trabalhando
    #               ao mesmo tempo, e ai somar e o certo.
    carga_util = carga_sab = 0.0
    pico = 0
    dias_reais = 0
    if cargas:
        if zona_unica is not None:
            c = (cargas.get("zona") or {}).get(zona_unica, {})
            carga_util, carga_sab = c.get("util", 0.0), c.get("sabado", 0.0)
            pico, dias_reais = c.get("pico", 0), c.get("dias", 0)
        else:
            porv = cargas.get("vendedor") or {}
            quem = [v for v in bloco["vendedores"] if v in porv]
            carga_util = sum(porv[v]["util"] for v in quem)
            carga_sab = sum(porv[v]["sabado"] for v in quem)
            pico = max((porv[v]["pico"] for v in quem), default=0)
            # os dias sao os do vendedor que trabalha mais dias do bloco -
            # eles trabalham em paralelo, nao em fila
            dias_reais = max((porv[v]["dias"] for v in quem), default=0)
    dias = dias_reais or bloco["dias_agenda"] or du
    saida = {
        "clientes": clientes,
        "visitas_mes": visitas,
        "visitas_uteis": bloco.get("visitas_uteis", 0),
        "cidades": len(bloco["cidades"]),
        "bairros": len(bloco["bairros"]),
        "areas": len(bloco["areas"]),
        # QTD VDE = so os ATIVOS. A cadeira VAGA nao e vendedor na base.
        "qtd_vendedores": len(bloco["vendedores_ativos"]),
        "qtd_vendedores_cadeira": len(bloco["vendedores"]),
        "qtd_zonas": len(bloco["zonas"]),
        # ZONAS C/ VDE e ZONAS S/ VDE: a zona sem ninguem e a zona com
        # vendedor INATIVO caem as duas no S/ VDE - as duas sao vaga aberta
        "zonas_com_vde": len(bloco["zonas_com_vde"]),
        "zonas_sem_vde": len(bloco["zonas"]) - len(bloco["zonas_com_vde"]),
        "qtd_supervisores": len(bloco["supervisores"]),
        "clientes_por_vendedor": (
            round(clientes / len(bloco["vendedores_ativos"]), 1)
            if bloco["vendedores_ativos"] else 0.0),
        "clientes_por_supervisor": (round(clientes / len(bloco["supervisores"]), 1)
                                    if bloco["supervisores"] else 0.0),
        "du": du,
        "dias_agenda": dias,
        # BASE VISITA = os clientes da rota da semana (dias uteis + ultimo
        # sabado). BASE CARTEIRA = todos, com os excedentes do deposito.
        "base_visita": bloco["base_visita"],
        "base_carteira": clientes,
        "excedentes": clientes - bloco["base_visita"],
        "clientes_dia": round(carga_util, 1) if carga_util
        else (round(visitas / dias, 1) if dias else 0.0),
        "clientes_dia_sabado": round(carga_sab, 1),
        "capacidade_dia": visitas_dia_config or bloco.get("capacidade") or 0,
        "com_limite": bloco["com_limite"],
        "limite_disponivel": round(bloco["limite_disponivel"], 2),
        "inadimplentes": bloco["inadimplentes"],
        "valor_atraso": round(bloco["valor_atraso"], 2),
        "pct_inadimplencia": round(pct(bloco["inadimplentes"], clientes), 1),
        # faturamento
        "receita_periodo": round(bloco["receita_periodo"], 2),
        "receita_6m": round(bloco["receita_6m"], 2),
        "receita_acumulada": round(bloco["receita_acumulada"], 2),
        "compradores": bloco["compradores"],
        "compradores_historico": bloco["compradores_historico"],
        # COMPRANTES = comprou nos ultimos N dias (padrao 90)
        "comprantes": bloco["comprantes"],
        # FAT. M6M = o que a linha fatura por mes na janela de 6 meses
        "faturamento_mensal": round(bloco["receita_6m"] / max(1, meses_fat), 2),
        # FAT/CLIENTE COMP. = a media M6M dividida so pelos comprantes
        "faturamento_por_comprante": round(
            bloco["receita_6m"] / max(1, meses_fat) / bloco["comprantes"], 2)
        if bloco["comprantes"] else 0.0,
        "pct_compradores": round(pct(bloco["compradores"], clientes), 1),
        "pct_comprantes": round(pct(bloco["comprantes"], clientes), 1),
    }
    # Os conjuntos crus viajam junto com a linha, com "_" na frente. Eles
    # nao saem em Excel nenhum (os exports escolhem coluna por coluna):
    # servem para o TOTAL DA TELA juntar as linhas visiveis sem contar
    # ninguem duas vezes - o mesmo vendedor em duas cidades e UM vendedor.
    saida["_vendedores"] = set(bloco["vendedores_ativos"])
    saida["_vendedores_cadeira"] = set(bloco["vendedores"])
    saida["_zonas"] = set(bloco["zonas"])
    saida["_zonas_com_vde"] = set(bloco["zonas_com_vde"])
    saida["_cidades"] = set(bloco["cidades"])
    saida["_supervisores"] = set(bloco["supervisores"])
    for k in CURVAS:
        saida[f"curva_{k}"] = bloco["curva"].get(k, 0)
    for k in STATUS:
        saida[f"status_{k}"] = bloco["status"].get(k, 0)
    saida["carteira_ativa"] = clientes - bloco["status"].get("NUNCA COMPROU", 0)
    if saida["capacidade_dia"]:
        saida["dias_necessarios"] = math.ceil(visitas / saida["capacidade_dia"])
        # a folga e medida contra os dias que a rota REALMENTE usa (com o
        # sabado, quando a zona usa sabado), e nao so contra os dias uteis
        saida["folga_dias"] = dias - saida["dias_necessarios"]
    else:
        saida["dias_necessarios"] = math.ceil(visitas / du) if du else 0
        saida["folga_dias"] = 0
    # o pior dia da rota de verdade, e quanto ele passou do teto
    saida["pico_dia"] = pico
    saida["acima_do_teto"] = max(
        0, saida["pico_dia"] - saida["capacidade_dia"]) \
        if saida["capacidade_dia"] else 0
    saida["cabe"] = not (saida["capacidade_dia"] and saida["folga_dias"] < 0)
    return saida


def sabados_do_mes(cfg: dict, dias=None) -> list:
    """Os sabados do mes que nao caem em feriado, em ordem."""
    if dias is None:
        dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    return [d for d in dias if d[3]]


def ultimo_sabado(cfg: dict, dias=None):
    """
    O ULTIMO SABADO DO MES - dia de rota de TODOS os vendedores, sempre,
    todo mes, com o mesmo teto de visitas por dia dos dias uteis. Nao ha
    parametro para ligar ou desligar: e regra fixa da BAP.
    """
    sab = sabados_do_mes(cfg, dias)
    return sab[-1] if sab else None


def primeiro_sabado(cfg: dict, dias=None):
    """
    O PRIMEIRO SABADO DO MES - o deposito dos clientes que nao couberam
    nos dias uteis, quando "colocar os excedentes no sabado" esta em SIM.
    Se o mes so tem um sabado, ele acumula os dois papeis.
    """
    sab = sabados_do_mes(cfg, dias)
    return sab[0] if sab else None


def agenda_da_zona(cfg: dict, z: dict, dias=None, clientes_da_zona=None):
    """
    Os dias em que ESTA zona sera rodada, na mesma regra que a rota usa:
    todos os dias uteis do mes MAIS o ultimo sabado, que e trabalhado
    sempre. O primeiro sabado nao entra: quando o deposito esta ligado ele
    e destino de excedente, nao dia de agenda.
    O gerencial e o PLANNER chamam esta mesma funcao - assim o CLI/DIA da
    tela e exatamente o que sai na rota.
    """
    if dias is None:
        dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    uteis = [d for d in dias if not d[3]] or dias
    ult = ultimo_sabado(cfg, dias)
    if ult is None:
        return uteis
    return sorted(uteis + [ult], key=lambda d: d[0])


def zona_so_excedente(z) -> bool:
    """(18/10) A zona marcada 'So no sabado do excedente' (aba Zonas)."""
    return bool((z or {}).get("so_excedente"))


def excedente_no_sabado(cfg: dict, z: dict) -> bool:
    """A zona joga no sabado o que passar do teto de visitas por dia?"""
    par = cfg.get("parametros") or {}
    return bool((z or {}).get("excedentes_no_sabado",
                              par.get("excedentes_no_sabado", False)))


def distribuir_visitas(lista, agenda, cap, excedente=False):
    """
    Espalha a carteira pelos dias da agenda. Devolve [(cliente, dia)].

    excedente = False  cada dia recebe piso ou teto de n/d visitas: a
                       carga fica igual em todos os dias, sabado incluso.
    excedente = True   o dia util enche ate o teto (cap) e o que passar
                       disso vai para o sabado. O SABADO TAMBEM TEM TETO:
                       ele e um dia de trabalho como os outros, nao um
                       deposito. E a regra "colocar os clientes
                       excedentes no sabado".

    Quando nem os sabados dao conta - a carteira nao cabe no mes com esse
    teto - o que ainda sobra e espalhado POR IGUAL entre todos os dias,
    em vez de empilhar num dia so. Nenhum cliente e descartado: a rota
    sai completa e o gerencial mostra a linha em vermelho, dizendo de
    quantos dias o vendedor precisaria.
    """
    n, d = len(lista), len(agenda)
    if not n or not d:
        return []
    if excedente and cap > 0:
        uteis = [x for x in agenda if not x[3]]
        sabados = [x for x in agenda if x[3]]
        if uteis:
            # O TETO E UM TETO, NAO UMA META. Se a carteira cabe nos dias
            # uteis, ela e espalhada POR IGUAL entre eles - senao o
            # vendedor trabalharia 9 dias no teto e ficaria 16 parado, e a
            # 2a visita, que so pode cair em dia que a cidade ja tem, nao
            # teria para onde ir (era assim que um teto de 120 virava 240).
            du = len(uteis)
            if n <= cap * du:
                return [(c, uteis[min(i * du // n, du - 1)])
                        for i, c in enumerate(lista)]
            saida, resto = [], list(lista)
            # 1) nao cabe: cada dia util enche ate o teto
            cabem = min(len(resto), cap * du)
            saida += [(c, uteis[i // cap]) for i, c in enumerate(resto[:cabem])]
            resto = resto[cabem:]
            # 2) o que passou do teto vai para o sabado, tambem ate o teto
            if resto and sabados:
                cabem = min(len(resto), cap * len(sabados))
                saida += [(c, sabados[i // cap])
                          for i, c in enumerate(resto[:cabem])]
                resto = resto[cabem:]
            # 3) nao cabe no mes: espalha o que sobrou por igual, sem
            #    perder ninguem (o gerencial acusa em vermelho)
            if resto:
                saida += [(c, agenda[i * d // len(resto)])
                          for i, c in enumerate(resto)]
            return saida
    return [(c, agenda[min(i * d // n, d - 1)]) for i, c in enumerate(lista)]


# --------------------------------------------------------------------------
# O CACHE DA ROTA
# --------------------------------------------------------------------------
# Montar a rota custa ~0,15 s. Parece pouco, mas a tela chama os indicadores
# a cada clique que muda alguma coisa - trocar de aba, ordenar, abrir o
# quadro de zonas, salvar parametro - e cada uma dessas chamadas remontava o
# mes inteiro do zero. Com a carteira grande isso vira meio segundo de
# espera a cada toque.
#
# Aqui fica guardada A ULTIMA rota montada. A chave e a configuracao inteira
# (mes, feriados, parametros, zonas, areas, pessoas e excecoes) mais a lista
# de clientes: mudou qualquer coisa, a rota e refeita. A lista de clientes
# fica presa no cache de proposito - assim o id() dela nao pode ser reusado
# por outro objeto e a comparacao continua valendo.
_CACHE_ROTA = {"chave": None, "rota": None, "clientes": None}

# so isto muda a rota; o resto do arquivo de configuracao nao
_PARTES_DA_ROTA = ("mes", "feriados", "parametros", "zonas", "areas",
                   "pessoas", "excecoes", "rota_cidade",
                   "rota_cidade_fora", "clientes_inativos", "rota_fixa")


def _impressao_digital(cfg: dict, clientes: list) -> tuple:
    miolo = {k: cfg.get(k) for k in _PARTES_DA_ROTA}
    try:
        texto = json.dumps(miolo, sort_keys=True, ensure_ascii=False,
                           default=str)
    except (TypeError, ValueError):
        return None
    # a planilha de coordenadas entra na chave: trocou o arquivo de
    # COORDENADAS_CIDADES_BAIRRO_BAP, a rota tem de ser refeita
    return (id(clientes), len(clientes), IGNORAR_ROTA_FIXA[0],
            geo.impressao_das_coordenadas(),
            hashlib.md5(texto.encode("utf-8")).hexdigest())


def rota_do_mes(cfg: dict, clientes: list[dict]) -> list[dict]:
    """
    A rota do mes, montada uma vez so enquanto nada mudar.

    E PARA LER, NAO PARA MEXER: quem precisa alterar as linhas (o PLANNER, o
    Excel da rota, os recortes) chama gerar_rota() e recebe uma lista nova.
    """
    chave = _impressao_digital(cfg, clientes)
    if chave is None:
        return gerar_rota(cfg, clientes)
    if _CACHE_ROTA["chave"] == chave:
        return _CACHE_ROTA["rota"]
    rota = gerar_rota(cfg, clientes)
    _CACHE_ROTA.update({"chave": chave, "rota": rota, "clientes": clientes})
    return rota


def esquecer_rota() -> None:
    """Joga fora a rota guardada. So os testes precisam disto."""
    _CACHE_ROTA.update({"chave": None, "rota": None, "clientes": None})


def indicadores(cfg: dict, clientes: list[dict], segmentos=None) -> dict:
    """
    Devolve as visoes. A visao por ZONA e a unica onde o vendedor e
    escolhido; vendedor, supervisor, cidade, segmento e total sao
    derivados dela.

    `segmentos`: so estes segmentos entram nos numeros (o filtro do
    gerencial). A rota continua sendo a do mes inteiro - o CLI/DIA e a
    agenda de verdade do vendedor, com todos os segmentos dele.
    """
    filtro_seg = ({_seg_norm(x) for x in segmentos} if segmentos else None)
    du = dias_uteis(cfg["mes"], cfg.get("feriados") or [])
    par = cfg["parametros"]
    meses = max(1, int(par.get("meses_curva", MESES_JANELA) or 1))
    meses_fat = max(1, int(par.get("meses_faturamento", 6) or 6))
    corte_comprante = int(par.get("dias_comprante", 90) or 90)
    zonas = {z["id"]: z for z in cfg["zonas"]}
    vend = {p["cod_protheus"]: p for p in vendedores(cfg)}
    # quantas visitas cada curva pede neste mes (S semanal, A semana sim
    # semana nao, B e C quinzenal, Z uma) - e o que diz se a carteira cabe
    n_semanas = len({d[2] for d in dias_do_mes(cfg["mes"],
                                               cfg.get("feriados") or [],
                                               False)}) or 1

    # a agenda de cada zona, do jeito que a rota vai montar: assim o
    # CLI/DIA do gerencial e o mesmo numero que sai no PLANNER. Depende de
    # quantos clientes a zona tem (e o que decide se o sabado entra), entao
    # a carteira e contada antes.
    carteira = Counter(zona_para_mostrar(cfg, c) for c in clientes)
    dias_mes = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    # a rota de verdade e quem diz quantas visitas cada dia tem. O sabado
    # do DEPOSITO fica de fora da media do dia: ele nao e dia de agenda.
    _dep = primeiro_sabado(cfg, dias_mes) if any(
        excedente_no_sabado(cfg, z) for z in cfg["zonas"]) else None
    _rota = rota_do_mes(cfg, clientes)
    cargas = cargas_da_rota(_rota, _dep[0] if _dep else None)
    # quem SO tem visita no sabado-deposito: e o excedente da rota, e ele
    # fica de fora da base de visita
    so_no_deposito = set()
    # (07/10) quantas visitas o cliente tem na rota FORA do 1o sabado
    vis_uteis = Counter(r["CHAVE_CLIENTE"] for r in _rota
                        if _dep is None or r["DATA"] != _dep[0])
    if _dep is not None:
        dias_do_cliente = defaultdict(set)
        for r in _rota:
            dias_do_cliente[r["CHAVE_CLIENTE"]].add(r["DATA"])
        so_no_deposito = {k for k, ds in dias_do_cliente.items()
                          if ds == {_dep[0]}}
    agendas = {}
    for z in cfg["zonas"]:
        agendas[z["id"]] = (cargas["zona"].get(z["id"], {}).get("dias")
                            or len(agenda_da_zona(cfg, z, dias_mes,
                                                  carteira.get(z["id"], 0))))

    por_zona = defaultdict(_bloco_vazio)
    por_vend = defaultdict(_bloco_vazio)
    por_sup = defaultdict(_bloco_vazio)
    por_ger = defaultdict(_bloco_vazio)
    por_cidade = defaultdict(_bloco_vazio)
    por_uf = defaultdict(_bloco_vazio)
    por_seg = defaultdict(_bloco_vazio)
    por_seg_vend = defaultdict(_bloco_vazio)     # segmento x vendedor
    total = _bloco_vazio()

    # o chefe de cada vendedor nao muda dentro do laco: resolve uma vez so
    chefia = {}
    for c in clientes:
        if filtro_seg is not None and _seg_norm(segmento_do_cliente(c)) not in filtro_seg:
            continue
        zid = zona_para_mostrar(cfg, c)
        z = zonas.get(zid)
        # o vendedor pode ter sido trocado so para este cliente, no analitico
        cod = vendedor_do_cliente(cfg, c, zonas)
        if cod not in chefia:
            chefia[cod] = (nome_supervisor(cfg, cod) or "(sem supervisor)",
                           nome_gerente(cfg, cod) or "(sem gerente)",
                           pessoa_ativa(cfg, cod))
        sup, ger, cod_ativo = chefia[cod]
        dias = c.get("DIAS_SEM_COMPRA")
        ctx = {
            "vendedor": cod, "zona": (z or {}).get("id", ""),
            "vendedor_ativo": cod_ativo,
            "supervisor": sup if cod else "",
            "visitas": plano_da_curva(c.get("CURVA_RECEITA", "Z"), n_semanas)[0],
            "dias_agenda": agendas.get(zid, du),
            "capacidade": int((z or {}).get("visitas_por_dia")
                              or par.get("visitas_por_dia") or 0) if z else 0,
            "comprante": dias is not None and dias <= corte_comprante,
            # cliente que so tem visita no sabado-deposito nao entra na
            # base de visita: ele e excedente, nao rota da semana
            "so_deposito": c["CHAVE_CLIENTE"] in so_no_deposito,
            "visitas_uteis": vis_uteis.get(c["CHAVE_CLIENTE"], 0),
        }
        _somar(por_zona[zid], c, ctx)
        _somar(por_vend[cod or "(sem vendedor)"], c, ctx)
        _somar(por_sup[sup], c, ctx)
        _somar(por_ger[ger], c, ctx)
        _somar(por_cidade[f"{c['UF']}|{c['CIDADE']}"], c, ctx)
        _somar(por_uf[c["UF"] or "(sem UF)"], c, ctx)
        _somar(por_seg[segmento_do_cliente(c)], c, ctx)
        _somar(por_seg_vend[(segmento_do_cliente(c),
                             cod or "(sem vendedor)")], c, ctx)
        _somar(total, c, ctx)

    visao_zona = []
    for z in cfg["zonas"]:
        b = por_zona.get(z["id"])
        if b is None and z["id"] not in por_zona:
            b = _bloco_vazio()
        cap = z.get("visitas_por_dia") or par["visitas_por_dia"]
        linha = _fechar(b, du, cap, 1, meses, meses_fat, cargas,
                        zona_unica=z["id"])
        cod = z.get("vendedor", "")
        ativo = bool(cod) and pessoa_ativa(cfg, cod)
        at = atendimento_da_zona(z)
        linha.update({
            "zona": z["id"], "zona_nome": z["nome"], "uf": z.get("uf", ""),
            "codigo": z.get("codigo", ""),
            "vendedor": cod, "vendedor_nome": vend.get(cod, {}).get("nome", ""),
            # mais de um vendedor na zona: cada um com os seus segmentos
            "atendimento_rotulo": (" / ".join(
                f"{vend.get(a['vendedor'], {}).get('nome', a['vendedor'])} "
                f"[{rotulo_segmentos(a['segmentos'])}]" for a in at)
                if len(at) > 1 else ""),
            "segmentos_sem_vde": segmentos_sem_vendedor(z) if at else [],
            "vendedor_ativo": ativo,
            "supervisor": nome_supervisor(cfg, cod),
            "frequencia": 0,          # nao existe mais: quem manda e a curva
            "interior": vendedor_do_interior(cfg, cod),
            # a linha E uma zona: ela mesma conta 1 de um lado ou do outro
            "qtd_zonas": 1,
            "zonas_com_vde": 1 if ativo else 0,
            "zonas_sem_vde": 0 if ativo else 1,
            "_zonas": {z["id"]},
            "_zonas_com_vde": {z["id"]} if ativo else set(),
        })
        visao_zona.append(linha)

    # Cliente que ainda nao pertence a nenhuma zona nao pode sumir do
    # gerencial: ele fica ESTACIONADO na zona virtual da UF dele
    # (Z-AM-100, Z-PA-100...), visivel e contado, sem vendedor e sem rota,
    # ate alguem por o bairro dele numa zona de verdade.
    for zid, sobra in sorted(por_zona.items()):
        if not (zid == SEM_ZONA or zid.endswith(f"-{SUFIXO_SEM_ZONA}")):
            continue
        if not sobra or not sobra["clientes"]:
            continue
        uf = zid.split("-")[1] if zid != SEM_ZONA else ""
        linha = _fechar(sobra, du, 0, 1, meses, meses_fat, cargas,
                        zona_unica=zid)
        linha.update({
            "zona": zid,
            "zona_nome": (f"{uf} - SEM ZONA (bairros ainda sem dono)"
                          if uf else SEM_ZONA),
            "uf": uf, "codigo": zid if uf else "",
            "vendedor": "", "vendedor_nome": "", "vendedor_ativo": False,
            "supervisor": "", "frequencia": 0,
            "interior": False,
            "qtd_zonas": 1, "zonas_com_vde": 0, "zonas_sem_vde": 1,
            "_zonas": {zid}, "_zonas_com_vde": set(),
        })
        visao_zona.append(linha)

    def derivada(mapa, rotulo):
        saida = []
        for chave, b in mapa.items():
            linha = _fechar(b, du, 0, 1, meses, meses_fat, cargas)
            linha[rotulo] = chave
            saida.append(linha)
        return sorted(saida, key=lambda x: -x["clientes"])

    visao_vend = derivada(por_vend, "vendedor")
    for linha in visao_vend:
        v = vend.get(linha["vendedor"], {})
        linha["vendedor_nome"] = v.get("nome", "") or linha["vendedor"]
        linha["supervisor"] = nome_supervisor(cfg, linha["vendedor"])
        linha["zonas"] = sorted(z["nome"] for z in
                                zonas_do_vendedor(cfg, linha["vendedor"]))

    visao_cidade = derivada(por_cidade, "cidade")
    for linha in visao_cidade:
        uf, _, cid = linha["cidade"].partition("|")
        linha["uf"], linha["cidade_nome"] = uf, cid

    # o segmento aberto por vendedor (o filtro VENDEDOR do Por segmento)
    visao_seg_vend = derivada(por_seg_vend, "chave")
    for linha in visao_seg_vend:
        seg, cod = linha.pop("chave")
        linha["segmento"], linha["vendedor"] = seg, cod
        linha["vendedor_nome"] = vend.get(cod, {}).get("nome", "") or cod
        linha["supervisor"] = nome_supervisor(cfg, cod)

    return {
        "mes": cfg["mes"],
        "du": du,
        "dias": dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True),
        "zona": visao_zona,
        "vendedor": visao_vend,
        "supervisor": derivada(por_sup, "supervisor"),
        "gerente": derivada(por_ger, "gerente"),
        "cidade": visao_cidade,
        "uf": derivada(por_uf, "uf"),
        "segmento": derivada(por_seg, "segmento"),
        "segmento_vendedor": visao_seg_vend,
        "segmentos_filtro": sorted(segmentos) if segmentos else [],
        "total": _fechar(total, du, 0, 1, meses, meses_fat, cargas),
    }


# campos que simplesmente se somam quando varias linhas viram uma so
SOMAVEIS_DO_TOTAL = (
    "clientes", "base_visita", "base_carteira", "visitas_mes", "excedentes",
    "visitas_uteis", "com_limite", "limite_disponivel", "inadimplentes", "valor_atraso",
    "receita_periodo", "receita_6m", "receita_acumulada",
    "compradores", "compradores_historico", "comprantes", "carteira_ativa",
)


def total_das_linhas(linhas: list, meses_fat: int = 6) -> dict:
    """
    O TOTAL DO QUE ESTA NA TELA. Serve ao filtro do gerencial: escondi
    tres cidades, o rodape tem de fechar com as que ficaram.

    O que se soma, soma (clientes, dinheiro, curvas). O que e CONTAGEM DE
    GENTE - vendedor, zona, supervisor, cidade - nao se soma: junta-se os
    conjuntos. O mesmo vendedor em duas cidades e UM vendedor, e somar
    1 + 1 daria dois. Os percentuais e as medias sao refeitos no fim, do
    total; media de media nao fecha.
    """
    linhas = [l for l in linhas if l]
    t = {campo: 0.0 for campo in SOMAVEIS_DO_TOTAL}
    for k in CURVAS:
        t[f"curva_{k}"] = 0
    for k in STATUS:
        t[f"status_{k}"] = 0
    conjuntos = {"_vendedores": set(), "_vendedores_cadeira": set(),
                 "_zonas": set(), "_zonas_com_vde": set(),
                 "_cidades": set(), "_supervisores": set()}
    dia = dia_sab = 0.0
    for l in linhas:
        for campo in SOMAVEIS_DO_TOTAL:
            t[campo] += l.get(campo) or 0
        for k in CURVAS:
            t[f"curva_{k}"] += l.get(f"curva_{k}") or 0
        for k in STATUS:
            t[f"status_{k}"] += l.get(f"status_{k}") or 0
        for chave, alvo in conjuntos.items():
            alvo |= set(l.get(chave) or ())
        dia += l.get("clientes_dia") or 0.0
        dia_sab += l.get("clientes_dia_sabado") or 0.0
    for campo in ("clientes", "base_visita", "base_carteira", "visitas_mes",
                  "visitas_uteis", "excedentes", "com_limite", "inadimplentes", "compradores",
                  "compradores_historico", "comprantes", "carteira_ativa"):
        t[campo] = int(round(t[campo]))
    t.update(conjuntos)
    t["qtd_vendedores"] = len(conjuntos["_vendedores"])
    t["qtd_vendedores_cadeira"] = len(conjuntos["_vendedores_cadeira"])
    t["qtd_zonas"] = len(conjuntos["_zonas"])
    t["zonas_com_vde"] = len(conjuntos["_zonas_com_vde"])
    t["zonas_sem_vde"] = t["qtd_zonas"] - t["zonas_com_vde"]
    t["qtd_supervisores"] = len(conjuntos["_supervisores"])
    t["cidades"] = len(conjuntos["_cidades"])
    t["clientes_dia"] = round(dia, 1)
    t["clientes_dia_sabado"] = round(dia_sab, 1)
    t["limite_disponivel"] = round(t["limite_disponivel"], 2)
    t["valor_atraso"] = round(t["valor_atraso"], 2)
    for campo in ("receita_periodo", "receita_6m", "receita_acumulada"):
        t[campo] = round(t[campo], 2)
    t["clientes_por_vendedor"] = (round(t["clientes"] / t["qtd_vendedores"], 1)
                                  if t["qtd_vendedores"] else 0.0)
    t["clientes_por_supervisor"] = (
        round(t["clientes"] / t["qtd_supervisores"], 1)
        if t["qtd_supervisores"] else 0.0)
    t["pct_inadimplencia"] = round(pct(t["inadimplentes"], t["clientes"]), 1)
    t["pct_compradores"] = round(pct(t["compradores"], t["clientes"]), 1)
    t["pct_comprantes"] = round(pct(t["comprantes"], t["clientes"]), 1)
    meses_fat = max(1, int(meses_fat or 6))
    t["faturamento_mensal"] = round(t["receita_6m"] / meses_fat, 2)
    t["faturamento_por_comprante"] = (
        round(t["receita_6m"] / meses_fat / t["comprantes"], 2)
        if t["comprantes"] else 0.0)
    return t


def recorte_por_zona(cfg: dict, clientes: list[dict], filtro) -> list[dict]:
    """
    As zonas por dentro de UMA linha do gerencial: os clientes que passam
    no `filtro` (um vendedor, um supervisor, uma cidade...) agrupados pela
    zona deles. E o que aparece quando se clica numa linha do resumo.

    Cada linha traz os mesmos numeros de _fechar() - so dos clientes do
    recorte - e diz de quem a zona e ("vendedor" e "vendedor_nome"). O
    CLI/DIA nao entra aqui: ele e da zona inteira e vem de indicadores().
    """
    par = cfg["parametros"]
    du = dias_uteis(cfg["mes"], cfg.get("feriados") or [])
    meses = max(1, int(par.get("meses_curva", MESES_JANELA) or 1))
    meses_fat = max(1, int(par.get("meses_faturamento", 6) or 6))
    corte = int(par.get("dias_comprante", 90) or 90)
    zonas = {z["id"]: z for z in cfg["zonas"]}
    vend = {p["cod_protheus"]: p for p in vendedores(cfg)}

    blocos = defaultdict(_bloco_vazio)
    for c in clientes:
        if not filtro(c):
            continue
        zid = zona_para_mostrar(cfg, c)
        dias = c.get("DIAS_SEM_COMPRA")
        _somar(blocos[zid], c, {
            "vendedor": vendedor_do_cliente(cfg, c, zonas), "zona": zid,
            "comprante": dias is not None and dias <= corte,
        })

    saida = []
    for zid, b in blocos.items():
        z = zonas.get(zid) or {}
        linha = _fechar(b, du, 0, 1, meses, meses_fat)
        cod = z.get("vendedor", "")
        linha.update({
            "zona": zid,
            "codigo": z.get("codigo", "") if z else "",
            "zona_nome": z.get("nome", "") if z else SEM_ZONA,
            "uf": z.get("uf", ""),
            "vendedor": cod,
            "vendedor_nome": vend.get(cod, {}).get("nome", ""),
        })
        saida.append(linha)
    return sorted(saida, key=lambda x: (-x["clientes"], x["codigo"] or "~"))


# ==========================================================================
# geracao da rota
# ==========================================================================
_CACHE_GEO = {}


# --------------------------------------------------------------------------
# (03/11, Alexandre) A ORDEM DO MES PELA PRIORIDADE: "curva S, A e clientes
# com limite devem ocupar as primeiras visitas do mes. Depois de ocupados,
# preencher com curva B, C e etc., sempre seguindo a proximidade por
# geolocalizacao e bairros." Grupos: 0 = S, A ou com limite; 1 = B; 2 = C;
# 3 = o resto (D, Z). Cada grupo vai na ordem geografica (cidade > caminho
# mais curto), um depois do outro; os dias sao enchidos nessa ordem, entao
# o comeco do mes fica com o grupo 0. O vendedor do interior (1 cidade por
# dia) vai primeiro as cidades que tem cliente do grupo 0, na ordem do
# caminho, e dentro da cidade o grupo 0 primeiro [SUPOSICAO: a cidade nao e
# partida em duas viagens]. O TOP 30 sem limite segue a curva dele
# [SUPOSICAO]. Vale com a roteirizacao por lugar (POR_LUGAR_DESDE).
# --------------------------------------------------------------------------
def grupo_do_mes(c) -> int:
    curva = norm(c.get("CURVA_RECEITA"))[:1] or "Z"
    if curva in ("S", "A") or com_limite(c):
        return 0
    return {"B": 1, "C": 2}.get(curva, 3)


def ordem_por_prioridade(cfg: dict, clientes: list, partida=None) -> list:
    """(03/11) O grupo 0 (S, A, com limite) na ordem geografica, depois o
    B, depois o C, depois o resto - cada um na ordem geografica."""
    grupos = defaultdict(list)
    for c in clientes:
        grupos[grupo_do_mes(c)].append(c)
    saida = []
    for g in sorted(grupos):
        saida += ordem_geografica(cfg, grupos[g], partida)
    return saida


def cidades_por_prioridade(lista: list) -> list:
    """(03/11) Vendedor do interior: as cidades (na ordem em que a lista
    geografica as traz) com cliente do grupo 0 primeiro, as outras depois;
    dentro da cidade, o grupo 0 antes, e o resto na ordem do caminho."""
    ordem, por_cid = [], defaultdict(list)
    for c in lista:
        k = (c["UF"], c["CIDADE"])
        if k not in por_cid:
            ordem.append(k)
        por_cid[k].append(c)
    com = [k for k in ordem if any(grupo_do_mes(c) == 0 for c in por_cid[k])]
    sem = [k for k in ordem if k not in com]
    saida = []
    for k in com + sem:
        saida += sorted(por_cid[k], key=grupo_do_mes)     # sort estavel
    return saida


def ordem_geografica(cfg: dict, clientes: list, partida=None):
    """
    Poe a carteira na ordem em que o vendedor vai rodar (06/10):
      1. CIDADE por cidade, sempre indo para a mais proxima da anterior
         (comecando pela base do vendedor);
      2. DENTRO da cidade, pelo CAMINHO MAIS CURTO entre os clientes: cada
         cliente e um ponto no mapa (LATITUDE/LONGITUDE do endereco; sem
         ela, o centro do bairro; sem ele, o da cidade) e a ordem e a do
         vizinho mais proximo, melhorada pelo 2-opt. A cidade seguinte
         comeca pelo cliente mais perto de onde a anterior terminou.
    Como os dias sao preenchidos NA ORDEM, cada dia fica com clientes
    vizinhos - e a cidade e atendida de uma vez so.
    """
    cidades = {(c["UF"], c["CIDADE"]) for c in clientes}
    if partida not in cidades:
        # sem base definida, comeca pela cidade de maior carteira
        conta = Counter((c["UF"], c["CIDADE"]) for c in clientes)
        partida = conta.most_common(1)[0][0] if conta else None
    pontos = {c["CHAVE_CLIENTE"]: geo.ponto_do_cliente(c)[:2]
              for c in clientes}
    chave_cache = (partida, tuple(sorted(
        (c["CHAVE_CLIENTE"], pontos[c["CHAVE_CLIENTE"]],
         c["CURVA_RECEITA"]) for c in clientes)))
    if chave_cache in _CACHE_GEO:
        por = {c["CHAVE_CLIENTE"]: c for c in clientes}
        return [por[k] for k in _CACHE_GEO[chave_cache]]
    ordem_cid = geo.ordenar_cidades(sorted(cidades), partida)
    peso_status = {"ATIVO": 0, "CHURN 30": 1, "CHURN 60": 2, "CHURN 90": 3,
                   SITUACAO_90: 4, "INATIVO": 4, "NUNCA COMPROU": 5}

    def desempate(c):
        # no MESMO ponto (o centro do bairro, antes de geocodificar), quem
        # vale mais vem antes
        return (PESO_CURVA.get(c["CURVA_RECEITA"], 4),
                peso_status.get(c["STATUS_CLIENTE"], 5),
                0 if c["LIMITE_DISPONIVEL"] > 0 else 1, c["CHAVE_CLIENTE"])
    por_cid = defaultdict(list)
    for c in clientes:
        por_cid[(c["UF"], c["CIDADE"])].append(c)
    saida = []
    ultimo = geo.coordenada(*partida) if partida else None
    for cid in ordem_cid:
        lista = sorted(por_cid.get(cid, []), key=desempate)
        if not lista:
            continue
        pts = [pontos[c["CHAVE_CLIENTE"]] for c in lista]
        inicio = ultimo or geo.coordenada(*cid)
        ordem = geo.caminho_mais_curto(pts, inicio, segundos=1.0)
        saida += [lista[i] for i in ordem]
        com_ponto = [pts[i] for i in ordem if pts[i][0] is not None]
        if com_ponto:
            ultimo = com_ponto[-1]
    if len(_CACHE_GEO) > 200:
        _CACHE_GEO.clear()
    _CACHE_GEO[chave_cache] = [c["CHAVE_CLIENTE"] for c in saida]
    return saida


def _ordem_do_cliente(c):
    """Ordenacao simples, sem geografia - usada so como reserva."""
    peso_curva = {"S": 0, "A": 1, "B": 2, "C": 3, "Z": 4}
    peso_status = {"ATIVO": 0, "CHURN 30": 1, "CHURN 60": 2, "CHURN 90": 3,
                   SITUACAO_90: 4, "INATIVO": 4, "NUNCA COMPROU": 5}
    return (
        c["UF"], c["CIDADE"], c["BAIRRO"],
        peso_curva.get(c["CURVA_RECEITA"], 4),
        peso_status.get(c["STATUS_CLIENTE"], 5),
        0 if c["LIMITE_DISPONIVEL"] > 0 else 1,
        c["CHAVE_CLIENTE"],
    )


# --------------------------------------------------------------------------
# QUANTAS VISITAS CADA CLIENTE RECEBE - pela CURVA, no automatico
#
# Nao ha mais chave para ligar ou desligar: a curva manda.
#     S  visita SEMANAL              - uma em cada semana do mes
#     A  SEMANA SIM, SEMANA NAO      - semanas 1, 3, 5...
#     B  QUINZENAL                   - duas no mes, de 15 em 15 dias
#     C  QUINZENAL                   - idem
#     Z  UMA visita, e so se sobrar espaco depois de todos os outros
#
# A curva sai da media mensal de faturamento (os cortes estao na aba 6),
# entao quem fatura mais e visto mais vezes - sem ninguem ter de escolher.
# --------------------------------------------------------------------------
PESO_CURVA = {"S": 0, "A": 1, "B": 2, "C": 3, "Z": 4}


# DE QUANTOS EM QUANTOS DIAS O VENDEDOR VOLTA NO CLIENTE.
# E a mesma tabela em dois lugares: aqui ela vira o plano de visitas da
# rota (plano_da_curva) e no arquivo do Protheus ela vira o campo
# "periodicidade". Mudar um numero aqui muda os dois de uma vez - eles
# nunca podem discordar.
#     S e A ... 7 dias  (semanal)
#     B ....... 14 dias (quinzenal)
#     C ....... 30 dias (mensal)
#     D e Z ... 60 dias (a cada dois meses)
PERIODICIDADE_DA_CURVA = {"S": 7, "A": 7, "B": 14, "C": 30, "D": 60, "Z": 60}
PERIODICIDADE_PADRAO = 60


def periodicidade_da_curva(curva) -> int:
    """Os dias de intervalo entre uma visita e a proxima, pela curva."""
    return PERIODICIDADE_DA_CURVA.get(
        norm(curva)[:1] or "Z", PERIODICIDADE_PADRAO)


# (27/10, Alexandre - validacao da Maxima do layout ERP_MXSROTACLI) o campo
# PERIODICIDADE so aceita estes valores. Na rota o intervalo continua o da
# curva (60 = uma vez, se sobrar lugar); no .json vai o valor ACEITO mais
# perto (acima de 45, 45 - o maior do layout) [SUPOSICAO]. A Maxima usa o
# campo so como informativo no app.
PERIODICIDADES_MAXIMA = (1, 7, 14, 15, 21, 28, 30, 35, 42, 45)


def periodicidade_maxima(dias) -> int:
    """O valor de PERIODICIDADE aceito pela Maxima mais perto de `dias`
    (empate: o menor). 60 -> 45."""
    try:
        d = int(dias)
    except (TypeError, ValueError):
        return PERIODICIDADES_MAXIMA[-1]
    return min(PERIODICIDADES_MAXIMA, key=lambda v: (abs(v - d), v))


def plano_da_curva(curva: str, n_semanas: int) -> tuple:
    """
    (quantas visitas no mes, de quantas em quantas semanas) para a curva.
    O numero de visitas acompanha o mes: um mes de 5 semanas da 5 visitas
    ao curva S, um de 4 semanas da 4.

    Sai da PERIODICIDADE_DA_CURVA acima: 7 dias = toda semana, 14 = de
    duas em duas, 30 = uma vez no mes, 60 = uma vez, e so se sobrar
    espaco depois de todo mundo.
    """
    n_semanas = max(1, int(n_semanas))
    dias = periodicidade_da_curva(curva)
    if dias <= 7:                          # S e A: semanal
        return n_semanas, 1
    if dias <= 14:                         # B: quinzenal
        return (2, 2) if n_semanas > 1 else (1, 0)
    return 1, 0                            # C, D e Z: uma visita no mes


def plano_de_visitas(lista: list, n_semanas: int) -> dict:
    """{chave_cliente: (quantas visitas, passo em semanas)} pela curva.
    (17/10) O cliente de VISITA SEMANAL (top 30 / com limite, vendedor da
    capital) e semanal, seja qual for a curva."""
    n = max(1, int(n_semanas))
    return {c["CHAVE_CLIENTE"]: ((n, 1) if c.get("VISITA_SEMANAL") == "SIM"
                                 else plano_da_curva(
                                     c.get("CURVA_RECEITA", "Z"), n_semanas))
            for c in lista}


def repartir_carteira(lista: list, plano: dict, teto_do_mes: int,
                      protegidos=()) -> tuple:
    """
    Divide a carteira entre quem cabe nos dias uteis e quem vai para o
    sabado. Devolve (dentro, fora).

    A ordem de quem entra e a CURVA: S, A, B, C e, por ultimo, o Z - "o
    que sobrar de espaco, encaixe com curva Z". Dentro da mesma curva,
    quem fatura mais entra primeiro. Quem nao coube sai da conta dos dias
    uteis e vai visitado UMA vez, no primeiro sabado do mes.

    teto_do_mes = visitas por dia x dias uteis da fatia daquela zona.
    protegidos  = clientes com dia/semana marcados a mao no analitico. Eles
                  nunca vao para o sabado: o que voce marcou manda mais que
                  a conta.
    """
    fila = sorted(lista, key=lambda c: (_peso_fila(c),
                                        -c.get("RECEITA_6M", 0.0),
                                        c["CHAVE_CLIENTE"]))
    protegidos = set(protegidos)
    dentro, fora, usado = set(), [], 0
    for c in fila:
        chave = c["CHAVE_CLIENTE"]
        quantas = plano[chave][0]
        if teto_do_mes and usado + quantas > teto_do_mes \
                and chave not in protegidos:
            fora.append(c)
            continue
        dentro.add(chave)
        usado += quantas
    # os que entram voltam para a ORDEM GEOGRAFICA - e ela que faz a rota
    # fechar cidade por cidade
    return [c for c in lista if c["CHAVE_CLIENTE"] in dentro], fora


def repartir_com_base(lista: list, plano: dict, teto_base: int,
                      teto_resto: int, na_base, protegidos=()) -> tuple:
    """(17/10) O repartir_carteira com a REGRA DA CIDADE BASE: o cliente
    de fora da regiao da base so cabe nos dias de depois da base
    (teto_resto); o da regiao da base usa os dias da base e, sobrando
    necessidade, os outros. A fila e a mesma (semanal, prioridade, curva,
    faturamento). Devolve (dentro, fora)."""
    fila = sorted(lista, key=lambda c: (_peso_fila(c),
                                        -c.get("RECEITA_6M", 0.0),
                                        c["CHAVE_CLIENTE"]))
    protegidos = set(protegidos)
    livre1, livre2 = int(teto_base), int(teto_resto)
    dentro, fora = set(), []
    for c in fila:
        chave = c["CHAVE_CLIENTE"]
        q = plano[chave][0]
        if na_base(c):
            if livre1 + livre2 >= q or chave in protegidos:
                usa1 = min(livre1, q)
                livre1 -= usa1
                livre2 -= (q - usa1)
                dentro.add(chave)
                continue
        elif livre2 >= q or chave in protegidos:
            livre2 -= q
            dentro.add(chave)
            continue
        fora.append(c)
    return [c for c in lista if c["CHAVE_CLIENTE"] in dentro], fora


def _dia_forcado(cfg, c, agenda):
    """
    O dia/semana que o usuario marcou a mao no analitico, se houver.
    Devolve o dia da agenda, ou None.
    """
    reg = excecao_do_cliente(cfg, c)
    dia, semana = reg.get("dia"), reg.get("semana")
    if not dia and not semana:
        return None
    if dia:
        for d in agenda:
            if d[0].day == int(dia):
                return d
    if semana:
        for d in agenda:
            if d[2] == int(semana):
                return d
    return None


def _linha_da_rota(cfg, c, z, zid, cod_vend, v, dia, volta, visitas):
    """Uma linha da rota: a visita de um cliente num dia."""
    data, nome_dia, semana, e_sabado = dia
    return {
        "SEMANA": f"Semana {semana}",
        "DIA_DO_MES": data.day,
        "DATA": data,
        "DIA_DA_SEMANA": nome_dia,
        "ORDEM_DE_VISITA": 0,              # renumerado no fim, por vendedor
        "VISITA_NO_MES": volta,
        "VISITAS_DO_CLIENTE": visitas,
        "ZONA": z["nome"],
        "COD_ZONA": z.get("codigo", ""),
        "ZONA_ID": zid,
        "UF_ZONA": z.get("uf", ""),
        "SUPERVISOR": nome_supervisor(cfg, cod_vend),
        # o Gerador de Meta le esta coluna para saber se a meta deste
        # vendedor entra na soma do supervisor (vendedor VAGO nao entra)
        "CONTA_SUPERVISOR": "SIM" if conta_para_o_supervisor(cfg, cod_vend)
                            else "NAO",
        # ATIVO/INATIVO da aba 2. Sem esta coluna no arquivo, o Gerador de
        # Meta nao tinha como saber que a cadeira esta vaga - e o vendedor
        # inativo entrava na lista com meta cheia e realizado zero.
        "VENDEDOR_ATIVO": "SIM" if v.get("ativo", True) else "NAO",
        "COD_VENDEDOR": cod_vend,
        "VENDEDOR": v.get("nome", ""),
        "COD_CLIENTE": c["COD_CLIENTE"],
        "LOJA": c["LOJA"],
        "CHAVE_CLIENTE": c["CHAVE_CLIENTE"],
        "NOME_CLIENTE": c["NOME_CLIENTE"],
        "NOME_FANTASIA": c.get("NOME_FANTASIA", ""),
        "SEGMENTO": c.get("SEGMENTO", ""),
        "SUBSEGMENTO": c.get("SUBSEGMENTO", ""),
        "UF": c["UF"],
        "CIDADE": c["CIDADE"],
        "BAIRRO": c["BAIRRO"],
        "ENDERECO": c["ENDERECO"],
        "NUMERO": c["NUMERO"],
        "CONTATO": c["CONTATO"],
        "TELEFONE": c.get("TELEFONE", ""),
        "DIAS_SEM_COMPRA": c.get("DIAS_SEM_COMPRA"),
        "LIMITE_DISPONIVEL": c["LIMITE_DISPONIVEL"],
        "VALOR_EM_ATRASO": c["VALOR_EM_ATRASO"],
        "INADIMPLENTE": "SIM" if c["VALOR_EM_ATRASO"] > 0 else "NAO",
        "CURVA_RECEITA": c["CURVA_RECEITA"],
        "STATUS_CLIENTE": c["STATUS_CLIENTE"],
        # (06/10) cliente roteirizado e ATIVO no Planner (e no Protheus),
        # seja qual for a situacao pelos dias sem compra
        "STATUS_PLANNER": "ATIVO",
        # o ponto que a rota usou (endereco, bairro ou cidade)
        "LATITUDE": geo.ponto_do_cliente(c)[0],
        "LONGITUDE": geo.ponto_do_cliente(c)[1],
        "PRECISAO_GEO": geo.ponto_do_cliente(c)[2],
        "COD_ULTIMO_VENDEDOR": c["COD_ULTIMO_VENDEDOR"],
        "AREA": c["AREA_ROTULO"],
        # (17/10) por que o cliente passa na frente: TOP 30 / LIMITE; e se
        # a visita dele e SEMANAL (vendedor da capital)
        "PRIORIDADE_ROTA": c.get("PRIORIDADE_ROTA", ""),
        "VISITA_SEMANAL": c.get("VISITA_SEMANAL", ""),
    }


RAIO_DO_COMPLETAR_KM = 40.0     # a volta de "encher o dia" fica perto da base
CIDADE_LONGE_KM = 25.0          # cidade mais longe que isso e outro dia


def _ciclos_da_fatia(lista, fatia, cap, par, plano, base_pt,
                     restritos=frozenset(), na_base=None, por_grupo=False):
    """
    (06/10) A rota do vendedor da capital em CICLOS, pela proximidade:
      1a volta: todos os clientes, na ordem do caminho mais curto
                (ordem_geografica), enchendo os dias EM SEQUENCIA ate o
                teto de cada um (sexta com o dela);
      2a volta: quem a curva pede mais de uma visita (S, A, B), na mesma
                ordem;
      e depois: enquanto sobrar lugar, novas voltas com quem mora a ate
                RAIO_DO_COMPLETAR_KM da base (nao inventa viagem longa).
    Nunca o mesmo cliente 2x no dia nem 2x na semana. Como cada volta
    segue o caminho, os clientes de um dia sao vizinhos.
    Devolve (primeiras [(cliente, dia)], repetidas [(cliente, dia)]).
    (17/10) restritos = os dias da CIDADE BASE (comeco do mes): neles so
    entra quem na_base(cliente) diz que e da regiao da base. E a VISITA
    SEMANAL (top 30 / limite) tem as voltas dela antes dos outros.
    """
    dias = list(fatia)
    if not dias:
        return [], []

    def pode(d, c):
        return na_base is None or d[0] not in restritos or na_base(c)
    if restritos and na_base is not None:
        # a regiao da base primeiro (o comeco do mes e dela), o resto depois
        # - cada parte na ordem do caminho. (03/11) Com a ordem por
        # prioridade, a base vem primeiro DENTRO de cada grupo (o grupo 0
        # de fora da base vai logo depois dos dias da base, antes do B)
        if por_grupo:
            lista = sorted(lista, key=lambda c: (grupo_do_mes(c),
                                                 not na_base(c)))
        else:
            lista = [c for c in lista if na_base(c)] + \
                [c for c in lista if not na_base(c)]
    teto = {d[0]: (teto_do_dia(cap, d[0], par) if cap else 0) or 10 ** 6
            for d in dias}
    carga = Counter()
    semanas = defaultdict(set)
    no_dia = defaultdict(set)
    cidades_dia = defaultdict(set)
    ptr = [0]

    def perto_do_dia(d, c):
        """Cidade longe (mais de CIDADE_LONGE_KM das cidades do dia) nao
        entra no mesmo dia: e outra viagem."""
        cid = (c["UF"], c["CIDADE"])
        if not cidades_dia[d[0]] or cid in cidades_dia[d[0]]:
            return True
        p = geo.coordenada(*cid)
        return p is None or any(
            geo.distancia_km(p, geo.coordenada(*x) or p) <= CIDADE_LONGE_KM
            for x in cidades_dia[d[0]])

    def marcar(d, c):
        carga[d[0]] += 1
        semanas[c["CHAVE_CLIENTE"]].add(d[2])
        no_dia[d[0]].add(c["CHAVE_CLIENTE"])
        cidades_dia[d[0]].add((c["UF"], c["CIDADE"]))
        return d

    def colocar(c, forcar=False):
        ch = c["CHAVE_CLIENTE"]
        while ptr[0] < len(dias) and carga[dias[ptr[0]][0]] >= \
                teto[dias[ptr[0]][0]]:
            ptr[0] += 1
        # a cidade longe fecha o dia corrente: a viagem comeca no seguinte
        if ptr[0] < len(dias) and pode(dias[ptr[0]], c) and \
                not perto_do_dia(dias[ptr[0]], c):
            ptr[0] += 1
        for j in range(ptr[0], len(dias)):
            d = dias[j]
            if carga[d[0]] >= teto[d[0]] or ch in no_dia[d[0]] or \
                    d[2] in semanas[ch] or not pode(d, c) or \
                    not perto_do_dia(d, c):
                continue
            return marcar(d, c)
        if forcar:              # a 1a visita nunca fica de fora
            livres = [d for d in dias if ch not in no_dia[d[0]]
                      and pode(d, c)] or \
                [d for d in dias if ch not in no_dia[d[0]]] or dias
            # sem lugar "de direito": o dia cujas cidades ficam mais perto
            # da cidade do cliente (e, empatando, o mais vazio)
            pc = geo.coordenada(c["UF"], c["CIDADE"])

            def longe(x):
                if not cidades_dia[x[0]] or pc is None:
                    return 0.0 if not cidades_dia[x[0]] else 1e6
                return min(geo.distancia_km(pc, geo.coordenada(*k) or pc)
                           for k in cidades_dia[x[0]])
            d = min(livres, key=lambda x: (carga[x[0]] >= teto[x[0]],
                                           not perto_do_dia(x, c),
                                           round(longe(x)),
                                           carga[x[0]] - teto[x[0]], x[0]))
            return marcar(d, c)
        return None
    # (17/10) A VISITA SEMANAL ENTRA ANTES DE TODO MUNDO, SEMANA A SEMANA:
    # em cada semana os clientes semanais (na ordem do caminho) enchem os
    # dias daquela semana em sequencia - a mesma rota se repete toda
    # semana. So depois a carteira comum ocupa o lugar que sobrou.
    semanais = [c for c in lista if c.get("VISITA_SEMANAL") == "SIM"]
    visitas_sem = defaultdict(list)
    if semanais:
        por_semana = defaultdict(list)
        for d in dias:
            por_semana[d[2]].append(d)
        for w in sorted(por_semana):
            ds, k = por_semana[w], 0
            for c in semanais:
                ch = c["CHAVE_CLIENTE"]
                while k < len(ds) and carga[ds[k][0]] >= teto[ds[k][0]]:
                    k += 1
                for jj in range(k, len(ds)):
                    d = ds[jj]
                    if carga[d[0]] >= teto[d[0]] or ch in no_dia[d[0]] or \
                            w in semanas[ch] or not pode(d, c) or \
                            not perto_do_dia(d, c):
                        continue
                    visitas_sem[ch].append(marcar(d, c))
                    break
    primeiras, repetidas = [], []
    for c in semanais:
        vs = visitas_sem.get(c["CHAVE_CLIENTE"])
        if vs:
            primeiras.append((c, vs[0]))
            repetidas += [(c, d) for d in vs[1:]]
    ptr[0] = 0
    primeiras += [(c, colocar(c, forcar=True)) for c in lista
                  if c.get("VISITA_SEMANAL") != "SIM"
                  or not visitas_sem.get(c["CHAVE_CLIENTE"])]
    resta = {c["CHAVE_CLIENTE"]: plano.get(c["CHAVE_CLIENTE"], (1, 0))[0] - 1
             for c in lista}
    for c in semanais:                  # a semanal ja teve as voltas dela
        if visitas_sem.get(c["CHAVE_CLIENTE"]):
            resta[c["CHAVE_CLIENTE"]] = 0
    perto = set()
    for c in lista:
        lat, lon, _p = geo.ponto_do_cliente(c)
        if base_pt is None or lat is None or \
                geo.distancia_km(base_pt, (lat, lon)) <= RAIO_DO_COMPLETAR_KM:
            perto.add(c["CHAVE_CLIENTE"])
    # as voltas seguintes, NA MESMA ORDEM: quem a curva pede de novo e quem
    # mora perto da base (encher o dia), ate acabar o lugar
    while True:
        andou = False
        for c in lista:
            ch = c["CHAVE_CLIENTE"]
            if resta[ch] <= 0 and ch not in perto:
                continue
            if resta[ch] <= 0 and not any(carga[d[0]] < teto[d[0]]
                                          for d in dias):
                continue
            d = colocar(c)
            if resta[ch] > 0:
                resta[ch] -= 1
            if d:
                repetidas.append((c, d))
                andou = True
        if not andou:
            break
    return primeiras, repetidas


def _fatiar_agenda(agenda: list, pesos: list) -> list:
    """
    Reparte os dias da agenda entre varios grupos, na proporcao do peso de
    cada um (a carteira). Cada grupo fica com dias SEGUIDOS - e o que
    impede o vendedor de ir a Manaus na segunda e a Boa Vista na terca e a
    Manaus de novo na quarta.
    """
    total = sum(pesos) or 1
    fatias, inicio, n = [], 0, len(agenda)
    for i, _ in enumerate(pesos):
        if i == len(pesos) - 1:
            fim = n
        else:
            fim = int(round(sum(pesos[:i + 1]) / total * n))
            # cada grupo leva pelo menos um dia, e sobra dia para os outros
            fim = max(inicio + 1, min(fim, n - (len(pesos) - i - 1)))
        fatias.append(agenda[inicio:fim] or [agenda[min(inicio, n - 1)]])
        inicio = max(fim, inicio)
    return fatias


# --------------------------------------------------------------------------
# A ROTA SEMANAL DA ZONA
# --------------------------------------------------------------------------
# No cadastro da zona (aba 3) a caixa SEMANA DA ROTA diz, semana a semana,
# quais cidades o vendedor roda e EM QUE ORDEM. Fica guardada na propria
# zona, em z["rota_semanal"], assim:
#     {"1": [{"cidade": "MA|IMPERATRIZ", "dia": null}],
#      "2": [{"cidade": "MA|AMARANTE", "dia": 1}, ...]}
# com dia = 0 segunda ... 5 sabado, ou null (o programa escolhe). Cidade
# que nao esta em caixa nenhuma continua no automatico, encadeada pela
# cidade vizinha, como sempre foi.
#
# E O CALENDARIO COMERCIAL DO VENDEDOR, escrito no programa: "semana 1 em
# Imperatriz; semana 2 Amarante, Buritirana, Gov. Edson Lobao..." A mesma
# cidade pode entrar em mais de uma semana - a cidade-base entra em todas,
# e a carteira dela se reparte entre elas.
#
# QUATRO REGRAS, combinadas:
#   1. a ORDEM dentro da caixa e a ordem da visita. A primeira cidade abre
#      a semana; cada uma enche o dia ate o teto de visitas e a proxima
#      continua no mesmo dia se couber, ou no dia seguinte;
#   2. DIA FIXO e excecao, para a cidade que so rende num dia certo. Sem
#      ele a rota se arruma sozinha quando cai feriado;
#   3. semana ou dia que nao existem no mes (semana 5 num mes de 4, dia
#      que caiu em feriado) vao para o mais PROXIMO, e o programa registra
#      no log o que foi deslocado;
#   4. o que voce marcou A MAO no analitico, cliente por cliente, continua
#      mandando mais que isto.
#
# A agenda antiga ({"PA|CASTANHAL": {"semana": 1, "dia": 1}}) continua
# sendo lida e escrita, para zona cadastrada antes desta caixa nao perder
# nada - mas quem manda, quando existe, e a rota semanal.
DIAS_DA_SEMANA_PT = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado"]


def chave_da_cidade(uf, cidade) -> str:
    return f"{norm(uf)}|{norm(cidade)}"


SEMANAS_DA_ROTA = 6          # nenhum mes tem mais que seis semanas


def semanas_do_mes(mes: str, feriados=None) -> list:
    """[1, 2, 3, 4] - as semanas que o mes realmente tem."""
    return sorted({d[2] for d in dias_do_mes(mes, feriados or [])})


def rota_semanal_da_zona(zona: dict) -> dict:
    """
    A ROTA DA ZONA SEMANA A SEMANA:

        {1: [{'cidade': 'MA|IMPERATRIZ', 'dia': None}, ...], 2: [...]}

    A ordem da lista E a ordem da visita: a primeira cidade abre a
    semana. `dia` e a excecao - 0 segunda ... 5 sabado - para a cidade
    que so rende num dia certo; None deixa o programa escolher.

    A MESMA CIDADE PODE ENTRAR EM MAIS DE UMA SEMANA. E o caso da
    cidade-base, que o vendedor roda toda semana: a carteira dela se
    reparte entre as semanas em que ela aparece.

    Zona que ainda nao tem rota semanal cai na agenda antiga
    ({cidade: {semana, dia}}), lida como se fosse uma rota - assim quem
    ja tinha dia marcado nao perde nada ao atualizar o programa.
    """
    bruto = zona.get("rota_semanal")
    rota = {}
    if isinstance(bruto, dict):
        for sem, itens in bruto.items():
            try:
                n = int(sem)
            except (TypeError, ValueError):
                continue
            if not 1 <= n <= SEMANAS_DA_ROTA or not isinstance(itens, list):
                continue
            lista = []
            for it in itens:
                if isinstance(it, str):
                    it = {"cidade": it}
                if not isinstance(it, dict):
                    continue
                cidade = str(it.get("cidade") or "").strip().upper()
                if "|" not in cidade:
                    continue
                dia = it.get("dia")
                try:
                    dia = (None if dia is None or str(dia).strip() == ""
                           else int(dia))
                except (TypeError, ValueError):
                    dia = None
                if dia is not None and not 0 <= dia <= 5:
                    dia = None
                lista.append({"cidade": cidade, "dia": dia})
            if lista:
                rota[n] = lista
    return rota or _rota_da_agenda_velha(zona)


def _rota_da_agenda_velha(zona: dict) -> dict:
    """A agenda antiga ({cidade: {semana, dia}}) lida como rota semanal."""
    rota = {}
    for chave, marca in dias_marcados_da_zona(zona).items():
        if not isinstance(marca, dict):
            continue
        sem, dia = marca.get("semana"), marca.get("dia")
        if sem is None and dia is None:
            continue
        rota.setdefault(int(sem) if sem is not None else 1, []).append(
            {"cidade": chave, "dia": None if dia is None else int(dia)})
    for itens in rota.values():
        # sem ordem guardada, a do dia marcado e a melhor que existe
        itens.sort(key=lambda it: (99 if it["dia"] is None else it["dia"],
                                   it["cidade"]))
    return rota


def gravar_rota_semanal(zona: dict, rota: dict) -> dict:
    """
    Guarda a rota na zona e deixa a agenda antiga coerente com ela.

    A agenda continua sendo escrita de proposito: ela e o que uma copia
    mais velha do programa - ou qualquer leitura que ainda chame
    dias_marcados_da_zona - vai encontrar. Nela cabe uma semana so por
    cidade, entao fica a PRIMEIRA em que a cidade aparece.
    """
    limpa = {}
    for sem, itens in (rota or {}).items():
        lista = [{"cidade": it["cidade"],
                  "dia": (None if it.get("dia") is None else int(it["dia"]))}
                 for it in (itens or []) if it.get("cidade")]
        if lista:
            limpa[str(int(sem))] = lista
    zona["rota_semanal"] = limpa
    agenda = {}
    for sem in sorted(limpa, key=int):
        for it in limpa[sem]:
            if it["cidade"] in agenda:
                continue
            marca = {"semana": int(sem)}
            if it["dia"] is not None:
                marca["dia"] = int(it["dia"])
            agenda[it["cidade"]] = marca
    zona["agenda"] = agenda
    return limpa


def dias_marcados_da_zona(zona: dict) -> dict:
    """
    {'UF|CIDADE': {'semana': n, 'dia': n}} da zona, sempre um dicionario.

    O nome NAO e agenda_da_zona: ja existe uma com esse nome, mais acima,
    que devolve os DIAS em que a zona e rodada. Duas funcoes com o mesmo
    nome no mesmo arquivo - a segunda apaga a primeira em silencio, e o
    erro so aparece quando alguem chama a de cima.
    """
    agenda = zona.get("agenda")
    return agenda if isinstance(agenda, dict) else {}


def _dias_por_semana(dias: list) -> dict:
    """{1: [dias da semana 1], 2: [...]} a partir da agenda do vendedor."""
    saida = {}
    for d in dias:
        saida.setdefault(int(d[2]), []).append(d)
    return saida


def _semana_que_existe(dias_sem: dict, semana: int):
    """
    A semana pedida, ou a mais perto que o mes tem.

    Devolve (semana, trocou). Montar a rota numa semana 5 e abrir o
    Planner num mes de quatro nao pode apagar as cidades daquela caixa
    em silencio - elas vao para a semana mais proxima e o log avisa.
    """
    if not dias_sem:
        return None, False
    if semana in dias_sem:
        return semana, False
    return min(dias_sem, key=lambda s: (abs(s - semana), s)), True


def _repartir_pelas_vezes(grupo: list, vezes: int) -> list:
    """
    Os clientes de uma cidade divididos entre as semanas em que ela entra.

    Em pedacos SEGUIDOS, nao intercalados: a lista ja vem na ordem
    geografica (bairro por bairro), entao o vendedor continua fechando
    um pedaco da cidade de cada vez.
    """
    vezes = max(1, int(vezes))
    n = len(grupo)
    return [grupo[i * n // vezes:(i + 1) * n // vezes] for i in range(vezes)]


def _colocar_com_semanas(dentro: list, fatia: list, cap: int, rota: dict,
                         interior: bool, avisos: list,
                         agenda_vend: list = None) -> list:
    """
    A 1a visita numa zona QUE TEM ROTA SEMANAL montada no cadastro.

    A caixa SEMANA DA ROTA diz, para cada semana, quais cidades o
    vendedor roda e em que ordem. Aqui essa ordem vira dia:

      - a primeira cidade da semana abre a segunda-feira;
      - cada cidade enche o dia ate o teto de visitas e a proxima
        continua no mesmo dia se ainda couber, ou no dia seguinte;
      - cidade com DIA FIXO pula para aquele dia da semana (ou o mais
        perto, quando o mes nao tem - e o log avisa);
      - cidade que nao esta em caixa nenhuma fica no automatico, nos
        dias que sobraram.

    As semanas sao procuradas no MES INTEIRO do vendedor, nao so na
    fatia desta zona: dizer "IMPERATRIZ na semana 1" quer dizer que o
    vendedor esta la naquela semana, entao aqueles dias passam a ser
    desta zona.
    """
    procurar_em = agenda_vend or fatia
    dias_sem = _dias_por_semana(procurar_em)
    if not dias_sem or not rota:
        return []
    vezes = Counter(it["cidade"] for itens in rota.values() for it in itens)
    grupos, livres = {}, []
    for c in dentro:
        chave = chave_da_cidade(c["UF"], c["CIDADE"])
        if chave in vezes:
            grupos.setdefault(chave, []).append(c)
        else:
            livres.append(c)
    if not grupos:
        return []
    pedacos = {ch: _repartir_pelas_vezes(g, vezes[ch])
               for ch, g in grupos.items()}
    gastos = Counter()
    carga = Counter()
    colocacao, dias_usados = [], set()
    for semana in sorted(rota):
        alvo, trocou = _semana_que_existe(dias_sem, int(semana))
        if alvo is None:
            continue
        dias = dias_sem[alvo]
        if trocou and rota[semana]:
            avisos.append(f"semana {semana} nao existe neste mes - as "
                          f"{len(rota[semana])} cidade(s) dela foram para a "
                          f"semana {alvo}")
        cursor = 0
        for it in rota[semana]:
            chave = it["cidade"]
            fatiado = pedacos.get(chave)
            if not fatiado:
                continue
            i = gastos[chave]
            gastos[chave] += 1
            grupo = fatiado[i] if i < len(fatiado) else []
            if not grupo:
                continue
            if it.get("dia") is not None:
                querido = int(it["dia"])
                melhor = min(dias, key=lambda d: (abs(d[0].weekday() - querido),
                                                  d[0]))
                if melhor[0].weekday() != querido:
                    avisos.append(
                        f"{chave.replace('|', ' / ')}: pedi "
                        f"{DIAS_DA_SEMANA_PT[querido]} na semana {semana}, "
                        f"nao existe no mes - ficou {melhor[1]} dia "
                        f"{melhor[0].day}")
                cursor = dias.index(melhor)
            cursor = min(cursor, len(dias) - 1)
            for c in grupo:
                while cap and cursor < len(dias) - 1 \
                        and carga[dias[cursor][0]] >= cap:
                    cursor += 1
                dia = dias[cursor]
                carga[dia[0]] += 1
                colocacao.append((c, dia))
                dias_usados.add(dia[0])
            if not cap:
                # SEM TETO POR DIA cada cidade fica com um dia so dela:
                # senao a semana inteira cairia na segunda-feira
                cursor = min(cursor + 1, len(dias) - 1)
            elif carga[dias[cursor][0]] >= cap:
                cursor = min(cursor + 1, len(dias) - 1)

    if livres:
        sobra = [d for d in fatia if d[0] not in dias_usados] or list(fatia)
        if interior:
            colocacao += _agenda_por_cidade(livres, sobra, cap)
        else:
            n, nd = len(livres), len(sobra)
            colocacao += [(c, sobra[min(i * nd // n, nd - 1)])
                          for i, c in enumerate(livres)]
    return colocacao


def _agenda_por_cidade(lista: list, fatia: list, cap: int,
                       cap_de=None) -> list:
    """
    A rota do VENDEDOR DO INTERIOR: UM DIA, UMA CIDADE SO.

    A lista ja vem na ordem geografica (cidade vizinha depois de cidade
    vizinha), entao as cidades saem na ordem em que ela as traz. Cada
    cidade fica com dias SEGUIDOS, quantos precisar para caber no teto de
    visitas por dia; cidade pequena fecha num dia so e o vendedor segue
    para a proxima no dia seguinte.

    Devolve [(cliente, dia)].
    """
    grupos = []
    for c in lista:
        chave = (c["UF"], c["CIDADE"])
        if grupos and grupos[-1][0] == chave:
            grupos[-1][1].append(c)
        else:
            grupos.append((chave, [c]))
    n_dias = len(fatia)
    if not grupos or not n_dias:
        return []

    # o teto MEDIO dos dias (a sexta de prospeccao tem teto menor)
    cap_med = (sum(cap_de(d[0]) for d in fatia) / len(fatia)
               if cap_de and cap and fatia else cap)

    def _precisa(gs):
        return [max(1, math.ceil(len(g) / cap_med)) if cap else 1
                for _, g in gs]

    # Mais cidades do que dias (ou cidade grande comendo o mes): nao da
    # para dar um dia inteiro a cada uma. Em vez de estourar o teto, as
    # cidades PEQUENAS E VIZINHAS sao juntadas num dia so - elas ja vem
    # lado a lado na ordem geografica, entao o vendedor continua sem ir e
    # voltar. A cidade grande nunca perde os dias dela.
    while sum(_precisa(grupos)) > n_dias and len(grupos) > 1:
        i = min(range(len(grupos) - 1),
                key=lambda k: len(grupos[k][1]) + len(grupos[k + 1][1]))
        juntos = grupos[i][1] + grupos[i + 1][1]
        grupos[i:i + 2] = [(grupos[i][0], juntos)]

    precisa = _precisa(grupos)
    # sobrou dia no mes: o dia extra vai para a cidade mais carregada, uma
    # de cada vez, ate acabarem os dias - assim o vendedor nao trabalha 8
    # dias no teto e fica 14 parado
    for _ in range(max(0, n_dias - sum(precisa))):
        i = max(range(len(grupos)),
                key=lambda k: (len(grupos[k][1]) / precisa[k], -k))
        precisa[i] += 1

    saida, inicio = [], 0
    for (_, grupo), q in zip(grupos, precisa):
        dias_da = fatia[inicio:inicio + q] or [fatia[min(inicio, n_dias - 1)]]
        inicio = min(inicio + q, n_dias)
        saida += _por_peso(grupo, dias_da, [
            (cap_de(d[0]) if cap_de else cap) or 1 for d in dias_da])
    return saida


def ordem_das_zonas(cfg: dict, zonas: list, clientes_por_zona: dict,
                    partida=None) -> list:
    """
    Em que ordem o vendedor roda as zonas dele: pela cidade de maior
    carteira de cada zona, indo sempre para a mais proxima da anterior.
    """
    if len(zonas) < 2:
        return list(zonas)
    principal = {}
    for z in zonas:
        conta = Counter((c["UF"], c["CIDADE"])
                        for c in clientes_por_zona.get(z["id"], []))
        principal[z["id"]] = conta.most_common(1)[0][0] if conta else ("", "")
    caminho = geo.ordenar_cidades(sorted(set(principal.values())), partida)
    posicao = {cid: i for i, cid in enumerate(caminho)}
    return sorted(zonas, key=lambda z: (posicao.get(principal[z["id"]], 9999),
                                        z.get("codigo") or z["id"]))


# ==========================================================================
# A ROTA POR CIDADE (aba 4): o calendario do vendedor
# ==========================================================================
# Para cada vendedor, o Analista arrasta as cidades para os dias do mes:
#     cfg["rota_cidade"] = {cod_vendedor: {"2026-10-05": ["MA|IMPERATRIZ"]}}
# A configuracao e do MES (o Planner e mes a mes), entao as datas tambem.
# Vendedor com calendario montado tem a rota TODA saindo dele:
#   1) a 1a visita: os clientes de cada cidade se dividem POR IGUAL entre
#      os dias em que a cidade esta (na ordem geografica);
#   2) cidade que ficou SEM DIA vai, no automatico, para os dias do
#      vendedor que ficaram sem cidade nenhuma;
#   3) cada dia e completado ate o teto de visitas com os clientes das
#      cidades daquele dia que menos foram visitados (curva mais alta
#      primeiro) - e assim que os mesmos clientes se repetem quando a
#      cidade tem menos cliente que dia. Nunca duas vezes no mesmo dia.
# Vendedor sem calendario continua na rota automatica de sempre.
def rota_cidade_do_vendedor(cfg: dict, cod: str) -> dict:
    """{data ISO: [chave da cidade]} do vendedor, so do mes do Planner."""
    mes = cfg.get("mes") or ""
    cal = ((cfg.get("rota_cidade") or {}).get(texto(cod)) or {})
    return {d: [c for c in chs if c] for d, chs in cal.items()
            if str(d).startswith(mes) and chs}


def gravar_rota_cidade(cfg: dict, cod: str, cal: dict) -> None:
    limpo = {d: list(dict.fromkeys(chs)) for d, chs in (cal or {}).items()
             if chs}
    todos = cfg.setdefault("rota_cidade", {})
    if limpo:
        todos[texto(cod)] = limpo
    else:
        todos.pop(texto(cod), None)


def cidades_fora_da_rota(cfg: dict, cod: str) -> set:
    """As cidades que o Alexandre TIROU da rota do vendedor neste mes
    (clique na cidade no calendario da aba Rota por cidade): os clientes
    delas ficam sem visita no mes."""
    return set((cfg.get("rota_cidade_fora") or {}).get(texto(cod)) or [])


def gravar_cidades_fora(cfg: dict, cod: str, fora) -> None:
    todos = cfg.setdefault("rota_cidade_fora", {})
    fora = sorted({c for c in (fora or []) if c})
    if fora:
        todos[texto(cod)] = fora
    else:
        todos.pop(texto(cod), None)


def fora_da_rota(cfg: dict, cliente: dict, cod: str, fora=None) -> bool:
    """O cliente esta numa cidade tirada da rota do vendedor? O cliente
    trazido a mao para um dia (excecao com dia fixo) continua na rota."""
    fora = cidades_fora_da_rota(cfg, cod) if fora is None else fora
    if not fora:
        return False
    if chave_da_cidade(cliente.get("UF"), cliente.get("CIDADE")) not in fora:
        return False
    return not excecao_do_cliente(cfg, cliente).get("dia")


def clientes_do_vendedor(cfg: dict, clientes: list, cod: str) -> list:
    """[(cliente, zona)] da carteira do vendedor - a mesma conta da rota."""
    zonas = {z["id"]: z for z in cfg["zonas"]}
    saida = []
    for c in clientes:
        zid = zona_do_cliente(cfg, c)
        if not zid or zid not in zonas:
            continue
        if vendedor_do_cliente(cfg, c, zonas) == texto(cod) and \
                not cliente_inativo(cfg, c):
            saida.append((c, zonas[zid]))
    return saida


def cidades_do_vendedor(cfg: dict, clientes: list, cod: str) -> list:
    """Todas as cidades da carteira, da maior para a menor."""
    conta = Counter()
    nome = {}
    for c, _z in clientes_do_vendedor(cfg, clientes, cod):
        ch = chave_da_cidade(c["UF"], c["CIDADE"])
        conta[ch] += 1
        nome[ch] = (c["UF"], c["CIDADE"])
    return [{"chave": ch, "uf": nome[ch][0], "cidade": nome[ch][1],
             "clientes": n} for ch, n in
            sorted(conta.items(), key=lambda kv: (-kv[1], kv[0]))]


def _teto_do_vendedor(cfg: dict, zonas_dele) -> int:
    par = cfg["parametros"]
    tetos = [int(z.get("visitas_por_dia") or 0) for z in zonas_dele]
    return max([t for t in tetos if t] or [int(par.get("visitas_por_dia")
                                               or 0)])


# a cidade fora da agenda e longe disso de todas as cidades do calendario:
# vai primeiro para o dia em branco (07/10)
LIMITE_KM_AGENDA = 80


def _rota_pelo_calendario(cfg, cod_vend, v, lista_zc, dias_mes, agenda_vend,
                          cap, base_vendedor, avisos, restritos=frozenset(),
                          na_base=None):
    """
    A rota do vendedor que tem calendario montado na aba ROTA POR CIDADE.
    Devolve (linhas, previa) - previa = {(data ISO, cidade): [novos, rep]}.
    (17/10) restritos/na_base: a REGRA DA CIDADE BASE manda nos primeiros
    dias uteis - a cidade de fora da regiao da base sai desses dias e a
    cidade base entra (salvo a data liberada pela agenda importada).
    """
    cal = calendario_com_a_base(cfg, cod_vend, v, dias_mes, restritos,
                                na_base, avisos)
    dia_de = {d[0].isoformat(): d for d in dias_mes}
    for iso in sorted(cal):
        if iso not in dia_de:
            avisos.append(f"{cod_vend}: {iso} nao e dia de rota (domingo ou "
                          f"feriado) - as cidades desse dia ficaram de fora")
    cidades_no_dia = {dia_de[iso]: chs for iso, chs in cal.items()
                      if iso in dia_de}
    dias_da_cidade = defaultdict(list)
    for d in sorted(cidades_no_dia, key=lambda x: x[0]):
        for ch in cidades_no_dia[d]:
            dias_da_cidade[ch].append(d)

    em_ordem = ordem_geografica(cfg, [c for c, _ in lista_zc], base_vendedor)
    zona_de = {c["CHAVE_CLIENTE"]: z for c, z in lista_zc}
    grupos = defaultdict(list)
    for c in em_ordem:
        grupos[chave_da_cidade(c["UF"], c["CIDADE"])].append(c)

    visitas = defaultdict(list)                 # cliente -> [dia]
    carga = Counter()
    previa = defaultdict(lambda: [0, 0])
    do_dia = defaultdict(set)                   # dia -> clientes do dia
    clientes_do_dia = defaultdict(list)         # dia -> quem pode repetir

    def por(c, d, repetida=False):
        visitas[c["CHAVE_CLIENTE"]].append(d)
        carga[d[0]] += 1
        do_dia[d[0]].add(c["CHAVE_CLIENTE"])
        previa[(d[0].isoformat(), chave_da_cidade(c["UF"], c["CIDADE"]))][
            1 if repetida else 0] += 1

    # O TETO MANDA (06/10): cada dia recebe no maximo o teto dele (12; a
    # sexta, 6). A cidade do dia divide o teto com as outras cidades do
    # mesmo dia; quem nao cabe no teto dos dias da cidade sai pela ordem
    # da carteira (curva S, A, B, C, Z e o faturamento) e vai para o
    # sabado do deposito (parametro do excedente em SIM) ou fica sem
    # visita no mes. O cliente com dia marcado a mao entra sempre.
    par_ = cfg["parametros"]

    def teto_d(d):
        return teto_do_dia(cap, d[0], par_) if cap else 0
    forcado = {c["CHAVE_CLIENTE"]: _dia_forcado(cfg, c, agenda_vend)
               for c in em_ordem}

    def prioridade(c):
        return (_peso_fila(c),
                -c.get("RECEITA_6M", 0.0), c["CHAVE_CLIENTE"])
    liberadas = liberadas_do_vendedor(cfg, cod_vend)

    def escolher(itens, vagas):
        if not cap:
            return itens, []
        dentro, fora, usado = set(), [], 0
        for c in sorted(itens, key=prioridade):
            k = c["CHAVE_CLIENTE"]
            if forcado.get(k) is None and usado >= vagas:
                fora.append(c)
                continue
            dentro.add(k)
            usado += 1
        return [c for c in itens if c["CHAVE_CLIENTE"] in dentro], fora
    peso_dia = defaultdict(dict)           # cidade -> {data: parte do teto}
    for d, chs in cidades_no_dia.items():
        for ch in chs:
            peso_dia[ch][d[0]] = teto_d(d) / max(len(chs), 1)
    excedentes = []

    # 1) a 1a visita, cidade por cidade, dividida pelos dias dela
    sem_dia = []
    for ch, itens in grupos.items():
        ds = dias_da_cidade.get(ch)
        if not ds:
            sem_dia += itens
            continue
        itens, sobra = escolher(itens, int(sum(peso_dia[ch].values())
                                           + 1e-9))
        excedentes += sobra
        for c, d0 in _por_peso(itens, ds, [peso_dia[ch].get(d[0]) or 1
                                           for d in ds]):
            d = forcado.get(c["CHAVE_CLIENTE"]) or d0
            por(c, d)
        for d in ds:
            clientes_do_dia[d[0]] += itens

    # 2) CIDADE SEM DIA (07/10): POR PROXIMIDADE - vai para o dia cuja
    #    cidade fica mais perto e ainda tem vaga no teto. Cidade longe de
    #    tudo (mais de LIMITE_KM_AGENDA) usa primeiro os dias em branco.
    #    O que nao couber em lugar nenhum e excedente (1o sabado).
    if sem_dia:
        livres = [d for d in agenda_vend if d not in cidades_no_dia]
        com_cidade = [d for d in agenda_vend if d in cidades_no_dia]
        pontos = {}
        for d in com_cidade:
            pts = []
            for ch in cidades_no_dia[d]:
                uf_, _, cid_ = ch.partition("|")
                p_ = geo.coordenada(uf_, cid_)
                if p_:
                    pts.append(p_)
            pontos[d[0]] = pts
        grupos_sem = defaultdict(list)
        for c in sem_dia:                       # ja na ordem geografica
            grupos_sem[(c["UF"], c["CIDADE"])].append(c)
        colocados = 0
        for (uf_, cid_), itens in sorted(grupos_sem.items(),
                                         key=lambda kv: -len(kv[1])):
            p_ = geo.coordenada(uf_, cid_)

            def km_ate(d, p_=p_):
                pts = pontos.get(d[0]) or []
                if not p_ or not pts:
                    return None
                return min(geo.distancia_km(p_, q) for q in pts)
            perto = sorted(((km_ate(d), d) for d in com_cidade),
                           key=lambda kd: (kd[0] is None, kd[0] or 0,
                                           carga[kd[1][0]], kd[1][0]))
            em_branco = sorted(livres, key=lambda d: (carga[d[0]], d[0]))
            longe = not perto or perto[0][0] is None or \
                perto[0][0] > LIMITE_KM_AGENDA
            ordem = ([d for d in em_branco] + [d for _k, d in perto]
                     if longe else [d for _k, d in perto] + em_branco)
            if not ordem:
                ordem = sorted(agenda_vend, key=lambda d: (carga[d[0]], d[0]))
            for c in sorted(itens, key=prioridade):
                d_fix = forcado.get(c["CHAVE_CLIENTE"])
                if d_fix is not None:
                    por(c, d_fix)
                    clientes_do_dia[d_fix[0]].append(c)
                    continue
                alvo = next((d for d in ordem
                             if (not cap or carga[d[0]] < teto_d(d))
                             and (na_base is None or d[0] not in restritos
                                  or d[0].isoformat() in liberadas
                                  or na_base(c))), None)
                if alvo is None:
                    excedentes.append(c)
                    continue
                por(c, alvo)
                clientes_do_dia[alvo[0]].append(c)
                colocados += 1
        if colocados:
            avisos.append(f"{cod_vend}: {colocados} cliente(s) de cidade sem "
                          f"dia na agenda - encaixados no dia mais perto")

    # quem nao coube no teto: o sabado do deposito ou sem visita
    sabados = [d for d in dias_mes if d[3]]
    deposito = sabados[0] if sabados and any(
        excedente_no_sabado(cfg, z) for _, z in lista_zc) else None
    if excedentes:
        if deposito is not None:
            for c in excedentes:
                por(c, deposito)
            avisos.append(f"{cod_vend}: {len(excedentes)} cliente(s) nao "
                          f"couberam no teto dos dias - foram para o sabado "
                          f"{deposito[0]:%d/%m} (excedente)")
        else:
            avisos.append(f"{cod_vend}: {len(excedentes)} cliente(s) nao "
                          f"couberam no teto dos dias - ficaram sem visita "
                          f"no mes")

    # 3) o dia completado ate o teto: os mesmos clientes se repetem
    if cap:
        for d in sorted(set(cidades_no_dia) | {x for vs in visitas.values()
                                               for x in vs},
                        key=lambda x: x[0]):
            vagas = teto_do_dia(cap, d[0], cfg["parametros"]) - carga[d[0]]
            if vagas <= 0:
                continue
            vistos = set()
            fila = []
            for c in clientes_do_dia.get(d[0], []):
                ch = c["CHAVE_CLIENTE"]
                if ch in vistos or ch in do_dia[d[0]]:
                    continue
                # nunca 2x na mesma semana (06/10)
                if any(x[2] == d[2] for x in visitas[ch]):
                    continue
                vistos.add(ch)
                fila.append(c)
            fila.sort(key=lambda c: (c.get("VISITA_SEMANAL") != "SIM",
                                     len(visitas[c["CHAVE_CLIENTE"]]),
                                     _peso_fila(c),
                                     -c.get("RECEITA_6M", 0.0),
                                     c["CHAVE_CLIENTE"]))
            for c in fila[:vagas]:
                por(c, d, repetida=True)

    linhas = []
    for c in em_ordem:
        dias_dele = sorted(visitas.get(c["CHAVE_CLIENTE"], []),
                           key=lambda x: x[0])
        z = zona_de[c["CHAVE_CLIENTE"]]
        for i, d in enumerate(dias_dele, start=1):
            linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v, d,
                                         i, len(dias_dele)))
    # as regras da semana (cliente 1x por semana, sexta com o teto dela)
    par_ = cfg["parametros"]
    pode_ = None
    if na_base is not None and restritos:
        def pode_(l, x):
            return x not in restritos or x.isoformat() in liberadas or \
                na_base(l)
    _regras_da_semana(cfg, linhas, 0, dias_mes, par_,
                      lambda x: teto_do_dia(cap, x, par_),
                      mover_primeira=False, pode=pode_)
    if cap:
        _teto_duro(linhas, dias_mes, lambda x: teto_do_dia(cap, x, par_),
                   {k for k, d in forcado.items() if d is not None},
                   deposito[0] if deposito is not None else None)
    _numerar(linhas, 0)
    previa = defaultdict(lambda: [0, 0])
    for l in linhas:
        previa[(l["DATA"].isoformat(), chave_da_cidade(l["UF"], l["CIDADE"]))][
            0 if l["VISITA_NO_MES"] == 1 else 1] += 1
    return linhas, dict(previa)


def calendario_com_a_base(cfg, cod, v, dias_mes, restritos=frozenset(),
                          na_base=None, avisos=None) -> dict:
    """(17/10) O calendario da Rota por cidade com a REGRA DA CIDADE BASE:
    nos primeiros dias uteis so fica cidade da regiao da base (a cidade
    base entra quando nao sobra nenhuma). A data que a AGENDA IMPORTADA
    liberou fica como foi importada."""
    cal = rota_cidade_do_vendedor(cfg, cod)
    if not cal or na_base is None or not restritos:
        return cal
    lib = liberadas_do_vendedor(cfg, cod)
    base_ch = chave_da_cidade(v.get("uf_base", ""), v.get("cidade_base", ""))
    cal = dict(cal)
    tirou = Counter()
    for d in dias_mes:
        iso = d[0].isoformat()
        if d[0] not in restritos or iso in lib:
            continue
        chs = cal.get(iso) or []
        ficam = []
        for ch in chs:
            uf_, _, cid_ = ch.partition("|")
            if na_base({"UF": uf_, "CIDADE": cid_}):
                ficam.append(ch)
            else:
                tirou[cid_ or ch] += 1
        cal[iso] = ficam or [base_ch]
    if tirou and avisos is not None:
        avisos.append(
            f"{cod}: regra da cidade base - nos {len(restritos)} primeiros "
            f"dias uteis o calendario ficou com {v.get('cidade_base', '')}; "
            f"sairam desses dias: " + ", ".join(
                f"{k} ({n}d)" for k, n in sorted(tirou.items())))
    return cal


def regra_da_base_do_vendedor(cfg, cod) -> tuple:
    """(datas da cidade base, f(cliente) regiao da base, datas liberadas)
    do vendedor no mes do Planner - para a aba Rota por cidade."""
    v = pessoa_por_codigo(cfg, cod) or {}
    dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    restritos = dias_da_cidade_base(dias, cfg["parametros"])
    nb = regiao_da_base(v, cfg["parametros"]) if restritos else None
    return (restritos if nb is not None else frozenset()), nb, \
        liberadas_do_vendedor(cfg, cod)


def calendario_efetivo(cfg, cod) -> dict:
    """O calendario como a rota usa: com a REGRA DA CIDADE BASE aplicada."""
    v = pessoa_por_codigo(cfg, cod) or {}
    dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    restritos, nb, _lib = regra_da_base_do_vendedor(cfg, cod)
    return calendario_com_a_base(cfg, cod, v, dias, restritos, nb)


def cidade_aceita_no_dia(cfg, cod, chave, iso) -> bool:
    """A cidade pode ir para o dia? Nos primeiros dias uteis so a regiao
    da cidade base (salvo a data liberada pela agenda importada)."""
    restritos, nb, lib = regra_da_base_do_vendedor(cfg, cod)
    d = data_de(iso)
    if nb is None or d not in restritos or str(iso) in lib:
        return True
    uf_, _, cid_ = str(chave).partition("|")
    return nb({"UF": uf_, "CIDADE": cid_})


def _teto_duro(linhas, dias_mes, cap_de, marcados, deposito):
    """Nenhum dia acima do teto (06/10) - o que sobrar de arredondamento:
    sai primeiro a visita repetida (curva mais baixa); a 1a visita vai para
    outro dia da mesma cidade com lugar (sem repetir a semana) ou, nao
    havendo, para o sabado do deposito - sem ele, sai. O cliente com dia
    marcado a mao e o deposito nao entram na conta."""
    info = {d[0]: d for d in dias_mes}
    carga = Counter(l["DATA"] for l in linhas)
    for data in sorted(carga):
        sobra = carga[data] - cap_de(data)
        if data == deposito or sobra <= 0:
            continue
        nvis = Counter(l["CHAVE_CLIENTE"] for l in linhas)
        do_dia = [l for l in linhas if l["DATA"] == data
                  and l["CHAVE_CLIENTE"] not in marcados]
        do_dia.sort(key=lambda l: (nvis[l["CHAVE_CLIENTE"]] > 1,
                                   PESO_CURVA.get(l.get("CURVA_RECEITA"), 4),
                                   l["CHAVE_CLIENTE"]), reverse=True)
        for l in do_dia[:sobra]:
            ch = l["CHAVE_CLIENTE"]
            carga[data] -= 1
            if nvis[ch] > 1:
                linhas.remove(l)
                nvis[ch] -= 1
                continue
            semanas = {info[x["DATA"]][2] for x in linhas
                       if x["CHAVE_CLIENTE"] == ch and x is not l
                       and x["DATA"] in info}
            cand = sorted({x["DATA"] for x in linhas
                           if x.get("UF") == l.get("UF")
                           and x.get("CIDADE") == l.get("CIDADE")
                           and x["DATA"] in info and x["DATA"] != deposito
                           and carga[x["DATA"]] < cap_de(x["DATA"])
                           and info[x["DATA"]][2] not in semanas},
                          key=lambda x: (carga[x], x))
            alvo = cand[0] if cand else deposito
            if alvo is None or alvo not in info:
                linhas.remove(l)
                continue
            d = info[alvo]
            l.update({"DATA": alvo, "DIA_DO_MES": alvo.day,
                      "DIA_DA_SEMANA": d[1], "SEMANA": f"Semana {d[2]}"})
            carga[alvo] += 1


def previa_rota_cidade(cfg: dict, clientes: list, cod: str) -> dict:
    """O que o calendario do vendedor vai dar, dia a dia e cidade a cidade:
    {(data ISO, cidade): [clientes novos, repetidos]} - a mesma conta da
    rota, para a aba mostrar antes de gravar."""
    fora = cidades_fora_da_rota(cfg, cod)
    lista_zc = [(c, z) for c, z in clientes_do_vendedor(cfg, clientes, cod)
                if not fora_da_rota(cfg, c, cod, fora)]
    if not lista_zc or not rota_cidade_do_vendedor(cfg, cod):
        return {}
    dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    agenda = _agenda_do_vendedor(cfg, dias, [z for _, z in lista_zc])
    v = pessoa_por_codigo(cfg, cod) or {}
    base = (v.get("uf_base", ""), v.get("cidade_base", ""))
    # (17/10) a mesma regra da rota: top 30 / limite e a cidade base
    marcar_visita_semanal(cfg, v, [c for c, _ in lista_zc])
    restritos = dias_da_cidade_base(dias, cfg["parametros"])
    _l, previa = _rota_pelo_calendario(
        cfg, texto(cod), v, lista_zc, dias, agenda,
        _teto_do_vendedor(cfg, {id(z): z for _, z in lista_zc}.values()),
        base, [], restritos,
        regiao_da_base(v, cfg["parametros"]) if restritos else None)
    return previa


def _agenda_do_vendedor(cfg, dias, zonas_dele) -> list:
    """Os dias uteis + o ULTIMO sabado (salvo quando ele e o deposito)."""
    uteis = [d for d in dias if not d[3]] or dias
    sabados = [d for d in dias if d[3]]
    sab_ultimo = sabados[-1] if sabados else None
    sab_deposito = sabados[0] if sabados else None
    deposito = any(excedente_no_sabado(cfg, z) for z in zonas_dele)
    agenda = list(uteis)
    if sab_ultimo is not None and not (deposito
                                       and sab_ultimo == sab_deposito):
        agenda = sorted(uteis + [sab_ultimo], key=lambda d: d[0])
    return agenda


# (21/10, Alexandre) os dias em que o vendedor do interior esta FORA da
# cidade base (o calendario da Rota por cidade) - a gerar_rota preenche,
# vendedor a vendedor, e o teto_do_dia usa: teto_interior (6) nesses dias
_DIAS_NO_INTERIOR = [frozenset()]


def dias_no_interior(cfg: dict, cod: str) -> set:
    """Os dias do calendario (Rota por cidade / agenda importada) em que o
    vendedor DO INTERIOR esta numa cidade que nao e a cidade base dele."""
    if not vendedor_do_interior(cfg, cod):
        return set()
    v = pessoa_por_codigo(cfg, cod) or {}
    base = norm(v.get("cidade_base", ""))
    saida = set()
    for d, chs in ((cfg.get("rota_cidade") or {}).get(cod) or {}).items():
        cids = [norm(str(ch).split("|", 1)[-1]) for ch in chs or ()]
        dd = data_de(d)
        # [SUPOSICAO] dia com duas cidades: vale a 1a do calendario
        if dd and cids and cids[0] != base:
            saida.add(dd)
    return saida


def teto_do_dia(cap: int, data, par: dict) -> int:
    """O teto de visitas do dia: a SEXTA e de prospeccao e tem o seu
    (parametro visitas_sexta, padrao 6). (21/10) Vendedor do interior fora
    da cidade base: teto_interior (6)."""
    if not cap:
        return cap
    try:
        sexta = int(par.get("visitas_sexta", 6) or 0)
    except (TypeError, ValueError):
        sexta = 6
    t = min(cap, sexta) if sexta and data.weekday() == 4 else cap
    if _DIAS_NO_INTERIOR[0] and data in _DIAS_NO_INTERIOR[0]:
        try:
            ti = int(par.get("teto_interior", 6) or 0)
        except (TypeError, ValueError):
            ti = 6
        if ti:
            t = min(t, ti)
    return t


def meta_de_visita_do_dia(cfg: dict, cod: str, d, cidade_do_dia=None,
                          por_du: int = 12, interior_du: int = 6) -> int:
    """(21/10, Alexandre) A META DE VISITA DO DIA do vendedor: 12 clientes
    por dia util (seg a sex, sem feriado; [SUPOSICAO] a sexta tambem 12) a
    partir da admissao; vendedor do interior: 6, e 12 no dia em que esta na
    cidade base. Sabado, domingo e feriado: 0."""
    fer = {data_de(f) for f in cfg.get("feriados") or ()}
    if d.weekday() >= 5 or d in fer:
        return 0
    v = pessoa_por_codigo(cfg, cod) or {}
    adm = data_admissao(v)
    if adm is not None and d < adm:
        return 0
    if not vendedor_do_interior(cfg, cod):
        return por_du
    base = norm(v.get("cidade_base", ""))
    return por_du if cidade_do_dia and norm(cidade_do_dia) == base \
        else interior_du


def cidades_do_dia(cfg: dict, cidade_do_cliente: dict) -> dict:
    """{(vendedor, dia): cidade} - a cidade em que o vendedor esta no dia:
    a de mais visitas na rota guardada (nos dias passados de outubro, o
    realizado); sem visita guardada, a 1a do calendario da Rota por cidade.
    cidade_do_cliente: {CHAVE_CLIENTE normalizada: cidade}."""
    saida = {}
    fixa = rota_fixa_valida(cfg)
    for cod, fv in (fixa.get("vendedores") or {}).items():
        cont = defaultdict(Counter)
        for chave, data, *_ in fv.get("visitas") or ():
            cid = cidade_do_cliente.get(chave_normal(chave))
            if cid:
                cont[data][norm(cid)] += 1
        for data, c in cont.items():
            dd = data_de(data)
            if dd:
                saida[(cod, dd)] = c.most_common(1)[0][0]
    for cod, cal in (cfg.get("rota_cidade") or {}).items():
        for d, chs in (cal or {}).items():
            dd = data_de(d)
            if dd and chs and (cod, dd) not in saida:
                saida[(cod, dd)] = norm(str(chs[0]).split("|", 1)[-1])
    return saida


def chave_normal(chave) -> str:
    """'010488-1' / '010488-01' / '01048801' -> '010488-1' (o codigo com 6
    digitos e a loja sem zero a esquerda)."""
    s = texto(chave)
    if "-" in s:
        a, _, b = s.partition("-")
    else:
        a, b = s[:6], s[6:]
    a = re.sub(r"\D", "", a).zfill(6)
    b = re.sub(r"\D", "", b).lstrip("0") or "1"
    return f"{a}-{b}"


def metas_de_visita_do_mes(cfg: dict, cidade_do_cliente: dict,
                           por_du: int = 12, interior_du: int = 6) -> dict:
    """{vendedor: {dia: meta}} - a meta de visita de cada dia util do mes,
    desde a admissao (so VENDEDOR ativo)."""
    dias = [d[0] for d in dias_do_mes(cfg["mes"], cfg.get("feriados") or [])]
    cid = cidades_do_dia(cfg, cidade_do_cliente)
    saida = {}
    for v in vendedores(cfg):
        cod = texto(v.get("cod_protheus"))
        if not cod or v.get("cargo") != "VENDEDOR" or \
                v.get("ativo") is False:
            continue
        saida[cod] = {d: meta_de_visita_do_dia(cfg, cod, d, cid.get((cod, d)),
                                               por_du, interior_du)
                      for d in dias}
    return saida


def datas_cadastro_lote_fora(cfg=None) -> set:
    """(21/10) Os dias de cadastro em lote que NAO contam como visita
    (parametro datas_cadastro_lote_fora do Planner)."""
    if cfg is None:
        try:
            cfg = json.loads((Path(__file__).resolve().parent
                              / "planner_config.json").read_text("utf-8"))
        except (OSError, ValueError):
            cfg = {}
    lst = (cfg.get("parametros") or {}).get("datas_cadastro_lote_fora")
    if lst is None:
        lst = PARAMETROS_PADRAO["datas_cadastro_lote_fora"]
    return {d for d in (data_de(x) for x in lst or ()) if d}


def _por_peso(lista: list, dias: list, pesos: list) -> list:
    """Divide a lista (na ordem geografica) pelos dias, cada dia com a sua
    fatia proporcional ao peso (o teto do dia): a sexta recebe menos."""
    n, total = len(lista), float(sum(pesos)) if pesos else 0.0
    if not n or not dias:
        return []
    if total <= 0:
        return [(c, dias[min(i * len(dias) // n, len(dias) - 1)])
                for i, c in enumerate(lista)]
    acum, limites = 0.0, []
    for p_ in pesos:
        acum += p_
        limites.append(acum)
    saida, j = [], 0
    for i, c in enumerate(lista):
        alvo = (i + 0.5) / n * total
        while j < len(dias) - 1 and limites[j] < alvo:
            j += 1
        saida.append((c, dias[j]))
    return saida


def _regras_da_semana(cfg, linhas, ini, dias, par, cap_de, fixo=None,
                      mover_primeira=True, pode=None):
    """
    As duas regras da semana (06/10), sobre as linhas do vendedor (de ini
    em diante):
      1. o MESMO CLIENTE NAO E VISITADO DUAS VEZES NA MESMA SEMANA: a 2a
         visita da semana sai e vai para outra semana, num dia em que o
         vendedor ja esta na cidade e que tem lugar; nao havendo, sai.
      2. a SEXTA tem o teto dela (prospeccao): o que passa sai - primeiro
         as visitas repetidas; a 1a visita de um cliente vai para outro dia
         da mesma cidade (a mesma semana, se der).
    cap_de(data) -> teto do dia. fixo: a data que nao entra (o deposito).
    mover_primeira=False (o CALENDARIO da aba Rota por cidade): a 1a visita
    fica no dia que voce deu a cidade, mesmo na sexta - so as repetidas
    saem.
    pode(linha, data) (17/10): a data aceita o cliente? (os dias da cidade
    base nao recebem cliente de fora da regiao da base)
    """
    if pode is None:
        def pode(_l, _x):
            return True
    info = {d[0]: d for d in dias}
    minhas = [l for l in linhas[ini:] if l["DATA"] != fixo]
    outras = [l for l in linhas[ini:] if l["DATA"] == fixo]
    carga = Counter(l["DATA"] for l in minhas)
    sem_cli = defaultdict(set)          # cliente -> semanas com visita
    dias_cidade = defaultdict(set)      # (zona, uf, cidade) -> datas
    dias_zona = defaultdict(set)        # zona -> datas (o pedaco do mes dela)
    for l in minhas:
        dias_cidade[(l.get("ZONA_ID"), l.get("UF"), l.get("CIDADE"))].add(
            l["DATA"])
        dias_zona[l.get("ZONA_ID")].add(l["DATA"])

    def semana(data):
        return info[data][2] if data in info else None

    def mover(l, data):
        d = info[data]
        l.update({"DATA": data, "DIA_DO_MES": data.day, "DIA_DA_SEMANA": d[1],
                  "SEMANA": f"Semana {d[2]}"})

    def lugar(l, mesma_semana=None):
        """Um dia da cidade do cliente, com lugar e sem o cliente na
        semana; o mais vazio."""
        ch = l["CHAVE_CLIENTE"]
        cand = [x for x in dias_cidade[(l.get("ZONA_ID"), l.get("UF"),
                                        l.get("CIDADE"))]
                if x in info and carga[x] < cap_de(x) and pode(l, x)
                and semana(x) not in sem_cli[ch]
                and (mesma_semana is None or semana(x) == mesma_semana)]
        return min(cand, key=lambda x: (carga[x], x)) if cand else None
    # a ordem de quem fica: a 1a visita antes das repetidas, data a data
    minhas.sort(key=lambda l: (l["DATA"], l.get("VISITA_NO_MES", 1) != 1))
    ficam, soltas = [], []
    for l in minhas:
        ch, sm = l["CHAVE_CLIENTE"], semana(l["DATA"])
        if sm in sem_cli[ch]:
            soltas.append(l)
            carga[l["DATA"]] -= 1
            continue
        sem_cli[ch].add(sm)
        ficam.append(l)
    # a sexta acima do teto: as repetidas saem primeiro, depois a curva Z
    for data in sorted({l["DATA"] for l in ficam}):
        sobra = carga[data] - cap_de(data)
        if sobra <= 0 or data.weekday() != 4:
            continue
        do_dia = [l for l in ficam if l["DATA"] == data]
        visitas = Counter(l["CHAVE_CLIENTE"] for l in ficam)
        if not mover_primeira:
            do_dia = [l for l in do_dia if visitas[l["CHAVE_CLIENTE"]] > 1]
        do_dia.sort(key=lambda l: (visitas[l["CHAVE_CLIENTE"]] > 1,
                                   PESO_CURVA.get(l.get("CURVA_RECEITA"), 4)),
                    reverse=True)
        for l in do_dia[:sobra]:
            ficam.remove(l)
            carga[data] -= 1
            sem_cli[l["CHAVE_CLIENTE"]].discard(semana(data))
            soltas.append(l)
    # as soltas: o cliente sem nenhuma outra visita no mes PRECISA de um
    # lugar; a repetida so volta se couber
    volta = []
    for l in soltas:
        ch = l["CHAVE_CLIENTE"]
        alvo = lugar(l, semana(l["DATA"])) or lugar(l)
        if alvo is None and not sem_cli[ch] and mover_primeira:
            cand = [x for x in dias_cidade[(l.get("ZONA_ID"), l.get("UF"),
                                            l.get("CIDADE"))]
                    if x in info and x.weekday() != 4] or \
                [x for x in dias_zona[l.get("ZONA_ID")]
                 if x in info and x.weekday() != 4 and x != fixo
                 and pode(l, x)] or \
                [x for x in info if x.weekday() != 4 and x != fixo
                 and pode(l, x)]
            alvo = min(cand, key=lambda x: (carga[x], x)) if cand else None
        if alvo is None:
            continue
        mover(l, alvo)
        carga[alvo] += 1
        sem_cli[ch].add(semana(alvo))
        volta.append(l)
    linhas[ini:] = ficam + volta + outras


def _completar_ate_o_teto(cfg, linhas, ini, ativas, listas, fatia_de, par,
                          cod_vend, v, restritos=frozenset(), na_base=None):
    """Enche cada dia da fatia de cada zona ate o teto, repetindo clientes
    (ver gerar_rota). Renumera VISITA_NO_MES / VISITAS_DO_CLIENTE das
    linhas do vendedor no fim."""
    minhas = linhas[ini:]
    no_dia = defaultdict(set)
    dias_cli = defaultdict(list)
    sem_cli = defaultdict(set)
    sem_de = {}
    for fs in fatia_de.values():
        for d in fs:
            sem_de[d[0]] = d[2]
    for l in minhas:
        no_dia[l["DATA"]].add(l["CHAVE_CLIENTE"])
        dias_cli[l["CHAVE_CLIENTE"]].append(l["DATA"])
        sem_cli[l["CHAVE_CLIENTE"]].add(sem_de.get(l["DATA"]))
    for z in ativas:
        cap = int(z.get("visitas_por_dia") or par["visitas_por_dia"] or 0)
        lista = listas.get(z["id"]) or []
        if not cap or not lista:
            continue
        por_chave = {c["CHAVE_CLIENTE"]: c for c in lista}
        for d in fatia_de.get(z["id"]) or []:
            vagas = teto_do_dia(cap, d[0], par) - len(no_dia[d[0]])
            if vagas <= 0:
                continue
            cidades = {(por_chave[ch]["UF"], por_chave[ch]["CIDADE"])
                       for ch in no_dia[d[0]] if ch in por_chave}
            # nunca duas vezes na mesma semana (regra de 06/10)
            pool = [c for c in lista if c["CHAVE_CLIENTE"] not in no_dia[d[0]]
                    and d[2] not in sem_cli[c["CHAVE_CLIENTE"]]
                    and (not cidades or (c["UF"], c["CIDADE"]) in cidades)
                    # (17/10) o dia da cidade base so com a regiao da base
                    and (na_base is None or d[0] not in restritos
                         or na_base(c))]

            def chave(c, d=d):
                ds = dias_cli[c["CHAVE_CLIENTE"]]
                perto = min((abs((d[0] - x).days) for x in ds), default=99)
                return (c.get("VISITA_SEMANAL") != "SIM", len(ds), -perto,
                        PESO_CURVA.get(c.get("CURVA_RECEITA"), 4),
                        -c.get("RECEITA_6M", 0.0), c["CHAVE_CLIENTE"])
            for c in sorted(pool, key=chave)[:vagas]:
                linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v,
                                             d, 0, 0))
                no_dia[d[0]].add(c["CHAVE_CLIENTE"])
                dias_cli[c["CHAVE_CLIENTE"]].append(d[0])
                sem_cli[c["CHAVE_CLIENTE"]].add(d[2])
    _numerar(linhas, ini)


def _ordenar_os_dias(linhas, vend, por_lugar=False) -> list:
    """As linhas na ordem vendedor > data > caminho mais curto do dia.
    (27/10) POR LUGAR: cidade > bairro > rua > numero (rota_lugar)."""
    grupos = defaultdict(list)
    for r in linhas:
        grupos[(r["COD_VENDEDOR"], r["DATA"])].append(r)
    saida = []
    for (cod, _d), ls in sorted(grupos.items(), key=lambda kv: kv[0]):
        v = vend.get(cod) or {}
        base = geo.coordenada(v.get("uf_base", ""), v.get("cidade_base", ""))
        if por_lugar:
            import rota_lugar as _rl                    # noqa: PLC0415
            ls.sort(key=lambda r: (r["UF"], r["CIDADE"], r["CHAVE_CLIENTE"]))
            saida += _rl.em_ordem(ls, base)
            continue
        ls.sort(key=lambda r: (r["UF"], r["CIDADE"], r["CHAVE_CLIENTE"]))
        pts = [(r.get("LATITUDE"), r.get("LONGITUDE")) for r in ls]
        ordem = geo.caminho_mais_curto(pts, base, segundos=0.3)
        saida += [ls[i] for i in ordem]
    return saida


def _numerar(linhas, ini):
    """A numeracao das visitas de cada cliente (1/3, 2/3, 3/3)."""
    por_cli = defaultdict(list)
    for l in linhas[ini:]:
        por_cli[l["CHAVE_CLIENTE"]].append(l)
    for ls in por_cli.values():
        ls.sort(key=lambda l: l["DATA"])
        for i, l in enumerate(ls, start=1):
            l["VISITA_NO_MES"] = i
            l["VISITAS_DO_CLIENTE"] = len(ls)


# ==========================================================================
# (27/10, Alexandre) ROTEIRIZACAO POR LUGAR: a geolocalizacao e a
# proximidade em camadas - CIDADE > BAIRRO > RUA (endereco) > NUMERO - e
# CADA CIDADE E UM DIA CHEIO (1 cidade por dia, capital ou interior).
#   - O Planner continua escolhendo QUEM entra em cada semana (curva, TOP 30,
#     limite, cidade base nos 10 primeiros dias, teto); a semana de cada
#     vendedor e entao REMONTADA: as cidades da semana viram dias (a base
#     primeiro, depois as cidades ate 50 km, depois as longes; a sexta, de
#     teto 6, vai para a cidade que cabe inteira nela; dia que sobra vai
#     para a cidade com mais visitas); dentro da cidade, bairro > rua >
#     numero; REGIAO LONGE dentro da cidade (ilha, distrito - ex. Mosqueiro)
#     e dia proprio (rota_lugar.SALTO_KM). DIA COMPACTO (27/10): bairro a
#     mais de rota_lugar.RAIO_DIA_KM do centro do dia fecha o dia, e a vaga
#     so pega cliente ate rota_lugar.RAIO_VAGA_KM (5 km).
#   - Vaga do dia: clientes da carteira da mesma cidade/regiao (menos
#     visitados no mes, curva, distancia); sem cliente, a vaga e
#     PROSPECCAO. Cidade que nao coube na semana passa para a semana
#     seguinte; no fim do mes, para o sabado do deposito (se ainda vier).
#   - Dia com CALENDARIO (Rota por cidade / agenda importada) fica com as
#     cidades do calendario [SUPOSICAO]; so a ordem do dia segue o lugar.
#   - Vale a partir de POR_LUGAR_DESDE (outubro ja estava rodando).
# ==========================================================================
POR_LUGAR_DESDE = "2026-11"


def por_lugar_ativo(cfg) -> bool:
    return str(cfg.get("mes") or "")[:7] >= POR_LUGAR_DESDE


# --------------------------------------------------------------------------
# (03/11, Alexandre) DIA FOCO NA ROTA: "segunda foco clientes bateria e
# terca foco clientes motopecas para os vendedores da capital, Ananindeua e
# Castanhal". Vale para o vendedor com cidade base numa capital ou em
# Ananindeua/Castanhal, de NOV/26 em diante, e o dia foco e na CIDADE BASE
# [SUPOSICAO]. O dia e montado antes do resto da semana:
#   cliente do foco ... BATERIA = segmento DISTRIBUIDOR DE BATERIAS ou quem
#                       comprou bateria (HIST_DETALHADO da BASE_CLIENTE);
#                       MOTO = segmento MOTOPECAS
#   depois ............ (so na bateria) AUTOPECAS, AUTOCENTER e POSTO E
#                       TROCA DE OLEO, que podem comprar bateria
#   depois ............ quem ja estava na semana, perto
# Cada grupo: quem ja estava na semana primeiro, depois a curva (S, A,
# limite), os menos visitados no mes e a distancia. O dia continua COMPACTO
# (ate 5 km do centro, que e o lugar com mais clientes do foco) e 1 cidade.
# Ninguem 2x na semana. Faltando cliente perto: prospeccao.
#
# (03/11, Alexandre) FAYGA E RODRIGO: "sempre estarao nas bases segunda e
# terca. Interior de quarta em diante." Segunda e terca so a cidade base;
# de quarta em diante so as outras cidades da carteira (a regra dos 10
# primeiros dias uteis na base nao vale para eles). Dia de interior sem
# cidade na semana: a cidade da carteira com mais clientes menos visitados.
# --------------------------------------------------------------------------
FOCO_DESDE = "2026-11"
FOCO_DO_DIA = {0: "BATERIA", 1: "MOTO"}          # segunda, terca
FOCO_CIDADES_BASE = ("ANANINDEUA", "CASTANHAL")  # + as capitais
FOCO_SEGMENTOS = {"BATERIA": ("DISTRIBUIDOR DE BATERIAS",),
                  "MOTO": ("MOTOPECAS",)}
FOCO_POTENCIAL = {"BATERIA": ("AUTOPECAS", "AUTOCENTER",
                              "POSTO E TROCA DE OLEO"),
                  "MOTO": ()}
BASE_SEG_TER = ("000023", "000007")       # Fayga (Ananindeua), Rodrigo
DIAS_DA_BASE_SEG_TER = (0, 1)             # segunda e terca


def foco_ativo(cfg, v) -> bool:
    """O vendedor tem dia foco (cidade base numa capital, Ananindeua ou
    Castanhal; de FOCO_DESDE em diante)."""
    if str(cfg.get("mes") or "")[:7] < FOCO_DESDE:
        return False
    base = norm(v.get("cidade_base", ""))
    return bool(base) and (base in CAPITAL_DA_UF.values()
                           or base in FOCO_CIDADES_BASE)


def foco_do_dia(cfg, v, data) -> str:
    """BATERIA na segunda, MOTO na terca (vazio: dia sem foco)."""
    if not foco_ativo(cfg, v):
        return ""
    return FOCO_DO_DIA.get(data.weekday(), "")


def nivel_do_foco(c, foco) -> int:
    """0 = cliente do foco; 1 = pode comprar (so na bateria); 2 = outro."""
    seg = norm(c.get("SEGMENTO"))
    if seg in FOCO_SEGMENTOS.get(foco, ()) or (
            foco == "BATERIA" and c.get("COMPRA_BATERIA")):
        return 0
    if seg in FOCO_POTENCIAL.get(foco, ()):
        return 1
    return 2


def base_seg_ter(cfg, cod) -> bool:
    """Fayga e Rodrigo: segunda e terca na base, quarta em diante no
    interior (de FOCO_DESDE em diante)."""
    return str(cfg.get("mes") or "")[:7] >= FOCO_DESDE and \
        texto(cod) in BASE_SEG_TER


def _montar_dia_foco(foco, t, pool_base, extras, vezes, cli_de, ja_mes):
    """O dia foco: (do pool, dos extras) - ate t clientes a ate
    RAIO_DIA_KM do lugar que junta mais clientes do foco e da semana.
    Ordem: 1) cliente do foco (o da semana, depois o da carteira, o menos
    visitado no mes antes); 2) quem ja estava na semana (o que pode
    comprar bateria antes); 3) quem pode comprar bateria e ainda nao teve
    visita no mes."""
    import rota_lugar as rl                             # noqa: PLC0415
    cands = []           # (linha_ou_cliente, da_semana, cliente, ponto)
    for r in pool_base:
        c = cli_de.get(r["CHAVE_CLIENTE"])
        if c is not None:
            cands.append((r, True, c, rl.ponto(r)))
    for k, c in extras:
        n = nivel_do_foco(c, foco)
        if n == 0 or (n == 1 and k not in ja_mes):
            cands.append((c, False, c, rl.ponto(c)))
    com_pt = [x for x in cands if x[3][0] is not None]
    if not com_pt or t <= 0:
        return [], []

    def nivel(x):
        n = nivel_do_foco(x[2], foco)
        return 0 if n == 0 else (1 if x[1] else 2)

    def peso(cen):
        w = 0
        for x in com_pt:
            if geo.distancia_km(cen, x[3]) <= rl.RAIO_DIA_KM:
                w += (3, 2, 1)[nivel(x)]
        return w
    sementes = [x for x in com_pt if nivel(x) == 0] or com_pt
    cen = max((x[3] for x in sementes), key=peso)
    perto = [x for x in com_pt if geo.distancia_km(cen, x[3])
             <= rl.RAIO_DIA_KM]
    perto.sort(key=lambda x: (nivel(x), not x[1],
                              nivel_do_foco(x[2], foco),
                              vezes.get(x[2]["CHAVE_CLIENTE"], 0),
                              grupo_do_mes(x[2]),
                              geo.distancia_km(cen, x[3])))
    escolhidos, vistos = [], set()
    for x in perto:
        k = x[2]["CHAVE_CLIENTE"]
        if k in vistos:
            continue
        vistos.add(k)
        escolhidos.append(x)
        if len(escolhidos) >= t:
            break
    return ([x[0] for x in escolhidos if x[1]],
            [x[2] for x in escolhidos if not x[1]])


def _mover_para(r, dia):
    data, nome_dia, semana, _sab = dia
    r["DATA"] = data
    r["DIA_DO_MES"] = data.day
    r["DIA_DA_SEMANA"] = nome_dia
    r["SEMANA"] = f"Semana {semana}"
    return r


def _renumerar_visitas(linhas):
    por_cli = defaultdict(list)
    for r in linhas:
        por_cli[(r["COD_VENDEDOR"], r["CHAVE_CLIENTE"])].append(r)
    for ls in por_cli.values():
        ls.sort(key=lambda r: r["DATA"])
        for i, r in enumerate(ls, start=1):
            r["VISITA_NO_MES"] = i
            r["VISITAS_DO_CLIENTE"] = len(ls)


def _reorganizar_por_lugar(cfg, linhas, vend, por_vendedor, zonas, dias,
                           desde, so_vendedores=None, liberar=(),
                           avisos=None):
    """A semana de cada vendedor remontada POR LUGAR (ver o bloco acima).
    Mexe so nos dias de rota de `desde` em diante (dias uteis + o ultimo
    sabado; o sabado do deposito fica como esta)."""
    import rota_lugar as rl                             # noqa: PLC0415
    par = cfg["parametros"]
    sab = [d for d in dias if d[3]]
    dep = sab[0] if sab else None
    ult = sab[-1] if len(sab) > 1 else None
    dias_rota = [d for d in dias if d[0] >= desde and (
        not d[3] or (ult is not None and d[0] == ult[0]))]
    if not dias_rota:
        return linhas
    semanas = defaultdict(list)
    for d in dias_rota:
        semanas[d[2]].append(d)
    datas_rota = {d[0] for d in dias_rota}
    try:
        t_sexta = int(par.get("visitas_sexta", 6) or 0)
    except (TypeError, ValueError):
        t_sexta = 6
    try:
        t_int = int(par.get("teto_interior", 6) or 0)
    except (TypeError, ValueError):
        t_int = 6
    por_cod, saida = defaultdict(list), []
    for r in linhas:
        if r["DATA"] in datas_rota and (so_vendedores is None
                                        or r["COD_VENDEDOR"] in so_vendedores):
            por_cod[r["COD_VENDEDOR"]].append(r)
        else:
            saida.append(r)
    norm_ = geo.normalizar
    for cod, rows in por_cod.items():
        v = vend.get(cod) or {}
        pz = por_vendedor.get(cod) or {}
        cap = _teto_do_vendedor(cfg, [zonas[z] for z in pz if z in zonas]) \
            or 12
        interior = vendedor_do_interior(cfg, cod)
        base = norm_(v.get("cidade_base", ""))
        uf = v.get("uf_base", "")
        cal = rota_cidade_do_vendedor(cfg, cod)
        zid_de, cart, cli_de = {}, defaultdict(list), {}
        for zid, cs in pz.items():
            if zona_so_excedente(zonas.get(zid)):
                continue
            for c in cs:
                zid_de[c["CHAVE_CLIENTE"]] = zid
                cli_de[c["CHAVE_CLIENTE"]] = c
                cart[norm_(c["CIDADE"])].append((c["CHAVE_CLIENTE"], c))

        def gr(r):              # (03/11) o grupo do mes da visita
            c_ = cli_de.get(r["CHAVE_CLIENTE"])
            return grupo_do_mes(c_) if c_ else 3
        todas = [r for r in linhas if r["COD_VENDEDOR"] == cod]
        vezes = Counter(r["CHAVE_CLIENTE"] for r in todas
                        if r["DATA"].weekday() < 5)

        def ini_de(cid):
            return geo.coordenada(uf, v.get("cidade_base", "") if cid == base
                                  else cid) or geo.coordenada(
                                      uf, v.get("cidade_base", ""))

        def teto(d, cid):
            t = cap
            if t_sexta and d.weekday() == 4:
                t = min(t, t_sexta)
            if interior and t_int and norm_(cid) != base:
                t = min(t, t_int)
            return t

        carry = []
        for sem in sorted(semanas):
            ds = [d for d in semanas[sem] if d[0].isoformat() not in cal]
            dcal = {d[0] for d in semanas[sem]} - {d[0] for d in ds}
            saida += [r for r in rows if r["DATA"] in dcal]
            dset = {d[0] for d in ds}
            pool, vistos = [], set()
            for r in [r for r in rows if r["DATA"] in dset] + carry:
                if r["CHAVE_CLIENTE"] not in vistos:
                    vistos.add(r["CHAVE_CLIENTE"])
                    pool.append(r)
            carry = []
            if not ds:
                carry = pool
                continue
            iso = ds[0][0].isocalendar()[:2]
            usados = {r["CHAVE_CLIENTE"] for r in todas
                      if r["DATA"].isocalendar()[:2] == iso
                      and r["DATA"] not in dset} | vistos
            usados -= set(liberar)
            # (03/11) DIA FOCO: segunda bateria, terca moto, na cidade base
            # (montado antes do resto da semana; ver FOCO_DO_DIA)
            ja_mes = {r["CHAVE_CLIENTE"] for r in saida
                      if r["COD_VENDEDOR"] == cod}
            for d in [d for d in ds if foco_do_dia(cfg, v, d[0])]:
                foco = foco_do_dia(cfg, v, d[0])
                t = teto(d[0], base)
                pool_b = [r for r in pool if norm_(r["CIDADE"]) == base]
                ext = [(k, c) for k, c in cart.get(base, ())
                       if k not in usados]
                do_pool, novos = _montar_dia_foco(foco, t, pool_b, ext,
                                                  vezes, cli_de, ja_mes)
                if not do_pool and not novos:
                    continue
                ids = {id(r) for r in do_pool}
                pool = [r for r in pool if id(r) not in ids]
                dia = list(do_pool)
                for c in novos:
                    k = c["CHAVE_CLIENTE"]
                    zid = zid_de[k]
                    dia.append(_linha_da_rota(cfg, c, zonas[zid], zid, cod,
                                              v, d, 0, 0))
                    usados.add(k)
                    vezes[k] += 1
                # a vaga que sobrou: a carteira perto (ate 5 km), o cliente
                # do foco antes, depois os menos visitados no mes
                vaga_ = rl.candidatos_do_dia(
                    dia, cart.get(base, ()), usados, vezes,
                    lambda c: "SBCZ"[grupo_do_mes(c)])
                vaga_.sort(key=lambda kc: nivel_do_foco(kc[1], foco))
                for k, c in vaga_[:max(0, t - len(dia))]:
                    zid = zid_de[k]
                    dia.append(_linha_da_rota(cfg, c, zonas[zid], zid, cod,
                                              v, d, 0, 0))
                    usados.add(k)
                    vezes[k] += 1
                for r in dia:
                    _mover_para(r, d)
                    r["FOCO_DO_DIA"] = foco
                saida += rl.em_ordem(dia, ini_de(base))
                ds = [x for x in ds if x[0] != d[0]]
            if not ds:
                carry = pool
                continue
            bst = base_seg_ter(cfg, cod)
            por_cid = defaultdict(list)
            for r in pool:
                por_cid[norm_(r["CIDADE"])].append(r)
            unidades = []          # [cidade, blocos, n, demanda]
            for cid, ls in por_cid.items():
                blocos = rl.ordenar_cidade(ls, ini_de(cid))
                rg = rl.regioes(blocos, separar=len(ls) > cap)
                for bl in rg:
                    n = sum(len(b[2]) for b in bl)
                    if len(rg) > 1:
                        cen = rl.centro([b[1] for b in bl])
                        dem = sum(1 for k, c in cart.get(cid, ())
                                  if cen[0] is not None
                                  and rl.ponto(c)[0] is not None
                                  and geo.distancia_km(cen, rl.ponto(c))
                                  <= rl.SALTO_KM)
                    else:
                        dem = len(cart.get(cid, ()))
                    g0 = sum(1 for b in bl for r in b[2] if gr(r) == 0)
                    unidades.append([cid, bl, n, max(n, dem), g0])
            a0 = ini_de(base)

            def dist(u):
                b_ = ini_de(u[0])
                return geo.distancia_km(a0, b_) if a0 and b_ else 999
            # (03/11) a cidade/regiao com cliente S, A ou com limite vai
            # antes na semana (as primeiras visitas do mes sao deles)
            unidades.sort(key=lambda u: (u[4] == 0, u[0] != base,
                                         dist(u) > 50, -u[4], -u[2]))
            livres = [d for d in ds]
            plano = []
            if bst:
                # (03/11) Fayga e Rodrigo: segunda e terca SO a base; de
                # quarta em diante SO as outras cidades, uma por dia, a que
                # tem mais cliente AINDA SEM VISITA NO MES primeiro (o
                # interior todo e coberto, nao so a cidade maior)
                lb = [d for d in livres
                      if d[0].weekday() in DIAS_DA_BASE_SEG_TER]
                li = [d for d in livres if d not in lb]
                ja_mes = {r["CHAVE_CLIENTE"] for r in saida
                          if r["COD_VENDEDOR"] == cod}
                for u in [u for u in unidades if u[0] == base]:
                    k = min(max(1, -(-u[2] // cap)), len(lb))
                    if k <= 0:
                        carry += [r for b in u[1] for r in b[2]]
                        continue
                    plano.append((u, lb[:k]))
                    del lb[:k]
                while lb:
                    u_b = next((x for x, _ in plano if x[0] == base), None)
                    if u_b is None:
                        plano.append(([base, [], 0, 0, 0], [lb.pop(0)]))
                        continue
                    next(dsx for x, dsx in plano if x is u_b).append(
                        lb.pop(0))
                un_int = {}
                for u in unidades:      # a maior regiao de cada cidade
                    if u[0] != base and (u[0] not in un_int
                                         or u[2] > un_int[u[0]][2]):
                        un_int[u[0]] = u
                da_sem_cid = defaultdict(set)
                for u in unidades:
                    for b in u[1]:
                        for r in b[2]:
                            da_sem_cid[u[0]].add(r["CHAVE_CLIENTE"])
                tomados = set()
                for d in li:
                    nota = {}
                    for cid, cs in cart.items():
                        if cid == base:
                            continue
                        t_ = teto(d[0], cid)
                        ks = [(k_, c_) for k_, c_ in cs
                              if (k_ not in usados or k_ in da_sem_cid[cid])
                              and k_ not in tomados]
                        if not ks:
                            continue
                        # o que cabe num dia COMPACTO (ate 5 km)
                        pts = [(k_, rl.ponto(c_)) for k_, c_ in ks]
                        com = [x for x in pts if x[1][0] is not None]
                        melhor = ([ks[0][0]], ks[0][0])
                        for k0, p0 in com:
                            grupo_ = [k_ for k_, p_ in com
                                      if geo.distancia_km(p0, p_)
                                      <= rl.RAIO_VAGA_KM]
                            if len(grupo_) > len(melhor[0]):
                                melhor = (grupo_, k0)
                        novos_ = sum(1 for k_ in melhor[0]
                                     if k_ not in ja_mes)
                        ja_dia = sum(1 for x, dsx in plano
                                     if x[0] == cid for _y in dsx)
                        nota[cid] = (3 * min(novos_, t_)
                                     + min(len(melhor[0]), t_)
                                     - t_ * ja_dia, melhor)
                    if not nota:
                        break                 # sem cliente: prospeccao
                    cid_n = max(nota, key=lambda c_: (nota[c_][0], c_))
                    grupo_n, semente = nota[cid_n][1]
                    u_x = next((x for x, _ in plano if x[0] == cid_n), None)
                    if u_x is None:
                        u_x = un_int.get(cid_n) or [cid_n, [], 0, 0, 0]
                        while len(u_x) < 6:
                            u_x.append(None)
                        u_x[5] = semente
                        plano.append((u_x, [d]))
                    else:
                        next(dsx for x, dsx in plano if x is u_x).append(d)
                    tomados |= set(grupo_n[:teto(d[0], cid_n)])
                for u in unidades:
                    if u[0] != base and not any(x is u for x, _ in plano):
                        carry += [r for b in u[1] for r in b[2]]
                livres = []
            for d in [d for d in livres if t_sexta and t_sexta < cap
                      and d[0].weekday() == 4]:
                u = next((u for u in unidades
                          if u[3] <= teto(d[0], u[0])
                          and not any(x is u for x, _ in plano)), None)
                if u:
                    plano.append((u, [d]))
                    livres.remove(d)
            for u in unidades:
                if bst or any(x is u for x, _ in plano):
                    continue
                k = min(max(1, -(-u[2] // cap)), len(livres))
                if k <= 0:
                    carry += [r for b in u[1] for r in b[2]]
                    continue
                plano.append((u, livres[:k]))
                livres = livres[k:]
            while livres and plano:
                u = next((x for x, _ in plano if x[0] == base), plano[0][0])
                for x, dsx in plano:
                    if x is u:
                        dsx.append(livres.pop(0))
                        break
            for u, dsu in plano:
                cid = u[0]
                dsu.sort(key=lambda d: d[0])
                # (03/11) passou do que cabe nos dias: sai primeiro quem e
                # de grupo mais baixo (C, D, Z), nunca o S/A/limite antes
                cabe = sum(teto(d[0], cid) for d in dsu)
                if u[2] > cabe:
                    todos_ = sorted(((gr(r), -bi, -ri, bi, ri)
                                     for bi, b in enumerate(u[1])
                                     for ri, r in enumerate(b[2])),
                                    reverse=True)
                    tirar = {(t[3], t[4]) for t in todos_[:u[2] - cabe]}
                    novos_bl = []
                    for bi, b in enumerate(u[1]):
                        fica = [r for ri, r in enumerate(b[2])
                                if (bi, ri) not in tirar]
                        carry += [r for ri, r in enumerate(b[2])
                                  if (bi, ri) in tirar]
                        if fica:
                            novos_bl.append((b[0], b[1], fica))
                    u[1] = novos_bl
                dias_u, sobra = rl.montar_dias(
                    u[1], [teto(d[0], cid) for d in dsu])
                # (03/11) o S/A/limite que sobrou (dia compacto) troca de
                # lugar com a visita de grupo mais baixo do dia mais perto
                for r0 in [r for r in sobra if gr(r) == 0]:
                    p0 = rl.ponto(r0)
                    melhor = None
                    for di, dia in enumerate(dias_u):
                        for ri, r1 in enumerate(dia):
                            if gr(r1) > 0:
                                cd = rl.centro([rl.ponto(x) for x in dia])
                                km = geo.distancia_km(cd, p0) if \
                                    cd[0] is not None and p0[0] is not None \
                                    else 999
                                if km > rl.RAIO_VAGA_KM:
                                    continue    # so troca perto (5 km)
                                k_ = (km, -gr(r1))
                                if melhor is None or k_ < melhor[0]:
                                    melhor = (k_, di, ri)
                    if melhor is not None:
                        _k, di, ri = melhor
                        sobra[sobra.index(r0)] = dias_u[di][ri]
                        dias_u[di][ri] = r0
                carry += sobra
                dias_u += [[] for _ in range(len(dsu) - len(dias_u))]
                for d, dia in zip(dsu, dias_u):
                    t = teto(d[0], cid)
                    for r in dia:
                        _mover_para(r, d)
                    # (03/11) a vaga pela PRIORIDADE do mes: S, A e limite
                    # antes de B, C... (os menos visitados no mes primeiro)
                    # (03/11) dia sem ninguem (cidade nova do interior da
                    # Fayga/Rodrigo): o 1o da fila abre o dia e o resto
                    # vem a ate 5 km dele (dia compacto)
                    sem_ = u[5] if len(u) > 5 else None
                    if not dia and t and sem_ and sem_ not in usados \
                            and sem_ in zid_de:
                        zid = zid_de[sem_]
                        dia.append(_linha_da_rota(cfg, cli_de[sem_],
                                                  zonas[zid], zid, cod, v,
                                                  d, 0, 0))
                        usados.add(sem_)
                        vezes[sem_] += 1
                    for _passo in ((1, None) if not dia and t else (None,)):
                        for k, c in rl.candidatos_do_dia(
                                dia, cart.get(cid, ()), usados, vezes,
                                lambda c: "SBCZ"[grupo_do_mes(c)])[
                                    :max(0, (_passo or t) - len(dia))]:
                            zid = zid_de[k]
                            dia.append(_linha_da_rota(cfg, c, zonas[zid],
                                                      zid, cod, v, d, 0, 0))
                            usados.add(k)
                            vezes[k] += 1
                    saida += dia
        if carry:
            if dep is not None and dep[0] >= desde:
                saida += [_mover_para(r, dep) for r in carry]
                txt = (f"{len(carry)} visita(s) de {v.get('nome', cod)} "
                       f"nao couberam por cidade: foram para o sabado "
                       f"{dep[0]:%d/%m}")
            else:
                txt = (f"{len(carry)} visita(s) de {v.get('nome', cod)} "
                       f"nao couberam por cidade e ficam para o mes que "
                       f"vem: " + ", ".join(sorted({texto(r['CIDADE'])
                                                     for r in carry})))
            if avisos is not None:
                avisos.append(txt)
    _renumerar_visitas([r for r in saida
                        if r["COD_VENDEDOR"] in por_cod])
    return saida


# ==========================================================================
# ROTA FIXA (15/10, Alexandre): o RECALCULAR PLANNER pergunta se refaz o
# planner COMPLETO ou SO OS VENDEDORES/ZONAS ALTERADOS. Cada recalculo
# guarda a rota de cada vendedor (cfg["rota_fixa"]: as visitas, dia e
# ordem) com a ASSINATURA da carteira dele (clientes + zona + dia marcado
# a mao, o cadastro dele, as zonas dele, cidades da agenda/fora da rota,
# mes e feriados). Enquanto a assinatura nao muda, a rota dele fica a
# guardada - a base do dia (curva, dias sem compra, coordenadas) nao mexe
# na rota que ja esta certa. Mudou a carteira do vendedor: so a dele e
# refeita. O COMPLETO ignora o que esta guardado e refaz todo mundo.
# ==========================================================================
ROTA_FIXA = "rota_fixa"
IGNORAR_ROTA_FIXA = [False]          # o RECALCULAR COMPLETO liga
# (21/10) o passado so e reescrito quando o Alexandre pede (o refazer com o
# realizado liga); HOJE_DA_ROTA: o "hoje" da regra (None = date.today())
REESCREVER_PASSADO = [False]
HOJE_DA_ROTA = [None]


def _carteira_da_rota(cfg, clientes, zonas=None):
    """{vendedor: {zona: [clientes]}} - quem entra na rota de quem (a mesma
    regra da gerar_rota: com zona, ativo, fora das cidades tiradas)."""
    zonas = zonas or {z["id"]: z for z in cfg["zonas"]}
    por_vendedor = defaultdict(lambda: defaultdict(list))
    fora_de = {cod: cidades_fora_da_rota(cfg, cod)
               for cod in (cfg.get("rota_cidade_fora") or {})}
    for c in clientes:
        zid = zona_do_cliente(cfg, c)
        if not zid:
            continue
        if cliente_inativo(cfg, c):
            continue                # INATIVO (aba Base cliente): sem rota
        cod_c = vendedor_do_cliente(cfg, c, zonas)
        # cidade TIRADA da rota do vendedor (clique no calendario): fica
        # sem visita no mes
        if fora_de.get(cod_c) and fora_da_rota(cfg, c, cod_c,
                                               fora_de[cod_c]):
            continue
        por_vendedor[cod_c][zid].append(c)
    return por_vendedor


def assinatura_da_carteira(cfg, cod, por_zona, zonas=None) -> str:
    """O que, mudando, muda a rota DESTE vendedor (ver ROTA FIXA)."""
    zonas = zonas or {z["id"]: z for z in cfg["zonas"]}
    cli = sorted((c["CHAVE_CLIENTE"], zid,
                  json.dumps(excecao_do_cliente(cfg, c), sort_keys=True,
                             default=str))
                 for zid, cs in por_zona.items() for c in cs)
    miolo = {"cli": cli, "pessoa": pessoa_por_codigo(cfg, cod),
             "zonas": [zonas.get(z) for z in sorted(por_zona)],
             "cidade": (cfg.get("rota_cidade") or {}).get(cod),
             "fora": (cfg.get("rota_cidade_fora") or {}).get(cod),
             "liberada": (cfg.get(ROTA_CIDADE_LIBERADA) or {}).get(cod),
             "regras": REGRAS_DA_ROTA,
             "mes": cfg.get("mes"), "feriados": cfg.get("feriados")}
    return hashlib.md5(json.dumps(miolo, sort_keys=True, ensure_ascii=False,
                                  default=str).encode("utf-8")).hexdigest()


def _assinatura_parametros(cfg) -> str:
    par_ = {k: v for k, v in (cfg.get("parametros") or {}).items()
            if k not in PARAMETROS_FORA_DA_ROTA}
    return hashlib.md5(json.dumps(par_,
                                  sort_keys=True, default=str)
                       .encode("utf-8")).hexdigest()


def rota_fixa_valida(cfg) -> dict:
    """A rota guardada, se for deste mes (senao {})."""
    f = cfg.get(ROTA_FIXA) or {}
    return f if f.get("mes") == cfg.get("mes") and f.get("vendedores") \
        else {}


def vendedores_alterados(cfg, clientes) -> dict:
    """O que mudou desde o ultimo recalculo: {"alterados": [cod],
    "iguais": [cod], "parametros": bool, "tem_fixa": bool}."""
    f = rota_fixa_valida(cfg)
    zonas = {z["id"]: z for z in cfg["zonas"]}
    carteira = _carteira_da_rota(cfg, clientes, zonas)
    guard = f.get("vendedores") or {}
    alt, ig = [], []
    for cod, por_zona in carteira.items():
        if not cod:
            continue
        a = assinatura_da_carteira(cfg, cod, por_zona, zonas)
        (ig if (guard.get(cod) or {}).get("assin") == a else alt).append(cod)
    alt += [cod for cod in guard if cod not in carteira]   # ficou sem rota
    return {"alterados": sorted(set(alt)), "iguais": sorted(ig),
            "parametros": bool(f) and f.get("par")
            != _assinatura_parametros(cfg), "tem_fixa": bool(f)}


def fotografar_rota(cfg, clientes) -> int:
    """Guarda a rota de agora como a ROTA FIXA (fim de todo recalculo).
    Devolve quantos vendedores ficaram guardados."""
    linhas = gerar_rota(cfg, clientes)
    assin = getattr(gerar_rota, "assinaturas", {}) or {}
    vendedores_ = {}
    for r in linhas:
        cod = r["COD_VENDEDOR"]
        if cod not in assin:
            continue
        vendedores_.setdefault(cod, {"assin": assin[cod], "visitas": []})[
            "visitas"].append([r["CHAVE_CLIENTE"], r["DATA"].isoformat(),
                               int(r["ORDEM_DE_VISITA"]),
                               r["VISITA_NO_MES"], r["VISITAS_DO_CLIENTE"],
                               r["ZONA_ID"]])
    cfg[ROTA_FIXA] = {"mes": cfg.get("mes"),
                      "em": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                      "par": _assinatura_parametros(cfg),
                      "vendedores": vendedores_}
    return len(vendedores_)


def _linhas_da_rota_fixa(cfg, fixa_v, cod, v, clientes_dele, zonas, dias):
    """As visitas guardadas do vendedor, com o cadastro de hoje do cliente
    (nome, curva, contato...) e o DIA e a ORDEM de quando foi calculada."""
    cmap = {c["CHAVE_CLIENTE"]: c for c in clientes_dele}
    dmap = {d[0].isoformat(): d for d in dias}
    saida = []
    for chave, data, ordem, volta, visitas, zid in fixa_v["visitas"]:
        c, z, dia = cmap.get(chave), zonas.get(zid), dmap.get(data)
        if not (c and z and dia):
            continue
        r = _linha_da_rota(cfg, c, z, zid, cod, v, dia, volta, visitas)
        r["ORDEM_DE_VISITA"] = ordem
        r["ROTA_FIXA"] = "SIM"
        saida.append(r)
    return saida


# ==========================================================================
# (17/10, Alexandre) A CIDADE BASE NO COMECO DO MES E A VISITA SEMANAL
# ==========================================================================
# 1. CIDADE BASE: nos N primeiros dias uteis do mes (parametro
#    dias_cidade_base, padrao 10) o vendedor so roda a cidade base do
#    cadastro (aba 2) e as cidades ate raio_base_km dela (padrao 50 km; a
#    conta e em linha reta). O resto da carteira vai do dia N+1 em diante.
#    Vale para a rota automatica e para o calendario da Rota por cidade -
#    no calendario, a cidade de fora posta nesses dias sai (fica no log).
#    So a AGENDA IMPORTADA (Importar agenda de cidade) passa por cima: e a
#    excecao que o Alexandre faz a mao (cfg["rota_cidade_liberada"]).
#    Faltou cliente na regiao da base, o dia fica abaixo do teto
#    (prospeccao na base) - nao inventa viagem.
# 2. VISITA SEMANAL: os TOP N clientes do vendedor (faturamento 6M, so
#    quem fatura) e todo cliente COM LIMITE de credito (aprovado ou
#    disponivel). Para o VENDEDOR DA CAPITAL - 80% ou mais da carteira a
#    ate raio_capital_km da capital da UF dele, e nao marcado como do
#    interior - esses clientes, quando estao a ate raio_capital_km da
#    capital, sao visitados TODA SEMANA, seja qual for a curva, e entram
#    antes de todo mundo. Para quem viaja (interior, carteira espalhada)
#    eles nao conseguem ser semanais: passam na frente da fila (nunca vao
#    para o sabado do deposito antes de um cliente comum).
# --------------------------------------------------------------------------
CAPITAL_DA_UF = {"AM": "MANAUS", "RR": "BOA VISTA", "AP": "MACAPA",
                 "PA": "BELEM", "MA": "SAO LUIS", "MT": "CUIABA"}
PCT_CARTEIRA_CAPITAL = 0.80     # vendedor da capital: 80% da carteira perto
ROTA_CIDADE_LIBERADA = "rota_cidade_liberada"
REGRAS_DA_ROTA = "2026-10-17"   # muda a regra -> a rota fixa e refeita


def _par_num(par, chave, padrao):
    try:
        v = par.get(chave, padrao)
        return float(padrao if v in (None, "") else v)
    except (TypeError, ValueError):
        return float(padrao)


def dias_da_cidade_base(dias, par) -> frozenset:
    """As datas dos N primeiros dias uteis do mes (sem sabado)."""
    n = int(_par_num(par, "dias_cidade_base", 10))
    if n <= 0:
        return frozenset()
    uteis = sorted(d[0] for d in dias if not d[3])
    return frozenset(uteis[:n])


def _perto(uf, cidade, uf_alvo, cidade_alvo, raio) -> bool:
    if norm(uf) == norm(uf_alvo) and norm(cidade) == norm(cidade_alvo):
        return True
    if raio <= 0:
        return False
    a, b = geo.coordenada(uf, cidade), geo.coordenada(uf_alvo, cidade_alvo)
    return bool(a and b and geo.distancia_km(a, b) <= raio)


def regiao_da_base(v, par):
    """f(cliente) -> True se o cliente e da regiao da base do vendedor (a
    cidade base + as cidades ate raio_base_km). Sem cidade base: None (a
    regra nao tem como valer)."""
    uf_b, cid_b = norm(v.get("uf_base", "")), norm(v.get("cidade_base", ""))
    if not cid_b:
        return None
    raio = _par_num(par, "raio_base_km", 50)
    memo = {}

    def na_base(c):
        k = (c.get("UF"), c.get("CIDADE"))
        if k not in memo:
            memo[k] = _perto(k[0], k[1], uf_b, cid_b, raio)
        return memo[k]
    return na_base


def vendedor_da_capital(v, clientes_dele, par) -> bool:
    """80% ou mais da carteira a ate raio_capital_km da capital da UF base,
    a cidade base perto da capital e o vendedor nao e do interior."""
    uf = norm(v.get("uf_base", ""))
    capital = CAPITAL_DA_UF.get(uf)
    if not capital or v.get("interior") or not clientes_dele:
        return False
    raio = _par_num(par, "raio_capital_km", 50)
    if not _perto(uf, v.get("cidade_base", "") or capital, uf, capital, raio):
        return False
    perto = sum(1 for c in clientes_dele
                if _perto(c.get("UF"), c.get("CIDADE"), uf, capital, raio))
    return perto >= PCT_CARTEIRA_CAPITAL * len(clientes_dele)


def com_limite(c) -> bool:
    return (c.get("LIMITE_APROVADO") or 0) > 0 or \
        (c.get("LIMITE_DISPONIVEL") or 0) > 0


def marcar_visita_semanal(cfg, v, clientes_dele) -> dict:
    """Marca em cada cliente da carteira PRIORIDADE_ROTA ('TOP 30',
    'LIMITE', 'TOP 30 + LIMITE' ou '') e VISITA_SEMANAL ('SIM' ou '').
    Devolve um resumo {capital, top, limite, semanais}."""
    par = cfg.get("parametros") or {}
    n_top = int(_par_num(par, "top_semanal", 30))
    raio_cap = _par_num(par, "raio_capital_km", 50)
    # (17/10) o MESMO TOP 30 da parcial e dos contatos do celular: maior
    # faturamento dos ultimos 6 meses (so quem faturou); empate, o maior
    # limite aprovado
    top = {c["CHAVE_CLIENTE"] for c in sorted(
        (c for c in clientes_dele if (c.get("RECEITA_6M") or 0) > 0),
        key=lambda c: (-(c.get("RECEITA_6M") or 0),
                       -(c.get("LIMITE_APROVADO") or 0), c["CHAVE_CLIENTE"])
    )[:max(0, n_top)]}
    capital = vendedor_da_capital(v, clientes_dele, par)
    uf = norm(v.get("uf_base", ""))
    cap_cid = CAPITAL_DA_UF.get(uf, "")
    n_sem = n_lim = 0
    for c in clientes_dele:
        motivo = []
        if c["CHAVE_CLIENTE"] in top:
            motivo.append(f"TOP {n_top}")
        if com_limite(c):
            motivo.append("LIMITE")
            n_lim += 1
        c["PRIORIDADE_ROTA"] = " + ".join(motivo)
        semanal = bool(motivo) and capital and _perto(
            c.get("UF"), c.get("CIDADE"), uf, cap_cid, raio_cap)
        c["VISITA_SEMANAL"] = "SIM" if semanal else ""
        n_sem += semanal
    return {"capital": capital, "top": len(top), "limite": n_lim,
            "semanais": n_sem}


def _peso_fila(c) -> int:
    """A fila de quem entra nos dias: VISITA SEMANAL, depois a prioridade
    (top 30 / limite de quem viaja), depois a curva."""
    if c.get("VISITA_SEMANAL") == "SIM":
        return -2
    if c.get("PRIORIDADE_ROTA"):
        return -1
    return PESO_CURVA.get(c.get("CURVA_RECEITA"), 4)


def liberadas_do_vendedor(cfg, cod) -> set:
    """As datas que a AGENDA IMPORTADA liberou da regra da cidade base."""
    return set((cfg.get(ROTA_CIDADE_LIBERADA) or {}).get(texto(cod)) or [])


def liberar_datas(cfg, cod, datas) -> None:
    """A agenda importada a mao passa por cima da regra da cidade base."""
    todos = cfg.setdefault(ROTA_CIDADE_LIBERADA, {})
    ds = sorted(set(todos.get(texto(cod)) or []) | {str(d) for d in datas})
    if ds:
        todos[texto(cod)] = ds


def _fatiar_com_base(agenda, listas_z, na_base, restritos):
    """Como _fatiar_agenda, com a REGRA DA CIDADE BASE: os dias da base vao
    so para as zonas que tem cliente da regiao da base (na proporcao
    desses clientes); os outros dias se repartem pelo que falta a cada
    zona - e toda zona com cliente de fora da base recebe dias depois da
    base. Nenhuma zona com cliente da base: os dias da base ficam sem rota
    (prospeccao), a carteira vai nos outros."""
    pesos = [len(l) for l in listas_z]
    a1 = [d for d in agenda if d[0] in restritos]
    a2 = [d for d in agenda if d[0] not in restritos]
    if not a1:
        return _fatiar_agenda(agenda, pesos)
    n_b = [sum(1 for c in l if na_base(c)) for l in listas_z]
    n_o = [p_ - b_ for p_, b_ in zip(pesos, n_b)]
    idx = [i for i, b_ in enumerate(n_b) if b_]
    f1 = dict(zip(idx, _fatiar_agenda(a1, [n_b[i] for i in idx]))) \
        if idx else {}
    total = float(sum(pesos)) or 1.0
    falta = []
    for i, p_ in enumerate(pesos):
        ideal = p_ / total * len(agenda)
        f = max(0.0, ideal - len(f1.get(i, [])))
        if n_o[i]:
            f = max(f, n_o[i] / total * len(agenda), 1e-6)
        falta.append(f)
    vivos = [i for i, f in enumerate(falta) if f > 0]
    f2 = dict(zip(vivos, _fatiar_agenda(a2, [falta[i] for i in vivos]))) \
        if a2 and vivos else {}
    saida = []
    for i in range(len(pesos)):
        f = sorted(list(f1.get(i, [])) + list(f2.get(i, [])),
                   key=lambda d: d[0])
        saida.append(f or list(a2[-1:] or a1[-1:]))
    return saida


def gerar_rota(cfg: dict, clientes: list[dict]) -> list[dict]:
    """
    Monta a rota do mes. A mecanica esta escrita por extenso em
    MECANICA_DA_ROTA, no fim deste arquivo - e o mesmo texto que aparece
    na aba PARAMETROS.
    """
    par = cfg["parametros"]
    # Os dias uteis do mes e os dois sabados que tem papel na rota:
    #   ULTIMO sabado ... dia de rota de todo mundo, sempre, com o mesmo
    #                     teto dos dias uteis (regra fixa, sem parametro)
    #   PRIMEIRO sabado . o DEPOSITO dos clientes que nao couberam na
    #                     semana, quando o parametro do excedente esta em
    #                     SIM. Os sabados do meio ficam livres.
    dias = dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    if not dias:
        return []
    uteis = [d for d in dias if not d[3]] or dias
    sabados = [d for d in dias if d[3]]
    sab_ultimo = sabados[-1] if sabados else None
    sab_deposito = sabados[0] if sabados else None
    n_semanas = len({d[2] for d in uteis}) or 1
    zonas = {z["id"]: z for z in cfg["zonas"]}
    vend = {p["cod_protheus"]: p for p in vendedores(cfg)}

    # a carteira e agrupada por VENDEDOR, e dentro dele por zona: o mes
    # dele e repartido entre as zonas, cada uma com dias seguidos
    por_vendedor = _carteira_da_rota(cfg, clientes, zonas)
    # (15/10) ROTA FIXA: quem nao mudou fica com a rota guardada
    assinaturas = {cod: assinatura_da_carteira(cfg, cod, pz, zonas)
                   for cod, pz in por_vendedor.items() if cod}
    gerar_rota.assinaturas = assinaturas
    fixa = {} if IGNORAR_ROTA_FIXA[0] else rota_fixa_valida(cfg)
    congelados = {cod for cod, a in assinaturas.items()
                  if ((fixa.get("vendedores") or {}).get(cod) or {})
                  .get("assin") == a}
    gerar_rota.congelados = congelados

    # (17/10) TOP 30 / LIMITE e a VISITA SEMANAL, vendedor por vendedor
    for c in clientes:
        c["PRIORIDADE_ROTA"] = ""
        c["VISITA_SEMANAL"] = ""
    resumo_semanal = {}
    for cod, pz in por_vendedor.items():
        if cod:
            # (18/10) a zona SO NO SABADO DO EXCEDENTE nao conta: ela nao
            # e rota de verdade (nem para o TOP 30 nem para o "da capital")
            resumo_semanal[cod] = marcar_visita_semanal(
                cfg, vend.get(cod, {}),
                [c for zid, cs in pz.items()
                 if not zona_so_excedente(zonas.get(zid)) for c in cs])
    gerar_rota.semanal = resumo_semanal
    restritos = dias_da_cidade_base(dias, par)

    linhas = []
    # o que nao coube no dia pedido fica registrado aqui e vai para o log,
    # em vez de a rota mudar em silencio
    avisos_da_agenda = []
    for cod_vend, por_zona in por_vendedor.items():
        if not cod_vend:
            continue                      # zona sem vendedor nao vira rota
        if cod_vend in congelados:
            continue                      # rota guardada (entra no fim)
        # (21/10) vendedor do interior: teto 6 fora da cidade base
        _DIAS_NO_INTERIOR[0] = frozenset(dias_no_interior(cfg, cod_vend))
        try:
            _gerar_do_vendedor(cfg, cod_vend, por_zona, vend, zonas, par,
                               dias, uteis, sab_ultimo, sab_deposito,
                               n_semanas, resumo_semanal,
                               frozenset() if base_seg_ter(cfg, cod_vend)
                               else restritos, linhas,
                               avisos_da_agenda)
        finally:
            _DIAS_NO_INTERIOR[0] = frozenset()
    return _fechar_rota(cfg, clientes, linhas, vend, congelados, fixa,
                        por_vendedor, zonas, dias, avisos_da_agenda)


def _gerar_do_vendedor(cfg, cod_vend, por_zona, vend, zonas, par, dias,
                       uteis, sab_ultimo, sab_deposito, n_semanas,
                       resumo_semanal, restritos, linhas, avisos_da_agenda):
    """A rota de UM vendedor (o miolo da gerar_rota; poe em linhas)."""
    if True:
        v = vend.get(cod_vend, {})
        # (18/10) A ZONA SO NO SABADO DO EXCEDENTE: os clientes ficam com o
        # vendedor (ativos, na carteira), mas vao todos direto para o 1o
        # sabado - nao ocupam dia de rota (ex.: Roraima do Thiago)
        so_sab = {zid: cs for zid, cs in por_zona.items()
                  if zona_so_excedente(zonas.get(zid))}
        if so_sab:
            por_zona = {zid: cs for zid, cs in por_zona.items()
                        if zid not in so_sab}
            for zid, cs in so_sab.items():
                if sab_deposito is None:
                    avisos_da_agenda.append(
                        f"{cod_vend}: {len(cs)} cliente(s) da zona "
                        f"{zonas[zid]['nome']} sem sabado no mes - sem visita")
                    continue
                for c in cs:
                    linhas.append(_linha_da_rota(cfg, c, zonas[zid], zid,
                                                 cod_vend, v, sab_deposito,
                                                 1, 1))
            if not por_zona:
                return
        base_vendedor = (v.get("uf_base", ""), v.get("cidade_base", ""))
        minhas = [zonas[zid] for zid in por_zona if zid in zonas]
        if not minhas:
            return
        minhas = ordem_das_zonas(cfg, minhas, por_zona, base_vendedor)

        # A agenda de rota do vendedor sao os DIAS UTEIS mais o ULTIMO
        # SABADO DO MES, que todo vendedor trabalha, sempre. O sabado do
        # deposito nao entra aqui: ele nao e dia de agenda, e destino do
        # excedente.
        deposito = any(excedente_no_sabado(cfg, z) for z in minhas)
        interior = vendedor_do_interior(cfg, cod_vend)
        # (17/10) A CIDADE BASE nos primeiros dias uteis
        na_base = regiao_da_base(v, par) if restritos else None
        if na_base is not None and not any(
                na_base(c) for cs in por_zona.values() for c in cs):
            avisos_da_agenda.append(
                f"{cod_vend}: nenhum cliente da carteira na cidade base "
                f"{v.get('cidade_base', '')} (ate "
                f"{_par_num(par, 'raio_base_km', 50):.0f} km) - os "
                f"{len(restritos)} primeiros dias uteis ficam sem rota "
                f"(prospeccao). Confira a cidade base no cadastro (aba 2)")
        agenda_vend = list(uteis)
        if sab_ultimo is not None and not (deposito
                                           and sab_ultimo == sab_deposito):
            agenda_vend = sorted(uteis + [sab_ultimo], key=lambda d: d[0])
        # (18/10) ADMITIDO NO MES: a rota comeca no dia da admissao
        adm = data_admissao(v)
        if adm is not None and agenda_vend and adm > agenda_vend[0][0]:
            agenda_vend = [d for d in agenda_vend if d[0] >= adm]
            avisos_da_agenda.append(
                f"{cod_vend}: admitido em {adm:%d/%m/%Y} - rota so a partir "
                f"desse dia")
            if not agenda_vend:
                return

        # O CALENDARIO DA ABA ROTA POR CIDADE manda na rota toda deste
        # vendedor (sem calendario, segue o automatico de sempre)
        if rota_cidade_do_vendedor(cfg, cod_vend):
            lista_zc = [(c, zonas[zid]) for zid, cs in por_zona.items()
                        if zid in zonas for c in cs]
            novas, _previa = _rota_pelo_calendario(
                cfg, cod_vend, v, lista_zc, dias, agenda_vend,
                _teto_do_vendedor(cfg, minhas), base_vendedor,
                avisos_da_agenda, restritos, na_base)
            linhas += novas
            return

        # (03/11) de NOV/26: a ordem do mes pela PRIORIDADE (S, A, limite;
        # depois B, C...), cada grupo na ordem geografica
        prio = por_lugar_ativo(cfg)
        _ordem = ordem_por_prioridade if prio else ordem_geografica
        listas = {z["id"]: _ordem(cfg, por_zona[z["id"]], base_vendedor)
                  for z in minhas}
        ativas = [z for z in minhas if listas[z["id"]]]
        if not ativas:
            return
        # o mes do vendedor repartido entre as zonas dele, cada uma com
        # dias SEGUIDOS (e o que impede ir e voltar da mesma cidade)
        if na_base is not None:
            fatias = _fatiar_com_base(
                agenda_vend, [listas[z["id"]] for z in ativas], na_base,
                restritos)
        else:
            fatias = _fatiar_agenda(agenda_vend,
                                    [len(listas[z["id"]]) for z in ativas])

        agendado = []                    # (cliente, zona, dia) da 1a visita
        excedentes = []                  # (cliente, zona) - vao para o sabado
        planos = {}                      # chave -> (quantas, passo)
        dias_da_cidade = defaultdict(set)
        carga_do_dia = Counter()
        por_ciclo = set()               # clientes colocados em ciclos (06/10)
        repet_ciclo = []                # (cliente, zona, dia) das voltas

        # (17/10) O VENDEDOR DA CAPITAL com mais de uma zona (a mesma
        # cidade): as zonas rodam JUNTAS o mes inteiro - a visita semanal
        # precisa de todas as semanas, e a fatia por zona tirava semanas
        zona_de_cli = {c["CHAVE_CLIENTE"]: z for z in ativas
                       for c in listas[z["id"]]}
        if len(ativas) > 1 and not interior and \
                (resumo_semanal.get(cod_vend) or {}).get("capital"):
            blocos = [(None, list(agenda_vend), _ordem(
                cfg, [c for z in ativas for c in listas[z["id"]]],
                base_vendedor))]
            fatias = [list(agenda_vend)] * len(ativas)
        else:
            blocos = [(z, f, listas[z["id"]]) for z, f in zip(ativas, fatias)]

        fatia_de = {}
        for z_, f_ in zip(ativas, fatias):
            fatia_de[z_["id"]] = f_
        for z, fatia, lista in blocos:
            cap = (int(z.get("visitas_por_dia") or par["visitas_por_dia"]
                       or 0) if z is not None
                   else _teto_do_vendedor(cfg, ativas))
            semanas_fatia = len({d[2] for d in fatia}) or 1
            plano = plano_de_visitas(lista, min(n_semanas, semanas_fatia))
            planos.update(plano)

            # quem cabe nos dias da fatia e quem vai para o sabado (a sexta
            # conta com o teto dela)
            teto_mes = sum(teto_do_dia(cap, d[0], par) for d in fatia) \
                if cap else 0
            if deposito and sab_deposito is not None and teto_mes:
                marcados = {c["CHAVE_CLIENTE"] for c in lista
                            if _dia_forcado(cfg, c, agenda_vend) is not None}
                if na_base is not None and any(d[0] in restritos
                                               for d in fatia):
                    # (17/10) quem e de fora da base so cabe depois dela
                    t1 = sum(teto_do_dia(cap, d[0], par) for d in fatia
                             if d[0] in restritos)
                    dentro, fora = repartir_com_base(
                        lista, plano, t1, teto_mes - t1, na_base, marcados)
                else:
                    dentro, fora = repartir_carteira(lista, plano, teto_mes,
                                                     marcados)
            else:
                dentro, fora = lista, []
            excedentes += [(c, z or zona_de_cli[c["CHAVE_CLIENTE"]])
                           for c in fora]

            if not dentro:
                continue
            # 1a VISITA - na ordem geografica, usando o MES INTEIRO da
            # fatia: os clientes novos sao divididos POR IGUAL entre os
            # dias (a divisao proporcional nao deixa o ultimo dia com as
            # sobras), e sao as visitas REPETIDAS que depois enchem cada
            # dia ate o teto.
            # O VENDEDOR DO INTERIOR e a excecao: a rota dele e por
            # CIDADE - um dia, uma cidade so, ate o teto por dia.
            # A ROTA SEMANAL da zona (a caixa SEMANA DA ROTA, aba 3)
            # manda aqui. Zona sem caixa montada nao muda nada: e a mesma
            # distribuicao de sempre, com a cidade encadeada pela vizinha.
            # (05/10) a SEMANA DA ROTA da zona saiu: nao manda mais
            rota_sem = {}
            colocacao = (_colocar_com_semanas(dentro, fatia, cap, rota_sem,
                                              interior, avisos_da_agenda,
                                              agenda_vend)
                         if rota_sem else [])
            if not colocacao:
                if interior:
                    cap_x = (lambda x, c_=cap: teto_do_dia(c_, x, par))
                    if prio:            # (03/11) cidades do grupo 0 antes
                        dentro = cidades_por_prioridade(dentro)
                    f1 = [d for d in fatia if d[0] in restritos] \
                        if na_base is not None else []
                    if f1:
                        # (17/10) a regiao da base nos primeiros dias, o
                        # resto da carteira depois deles
                        f2 = [d for d in fatia if d[0] not in restritos]
                        b_ = [c for c in dentro if na_base(c)]
                        o_ = [c for c in dentro if not na_base(c)]
                        if not o_ or not f2:
                            f1, f2 = (fatia, []) if not o_ else (f1, f2)
                        elif cap:
                            # a base cabe nos dias dela; o que passar vai
                            # com o resto, que cabe nos dias de depois (o
                            # que nao couber vai para o sabado)
                            t1 = sum(teto_do_dia(cap, d[0], par) for d in f1)
                            b_, sobra_b = repartir_carteira(
                                b_, {c["CHAVE_CLIENTE"]: (1, 0) for c in b_},
                                t1)
                            o_ = sobra_b + o_
                        colocacao = (_agenda_por_cidade(b_, f1, cap, cap_x)
                                     if b_ else [])
                        if o_:
                            colocacao += _agenda_por_cidade(
                                o_, f2 or fatia, cap, cap_x)
                    else:
                        colocacao = _agenda_por_cidade(dentro, fatia, cap,
                                                       cap_x)
                else:
                    # (06/10) EM CICLOS PELA PROXIMIDADE: os dias sao
                    # enchidos na ordem do caminho mais curto ate o teto;
                    # acabada a carteira, uma nova volta (as visitas da
                    # curva e depois o completar ate o teto, so com quem
                    # mora perto da base). Cada dia fica com vizinhos.
                    colocacao, repetidas = _ciclos_da_fatia(
                        dentro, fatia, cap, par, plano,
                        geo.coordenada(*base_vendedor)
                        if base_vendedor[1] else None,
                        restritos, na_base, por_grupo=prio)
                    por_ciclo.update(c["CHAVE_CLIENTE"] for c in dentro)
                    for c, dia in repetidas:
                        carga_do_dia[dia[0]] += 1
                        repet_ciclo.append(
                            (c, z or zona_de_cli[c["CHAVE_CLIENTE"]], dia))
                        dias_da_cidade[(c["UF"], c["CIDADE"])].add(dia)
            for c, dia in colocacao:
                forcado = _dia_forcado(cfg, c, agenda_vend)
                if forcado is not None:
                    dia = forcado
                carga_do_dia[dia[0]] += 1
                agendado.append((c, z or zona_de_cli[c["CHAVE_CLIENTE"]],
                                 dia))
                dias_da_cidade[(c["UF"], c["CIDADE"])].add(dia)

        ini_vend = len(linhas)
        for c, z, dia in agendado:
            linhas.append(_linha_da_rota(
                cfg, c, z, z["id"], cod_vend, v, dia, 1,
                planos.get(c["CHAVE_CLIENTE"], (1, 0))[0]))
        for c, z, dia in repet_ciclo:   # renumeradas no fim (completar)
            linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v,
                                         dia, 2, 2))

        # AS REPETIDAS - a 2a, 3a, 4a visita do mes. Cada uma cai em outro
        # dia da MESMA cidade (o vendedor nao faz viagem a mais so por
        # causa dela), na semana que a curva pede: de 1 em 1 semana para o
        # curva S, de 2 em 2 para A, B e C. Nunca no mesmo dia da anterior
        # e nunca num dia que ja bateu o teto.
        feitas = Counter()
        for c, z, dia in agendado:
            chave = c["CHAVE_CLIENTE"]
            quantas, passo = planos.get(chave, (1, 0))
            if quantas < 2 or not passo or chave in por_ciclo:
                continue
            cap = int(z.get("visitas_por_dia") or par["visitas_por_dia"] or 0)
            da_cidade = dias_da_cidade[(c["UF"], c["CIDADE"])]
            usados = {dia[0]}
            semanas_dele = {dia[2]}       # nunca 2x na mesma semana (06/10)
            alvo = dia[2] + passo
            for _ in range(quantas - 1):
                livres = [d for d in da_cidade if d[0] not in usados
                          and d[2] not in semanas_dele
                          and (na_base is None or d[0] not in restritos
                               or na_base(c))
                          and (not cap or carga_do_dia[d[0]]
                               < teto_do_dia(cap, d[0], par))]
                if not livres:
                    break
                # o dia da semana ALVO que estiver mais vazio; nao havendo
                # a semana exata, o mais perto dela
                outro = min(livres, key=lambda d: (abs(d[2] - alvo),
                                                   carga_do_dia[d[0]], d[0]))
                usados.add(outro[0])
                semanas_dele.add(outro[2])
                carga_do_dia[outro[0]] += 1
                feitas[chave] += 1
                alvo = outro[2] + passo
                linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v,
                                             outro, feitas[chave] + 1, quantas))

        # ANTES DE MANDAR PARA O SABADO: sobrou lugar na semana? As visitas
        # repetidas ficam presas aos dias em que o vendedor esta naquela
        # cidade, entao as vezes um dia fecha com 10 de 12. Esses lugares
        # sao preenchidos aqui, puxando de volta quem iria para o deposito -
        # mas so num dia em que o vendedor JA esta na cidade do cliente, para
        # nao inventar viagem.
        if excedentes:
            sobraram = []
            for c, z in excedentes:
                cap = int(z.get("visitas_por_dia") or par["visitas_por_dia"] or 0)
                livres = [d for d in dias_da_cidade[(c["UF"], c["CIDADE"])]
                          if not cap or carga_do_dia[d[0]]
                          < teto_do_dia(cap, d[0], par)]
                if not livres:
                    sobraram.append((c, z))
                    continue
                dia = min(livres, key=lambda d: (carga_do_dia[d[0]], d[0]))
                carga_do_dia[dia[0]] += 1
                linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v,
                                             dia, 1, 1))
            excedentes = sobraram

        # O DIA ATE O TETO (06/10): a carteira pequena nao deixa o dia com
        # 5 de 12. Os mesmos clientes se REPETEM ate o dia fechar no teto
        # (o parametro "visitas por dia" da zona): primeiro quem teve menos
        # visitas no mes, depois quem esta mais longe da ultima visita, a
        # curva e o faturamento. So clientes da cidade em que o vendedor ja
        # esta naquele dia (nao inventa viagem) e nunca duas vezes no dia.
        cap_v = _teto_do_vendedor(cfg, minhas)
        pode_ = None
        if na_base is not None:
            def pode_(l, x, nb=na_base):
                return x not in restritos or nb(l)
        _regras_da_semana(cfg, linhas, ini_vend, dias, par,
                          lambda x, c_=cap_v: teto_do_dia(c_, x, par),
                          pode=pode_)
        _completar_ate_o_teto(cfg, linhas, ini_vend, ativas, listas,
                              fatia_de, par, cod_vend, v, restritos, na_base)

        # O SABADO E O DEPOSITO: quem nao coube na semana e visitado UMA
        # vez, no PRIMEIRO SABADO do mes, sem teto nenhum. E a valvula de
        # escape - ninguem fica fora da rota.
        for c, z in excedentes:
            linhas.append(_linha_da_rota(cfg, c, z, z["id"], cod_vend, v,
                                         sab_deposito, 1, 1))


def _fechar_rota(cfg, clientes, linhas, vend, congelados, fixa,
                 por_vendedor, zonas, dias, avisos_da_agenda):
    """O fim da gerar_rota: o passado guardado, sem repetir no dia, a ordem
    do dia e as rotas congeladas."""
    # (21/10, Alexandre) OS DIAS QUE JA PASSARAM NAO SAO REESCRITOS: no
    # recalculo (so os alterados ou completo), o vendedor refeito fica com
    # os dias de antes de hoje como estavam na rota guardada; so de hoje em
    # diante a rota e nova (e sem repetir na semana quem ja foi visitado nos
    # dias guardados). Refazer o passado com o realizado + a meta do dia e
    # so quando o Alexandre pedir (REESCREVER_PASSADO).
    passado = []
    guard = (rota_fixa_valida(cfg).get("vendedores") or {}) \
        if not REESCREVER_PASSADO[0] else {}
    hoje = HOJE_DA_ROTA[0] or dt.date.today()
    refeitos = {cod for cod in guard if cod not in congelados
                and cod in por_vendedor}
    if refeitos and dias and dias[0][0] < hoje:
        for cod in refeitos:
            fv = dict(guard[cod])
            fv["visitas"] = [x for x in fv.get("visitas") or ()
                             if (data_de(x[1]) or hoje) < hoje]
            passado += _linhas_da_rota_fixa(
                cfg, fv, cod, vend.get(cod, {}),
                [c for cs in por_vendedor[cod].values() for c in cs],
                zonas, dias)
        semana_feita = {(r["COD_VENDEDOR"], r["CHAVE_CLIENTE"],
                         r["DATA"].isocalendar()[:2]) for r in passado}
        linhas[:] = [r for r in linhas if r["COD_VENDEDOR"] not in refeitos
                     or (r["DATA"] >= hoje and (
                         r["COD_VENDEDOR"], r["CHAVE_CLIENTE"],
                         r["DATA"].isocalendar()[:2]) not in semana_feita)]
        if passado:
            avisos_da_agenda.append(
                f"{len(refeitos)} vendedor(es) refeito(s) de "
                f"{hoje:%d/%m} em diante; os dias anteriores ficaram como "
                f"estavam na rota guardada")

    # (27/10, Alexandre) ROTEIRIZACAO POR LUGAR: cidade > bairro > rua >
    # numero, 1 cidade por dia (a partir de POR_LUGAR_DESDE)
    por_lugar = por_lugar_ativo(cfg) and bool(dias)
    if por_lugar:
        desde = dias[0][0] if REESCREVER_PASSADO[0] else max(
            hoje, dias[0][0])
        linhas = _reorganizar_por_lugar(cfg, linhas, vend, por_vendedor,
                                        zonas, dias, desde,
                                        avisos=avisos_da_agenda)

    # o mesmo cliente nao pode ser visitado duas vezes no mesmo dia: quando
    # a marcacao a mao empurra a 2a visita para cima da 1a, uma sai
    vistos = set()
    limpas = []
    for r in sorted(linhas, key=lambda x: (x["CHAVE_CLIENTE"], x["DATA"],
                                           x["VISITA_NO_MES"])):
        chave = (r["CHAVE_CLIENTE"], r["DATA"])
        if chave in vistos:
            continue
        vistos.add(chave)
        limpas.append(r)
    linhas = limpas

    # a ordem do dia e do VENDEDOR, nao da zona: se ele atende duas zonas no
    # mesmo dia, a numeracao tem de correr de 1 a N sem reiniciar. (06/10)
    # Dentro do dia, o CAMINHO MAIS CURTO entre os clientes, saindo do lado
    # da base do vendedor (antes era o nome do bairro: ficava alfabetica).
    linhas = _ordenar_os_dias(linhas, vend, por_lugar=por_lugar)
    atual = None
    contador = 0
    for i, r in enumerate(linhas, start=1):
        chave = (r["COD_VENDEDOR"], r["DATA"])
        if chave != atual:
            atual, contador = chave, 0
        contador += 1
        r["ORDEM_DE_VISITA"] = contador
        r["ID"] = i
    if congelados or passado:
        for cod in congelados:
            linhas += _linhas_da_rota_fixa(
                cfg, fixa["vendedores"][cod], cod, vend.get(cod, {}),
                [c for cs in por_vendedor[cod].values() for c in cs],
                zonas, dias)
        linhas += passado
        linhas.sort(key=lambda r: (r["COD_VENDEDOR"], r["DATA"],
                                   r["ORDEM_DE_VISITA"]))
        for i, r in enumerate(linhas, start=1):
            r["ID"] = i
    gerar_rota.avisos = avisos_da_agenda
    return linhas


# ==========================================================================
# Excel
# ==========================================================================
AZUL = "1F4E79"
CINZA = "F2F2F2"
AMARELO = "FFF2CC"
VERDE = "E2EFDA"
BORDA = Border(*(Side(style="thin", color="D0D0D0"),) * 4)


def _cabecalho(ws, titulos, largura=None, linha=1):
    for c, t in enumerate(titulos, start=1):
        cel = ws.cell(linha, c, t)
        cel.font = Font(bold=True, color="FFFFFF", size=9)
        cel.fill = PatternFill("solid", fgColor=AZUL)
        cel.alignment = Alignment(horizontal="center", vertical="center",
                                  wrap_text=True)
        cel.border = BORDA
    ws.row_dimensions[linha].height = 32
    if largura:
        for i, w in enumerate(largura, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    # coordenada em texto: usar ws.cell() aqui criaria a celula e faria o
    # proximo ws.append() pular uma linha, deixando a linha 2 em branco
    ws.freeze_panes = f"A{linha + 1}"


def gravar_rota(cfg, clientes, caminho, resumo=None):
    """Escreve o Excel da rota do mes + as abas gerenciais."""
    linhas = gerar_rota(cfg, clientes)
    resumo = resumo if resumo is not None else indicadores(cfg, clientes)
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # ---- aba 1: a rota --------------------------------------------------
    ws = wb.active
    ws.title = "ROTA"
    cols = ["ID", "SEMANA", "DIA_DO_MES", "DATA", "DIA_DA_SEMANA",
            "ORDEM_DE_VISITA", "VISITA_NO_MES", "SUPERVISOR", "COD_VENDEDOR",
            "VENDEDOR", "COD_ZONA", "ZONA", "UF", "CIDADE", "BAIRRO",
            "COD_CLIENTE",
            "LOJA", "NOME_CLIENTE", "ENDERECO", "NUMERO", "CONTATO",
            "TELEFONE",
            "LIMITE_DISPONIVEL", "VALOR_EM_ATRASO", "INADIMPLENTE",
            "CURVA_RECEITA", "STATUS_CLIENTE", "STATUS_PLANNER",
            "COD_ULTIMO_VENDEDOR"]
    larg = [6, 11, 8, 11, 11, 8, 8, 26, 10, 26, 10, 30, 5, 20, 22, 11, 6, 38,
            34, 8, 18, 16, 15, 14, 12, 8, 14, 14, 12]
    _cabecalho(ws, cols, larg)
    for r in linhas:
        ws.append([r.get(c) for c in cols])
    col_limite = cols.index("LIMITE_DISPONIVEL") + 1
    col_atraso = cols.index("VALOR_EM_ATRASO") + 1
    for l in range(2, ws.max_row + 1):
        ws.cell(l, 4).number_format = "DD/MM/YYYY"
        ws.cell(l, col_limite).number_format = '#,##0.00'
        ws.cell(l, col_atraso).number_format = '#,##0.00'
        for c in range(1, len(cols) + 1):
            ws.cell(l, c).font = Font(size=9)
            ws.cell(l, c).border = BORDA
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"

    # ---- aba 2: gerencial por zona -------------------------------------
    wz = wb.create_sheet("GERENCIAL_ZONA")
    wz["A1"] = f"BAP - {MESES_PT[int(cfg['mes'][5:7])]}/{cfg['mes'][:4]}"
    wz["A1"].font = Font(bold=True, size=13, color=AZUL)
    wz["A2"] = (f"{resumo['du']} dias uteis  |  "
                f"{resumo['total']['clientes']} clientes  |  "
                f"{resumo['total']['cidades']} cidades  |  "
                f"{resumo['total']['bairros']} bairros")
    wz["A2"].font = Font(size=10, italic=True)
    cabz = ["COD", "ZONA", "UF", "COD VEND", "VENDEDOR", "SUPERVISOR",
            "CLIENTES", "CIDADES", "BAIRROS", "FREQ", "VISITAS/MES",
            "CLIENTES/DIA", "CAP/DIA", "DIAS NECESS.", "FOLGA (DU)",
            "FAT. MENSAL MEDIO R$", "FAT. / CLIENTE COMPRANTE R$",
            "FAT. ACUMULADO R$", "CLIENTES COMPRANTES", "% COMPRANTES",
            "CURVA S", "CURVA A", "CURVA B", "CURVA C", "CURVA Z",
            "COM LIMITE", "LIMITE DISP. R$",
            "INADIMPL. QTD", "INADIMPL. R$", "INADIMPL. %",
            "ATIVO", "CHURN 30", "CHURN 60", "CHURN 90", "CHURN 90+",
            "NUNCA COMPROU"]
    largz = [10, 32, 5, 9, 26, 26] + [10] * 9 + [16, 18, 16, 13, 12] \
        + [8] * 5 + [11, 15, 12, 14, 11] + [10] * 6
    _cabecalho(wz, cabz, largz, linha=4)
    for r in sorted(resumo["zona"], key=lambda x: (-x["clientes"], x["zona_nome"])):
        wz.append([
            r["codigo"], r["zona_nome"], r["uf"], r["vendedor"],
            r["vendedor_nome"], r["supervisor"], r["clientes"], r["cidades"],
            r["bairros"], r["frequencia"], r["visitas_mes"], r["clientes_dia"],
            r["capacidade_dia"], r["dias_necessarios"], r["folga_dias"],
            r["faturamento_mensal"], r["faturamento_por_comprante"],
            r["receita_acumulada"], r["compradores"],
            r["pct_compradores"] / 100.0,
            r["curva_S"], r["curva_A"], r["curva_B"], r["curva_C"], r["curva_Z"],
            r["com_limite"], r["limite_disponivel"], r["inadimplentes"],
            r["valor_atraso"], r["pct_inadimplencia"] / 100.0,
            r["status_ATIVO"], r["status_CHURN 30"], r["status_CHURN 60"],
            r["status_CHURN 90"], r[f"status_{SITUACAO_90}"],
            r["status_NUNCA COMPROU"],
        ])
    dinheiros = [cabz.index(x) + 1 for x in
                 ("FAT. MENSAL MEDIO R$", "FAT. / CLIENTE COMPRANTE R$",
                  "FAT. ACUMULADO R$", "LIMITE DISP. R$", "INADIMPL. R$")]
    percentuais = [cabz.index(x) + 1 for x in ("% COMPRANTES", "INADIMPL. %")]
    col_vend = cabz.index("COD VEND") + 1
    col_folga = cabz.index("FOLGA (DU)") + 1
    for l in range(5, wz.max_row + 1):
        for c in range(1, len(cabz) + 1):
            cel = wz.cell(l, c)
            cel.font = Font(size=9)
            cel.border = BORDA
            if c > 6:
                cel.alignment = Alignment(horizontal="center")
        for c in dinheiros:
            wz.cell(l, c).number_format = '#,##0.00'
        for c in percentuais:
            wz.cell(l, c).number_format = '0.0%'
        wz.cell(l, 1).font = Font(size=9, bold=True)
        if not wz.cell(l, col_vend).value:
            for c in range(1, len(cabz) + 1):
                wz.cell(l, c).fill = PatternFill("solid", fgColor=AMARELO)
        elif (wz.cell(l, col_folga).value or 0) < 0:
            wz.cell(l, col_folga).fill = PatternFill("solid", fgColor="F8CBAD")
    wz.auto_filter.ref = f"A4:{get_column_letter(len(cabz))}{wz.max_row}"

    # ---- abas 3 a 5: visoes derivadas ----------------------------------
    def aba_derivada(nome, chave, rotulo, largura_1=30):
        w = wb.create_sheet(nome)
        cab = [rotulo, "CLIENTES", "CIDADES", "BAIRROS", "VISITAS/MES",
               "CLIENTES/DIA", "FAT. MENSAL MEDIO R$",
               "FAT. / CLIENTE COMPRANTE R$", "FAT. ACUMULADO R$",
               "CLIENTES COMPRANTES", "CURVA S", "CURVA A", "CURVA B",
               "CURVA C", "CURVA Z", "COM LIMITE", "LIMITE DISP. R$",
               "INADIMPL. QTD", "INADIMPL. R$", "INADIMPL. %",
               "CARTEIRA ATIVA", "NUNCA COMPROU"]
        _cabecalho(w, cab, [largura_1, 11, 11, 11, 11, 11, 16, 18, 16, 13]
                   + [11] * (len(cab) - 10))
        for r in resumo[chave]:
            if chave == "vendedor":
                titulo = f"{r['vendedor']} - {r['vendedor_nome']}" \
                    if r["vendedor"] not in ("", "(sem vendedor)") else "(SEM VENDEDOR)"
            elif chave == "cidade":
                titulo = f"{r['uf']} - {r['cidade_nome']}"
            else:
                titulo = r[chave]
            w.append([titulo, r["clientes"], r["cidades"], r["bairros"],
                      r["visitas_mes"], r["clientes_dia"],
                      r["faturamento_mensal"], r["faturamento_por_comprante"],
                      r["receita_acumulada"], r["compradores"],
                      r["curva_S"], r["curva_A"], r["curva_B"], r["curva_C"],
                      r["curva_Z"], r["com_limite"], r["limite_disponivel"],
                      r["inadimplentes"], r["valor_atraso"],
                      r["pct_inadimplencia"] / 100.0, r["carteira_ativa"],
                      r["status_NUNCA COMPROU"]])
        dinheiro_cols = [cab.index(x) + 1 for x in
                         ("FAT. MENSAL MEDIO R$", "FAT. / CLIENTE COMPRANTE R$",
                          "FAT. ACUMULADO R$", "LIMITE DISP. R$",
                          "INADIMPL. R$")]
        for l in range(2, w.max_row + 1):
            for c in range(1, len(cab) + 1):
                w.cell(l, c).font = Font(size=9)
                w.cell(l, c).border = BORDA
                if c > 1:
                    w.cell(l, c).alignment = Alignment(horizontal="center")
            for c in dinheiro_cols:
                w.cell(l, c).number_format = '#,##0.00'
            w.cell(l, cab.index("INADIMPL. %") + 1).number_format = '0.0%'
        w.auto_filter.ref = f"A1:{get_column_letter(len(cab))}{w.max_row}"

    aba_derivada("GERENCIAL_VENDEDOR", "vendedor", "VENDEDOR", 34)
    aba_derivada("GERENCIAL_SUPERVISOR", "supervisor", "SUPERVISOR", 30)
    aba_derivada("GERENCIAL_CIDADE", "cidade", "CIDADE", 28)

    # ---- aba 6: BAP total ----------------------------------------------
    wt = wb.create_sheet("BAP_TOTAL")
    t = resumo["total"]
    wt["A1"] = "BAP - VISAO TOTAL"
    wt["A1"].font = Font(bold=True, size=14, color=AZUL)
    itens = [
        ("Mes de referencia", f"{MESES_PT[int(cfg['mes'][5:7])]}/{cfg['mes'][:4]}"),
        ("Dias uteis", resumo["du"]),
        ("Clientes na base", t["clientes"]),
        ("Cidades atendidas", t["cidades"]),
        ("Bairros atendidos", t["bairros"]),
        ("Visitas no mes", t["visitas_mes"]),
        ("Clientes por dia (media BAP)", t["clientes_dia"]),
        ("", ""),
        ("Faturamento mensal medio R$", t["faturamento_mensal"]),
        ("Faturamento por cliente comprante R$", t["faturamento_por_comprante"]),
        ("Faturamento acumulado R$", t["receita_acumulada"]),
        ("Clientes que compraram no periodo", t["compradores"]),
        ("Clientes que ja compraram alguma vez", t["compradores_historico"]),
        ("", ""),
        ("Curva S", t["curva_S"]), ("Curva A", t["curva_A"]),
        ("Curva B", t["curva_B"]), ("Curva C", t["curva_C"]),
        ("Curva Z (sem faturamento)", t["curva_Z"]),
        ("", ""),
        ("Clientes com limite", t["com_limite"]),
        ("Limite disponivel R$", t["limite_disponivel"]),
        ("Inadimplentes (qtd)", t["inadimplentes"]),
        ("Inadimplencia R$", t["valor_atraso"]),
        ("Inadimplencia %", t["pct_inadimplencia"] / 100.0),
        ("", ""),
        ("Ativos", t["status_ATIVO"]), ("Churn 30", t["status_CHURN 30"]),
        ("Churn 60", t["status_CHURN 60"]), ("Churn 90", t["status_CHURN 90"]),
        ("Churn 90+", t[f"status_{SITUACAO_90}"]),
        ("Nunca compraram", t["status_NUNCA COMPROU"]),
        ("", ""),
        ("Linhas geradas na rota", len(linhas)),
        ("Zonas com vendedor", sum(1 for z in resumo["zona"] if z["vendedor"])),
        ("Zonas SEM vendedor", sum(1 for z in resumo["zona"]
                                   if not z["vendedor"] and z["clientes"])),
    ]
    for i, (rotulo, valor) in enumerate(itens, start=3):
        wt.cell(i, 1, rotulo).font = Font(bold=not rotulo.startswith(" "), size=10)
        cel = wt.cell(i, 2, valor)
        cel.font = Font(size=10)
        if "R$" in rotulo:
            cel.number_format = '#,##0.00'
        if rotulo.endswith("%"):
            cel.number_format = '0.0%'
    wt.column_dimensions["A"].width = 34
    wt.column_dimensions["B"].width = 20

    wb.calculation.fullCalcOnLoad = True
    wb.save(caminho)
    wb.close()
    return linhas, resumo


# ==========================================================================
# PLANNER - o Excel que o Alexandre leva para a rua
# ==========================================================================
# Os codigos saem EXATAMENTE como foram digitados no cadastro. Quem tem
# zero na frente ("000015") vai como texto e conserva o zero; quem nao tem
# ("8") vai como numero, para dar para somar e cruzar. Ver codigo_excel().
COLUNAS_PLANNER = [
    # (titulo, chave, largura, formato)
    ("MES_VISITA", "MES_VISITA", 11, None),
    ("SEMANA_VISITA", "SEMANA_VISITA", 13, None),
    ("DIA_VISITA", "DIA_VISITA", 11, None),
    ("DIA_DA_SEMANA", "DIA_DA_SEMANA", 13, None),
    ("DATA_VISITA", "DATA", 12, "DD/MM/YYYY"),
    ("ORDEM_VISITA", "ORDEM_DE_VISITA", 12, None),
    ("COD_ZONA", "COD_ZONA", 11, None),
    ("ZONA", "ZONA", 30, None),
    ("COD_GERENTE", "COD_GERENTE", 13, None),
    ("COD_GERENTE_MAXIMA", "COD_GERENTE_MAXIMA", 19, None),
    ("GERENTE", "GERENTE", 26, None),
    ("COD_SUPERVISOR", "COD_SUPERVISOR", 15, None),
    ("COD_SUPERVISOR_MAXIMA", "COD_SUPERVISOR_MAXIMA", 22, None),
    ("SUPERVISOR", "SUPERVISOR", 26, None),
    ("COD_VENDEDOR", "COD_VENDEDOR_EXCEL", 14, None),
    ("COD_VENDEDOR_MAXIMA", "COD_VENDEDOR_MAXIMA", 20, None),
    ("VENDEDOR", "VENDEDOR", 28, None),
    ("CONTA_SUPERVISOR", "CONTA_SUPERVISOR", 18, None),
    ("VENDEDOR_ATIVO", "VENDEDOR_ATIVO", 16, None),
    ("COD_CLIENTE", "COD_CLIENTE", 12, None),
    ("LOJA", "LOJA", 7, None),
    ("CLIENTE", "NOME_CLIENTE", 40, None),
    ("NOME_FANTASIA", "NOME_FANTASIA", 30, None),
    ("SEGMENTO", "SEGMENTO", 24, None),
    ("SUBSEGMENTO", "SUBSEGMENTO", 28, None),
    ("UF", "UF", 5, None),
    ("CIDADE", "CIDADE", 22, None),
    ("BAIRRO", "BAIRRO", 24, None),
    ("ENDERECO", "ENDERECO", 36, None),
    ("NUMERO", "NUMERO", 8, None),
    ("CONTATO", "CONTATO", 20, None),
    ("TELEFONE", "TELEFONE", 16, None),
    ("CURVA", "CURVA_RECEITA", 8, None),
    ("STATUS_CLIENTE", "STATUS_CLIENTE", 15, None),
    ("STATUS_PLANNER", "STATUS_PLANNER", 15, None),
    ("LIMITE_DISPONIVEL", "LIMITE_DISPONIVEL", 17, '#,##0.00'),
    ("VALOR_EM_ATRASO", "VALOR_EM_ATRASO", 16, '#,##0.00'),
    ("INADIMPLENTE", "INADIMPLENTE", 13, None),
    # MEDIA MENSAL, nao soma da janela: M3M e M6M sao medias por mes
    ("FAT_M3M", "MEDIA_MENSAL", 14, '#,##0.00'),
    ("FAT_M3M_ANTERIOR", "MEDIA_MENSAL_ANTERIOR", 18, '#,##0.00'),
    ("FAT_M6M", "MEDIA_MENSAL_6M", 14, '#,##0.00'),
    ("FAT_ACUMULADO", "RECEITA_ACUMULADA", 15, '#,##0.00'),
    ("ULTIMA_COMPRA", "ULTIMA_COMPRA", 13, "DD/MM/YYYY"),
    ("DIAS_SEM_COMPRA", "DIAS_SEM_COMPRA", 15, None),
    ("COD_ULTIMO_VENDEDOR", "COD_ULTIMO_VENDEDOR", 17, None),
    # (06/10) o ponto que a rota usou
    ("LATITUDE", "LATITUDE", 12, "0.000000"),
    ("LONGITUDE", "LONGITUDE", 12, "0.000000"),
    # (17/10) TOP 30 / LIMITE e se a visita e semanal
    ("PRIORIDADE_ROTA", "PRIORIDADE_ROTA", 18, None),
    ("VISITA_SEMANAL", "VISITA_SEMANAL", 15, None),
]

# a mesma coisa sem repetir o cliente: uma linha por cliente, com quantas
# visitas ele tem no mes e em que dias
COLUNAS_CLIENTE = [
    ("COD_ZONA", "COD_ZONA", 11, None),
    ("ZONA", "ZONA", 30, None),
    ("COD_GERENTE", "COD_GERENTE", 13, None),
    ("COD_GERENTE_MAXIMA", "COD_GERENTE_MAXIMA", 19, None),
    ("GERENTE", "GERENTE", 26, None),
    ("COD_SUPERVISOR", "COD_SUPERVISOR", 15, None),
    ("COD_SUPERVISOR_MAXIMA", "COD_SUPERVISOR_MAXIMA", 22, None),
    ("SUPERVISOR", "SUPERVISOR", 26, None),
    ("COD_VENDEDOR", "COD_VENDEDOR_EXCEL", 14, None),
    ("COD_VENDEDOR_MAXIMA", "COD_VENDEDOR_MAXIMA", 20, None),
    ("VENDEDOR", "VENDEDOR", 28, None),
    ("CONTA_SUPERVISOR", "CONTA_SUPERVISOR", 18, None),
    ("VENDEDOR_ATIVO", "VENDEDOR_ATIVO", 16, None),
    ("COD_CLIENTE", "COD_CLIENTE", 12, None),
    ("LOJA", "LOJA", 7, None),
    ("CLIENTE", "NOME_CLIENTE", 40, None),
    ("NOME_FANTASIA", "NOME_FANTASIA", 30, None),
    ("SEGMENTO", "SEGMENTO", 24, None),
    ("SUBSEGMENTO", "SUBSEGMENTO", 28, None),
    ("UF", "UF", 5, None),
    ("CIDADE", "CIDADE", 22, None),
    ("BAIRRO", "BAIRRO", 24, None),
    ("ENDERECO", "ENDERECO", 36, None),
    ("NUMERO", "NUMERO", 8, None),
    ("CONTATO", "CONTATO", 20, None),
    ("TELEFONE", "TELEFONE", 16, None),
    ("CURVA", "CURVA_RECEITA", 8, None),
    ("STATUS_CLIENTE", "STATUS_CLIENTE", 15, None),
    ("STATUS_PLANNER", "STATUS_PLANNER", 15, None),
    ("LIMITE_DISPONIVEL", "LIMITE_DISPONIVEL", 17, '#,##0.00'),
    ("VALOR_EM_ATRASO", "VALOR_EM_ATRASO", 16, '#,##0.00'),
    ("INADIMPLENTE", "INADIMPLENTE", 13, None),
    # MEDIA MENSAL, nao soma da janela: M3M e M6M sao medias por mes
    ("FAT_M3M", "MEDIA_MENSAL", 14, '#,##0.00'),
    ("FAT_M3M_ANTERIOR", "MEDIA_MENSAL_ANTERIOR", 18, '#,##0.00'),
    ("FAT_M6M", "MEDIA_MENSAL_6M", 14, '#,##0.00'),
    ("FAT_ACUMULADO", "RECEITA_ACUMULADA", 15, '#,##0.00'),
    ("ULTIMA_COMPRA", "ULTIMA_COMPRA", 13, "DD/MM/YYYY"),
    ("DIAS_SEM_COMPRA", "DIAS_SEM_COMPRA", 15, None),
    ("COD_ULTIMO_VENDEDOR", "COD_ULTIMO_VENDEDOR", 17, None),
    ("VISITAS_NO_MES", "VISITAS_NO_MES", 15, None),
    ("DIAS_DE_VISITA", "DIAS_DE_VISITA", 18, None),
    ("SEMANAS_DE_VISITA", "SEMANAS_DE_VISITA", 19, None),
    ("LATITUDE", "LATITUDE", 12, "0.000000"),
    ("LONGITUDE", "LONGITUDE", 12, "0.000000"),
]


def nome_do_planner(quando=None, mes: str = "") -> str:
    """PLANNER_BAP_<mes da rota>_AAAAMMDD.xlsx - o mes e a data em que foi
    gerado (sem mes: PLANNER_BAP_AAAAMMDD.xlsx, o nome antigo)."""
    d = quando or dt.date.today()
    if mes:
        return f"PLANNER_BAP_{mes}_{d.strftime('%Y%m%d')}.xlsx"
    return f"PLANNER_BAP_{d.strftime('%Y%m%d')}.xlsx"


# --------------------------------------------------------------------------
# O PLANNER MES A MES
# --------------------------------------------------------------------------
def mes_seguinte(mes: str, n: int = 1) -> str:
    a, m = int(mes[:4]), int(mes[5:7]) + n
    while m > 12:
        a, m = a + 1, m - 12
    while m < 1:
        a, m = a - 1, m + 12
    return f"{a:04d}-{m:02d}"


def rotulo_do_mes(mes: str) -> str:
    """2026-09 -> SET/2026"""
    return f"{MESES_PT[int(mes[5:7])][:3].upper()}/{mes[:4]}" if mes else ""


def gerar_planner_do_mes(raiz, mes: str) -> Path:
    """
    Refaz o PLANNER daquele mes a partir da configuracao do mes (equipe,
    zonas, quem responde a quem) e da BASE_CLIENTE - o mesmo que o
    EXPORTAR do Planner faz. E o RECALCULAR do Gerador de Meta: mudou a
    equipe de setembro no Planner, a meta de setembro segue.
    """
    import pastas_bap as pb                             # noqa: PLC0415
    raiz = Path(raiz)
    cfg = carregar_config(pb.config_do_planner(raiz, mes))
    cfg["mes"] = mes
    clientes = ler_base_cliente(raiz / pb.RELATORIOS / "BASE_CLIENTE.xlsx")
    aplicar_parametros(cfg, clientes)
    migrar_areas_antigas(cfg, clientes)
    sincronizar_areas(cfg, clientes)
    destino = raiz / getattr(pb, "ROTEIRIZACAO", pb.RELATORIOS) / \
        nome_do_planner(mes=mes)
    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_planner(cfg, clientes, destino)
    pb.aposentar_planners(raiz)
    return pb.planner_do_mes(raiz, mes) or destino


def duplicar_config(cfg: dict, mes: str) -> dict:
    """A configuracao inteira (zonas, equipe, areas, excecoes, parametros)
    copiada para outro mes. O filtro do resumo nao vai junto."""
    nova = json.loads(json.dumps(cfg))
    nova["mes"] = mes
    nova.pop("filtro_resumo", None)
    # a cidade tirada da rota vale so para o mes em que foi tirada
    nova.pop("rota_cidade_fora", None)
    # (17/10) a excecao importada a cidade base tambem e do mes
    nova.pop(ROTA_CIDADE_LIBERADA, None)
    return nova


def _completar_planner(cfg: dict, linhas: list, clientes: list) -> list:
    """Poe na linha da rota o que o PLANNER precisa alem do que a rota traz."""
    porcliente = {c["CHAVE_CLIENTE"]: c for c in clientes}
    mes_nome = MESES_PT[int(cfg["mes"][5:7])]
    for r in linhas:
        c = porcliente.get(r["CHAVE_CLIENTE"], {})
        r["MES_VISITA"] = f"{mes_nome}/{cfg['mes'][:4]}"
        r["SEMANA_VISITA"] = r["SEMANA"]
        r["DIA_VISITA"] = r["DIA_DO_MES"]
        cod_v = r.get("COD_VENDEDOR", "")
        vendedor = pessoa_por_codigo(cfg, cod_v)
        supervisor = chefe_de(cfg, cod_v)
        gerente = gerente_de(cfg, cod_v)
        r["COD_VENDEDOR_EXCEL"] = codigo_excel(cod_v)
        r["COD_VENDEDOR_MAXIMA"] = codigo_excel(vendedor.get("cod_maxima"))
        r["COD_SUPERVISOR"] = codigo_excel(supervisor.get("cod_protheus"))
        r["COD_SUPERVISOR_MAXIMA"] = codigo_excel(supervisor.get("cod_maxima"))
        r["SUPERVISOR"] = supervisor.get("nome", "")
        r["COD_GERENTE"] = codigo_excel(gerente.get("cod_protheus"))
        r["COD_GERENTE_MAXIMA"] = codigo_excel(gerente.get("cod_maxima"))
        r["GERENTE"] = gerente.get("nome", "")
        r["NUMERO"] = c.get("NUMERO", "")
        r["NOME_FANTASIA"] = c.get("NOME_FANTASIA", "")
        r["RECEITA_PERIODO"] = c.get("RECEITA_PERIODO", 0.0)
        r["RECEITA_6M"] = c.get("RECEITA_6M", c.get("RECEITA_PERIODO", 0.0))
        # o que sai no PLANNER como FAT_M3M e FAT_M6M e a MEDIA MENSAL
        r["MEDIA_MENSAL"] = c.get("MEDIA_MENSAL", 0.0)
        r["MEDIA_MENSAL_ANTERIOR"] = c.get("MEDIA_MENSAL_ANTERIOR", 0.0)
        r["MEDIA_MENSAL_6M"] = c.get(
            "MEDIA_MENSAL_6M", round(r["RECEITA_6M"] / 6, 2))
        r["RECEITA_ACUMULADA"] = c.get("RECEITA_ACUMULADA", 0.0)
        r["ULTIMA_COMPRA"] = c.get("ULTIMA_COMPRA")
        r["DIAS_SEM_COMPRA"] = c.get("DIAS_SEM_COMPRA")
    return linhas


def resumir_por_cliente(linhas: list) -> list:
    """
    Junta as visitas por cliente: uma linha por cliente, dizendo quantas
    visitas ele tem no mes, em que dias e em que semanas. E a visao
    "sem repetir o cliente" do analitico.
    """
    porcliente = {}
    for r in linhas:
        chave = r["CHAVE_CLIENTE"]
        reg = porcliente.get(chave)
        if reg is None:
            reg = porcliente[chave] = dict(r)
            reg["_dias"], reg["_semanas"] = [], []
        reg["_dias"].append(r["DIA_DO_MES"])
        reg["_semanas"].append(r["SEMANA"])
    saida = []
    for reg in porcliente.values():
        dias = sorted(set(reg.pop("_dias")))
        semanas = sorted(set(reg.pop("_semanas")))
        reg["VISITAS_NO_MES"] = len(dias)
        reg["DIAS_DE_VISITA"] = ", ".join(str(d) for d in dias)
        reg["SEMANAS_DE_VISITA"] = ", ".join(
            s.replace("Semana ", "") for s in semanas)
        saida.append(reg)
    saida.sort(key=lambda r: (r["COD_VENDEDOR"], r["UF"], r["CIDADE"],
                              r["BAIRRO"], r["NOME_CLIENTE"]))
    return saida


def _folha_planner(ws, linhas, colunas=None):
    """Escreve as linhas numa aba, com formato e cor."""
    colunas = colunas or COLUNAS_PLANNER
    titulos = [t for t, _, _, _ in colunas]
    larguras = [w for _, _, w, _ in colunas]
    _cabecalho(ws, titulos, larguras)
    for r in linhas:
        ws.append([r.get(chave) for _, chave, _, _ in colunas])
    formatos = {i + 1: f for i, (_, _, _, f) in enumerate(colunas) if f}
    vermelho = PatternFill("solid", fgColor="FBE4E4")
    col_inad = titulos.index("INADIMPLENTE") + 1
    n_col = len(titulos)
    if ws.max_row >= 2:
        # o estilo de cada coluna e montado UMA vez (normal e vermelho) e
        # copiado celula a celula: montar Font/Border em cada uma das
        # 100 mil celulas levava a maior parte do tempo de gravar
        from copy import copy as _copiar                # noqa: PLC0415
        normal, inad = {}, {}
        for c in range(1, n_col + 1):
            cel = ws.cell(2, c)
            cel.font = Font(size=9)
            cel.border = BORDA
            if c in formatos:
                cel.number_format = formatos[c]
            normal[c] = _copiar(cel._style)
            cel.fill = vermelho
            inad[c] = _copiar(cel._style)
            cel._style = _copiar(normal[c])
        for linha in ws.iter_rows(min_row=2, max_row=ws.max_row,
                                  max_col=n_col):
            estilo = inad if linha[col_inad - 1].value == "SIM" else normal
            for c, cel in enumerate(linha, start=1):
                cel._style = _copiar(estilo[c])
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(titulos))}{ws.max_row}"


# ==========================================================================
# O ARQUIVO DA ROTA NO FORMATO DO PROTHEUS
# ==========================================================================
# O Protheus nao le o Excel do PLANNER: ele espera a rota como uma LISTA
# DE OBJETOS JSON, um por visita, com estes DEZ campos e nesta ordem.
# (27/10, Alexandre - validacao da Maxima, layout ERP_MXSROTACLI) sairam
# hash, hashregistro, LATITUDE e LONGITUDE (nao fazem parte deste
# endpoint) e a periodicidade so vai com os valores do layout
# (PERIODICIDADES_MAXIMA: 1, 7, 14, 15, 21, 28, 30, 35, 42, 45). HORAVISITA
# e MINUTOVISITA sao opcionais e nao vao. A coordenada continua no .json da
# BASE de clientes.
#
#     codcli ......... codigo do cliente: A1_COD com 6 digitos colado no
#                      A1_LOJA com 2 -> 010989 + 01 = "01098901"
#     codusur ........ codigo do vendedor, 6 digitos ("000015")
#     codcompromisso . AAAAMMDDHHMMSS do momento da exportacao. E o mesmo
#                      em todas as linhas: ele identifica a REMESSA
#     dtproxvisita ... a data EXATA da visita (o ERP calcula - formato
#                      combinado com a Maxima em 07/10/2026)
#     periodicidade .. de quantos em quantos dias o vendedor volta ali.
#                      Sai da PERIODICIDADE_DA_CURVA (a tabela que monta a
#                      rota), levada para o valor aceito pela Maxima mais
#                      perto (periodicidade_maxima: S/A 7, B 14, C 30,
#                      D/Z 60 -> 45)
#     sequencia ...... a ordem da visita no dia (1 = o primeiro cliente)
#     diasemana ...... SEGUNDA, TERCA, QUARTA, QUINTA, SEXTA ou SABADO,
#                      maiuscula e sem acento
#     numsemana ...... SEMPRE 1. A Maxima gera a visita na N-esima
#                      DIASEMANA a partir da dtproxvisita; com a data exata,
#                      N = 1 cai na propria data. (Ate 07/10 ia a semana
#                      do calendario e empurrava a visita N-1 semanas.)
#     dtinicio ....... 2000-01-01 e
#     dtfinal ........ (20/11, Alexandre) dtproxvisita + periodicidade - 1
#                      dia (dtfinal_protheus), com a MESMA periodicidade do
#                      campo acima: a Maxima repete a linha a cada
#                      periodicidade dias ate o dtfinal, entao cada remessa
#                      gera UMA visita e nao se sobrepoe a seguinte. Nenhuma
#                      linha sai com 3000-01-01 (antes eram 753 duplicados).
#
# (20/11, Alexandre) FICAM FORA DO ARQUIVO (motivo_fora_da_maxima): cliente
# INATIVO, cliente INTERNO (meta_nucleo.e_cliente_interno), a conta 000040
# (vendedor de teste). O SABADO-DEPOSITO (1o sabado do mes) VOLTA ao arquivo,
# com o dtfinal curto (dtfinal_protheus), R-20261120-111303: nenhum cliente
# ativo some da Maxima.
#
# As duas datas saem no formato do exemplo: "2026-09-24T00:00:00".
VIGENCIA_INICIO_PROTHEUS = "2000-01-01T00:00:00"
MOTIVOS_FORA_DA_MAXIMA = ("INATIVO", "INTERNO", "CONTA_000040")
                          # na ordem de precedencia
CONTA_TESTE_MAXIMA = "000040"
DIAS_PROTHEUS = ["SEGUNDA", "TERCA", "QUARTA", "QUINTA", "SEXTA",
                 "SABADO", "DOMINGO"]
CAMPOS_PROTHEUS = ["codcli", "codusur", "codcompromisso", "dtproxvisita",
                   "periodicidade", "sequencia", "diasemana", "numsemana",
                   "dtinicio", "dtfinal"]
# o que cada campo quer dizer, para a tela da aba 6 nao precisar repetir
ROTULO_PROTHEUS = {
    "codcli": "CLIENTE (cod+loja)", "codusur": "VENDEDOR",
    "codcompromisso": "COMPROMISSO", "dtproxvisita": "DATA DA VISITA",
    "periodicidade": "PERIODIC.", "sequencia": "SEQ.",
    "diasemana": "DIA DA SEMANA", "numsemana": "SEM.",
    "dtinicio": "VIGENCIA INICIO", "dtfinal": "VIGENCIA FIM",
}
LARGURA_PROTHEUS = [120, 80, 130, 150, 78, 50, 112, 50, 150, 150]


def codigo_do_compromisso(quando=None) -> str:
    """ANO+MES+DIA+HORA+MIN+SEG do momento da exportacao."""
    return (quando or dt.datetime.now()).strftime("%Y%m%d%H%M%S")


def _codcli_protheus(cod, loja) -> str:
    """A1_COD com 6 digitos + A1_LOJA com 2 -> "01098901"."""
    cod = re.sub(r"\D", "", texto(cod))
    loja = re.sub(r"\D", "", texto(loja)) or "0"
    return f"{cod.zfill(6)}{loja.zfill(2)}"


def _codusur_protheus(cod) -> str:
    """O codigo do vendedor com 6 digitos. So digito vira zero a esquerda."""
    cod = texto(cod)
    return cod.zfill(6) if cod.isdigit() else cod


def _data_protheus(d) -> str:
    return f"{d:%Y-%m-%d}T00:00:00"


def dtfinal_protheus(data_visita: dt.date, periodicidade: int) -> str:
    """(20/11, Alexandre) dtfinal = dtproxvisita + periodicidade - 1 dia, no
    formato "AAAA-MM-DDT00:00:00". Funcao pura."""
    return _data_protheus(data_visita
                          + dt.timedelta(days=int(periodicidade) - 1))


def motivo_fora_da_maxima(cfg: dict, linha_rota: dict, cliente=None) -> str:
    """(20/11, Alexandre) "" se a linha vai para o arquivo da Maxima; senao o
    codigo (MOTIVOS_FORA_DA_MAXIMA), nesta precedencia: INATIVO, INTERNO,
    CONTA_000040. O sabado-deposito NAO e motivo (R-20261120-111303). Funcao
    pura."""
    import meta_nucleo as _mn                           # noqa: PLC0415
    cfg = cfg or {}
    if cliente is not None and cliente_inativo(cfg, cliente):
        return "INATIVO"
    nome = linha_rota.get("NOME_CLIENTE") or ""
    fant = linha_rota.get("NOME_FANTASIA") or ""
    if cliente is not None:
        nome = nome or cliente.get("NOME_CLIENTE") or ""
        fant = fant or cliente.get("NOME_FANTASIA") or ""
    if _mn.e_cliente_interno(nome, fant):
        return "INTERNO"
    if _codusur_protheus(linha_rota.get("COD_VENDEDOR")) == CONTA_TESTE_MAXIMA:
        return "CONTA_000040"
    return ""


def remessas_dtfinal_3000(listas_de_linhas: list) -> list:
    """(20/11, R-20261120-111303) Das remessas ja gravadas (cada uma a lista
    de linhas do JSON), devolve so as que tem alguma linha com dtfinal
    3000-01-01 (a regra antiga): [{"quando": "dd/mm/aaaa hh:mm" ou "",
    "vendedores": [codusur ordenados]}], da mais antiga a mais nova. Nao traz
    nome de arquivo, nome nem CNPJ. Funcao pura."""
    saida = []
    for linhas in listas_de_linhas or []:
        linhas = [x for x in (linhas or []) if isinstance(x, dict)]
        if not any(texto(x.get("dtfinal")).startswith("3000-01-01")
                   for x in linhas):
            continue
        comp = Counter(texto(x.get("codcompromisso")) for x in linhas
                       if texto(x.get("codcompromisso")))
        codigo = comp.most_common(1)[0][0] if comp else ""
        try:
            quando = dt.datetime.strptime(codigo, "%Y%m%d%H%M%S")
        except ValueError:
            quando = None
        saida.append({
            "quando": quando.strftime("%d/%m/%Y %H:%M") if quando else "",
            "_ordem": quando or dt.datetime.max,
            "vendedores": sorted({texto(x.get("codusur")) for x in linhas
                                  if texto(x.get("codusur"))})})
    saida.sort(key=lambda r: r["_ordem"])
    for r in saida:
        del r["_ordem"]
    return saida


def remessas_a_excluir(remessas: list) -> list:
    """(20/11, RN-ROT-001, R-20261120-111303) `remessas`: lista de pares
    (data, linhas): `data` e datetime ou None (o mtime do arquivo) e `linhas`
    a lista do JSON. A data da remessa e a do codcompromisso mais comum
    (%Y%m%d%H%M%S); sem ele, vale a `data` do par. Remessa curta = tem linhas
    e nenhuma com dtfinal 3000-01-01. Devolve (no formato de
    remessas_dtfinal_3000) so as remessas com 3000 MAIS NOVAS que a ultima
    curta datada; sem curta, todas as com 3000 (a sem data so entra assim).
    Sem disco, sem nome de arquivo, nome nem CNPJ. Funcao pura."""
    itens = []
    for par in remessas or []:
        try:
            data, linhas = par
        except (TypeError, ValueError):
            continue
        linhas = [x for x in (linhas or []) if isinstance(x, dict)]
        comp = Counter(texto(x.get("codcompromisso")) for x in linhas
                       if texto(x.get("codcompromisso")))
        try:
            quando = dt.datetime.strptime(comp.most_common(1)[0][0],
                                          "%Y%m%d%H%M%S")
        except (IndexError, ValueError):
            quando = data if isinstance(data, dt.datetime) else None
        tem3000 = any(texto(x.get("dtfinal")).startswith("3000-01-01")
                      for x in linhas)
        itens.append((quando, linhas, tem3000))
    curtas = [q for q, linhas, t3 in itens if linhas and not t3 and q]
    corte = max(curtas) if curtas else None
    escolhidas = [linhas for q, linhas, t3 in itens if t3 and (
        corte is None or (q is not None and q > corte))]
    return remessas_dtfinal_3000(escolhidas)


def pedido_exclusao_maxima(remessas: list) -> str:
    """(20/11) O texto do pedido a Máxima para excluir TODAS as remessas
    anteriores com data final 3000-01-01. `remessas`: saida de
    remessas_dtfinal_3000. Cita so o periodo (datas das remessas) e o codusur
    dos vendedores: nunca arquivo, nome nem CNPJ. Funcao pura."""
    remessas = [r for r in (remessas or []) if isinstance(r, dict)]
    datas = [texto(r.get("quando")) for r in remessas if r.get("quando")]
    periodo = (f"{datas[0]} a {datas[-1]}" if len(datas) > 1 and
               datas[0] != datas[-1] else (datas[0] if datas else
                                           "data não identificada"))
    vend = sorted({texto(v) for r in remessas
                   for v in (r.get("vendedores") or []) if texto(v)})
    return ("Pedido de exclusão de remessas da rota (ERP_MXSROTACLI)\n"
            f"Remessas enviadas em: {periodo}\n"
            f"Vendedores (codusur): {', '.join(vend) or 'nenhum'}\n"
            "Favor excluir TODAS as remessas anteriores com data final "
            "3000-01-01 antes de importar a nova.")


def _numero_da_semana(rotulo) -> int:
    """'Semana 3' -> 3."""
    achado = re.search(r"(\d+)", texto(rotulo))
    return int(achado.group(1)) if achado else 1


def linhas_protheus(cfg: dict, clientes: list, chaves=None,
                    compromisso=None, linhas=None) -> list:
    """
    As visitas do mes no layout do Protheus, uma linha por visita.

    A rota NAO e recalculada de outro jeito: sai da mesma gerar_rota que
    monta o PLANNER e o analitico. Aqui so se traduz o nome dos campos.
    `linhas` permite reaproveitar uma rota ja montada, para a tela nao
    refazer a conta a cada clique.
    """
    if linhas is None:
        linhas = gerar_rota(cfg, clientes)
    if chaves is not None:
        alvo = set(chaves)
        linhas = [r for r in linhas if r["CHAVE_CLIENTE"] in alvo]
    compromisso = compromisso or codigo_do_compromisso()
    curva = {c["CHAVE_CLIENTE"]: c.get("CURVA_RECEITA", "Z") for c in clientes}

    por_chave = {c["CHAVE_CLIENTE"]: c for c in clientes}

    saida = []
    for r in sorted(linhas, key=lambda x: (x["COD_VENDEDOR"], x["DATA"],
                                           x["ORDEM_DE_VISITA"])):
        if motivo_fora_da_maxima(cfg, r, por_chave.get(r["CHAVE_CLIENTE"])):
            continue
        data = r["DATA"]
        dias = periodicidade_da_curva(curva.get(r["CHAVE_CLIENTE"],
                                                r.get("CURVA_RECEITA", "Z")))
        if r.get("VISITA_SEMANAL") == "SIM":
            dias = 7                    # (17/10) top 30 / limite: semanal
        # (27/10) so os campos do layout ERP_MXSROTACLI; periodicidade com
        # os valores aceitos (60 -> 45)
        per = periodicidade_maxima(dias)
        saida.append({
            "codcli": _codcli_protheus(r["COD_CLIENTE"], r["LOJA"]),
            "codusur": _codusur_protheus(r["COD_VENDEDOR"]),
            "codcompromisso": compromisso,
            "dtproxvisita": _data_protheus(data),
            "periodicidade": str(per),
            "sequencia": int(r["ORDEM_DE_VISITA"]),
            "diasemana": DIAS_PROTHEUS[data.weekday()],
            "numsemana": 1,
            "dtinicio": VIGENCIA_INICIO_PROTHEUS,
            "dtfinal": dtfinal_protheus(data, per),
        })
    return saida


def gravar_protheus(cfg: dict, clientes: list, caminho, chaves=None,
                    compromisso=None) -> list:
    """Grava o .json da rota no formato do Protheus. Devolve as linhas."""
    linhas = linhas_protheus(cfg, clientes, chaves, compromisso)
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json_protheus(linhas), encoding="utf-8")
    return linhas


def rota_a_partir_de(linhas, data=None) -> list:
    """(26/10, Alexandre) Exportar a rota "so a partir de hoje": das linhas
    no layout do Protheus (rota), so as visitas de `data` (hoje) em diante.
    O mes inteiro continua sendo o padrao."""
    iso = (data or dt.date.today()).isoformat()
    return [x for x in linhas if str(x.get("dtproxvisita") or "")[:10] >= iso]


def sufixo_a_partir_de(data=None) -> str:
    """O pedaco do nome do .json quando sai so de hoje em diante."""
    return f"A_PARTIR_{(data or dt.date.today()):%d-%m}_"


def json_protheus(linhas) -> str:
    """(23/10, Alexandre) o TEXTO dos .json do Protheus/Maxima (rota e base
    de clientes) no formato do modelo: tab na margem e '"CHAVE" : valor'."""
    return json.dumps(linhas, ensure_ascii=False, indent="\t",
                      separators=(",", " : ")) + "\n"


CAMPOS_BASE_PROTHEUS = ["A1_FILIAL", "A1_COD", "A1_LOJA", "A1_VEND",
                        "A1_NOME", "A1_NREDUZ", "SUPERVISOR", "STATUS",
                        "LATITUDE", "LONGITUDE"]


def vendedor_padrao(cfg, chave="vendedor_padrao") -> str:
    """O VENDEDOR PADRAO (aba Parametros): 6 digitos, padrao 000000.
    chave="supervisor_padrao": o SUPERVISOR PADRAO (padrao 000037)."""
    v = re.sub(r"\D", "", texto((cfg.get("parametros") or {}).get(chave)
                                or PARAMETROS_PADRAO[chave]))
    return (v or "0").zfill(6)[-6:]


def supervisor_padrao(cfg) -> str:
    return vendedor_padrao(cfg, "supervisor_padrao")


def status_para_protheus(inativo=False) -> str:
    """O STATUS do cliente NO PLANNER (aba Base cliente): INATIVO e so quem
    o Alexandre inativou ali (e esse cliente sai da rota)."""
    return "INATIVO" if inativo else "ATIVO"


# (20/10, Alexandre) NO .JSON DA BASE DE CLIENTES TODO CLIENTE VAI ATIVO. O
# que decide se o vendedor ve o cliente na Maxima e o A1_VEND (a quem ele
# esta atrelado): quem esta fora do Planner - sem vendedor, cadeira
# vaga/provisoria ou inativado na aba Base cliente - vai com o VENDEDOR
# PADRAO e o SUPERVISOR PADRAO (aba Parametros, 000000 e 000037).
STATUS_JSON = "ATIVO"


def status_no_json(*_ignorado) -> str:
    """O STATUS da base de clientes no .json: sempre ATIVO (20/10)."""
    return STATUS_JSON


def clientes_na_rota(cfg: dict, clientes: list) -> set:
    """As CHAVE_CLIENTE com visita na rota do mes (sabado incluido)."""
    try:
        return {r["CHAVE_CLIENTE"] for r in rota_do_mes(cfg, clientes)}
    except Exception:                                   # noqa: BLE001
        return set()


def filiais_dos_clientes(caminho_tabela) -> dict:
    """{(A1_COD, A1_LOJA): A1_FILIAL} da aba dClientesBap da TABELA_BAP."""
    saida = {}
    try:
        wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    except Exception:                                   # noqa: BLE001
        return saida
    try:
        if "dClientesBap" not in wb.sheetnames:
            return saida
        it = wb["dClientesBap"].iter_rows(values_only=True)
        cab = [texto(c) for c in next(it, [])]
        if not {"A1_FILIAL", "A1_COD", "A1_LOJA"} <= set(cab):
            return saida
        i_f, i_c, i_l = (cab.index("A1_FILIAL"), cab.index("A1_COD"),
                         cab.index("A1_LOJA"))
        for r in it:
            if r and len(r) > max(i_f, i_c, i_l) and r[i_c]:
                saida[(re.sub(r"\D", "", texto(r[i_c])).zfill(6),
                       re.sub(r"\D", "", texto(r[i_l])).zfill(2))] = \
                    texto(r[i_f])
    finally:
        wb.close()
    return saida


def texto_coordenada(v) -> str:
    """(23/10, Alexandre) a coordenada como no modelo: texto com ponto, ate
    7 casas, sem zero sobrando no fim ("-3.010709", "-60.0082203")."""
    t = f"{float(v):.7f}".rstrip("0")
    return t + "0" if t.endswith(".") else t


def coordenada_protheus(lat, lon) -> tuple:
    """(14/10) LATITUDE e LONGITUDE para o .json da base de clientes e da
    rota: texto com ponto (23/10: ate 7 casas, "-3.010709" /
    "-60.0082203"); vazio quando o cliente ainda nao foi localizado (o BAP
    nao manda ponto inventado)."""
    try:
        la, lo = float(str(lat).replace(",", ".")), float(
            str(lon).replace(",", "."))
    except (TypeError, ValueError):
        return "", ""
    if not (-34.0 <= la <= 5.5 and -74.5 <= lo <= -28.0) or \
            (abs(la) < 1e-6 and abs(lo) < 1e-6):
        return "", ""
    return texto_coordenada(la), texto_coordenada(lo)


def base_protheus(cfg: dict, clientes: list, filiais=None,
                  na_rota=None) -> list:
    """
    A BASE DE CLIENTES para o Protheus: o vendedor de cada cliente como a
    roteirizacao do Planner deixou (zona + segmento, ou a excecao do
    analitico) e o supervisor dele. (15/10) Cliente sem vendedor, de
    cadeira vaga/provisoria ou inativado no Planner sai com o VENDEDOR e o
    SUPERVISOR PADRAO (aba Parametros, 000000/000037). (20/10) TODOS vao
    ATIVO - quem ve o cliente e o vendedor atrelado. A1_FILIAL vem da
    dClientesBap; quem nao esta la leva a filial mais comum.
    """
    filiais = filiais or {}
    padrao = Counter(filiais.values()).most_common(1)
    padrao = padrao[0][0] if padrao else ""
    zonas = {z["id"]: z for z in cfg.get("zonas") or []}
    saida = []
    v_padrao = vendedor_padrao(cfg)
    s_padrao = supervisor_padrao(cfg)
    for c in clientes:
        vend = texto(vendedor_do_cliente(cfg, c, zonas))
        # (15/10, Alexandre) quem NAO entra no Planner - sem vendedor,
        # cadeira VAGA/provisoria (o "1001") ou inativado na aba Base
        # cliente - vai com o VENDEDOR PADRAO (antes ficava de fora);
        # (20/10) ATIVO como todos
        fora = (not vend or not re.fullmatch(r"\d{6}", vend)
                or pessoa_por_codigo(cfg, vend).get("provisorio")
                or cliente_inativo(cfg, c))
        if fora:
            vend = v_padrao
        cod = re.sub(r"\D", "", texto(c["COD_CLIENTE"])).zfill(6)
        loja = re.sub(r"\D", "", texto(c["LOJA"])).zfill(2)
        sup = {} if fora else chefe_de(cfg, vend)
        saida.append({
            "A1_FILIAL": filiais.get((cod, loja), padrao),
            "A1_COD": cod, "A1_LOJA": loja,
            "A1_VEND": _codusur_protheus(vend),
            "A1_NOME": texto(c.get("NOME_CLIENTE")),
            "A1_NREDUZ": texto(c.get("NOME_FANTASIA")),
            "SUPERVISOR": s_padrao if fora else (
                _codusur_protheus(sup.get("cod_protheus", ""))
                if sup.get("cargo") == "SUPERVISOR" else ""),
            # (10/11, Alexandre) o INATIVO do Protheus vai INATIVO
            # [SUPOSICAO]; o resto continua ATIVO (regra de 20/10)
            "STATUS": ("INATIVO" if inativo_no_protheus(c)
                       else status_no_json(fora)),
            # (14/10) o ponto do cliente (BASE_CLIENTE / COORDENADAS_CLIENTES)
            "LATITUDE": coordenada_protheus(c.get("LATITUDE"),
                                            c.get("LONGITUDE"))[0],
            "LONGITUDE": coordenada_protheus(c.get("LATITUDE"),
                                             c.get("LONGITUDE"))[1],
        })
    saida.sort(key=lambda x: (x["A1_VEND"], x["A1_COD"], x["A1_LOJA"]))
    return saida


def gravar_recorte(cfg: dict, clientes: list, caminho, chaves=None,
                   titulo="", visao="VISITA", dias=None, semanas=None) -> list:
    """
    Grava a rota de um PEDACO da carteira - o que esta na tela do
    analitico. Duas visoes:
        VISITA  - uma linha por visita (o cliente repete no mes)
        CLIENTE - uma linha por cliente, com os dias e as semanas dele
    dias/semanas filtram a agenda (so valem na visao VISITA).
    """
    linhas = _completar_planner(cfg, gerar_rota(cfg, clientes), clientes)
    if chaves is not None:
        alvo = set(chaves)
        linhas = [r for r in linhas if r["CHAVE_CLIENTE"] in alvo]
    if dias:
        linhas = [r for r in linhas if r["DIA_DO_MES"] in set(dias)]
    if semanas:
        linhas = [r for r in linhas if r["SEMANA"] in set(semanas)]
    colunas = COLUNAS_PLANNER
    if norm(visao).startswith("CLIENTE"):
        linhas = resumir_por_cliente(linhas)
        colunas = COLUNAS_CLIENTE
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "ROTA"
    _folha_planner(ws, linhas, colunas)

    # uma aba dizendo de onde saiu este recorte
    wr = wb.create_sheet("FILTRO")
    _cabecalho(wr, ["O QUE", "VALOR"], [28, 70])
    mes = f"{MESES_PT[int(cfg['mes'][5:7])]}/{cfg['mes'][:4]}"
    for a, b in (("Recorte", titulo or "todos"),
                 ("Visao", "uma linha por cliente"
                  if norm(visao).startswith("CLIENTE")
                  else "uma linha por visita"),
                 ("Dias filtrados", ", ".join(str(d) for d in sorted(dias))
                  if dias else "todos"),
                 ("Semanas filtradas", ", ".join(sorted(semanas))
                  if semanas else "todas"),
                 ("Mes da rota", mes),
                 ("Dias uteis", dias_uteis(cfg["mes"], cfg.get("feriados") or [])),
                 ("Clientes", len({r["CHAVE_CLIENTE"] for r in linhas})),
                 ("Visitas", len(linhas)),
                 ("Gerado em", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))):
        wr.append([a, b])
    for l in range(2, wr.max_row + 1):
        for c in (1, 2):
            wr.cell(l, c).font = Font(size=9)
            wr.cell(l, c).border = BORDA
    wb.save(caminho)
    wb.close()
    return linhas


def gravar_planner(cfg: dict, clientes: list, caminho) -> tuple:
    """
    Gera a rota do mes e grava o PLANNER: uma linha por visita, com o dia,
    a semana e o mes da visita, e o codigo do vendedor e do supervisor em
    numero (e nao em texto com zeros a esquerda).
    """
    linhas = _completar_planner(cfg, gerar_rota(cfg, clientes), clientes)
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "PLANNER"
    _folha_planner(ws, linhas)

    # uma aba de conferencia, para saber o que entrou
    wr = wb.create_sheet("RESUMO")
    resumo = indicadores(cfg, clientes)
    _cabecalho(wr, ["COD_ZONA", "ZONA", "COD_VENDEDOR", "VENDEDOR",
                    "SEGMENTOS", "COD_SUPERVISOR", "SUPERVISOR", "CLIENTES",
                    "VISITAS", "VISITAS/DIA", "INTERIOR", "DIAS UTEIS"],
               [11, 30, 13, 28, 30, 14, 26, 10, 10, 12, 9, 11])
    # uma linha por ZONA + VENDEDOR: a zona com dois vendedores (cada um
    # com os seus segmentos) aparece duas vezes
    visitas = Counter((r["COD_ZONA"], r["COD_VENDEDOR"]) for r in linhas)
    clientes_zv = defaultdict(set)
    for r in linhas:
        clientes_zv[(r["COD_ZONA"], r["COD_VENDEDOR"])].add(r["CHAVE_CLIENTE"])
    cap_zona = {z["codigo"]: z["capacidade_dia"] for z in resumo["zona"]}
    for z in sorted(cfg["zonas"], key=lambda x: x.get("codigo") or ""):
        for a in atendimento_da_zona(z):
            cod_v = a["vendedor"]
            try:
                cod = int(cod_v)
            except (TypeError, ValueError):
                cod = None
            chave = (z.get("codigo", ""), cod_v)
            wr.append([z.get("codigo", ""), z["nome"], cod,
                       pessoa_por_codigo(cfg, cod_v).get("nome", ""),
                       rotulo_segmentos(a["segmentos"]),
                       codigo_supervisor(cfg, cod_v), nome_supervisor(cfg, cod_v),
                       len(clientes_zv.get(chave, ())), visitas.get(chave, 0),
                       cap_zona.get(z.get("codigo", ""), 0),
                       "SIM" if vendedor_do_interior(cfg, cod_v) else "NAO",
                       resumo["du"]])
    for l in range(2, wr.max_row + 1):
        for c in range(1, 13):
            wr.cell(l, c).font = Font(size=9)
            wr.cell(l, c).border = BORDA
    if wr.max_row > 1:
        wr.auto_filter.ref = f"A1:L{wr.max_row}"

    wb.calculation.fullCalcOnLoad = True
    wb.save(caminho)
    wb.close()
    return linhas, resumo


# ==========================================================================
# IMPORTAR o PLANNER de volta
# ==========================================================================
def importar_planner(caminho) -> dict:
    """
    Le um PLANNER_BAP e reconstroi tudo: zonas, equipe, a lotacao de cada
    area (UF/cidade/bairro) e a lista de clientes. E o caminho de volta -
    o arquivo que saiu daqui entra de novo e o planner fica no mesmo
    estado, sem depender da TABELA_BAP.
    """
    caminho = Path(caminho)
    wb = load_workbook(caminho, read_only=True, data_only=True)
    aba = "PLANNER" if "PLANNER" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[aba]
    it = ws.iter_rows(values_only=True)
    cab = [texto(c).upper() for c in next(it)]

    def idx(*nomes):
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    col = {
        "cod_zona": idx("COD_ZONA"), "zona": idx("ZONA"),
        "cod_vend": idx("COD_VENDEDOR_PROTHEUS", "COD_VENDEDOR"),
        "max_vend": idx("COD_VENDEDOR_MAXIMA"), "vend": idx("VENDEDOR"),
        "cod_sup": idx("COD_SUPERVISOR_PROTHEUS", "COD_SUPERVISOR"),
        "max_sup": idx("COD_SUPERVISOR_MAXIMA"), "sup": idx("SUPERVISOR"),
        "cod_ger": idx("COD_GERENTE"), "max_ger": idx("COD_GERENTE_MAXIMA"),
        "ger": idx("GERENTE"),
        "cod_cli": idx("COD_CLIENTE"), "loja": idx("LOJA"),
        "cliente": idx("CLIENTE", "NOME_CLIENTE"),
        "fantasia": idx("NOME_FANTASIA"), "uf": idx("UF"),
        "cidade": idx("CIDADE"), "bairro": idx("BAIRRO"),
        "endereco": idx("ENDERECO"), "numero": idx("NUMERO"),
        "contato": idx("CONTATO"), "curva": idx("CURVA", "CURVA_RECEITA"),
        "status": idx("STATUS_CLIENTE"), "limite": idx("LIMITE_DISPONIVEL"),
        "atraso": idx("VALOR_EM_ATRASO"),
        # PLANNER novo traz a MEDIA mensal (FAT_M3M/FAT_M6M); o antigo
        # trazia a SOMA da janela (FAT_JANELA_CURVA/FAT_6M). Os dois sao
        # aceitos - ver o ajuste logo abaixo da leitura.
        "fat3": idx("FAT_M3M", "MEDIA_MENSAL"),
        "fat6": idx("FAT_M6M", "MEDIA_MENSAL_6M"),
        "fat3_ant": idx("FAT_M3M_ANTERIOR", "MEDIA_MENSAL_ANTERIOR"),
        "fat3_soma": idx("FAT_JANELA_CURVA", "FAT_3_MESES", "RECEITA_PERIODO"),
        "fat6_soma": idx("FAT_6M", "RECEITA_6M"),
        "facum": idx("FAT_ACUMULADO"), "ultima": idx("ULTIMA_COMPRA"),
        "ultvend": idx("COD_ULTIMO_VENDEDOR"), "dias": idx("DIAS_SEM_COMPRA"),
        "segmento": idx("SEGMENTO"), "subsegmento": idx("SUBSEGMENTO"),
    }
    if col["cod_cli"] is None:
        wb.close()
        raise ValueError(f"'{caminho.name}' nao parece um PLANNER: nao achei a "
                         f"coluna COD_CLIENTE.")
    # as janelas com que a media do arquivo foi feita (as de fabrica: o
    # PLANNER nao guarda os parametros da aba 6)
    meses_curva = MESES_JANELA
    meses_seis = 6

    def pega(r, chave, padrao=""):
        i = col.get(chave)
        return r[i] if i is not None and i < len(r) else padrao

    zonas, equipe, areas, clientes = {}, {}, {}, {}
    voto_area = defaultdict(Counter)      # bairro -> qual zona ele e
    voto_vend = defaultdict(Counter)      # zona   -> qual o vendedor dela
    voto_seg = defaultdict(Counter)       # (zona, segmento) -> vendedor
    linha_do_cliente = {}                 # o que cada cliente trouxe
    for r in it:
        cod_cli = texto(pega(r, "cod_cli"))
        if not cod_cli:
            continue
        uf = norm(pega(r, "uf"))
        cidade = norm(pega(r, "cidade"))
        bairro = norm(pega(r, "bairro")) or "(SEM BAIRRO)"
        chave_area = chave_de_area(uf, cidade, bairro)

        cod_zona = texto(pega(r, "cod_zona"))
        nome_zona = texto(pega(r, "zona"))
        if cod_zona:
            z = zonas.setdefault(cod_zona, {
                "id": cod_zona, "codigo": cod_zona,
                "nome": nome_zona or cod_zona, "uf": uf, "vendedor": "",
                "visitas_por_dia": 0, "frequencia": 0})
            # a zona do bairro e a que aparece na MAIORIA dos clientes dele;
            # quem fugir vira excecao la embaixo
            voto_area[chave_area][cod_zona] += 1

        # o codigo do vendedor volta exatamente como foi cadastrado: nada de
        # zeros a esquerda, senao "400" volta "000400" e o vinculo se perde
        # a equipe inteira volta do arquivo: gerente, supervisor e vendedor,
        # cada um com o codigo Protheus e o Maxima como foram digitados
        cod_ger = texto(pega(r, "cod_ger"))
        if cod_ger:
            equipe.setdefault(cod_ger, {
                "cod_protheus": cod_ger, "cod_maxima": texto(pega(r, "max_ger")),
                "nome": texto(pega(r, "ger")) or f"({cod_ger})",
                "cargo": "GERENTE", "responde_a": ""})
        cod_sup = texto(pega(r, "cod_sup"))
        if cod_sup:
            reg = equipe.setdefault(cod_sup, {
                "cod_protheus": cod_sup, "cod_maxima": texto(pega(r, "max_sup")),
                "nome": texto(pega(r, "sup")) or f"({cod_sup})",
                "cargo": "SUPERVISOR", "responde_a": ""})
            if cod_ger and not reg["responde_a"]:
                reg["responde_a"] = cod_ger
        cod_vend = texto(pega(r, "cod_vend"))
        if cod_vend:
            reg = equipe.setdefault(cod_vend, {
                "cod_protheus": cod_vend, "cod_maxima": texto(pega(r, "max_vend")),
                "nome": texto(pega(r, "vend")) or f"({cod_vend})",
                "cargo": "VENDEDOR", "responde_a": ""})
            if cod_sup and not reg["responde_a"]:
                reg["responde_a"] = cod_sup
            if cod_zona:
                voto_vend[cod_zona][cod_vend] += 1
                seg_linha = texto(pega(r, "segmento")).upper()
                if seg_linha:
                    voto_seg[(cod_zona, seg_linha)][cod_vend] += 1

        loja = texto(pega(r, "loja"))
        chave_cli = f"{cod_cli.zfill(6)}-{loja or '00'}"
        linha_do_cliente.setdefault(chave_cli,
                                    (chave_area, cod_zona, cod_vend))
        if chave_cli in clientes:
            continue
        ultima = data_de(pega(r, "ultima", None))
        clientes[chave_cli] = {
            "CHAVE_CLIENTE": chave_cli, "COD_CLIENTE": cod_cli.zfill(6),
            "LOJA": loja, "NOME_CLIENTE": texto(pega(r, "cliente")),
            "NOME_FANTASIA": texto(pega(r, "fantasia")),
            "UF": uf, "CIDADE": cidade, "BAIRRO": bairro,
            "ENDERECO": texto(pega(r, "endereco")),
            "NUMERO": texto(pega(r, "numero")),
            "CONTATO": texto(pega(r, "contato")),
            "LIMITE_DISPONIVEL": numero(pega(r, "limite", 0)),
            "LIMITE_APROVADO": numero(pega(r, "limite", 0)),
            "VALOR_EM_ATRASO": numero(pega(r, "atraso", 0)),
            "DIAS_ATRASO": 0,
            "CURVA_RECEITA": (texto(pega(r, "curva")) or "Z")[-1].upper(),
            # A rota so precisa da MEDIA (e ela que da a curva). Quando o
            # PLANNER e novo, a media vem pronta e a soma e reconstruida
            # multiplicando pela janela; quando e antigo, so ha a soma e a
            # media sai dela. Nos dois casos o cliente entra igual.
            "RECEITA_PERIODO": (numero(pega(r, "fat3", 0)) * meses_curva
                                if col.get("fat3") is not None
                                else numero(pega(r, "fat3_soma", 0))),
            "RECEITA_6M": (numero(pega(r, "fat6", 0)) * meses_seis
                           if col.get("fat6") is not None
                           else numero(pega(r, "fat6_soma", 0))),
            "MEDIA_MENSAL": 0.0,
            "MEDIA_MENSAL_6M": 0.0,
            "RECEITA_PERIODO_ANTERIOR": (
                numero(pega(r, "fat3_ant", 0)) * meses_curva),
            "MEDIA_MENSAL_ANTERIOR": 0.0,
            "RECEITA_ACUMULADA": numero(pega(r, "facum", 0)),
            "STATUS_CLIENTE": (texto(pega(r, "status")) or "NUNCA COMPROU").upper(),
            "DIAS_SEM_COMPRA": (int(numero(pega(r, "dias", 0))) or None)
            if col.get("dias") is not None else None,
            "ULTIMA_COMPRA": ultima,
            "COD_ULTIMO_VENDEDOR": texto(pega(r, "ultvend")),
            "SEGMENTO": texto(pega(r, "segmento")).upper(),
            "SUBSEGMENTO": texto(pega(r, "subsegmento")).upper(),
            "AREA": chave_area,
            "AREA_ROTULO": f"{uf} / {cidade} / {bairro}",
        }
    wb.close()

    # cada bairro fica com a zona que a maioria dos clientes dele tem, e
    # cada zona com o vendedor que a maioria das linhas dela tem
    for chave_area, votos in voto_area.items():
        areas[chave_area] = votos.most_common(1)[0][0]
    for cod_zona, votos in voto_vend.items():
        zonas[cod_zona]["vendedor"] = votos.most_common(1)[0][0]
    # o ATENDIMENTO volta pelo segmento: em cada zona, cada segmento fica
    # com o vendedor que mais o atendeu. Vendedor unico = TODOS.
    for cod_zona, z in zonas.items():
        dono = {}
        for (zid, seg), votos in voto_seg.items():
            if zid == cod_zona:
                dono[seg] = votos.most_common(1)[0][0]
        donos = sorted(set(dono.values()))
        if len(donos) <= 1:
            z["atendimento"] = ([{"vendedor": z["vendedor"], "segmentos": []}]
                                if z.get("vendedor") else [])
        else:
            titular = z["vendedor"]
            z["atendimento"] = (
                [{"vendedor": titular, "segmentos": []}]
                + [{"vendedor": v, "segmentos": sorted(
                    s for s, d in dono.items() if d == v)}
                   for v in donos if v != titular])
        _sincronizar_titular(z)

    # quem fugiu da maioria volta como EXCECAO, do jeito que estava
    excecoes = {}
    for chave_cli, (chave_area, cod_zona, cod_vend) in linha_do_cliente.items():
        reg = {}
        if cod_zona and areas.get(chave_area) != cod_zona:
            reg["zona"] = cod_zona
        zona_final = reg.get("zona") or areas.get(chave_area) or ""
        zf = zonas.get(zona_final)
        da_zona = (vendedor_da_zona_para(zf, clientes.get(chave_cli, {}).get(
            "SEGMENTO", "")) if zf else "")
        if cod_vend and cod_vend != da_zona:
            reg["vendedor"] = cod_vend
        if reg:
            excecoes[chave_cli] = reg

    # dias sem compra: se o PLANNER nao trouxe, calcula pela ultima compra
    ultimas = [c["ULTIMA_COMPRA"] for c in clientes.values() if c["ULTIMA_COMPRA"]]
    referencia = max(ultimas) if ultimas else dt.date.today()
    for c in clientes.values():
        if c["DIAS_SEM_COMPRA"] is None and c["ULTIMA_COMPRA"]:
            c["DIAS_SEM_COMPRA"] = (referencia - c["ULTIMA_COMPRA"]).days

    ordem_cargo = {"GERENTE": 0, "SUPERVISOR": 1, "VENDEDOR": 2}
    pessoas = [{"cod_protheus": p["cod_protheus"],
                "cod_maxima": p["cod_maxima"], "nome": p["nome"],
                "cargo": p["cargo"], "uf_base": "", "cidade_base": "",
                "responde_a": p["responde_a"], "ativo": True,
                "provisorio": False}
               for p in sorted(equipe.values(),
                               key=lambda x: (ordem_cargo.get(x["cargo"], 9),
                                              x["nome"]))]

    return {
        "zonas": sorted(zonas.values(), key=lambda z: z["codigo"]),
        "pessoas": pessoas,
        "areas": areas,
        "excecoes": excecoes,
        "clientes": sorted(clientes.values(),
                           key=lambda c: (c["UF"], c["CIDADE"], c["BAIRRO"],
                                          c["NOME_CLIENTE"])),
        "arquivo": str(caminho),
    }


def importar_rota(caminho, cfg: dict, clientes: list) -> dict:
    """
    Le de volta um arquivo de rota exportado pelo analitico (EXPORTAR
    ROTA), nas duas visoes, e transforma o que estiver la em EXCECOES:
    a zona, o vendedor, a semana e o dia de cada cliente passam a ser os
    do arquivo.

    E o caminho de volta do "exporta, mexe no Excel, devolve": o gerente
    manda a rota para o supervisor, ele acerta a semana de cada cidade na
    planilha e sobe o arquivo aqui.

    Devolve um resumo do que mudou - nada e gravado sem o cfg.
    """
    caminho = Path(caminho)
    wb = load_workbook(caminho, read_only=True, data_only=True)
    aba = "ROTA" if "ROTA" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[aba]
    it = ws.iter_rows(values_only=True)
    cab = [texto(c).upper() for c in next(it)]

    def idx(*nomes):
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    col = {
        "cod_cli": idx("COD_CLIENTE"), "loja": idx("LOJA"),
        "cod_zona": idx("COD_ZONA"),
        "cod_vend": idx("COD_VENDEDOR_PROTHEUS", "COD_VENDEDOR"),
        "semana": idx("SEMANA_VISITA", "SEMANAS_DE_VISITA", "SEMANA"),
        "dia": idx("DIA_VISITA", "DIAS_DE_VISITA", "DIA"),
    }
    if col["cod_cli"] is None:
        wb.close()
        raise ValueError(f"'{caminho.name}' nao parece um arquivo de rota: "
                         f"nao achei a coluna COD_CLIENTE.")

    por_codigo = {z.get("codigo"): z["id"] for z in cfg["zonas"]}
    pessoas = {p["cod_protheus"] for p in cfg.get("pessoas") or []}
    na_base = {c["CHAVE_CLIENTE"] for c in clientes}

    resumo = {"linhas": 0, "clientes": 0, "zona": 0, "vendedor": 0,
              "semana": 0, "dia": 0, "fora_da_base": [], "zona_nova": set(),
              "vendedor_novo": set(), "arquivo": str(caminho)}
    mudancas = {}
    for r in it:
        cod = texto(r[col["cod_cli"]] if col["cod_cli"] < len(r) else "")
        if not cod:
            continue
        resumo["linhas"] += 1
        loja = texto(r[col["loja"]]) if col["loja"] is not None else ""
        chave = f"{cod.zfill(6)}-{loja or '00'}"
        if chave not in na_base:
            if len(resumo["fora_da_base"]) < 20:
                resumo["fora_da_base"].append(chave)
            continue
        reg = mudancas.setdefault(chave, {})
        if col["cod_zona"] is not None:
            cz = texto(r[col["cod_zona"]])
            if cz and cz in por_codigo:
                reg["zona"] = por_codigo[cz]
            elif cz:
                resumo["zona_nova"].add(cz)
        if col["cod_vend"] is not None:
            cv = texto(r[col["cod_vend"]])
            if cv and cv in pessoas:
                reg["vendedor"] = cv
            elif cv:
                resumo["vendedor_novo"].add(cv)
        if col["semana"] is not None:
            sem = texto(r[col["semana"]]).replace("Semana", "").strip()
            sem = sem.split(",")[0].strip()
            if sem.isdigit():
                reg["semana"] = int(sem)
        if col["dia"] is not None:
            dia = texto(r[col["dia"]]).split(",")[0].strip()
            if dia.isdigit() and 1 <= int(dia) <= 31:
                reg["dia"] = int(dia)
    wb.close()

    # so vira excecao o que REALMENTE muda o que o programa faria sozinho
    zonas = {z["id"]: z for z in cfg["zonas"]}
    agenda = {}
    for r in gerar_rota(cfg, clientes):
        agenda.setdefault(r["CHAVE_CLIENTE"], r)
    porchave = {c["CHAVE_CLIENTE"]: c for c in clientes}
    for chave, reg in mudancas.items():
        c = porchave[chave]
        atual = agenda.get(chave)
        novo = {}
        if reg.get("zona") and reg["zona"] != zona_do_cliente(cfg, c):
            novo["zona"] = reg["zona"]
            resumo["zona"] += 1
        if (reg.get("vendedor")
                and reg["vendedor"] != vendedor_do_cliente(cfg, c, zonas)):
            novo["vendedor"] = reg["vendedor"]
            resumo["vendedor"] += 1
        if reg.get("dia") and (not atual or reg["dia"] != atual["DIA_DO_MES"]):
            novo["dia"] = reg["dia"]
            resumo["dia"] += 1
        elif reg.get("semana"):
            de_agora = int(texto(atual["SEMANA"]).split()[-1]) if atual else 0
            if reg["semana"] != de_agora:
                novo["semana"] = reg["semana"]
                resumo["semana"] += 1
        if novo:
            marcar_excecao(cfg, [chave], **{k: v for k, v in novo.items()
                                            if k in ("zona", "vendedor")})
            if "semana" in novo or "dia" in novo:
                reg_ex = cfg.setdefault("excecoes", {}).setdefault(chave, {})
                reg_ex.update({k: v for k, v in novo.items()
                               if k in ("semana", "dia")})
            resumo["clientes"] += 1
    resumo["zona_nova"] = sorted(resumo["zona_nova"])
    resumo["vendedor_novo"] = sorted(resumo["vendedor_novo"])
    return resumo


# ==========================================================================
# a mecanica da rota, em portugues - o mesmo texto aparece na aba PARAMETROS
# ==========================================================================
MECANICA_DA_ROTA = [
    ('1. Quem entra na rota',
     'Todo cliente que tem ZONA e cuja zona tem VENDEDOR. Cliente sem '
     'zona, ou de zona sem vendedor, fica de fora e aparece no '
     'gerencial para voce resolver. Ninguem e descartado em silencio.'),
    ('2. Quantas visitas cada cliente recebe - PELA CURVA, no automatico',
     'Nao ha chave para ligar ou desligar: quem manda e a curva de '
     'receita (os cortes em R$ estao na aba 6).\n'
     '    curva S ... 7 DIAS  - visita semanal, uma em cada semana do '
     'mes\n'
     '    curva A ... 7 DIAS  - visita semanal, igual ao S\n'
     '    curva B ... 14 DIAS - quinzenal, duas no mes\n'
     '    curva C ... 30 DIAS - mensal, uma no mes\n'
     '    curva Z ... 60 DIAS - UMA visita, e so se sobrar espaco\n'
     "E a MESMA tabela que vai no campo 'periodicidade' do arquivo do "
     'Protheus (aba 6), entao o que esta na rota e o que o Protheus '
     'le nunca discordam.\n'
     'Quem fatura mais e visto mais vezes, sem ninguem precisar '
     'escolher. EXCECAO: o TOP 30 e o cliente COM LIMITE do vendedor '
     'da capital sao SEMANAIS, seja qual for a curva (item 17). Num '
     'mes de 5 semanas o curva S recebe 5 visitas; num de 4, recebe 4.'),
    ('3. A agenda do mes - dias uteis + o ULTIMO SABADO',
     'Os dias uteis do mes escolhido na aba 6, menos os feriados, '
     'MAIS o ULTIMO SABADO DO MES. Esse sabado e trabalhado por TODOS '
     'os vendedores, sempre, todo mes, com o mesmo teto de visitas '
     'por dia dos dias uteis (por exemplo, 12 clientes). Nao ha chave '
     'para ligar ou desligar: e regra fixa da BAP. O PRIMEIRO sabado '
     'tem outro papel - e o deposito do excedente (item 6). Os '
     'sabados do meio ficam livres.'),
    ('4. O mes do vendedor e repartido entre as zonas dele',
     'Quem atende mais de uma zona nao mistura: cada zona fica com um '
     'PEDACO SEGUIDO do mes, na proporcao da carteira, e as zonas sao '
     'visitadas na ordem geografica (a zona mais proxima da '
     'anterior). Assim ele fica dias seguidos em Manaus e depois dias '
     'seguidos em Boa Vista, e nao um dia em cada. O vendedor da '
     'capital (item 17) roda as zonas dele JUNTAS, o mes inteiro: a '
     'visita semanal precisa de todas as semanas.'),
    ('5. Quem cabe na semana - a fila e a curva',
     'Cada dia util recebe exatamente o TETO de visitas por dia da '
     'aba 6 (por exemplo, 12). A fila para ocupar esses lugares: '
     'primeiro a VISITA SEMANAL (item 17), depois o TOP 30 e o '
     'cliente COM LIMITE de quem viaja, e entao a curva - os S, '
     'depois os A, os B e os C - com as visitas que a curva pede. O '
     'espaco que sobrar e preenchido com os clientes de curva Z, um '
     'por um, na ordem geografica. Dentro da mesma curva, quem fatura '
     'mais entra primeiro.'),
    ('6. O PRIMEIRO SABADO E O DEPOSITO - sem limite',
     "Com 'colocar os clientes excedentes no sabado' em SIM: tudo o "
     'que nao coube nos dias uteis (na pratica, o curva Z que ficou '
     'de fora) e visitado UMA vez, no PRIMEIRO SABADO DO MES. Nao ha '
     'teto nesse dia - ele e a valvula de escape que garante que '
     'NENHUM cliente fica fora da rota. Nao confunda com o ULTIMO '
     'sabado do item 3, que e dia de rota normal, com teto. Os '
     'sabados do meio ficam livres.\n'
     'A ZONA marcada "So no sabado do excedente" (aba Zonas) vai inteira '
     'para este sabado: os clientes continuam ATIVOS na carteira do '
     'vendedor, mas nao ocupam dia de rota (ex.: Roraima do Thiago, que '
     'fica 100% em Manaus).'),
    ('7. A ordem dentro da zona: cidade vizinha depois de cidade vizinha',
     'As cidades sao encadeadas pelo vizinho mais proximo, partindo '
     'da cidade base do vendedor (aba 2). A distancia sai da '
     'coordenada do municipio (tabela do IBGE que ja vem no '
     'programa). Cidade sem coordenada entra no fim, sem sumir da '
     'rota.'),
    ('8. Dentro da cidade: o CAMINHO MAIS CURTO entre os clientes',
     'Cada cliente e um ponto no mapa: a LATITUDE e a LONGITUDE do '
     'endereco (colunas da BASE_CLIENTE, OpenStreetMap; atualizam '
     'sozinhas quando o cliente e novo ou muda de endereco - e o '
     'botao Atualizar coordenadas da aba Base cliente). Sem o '
     'endereco localizado, vale o centro do bairro; sem ele, o da '
     'cidade. A ordem e a do vizinho mais proximo, melhorada para nao '
     'cruzar o proprio caminho (2-opt); a cidade seguinte comeca pelo '
     'cliente mais perto de onde a anterior terminou. No mesmo ponto '
     'vem primeiro a curva melhor e quem esta comprando.'),
    ('9. A cidade e fechada de uma vez - e o VENDEDOR DO INTERIOR fecha o DIA',
     'Como os dias sao preenchidos NA ORDEM da lista acima, os '
     'clientes de uma cidade caem em dias seguidos. Nao existe ir a '
     'Castanhal na segunda, Belem na terca e Castanhal de novo na '
     'quarta. A cidade so volta quando o cliente tem visita repetida '
     '(item 10).\n'
     'O vendedor marcado como DO INTERIOR na aba 2 vai mais longe: a '
     'rota dele e montada POR CIDADE - cada dia tem UMA cidade so, '
     'ate o teto de visitas por dia. Cidade grande ocupa quantos dias '
     'precisar; cidade pequena fecha num dia e ele segue para a '
     'proxima no dia seguinte. E a diferenca entre rodar bairro a '
     'bairro dentro de Manaus e viajar para uma cidade e passar o dia '
     'la.\n'
     'O calendario da aba ROTA POR CIDADE manda mais que isto: o '
     'vendedor com calendario roda as cidades nos dias em que voce as '
     'pos.'),
    ('10. Onde caem a 2a, a 3a e a 4a visita',
     'Sempre em OUTRO dia da MESMA cidade - a visita repetida nunca '
     'obriga a uma viagem a mais. O dia escolhido e o da SEMANA que a '
     'curva pede (de 1 em 1 semana para o curva S e A, de 2 em 2 para '
     'o B) e, entre os possiveis, o mais VAZIO. O teto de visitas por '
     'dia vale para todas elas. Se o vendedor passa poucos dias '
     'naquela cidade, o cliente recebe menos visitas do que a curva '
     'pediria - nao daria para fazer mesmo. O mesmo cliente nunca e '
     'visitado duas vezes no mesmo dia.'),
    ('11. Quando a carteira nao cabe',
     'Sem a regra do sabado, a rota sai assim mesmo com os dias acima '
     'do teto, divididos por igual - nenhum cliente e descartado - e '
     'a linha aparece em VERMELHO no gerencial, dizendo de quantos '
     'dias o vendedor precisaria. Com a regra do sabado ligada isso '
     'nao acontece: o excedente vai todo para o primeiro sabado.'),
    ('12. O que voce marcou a mao manda mais que a conta',
     'Zona, vendedor, semana e dia trocados no ANALITICO ROTA valem '
     'por cima de tudo o que esta acima - voce viu alguma coisa que a '
     'conta nao ve. Essas linhas ficam em amarelo no analitico e as '
     'trocas viajam no PLANNER.'),
    ('13. A ordem do dia',
     'Dentro do dia as visitas sao numeradas de 1 a N pelo CAMINHO '
     'MAIS CURTO entre os clientes do dia, saindo do lado da base do '
     'vendedor (antes era o nome do bairro, e ficava em ordem '
     'alfabetica). Se o vendedor atende duas zonas no mesmo dia, a '
     'numeracao corre sem reiniciar.'),
    ('14. O dia ate o teto, 1 vez por semana e a SEXTA de prospeccao',
     'O dia util e completado ate o TETO de visitas por dia repetindo '
     'os clientes da cidade em que o vendedor ja esta naquele dia '
     '(primeiro quem teve menos visitas no mes, depois quem esta ha '
     'mais tempo sem visita, a curva e o faturamento).\n'
     'O MESMO CLIENTE NUNCA E VISITADO DUAS VEZES NA MESMA SEMANA: a '
     'visita a mais vai para outra semana ou sai.\n'
     "A SEXTA-FEIRA: o teto dela e o 'Visitas na sexta' da aba de "
     "parametros. (03/11, Alexandre) Desde NOV/26 a sexta e dia NORMAL, "
     '12 clientes (antes: prospeccao, 6).'),
    ('15. Cidade fora da rota',
     'Na aba Rota por cidade, CLICAR NA CIDADE do calendario (fixa ou '
     'automatica) tira a cidade da rota do vendedor NO MES: os '
     'clientes dela ficam sem visita (so continua quem foi trazido a '
     'mao para um dia). A cidade fica cinza no fim da lista; clicar '
     'nela ou arrasta-la para um dia devolve. Nao passa para o mes '
     'seguinte. As cidades do calendario aparecem sempre em ordem '
     'alfabetica.\n'
     'No CALENDARIO montado a mao tambem vale o TETO (12; sexta 12 '
     'desde NOV/26): '
     'quem nao cabe nos dias da cidade sai pela curva e pelo '
     'faturamento e vai para o sabado do deposito (excedente em SIM) '
     'ou fica sem visita.'),
    ('16. A CIDADE BASE nos primeiros dias uteis',
     "Nos 10 PRIMEIROS DIAS UTEIS do mes (parametro 'Dias uteis so na "
     "cidade base') o vendedor so roda a CIDADE BASE do cadastro (aba "
     "2) e as cidades ate 50 km dela (parametro 'Raio da cidade "
     "base'; a conta e em linha reta). O resto da carteira vai do 11o "
     'dia util em diante.\n'
     'Vale para a rota automatica e para o calendario da Rota por '
     'cidade: nesses dias a cidade de fora sai (o log diz qual) e a '
     'cidade base entra, e a aba nao deixa arrastar outra cidade para '
     "eles (o dia aparece com 'base'). A unica excecao e a AGENDA "
     'IMPORTADA (Importar agenda de cidade): os dias que vieram no '
     'arquivo ficam como foram importados. Faltou cliente na regiao '
     'da base, o dia fica abaixo do teto (prospeccao na base) - nao '
     'inventa viagem.'),
    ('17. VISITA SEMANAL: o TOP 30 e o cliente COM LIMITE',
     'Os TOP 30 clientes de cada vendedor (maior faturamento dos '
     'ultimos 6 meses, so quem faturou - o mesmo TOP 30 da parcial e dos '
     'contatos do celular) e todo cliente COM LIMITE de credito '
     '(aprovado ou disponivel) passam na frente de todo mundo.\n'
     'Para o VENDEDOR DA CAPITAL - 80% ou mais da carteira a ate 50 '
     'km da capital da UF dele e nao marcado como do interior - esses '
     'clientes, quando estao a ate 50 km da capital, sao visitados '
     'TODA SEMANA: a rota deles e montada primeiro, semana a semana, '
     'e a carteira comum ocupa o lugar que sobra. O teto do dia '
     'continua valendo; na semana curta (o mes que comeca na quinta) '
     'nem todos cabem.\n'
     'Para o vendedor que viaja (interior, carteira espalhada) eles '
     'nao conseguem ser semanais: entram primeiro na fila e nunca vao '
     'para o sabado do deposito antes de um cliente comum.\n'
     'O PLANNER mostra o motivo em PRIORIDADE_ROTA e VISITA_SEMANAL, '
     'e o arquivo do Protheus leva periodicidade 7 para o semanal.'),
    ('18. REGRAS EM VIGOR DESDE 18/10 - o TETO e 12 por dia, SEXTA 6, INTERIOR 6',
     'O teto do dia e 12 clientes; na sexta (prospeccao), 6 da carteira. '
     'As metas de visita do mes foram feitas com esses numeros. O teto '
     'de 15 (sexta 8), simulado em 18/10 de manha, foi CANCELADO pelo '
     'Alexandre e nao vale.\n'
     'VENDEDOR DO INTERIOR: quando esta numa cidade do interior, a meta '
     'e 6 clientes por dia; vale visita de cliente da base ou cadastro '
     'novo. No dia da CIDADE BASE dele, o teto normal (12). Desde 21/10 '
     'isso vale tambem no recalculo automatico (item 23).\n'
     'CANCELADA: a regra de no minimo um dia por cidade do interior. Os '
     '12 clientes cadastrados por cidade do interior sao so um '
     'INDICADOR da parcial (CLI. P/ CIDADE), nao regra de rota.'),
    ('19. DIAS QUE JA PASSARAM: so com o REALIZADO quando o Alexandre pede',
     'Quando o Alexandre pede para REFAZER o mes, a agenda dos dias que '
     'ja passaram vira o que o vendedor visitou de fato (Espelho de '
     'Rotas da Maxima), completado ate a meta do dia (12, sexta 6, '
     'interior 6 e 12 na cidade base) com a regra normal do Planner para '
     'aquele dia, desde a admissao. Do dia seguinte em diante, a rota '
     'segue as regras, descontando da frequencia o que ja foi visitado. '
     'Em outubro/26 foi refeito assim em 18/10 e de novo em 21/10 '
     '(01 a 21/10), gravado como ROTA FIXA e no arquivo '
     'RELATORIOS\\Roteirizacao\\ROTA_PROTHEUS_2026-10_AJUSTADA_'
     '20261021_2200.json (vale sobre os envios antigos ate 21/10).\n'
     'NO RECALCULO NORMAL (so os alterados ou completo) os dias que ja '
     'passaram NAO sao reescritos: ficam como estavam na rota guardada '
     '(item 24).'),
    ('20. DATA DE ADMISSAO (cadastro, aba 2)',
     'Cada vendedor e supervisor tem a data de admissao. No mes da '
     'admissao a rota comeca no dia dela e a meta da tabela de meses '
     'de casa e proporcional aos dias uteis desde a admissao. Com a '
     'data de admissao o MES DE CASA e automatico (so informativo, nao '
     'se escreve) e vale de OUT/2026 em diante (Replicar equipe '
     'tambem); sem a data, vale o mes de casa escrito.'),
    ('21. Como a rota e medida: ADERENCIA ao Planner',
     'O Farol de Visita mede a rota assim: AGENDADOS = clientes '
     'programados no Planner para o vendedor no dia (a rota exportada '
     'para a Maxima que valia naquele dia; nao a agenda da Maxima, que '
     'junta importacoes antigas); VISITADOS = Espelho da Maxima + '
     'cadastros novos do dia; % ADERENCIA = programados visitados; '
     '% FORA DE ROTA = visitas a quem nao estava programado; % PED. NA '
     'ROTA = pedidos (Farol de Pedidos) em cliente visitado naquele dia.'),
    ('22. BASE DE CLIENTES no .json (Protheus/Maxima)',
     'TODO cliente vai ATIVO no .json da base de clientes. O que decide '
     'se o vendedor ve o cliente e a quem ele esta atrelado (A1_VEND): '
     'o cliente com vendedor no Planner vai com esse vendedor e o '
     'supervisor dele; o cliente sem vendedor (zona/segmento sem '
     'vendedor, cadeira vaga ou provisoria, ou inativado na aba Base '
     'cliente) vai com o VENDEDOR PADRAO e o SUPERVISOR PADRAO da aba '
     'Parametros (000000 e 000037) - ninguem da equipe ve. INATIVO na '
     'aba Base cliente so tira o cliente da rota.'),
    ('23. VENDEDOR DO INTERIOR: 6 por dia no interior, 12 na cidade base',
     '(21/10, Alexandre) O vendedor marcado como do INTERIOR (aba 2) tem '
     'teto de 6 clientes por dia (parametro teto_interior) nos dias em '
     'que o calendario da Rota por cidade (ou a agenda importada) o poe '
     'numa cidade que nao e a cidade base dele; no dia da cidade base, o '
     'teto normal (12; sexta 6). Dia com duas cidades no calendario: '
     'vale a primeira. Sem calendario, o interior segue o teto normal.'),
    ('24. RECALCULAR NAO REESCREVE O PASSADO',
     '(21/10, Alexandre) Em todo recalculo - so os alterados ou PLANNER '
     'COMPLETO - o vendedor refeito fica com os dias de antes de hoje '
     'como estavam na rota guardada (o que foi programado). So de hoje em '
     'diante a rota e nova, e quem ja estava programado na semana nos '
     'dias guardados nao volta na mesma semana. Trocar o passado pelo '
     'realizado + a meta do dia (item 19) e so quando o Alexandre pede.'),
    ('25. META DE VISITA: 12 por dia util desde a admissao',
     '(21/10, Alexandre) A meta de visita do mes (Gerador de Meta, Farol '
     'de Metas, RV e Farol de Visita) e a soma das metas dos dias uteis '
     '(segunda a sexta, sem feriado) desde a data de admissao: 12 '
     'clientes por dia; o VENDEDOR DO INTERIOR tem 6 por dia, e 12 no dia '
     'em que esta na cidade base. A cidade do dia e a da rota guardada '
     '(nos dias refeitos, onde ele visitou). Substitui os 90% das '
     'visitas da rota. A sexta tambem conta 12 [SUPOSICAO]; sabado nao '
     'tem meta.'),
    ('26. CADASTRO EM LOTE NAO E VISITA',
     '(21/10, Alexandre) O cadastro novo do dia conta como visita, menos '
     'os cadastros com data (A1_DTCAD) de um lote lancado no Protheus - '
     'parametro datas_cadastro_lote_fora (hoje: 16/10/2026, 112 '
     'clientes). Eles continuam como cadastro na base e no cadastro com '
     'compra; so nao somam nas visitas (Farol de Visita, Parcial, Farol '
     'de Metas e RV).'),
    ('27. ROTEIRIZACAO POR LUGAR: cidade > bairro > rua > numero',
     '(27/10, Alexandre; vale de NOV/26 em diante) A rota segue a '
     'geolocalizacao e a proximidade em camadas: primeiro a CIDADE, depois '
     'o BAIRRO, depois a RUA (endereco) e por fim o NUMERO. CADA CIDADE E UM '
     'DIA CHEIO: 1 cidade por dia, seja o vendedor da capital ou do '
     'interior. O Planner escolhe quem entra na semana (curva, TOP 30, '
     'limite, cidade base, teto) e remonta a semana: a cidade base primeiro, '
     'depois as cidades ate 50 km, depois as longes (a sexta com teto menor '
     'vai para a cidade que cabe inteira nela). Dentro da cidade, os bairros pelo '
     'caminho mais curto entre os centros, as ruas idem e o numero em ordem. '
     'Regiao longe dentro da mesma cidade (ilha ou distrito, mais de 10 km '
     'do bairro anterior - ex. Mosqueiro em Belem) e dia proprio. DIA '
     'COMPACTO (27/10): bairro a mais de 5 km do centro do dia fecha o dia '
     'e vai para o seguinte, mesmo sem o dia cheio (na capital a cidade e '
     'continua: Marco e Icoaraci nao ficam no mesmo dia). A vaga do '
     'dia e completada com clientes da carteira da mesma cidade a ate 5 km '
     'do centro do dia (os menos visitados no mes primeiro); sem cliente, a '
     'vaga e PROSPECCAO '
     'naquela cidade. Cidade que nao coube na semana vai para a semana '
     'seguinte. Dia com calendario (Rota por cidade ou agenda importada) '
     'fica com as cidades do calendario; so a ordem do dia segue o lugar.'),
    ('28. A ORDEM DO MES: S, A E CLIENTE COM LIMITE PRIMEIRO; SEXTA 12',
     '(03/11, Alexandre; vale de NOV/26 em diante) As primeiras visitas do '
     'mes sao dos clientes curva S, curva A e com limite de credito '
     '(aprovado ou disponivel); depois de todos eles terem a 1a visita, os '
     'dias sao preenchidos com a curva B, depois a C, depois o resto (D, Z) '
     '- sempre na ordem da proximidade (cidade, bairro, rua, numero). A '
     'frequencia continua a da curva (S e A toda semana; o TOP 30 e o '
     'cliente com limite do vendedor da capital, toda semana). A regra da '
     'cidade base continua: nos 10 primeiros dias uteis so a regiao da '
     'base, e dentro de cada grupo a base vem primeiro. Vendedor do '
     'interior (1 cidade por dia): primeiro as cidades com cliente S, A ou '
     'com limite, depois as outras; a cidade nao e partida em duas viagens. '
     'A vaga do dia tambem prefere S, A e limite. A SEXTA E DIA NORMAL: 12 '
     'clientes (parametro Visitas na sexta = 12). Feriados de NOV/26: 02/11 '
     'e 20/11.'),
    ('29. DIA FOCO: SEGUNDA BATERIA, TERCA MOTO; FAYGA E RODRIGO NA BASE '
     'SEG/TER',
     '(03/11, Alexandre; vale de NOV/26 em diante) Vendedor com cidade base '
     'numa capital, em Ananindeua ou em Castanhal: a SEGUNDA e o dia dos '
     'clientes de BATERIA (segmento Distribuidor de baterias ou quem ja '
     'comprou bateria; depois autopecas, autocenter e posto/troca de oleo) '
     'e a TERCA e o dia dos clientes de MOTOPECAS, na cidade base. O dia e '
     'montado antes do resto da semana, no lugar com mais clientes do foco, '
     'compacto (ate 5 km do centro) e com quem ja estava na semana '
     'primeiro; sobrando vaga, entra cliente do foco da carteira que nao '
     'esta na semana; faltando, prospeccao. FAYGA E RODRIGO: segunda e '
     'terca sempre na cidade base (Ananindeua, Castanhal); de quarta em '
     'diante so o interior (as outras cidades da carteira) - para eles nao '
     'vale a regra dos 10 primeiros dias uteis na base.'),
]
