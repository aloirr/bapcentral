# -*- coding: utf-8 -*-
"""
O MOTOR DO GERADOR DE META - a conta, sem tela nenhuma.

DE ONDE VEM O DADO
  Do PLANNER_BAP mais recente (a pasta RELATORIOS). Ele ja tem tudo o que a
  meta precisa: a hierarquia inteira (gerente, supervisor, vendedor, zona,
  UF, cidade, bairro), o cliente, a curva, o faturamento da janela de 3
  meses (FAT_JANELA_CURVA) e UMA LINHA POR VISITA - e por isso que da para
  contar visitas e saber quem caiu no sabado do deposito.

A META NASCE NO CLIENTE - E CADA NIVEL TEM A SUA REGRA
  A meta de cada cliente e calculada pelo historico DELE; dai para cima,
  cada nivel tem uma regra propria - e por isso os niveis nao sao mais a
  simples soma um do outro:

      meta do cliente   = o historico dele, com o PISO do cliente
      meta do bairro    = soma dos clientes do bairro
      meta da cidade    = soma dos bairros
      meta da zona      = soma dos clientes da zona, com o PISO da zona
      meta do vendedor  = o historico DELE, com o PISO do vendedor
      meta do supervisor= soma da meta dos VENDEDORES dele
      meta da UF        = o rateio da META GERAL
      meta do gerente   = o rateio da META GERAL

  E UMA MECANICA SO: nao ha modo de calculo a escolher.
  Toda linha traz tambem "meta_dos_clientes" - a soma pura - para a
  diferenca ficar a vista.

ONDE A META FICA
  Num arquivo so, RELATORIOS/ACOMPANHAMENTO_META_BAP.xlsx: uma aba por
  mes ("202609") e UMA aba ANALITICO com todos os meses, com a coluna
  MES para filtrar. Ver guardar_meta_do_mes().

AS OUTRAS TRES METAS
      META VISITA   = 90% das visitas que o PLANNER marcou para ele no mes
      POSITIVACAO   = 50% dos clientes marcados para visita, TIRANDO os que
                      so tem visita no primeiro sabado (os excedentes)
      POR CATEGORIA = um percentual da meta de faturamento da propria linha
                      (pecas, bateria, lubrificante, pneu)

  Os percentuais de categoria podem ser mudados POR UF ou POR ZONA: mexeu no
  estado, muda tudo daquele estado; mexeu na zona, muda tudo daquela zona.
  A zona manda mais que a UF.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook
try:  # leitura rapida com cache (sem o arquivo: openpyxl)
    from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
except ImportError:
    from openpyxl import load_workbook  # noqa: PLC0415

import familia_nucleo as fam

# --------------------------------------------------------------------------
# parametros
# --------------------------------------------------------------------------
# as janelas com que o PLANNER calcula as medias mensais (as de fabrica
# da aba 5 do Planner) - so servem para converter PLANNER antigo, que
# guardava a soma da janela em vez da media
MESES_M3M = 3
MESES_M6M = 6

CATEGORIAS = [
    # (chave, rotulo, percentual de fabrica)
    ("pecas", "PECAS", 40.0),
    ("bateria", "BATERIA", 25.0),
    ("lubrificante", "LUBRIFICANTE", 30.0),
    ("pneu", "PNEU", 15.0),
]

# ==========================================================================
# COMO A META E CALCULADA
# ==========================================================================
# Dois modos, escolhidos na aba 1:
#
#   "crescimento"  (o padrao)
#       A meta sai do proprio historico de quem recebe: compara-se o M3M
#       ATUAL com o M3M ANTERIOR (os 3 meses de antes) e ve-se se esta
#       crescendo ou caindo. Quem ja cresceu muito ganha um acrescimo
#       menor; quem esta caindo tem de voltar ao patamar de antes e ainda
#       crescer em cima dele.
#
#           cresceu 10% ou mais ..... meta = M3M ATUAL    + 5%
#           cresceu de 5% a 10% ..... meta = M3M ATUAL    + 8%
#           cresceu menos que 5%
#           ou esta caindo .......... meta = M3M ANTERIOR + 10%
#
#       As faixas e os percentuais sao editaveis. Depois vem o PISO: a
#       meta nunca fica abaixo do minimo daquele nivel.
#
#   "rateio"
#       O modo antigo: uma META GERAL e repartida entre os clientes na
#       proporcao do M3M de cada um.
FAIXAS_PADRAO = [
    # (de quanto cresceu, sobre qual base, quanto acrescentar)
    {"cresceu_ate": None, "desde": 10.0, "base": "atual", "acrescimo": 5.0},
    {"cresceu_ate": 10.0, "desde": 5.0, "base": "atual", "acrescimo": 8.0},
    {"cresceu_ate": 5.0, "desde": None, "base": "anterior", "acrescimo": 10.0},
]

# ==========================================================================
# A REMUNERACAO VARIAVEL (RV)
# ==========================================================================
# Cada KPI paga um valor FIXO por FAIXA DE ATINGIMENTO - nao e percentual
# sobre nada. Bateu 97% da meta de faturamento, o vendedor leva os R$ 926
# da faixa de 95 a 99,999%; bateu 100%, pula para R$ 3.120. O salto entre
# as faixas e grande de proposito: e ele que faz a pessoa correr atras do
# ultimo ponto percentual.
#
# A FAIXA E FECHADA DOS DOIS LADOS e elas nao se encostam por acaso: a de
# cima termina em 79,999 e a seguinte comeca em 80,000. Atingimento entre
# 79,999 e 80,000 nao existe na pratica (o calculo tem tres casas), mas
# se existisse cairia na PRIMEIRA que servir, lendo de cima para baixo.
#
# O que entra em cada KPI:
#   fat ........... o ATINGIMENTO do FAT TOTAL - o que a pessoa VENDEU
#                   pelo codigo dela na nota, contra a meta dela. Nao e o
#                   FATURAMENTO CARTEIRA, que e outra leitura e fica ao
#                   lado so para informar.
#   positivacao ... o atingimento da POSITIVACAO
#   visita ........ o atingimento da VISITA
#
# O GERENTE nasce sem faixa nenhuma: a tabela dele ainda nao existe. Sem
# faixa, a RV dele e zero e nenhuma coluna mente - e diferente de ter uma
# faixa que paga zero.
KPIS_DA_RV = [
    # a RV de faturamento paga pela META RH (o modelo de sempre); a
    # comercial e a dos acompanhamentos
    ("fat", "FAT TOTAL", "atingimento_rh"),
    ("positivacao", "POSITIVACAO", "atingimento_positivacao"),
    ("visita", "VISITA", "atingimento_visita"),
]
NIVEIS_DA_RV = [("vendedor", "VENDEDOR"), ("supervisor", "SUPERVISOR"),
                ("gerente", "GERENTE")]
TETO_DA_FAIXA = 999999.0


def _faixa(de: float, ate: float, valor: float) -> dict:
    return {"de": de, "ate": ate, "valor": valor}


FAIXAS_RV_PADRAO = {
    "vendedor": {
        "fat": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 292.0),
            _faixa(90.0, 94.999, 702.0),
            _faixa(95.0, 99.999, 926.0),
            _faixa(100.0, 109.999, 3120.0),
            _faixa(110.0, 119.999, 3861.0),
            _faixa(120.0, TETO_DA_FAIXA, 4680.0),
        ],
        "positivacao": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 390.0),
            _faixa(90.0, 94.999, 702.0),
            _faixa(95.0, 99.999, 741.0),
            _faixa(100.0, 109.999, 780.0),
            _faixa(110.0, 119.999, 858.0),
            _faixa(120.0, TETO_DA_FAIXA, 936.0),
        ],
        "visita": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 0.0),
            _faixa(90.0, 94.999, 1053.0),
            _faixa(95.0, 99.999, 1112.0),
            _faixa(100.0, 109.999, 1170.0),
            _faixa(110.0, 119.999, 1286.0),
            _faixa(120.0, TETO_DA_FAIXA, 1404.0),
        ],
    },
    "supervisor": {
        "fat": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 1125.0),
            _faixa(90.0, 99.999, 2225.0),
            _faixa(100.0, 119.990, 3750.0),
            _faixa(120.0, TETO_DA_FAIXA, 4750.0),
        ],
        "positivacao": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 450.0),
            _faixa(90.0, 99.999, 890.0),
            _faixa(100.0, 119.999, 1100.0),
            _faixa(120.0, TETO_DA_FAIXA, 1900.0),
        ],
        "visita": [
            _faixa(0.0, 79.999, 0.0),
            _faixa(80.0, 89.999, 0.0),
            _faixa(90.0, 99.999, 1335.0),
            _faixa(100.0, 109.999, 1650.0),
            _faixa(110.0, 119.999, 2250.0),
            _faixa(120.0, TETO_DA_FAIXA, 2850.0),
        ],
    },
    # sem tabela ainda - ver o comentario acima
    "gerente": {"fat": [], "positivacao": [], "visita": []},
}


def rv_padrao() -> dict:
    return json.loads(json.dumps(FAIXAS_RV_PADRAO))


def valor_da_rv(faixas, atingimento) -> float:
    """
    Quanto aquele atingimento paga, pela tabela de faixas.

    Le de cima para baixo e para na PRIMEIRA que servir. Sem faixa
    nenhuma devolve 0 - e o caso do gerente, que ainda nao tem tabela.
    Atingimento acima do teto da ultima faixa leva o valor dela: foi
    para isso que o teto nasceu em 999999%.
    """
    if not faixas or atingimento is None:
        return 0.0
    try:
        # (04/11) arredondado a 3 casas, como as faixas (79,999 / 80): 80%
        # exato que a conta de ponto flutuante faz virar 79,99999999 nao
        # cai no buraco entre as faixas. O Excel do RH faz o mesmo
        # (ARRED(%*100;3)), para a formula bater centavo a centavo
        ating = round(float(atingimento), 3)
    except (TypeError, ValueError):
        return 0.0
    for faixa in faixas:
        de = _numero(faixa.get("de"))
        ate = _numero(faixa.get("ate"))
        if de <= ating <= ate:
            return _numero(faixa.get("valor"))
    # passou do teto da ultima: leva a ultima, nao zero
    ultima = faixas[-1]
    if ating > _numero(ultima.get("ate")):
        return _numero(ultima.get("valor"))
    return 0.0


def faixas_da_rv(par: dict, nivel: str, kpi: str) -> list:
    """As faixas de um nivel e KPI, caindo no padrao quando faltar."""
    guardado = ((par or {}).get("rv") or {}).get(nivel)
    if guardado is None:
        guardado = rv_padrao().get(nivel) or {}
    return list(guardado.get(kpi) or [])


def rv_da_linha(par: dict, nivel: str, linha: dict) -> dict:
    """
    {rv_fat, rv_positivacao, rv_visita, rv_total} de uma pessoa.

    Nivel que nao e de pessoa (zona, cidade, bairro, cliente) nao tem RV:
    quem recebe e gente, nao territorio.
    """
    saida = {}
    total = 0.0
    # NIVEL SEM TABELA NENHUMA FICA VAZIO, nao zerado. "R$ 0,00" diz que
    # a pessoa nao bateu nada; vazio diz que ainda nao ha regra para ela.
    # Sao coisas diferentes e o gerente, hoje, e o segundo caso.
    tem = (nivel in {n for n, _ in NIVEIS_DA_RV}
           and any(faixas_da_rv(par, nivel, k) for k, _, _ in KPIS_DA_RV))
    for chave, _rotulo, campo_ating in KPIS_DA_RV:
        ating = linha.get(campo_ating)
        if ating is None and campo_ating == "atingimento_rh":
            ating = linha.get("atingimento")    # linha sem meta RH
        valor = (valor_da_rv(faixas_da_rv(par, nivel, chave), ating)
                 if tem else None)
        saida[f"rv_{chave}"] = valor
        total += valor or 0.0
    saida["rv_total"] = total if tem else None
    return saida


PARAMETROS_PADRAO = {
    "modo": "crescimento",
    "faixas": FAIXAS_PADRAO,
    # o piso de cada nivel: a meta nunca fica abaixo disto
    "piso_cliente": 1000.0,
    # O PISO DO CLIENTE VALE SO PARA QUEM JA COMPROU?
    #   SIM (padrao) ... o piso segura a meta do cliente PEQUENO - que e
    #                    para o que ele serve. Quem nunca comprou nada nas
    #                    duas janelas nao ganha meta de faturamento; ele
    #                    entra pela POSITIVACAO, que e a meta certa para
    #                    quem ainda nao compra.
    #   NAO ............ todo cliente da rota ganha o piso, tenha ou nao
    #                    historico. Na carteira de hoje isso cria mais de
    #                    R$ 1,8 milhao de meta a partir de clientes que
    #                    nunca faturaram - confira se e isso que voce quer.
    "piso_so_com_faturamento": True,
    # a META MINIMA (comercial) de quem ja passou dos meses da tabela
    # abaixo; e a META RH do vendedor nunca passa do teto
    "piso_vendedor": 120000.0,
    "teto_rh_vendedor": 120000.0,
    # A META DE QUEM ESTA CHEGANDO: 1o, 2o, 3o e 4o mes de casa (o mes de
    # casa vem do cadastro do vendedor/supervisor no Planner do mes)
    "meta_mes_de_casa": [60000.0, 80000.0, 100000.0, 120000.0],
    # E-MAILS EM COPIA da parcial DO GERENTE (ate 5): so no e-mail do
    # gerente, nunca no de supervisor ou vendedor
    "emails_copia_gerente": ["fernando.fernandes@grupopmz.com.br",
                             "lucas.noronha@grupopmz.com.br",
                             "daniel.vasconcelos@grupopmz.com.br",
                             "leandro.santos@bapautoparts.com.br",
                             "mayara.santos@bapautoparts.com.br"],
    "piso_zona": 120000.0,
    "meta_geral": 0.0,           # a meta do mes inteiro da BAP
    # o mes da meta, em AAAA-MM. Vazio = o mes do proprio PLANNER.
    "competencia": "",
    "pct_visita": 90.0,          # META VISITA = 90% das visitas do PLANNER
    # (21/10, Alexandre) META VISITA = 12 clientes por DIA UTIL desde a
    # admissao; vendedor do INTERIOR 6, e 12 no dia da cidade base (a
    # cidade do dia vem da rota do Planner). 0 = volta aos pct_visita
    "meta_visita_por_du": 12,
    "meta_visita_interior": 6,
    # (21/10, Alexandre) META DE FATURAMENTO TRAVADA no mes: {"AAAA-MM":
    # {"cod do vendedor": [comercial, RH]}} - o vendedor fica com estes
    # valores mesmo que a admissao / a equipe do mes mude; supervisor,
    # gerente e territorios somam os vendedores (a RH do gerente fica)
    "metas_travadas": {},
    # (26/10, Alexandre) VISITA e POSITIVACAO TRAVADAS no mes: {"AAAA-MM":
    # {"meta_visita": {"cod": valor}, "meta_positivacao": {"cod": valor}}}
    # - a meta nao muda no meio do mes (Planner refeito, regra nova...)
    "metas_travadas_ind": {},
    "pct_positivacao": 50.0,     # POSITIVACAO = 50% dos clientes da rota
    # CADASTRO COM COMPRA: quantos clientes NOVOS cada vendedor tem de
    # cadastrar E fazer comprar dentro do mes. Supervisor e gerente sao a
    # soma da equipe; zona, cidade, bairro e cliente nao tem essa meta -
    # quem prospecta e a pessoa, nao o territorio.
    "meta_cadastro": 12.0,
    "categorias": {c: p for c, _, p in CATEGORIAS},
    # as faixas de remuneracao variavel, por nivel e por KPI
    "rv": FAIXAS_RV_PADRAO,
    # {"AM": {"pecas": 45.0, ...}} - so o que foi mexido fica gravado
    "por_uf": {},
    # {"Z-AM-01": {...}} - manda mais que a UF
    "por_zona": {},
    # {"5980 - BAP LUB": "lubrificante"} - a classificacao dos produtos
    # para o acompanhamento por categoria
    "categoria_por_fornecedor": {},
    # ajustes feitos a mao depois de gerar: {"vendedor|000015": 120000.0}
    "ajustes": {},
    # O PAINEL DE INDICADORES EXECUTIVOS (aba 4): os pesos, as metas
    # digitadas e as despesas. TEM DE ESTAR AQUI: carregar_parametros so
    # traz do arquivo as chaves que existem neste dicionario, entao uma
    # chave que falta aqui e jogada fora toda vez que o programa abre -
    # foi assim que o painel inteiro sumia depois de fechar a janela.
    "executivo": {},
    # a planilha de metas importada (ANO | MES | CIDADE | CATEGORIA |
    # META), pelo mesmo motivo
    "metas_importadas": {},
    # QUEM NAO CONTA NA META DO SUPERVISOR, MES A MES:
    #   {"2026-09": {"vendedor": ["1001"], "zona": ["Z-AM-05"]}}
    # So fica gravado quem esta de FORA. Mes que nao aparece aqui ainda
    # nao foi decidido - ver fora_do_mes().
    "fora_da_meta": {},
    # as colunas da folha de impressao, NA ORDEM que ele escolheu, por
    # fonte: {"ACOMPANHAMENTO": [...], "PAINEL DE META": [...]}
    "folha_colunas": {},
    "folha_colunas_vistas": {},
    # as outras metas escritas a mao (visita, positivacao, cadastro):
    # {campo: {"recorte|chave": valor}} - do mes aberto, como "ajustes"
    "ajustes_ind": {},
    # a META GERAL digitada para o mes sem meta no arquivo: {"2026-10": v}
    "metas_gerais": {},
    # O QUE FOI ESCRITO A MAO, MES A MES: {"2026-09": {"ajustes": {...},
    # "ajustes_ind": {...}}}. "ajustes"/"ajustes_ind" acima sao sempre os
    # do mes aberto (ajustes_competencia) - ver sincronizar_ajustes()
    "ajustes_por_mes": {},
    "ajustes_competencia": "",
}

# os recortes do painel, na mesma ordem do resumo gerencial do PLANNER
RECORTES = ["gerente", "supervisor", "vendedor", "zona", "segmento", "uf",
            "cidade", "bairro", "cliente"]

TITULO_DO_RECORTE = {
    "gerente": "GERENTE", "supervisor": "SUPERVISOR", "vendedor": "VENDEDOR",
    "zona": "ZONA", "segmento": "SEGMENTO", "uf": "UF", "cidade": "CIDADE",
    "bairro": "BAIRRO", "cliente": "CLIENTE",
}
SEM_SEGMENTO = "(SEM SEGMENTO)"
TODOS_OS_SEGMENTOS = "(todos)"


def parametros_novos() -> dict:
    p = json.loads(json.dumps(PARAMETROS_PADRAO))
    return p


def carregar_parametros(caminho) -> dict:
    caminho = Path(caminho)
    p = parametros_novos()
    if caminho.exists():
        try:
            with open(caminho, encoding="utf-8") as f:
                guardado = json.load(f)
            for k, v in guardado.items():
                if k in p:
                    p[k] = v
            for c, _, padrao in CATEGORIAS:
                p["categorias"].setdefault(c, padrao)
        except (OSError, ValueError):
            pass
    return p


def sincronizar_ajustes(par: dict) -> None:
    """
    As metas escritas a mao valem SO para o mes em que foram escritas.
    "ajustes" e "ajustes_ind" sao a vitrine do mes aberto; o arquivo guarda
    todos os meses em "ajustes_por_mes". Trocou o mes: o que estava na
    vitrine volta para o mes dele e entra o do mes novo.
    (Antes de 05/10 os ajustes eram um so para todos os meses: o que havia
    fica com o mes que estava aberto quando a regra mudou.)
    """
    comp = normalizar_competencia(par.get("competencia")) or ""
    por_mes = par.get("ajustes_por_mes")
    if not isinstance(por_mes, dict):
        por_mes = {}
    de = par.get("ajustes_competencia") or ""
    if not de and not por_mes:
        de = comp                       # a primeira vez: herda o mes aberto
    if de:
        atual = {"ajustes": dict(par.get("ajustes") or {}),
                 "ajustes_ind": {k: dict(v) for k, v in
                                 (par.get("ajustes_ind") or {}).items() if v}}
        if atual["ajustes"] or atual["ajustes_ind"]:
            por_mes[de] = atual
        else:
            por_mes.pop(de, None)
    if de != comp:
        mes = por_mes.get(comp) or {}
        par["ajustes"] = dict(mes.get("ajustes") or {})
        par["ajustes_ind"] = {k: dict(v) for k, v in
                              (mes.get("ajustes_ind") or {}).items()}
    par["ajustes_por_mes"] = por_mes
    par["ajustes_competencia"] = comp


def gravar_parametros(par: dict, caminho) -> None:
    if "competencia" in par:
        sincronizar_ajustes(par)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(par, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# ler o PLANNER
# --------------------------------------------------------------------------
def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def normalizar_competencia(v) -> str:
    """
    Aceita '2026-09', '202609', '09/2026', 'Setembro/2026' nao - so numero.
    Devolve sempre 'AAAA-MM', ou '' se nao der para entender.
    """
    d = re.sub(r"\D", "", _texto(v))
    if len(d) != 6:
        return ""
    if d[:2] in ("19", "20", "21"):
        ano, mes = d[:4], d[4:]
    else:
        mes, ano = d[:2], d[2:]
    if not (1 <= int(mes) <= 12):
        return ""
    return f"{ano}-{mes}"


def competencia_da_meta(par: dict, dados: dict) -> str:
    """O mes escolhido no PARAMETROS manda; sem ele, o mes do PLANNER."""
    return (normalizar_competencia((par or {}).get("competencia"))
            or _texto((dados or {}).get("competencia")))


# --------------------------------------------------------------------------
# QUEM CONTA NA META DO SUPERVISOR - mes a mes
# --------------------------------------------------------------------------
# A cadeira VAGA, o vendedor que acabou de entrar, a zona que ninguem
# cobre neste mes: a carteira deles continua com meta (a meta e dos
# clientes, nao da pessoa) e o REALIZADO deles continua somando para o
# supervisor - se vendeu, vendeu. O que nao sobe para o supervisor e a
# META daquele mes: faturamento, visita e positivacao.
#
# A decisao e POR MES e fica gravada: so muda quando voce mudar de novo.
NIVEIS_DO_CORTE = ("vendedor", "zona")


def fora_da_meta(par: dict, competencia: str) -> dict:
    """Quem esta de fora NAQUELE mes: {'vendedor': {...}, 'zona': {...}}."""
    guardado = ((par or {}).get("fora_da_meta") or {}).get(
        normalizar_competencia(competencia)) or {}
    return {n: {_texto(x) for x in (guardado.get(n) or []) if _texto(x)}
            for n in NIVEIS_DO_CORTE}


def mes_configurado(par: dict, competencia: str) -> bool:
    """Ja decidiram quem conta neste mes?"""
    comp = normalizar_competencia(competencia)
    return bool(comp) and comp in ((par or {}).get("fora_da_meta") or {})


def guardar_fora_da_meta(par: dict, competencia: str,
                         vendedores=(), zonas=()) -> None:
    """Grava a decisao do mes - e so ela muda o que vale dali para frente."""
    comp = normalizar_competencia(competencia)
    if not comp:
        return
    par.setdefault("fora_da_meta", {})[comp] = {
        "vendedor": sorted({_texto(v) for v in vendedores if _texto(v)}),
        "zona": sorted({_texto(z) for z in zonas if _texto(z)}),
    }


def esquecer_fora_da_meta(par: dict, competencia: str) -> None:
    """Apaga a decisao do mes - ele volta a seguir a sugestao."""
    ((par or {}).get("fora_da_meta") or {}).pop(
        normalizar_competencia(competencia), None)


def sugerir_fora_da_meta(par: dict, competencia: str, clientes=()) -> dict:
    """
    O que propor para um mes que ainda NAO foi decidido:

        1. o ultimo mes ja decidido antes dele - o mes novo comeca igual
           ao anterior, que e o que quase sempre se quer
        2. nao havendo nenhum, o que o PLANNER trazia na coluna
           CONTA_SUPERVISOR (a marca antiga da cadeira vaga), para o
           numero de hoje nao mudar sozinho na primeira abertura
    """
    comp = normalizar_competencia(competencia)
    guardados = (par or {}).get("fora_da_meta") or {}
    if comp and comp in guardados:
        return fora_da_meta(par, comp)
    anteriores = sorted(k for k in guardados if not comp or k < comp)
    if anteriores:
        return fora_da_meta(par, anteriores[-1])
    if guardados:
        return fora_da_meta(par, sorted(guardados)[-1])
    return {"vendedor": {_texto(c.get("cod_vendedor")) for c in clientes
                         if _texto(c.get("cod_vendedor"))
                         and not c.get("conta_supervisor", True)},
            "zona": set()}


def fora_do_mes(par: dict, competencia: str, clientes=()) -> dict:
    """
    Quem fica FORA da meta do supervisor no mes (05/10): so a cadeira
    INATIVA no Planner daquele mes. O Planner e mes a mes, entao quem
    nao deve contar fica inativo la - ou tem a meta zerada no painel. A
    antiga aba QUEM CONTA NA META saiu; o que estava gravado nela nao
    vale mais.
    """
    return {"vendedor": {_texto(c.get("cod_vendedor")) for c in clientes
                         if _texto(c.get("cod_vendedor"))
                         and c.get("vendedor_ativo") is False},
            "zona": set()}


def meta_geral_do_mes(par: dict, competencia: str) -> float:
    """A META GERAL digitada para aquele mes (0 = nao tem)."""
    v = ((par or {}).get("metas_gerais") or {}).get(
        normalizar_competencia(competencia))
    return float(_numero(v)) if v not in (None, "") else 0.0


def gravar_meta_geral_do_mes(par: dict, competencia: str, valor) -> None:
    comp = normalizar_competencia(competencia)
    if not comp:
        return
    if valor in (None, "") or float(_numero(valor)) <= 0:
        (par.get("metas_gerais") or {}).pop(comp, None)
    else:
        par.setdefault("metas_gerais", {})[comp] = float(_numero(valor))


def _numero(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _data(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _texto(v)
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    # o cadastro do Protheus grava data como texto AAAAMMDD ("20260304")
    if len(s) == 8 and s.isdigit():
        try:
            return dt.datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass
    return None


_CHAVES: dict = {}


def _chave(titulo) -> str:
    k = _CHAVES.get(titulo) if isinstance(titulo, str) else None
    if k is None:
        k = re.sub(r"[^A-Z0-9]", "", str(titulo or "").upper())
        if isinstance(titulo, str) and len(_CHAVES) < 5000:
            _CHAVES[titulo] = k
    return k


def ler_planner(caminho) -> dict:
    """
    O PLANNER lido e guardado em RELATORIOS\\_CACHE_RELATORIOS: o mesmo
    PLANNER (e a mesma BASE_CLIENTE, de onde vem o segmento) abre na hora
    da segunda vez em diante. Mudou o arquivo: le de novo.
    """
    import os as _os                                   # noqa: PLC0415
    import pickle as _pickle                           # noqa: PLC0415
    caminho = Path(caminho)
    base = caminho.parent / "BASE_CLIENTE.xlsx"
    pasta = caminho.parent / "_CACHE_RELATORIOS"
    arq = pasta / f"planner_{caminho.stem}.pkl"
    assin = "|".join(f"{a.name}:{a.stat().st_mtime_ns}:{a.stat().st_size}"
                     for a in (caminho, base) if a.exists()) + "|v1"
    try:
        with open(arq, "rb") as f:
            guardado = _pickle.load(f)
        if guardado.get("assinatura") == assin:
            dados = guardado["dados"]
            dados["arquivo"] = caminho
            return dados
    except Exception:                                  # noqa: BLE001
        pass
    dados = _ler_planner_do_arquivo(caminho)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(f".{_os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            _pickle.dump({"assinatura": assin, "dados": dados}, f, protocol=4)
        _os.replace(tmp, arq)
    except OSError:
        pass
    return dados


def _ler_planner_do_arquivo(caminho) -> dict:
    """
    Le o PLANNER_BAP e devolve a carteira no nivel do CLIENTE, que e onde a
    meta nasce.

    Devolve {"clientes": [...], "mes": "2026-10", "visitas": n,
             "primeiro_sabado": data, "arquivo": Path}
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"PLANNER nao encontrado: {caminho}")
    wb = load_workbook(caminho, read_only=True, data_only=True)
    aba = "PLANNER" if "PLANNER" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[aba]
    it = ws.iter_rows(values_only=True)
    try:
        cabecalho = list(next(it))
    except StopIteration:
        wb.close()
        raise ValueError("O PLANNER esta vazio.")
    col = {_chave(t): i for i, t in enumerate(cabecalho) if t}

    def pega(linha, *nomes):
        for n in nomes:
            i = col.get(_chave(n))
            if i is not None and i < len(linha):
                return linha[i]
        return None

    if _chave("COD_CLIENTE") not in col:
        wb.close()
        raise ValueError("Este arquivo nao parece um PLANNER: nao tem "
                         "COD_CLIENTE.")

    por_cliente: dict[str, dict] = {}
    sabados = defaultdict(int)
    meses = set()
    competencias = set()          # AAAA-MM, tirado da propria data da visita
    total_linhas = 0
    for r in it:
        cod = _texto(pega(r, "COD_CLIENTE"))
        if not cod:
            continue
        total_linhas += 1
        loja = _texto(pega(r, "LOJA"))
        chave = f"{cod}-{loja or '00'}"
        data = _data(pega(r, "DATA_VISITA", "DATA"))
        if data is not None:
            competencias.add(f"{data.year:04d}-{data.month:02d}")
            if data.weekday() == 5:
                sabados[data] += 1
        mes = _texto(pega(r, "MES_VISITA"))
        if mes:
            meses.add(mes)
        c = por_cliente.get(chave)
        if c is None:
            c = por_cliente[chave] = {
                "chave": chave,
                "cod_cliente": cod,
                "loja": loja,
                "cliente": _texto(pega(r, "CLIENTE", "NOME_CLIENTE")),
                "fantasia": _texto(pega(r, "NOME_FANTASIA")),
                "gerente": _texto(pega(r, "GERENTE")) or "(sem gerente)",
                "cod_gerente": _texto(pega(r, "COD_GERENTE")),
                "supervisor": _texto(pega(r, "SUPERVISOR")) or "(sem supervisor)",
                "cod_supervisor": _texto(pega(r, "COD_SUPERVISOR")),
                "vendedor": _texto(pega(r, "VENDEDOR")) or "(sem vendedor)",
                "cod_vendedor": _texto(pega(r, "COD_VENDEDOR")),
                # vindo NAO do PLANNER, a meta deste vendedor nao sobe
                # para o supervisor (cadeira vaga). Sem a coluna - PLANNER
                # antigo - vale SIM, que e o de sempre.
                "conta_supervisor":
                    _texto(pega(r, "CONTA_SUPERVISOR")).upper() != "NAO",
                # a cadeira esta ocupada? PLANNER antigo nao tem a coluna:
                # ali todo mundo vale como ATIVO, que e o de sempre
                "vendedor_ativo":
                    _texto(pega(r, "VENDEDOR_ATIVO")).upper() != "NAO",
                "zona": _texto(pega(r, "ZONA")),
                "cod_zona": _texto(pega(r, "COD_ZONA")),
                # um dos 8 segmentos (PLANNER antigo, sem a coluna: vazio)
                "segmento": _texto(pega(r, "SEGMENTO")).upper() or SEM_SEGMENTO,
                "uf": _texto(pega(r, "UF")),
                "cidade": _texto(pega(r, "CIDADE")),
                "bairro": _texto(pega(r, "BAIRRO")),
                "curva": (_texto(pega(r, "CURVA", "CURVA_RECEITA")) or "Z")[-1],
                # O M3M e a MEDIA MENSAL dos 3 meses, nao a soma deles -
                # e ele que da o peso do cliente. PLANNER antigo so tinha a
                # soma da janela (FAT_JANELA_CURVA): ela e aceita e
                # dividida pelos meses, para o numero na tela ser sempre
                # media mensal.
                "fat_m3m": _numero(pega(r, "FAT_M3M", "MEDIA_MENSAL")),
                "fat_m3m_anterior": _numero(pega(r, "FAT_M3M_ANTERIOR",
                                                 "MEDIA_MENSAL_ANTERIOR")),
                "fat_m3m_soma": _numero(pega(r, "FAT_JANELA_CURVA",
                                             "RECEITA_PERIODO")),
                "fat_m6m": _numero(pega(r, "FAT_M6M", "MEDIA_MENSAL_6M")),
                "fat_m6m_soma": _numero(pega(r, "FAT_6M", "RECEITA_6M")),
                # AS VISITAS SE CONTAM SEPARADAS:
                #   visitas ........... as da ROTA DA SEMANA (dias uteis
                #                       mais o ultimo sabado) - sao estas
                #                       que a META VISITA usa
                #   visitas_deposito .. a visita unica do excedente, no
                #                       primeiro sabado
                "visitas": 0,
                "visitas_deposito": 0,
                "visitas_total": 0,
                "datas": [],
            }
        c["visitas_total"] += 1
        if data is not None:
            c["datas"].append(data)
    wb.close()

    # so agora se sabe qual sabado e o deposito, entao a separacao entre a
    # visita de rota e a do deposito e feita aqui, com as datas na mao

    # PLANNER antigo: so tem a SOMA da janela. Divide-se pelos meses para
    # o M3M e o M6M serem sempre media mensal, aqui e em todo lugar.
    antigo = not any(c["fat_m3m"] for c in por_cliente.values())
    if antigo:
        for c in por_cliente.values():
            c["fat_m3m"] = round(c["fat_m3m_soma"] / MESES_M3M, 2)
            c["fat_m6m"] = round(c["fat_m6m_soma"] / MESES_M6M, 2)
    for c in por_cliente.values():
        c.pop("fat_m3m_soma", None)
        c.pop("fat_m6m_soma", None)

    # O SABADO DO DEPOSITO e o PRIMEIRO SABADO DO MES - e la que o PLANNER
    # poe quem nao coube na semana. Nao e "o primeiro sabado com visita":
    # quando o deposito esta desligado so o ULTIMO sabado tem visita, e ele
    # e dia de rota normal, nao deposito. Entao a data e calculada pelo
    # calendario do mes e so vale se aquele dia realmente tiver visita.
    primeiro_sabado = None
    if sabados:
        qualquer = min(sabados)
        primeiro_do_mes = min(
            d for d in (dt.date(qualquer.year, qualquer.month, dia)
                        for dia in range(1, 8))
            if d.weekday() == 5)
        if primeiro_do_mes in sabados:
            primeiro_sabado = primeiro_do_mes
    for c in por_cliente.values():
        no_deposito = sum(1 for d in c["datas"] if d == primeiro_sabado) \
            if primeiro_sabado is not None else 0
        c["visitas_deposito"] = no_deposito
        c["visitas"] = c["visitas_total"] - no_deposito
        c["so_no_deposito"] = bool(
            primeiro_sabado is not None and c["datas"]
            and all(d == primeiro_sabado for d in c["datas"]))
        c.pop("datas", None)

    # O SEGMENTO E DA BASE_CLIENTE. Um PLANNER gerado antes da
    # segmentacao (ou um cliente que mudou de segmento depois) chegaria
    # aqui "(SEM SEGMENTO)" - a BASE_CLIENTE da mesma pasta corrige.
    try:
        seg_base = segmentos_da_base(Path(caminho).parent / "BASE_CLIENTE.xlsx")
    except (OSError, ValueError, KeyError):
        seg_base = {}
    if seg_base:
        for c in por_cliente.values():
            cod = _texto(c.get("cod_cliente"))
            novo = seg_base.get(cod) or seg_base.get(cod.zfill(6))
            if novo and novo != SEM_SEGMENTO:
                c["segmento"] = novo

    return {
        "clientes": list(por_cliente.values()),
        "formato_antigo": antigo,
        # PLANNER velho (ou BASE_CLIENTE velha): sem a janela anterior nao
        # da para saber quem cresceu e quem caiu, e TODO MUNDO cai na
        # faixa de quem esta caindo. A tela avisa em vermelho.
        "sem_m3m_anterior": not any(c.get("fat_m3m_anterior", 0.0) > 0
                                    for c in por_cliente.values()),
        "mes": sorted(meses)[0] if meses else "",
        # a competencia em AAAA-MM: e ela que nomeia o arquivo, porque o
        # MES_VISITA vem por extenso ("Outubro/2026") e barra nao pode
        # entrar em nome de arquivo
        "competencia": sorted(competencias)[0] if competencias else "",
        "visitas": total_linhas,
        "primeiro_sabado": primeiro_sabado,
        "arquivo": caminho,
    }


# --------------------------------------------------------------------------
# a conta da meta
# --------------------------------------------------------------------------
def percentuais_do_cliente(par: dict, cliente: dict) -> dict:
    """
    Os percentuais de categoria que valem para ESTE cliente. A zona manda
    mais que a UF, e a UF manda mais que o geral.
    """
    base = dict(par.get("categorias") or {})
    da_uf = (par.get("por_uf") or {}).get(cliente["uf"])
    if da_uf:
        base.update(da_uf)
    da_zona = (par.get("por_zona") or {}).get(cliente["cod_zona"])
    if da_zona:
        base.update(da_zona)
    return base


def crescimento(atual: float, anterior: float):
    """
    Quanto cresceu, em %, do M3M anterior para o atual.

    Sem faturamento na janela anterior nao ha com o que comparar: devolve
    None, e quem chama trata como "nao da para medir".
    """
    if not anterior or anterior <= 0:
        return None
    return (atual - anterior) / anterior * 100.0


def meta_por_crescimento(atual: float, anterior: float, par: dict) -> tuple:
    """
    A meta de UMA linha (cliente, vendedor, o que for) pelo historico dela.

    Devolve (meta, faixa) - a faixa e o texto que explica de onde veio,
    para aparecer na tela e no Excel.
    """
    faixas = par.get("faixas") or FAIXAS_PADRAO
    cres = crescimento(atual, anterior)
    if cres is None:
        # nao faturou na janela anterior: nao da para medir crescimento.
        # Vale a faixa de quem esta caindo, sobre o que ele tem hoje.
        ultima = faixas[-1]
        acrescimo = float(ultima.get("acrescimo") or 0.0)
        return atual * (1 + acrescimo / 100.0), "sem base de comparacao"
    for faixa in faixas:
        desde = faixa.get("desde")
        ate = faixa.get("cresceu_ate")
        if desde is not None and cres < float(desde):
            continue
        if ate is not None and cres >= float(ate):
            continue
        base = anterior if faixa.get("base") == "anterior" else atual
        acrescimo = float(faixa.get("acrescimo") or 0.0)
        de_onde = ("M3M anterior" if faixa.get("base") == "anterior"
                   else "M3M atual")
        return (base * (1 + acrescimo / 100.0),
                f"cresceu {cres:+.1f}% -> {de_onde} +{acrescimo:.0f}%")
    return atual, "sem faixa"


def _meta_visita_por_du(clientes: list, dados: dict, par: dict) -> None:
    """(21/10, Alexandre) A meta de visita do VENDEDOR = soma das metas dos
    dias uteis do mes desde a admissao (12; interior 6, e 12 no dia da
    cidade base - planner_nucleo.metas_de_visita_do_mes, posta em
    dados["meta_visita_dias"] pela aplicar_equipe_do_mes). Ela se reparte
    entre os clientes dele na proporcao das visitas da rota (zona, cidade,
    bairro... seguem somando)."""
    dias = dados.get("meta_visita_dias")
    if not dias or not float(par.get("meta_visita_por_du") or 0):
        return
    por_v = defaultdict(list)
    for c in clientes:
        por_v[_cod_vendedor(c.get("cod_vendedor"))].append(c)
    # (26/10, Alexandre) os 12 por dia sao o TOTAL A SER VISITADO; a meta
    # (RH) e pct_visita (90%) desse total
    pct = float(par.get("pct_visita") or 100.0) / 100.0
    for cod, cs in por_v.items():
        dv = dias.get(cod)
        if dv is None:
            continue
        total = float(sum(dv.values())) * pct
        base = sum(c.get("visitas") or 0 for c in cs)
        for c in cs:
            fatia = ((c.get("visitas") or 0) / base) if base else 1 / len(cs)
            c["meta_visita"] = total * fatia


def _com_piso(valor: float, piso: float) -> float:
    return max(float(valor or 0.0), float(piso or 0.0))


def calcular(dados: dict, par: dict) -> dict:
    """
    Poe a meta em cada cliente e devolve os recortes prontos.

    E UMA MECANICA SO, nao ha modo a escolher: a meta de cada cliente sai
    do historico dele - o M3M atual contra o M3M anterior - e nunca fica
    abaixo do piso do cliente. Ver meta_por_crescimento().

    Quem nao tem historico nenhum fica sem meta de faturamento, mas
    continua contando para visita e positivacao.
    """
    clientes = dados["clientes"]
    sincronizar_ajustes(par)
    meta_geral = float(par.get("meta_geral") or 0.0)
    pct_visita = float(par.get("pct_visita") or 0.0) / 100.0
    pct_pos = float(par.get("pct_positivacao") or 0.0) / 100.0
    piso_cliente = float(par.get("piso_cliente") or 0.0)
    so_com_fat = bool(par.get("piso_so_com_faturamento", True))

    total_m3m = sum(c["fat_m3m"] for c in clientes if c["fat_m3m"] > 0)

    # A META IMPORTADA, quando ha uma para este mes. Ela e por CIDADE e
    # por CATEGORIA, e o que o programa faz aqui e so distribui-la entre
    # os clientes daquela cidade, na proporcao do M3M de cada um.
    competencia_agora = competencia_da_meta(par, dados)
    cfg_metas = par.get("metas_importadas") or {}
    importadas = metas_do_mes(cfg_metas, competencia_agora)
    # QUANDO A META VEM POR FILIAL (o MODELO), a linha e o POLO -
    # MANAUS, BELEM, MATOGROSSO - e nao a cidade do cliente. O mapa
    # abaixo leva a cidade de cada cliente ao polo dele: primeiro pelo
    # que a aba Filiais da TABELA_BAP diz, depois pelo polo mais proximo
    # da mesma UF. Quando a meta vem por CIDADE, o mapa fica vazio e a
    # cidade casa com ela mesma.
    ligacao = (ligar_cidades_aos_polos(cfg_metas, clientes)
               if importadas and cfg_metas.get("por_polo") else {})
    polo_da_cidade = ligacao.get("polo_da_cidade") or {}

    def _linha_da_meta(cliente) -> str:
        """A chave com que o cliente procura a meta importada."""
        chave = chave_de_cidade(cliente.get("cidade"))
        return polo_da_cidade.get(chave, chave) if polo_da_cidade else chave

    m3m_da_cidade: dict[str, float] = {}
    if importadas:
        for c in clientes:
            if c["fat_m3m"] > 0:
                chave_c = _linha_da_meta(c)
                m3m_da_cidade[chave_c] = (m3m_da_cidade.get(chave_c, 0.0)
                                          + c["fat_m3m"])
    cidades_importadas = set()
    cidades_sem_m3m = set()

    for c in clientes:
        peso = (c["fat_m3m"] / total_m3m) if (total_m3m and c["fat_m3m"] > 0) \
            else 0.0
        c["peso"] = peso
        bruta, faixa = meta_por_crescimento(c["fat_m3m"],
                                            c.get("fat_m3m_anterior", 0.0),
                                            par)
        c["meta_calculada"] = bruta
        c["faixa"] = faixa
        # O PISO segura a meta do cliente pequeno la em cima e, com isso,
        # tira peso do cliente grande: a soma nao fica toda concentrada em
        # quem ja compra muito.
        tem_historico = (c["fat_m3m"] > 0
                         or c.get("fat_m3m_anterior", 0.0) > 0)
        piso_dele = piso_cliente if (tem_historico or not so_com_fat) else 0.0
        c["meta"] = _com_piso(bruta, piso_dele)
        c["no_piso"] = c["meta"] > bruta + 0.005
        c["tem_historico"] = tem_historico
        pcts = percentuais_do_cliente(par, c)
        for chave, _, _ in CATEGORIAS:
            c[f"meta_{chave}"] = c["meta"] * float(pcts.get(chave, 0.0)) / 100.0
        # A META VISITA sai das visitas da ROTA DA SEMANA. A visita unica
        # do excedente, no sabado-deposito, nao entra: ela nao e rota, e
        # valvula de escape - e somar as duas inflava a meta.
        c["meta_visita"] = c["visitas"] * pct_visita
        # positivacao: o cliente do deposito nao entra na conta
        c["conta_positivacao"] = 0 if c["so_no_deposito"] else 1
        c["meta_positivacao"] = c["conta_positivacao"] * pct_pos

        c["meta_de"] = "crescimento"

        # A CIDADE COM META IMPORTADA manda: a meta do cliente passa a ser
        # a fatia dele no M3M da cidade. Aqui NAO entra piso nem
        # crescimento - o que a diretoria fechou para a cidade e o que a
        # soma dos clientes dela tem de dar.
        chave_c = _linha_da_meta(c)
        c["polo_da_meta"] = chave_c
        da_cidade = importadas.get(chave_c)
        if da_cidade is not None:
            cidades_importadas.add(chave_c)
            base = m3m_da_cidade.get(chave_c, 0.0)
            if base <= 0:
                # sem M3M nenhum na cidade nao ha como repartir: a meta
                # dela fica sem dono, e o programa diz qual foi
                cidades_sem_m3m.add(chave_c)
                fatia = None
            else:
                fatia = c["fat_m3m"] / base if c["fat_m3m"] > 0 else 0.0
        if da_cidade is not None and fatia is not None:
            total_cid, por_cat, do_total = _meta_total_da_cidade(da_cidade,
                                                                 par)
            c["meta"] = total_cid * fatia
            c["meta_calculada"] = c["meta"]
            c["no_piso"] = False
            c["meta_de"] = "importada"
            c["faixa"] = "meta importada da cidade"
            if sum(por_cat.values()) > 0:
                for chave, _, _ in CATEGORIAS:
                    c[f"meta_{chave}"] = por_cat.get(chave, 0.0) * fatia
                if do_total:
                    # o arquivo trouxe categorias E um total: o total se
                    # reparte pelos percentuais da aba 1
                    for chave, _, _ in CATEGORIAS:
                        c[f"meta_{chave}"] += (do_total * fatia
                                               * float(pcts.get(chave, 0.0))
                                               / 100.0)
            else:
                for chave, _, _ in CATEGORIAS:
                    c[f"meta_{chave}"] = (c["meta"]
                                          * float(pcts.get(chave, 0.0))
                                          / 100.0)

    # A META GERAL DO MES, digitada para o mes que NAO tem meta no arquivo:
    # ela se reparte entre todos os clientes pelo M3M de cada um e sobe
    # (cliente -> zona/vendedor -> supervisor -> gerente), sem piso nem
    # crescimento.
    geral_mes = 0.0 if importadas else meta_geral_do_mes(par,
                                                         competencia_agora)
    if geral_mes > 0 and clientes:
        for c in clientes:
            if total_m3m:
                fatia = c["fat_m3m"] / total_m3m if c["fat_m3m"] > 0 else 0.0
            else:
                fatia = 1.0 / len(clientes)
            c["meta"] = geral_mes * fatia
            c["meta_calculada"] = c["meta"]
            c["no_piso"] = False
            c["meta_de"] = "geral"
            c["faixa"] = "rateio da meta geral do mes"
            pcts = percentuais_do_cliente(par, c)
            for chave, _, _ in CATEGORIAS:
                c[f"meta_{chave}"] = c["meta"] * float(pcts.get(chave, 0.0)) \
                    / 100.0

    # (21/10, Alexandre) A META DE VISITA POR DIA UTIL (substitui os 90%)
    _meta_visita_por_du(clientes, dados, par)
    # (26/10) a trava do mes vem antes do ajuste a mao: o que o analista
    # escrever no Gerador de Meta continua valendo por cima
    _aplicar_travadas_ind(clientes, par, competencia_agora)
    _aplicar_ajustes(clientes, par)
    _aplicar_ajustes_ind(clientes, par)
    # (06/11, Alexandre: "Tirar AP e os 30") a carteira do vendedor INATIVO
    # no Planner do mes (ex.: o 000040 com os clientes do Amapa) nao leva
    # meta de visita nem de positivacao nos clientes: antes a linha dele
    # zerava (03/11), mas os clientes guardavam a meta e ela subia para o
    # "(sem gerente)", a UF AP e o total da BAP (227 em vez de 197)
    for c in clientes:
        if c.get("vendedor_ativo") is False:
            c["meta_visita"] = 0.0
            c["meta_positivacao"] = 0.0
    par["_meta_importada"] = bool(importadas)
    par["_meta_geral_mes"] = geral_mes
    recortes = _montar_recortes(clientes, par,
                                fora_do_mes(par, competencia_agora, clientes))
    par.pop("_meta_importada", None)
    par.pop("_meta_geral_mes", None)
    # A META COMERCIAL: a do gerente desdobrada (a de antes vira meta_rh)
    _aplicar_comercial(clientes, recortes, par,
                       dados.get("meses_de_casa") or {},
                       dados.get("fracao_de_casa") or {})
    _aplicar_metas_travadas(clientes, recortes, par, competencia_agora)
    familias = _metas_por_familia(clientes,
                                  _mix_dos_dados(dados, competencia_agora))
    categorias_bap = _metas_por_categoria(
        clientes, _mix_dos_dados(dados, competencia_agora, "categoria"))
    try:
        import catalogo_bap as _cb                     # noqa: PLC0415
        o_sis, o_lin = _cb.ORDEM_SISTEMA, _cb.ORDEM_LINHA
    except Exception:                                  # noqa: BLE001
        o_sis = o_lin = ()
    sistemas = _metas_por_grupo(
        clientes, _mix_dos_dados(dados, competencia_agora, "sistema"),
        "meta_sistema", o_sis)
    linhas_cat = _metas_por_grupo(
        clientes, _mix_dos_dados(dados, competencia_agora, "linha"),
        "meta_linha", o_lin)
    total_geral = _fechar_linha("TOTAL", clientes)
    total_geral["meta_rh"] = sum(l.get("meta_rh") or 0.0
                                 for l in recortes.get("gerente") or [])
    return {
        "clientes": clientes,
        "recortes": recortes,
        # UMA linha TOTAL POR RECORTE - a soma do que esta naquela aba
        "totais": {r: total_do_recorte(recortes[r]) for r in RECORTES},
        "total": total_geral,
        # a meta comercial aberta por FAMILIA DA PECA (a BAP inteira)
        "familias": familias,
        # e por CATEGORIA (Catalogo BAP 2026: peças, baterias...)
        "categorias_bap": categorias_bap,
        # (15/10) e por SISTEMA e LINHA do catalogo
        "sistemas": sistemas, "linhas_catalogo": linhas_cat,
        "mes": dados.get("mes", ""),
        "competencia": competencia_da_meta(par, dados),
        "visitas": dados.get("visitas", 0),
        "primeiro_sabado": dados.get("primeiro_sabado"),
        "arquivo": dados.get("arquivo"),
        "total_m3m": total_m3m,
        "sem_faturamento": sum(1 for c in clientes if c["fat_m3m"] <= 0),
        "sem_historico": sum(1 for c in clientes
                             if not c.get("tem_historico")),
        "no_piso": sum(1 for c in clientes if c.get("no_piso")),
        "modo": ("importada" if importadas else
                 "geral" if geral_mes > 0 else "crescimento"),
        "meta_geral_mes": geral_mes,
        # quem ficou de fora da meta do supervisor neste mes, e se essa
        # decisao ja foi gravada ou ainda e a sugestao
        "fora_da_meta": {n: sorted(v) for n, v in
                         fora_do_mes(par, competencia_agora, clientes).items()},
        "mes_configurado": mes_configurado(par, competencia_agora),
        "clientes_fora_da_meta": sum(1 for c in clientes
                                     if not c.get("conta_na_meta", True)),
        # o rastro da importacao, para a tela poder contar a historia
        "meta_importada": bool(importadas),
        "cidades_importadas": sorted(cidades_importadas),
        "cidades_no_arquivo": len(importadas),
        "cidades_sem_m3m": sorted(cidades_sem_m3m),
        "clientes_importados": sum(1 for c in clientes
                                   if c.get("meta_de") == "importada"),
        "meta_importada_total": sum(
            _meta_total_da_cidade(v, par)[0]
            for k, v in importadas.items() if k in cidades_importadas),
        # quando a meta vem por FILIAL, vale saber o que sobrou de fora
        "por_polo": bool(cfg_metas.get("por_polo")),
        "nomes_das_linhas": dict(cfg_metas.get("polos")
                                 or cfg_metas.get("cidades") or {}),
        "cidades_sem_polo": list(ligacao.get("sem_polo") or []),
    }


def _mix_dos_dados(dados: dict, competencia: str, qual="familia") -> dict:
    """O mix do M3M (qual = "familia" ou "categoria"): o que veio pronto em
    dados["mix_familia"/"mix_categoria"] ou o da TABELA_BAP que mora ao
    lado do PLANNER."""
    if dados.get(f"mix_{qual}") is not None:
        return dados[f"mix_{qual}"]
    if qual != "familia" and dados.get("mix_familia") is not None:
        return {}           # teste com mix pronto: sem categoria
    guardado = dados.setdefault(f"_mix_por_mes_{qual}", {})
    if competencia not in guardado:
        arq = dados.get("arquivo")
        tabela = None
        if arq:      # o PLANNER do mes pode morar numa subpasta da RELATORIOS
            for pasta in list(Path(arq).parents)[:3]:
                for cand in (pasta / "TABELA_BAP.xlsx",
                             pasta / RELATORIOS_SUB / "TABELA_BAP.xlsx"):
                    if cand.exists():
                        tabela = cand
                        break
                if tabela:
                    break
        try:
            guardado[competencia] = (
                (_mix_m3m(tabela, competencia).get(qual) or {})
                if tabela else {})
        except Exception:                              # noqa: BLE001
            guardado[competencia] = {}
    return guardado[competencia]


# como cada recorte identifica a linha e como ela se chama
_CAMPO_DO_RECORTE = {
    "gerente": ("gerente", "gerente"),
    "supervisor": ("supervisor", "supervisor"),
    "vendedor": ("cod_vendedor", "vendedor"),
    "zona": ("cod_zona", "zona"),
    "segmento": ("segmento", "segmento"),
    "uf": ("uf", "uf"),
    "cidade": ("cidade", "cidade"),
    "bairro": ("bairro", "bairro"),
    "cliente": ("chave", "cliente"),
}


def chave_da_linha(recorte: str, cliente: dict) -> str:
    campo, _ = _CAMPO_DO_RECORTE[recorte]
    if recorte == "cidade":
        return f"{cliente['uf']}|{cliente['cidade']}"
    if recorte == "bairro":
        return f"{cliente['uf']}|{cliente['cidade']}|{cliente['bairro']}"
    return cliente.get(campo) or ""


def _rotulo(recorte: str, cliente: dict) -> str:
    _, campo = _CAMPO_DO_RECORTE[recorte]
    if recorte == "vendedor":
        return f"{cliente['cod_vendedor']} - {cliente['vendedor']}".strip(" -")
    if recorte == "zona":
        return f"{cliente['cod_zona']} - {cliente['zona']}".strip(" -")
    if recorte == "cidade":
        return f"{cliente['uf']} - {cliente['cidade']}"
    if recorte == "bairro":
        return f"{cliente['cidade']} - {cliente['bairro']}"
    if recorte == "cliente":
        return f"{cliente['cod_cliente']}/{cliente['loja']} - {cliente['cliente']}"
    return cliente.get(campo) or ""


def codigo_e_nome(recorte: str, cliente: dict) -> tuple:
    """
    O CODIGO e o NOME da linha, separados - para o Excel ter as duas
    colunas em vez de "000035 - MARCOS AURELIO" tudo junto.
    """
    if recorte == "gerente":
        return cliente.get("cod_gerente", ""), cliente.get("gerente", "")
    if recorte == "supervisor":
        return cliente.get("cod_supervisor", ""), cliente.get("supervisor", "")
    if recorte == "vendedor":
        return cliente.get("cod_vendedor", ""), cliente.get("vendedor", "")
    if recorte == "zona":
        return cliente.get("cod_zona", ""), cliente.get("zona", "")
    if recorte == "segmento":
        return "", cliente.get("segmento", "")
    if recorte == "uf":
        return cliente.get("uf", ""), cliente.get("uf", "")
    if recorte == "cidade":
        return cliente.get("uf", ""), cliente.get("cidade", "")
    if recorte == "bairro":
        return cliente.get("cidade", ""), cliente.get("bairro", "")
    if recorte == "cliente":
        return (f"{cliente.get('cod_cliente', '')}/"
                f"{cliente.get('loja', '')}", cliente.get("cliente", ""))
    return "", ""


def _fechar_linha(rotulo: str, grupo: list) -> dict:
    linha = {
        "rotulo": rotulo,
        "clientes": len(grupo),
        # AS DUAS BASES: quem esta na rota da semana, e a carteira inteira
        "base_visita": sum(1 for c in grupo if not c["so_no_deposito"]),
        "base_carteira": len(grupo),
        "excedentes": sum(1 for c in grupo if c["so_no_deposito"]),
        # VISITAS = as da rota da semana. O excedente aparece separado,
        # para o total continuar batendo com o PLANNER.
        "visitas": sum(c["visitas"] for c in grupo),
        "visitas_deposito": sum(c.get("visitas_deposito", 0) for c in grupo),
        "visitas_total": sum(c.get("visitas_total", c["visitas"])
                             for c in grupo),
        "fat_m3m": sum(c["fat_m3m"] for c in grupo),
        "fat_m3m_anterior": sum(c.get("fat_m3m_anterior", 0.0) for c in grupo),
        "meta_dos_clientes": sum(c["meta"] for c in grupo),
        "meta": sum(c["meta"] for c in grupo),
        "meta_visita": sum(c["meta_visita"] for c in grupo),
        "positivacao_base": sum(c["conta_positivacao"] for c in grupo),
        "meta_positivacao": sum(c["meta_positivacao"] for c in grupo),
        "ajustada": any(c.get("ajustado") for c in grupo),
    }
    for chave, _, _ in CATEGORIAS:
        linha[f"meta_{chave}"] = sum(c[f"meta_{chave}"] for c in grupo)
    return linha


def total_do_recorte(linhas: list, rotulo: str = "TOTAL") -> dict:
    """
    A linha TOTAL de UM recorte: a soma das linhas QUE ESTAO NA TELA.

    Nao da para usar a mesma linha TOTAL em todas as abas: cada nivel tem
    a sua regra, entao a soma da coluna META FAT. muda de aba para aba - a
    do CLIENTE e a soma dos clientes, a da UF e a META GERAL, a do
    SUPERVISOR e a soma dos vendedores. O que nao muda sao as contagens
    (base, visitas) e o FAT M3M, porque todo recorte reparte os MESMOS
    clientes.
    """
    soma = {
        "rotulo": rotulo,
        "chave": "",
        "recorte": "total",
        "faixa": "",
        "ajustada": any(l.get("ajustada") for l in linhas),
        "no_piso": False,
    }
    # meta_cadastro estava de fora: a coluna META CAD. tinha numero em
    # cada linha e o TOTAL saia VAZIO. So nao aparecia porque a coluna
    # nao estava no conjunto executivo.
    campos = ["clientes", "base_visita", "base_carteira", "excedentes",
              "visitas", "visitas_deposito", "visitas_total", "fat_m3m",
              "fat_m3m_anterior", "meta_dos_clientes", "meta", "meta_visita",
              "positivacao_base", "meta_positivacao", "meta_cadastro",
              "meta_calculada", "meta_rh"]
    campos += [f"meta_{c}" for c, _, _ in CATEGORIAS]
    for campo in campos:
        soma[campo] = sum(l.get(campo) or 0 for l in linhas)
    return soma


def _chefe_do_grupo(recorte: str, grupo: list) -> tuple:
    """
    (codigo, nome) de quem o grupo responde - o SUPERVISOR do vendedor.

    Sai da carteira, nao de um cadastro a parte: e o supervisor que esta
    nos clientes daquele vendedor. Carteira dividida entre dois
    supervisores (acontece quando o vendedor acabou de trocar de equipe)
    fica com o que tem MAIS clientes, e nao com o primeiro que aparecer.
    Nos outros recortes a coluna fica vazia - zona e cidade nao respondem
    a supervisor nenhum.
    """
    if recorte not in ("vendedor", "cliente"):
        return "", ""
    conta = Counter((_texto(c.get("cod_supervisor")),
                     _texto(c.get("supervisor"))) for c in grupo)
    (cod, nome), _ = conta.most_common(1)[0]
    return cod, nome


def _agrupar(clientes: list, recorte: str) -> list:
    grupos: dict[str, list] = defaultdict(list)
    rotulos: dict[str, str] = {}
    for c in clientes:
        k = chave_da_linha(recorte, c)
        grupos[k].append(c)
        rotulos.setdefault(k, _rotulo(recorte, c))
    saida = []
    for k, grupo in grupos.items():
        linha = _fechar_linha(rotulos[k], grupo)
        linha["chave"] = k
        linha["recorte"] = recorte
        linha["codigo"], linha["nome"] = codigo_e_nome(recorte, grupo[0])
        # a UF e a zona da linha, para o painel saber o que abrir quando
        # alguem quiser mexer no percentual daquele pedaco
        linha["uf"] = grupo[0]["uf"] if recorte in ("uf", "cidade", "bairro") \
            else ""
        linha["cod_zona"] = grupo[0]["cod_zona"] if recorte == "zona" else ""
        linha["vendedor_ativo"] = bool(grupo[0].get("vendedor_ativo", True))
        linha["cod_supervisor"], linha["supervisor"] = _chefe_do_grupo(recorte,
                                                                      grupo)
        saida.append(linha)
    return sorted(saida, key=lambda x: -x["meta"])


def _montar_recortes(clientes: list, par: dict, fora: dict = None) -> dict:
    """
    Monta os oito recortes. CADA NIVEL TEM A SUA REGRA - e por isso que
    eles nao sao mais a simples soma um do outro:

        CLIENTE ..... a meta dele, pelo historico dele, com o PISO do
                      cliente (ja veio pronta de calcular())
        BAIRRO e
        CIDADE ...... a soma dos clientes
        ZONA ........ a soma dos clientes DELA, com o PISO da zona
        VENDEDOR .... a meta DELE, pelo historico dele (o M3M da carteira
                      dele contra o M3M anterior), com o PISO do vendedor.
                      Nao e a soma dos clientes - a coluna
                      "meta_dos_clientes" mostra a soma, para voce ver a
                      diferenca
        SUPERVISOR .. a soma da meta dos VENDEDORES da equipe dele
        UF e
        GERENTE ..... o rateio da META GERAL: com uma linha so, ela fica
                      com a meta geral inteira; com mais de uma, cada uma
                      leva a fatia proporcional ao M3M da carteira dela

    E UMA MECANICA SO - nao ha modo a escolher. O M3M x o M3M anterior
    vale para CLIENTE e VENDEDOR; a META GERAL dos parametros vale para
    GERENTE e UF; o resto e soma.

    Toda linha traz "meta_dos_clientes" (a soma pura) e "meta" (a que vale
    depois da regra do nivel), para a diferenca ficar a vista.
    """
    recortes = {r: _agrupar(clientes, r) for r in RECORTES}
    total = sum(c["meta"] for c in clientes)
    ajustes = par.get("ajustes") or {}

    # QUEM NAO CONTA NA META DO SUPERVISOR NESTE MES. A linha do vendedor
    # e a da zona continuam com a meta delas; o que nao sobe para o
    # supervisor e essa meta. O realizado sobe sempre - se vendeu, vendeu.
    fora = fora or {}
    fora_v = {_texto(v) for v in (fora.get("vendedor") or ())}
    fora_z = {_texto(z) for z in (fora.get("zona") or ())}
    # o quanto da carteira de cada vendedor esta DENTRO da meta do mes
    dentro_v = defaultdict(lambda: [0.0, 0.0, 0.0])
    toda_v = defaultdict(lambda: [0.0, 0.0, 0.0])
    dentro_sup = defaultdict(lambda: [0.0, 0.0, 0.0])
    zonas_fora_sup = defaultdict(set)
    for c in clientes:
        cod_v = _texto(c.get("cod_vendedor"))
        cod_z = _texto(c.get("cod_zona"))
        conta = cod_v not in fora_v and cod_z not in fora_z
        c["conta_na_meta"] = conta
        trio = (c["meta"], c["meta_visita"], c["meta_positivacao"])
        for i, valor in enumerate(trio):
            toda_v[cod_v][i] += valor
            if conta:
                dentro_v[cod_v][i] += valor
                dentro_sup[c.get("supervisor", "")][i] += valor
        if cod_z in fora_z:
            zonas_fora_sup[c.get("supervisor", "")].add(cod_z)

    def _fatia_do_vendedor(cod: str, i: int) -> float:
        """Quanto da meta do vendedor conta - descontando a zona de fora."""
        inteiro = toda_v[cod][i]
        return (dentro_v[cod][i] / inteiro) if inteiro else 1.0

    for recorte in RECORTES:
        for linha in recortes[recorte]:
            linha["conta_na_meta"] = not (
                (recorte == "vendedor" and linha["chave"] in fora_v)
                or (recorte == "zona" and linha["chave"] in fora_z))
            # CADASTRO COM COMPRA e meta de GENTE, nao de territorio:
            # quem prospecta e o vendedor. Zona, cidade, bairro e cliente
            # ficam sem meta (mostram so o realizado), como ja acontece
            # com a visita.
            linha["meta_cadastro"] = None
    meta_cad = float(par.get("meta_cadastro") or 0.0)

    def cad_do_vendedor(cod):
        a_mao = ajuste_de(par, "meta_cadastro", "vendedor", cod)
        return meta_cad if a_mao is None else a_mao
    for linha in recortes["vendedor"]:
        linha["meta_cadastro"] = (cad_do_vendedor(linha["chave"])
                                  if linha["chave"] else None)
    vendedores_do_gerente = defaultdict(set)
    for c in clientes:
        cod_v = _texto(c.get("cod_vendedor"))
        if cod_v and cod_v not in fora_v:
            vendedores_do_gerente[c.get("gerente", "")].add(cod_v)

    def escrito_a_mao(recorte, chave):
        """O valor que voce escreveu para esta linha, se escreveu."""
        v = ajustes.get(f"{recorte}|{chave}")
        return None if v is None else float(v)

    # ZONA: piso proprio
    piso_zona = float(par.get("piso_zona") or 0.0)
    for linha in recortes["zona"]:
        linha["meta_calculada"] = linha["meta"]
        a_mao = escrito_a_mao("zona", linha["chave"])
        if a_mao is not None:
            linha["meta"] = a_mao
            linha["no_piso"] = False
            linha["faixa"] = "escrita a mao"
            linha["ajustada"] = True
        elif par.get("_meta_geral_mes"):
            linha["no_piso"] = False
            linha["faixa"] = "soma dos clientes"
        else:
            linha["no_piso"] = piso_zona > linha["meta"] + 0.005
            linha["meta"] = _com_piso(linha["meta"], piso_zona)
            linha["faixa"] = ("no piso da zona" if linha["no_piso"]
                              else "soma dos clientes")
        _refazer_categorias(linha, par, clientes)

    # VENDEDOR: a meta e do vendedor, nao a soma dos clientes dele
    piso_vend = float(par.get("piso_vendedor") or 0.0)
    for linha in recortes["vendedor"]:
        if par.get("_meta_geral_mes"):
            bruta, faixa = linha["meta"], "soma dos clientes (meta geral)"
        elif linha["chave"]:
            bruta, faixa = meta_por_crescimento(linha["fat_m3m"],
                                                linha["fat_m3m_anterior"], par)
        else:
            bruta, faixa = linha["meta"], "soma dos clientes"
        linha["meta_calculada"] = bruta
        a_mao = escrito_a_mao("vendedor", linha["chave"])
        if a_mao is not None:
            linha["meta"] = a_mao
            linha["no_piso"] = False
            linha["faixa"] = "escrita a mao"
            linha["ajustada"] = True
        elif par.get("_meta_geral_mes"):
            linha["no_piso"] = False
            linha["meta"] = bruta
            linha["faixa"] = faixa
        else:
            linha["no_piso"] = piso_vend > bruta + 0.005
            linha["meta"] = _com_piso(bruta, piso_vend)
            linha["faixa"] = ("no piso do vendedor" if linha["no_piso"]
                              else faixa)
        _refazer_categorias(linha, par, clientes)

    # SUPERVISOR: a soma da meta dos VENDEDORES da equipe dele
    supervisor_do_vendedor = {}
    for c in clientes:
        if c["cod_vendedor"]:
            supervisor_do_vendedor.setdefault(c["cod_vendedor"],
                                              c["supervisor"])
    meta_do_vendedor = {l["chave"]: l["meta"] for l in recortes["vendedor"]
                        if l["chave"]}
    for linha in recortes["supervisor"]:
        # SO ENTRA QUEM CONTA NESTE MES: o vendedor de fora (a cadeira
        # vaga, o que acabou de entrar) tem meta propria, mas ela nao
        # sobe para a equipe. A zona de fora desconta a fatia dela da
        # meta do vendedor que a atende.
        seus = [v for v in meta_do_vendedor
                if supervisor_do_vendedor.get(v) == linha["chave"]]
        contam = [v for v in seus if v not in fora_v]
        linha["meta_calculada"] = sum(meta_do_vendedor[v]
                                      * _fatia_do_vendedor(v, 0)
                                      for v in contam)
        a_mao = escrito_a_mao("supervisor", linha["chave"])
        linha["meta"] = (a_mao if a_mao is not None
                         else linha["meta_calculada"])
        # VISITA e POSITIVACAO tambem param na porta: sao a soma dos
        # clientes que contam, nao da carteira inteira
        linha["meta_visita"] = dentro_sup[linha["chave"]][1]
        linha["meta_positivacao"] = dentro_sup[linha["chave"]][2]
        linha["vendedores_ativos"] = len(contam)
        linha["vendedores_fora"] = len(seus) - len(contam)
        # a meta de cadastro do supervisor e a da equipe que conta
        linha["meta_cadastro"] = sum(cad_do_vendedor(v) for v in contam)
        linha["zonas_fora"] = len(zonas_fora_sup.get(linha["chave"], ()))
        linha["no_piso"] = False
        linha["ajustada"] = linha.get("ajustada") or a_mao is not None
        de_fora = ""
        if linha["vendedores_fora"] or linha["zonas_fora"]:
            partes = []
            if linha["vendedores_fora"]:
                partes.append(f"{linha['vendedores_fora']} vendedor(es)")
            if linha["zonas_fora"]:
                partes.append(f"{linha['zonas_fora']} zona(s)")
            de_fora = " - fora da meta do mes: " + " e ".join(partes)
        linha["faixa"] = ("escrita a mao" if a_mao is not None else
                          ((f"soma de {len(contam)} vendedor(es)"
                            if contam else "sem vendedor na equipe") + de_fora))
        _refazer_categorias(linha, par, clientes)

    # GERENTE: o rateio da META GERAL. Com um gerente so, ele fica com ela
    # inteira; com mais de um, cada um leva a fatia proporcional ao M3M da
    # carteira dele.
    # Com meta importada, o rateio de UF e GERENTE sai da SOMA dos
    # clientes - nao faria sentido ratear um numero digitado por cima de
    # uma meta que a diretoria ja fechou cidade por cidade.
    if par.get("_meta_importada"):
        meta_geral = total
    elif par.get("_meta_geral_mes"):
        meta_geral = float(par["_meta_geral_mes"])
    else:
        meta_geral = float(par.get("meta_geral") or 0.0) or total
    for recorte in ("gerente", "uf"):
        linhas = recortes[recorte]
        m3m_total = sum(l["fat_m3m"] for l in linhas) or 0.0
        for linha in linhas:
            if len(linhas) == 1 or not m3m_total:
                fatia = meta_geral / max(1, len(linhas))
                como = ("a META GERAL inteira" if len(linhas) == 1
                        else f"a META GERAL dividida pelas {len(linhas)} "
                             f"linhas")
            else:
                fatia = meta_geral * (linha["fat_m3m"] / m3m_total)
                como = (f"rateio da META GERAL "
                        f"({linha['fat_m3m'] / m3m_total * 100:.1f}% do M3M)")
            linha["meta_calculada"] = fatia
            a_mao = escrito_a_mao(recorte, linha["chave"])
            linha["meta"] = a_mao if a_mao is not None else fatia
            linha["no_piso"] = False
            linha["ajustada"] = linha.get("ajustada") or a_mao is not None
            linha["faixa"] = "escrita a mao" if a_mao is not None else como
            if recorte == "gerente":
                linha["meta_cadastro"] = sum(
                    cad_do_vendedor(v)
                    for v in vendedores_do_gerente.get(linha["chave"], ()))
            _refazer_categorias(linha, par, clientes)

    # a linha que teve a meta escrita a mao mostra exatamente o que se
    # escreveu (a visita do supervisor, por exemplo, so soma quem conta)
    for campo, por_linha in (par.get("ajustes_ind") or {}).items():
        for chave_completa, valor in (por_linha or {}).items():
            recorte, _, chave = str(chave_completa).partition("|")
            if recorte not in recortes:
                continue
            if campo in AJUSTE_SO_EM_PESSOA and \
                    recorte not in AJUSTE_SO_EM_PESSOA[campo]:
                continue
            for linha in recortes[recorte]:
                if linha["chave"] == chave:
                    linha[campo] = float(valor)
                    linha["ajustada"] = True
                    linha.setdefault("ajustes_da_linha", []).append(campo)

    for recorte in RECORTES:
        recortes[recorte].sort(key=lambda x: -x["meta"])
    return recortes


def _refazer_categorias(linha: dict, par: dict, clientes: list) -> None:
    """
    Depois que a meta da linha mudou (piso, crescimento, soma de zonas), as
    metas por categoria acompanham - na mesma proporcao que as categorias
    tinham na soma dos clientes daquela linha, para respeitar os
    percentuais de UF e de zona que estiverem valendo.
    """
    base = linha.get("meta_dos_clientes") or 0.0
    if base > 0:
        fator = linha["meta"] / base
        for chave, _, _ in CATEGORIAS:
            linha[f"meta_{chave}"] = linha[f"meta_{chave}"] * fator
        return
    # linha sem meta de cliente nenhuma: reparte pelos percentuais gerais
    pcts = par.get("categorias") or {}
    for chave, _, padrao in CATEGORIAS:
        linha[f"meta_{chave}"] = linha["meta"] * float(
            pcts.get(chave, padrao)) / 100.0


# ==========================================================================
# AS DUAS METAS DE FATURAMENTO (06/10)
# ==========================================================================
#   META RH ......... o modelo de sempre: cada nivel com a sua regra (o
#                     piso do vendedor, a soma dos vendedores ativos no
#                     supervisor, o rateio da META GERAL no gerente, o que
#                     foi escrito a mao). E a que paga a RV e a que vai no
#                     PDF da parcial. Fica em "meta_rh".
#   META COMERCIAL .. a meta do GERENTE desdobrada para todo mundo: os
#                     clientes do gerente sao reescalados para somar
#                     exatamente a meta dele e TODO recorte vira a soma
#                     dos seus clientes - vendedor = soma das UFs = soma
#                     das cidades = soma dos segmentos, bairros, clientes e
#                     familias. Fica em "meta" e e a de todos os
#                     acompanhamentos.
# A proporcao entre os clientes e a da meta RH deles (historico, piso do
# cliente, meta importada, o que foi escrito a mao): a comercial so
# muda a escala para fechar com o gerente.
# Visita, positivacao e cadastro sao uma meta so - nao ha versao RH.
def meta_do_mes_de_casa(par: dict, n: int):
    """A meta fixa de quem esta no n-esimo mes de casa (1 = primeiro), ou
    None quando ele ja passou da tabela (vale o piso e o potencial)."""
    tabela = [float(_numero(v)) for v in
              ((par or {}).get("meta_mes_de_casa") or [])]
    if n and 1 <= n <= len(tabela):
        return tabela[n - 1]
    return None


def _repartir(total: float, pesos: dict, pisos: dict) -> dict:
    """Reparte o total pelos pesos, garantindo o piso de quem tem piso.
    Nao cabe o piso de todos: reparte so pelos pesos (o total manda)."""
    if not pesos:
        return {}
    if sum(pisos.values()) > total + 0.005:
        pisos = {}
    saida, livres, resta = {}, dict(pesos), total
    while livres:
        soma = sum(livres.values())
        parte = {k: (resta * w / soma) if soma else resta / len(livres)
                 for k, w in livres.items()}
        abaixo = [k for k, v in parte.items() if v < pisos.get(k, 0.0) - 0.005]
        if not abaixo:
            saida.update(parte)
            break
        for k in abaixo:
            saida[k] = pisos[k]
            resta -= pisos[k]
            livres.pop(k)
    return saida


def _aplicar_comercial(clientes: list, recortes: dict, par: dict,
                       casa: dict = None, fracao: dict = None) -> None:
    """
    A meta COMERCIAL, de cima para baixo, gerente a gerente:
      1. quem esta nos primeiros meses de casa leva a meta fixa da tabela
         da aba 1 (1o mes 60 mil, 2o 80, 3o 100, 4o 120);
      2. o que sobra da meta do gerente se reparte entre os demais
         vendedores pelo POTENCIAL de cada um (a soma da meta RH dos
         clientes dele = o historico), com o PISO do vendedor (120 mil)
         para quem ja passou da tabela - mas a soma nunca passa da meta do
         gerente: faltando so 300 mil, o ultimo leva 300 mil;
      3. a meta do vendedor desce para os clientes dele na proporcao de
         antes, e todo recorte vira a soma dos clientes.
    A META RH do vendedor (a que paga a RV) passa a ser a comercial com
    TETO: o da tabela nos primeiros meses e o teto RH (120 mil) depois.
    O que foi escrito a mao no vendedor continua mandando na RH.
    (03/11, Alexandre) Vendedor INATIVO no Planner do mes (cadeira vaga,
    quem saiu) nao leva desafio nem meta RH: o desafio da carteira dele se
    reparte entre os ativos (pelo potencial) e o time continua somando a
    meta do gerente.
    """
    casa = casa or {}
    fracao = fracao or {}
    alvo = {l["chave"]: float(l["meta"] or 0.0)
            for l in recortes.get("gerente") or []}
    piso = float(par.get("piso_vendedor") or 0.0)
    por_ger = defaultdict(lambda: defaultdict(list))
    for c in clientes:
        c["meta_rh_cliente"] = c["meta"]
        cod = _texto(c.get("cod_vendedor"))
        por_ger[chave_da_linha("gerente", c)][cod].append(c)
    # (03/11) o gerente que so tem vendedor INATIVO (ex.: o 000040 sem
    # superior, num "(sem gerente)") passa a meta dele para os outros
    # gerentes, na proporcao das metas - o time continua somando a geral
    def so_inativos(vend):
        return not any((not cod) or grupo[0].get("vendedor_ativo", True)
                       is not False for cod, grupo in vend.items())
    vazios = [g for g, vend in por_ger.items()
              if alvo.get(g) and so_inativos(vend)]
    cheios = {g: alvo[g] for g, vend in por_ger.items()
              if alvo.get(g) and not so_inativos(vend)}
    if vazios and cheios:
        sobra = sum(alvo[g] for g in vazios)
        base_ = sum(cheios.values())
        for g in vazios:
            alvo[g] = 0.0
        for g, v in cheios.items():
            alvo[g] = v + sobra * v / base_
        for linha in recortes.get("gerente") or []:
            if linha["chave"] in alvo:
                linha["meta"] = alvo[linha["chave"]]
    for ger, vendedores in por_ger.items():
        meta_g = alvo.get(ger)
        if meta_g is None:
            continue
        fixos, pesos, pisos = {}, {}, {}
        for cod, grupo in vendedores.items():
            ativo = bool(cod) and grupo[0].get("vendedor_ativo", True) \
                is not False
            if cod and not ativo:
                continue        # (03/11) inativo: sem desafio (fica 0)
            n = casa.get(_cod_vendedor(cod), 0) if ativo else 0
            fixa = meta_do_mes_de_casa(par, n) if ativo else None
            if fixa is not None:
                # (18/10) admitido no meio do mes: a meta da tabela na
                # proporcao dos dias uteis desde a admissao
                fixos[cod] = fixa * fracao.get(_cod_vendedor(cod), 1.0)
                continue
            pesos[cod] = sum(max(c["meta"], 0.0) for c in grupo)
            if ativo:
                pisos[cod] = piso
        soma_fixos = sum(fixos.values())
        if soma_fixos > meta_g and soma_fixos:
            fixos = {k: v * meta_g / soma_fixos for k, v in fixos.items()}
            soma_fixos = meta_g
        if pesos and not any(pesos.values()):
            pesos = {k: 1.0 for k in pesos}
        meta_v = dict(fixos)
        meta_v.update(_repartir(meta_g - soma_fixos, pesos, pisos))
        for cod, grupo in vendedores.items():
            alvo_v = meta_v.get(cod, 0.0)
            soma = sum(max(c["meta"], 0.0) for c in grupo)
            if soma > 0:
                fatias = [max(c["meta"], 0.0) / soma for c in grupo]
            else:
                m3m = sum(max(c["fat_m3m"], 0.0) for c in grupo)
                fatias = [(max(c["fat_m3m"], 0.0) / m3m) if m3m
                          else 1.0 / len(grupo) for c in grupo]
            for c, fatia in zip(grupo, fatias):
                antes = c["meta"]
                c["meta"] = alvo_v * fatia
                if antes > 0:
                    fator = c["meta"] / antes
                    for k, _, _ in CATEGORIAS:
                        c[f"meta_{k}"] *= fator
                else:
                    pcts_ = percentuais_do_cliente(par, c)
                    for k, _, padrao in CATEGORIAS:
                        c[f"meta_{k}"] = c["meta"] * float(
                            pcts_.get(k, padrao)) / 100.0
    for recorte, linhas in recortes.items():
        soma = defaultdict(lambda: defaultdict(float))
        for c in clientes:
            s = soma[chave_da_linha(recorte, c)]
            s["meta"] += c["meta"]
            for k, _, _ in CATEGORIAS:
                s[f"meta_{k}"] += c[f"meta_{k}"]
        for linha in linhas:
            s = soma.get(linha["chave"]) or {}
            linha["meta_rh"] = linha["meta"]
            linha["meta_calculada_rh"] = linha.get("meta_calculada",
                                                   linha["meta"])
            linha["faixa_rh"] = linha.get("faixa", "")
            linha["meta"] = float(s.get("meta", 0.0))
            linha["meta_dos_clientes"] = linha["meta"]
            for k, _, _ in CATEGORIAS:
                linha[f"meta_{k}"] = float(s.get(f"meta_{k}", 0.0))
    _meta_rh_com_teto(clientes, recortes, par, casa, fracao)


def _aplicar_metas_travadas(clientes, recortes, par, competencia) -> None:
    """(21/10, Alexandre) A meta de faturamento TRAVADA do mes (parametro
    metas_travadas): o vendedor fica com a comercial e a RH escritas; os
    clientes dele na mesma proporcao; supervisor, gerente, zona, UF,
    cidade... somam os clientes (a RH do supervisor = a soma das RH dos
    vendedores dele; a RH do gerente fica a dele)."""
    trav = (par.get("metas_travadas") or {}).get(
        normalizar_competencia(competencia) if competencia else "") or {}
    if not trav:
        return
    trav = {_cod_vendedor(k): v for k, v in trav.items()}
    por_v = defaultdict(list)
    for c in clientes:
        por_v[_cod_vendedor(c.get("cod_vendedor"))].append(c)
    rh_v = {}
    for linha in recortes.get("vendedor") or []:
        cod = _cod_vendedor(linha.get("chave"))
        if cod not in trav:
            if linha.get("chave"):
                rh_v[cod] = linha.get("meta_rh") or 0.0
            continue
        com, rh = (list(trav[cod]) + [None, None])[:2]
        com = float(com or 0.0)
        rh = float(rh if rh is not None else com)
        grupo = por_v.get(cod) or []
        soma = sum(max(c["meta"], 0.0) for c in grupo)
        for c in grupo:
            fatia = (max(c["meta"], 0.0) / soma) if soma else 1 / len(grupo)
            antes = c["meta"]
            c["meta"] = com * fatia
            for k, _, padrao in CATEGORIAS:
                c[f"meta_{k}"] = (c[f"meta_{k}"] * c["meta"] / antes
                                  if antes > 0 else c["meta"] * padrao / 100)
        linha["meta"] = linha["meta_dos_clientes"] = com
        for k, _, _ in CATEGORIAS:
            linha[f"meta_{k}"] = sum(c[f"meta_{k}"] for c in grupo)
        linha["meta_rh"] = rh
        linha["faixa_rh"] = linha["faixa"] = "meta travada no mes (21/10)"
        rh_v[cod] = rh
    sup_de = {}
    for c in clientes:
        cod = _cod_vendedor(c.get("cod_vendedor"))
        if cod and c.get("conta_na_meta", True):
            sup_de.setdefault(cod, chave_da_linha("supervisor", c))
    ajustes = par.get("ajustes") or {}
    for recorte, linhas in recortes.items():
        if recorte == "vendedor":
            continue                 # o gerente: a comercial soma; a RH fica
        soma = defaultdict(lambda: defaultdict(float))
        for c in clientes:
            s_ = soma[chave_da_linha(recorte, c)]
            s_["meta"] += c["meta"]
            for k, _, _ in CATEGORIAS:
                s_[f"meta_{k}"] += c[f"meta_{k}"]
        for linha in linhas:
            s_ = soma.get(linha["chave"]) or {}
            linha["meta"] = linha["meta_dos_clientes"] = float(
                s_.get("meta", 0.0))
            for k, _, _ in CATEGORIAS:
                linha[f"meta_{k}"] = float(s_.get(f"meta_{k}", 0.0))
            if recorte == "supervisor" and ajustes.get(
                    f"supervisor|{linha['chave']}") is None:
                linha["meta_rh"] = sum(v for cod, v in rh_v.items()
                                       if sup_de.get(cod) == linha["chave"])


def _meta_rh_com_teto(clientes, recortes, par, casa, fracao=None) -> None:
    """META RH do vendedor = a comercial dele com o teto do mes de casa
    (escrita a mao manda); a do supervisor = a soma dos vendedores dele
    que contam no mes (escrita a mao manda)."""
    teto_rh = float(par.get("teto_rh_vendedor") or 0.0)
    ajustes = par.get("ajustes") or {}
    rh_v = {}
    for linha in recortes.get("vendedor") or []:
        cod = linha["chave"]
        if not cod:
            continue
        if ajustes.get(f"vendedor|{cod}") is not None:
            rh_v[cod] = linha["meta_rh"]
            continue
        if linha.get("vendedor_ativo", True) is False:
            # (03/11, Alexandre) inativo no Planner do mes: sem meta RH
            # (nao tem RV) e sem desafio - a carteira foi para os ativos
            linha["meta_rh"] = 0.0
            linha["meta_calculada_rh"] = 0.0
            linha["meses_de_casa"] = None
            linha["faixa_rh"] = linha["faixa"] = (
                "inativo no Planner do mes: sem meta e sem RV")
            linha["no_piso"] = False
            # nem visita, positivacao e cadastro (tambem pagam RV); a
            # BASE VISITA fica, para mostrar a carteira sem dono
            for k_ in ("meta_visita", "meta_positivacao", "meta_cadastro"):
                if linha.get(k_) is not None:
                    linha[k_] = 0
            rh_v[cod] = 0.0
            continue
        n = casa.get(_cod_vendedor(cod), 0)
        fixa = meta_do_mes_de_casa(par, n) if linha.get(
            "vendedor_ativo", True) else None
        if fixa is not None:
            fixa *= (fracao or {}).get(_cod_vendedor(cod), 1.0)
        teto = fixa if fixa is not None else teto_rh
        linha["meta_rh"] = min(linha["meta"], teto) if teto else linha["meta"]
        linha["meses_de_casa"] = n or None
        linha["faixa_rh"] = linha["faixa"] = (
            (f"{n}o mes de casa: meta da tabela" + (
                f" x {(fracao or {})[_cod_vendedor(cod)] * 100:.0f}% (dias "
                f"uteis desde a admissao)" if (fracao or {}).get(
                    _cod_vendedor(cod), 1.0) < 1.0 else ""))
            if fixa is not None else
            (f"comercial com teto RH de {teto:,.0f}".replace(",", ".")
             if teto and linha["meta"] > teto + 0.5 else "igual a comercial"))
        linha["no_piso"] = False
        rh_v[cod] = linha["meta_rh"]
    sup_de = {}
    for c in clientes:
        cod = _texto(c.get("cod_vendedor"))
        if cod and c.get("conta_na_meta", True):
            sup_de.setdefault(cod, chave_da_linha("supervisor", c))
    for linha in recortes.get("supervisor") or []:
        if ajustes.get(f"supervisor|{linha['chave']}") is not None:
            continue
        linha["meta_rh"] = sum(v for cod, v in rh_v.items()
                               if sup_de.get(cod) == linha["chave"])


# --------------------------------------------------------------------------
# A META POR FAMILIA DA PECA
# --------------------------------------------------------------------------
# meta da familia no cliente = meta comercial do cliente x o peso da
# familia no que ELE comprou nos 3 meses antes do mes da meta (o M3M).
# Cliente sem compra na janela usa o mix do SEGMENTO dele; segmento sem
# compra nenhuma, o mix da BAP inteira. Assim a soma das familias de
# qualquer recorte e a meta comercial daquele recorte.
def janela_m3m(competencia: str, n: int = MESES_M3M) -> list:
    comp = normalizar_competencia(competencia)
    if not comp:
        return []
    ano, mes = int(comp[:4]), int(comp[5:])
    saida = []
    for _ in range(n):
        mes -= 1
        if not mes:
            ano, mes = ano - 1, 12
        saida.append(f"{ano}-{mes:02d}")
    return saida


def mix_de_familia(caminho_tabela, competencia: str) -> dict:
    """{cod_cliente: {familia: venda}} nos 3 meses antes da competencia
    (so VND/VEA: devolucao nao entra no peso). Guardado em
    RELATORIOS/_CACHE_RELATORIOS - a TABELA_BAP so e lida de novo quando
    muda."""
    return _mix_m3m(caminho_tabela, competencia).get("familia") or {}


def mix_de_categoria(caminho_tabela, competencia: str) -> dict:
    """{cod_cliente: {categoria BAP: venda}} - o mesmo, por categoria."""
    return _mix_m3m(caminho_tabela, competencia).get("categoria") or {}


def _mix_m3m(caminho_tabela, competencia: str) -> dict:
    """{"familia": mix, "categoria": mix} numa leitura so da ftPedidos."""
    import os as _os                                   # noqa: PLC0415
    import pickle as _pickle                           # noqa: PLC0415
    caminho = Path(caminho_tabela)
    meses = set(janela_m3m(competencia))
    if not caminho.exists() or not meses:
        return {}
    csv_cat = (achar_csv_de_categorias(caminho.parent.parent)
               or achar_csv_de_categorias(caminho.parent))
    st = caminho.stat()
    st_c = csv_cat.stat().st_mtime_ns if csv_cat else 0
    # (15/10) a classificacao do CATALOGO BAP 2026 (ESTOQUE_BAP / base v8)
    try:
        import catalogo_bap as _cb                     # noqa: PLC0415
        raiz_cat = (caminho.parent.parent
                    if caminho.parent.name.upper() == RELATORIOS_SUB.upper()
                    else caminho.parent)
        catalogo = _cb.Catalogo(raiz_cat, caminho.parent / "ESTOQUE_BAP.xlsx")
        assin_cat = "|".join(
            f"{a.stat().st_mtime_ns}" for a in (catalogo.arq_base,
                                               catalogo.arq_estoque) if a)
        # (19/10) a regra de familia do catalogo (ARREFECIMENTO DO MOTOR)
        assin_cat += "|" + getattr(_cb, "VERSAO_REGRAS", "")
    except Exception:                                  # noqa: BLE001
        catalogo, assin_cat = None, ""
    assin = (f"{st.st_mtime_ns}:{st.st_size}:{st_c}:{competencia}:v3:"
             f"{assin_cat}")
    pasta = caminho.parent / "_CACHE_RELATORIOS"
    arq = pasta / f"mix_familia_{normalizar_competencia(competencia)}.pkl"
    try:
        with open(arq, "rb") as f:
            guardado = _pickle.load(f)
        if guardado.get("assinatura") == assin:
            return guardado["mix"]
    except Exception:                                  # noqa: BLE001
        pass
    mix: dict = {}
    mix_cat: dict = {}
    mix_sis: dict = {}
    mix_lin: dict = {}
    classe_de: dict = {}
    crua = ler_categoria_crua(csv_cat)
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except Exception:                                  # noqa: BLE001
        return {}
    try:
        if "ftPedidos" not in wb.sheetnames:
            return {}
        descricoes = fam.descricoes_da_tabela(wb)
        forn_de = {}
        if "ProdutosBAP" in wb.sheetnames:
            it_p = wb["ProdutosBAP"].iter_rows(values_only=True)
            cab_p = [_chave(c) for c in next(it_p, [])]
            i_pf = (cab_p.index(_chave("FORNECEDOR"))
                    if _chave("FORNECEDOR") in cab_p else None)
            i_pc = next((cab_p.index(_chave(n)) for n in
                         ("Cód. Produto", "Cod. Produto", "COD_PRODUTO")
                         if _chave(n) in cab_p), None)
            if i_pf is not None and i_pc is not None:
                for r in it_p:
                    if r and len(r) > max(i_pf, i_pc) and r[i_pc]:
                        forn_de[_texto(r[i_pc]).upper()] = _texto(r[i_pf])
        crua_up = {k.upper(): v for k, v in crua.items()}
        categoria_de = {}
        it = wb["ftPedidos"].iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]

        def coluna(*nomes):
            for n in nomes:
                if _chave(n) in cab:
                    return cab.index(_chave(n))
            return None
        i_cli, i_tipo = coluna("D2_CLIENTE"), coluna("TIPO")
        i_valor = coluna("VALOR TOTAL", "VALOR_TOTAL")
        i_nf, i_cod = coluna("DATA_NF"), coluna("D2_COD")
        if None in (i_cli, i_tipo, i_valor, i_nf):
            return {}
        familia_de = {}
        for r in it:
            if _texto(r[i_tipo]).upper() not in TIPOS_VENDA:
                continue
            data = _data(r[i_nf])
            if data is None or _mes_de(data) not in meses:
                continue
            cod = _texto(r[i_cli])
            if not cod:
                continue
            valor = r[i_valor]
            if not isinstance(valor, (int, float)):
                valor = _numero(valor)
            prod = (_texto(r[i_cod]) if i_cod is not None else "").upper()
            cl = classe_de.get(prod)
            if cl is None:
                antiga = categoria_bap(crua_up.get(prod, ""),
                                       forn_de.get(prod, ""),
                                       descricoes.get(prod, ""))
                if catalogo is not None:
                    cl = catalogo.de(prod, antiga, descricoes.get(prod, ""))
                else:
                    cl = {"FAMILIA": fam.classificar(
                        descricoes.get(prod, ""))[0], "CATEGORIA": antiga,
                        "SISTEMA": "OUTROS", "LINHA": "OUTROS"}
                classe_de[prod] = cl
            for alvo, campo in ((mix, "FAMILIA"), (mix_cat, "CATEGORIA"),
                                (mix_sis, "SISTEMA"), (mix_lin, "LINHA")):
                g = cl.get(campo) or "OUTROS"
                dest = alvo.setdefault(cod, {})
                dest[g] = dest.get(g, 0.0) + valor
    finally:
        wb.close()
    saida = {"familia": mix, "categoria": mix_cat, "sistema": mix_sis,
             "linha": mix_lin}
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(f".{_os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            _pickle.dump({"assinatura": assin, "mix": saida}, f)
        _os.replace(tmp, arq)
    except OSError:
        pass
    return saida


def _pesos(dic: dict) -> dict:
    tot = sum(v for v in dic.values() if v > 0)
    return {k: v / tot for k, v in dic.items() if v > 0} if tot else {}


def _metas_por_familia(clientes: list, mix: dict) -> list:
    """Poe c["meta_familia"] em cada cliente e devolve uma linha por
    familia: {familia, meta, m3m, clientes_m3m}."""
    return _metas_por_mix(clientes, mix, "meta_familia",
                          {n: i for i, n in enumerate(fam.ORDEM_FAMILIA)})


def categorias_do_catalogo() -> tuple:
    """(15/10) As CATEGORIAS do Catalogo BAP 2026 (PEÇAS, BATERIAS...)."""
    try:
        import catalogo_bap as _cb                     # noqa: PLC0415
        return tuple(c for c in _cb.ORDEM_CATEGORIA if c != "OUTROS")
    except Exception:                                  # noqa: BLE001
        return CATEGORIAS_BAP


def _metas_por_categoria(clientes: list, mix: dict) -> list:
    """O mesmo por CATEGORIA (Catalogo BAP 2026): c["meta_categoria"]; uma
    linha por categoria (todas sempre, na ordem fixa; "familia" = a
    categoria)."""
    cats = categorias_do_catalogo()
    ordem = {n: i for i, n in enumerate(cats + (OUTRA_CATEGORIA,))}
    linhas = _metas_por_mix(clientes, mix, "meta_categoria", ordem)
    tem = {x["familia"] for x in linhas}
    linhas += [{"familia": c_, "meta": 0.0, "m3m": 0.0, "clientes_m3m": 0}
               for c_ in cats if c_ not in tem]
    return sorted(linhas, key=lambda x: (-x["meta"],
                                         ordem.get(x["familia"], 99)))


def _metas_por_grupo(clientes: list, mix: dict, campo: str, ordem=()) -> list:
    """(15/10) O mesmo por SISTEMA (c["meta_sistema"]) ou LINHA
    (c["meta_linha"]) do Catalogo BAP 2026."""
    return _metas_por_mix(clientes, mix, campo,
                          {n: i for i, n in enumerate(ordem)})


def _metas_por_mix(clientes: list, mix: dict, campo: str, ordem: dict
                   ) -> list:
    """A meta comercial do cliente aberta pelo peso de cada grupo (familia
    ou categoria) no M3M dele - sem M3M, o do segmento; sem segmento, o da
    BAP. A soma dos grupos fecha com a meta do cliente."""
    seg_soma = defaultdict(lambda: defaultdict(float))
    bap = defaultdict(float)
    for c in clientes:
        for f, v in (mix.get(c["cod_cliente"]) or {}).items():
            if v > 0:
                seg_soma[c.get("segmento") or SEM_SEGMENTO][f] += v
                bap[f] += v
    seg_pesos = {s: _pesos(d) for s, d in seg_soma.items()}
    bap_pesos = _pesos(bap)
    linhas = {}
    vistos = set()
    for c in clientes:
        proprio = mix.get(c["cod_cliente"]) or {}
        pesos = _pesos(proprio)
        if pesos:
            de_onde = "cliente"
        else:
            pesos = (seg_pesos.get(c.get("segmento") or SEM_SEGMENTO)
                     or bap_pesos)
            de_onde = "segmento" if pesos is not bap_pesos else "bap"
        c[campo] = {f: c["meta"] * p for f, p in pesos.items()}
        c[campo.replace("meta_", "") + "_de_onde"] = de_onde if pesos else ""
        for f, v in c[campo].items():
            ln = linhas.setdefault(f, {"familia": f, "meta": 0.0, "m3m": 0.0,
                                       "clientes_m3m": 0})
            ln["meta"] += v
        if c["cod_cliente"] not in vistos:
            vistos.add(c["cod_cliente"])
            for f, v in proprio.items():
                if v > 0:
                    ln = linhas.setdefault(f, {"familia": f, "meta": 0.0,
                                               "m3m": 0.0, "clientes_m3m": 0})
                    ln["m3m"] += v / MESES_M3M
                    ln["clientes_m3m"] += 1
    return sorted(linhas.values(),
                  key=lambda x: (-x["meta"], ordem.get(x["familia"], 99)))


def metas_de_familia_por(clientes: list, recorte: str,
                         campo: str = "meta_familia") -> dict:
    """{chave da linha: {familia: meta}} - a meta por familia (ou, com
    campo="meta_categoria", por categoria) de cada linha de um recorte."""
    saida = defaultdict(lambda: defaultdict(float))
    for c in clientes:
        k = chave_da_linha(recorte, c)
        for f, v in (c.get(campo) or {}).items():
            saida[k][f] += v
    return {k: dict(v) for k, v in saida.items()}


# --------------------------------------------------------------------------
# ajuste a mao
# --------------------------------------------------------------------------
# AS OUTRAS METAS ESCRITAS A MAO. A de faturamento continua em "ajustes"
# (o arquivo de quem ja usava nao muda); visita, positivacao e cadastro
# ficam em "ajustes_ind" = {campo: {"recorte|chave": valor}}.
#   VISITA e POSITIVACAO sao soma de cliente: o valor escrito se reparte
#     entre os clientes da linha (na proporcao de antes) e sobe sozinho.
#   CADASTRO e meta de PESSOA: a do vendedor soma no supervisor e no
#     gerente; zona, UF, cidade... nao tem meta de cadastro.
CAMPOS_COM_AJUSTE = ("meta", "meta_visita", "meta_positivacao",
                     "meta_cadastro")
AJUSTE_SO_EM_PESSOA = {"meta_cadastro": ("gerente", "supervisor", "vendedor")}


def marcar_ajuste(par: dict, recorte: str, chave: str, valor: float,
                  campo: str = "meta") -> None:
    """Guarda 'esta linha vale X', escrito a mao."""
    if campo == "meta":
        par.setdefault("ajustes", {})[f"{recorte}|{chave}"] = float(valor)
    else:
        par.setdefault("ajustes_ind", {}).setdefault(campo, {})[
            f"{recorte}|{chave}"] = float(valor)


def tirar_ajuste(par: dict, recorte: str, chave: str,
                 campo: str = "meta") -> None:
    if campo == "meta":
        par.get("ajustes", {}).pop(f"{recorte}|{chave}", None)
    else:
        ((par.get("ajustes_ind") or {}).get(campo) or {}).pop(
            f"{recorte}|{chave}", None)


def ajuste_de(par: dict, campo: str, recorte: str, chave: str):
    """O valor escrito a mao para aquela meta daquela linha, ou None."""
    if campo == "meta":
        v = (par.get("ajustes") or {}).get(f"{recorte}|{chave}")
    else:
        v = ((par.get("ajustes_ind") or {}).get(campo) or {}).get(
            f"{recorte}|{chave}")
    return None if v is None else float(v)


def _aplicar_travadas_ind(clientes: list, par: dict, competencia) -> None:
    """(26/10, Alexandre) "Nao posso mudar a meta no meio do mes": a meta de
    VISITA e a de POSITIVACAO do vendedor travadas no mes (parametro
    metas_travadas_ind). O valor do vendedor se reparte entre os clientes
    dele na proporcao de antes; supervisor, gerente e territorios somam."""
    trav = (par.get("metas_travadas_ind") or {}).get(
        normalizar_competencia(competencia) if competencia else "") or {}
    if not trav:
        return
    por_v = defaultdict(list)
    for c in clientes:
        por_v[_cod_vendedor(c.get("cod_vendedor"))].append(c)
    for campo in ("meta_visita", "meta_positivacao"):
        for cod, valor in (trav.get(campo) or {}).items():
            grupo = por_v.get(_cod_vendedor(cod)) or []
            if not grupo:
                continue
            antes = sum(c.get(campo) or 0.0 for c in grupo)
            for c in grupo:
                fatia = ((c.get(campo) or 0.0) / antes) if antes \
                    else 1.0 / len(grupo)
                c[campo] = float(valor) * fatia


def _aplicar_ajustes_ind(clientes: list, par: dict) -> None:
    """Visita e positivacao escritas a mao: repartidas entre os clientes."""
    ordem = {r: i for i, r in enumerate(RECORTES)}
    for campo in ("meta_visita", "meta_positivacao"):
        do_campo = (par.get("ajustes_ind") or {}).get(campo) or {}
        itens = []
        for chave_completa, valor in do_campo.items():
            recorte, _, chave = str(chave_completa).partition("|")
            if recorte in ordem:
                itens.append((ordem[recorte], recorte, chave, float(valor)))
        for _, recorte, chave, valor in sorted(itens):
            grupo = [c for c in clientes if chave_da_linha(recorte, c) == chave]
            if not grupo:
                continue
            antes = sum(c[campo] for c in grupo)
            for c in grupo:
                fatia = (c[campo] / antes) if antes else (1.0 / len(grupo))
                c[campo] = valor * fatia
                c["ajustado"] = True


def _aplicar_ajustes(clientes: list, par: dict) -> None:
    """
    Poe de pe os ajustes feitos a mao. Ajustar uma linha de VENDEDOR (ou de
    zona, cidade, UF...) reparte o novo valor entre os clientes dela na
    mesma proporcao de antes - assim "a meta do vendedor e a soma dos
    clientes" continua verdade, e as categorias acompanham.

    A ordem importa: do recorte mais amplo para o mais estreito, para que
    um ajuste no cliente mande mais que um ajuste no gerente.
    """
    for c in clientes:
        c["ajustado"] = False
    ajustes = par.get("ajustes") or {}
    if not ajustes:
        return
    ordem = {r: i for i, r in enumerate(RECORTES)}
    itens = []
    for chave_completa, valor in ajustes.items():
        recorte, _, chave = str(chave_completa).partition("|")
        if recorte in ordem:
            itens.append((ordem[recorte], recorte, chave, float(valor)))
    for _, recorte, chave, valor in sorted(itens):
        grupo = [c for c in clientes if chave_da_linha(recorte, c) == chave]
        if not grupo:
            continue
        antes = sum(c["meta"] for c in grupo)
        for c in grupo:
            fatia = (c["meta"] / antes) if antes else (1.0 / len(grupo))
            c["meta"] = valor * fatia
            pcts = percentuais_do_cliente(par, c)
            for k, _, _ in CATEGORIAS:
                c[f"meta_{k}"] = c["meta"] * float(pcts.get(k, 0.0)) / 100.0
            c["ajustado"] = True


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------
COLUNAS_EXCEL = [
    # A META VEM PRIMEIRO E JUNTA: quem abre o arquivo quer ver a meta,
    # nao procurar a coluna dela no meio do resto.
    ("RECORTE", "recorte", 14, None),
    ("CODIGO", "codigo", 14, None),
    ("NOME", "nome", 34, None),
    ("BASE VISITA", "base_visita", 13, None),
    ("META FAT. TT R$", "meta", 18, "#,##0.00"),
    # a META RH (o modelo de cada nivel): a que paga a RV
    ("META FAT. TT RH R$", "meta_rh", 20, "#,##0.00"),
    ("META PECAS R$", "meta_pecas", 17, "#,##0.00"),
    ("META LUBRIF. R$", "meta_lubrificante", 17, "#,##0.00"),
    ("META BATERIA R$", "meta_bateria", 17, "#,##0.00"),
    ("META PNEU R$", "meta_pneu", 16, "#,##0.00"),
    ("META VISITA", "meta_visita_int", 13, "#,##0"),
    ("META POSITIVACAO", "meta_positivacao_int", 18, "#,##0"),
    ("META CAD. COM COMPRA", "meta_cadastro_int", 21, "#,##0"),
    # dai para a direita, o que explica de onde a meta veio
    ("LINHA", "rotulo", 42, None),
    ("BASE TOTAL", "base_carteira", 13, None),
    ("EXCEDENTES NO SABADO", "excedentes", 21, None),
    ("VISITAS NA ROTA", "visitas", 16, None),
    ("VISITAS NO DEPOSITO", "visitas_deposito", 20, None),
    ("VISITAS NO MES (TOTAL)", "visitas_total", 23, None),
    ("BASE POSITIVACAO", "positivacao_base", 17, None),
    ("FAT M3M R$", "fat_m3m", 16, "#,##0.00"),
    ("FAT M3M ANTERIOR R$", "fat_m3m_anterior", 20, "#,##0.00"),
    ("SOMA DA META DOS CLIENTES R$", "meta_dos_clientes", 28, "#,##0.00"),
    ("DE ONDE VEIO A META RH", "faixa", 30, None),
    ("AJUSTADA A MAO", "ajustada", 15, None),
    # vendedor e zona: NAO quer dizer que a meta dele nao sobe para o
    # supervisor NESTE mes (o realizado sobe do mesmo jeito)
    ("CONTA NA META DO SUP.", "conta_na_meta_txt", 22, None),
]


def _arredondar_metas(linha: dict) -> dict:
    """
    META VISITA e META POSITIVACAO sao PESSOAS E VISITAS - coisa que se
    conta, nao que se divide. Entao vao para o Excel e para a tela como
    numero inteiro, sem casa decimal. Arredonda para cima: pedir 89,4
    visitas e pedir 90.
    """
    copia = dict(linha)
    # so vendedor e zona respondem essa pergunta - nos outros niveis ela
    # nao quer dizer nada, e vazio e melhor que um SIM que confunde
    copia["conta_na_meta_txt"] = (
        ("SIM" if linha.get("conta_na_meta", True) else "NAO")
        if linha.get("recorte") in NIVEIS_DO_CORTE else "")
    for origem, destino in (("meta_visita", "meta_visita_int"),
                            ("meta_positivacao", "meta_positivacao_int"),
                            ("meta_cadastro", "meta_cadastro_int")):
        bruto = linha.get(origem)
        if bruto is None:          # None = a linha nao TEM essa meta
            copia[destino] = None  # (zona nao visita) - e vazio, nao zero
            continue
        try:
            copia[destino] = int(math.ceil(float(bruto)))
        except (TypeError, ValueError):
            copia[destino] = 0
    return copia


def gravar_excel(resultado: dict, par: dict, caminho) -> Path:
    """Uma aba por recorte, mais a aba PARAMETROS com o que gerou a meta."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    wb = Workbook()
    wb.remove(wb.active)
    cabecalho = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)

    for recorte in RECORTES:
        ws = wb.create_sheet(TITULO_DO_RECORTE[recorte][:31])
        ws.append([t for t, _, _, _ in COLUNAS_EXCEL])
        for i, (_, _, largura, _) in enumerate(COLUNAS_EXCEL, start=1):
            ws.cell(1, i).fill = cabecalho
            ws.cell(1, i).font = branco
            ws.cell(1, i).alignment = Alignment(horizontal="center",
                                                wrap_text=True)
            ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
        for linha in resultado["recortes"][recorte]:
            linha = _arredondar_metas(linha)
            ws.append([("SIM" if linha.get(k) else "")
                       if k == "ajustada" else
                       (TITULO_DO_RECORTE[recorte] if k == "recorte"
                        else linha.get(k))
                       for _, k, _, _ in COLUNAS_EXCEL])
        total = _arredondar_metas(resultado.get("totais", {}).get(recorte)
                                  or resultado["total"])
        ws.append([("TOTAL" if k == "recorte" else
                    ("BAP INTEIRA" if k == "rotulo" else
                     ("" if k == "ajustada" else total.get(k))))
                   for _, k, _, _ in COLUNAS_EXCEL])
        for j, (_, _, _, formato) in enumerate(COLUNAS_EXCEL, start=1):
            if formato:
                for linha_n in range(2, ws.max_row + 1):
                    ws.cell(linha_n, j).number_format = formato
        for j in range(1, len(COLUNAS_EXCEL) + 1):
            ws.cell(ws.max_row, j).font = Font(bold=True, size=9)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{ws.cell(1, len(COLUNAS_EXCEL)).column_letter}" \
                             f"{ws.max_row - 1}"

    ws = wb.create_sheet("PARAMETROS")
    ws.append(["PARAMETRO", "VALOR"])
    ws.cell(1, 1).fill = cabecalho
    ws.cell(1, 1).font = branco
    ws.cell(1, 2).fill = cabecalho
    ws.cell(1, 2).font = branco
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 26
    ws.append(["PLANNER usado", str(resultado.get("arquivo") or "")])
    ws.append(["Mes da rota", resultado.get("mes", "")])
    ws.append(["Como a meta e calculada",
               "M3M atual x M3M anterior no cliente e no vendedor; "
               "rateio da META GERAL na UF e no gerente"])
    ws.append(["META GERAL (R$) - so no modo rateio",
               float(par.get("meta_geral") or 0)])
    for chave, rotulo in (("piso_cliente", "CLIENTE"),
                          ("piso_vendedor", "VENDEDOR"),
                          ("piso_zona", "ZONA")):
        ws.append([f"Piso por {rotulo} (R$)", float(par.get(chave) or 0)])
    ws.append(["O piso do cliente vale so para quem ja comprou",
               "SIM" if par.get("piso_so_com_faturamento", True) else "NAO"])
    for i, faixa in enumerate(par.get("faixas") or FAIXAS_PADRAO, start=1):
        ws.append([f"Faixa {i}: base {faixa.get('base')}",
                   f"+{faixa.get('acrescimo')}%"])
    ws.append(["META VISITA (% das visitas)", par.get("pct_visita")])
    ws.append(["POSITIVACAO (% dos clientes)", par.get("pct_positivacao")])
    for chave, rotulo, _ in CATEGORIAS:
        ws.append([f"{rotulo} (% da meta de faturamento)",
                   (par.get("categorias") or {}).get(chave)])
    for uf, pcts in sorted((par.get("por_uf") or {}).items()):
        ws.append([f"UF {uf}", json.dumps(pcts, ensure_ascii=False)])
    for zona, pcts in sorted((par.get("por_zona") or {}).items()):
        ws.append([f"ZONA {zona}", json.dumps(pcts, ensure_ascii=False)])
    for chave, valor in sorted((par.get("ajustes") or {}).items()):
        ws.append([f"AJUSTE A MAO {chave}", valor])

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


ARQUIVO_ACOMPANHAMENTO = "ACOMPANHAMENTO_META_BAP.xlsx"
ABA_ANALITICO = "ANALITICO"
# a subpasta onde o arquivo mora - a mesma que o resto do BAP TOOLS usa
try:
    from pastas_bap import RELATORIOS as RELATORIOS_SUB
    from pastas_bap import VISITAS as VISITAS_SUB
except ImportError:                                   # rodando solto
    RELATORIOS_SUB = "RELATORIOS"
    VISITAS_SUB = "RELATORIOS/Visitas"


def marca_do_mes(competencia: str = "") -> str:
    """'2026-09' -> '202609'. E o nome da aba daquele mes."""
    boa = normalizar_competencia(competencia)
    return boa.replace("-", "") if boa else dt.date.today().strftime("%Y%m")


def nome_do_arquivo(competencia: str = "") -> str:
    """O arquivo do RH, do mes: META_BAP_AAAAMM.xlsx."""
    return f"META_BAP_{marca_do_mes(competencia)}.xlsx"


NOMES_DOS_MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
                   "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def rotulo_do_mes(competencia: str) -> str:
    """'2026-09' -> 'SET/26'. E o que vai no cabecalho do painel."""
    boa = normalizar_competencia(competencia)
    if not boa:
        return _texto(competencia)
    ano, mes = boa.split("-")
    return f"{NOMES_DOS_MESES[int(mes) - 1]}/{ano[2:]}"


def meses_do_ano(ano: int) -> list:
    """Os doze meses daquele ano, em AAAA-MM."""
    return [f"{int(ano):04d}-{m:02d}" for m in range(1, 13)]


def meses_por_perto(antes: int = 12, depois: int = 3, hoje=None) -> list:
    """
    A lista que a caixinha 'MES DA META' oferece: os 12 meses passados, o
    mes corrente e os 3 seguintes, sempre em AAAA-MM. E so uma sugestao -
    o campo aceita qualquer mes digitado.
    """
    base = hoje or dt.date.today()
    saida = []
    for passo in range(-antes, depois + 1):
        mes = base.month - 1 + passo
        ano = base.year + mes // 12
        saida.append(f"{ano:04d}-{mes % 12 + 1:02d}")
    return saida


def meses_de(competencia: str, quantos: int = 24) -> list:
    """A lista de AAAA-MM para o seletor de mes da tela."""
    base = competencia if re.fullmatch(r"\d{4}-\d{2}", competencia or "") \
        else dt.date.today().strftime("%Y-%m")
    ano, mes = (int(x) for x in base.split("-"))
    saida = []
    for passo in range(-quantos // 2, quantos // 2 + 1):
        total = (ano * 12 + mes - 1) + passo
        saida.append(f"{total // 12:04d}-{total % 12 + 1:02d}")
    return saida


# ==========================================================================
# O ACOMPANHAMENTO DA META - o que foi realizado, contra o que foi pedido
# ==========================================================================
"""
DE ONDE VEM O REALIZADO
  Da TABELA_BAP, aba ftPedidos - a mesma que a automacao atualiza todo dia.
  Ela tem uma linha por item de nota, com o cliente (D2_CLIENTE), o vendedor
  da venda (C5_VEND1), o produto (ID_PRODUTO), a data (DATA_NF / DATA_DEV),
  o TIPO e o VALOR TOTAL.

      TIPO = VND / VEA ... venda
      TIPO = DEV ......... devolucao (o valor ja vem negativo)
      TIPO = TRF / EXC ... transferencia e exclusao: NAO sao venda e ficam
                           de fora

  FATURAMENTO LIQUIDO = venda + devolucao (a devolucao ja e negativa).

COMO O REALIZADO ENCONTRA A META - DUAS LEITURAS, LADO A LADO
  O mesmo mes e lido de dois jeitos, e as duas colunas aparecem juntas:

    FAT TOTAL ............. o que a PESSOA VENDEU, pelo codigo do vendedor
                            na nota (C5_VEND1). O supervisor e a soma dos
                            vendedores dele; o gerente, a soma dos
                            supervisores.
    FATURAMENTO CARTEIRA .. o que os CLIENTES dela faturaram, nao importa
                            quem bateu a nota. E a leitura antiga.

  Vale so para os recortes de PESSOA - vendedor, supervisor e gerente. Em
  zona, UF, cidade, bairro e cliente nao existe "quem vendeu" que suba, e
  as duas colunas sao o mesmo numero.

  ISTO TEM CONSEQUENCIA, e e de proposito: o vendedor passa a ser medido
  pelo que ele vendeu, inclusive em cliente de outro. Quem so registrou
  devolucao no proprio codigo fica com FAT TOTAL negativo, mesmo com a
  carteira faturando bem - e a coluna do lado mostra isso.

  Os dois totais fecham: as duas leituras percorrem as MESMAS linhas da
  ftPedidos. Venda em codigo que o PLANNER nao conhece ganha linha propria
  no recorte VENDEDOR, com meta zero, em vez de sumir.

  Cliente que faturou e nao esta no PLANNER aparece numa linha (FORA DO
  PLANNER): ele nao tem meta, mas o faturamento dele nao some.

  A ftPedidos identifica o cliente so pelo CODIGO, sem a loja. Entao o
  acompanhamento junta as lojas do mesmo codigo dos dois lados - meta e
  realizado - para a conta bater.
"""

TIPOS_VENDA = ("VND", "VEA")
TIPO_DEVOLUCAO = "DEV"

# Onde vai parar a venda cuja nota nao diz quem vendeu. Ela NAO e jogada
# fora: sem esta gaveta, a soma por vendedor deixaria de fechar com a soma
# por cliente e ninguem saberia por que.
SEM_VENDEDOR_NA_NOTA = "(SEM VENDEDOR NA NOTA)"


def _cod_vendedor(valor) -> str:
    """
    O codigo do vendedor do jeito que o cadastro guarda: seis digitos.
    A ftPedidos as vezes traz '15' onde o PLANNER tem '000015' - sem
    igualar os dois, o mesmo vendedor viraria duas pessoas.
    """
    cod = _texto(valor)
    if not cod:
        return SEM_VENDEDOR_NA_NOTA
    return cod.zfill(6) if cod.isdigit() else cod

# ==========================================================================
# A CATEGORIA DE CADA PRODUTO
# ==========================================================================
# A TABELA_BAP nao sabe o que e bateria nem o que e pneu: o unico corte
# que ela tem e o FORNECEDOR, que separa lubrificante e mais nada.
#
# Quem sabe e o CATEGORIAS_PRODUTO.csv - a exportacao "Estoque Total" do
# sistema, com quatro colunas: Forn., Cod. Prod., Produto e CATEGORIA.
# Basta deixar o arquivo na pasta (ou dentro da RELATORIOS) que o
# acompanhamento passa a medir o realizado por categoria de verdade.
#
# Os nomes que o sistema usa, e para onde eles vao na meta:
CATEGORIA_DO_SISTEMA = {
    "PECAS LINHA LEVE": "pecas",
    "PECAS LINHA PESADA": "pecas",
    "PECAS": "pecas",
    "OLEO": "lubrificante",
    "LUBRIFICANTE": "lubrificante",
    "BATERIA": "bateria",
    "PNEU": "pneu",
}

# os nomes que o arquivo pode ter na pasta - o primeiro que existir manda
NOMES_DO_CSV = ("CATEGORIAS_PRODUTO.csv", "Estoque Total.csv",
                "ESTOQUE_TOTAL.csv", "Estoque_Total.csv")

# ultimo recurso, quando nao ha o CSV: o que da para deduzir do
# FORNECEDOR da ProdutosBAP
CATEGORIA_POR_FORNECEDOR = {
    "BAP LUB": "lubrificante",
    "BAP FILTROS": "pecas",
    "BAP MOTOS": "pecas",
    "BAP": "pecas",
}
CATEGORIA_PADRAO = "pecas"


def _limpar_categoria(texto: str) -> str:
    """'PEÇAS - LINHA LEVE' -> 'PECAS LINHA LEVE'."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = t.encode("ascii", "ignore").decode().upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def achar_csv_de_categorias(raiz) -> Path | None:
    """Onde esta o CATEGORIAS_PRODUTO.csv: na pasta, ou na RELATORIOS."""
    raiz = Path(raiz)
    for pasta in (raiz, raiz / "RELATORIOS"):
        for nome in NOMES_DO_CSV:
            caminho = pasta / nome
            if caminho.exists():
                return caminho
    return None


def ler_categorias_de_produto(caminho) -> dict:
    """
    {codigo do produto -> categoria da meta}, lido do CATEGORIAS_PRODUTO.csv.

    O arquivo sai do sistema com virgula e cabecalho em portugues; a
    leitura aceita virgula ou ponto e virgula e ignora o BOM do Excel.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    import csv as _csv
    saida = {}
    try:
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            separador = ";" if amostra.count(";") > amostra.count(",") else ","
            for linha in _csv.DictReader(f, delimiter=separador):
                limpo = {_limpar_categoria(k): v for k, v in linha.items() if k}
                cod = _texto(limpo.get("COD PROD") or limpo.get("CODIGO")
                             or limpo.get("COD PRODUTO"))
                categoria = CATEGORIA_DO_SISTEMA.get(
                    _limpar_categoria(limpo.get("CATEGORIA")))
                if cod and categoria:
                    saida[cod] = categoria
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return saida


# ==========================================================================
# A CATEGORIA BAP (a do Farol: LINHA LEVE, PESADA, MOTO, PNEU, BATERIA,
# LUBRIFICANTES) - mais aberta que a da meta de categoria (pecas/bateria/
# lubrificante/pneu). Regra, nesta ordem:
#   1) o CATEGORIAS_PRODUTO.csv diz PNEU, BATERIA ou OLEO -> PNEU,
#      BATERIA, LUBRIFICANTES (pneu de moto e PNEU, oleo 4T e LUBRIF.);
#   2) fornecedor BAP MOTOS (7980) -> LINHA MOTO;
#   3) o CSV diz LINHA PESADA -> LINHA PESADA; LINHA LEVE -> LINHA LEVE;
#   4) sem o CSV: BAP LUB -> LUBRIFICANTES; descricao BATERIA/PNEU;
#      fornecedor BAP (pecas, filtros) -> LINHA LEVE; o resto -> OUTROS
#      (banner, brinde: o que nao e produto BAP).
# ==========================================================================
CATEGORIAS_BAP = ("LINHA LEVE", "LINHA PESADA", "LINHA MOTO", "PNEU",
                  "BATERIA", "LUBRIFICANTES")
OUTRA_CATEGORIA = "OUTROS"


def ler_categoria_crua(caminho) -> dict:
    """{codigo do produto -> categoria do sistema, limpa} do CSV
    ('PECAS LINHA LEVE', 'OLEO', 'PNEU'...)."""
    caminho = Path(caminho) if caminho else None
    if not caminho or not caminho.exists():
        return {}
    import csv as _csv                                    # noqa: PLC0415
    saida = {}
    try:
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            separador = ";" if amostra.count(";") > amostra.count(",") else ","
            for linha in _csv.DictReader(f, delimiter=separador):
                limpo = {_limpar_categoria(k): v for k, v in linha.items() if k}
                cod = _texto(limpo.get("COD PROD") or limpo.get("CODIGO")
                             or limpo.get("COD PRODUTO"))
                cat = _limpar_categoria(limpo.get("CATEGORIA"))
                if cod and cat:
                    saida[cod] = cat
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return saida


def categoria_bap(crua: str = "", fornecedor: str = "",
                  descricao: str = "") -> str:
    """A categoria BAP de um produto (ver a regra acima)."""
    crua = _limpar_categoria(crua)
    forn = _limpar_categoria(fornecedor)
    desc = _limpar_categoria(descricao)
    if crua in ("PNEU", "BATERIA"):
        return crua
    if crua in ("OLEO", "LUBRIFICANTE", "LUBRIFICANTES"):
        return "LUBRIFICANTES"
    if "BAP MOTOS" in forn or forn.startswith("7980"):
        return "LINHA MOTO"
    if "PESADA" in crua:
        return "LINHA PESADA"
    if crua:
        return "LINHA LEVE"
    if "BAP LUB" in forn:
        return "LUBRIFICANTES"
    if desc.startswith("BATERIA"):
        return "BATERIA"
    if desc.startswith("PNEU"):
        return "PNEU"
    if forn:
        return "LINHA LEVE"
    return OUTRA_CATEGORIA


def _mes_de(data) -> str:
    return f"{data.year:04d}-{data.month:02d}" if data else ""


def mapa_de_categorias(caminho_tabela, guardado=None) -> dict:
    """
    {FORNECEDOR -> categoria}. Comeca no que da para deduzir do proprio
    nome do fornecedor e e completado pelo que estiver no meta_categorias
    (o que voce escreveu manda mais).
    """
    mapa = {}
    try:
        wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
        if "ProdutosBAP" in wb.sheetnames:
            ws = wb["ProdutosBAP"]
            it = ws.iter_rows(values_only=True)
            cab = [_chave(c) for c in next(it)]
            i_forn = cab.index(_chave("FORNECEDOR")) if _chave("FORNECEDOR") in cab else None
            if i_forn is not None:
                for r in it:
                    nome = _texto(r[i_forn])
                    if nome and nome not in mapa:
                        limpo = nome.split("-", 1)[-1].strip().upper()
                        mapa[nome] = CATEGORIA_POR_FORNECEDOR.get(
                            limpo, CATEGORIA_PADRAO)
        wb.close()
    except (OSError, ValueError, KeyError):
        pass
    for nome, categoria in (guardado or {}).items():
        if categoria in {c for c, _, _ in CATEGORIAS}:
            mapa[nome] = categoria
    return mapa


def _segmento_do_codigo(realizado_ou_mapa, cod) -> str:
    mapa = (realizado_ou_mapa.get("segmento_do_cliente")
            if isinstance(realizado_ou_mapa, dict)
            and "segmento_do_cliente" in realizado_ou_mapa
            else realizado_ou_mapa) or {}
    cod = _texto(cod)
    return mapa.get(cod) or mapa.get(cod.zfill(6)) or mapa.get(
        cod.lstrip("0")) or ""


# (12/10) CLIENTES INTERNOS: os CNPJs do proprio grupo (FRW, BAP AUTOPARTS)
# nao contam para o resultado - nem faturamento, nem positivacao, nem RV.
def e_cliente_interno(nome="", fantasia="") -> bool:
    s = unicodedata.normalize("NFKD", f"{nome or ''} {fantasia or ''}")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    return bool(re.search(r"\bFRW\b", s)) or "BAP AUTOPARTS" in s \
        or "BAP AUTO PARTS" in s \
        or "PMZ DISTRIBUIDORA" in s       # (14/10) 000560, 001287


def ler_realizado(caminho_tabela, competencia: str, mapa=None,
                  categorias_csv=None, segmento_do_cliente=None) -> dict:
    """
    O que foi faturado no mes, cliente a cliente.

    categorias_csv = {codigo do produto -> categoria}, vindo do
    CATEGORIAS_PRODUTO.csv. Com ele, o realizado por categoria e o de
    verdade; sem ele, sobra o palpite pelo fornecedor.

    competencia = "AAAA-MM". Devolve
        {"clientes": {cod: {...}}, "competencia": ..., "notas": n,
         "sem_categoria": n}
    """
    caminho_tabela = Path(caminho_tabela)
    if not caminho_tabela.exists():
        raise FileNotFoundError(f"TABELA_BAP nao encontrada: {caminho_tabela}")
    mapa = mapa or {}
    categorias_csv = categorias_csv or {}

    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    if "ftPedidos" not in wb.sheetnames:
        wb.close()
        raise ValueError("A TABELA_BAP nao tem a aba ftPedidos - e dela que "
                         "sai o faturamento.")

    # A CATEGORIA DE CADA PRODUTO, em tres passos:
    #   1) o CATEGORIAS_PRODUTO.csv, pelo codigo do produto (o certo)
    #   2) a ponte ID_PRODUTO -> Cod. Produto da ProdutosBAP, para o caso
    #      de a nota trazer o ID e nao o codigo
    #   3) o fornecedor, que so sabe separar lubrificante
    categoria_do_produto = dict(categorias_csv)
    if "ProdutosBAP" in wb.sheetnames:
        ws = wb["ProdutosBAP"]
        it = ws.iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]

        def onde(*nomes):
            for n in nomes:
                if _chave(n) in cab:
                    return cab.index(_chave(n))
            return None

        i_id = onde("ID_PRODUTO")
        i_cod = onde("Cód. Produto", "Cod. Produto", "COD_PRODUTO")
        i_forn = onde("FORNECEDOR")
        if i_id is not None:
            for r in it:
                pid = _texto(r[i_id])
                if not pid:
                    continue
                cod = _texto(r[i_cod]) if i_cod is not None else ""
                if cod and cod in categorias_csv:
                    categoria_do_produto.setdefault(pid, categorias_csv[cod])
                elif pid not in categoria_do_produto:
                    categoria_do_produto[pid] = mapa.get(
                        _texto(r[i_forn]) if i_forn is not None else "",
                        CATEGORIA_PADRAO)

    # A FAMILIA DA PECA sai da DESCRICAO do produto - a mesma leitura
    # que o Oportunidades faz. Ela nao substitui a CATEGORIA (que tem
    # meta): e uma segunda vista do mesmo faturamento, mais fina.
    descricoes = fam.descricoes_da_tabela(wb)

    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    cab = [_chave(c) for c in next(it)]

    def coluna(*nomes):
        for n in nomes:
            if _chave(n) in cab:
                return cab.index(_chave(n))
        return None

    i_cli = coluna("D2_CLIENTE")
    i_tipo = coluna("TIPO")
    i_valor = coluna("VALOR TOTAL", "VALOR_TOTAL")
    i_nf = coluna("DATA_NF")
    i_dev = coluna("DATA_DEV")
    i_vend = coluna("C5_VEND1")
    i_razao = coluna("RAZÃO_SOCIAL", "RAZAO_SOCIAL")
    i_prod = coluna("ID_PRODUTO")
    i_cod_prod = coluna("D2_COD")
    i_doc = coluna("D2_DOC", "NUM_NF")
    if None in (i_cli, i_tipo, i_valor):
        wb.close()
        raise ValueError("A ftPedidos nao tem D2_CLIENTE, TIPO ou VALOR "
                         "TOTAL - nao da para medir o realizado.")

    clientes: dict[str, dict] = {}
    # O MESMO faturamento, somado por QUEM VENDEU (C5_VEND1) em vez de por
    # quem e o dono do cliente. Sao as duas leituras do mesmo mes:
    #   por cliente .... o que a CARTEIRA do vendedor faturou
    #   por vendedor ... o que ELE faturou, inclusive em cliente de outro
    # Nenhuma linha da ftPedidos entra duas vezes nem fica de fora de
    # nenhum dos dois lados, entao o TOTAL dos dois e igual.
    por_vendedor: dict[str, dict] = {}
    # A MESMA venda, uma terceira vez: por FAMILIA DA PECA, dentro de
    # cada vendedor. Guardar por vendedor (e nao so por familia) e o que
    # deixa a vista subir para supervisor e gerente depois, pelo mesmo
    # caminho que o resto do acompanhamento ja usa.
    por_familia: dict[tuple, dict] = {}
    # E UMA QUARTA VEZ, por SEGMENTO do cliente: o que o vendedor vendeu em
    # cada segmento (e por familia dentro dele). E o que deixa o
    # acompanhamento ser FILTRADO por segmento sem perder a regra de "quem
    # vendeu" nas linhas de pessoa.
    seg_mapa = segmento_do_cliente or {}
    por_vend_seg: dict[tuple, dict] = {}
    por_fam_seg: dict[tuple, dict] = {}
    notas = 0
    sem_categoria = 0
    sem_descricao = 0
    for r in it:
        tipo = _texto(r[i_tipo]).upper()
        if tipo not in TIPOS_VENDA and tipo != TIPO_DEVOLUCAO:
            continue
        data = _data(r[i_nf] if i_nf is not None else None)
        if data is None and i_dev is not None:
            data = _data(r[i_dev])
        if data is None or _mes_de(data) != competencia:
            continue
        valor = r[i_valor]
        if not isinstance(valor, (int, float)):
            valor = _numero(valor)
        cod = _texto(r[i_cli])
        if not cod:
            continue
        if i_razao is not None and e_cliente_interno(r[i_razao]):
            continue                    # (12/10) CNPJ interno: nao conta
        c = clientes.get(cod)
        if c is None:
            c = clientes[cod] = {
                "cod_cliente": cod, "faturado": 0.0, "devolvido": 0.0,
                "liquido": 0.0, "notas": set(), "vendedores": set(),
                **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS},
                # o mesmo cliente, aberto por QUEM VENDEU - e o que deixa
                # o supervisor somar os clientes das zonas dele sem contar
                # duas vezes o que a equipe dele ja vendeu
                "por_vend": {},
            }
        if tipo == TIPO_DEVOLUCAO:
            c["devolvido"] += valor
        else:
            c["faturado"] += valor
        c["liquido"] += valor
        vendeu = _texto(r[i_vend]) if i_vend is not None else ""
        if vendeu:
            c["vendedores"].add(vendeu)
        # a mesma linha, agora na conta de quem vendeu. Nota sem vendedor
        # nao e descartada: vai para uma chave propria, senao o total por
        # vendedor deixaria de fechar com o total por cliente.
        chave_v = _cod_vendedor(vendeu)
        v = por_vendedor.get(chave_v)
        if v is None:
            v = por_vendedor[chave_v] = {
                "cod_vendedor": chave_v, "faturado": 0.0, "devolvido": 0.0,
                "liquido": 0.0, "notas": set(), "clientes": set(),
                **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS},
            }
        if tipo == TIPO_DEVOLUCAO:
            v["devolvido"] += valor
        else:
            v["faturado"] += valor
        v["liquido"] += valor
        v["clientes"].add(cod)
        if i_doc is not None and _texto(r[i_doc]):
            v["notas"].add(_texto(r[i_doc]))
        if i_doc is not None and _texto(r[i_doc]):
            c["notas"].add(_texto(r[i_doc]))
        # a nota traz o codigo do produto (D2_COD); o ID e a segunda porta
        cod_prod = _texto(r[i_cod_prod]) if i_cod_prod is not None else ""
        pid = _texto(r[i_prod]) if i_prod is not None else ""
        categoria = (categoria_do_produto.get(cod_prod)
                     or categoria_do_produto.get(pid))
        if categoria is None:
            sem_categoria += 1
            categoria = CATEGORIA_PADRAO
        c[f"real_{categoria}"] += valor
        v[f"real_{categoria}"] += valor
        cv = c["por_vend"].get(chave_v)
        if cv is None:
            cv = c["por_vend"][chave_v] = {
                "faturado": 0.0, "devolvido": 0.0, "liquido": 0.0,
                **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS}}
        if tipo == TIPO_DEVOLUCAO:
            cv["devolvido"] += valor
        else:
            cv["faturado"] += valor
        cv["liquido"] += valor
        cv[f"real_{categoria}"] += valor
        seg = _segmento_do_codigo(seg_mapa, cod) or SEM_SEGMENTO
        vs = por_vend_seg.get((seg, chave_v))
        if vs is None:
            vs = por_vend_seg[(seg, chave_v)] = {
                "cod_vendedor": chave_v, "faturado": 0.0, "devolvido": 0.0,
                "liquido": 0.0, "notas": set(), "clientes": set(),
                **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS},
            }
        if tipo == TIPO_DEVOLUCAO:
            vs["devolvido"] += valor
        else:
            vs["faturado"] += valor
        vs["liquido"] += valor
        vs["clientes"].add(cod)
        if i_doc is not None and _texto(r[i_doc]):
            vs["notas"].add(_texto(r[i_doc]))
        vs[f"real_{categoria}"] += valor

        # a FAMILIA do item, pela descricao do produto
        desc = descricoes.get(cod_prod.upper(), "")
        if not desc:
            sem_descricao += 1
        familia, grupo, _lin = fam.classificar(desc)
        chave_f = (chave_v, familia)
        f = por_familia.get(chave_f)
        if f is None:
            f = por_familia[chave_f] = {
                "cod_vendedor": chave_v, "familia": familia,
                "faturado": 0.0, "devolvido": 0.0, "liquido": 0.0,
                "notas": set(), "clientes": set(), "skus": set(),
                "grupos": {}}
        if tipo == TIPO_DEVOLUCAO:
            f["devolvido"] += valor
        else:
            f["faturado"] += valor
        f["liquido"] += valor
        f["clientes"].add(cod)
        if cod_prod:
            f["skus"].add(cod_prod)
        if i_doc is not None and _texto(r[i_doc]):
            f["notas"].add(_texto(r[i_doc]))
        g = f["grupos"].get(grupo)
        if g is None:
            g = f["grupos"][grupo] = {"grupo": grupo, "liquido": 0.0,
                                      "skus": set(), "clientes": set()}
        g["liquido"] += valor
        g["clientes"].add(cod)
        if cod_prod:
            g["skus"].add(cod_prod)
        fs = por_fam_seg.get((seg, chave_v, familia))
        if fs is None:
            fs = por_fam_seg[(seg, chave_v, familia)] = {
                "cod_vendedor": chave_v, "familia": familia,
                "faturado": 0.0, "devolvido": 0.0, "liquido": 0.0,
                "notas": set(), "clientes": set(), "skus": set(),
                "grupos": {}}
        if tipo == TIPO_DEVOLUCAO:
            fs["devolvido"] += valor
        else:
            fs["faturado"] += valor
        fs["liquido"] += valor
        fs["clientes"].add(cod)
        if cod_prod:
            fs["skus"].add(cod_prod)
        if i_doc is not None and _texto(r[i_doc]):
            fs["notas"].add(_texto(r[i_doc]))
        gs = fs["grupos"].get(grupo)
        if gs is None:
            gs = fs["grupos"][grupo] = {"grupo": grupo, "liquido": 0.0,
                                        "skus": set(), "clientes": set()}
        gs["liquido"] += valor
        gs["clientes"].add(cod)
        if cod_prod:
            gs["skus"].add(cod_prod)
        notas += 1
    wb.close()

    for c in clientes.values():
        c["qtd_notas"] = len(c["notas"])
        c["vendedor_da_nota"] = ", ".join(sorted(c["vendedores"]))
        c.pop("notas", None)
        c.pop("vendedores", None)
        # positivou = faturou de verdade no mes (liquido acima de zero)
        c["positivou"] = 1 if c["liquido"] > 0 else 0

    for v in list(por_vendedor.values()) + list(por_vend_seg.values()):
        v["qtd_notas"] = len(v["notas"])
        v["qtd_clientes"] = len(v["clientes"])
        v.pop("notas", None)
        v.pop("clientes", None)

    for f in list(por_familia.values()) + list(por_fam_seg.values()):
        f["qtd_notas"] = len(f["notas"])
        f["qtd_clientes"] = len(f["clientes"])
        f["qtd_skus"] = len(f["skus"])
        f.pop("notas", None)
        f.pop("clientes", None)
        f.pop("skus", None)
        for g in f["grupos"].values():
            g["qtd_skus"] = len(g["skus"])
            g["qtd_clientes"] = len(g["clientes"])
            g.pop("skus", None)
            g.pop("clientes", None)

    for cod, c in clientes.items():
        c["segmento"] = _segmento_do_codigo(seg_mapa, cod) or SEM_SEGMENTO
    return {"clientes": clientes, "por_vendedor": por_vendedor,
            "por_familia": por_familia,
            "por_vendedor_segmento": por_vend_seg,
            "por_familia_segmento": por_fam_seg,
            "segmento_do_cliente": dict(seg_mapa),
            "competencia": competencia,
            "linhas": notas, "sem_categoria": sem_categoria,
            "sem_descricao": sem_descricao,
            "com_csv": bool(categorias_csv),
            "arquivo": caminho_tabela}


FORA_DO_PLANNER = "(FORA DO PLANNER)"


# --------------------------------------------------------------------------
# O FILTRO POR SEGMENTO
# --------------------------------------------------------------------------
def segmentos_da_base(caminho_base) -> dict:
    """
    {COD_CLIENTE: SEGMENTO}, das abas BASE_CLIENTE e EXCLUIDOS. Quem esta
    na EXCLUIDOS sai como "(EXCLUIDO)": a venda dele existe, mas ele nao
    esta em nenhum dos 8 segmentos.
    """
    caminho_base = Path(caminho_base)
    if not caminho_base.exists():
        return {}
    saida = {}
    wb = load_workbook(caminho_base, read_only=True, data_only=True)
    try:
        for aba, fixo in (("BASE_CLIENTE", None), ("EXCLUIDOS", "(EXCLUIDO)")):
            if aba not in wb.sheetnames:
                continue
            it = wb[aba].iter_rows(values_only=True)
            try:
                cab = [_chave(c) for c in next(it)]
            except StopIteration:
                continue
            if _chave("COD_CLIENTE") not in cab:
                continue
            i_cod = cab.index(_chave("COD_CLIENTE"))
            i_seg = cab.index(_chave("SEGMENTO")) if _chave("SEGMENTO") in cab else None
            for r in it:
                cod = _texto(r[i_cod]) if i_cod < len(r) else ""
                if not cod:
                    continue
                seg = fixo or (_texto(r[i_seg]).upper()
                               if i_seg is not None and i_seg < len(r) else "")
                for k in (cod, cod.zfill(6), cod.lstrip("0")):
                    saida.setdefault(k, seg or SEM_SEGMENTO)
    finally:
        wb.close()
    return saida


def resultado_do_segmento(resultado: dict, segmento: str) -> dict:
    """
    A meta vista SO por um segmento. Cada linha passa a ser a SOMA DOS
    CLIENTES daquele segmento - a regra de cada nivel (crescimento do
    vendedor, rateio da META GERAL na UF e no gerente) e da carteira
    inteira e nao se reparte por segmento. Serve para LER; a meta que
    vale e grava continua sendo a de todos os segmentos.
    """
    if not resultado or not segmento or segmento == TODOS_OS_SEGMENTOS:
        return resultado
    clientes = [c for c in resultado["clientes"]
                if (c.get("segmento") or SEM_SEGMENTO) == segmento]
    recortes = {r: _agrupar(clientes, r) for r in RECORTES}
    for r in RECORTES:
        for linha in recortes[r]:
            linha["meta_calculada"] = linha["meta"]
            linha["faixa"] = f"soma dos clientes de {segmento}"
            linha["no_piso"] = False
            linha["conta_na_meta"] = True
            linha["meta_cadastro"] = None
    novo = dict(resultado)
    novo.update({
        "clientes": clientes,
        "recortes": recortes,
        "totais": {r: total_do_recorte(recortes[r]) for r in RECORTES},
        "total": _fechar_linha("TOTAL", clientes),
        "segmento": segmento,
    })
    return novo


def realizado_do_segmento(realizado: dict, segmento: str) -> dict:
    """O realizado so do segmento: cliente, vendedor e familia."""
    if not realizado or not segmento or segmento == TODOS_OS_SEGMENTOS:
        return realizado
    novo = dict(realizado)
    novo["clientes"] = {cod: c for cod, c in realizado["clientes"].items()
                        if c.get("segmento", SEM_SEGMENTO) == segmento}
    novo["por_vendedor"] = {
        cv: v for (sg, cv), v in (realizado.get("por_vendedor_segmento")
                                  or {}).items() if sg == segmento}
    novo["por_familia"] = {
        (cv, fm): f for (sg, cv, fm), f in (realizado.get("por_familia_segmento")
                                            or {}).items() if sg == segmento}
    novo["segmento"] = segmento
    return novo


def dias_uteis_do_mes(competencia: str, feriados=()) -> list:
    """Os dias de venda do mes: segunda a sexta, tirando os feriados."""
    comp = normalizar_competencia(competencia)
    if not comp:
        return []
    ano, mes = int(comp[:4]), int(comp[5:7])
    fora = set()
    for f in feriados or ():
        d = _data(f)
        if d is not None:
            fora.add(d.date() if hasattr(d, "date") else d)
    ultimo = calendar.monthrange(ano, mes)[1]
    dias = []
    for dia in range(1, ultimo + 1):
        data = dt.date(ano, mes, dia)
        if data.weekday() < 5 and data not in fora:
            dias.append(data)
    return dias


def dias_uteis_restantes(competencia: str, hoje=None, feriados=()) -> int:
    """
    Quantos dias de venda AINDA FALTAM no mes, contando hoje.

    E o denominador do NEC./DIA. Mes que ja passou devolve 0 - e ali a
    coluna fica vazia, porque "quanto por dia" nao quer dizer mais nada.
    Mes que ainda nao comecou devolve o mes inteiro.
    """
    dias = dias_uteis_do_mes(competencia, feriados)
    if not dias:
        return 0
    hoje = hoje or dt.date.today()
    if hasattr(hoje, "date"):
        hoje = hoje.date()
    return sum(1 for d in dias if d >= hoje)


def _meta_do_gap(linha: dict, chave: str):
    """
    A meta que o GAP usa. As colunas de contagem sao gravadas so na hora
    de mostrar (meta_visita_int), entao aqui se pega a crua e se
    arredonda para cima do mesmo jeito - o GAP tem de bater com o numero
    que esta na tela ao lado dele.
    """
    valor = linha.get(chave)
    if valor is None and chave.endswith("_int"):
        cru = linha.get(chave[:-4])
        if cru is None:
            return None
        try:
            return float(math.ceil(float(cru)))
        except (TypeError, ValueError):
            return None
    return valor


def _fechar_rh(linha: dict, dias: int) -> None:
    """A META RH de faturamento contra o mesmo realizado: atingimento,
    falta e NEC./DIA. E por ela que a RV de faturamento paga."""
    meta = linha.get("meta_rh")
    if meta is None:
        meta = linha["meta_rh"] = linha.get("meta") or 0.0
    real = linha.get("realizado") or 0.0
    linha["atingimento_rh"] = (real / meta * 100.0) if meta else 0.0
    linha["falta_rh"] = meta - real
    linha["nec_fat_rh"] = (max(0.0, meta - real) / dias) if dias else None


def _fechar_gaps(linha: dict, dias: int) -> None:
    """O GAP DO MES e o NEC./DIA de cada indicador daquela linha."""
    for _, meta_k, real_k, _, gap_k, nec_k in METAS_DO_ACOMPANHAMENTO:
        meta = _meta_do_gap(linha, meta_k)
        real = linha.get(real_k)
        if meta is None:
            linha[gap_k] = None
            linha[nec_k] = None
            continue
        gap = float(meta) - float(real or 0.0)
        linha[gap_k] = gap
        linha[nec_k] = (max(0.0, gap) / dias) if dias else None
    linha["dias_restantes"] = dias or None


# --------------------------------------------------------------------------
# O FATURAMENTO DE QUEM VENDEU
# --------------------------------------------------------------------------
# Nos recortes de PESSOA - vendedor, supervisor e gerente - o FAT TOTAL e
# as categorias sao o que a pessoa VENDEU, pelo codigo do vendedor na nota
# (C5_VEND1), e nao o que a carteira dela faturou.
#
#   vendedor ..... as notas que saíram no codigo dele
#   supervisor ... a soma dos vendedores dele
#   gerente ...... a soma dos supervisores dele
#
# O que a carteira faturou nao se perde: fica na coluna FATURAMENTO
# CARTEIRA, ao lado. Nos recortes que nao sao de pessoa (zona, UF, cidade,
# bairro, cliente) nao existe "quem vendeu" que suba, entao as duas
# colunas continuam sendo a mesma coisa.
#
# POR QUE OS DOIS TOTAIS FECHAM: as duas leituras percorrem as MESMAS
# linhas da ftPedidos, so mudam de gaveta. Venda de vendedor que nao esta
# no PLANNER, e nota sem vendedor, ganham linha propria em vez de sumir.
NIVEIS_DA_VENDA = ("vendedor", "supervisor", "gerente")
CAMPOS_DA_VENDA = ("faturado", "devolvido", "realizado", "notas")


def _chave_do_nivel(nivel: str, chave) -> str:
    """No vendedor a chave e o codigo (que precisa dos seis digitos dos
    dois lados); no supervisor e no gerente e o nome, que vai como esta."""
    return _cod_vendedor(chave) if nivel == "vendedor" else chave


def _equipe_por_vendedor(clientes: list) -> dict:
    """{codigo do vendedor: a ficha dele no PLANNER (nome, sup, gerente)}."""
    equipe = {}
    for c in clientes:
        cod = _cod_vendedor(c.get("cod_vendedor"))
        if cod and cod != SEM_VENDEDOR_NA_NOTA and cod not in equipe:
            equipe[cod] = c
    return equipe


def _zerar_como(modelo: dict) -> dict:
    """
    Uma linha nova com a mesma forma de uma que ja existe, tudo zerado.

    Copiar a forma em vez de montar o dicionario na mao e de proposito:
    o acompanhamento tem dezenas de campos e, quando alguem acrescenta
    mais um, esta linha acompanha sozinha - em vez de quebrar na tela
    com um KeyError meses depois.
    """
    nova = {}
    for chave, valor in modelo.items():
        if valor is None:
            nova[chave] = None
        elif isinstance(valor, bool):
            nova[chave] = False
        elif isinstance(valor, (int, float)):
            nova[chave] = type(valor)(0)
        elif isinstance(valor, str):
            nova[chave] = ""
        else:
            nova[chave] = valor
    return nova


def _vendas_por_nivel(realizado: dict, equipe: dict) -> dict:
    """
    {nivel: {codigo: somas da venda}} para vendedor, supervisor e gerente.
    Quem vendeu e nao esta no PLANNER cai na chave FORA DO PLANNER, nos
    tres niveis - assim o gerente continua fechando com o total.
    """
    vazio = lambda: {"faturado": 0.0, "devolvido": 0.0, "realizado": 0.0,
                     "notas": 0,
                     **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS}}
    soma = {n: defaultdict(vazio) for n in NIVEIS_DA_VENDA}
    nomes = {}
    for cod, v in (realizado.get("por_vendedor") or {}).items():
        ficha = equipe.get(cod)
        # A CHAVE E A MESMA QUE O AGRUPAMENTO USA, nao uma inventada aqui:
        # chave_da_linha() e por codigo no vendedor e por NOME no
        # supervisor e no gerente. Montar a chave na mao fez todas as
        # linhas cairem em "(FORA DO PLANNER)" na primeira versao disto.
        if ficha:
            chaves = {n: chave_da_linha(n, ficha) for n in NIVEIS_DA_VENDA}
        else:
            # Vendeu e o PLANNER nao conhece o codigo. No SUPERVISOR e no
            # GERENTE tudo isso junta numa linha so - eles nao tem onde
            # pendurar. No VENDEDOR cada codigo ganha a SUA linha: e
            # assim que se descobre que existe venda saindo no "000000".
            chaves = {n: FORA_DO_PLANNER for n in NIVEIS_DA_VENDA}
            chaves["vendedor"] = cod
            nomes.setdefault("vendedor", {})[cod] = (
                f"{FORA_DO_PLANNER} {cod}" if cod != SEM_VENDEDOR_NA_NOTA
                else cod)
        for nivel in NIVEIS_DA_VENDA:
            alvo = soma[nivel][chaves[nivel]]
            alvo["faturado"] += v["faturado"]
            alvo["devolvido"] += v["devolvido"]
            alvo["realizado"] += v["liquido"]
            alvo["notas"] += v["qtd_notas"]
            for k, _, _ in CATEGORIAS:
                alvo[f"real_{k}"] += v[f"real_{k}"]
    return soma, nomes


# ==========================================================================
# A VISTA POR FAMILIA DA PECA
# ==========================================================================
# As quatro CATEGORIAS da meta (PECAS, BATERIA, LUBRIFICANTE, PNEU)
# continuam sendo as que tem meta e atingimento - nada muda ali. A
# FAMILIA e uma segunda vista do MESMO faturamento, mais fina: dentro de
# PECAS ela separa FREIO de SUSPENSAO de MOTOR, que e a conversa que o
# vendedor tem com o cliente na porta da loja.
#
# Ela NAO tem meta, de proposito. Meta por familia obrigaria a mexer na
# aba de parametros e no arquivo do RH; e a pergunta que ela responde -
# "esse vendedor esta vendendo so bateria?" - nao precisa de meta para
# ser util.
#
# Cada linha da ftPedidos ja foi somada por familia DENTRO DO VENDEDOR
# da nota (ler_realizado). Subir para supervisor e gerente e so trocar a
# chave, pelo mesmo caminho do resto do acompanhamento - por isso a soma
# das familias fecha com o FAT TOTAL em qualquer nivel.
COLUNAS_FAMILIA = (
    ("FAMILIA", "familia", 20, None),
    ("FATURADO R$", "faturado", 16, "#,##0.00"),
    ("DEVOLVIDO R$", "devolvido", 16, "#,##0.00"),
    ("REALIZADO R$", "realizado", 16, "#,##0.00"),
    ("% DO TOTAL", "perc", 13, "#,##0.0"),
    ("CLIENTES", "qtd_clientes", 11, "#,##0"),
    ("NOTAS", "qtd_notas", 9, "#,##0"),
    ("SKUS", "qtd_skus", 9, "#,##0"),
    ("TICKET MEDIO R$", "ticket", 18, "#,##0.00"),
)

COLUNAS_FAMILIA_EXCEL = ((("NIVEL", "nivel", 14, None),
                          ("QUEM", "quem", 34, None))
                         + COLUNAS_FAMILIA)

NIVEL_BAP = "bap"
NIVEIS_DA_FAMILIA = (NIVEL_BAP, "gerente", "supervisor", "vendedor")


def _chaves_do_vendedor(cod: str, equipe: dict) -> dict:
    """As tres chaves (gerente, supervisor, vendedor) de um codigo."""
    ficha = equipe.get(cod)
    if ficha:
        saida = {n: chave_da_linha(n, ficha) for n in NIVEIS_DA_VENDA}
    else:
        saida = {n: FORA_DO_PLANNER for n in NIVEIS_DA_VENDA}
        saida["vendedor"] = cod
    saida[NIVEL_BAP] = "BAP"
    return saida


def pessoas_da_familia(realizado: dict, resultado: dict,
                       nivel: str = "vendedor") -> list:
    """Quem existe naquele nivel, para encher a lista da tela."""
    if nivel == NIVEL_BAP:
        return ["BAP"]
    equipe = _equipe_por_vendedor((resultado or {}).get("clientes") or [])
    vistas = set()
    for (cod, _familia) in (realizado.get("por_familia") or {}):
        vistas.add(_chaves_do_vendedor(cod, equipe)[nivel])
    return sorted(vistas)


def visao_por_familia(realizado: dict, resultado: dict,
                      nivel: str = NIVEL_BAP, chave: str = "") -> list:
    """
    Uma linha por FAMILIA, somando o faturamento do mes.

    nivel = "bap" olha a BAP inteira; "gerente"/"supervisor"/"vendedor"
    com a `chave` preenchida olham so aquela pessoa. A soma da coluna
    REALIZADO e o mesmo FAT TOTAL que o acompanhamento mostra para ela.
    """
    equipe = _equipe_por_vendedor((resultado or {}).get("clientes") or [])
    nivel = nivel if nivel in NIVEIS_DA_FAMILIA else NIVEL_BAP
    junto: dict[str, dict] = {}
    for (cod, familia), v in (realizado.get("por_familia") or {}).items():
        if nivel != NIVEL_BAP and chave:
            if _chaves_do_vendedor(cod, equipe)[nivel] != chave:
                continue
        alvo = junto.get(familia)
        if alvo is None:
            alvo = junto[familia] = {
                "familia": familia, "faturado": 0.0, "devolvido": 0.0,
                "realizado": 0.0, "qtd_clientes": 0, "qtd_notas": 0,
                "qtd_skus": 0, "grupos": {}}
        alvo["faturado"] += v["faturado"]
        alvo["devolvido"] += v["devolvido"]
        alvo["realizado"] += v["liquido"]
        alvo["qtd_clientes"] += v["qtd_clientes"]
        alvo["qtd_notas"] += v["qtd_notas"]
        alvo["qtd_skus"] += v["qtd_skus"]
        for nome, g in (v.get("grupos") or {}).items():
            alvo_g = alvo["grupos"].get(nome)
            if alvo_g is None:
                alvo_g = alvo["grupos"][nome] = {
                    "grupo": nome, "realizado": 0.0, "qtd_skus": 0,
                    "qtd_clientes": 0}
            alvo_g["realizado"] += g["liquido"]
            alvo_g["qtd_skus"] += g["qtd_skus"]
            alvo_g["qtd_clientes"] += g["qtd_clientes"]
    total = sum(x["realizado"] for x in junto.values())
    linhas = []
    for nome in fam.ORDEM_FAMILIA:
        x = junto.get(nome)
        if x is None:
            continue
        x["perc"] = (x["realizado"] / total * 100.0) if total else 0.0
        x["ticket"] = (x["realizado"] / x["qtd_notas"]) if x["qtd_notas"] \
            else 0.0
        linhas.append(x)
    linhas.sort(key=lambda x: -x["realizado"])
    return linhas


def total_da_familia(linhas: list) -> dict:
    """O TOTAL do rodape. Tem de bater com o FAT TOTAL daquele nivel."""
    realizado = sum(l.get("realizado") or 0.0 for l in linhas)
    notas = sum(l.get("qtd_notas") or 0 for l in linhas)
    return {
        "familia": "TOTAL",
        "faturado": sum(l.get("faturado") or 0.0 for l in linhas),
        "devolvido": sum(l.get("devolvido") or 0.0 for l in linhas),
        "realizado": realizado,
        "perc": 100.0 if linhas else 0.0,
        # CLIENTES, NOTAS e SKUS nao se somam entre familias: o mesmo
        # cliente compra freio e filtro, e seria contado duas vezes.
        # Melhor vazio do que um numero que ninguem consegue conferir.
        "qtd_clientes": None, "qtd_notas": None, "qtd_skus": None,
        "ticket": (realizado / notas) if notas else 0.0,
    }


def grupos_da_familia(linhas: list, familia: str) -> list:
    """O detalhe de uma familia: uma linha por GRUPO."""
    for l in linhas:
        if l.get("familia") == familia:
            grupos = list((l.get("grupos") or {}).values())
            grupos.sort(key=lambda x: -x["realizado"])
            return grupos
    return []


def _trocar_pelo_vendedor_da_nota(recortes: dict, resultado: dict,
                                  realizado: dict) -> None:
    """
    Nos tres recortes de pessoa, troca o realizado da CARTEIRA pelo que a
    pessoa VENDEU. Roda antes de a meta do painel ser aplicada, para o
    atingimento ja nascer do numero novo.
    """
    if not (realizado.get("por_vendedor") or {}):
        return
    equipe = _equipe_por_vendedor(resultado.get("clientes") or [])
    soma, nomes = _vendas_por_nivel(realizado, equipe)
    # (09/10) A POSITIVACAO TAMBEM E DE QUEM VENDEU: o cliente conta para o
    # vendedor que bateu a nota (liquido dele > 0 no cliente), igual ao
    # faturamento - antes contava para o dono da carteira (Thiago vendeu
    # para um cliente da carteira do Valmir: o faturamento ia para o
    # Thiago e a positivacao para o Valmir). Supervisor e gerente: os
    # clientes distintos que a equipe deles positivou.
    pos = {n: defaultdict(set) for n in NIVEIS_DA_VENDA}
    for cod_c, c in (realizado.get("clientes") or {}).items():
        for vend, v in (c.get("por_vend") or {}).items():
            if (v.get("liquido") or 0) <= 0:
                continue
            ch = _chaves_do_vendedor(vend, equipe)
            for nivel in NIVEIS_DA_VENDA:
                pos[nivel][ch[nivel]].add(cod_c)

    for nivel in NIVEIS_DA_VENDA:
        linhas = recortes.get(nivel)
        if not linhas:
            continue
        por_chave = {}
        for linha in linhas:
            por_chave.setdefault(_chave_do_nivel(nivel, linha["chave"]), linha)
        for chave, valores in soma[nivel].items():
            linha = por_chave.get(chave)
            if linha is None:
                # vendeu e nao tem linha: o PLANNER nao conhece esse
                # codigo, ou o supervisor nao tem cliente nenhum
                linha = _zerar_como(linhas[0])
                linha["chave"] = chave
                linha["recorte"] = nivel
                linha["codigo"] = chave
                linha["nome"] = (nomes.get(nivel, {}).get(chave)
                                 or FORA_DO_PLANNER)
                linha["rotulo"] = linha["nome"]
                linha["fora_do_planner"] = True
                # nao e cadeira vaga: e codigo que o cadastro nao conhece
                linha["vendedor_ativo"] = True
                linhas.append(linha)
                por_chave[chave] = linha
            for c in CAMPOS_DA_VENDA:
                linha[c] = valores[c]
            for k, _, _ in CATEGORIAS:
                linha[f"real_{k}"] = valores[f"real_{k}"]
            linha["positivados"] = len(pos[nivel].get(chave, ()))
            _refechar_acompanhamento(linha)
        # quem tem carteira mas NAO vendeu nada no proprio codigo zera o
        # realizado - senao ficaria com o da carteira, que nao e dele
        for linha in linhas:
            if _chave_do_nivel(nivel, linha["chave"]) in soma[nivel]:
                continue
            for c in CAMPOS_DA_VENDA:
                linha[c] = 0.0 if c != "notas" else 0
            for k, _, _ in CATEGORIAS:
                linha[f"real_{k}"] = 0.0
            linha["positivados"] = 0
            _refechar_acompanhamento(linha)


# --------------------------------------------------------------------------
# AS ZONAS DO SUPERVISOR
# --------------------------------------------------------------------------
# As ZONAS DO SUPERVISOR = as zonas dos vendedores ativos dele (padrao)
# + as que forem cadastradas na ficha dele no Planner.
# O RESULTADO do supervisor = o que os vendedores dele venderam (como
# sempre) MAIS, nos clientes dessas zonas, a venda que a equipe dele nao
# fez (nota de outro vendedor, ou sem vendedor) - seja o cliente da
# carteira da equipe ou nao. Nada entra duas vezes. Vale para faturamento, categorias, positivacao e cadastro.
# NAO vale para VISITA (soma dos vendedores) nem para a META: a meta e
# SEMPRE a soma da meta dos vendedores ativos - a zona so mexe no
# resultado. O gerente continua sendo a soma do que os vendedores venderam.
CONFIG_DO_PLANNER = "planner_config.json"


def aplicar_equipe_do_mes(dados: dict, caminho_cfg) -> int:
    """
    A EQUIPE DO MES DA META. O PLANNER traz quem responde a quem do dia em
    que foi gerado; a configuracao do Planner daquele mes (PLANNER_MESES)
    manda: supervisor, gerente e cadeira ativa de cada vendedor. Devolve
    quantos clientes mudaram de equipe.
    """
    import planner_nucleo as nu                         # noqa: PLC0415
    try:
        cfg = nu.carregar_config(caminho_cfg)
    except (OSError, ValueError):
        return 0
    if not cfg.get("pessoas"):
        return 0
    # OS MESES DE CASA de cada codigo (vendedor ou supervisor com
    # carteira), do cadastro do Planner daquele mes - a meta de quem
    # esta chegando sai da tabela da aba 1
    casa = dados.setdefault("meses_de_casa", {})
    fracao = dados.setdefault("fracao_de_casa", {})
    mes_cfg = _texto(cfg.get("mes"))
    # (21/10) a meta de visita de cada dia util, vendedor a vendedor
    if hasattr(nu, "metas_de_visita_do_mes") and mes_cfg:
        try:
            cid = {nu.chave_normal(f"{_texto(c.get('cod_cliente'))}-"
                                   f"{_texto(c.get('loja'))}"): c.get("cidade")
                   for c in dados.get("clientes") or []}
            dados["meta_visita_dias"] = {
                _cod_vendedor(k): {d.isoformat(): m for d, m in v.items()}
                for k, v in nu.metas_de_visita_do_mes(cfg, cid).items()}
        except Exception:                               # noqa: BLE001
            dados.pop("meta_visita_dias", None)
    for pz in cfg.get("pessoas") or []:
        # (18/10) de nov/26 em diante o mes de casa sai da DATA DE ADMISSAO
        # (antes, o que estava escrito); no mes da admissao, a proporcao dos
        # dias uteis trabalhados
        n = nu.mes_de_casa_no_mes(pz, mes_cfg) \
            if hasattr(nu, "mes_de_casa_no_mes") else meses_de_casa(pz)
        if n and _texto(pz.get("cod_protheus")):
            casa[_cod_vendedor(pz.get("cod_protheus"))] = n
        f = nu.fracao_do_mes(pz, mes_cfg, cfg.get("feriados") or ()) \
            if hasattr(nu, "fracao_do_mes") else 1.0
        if f < 1.0 and _texto(pz.get("cod_protheus")):
            fracao[_cod_vendedor(pz.get("cod_protheus"))] = f
    mudou = 0
    for c in dados.get("clientes") or []:
        cod = _texto(c.get("cod_vendedor"))
        v = nu.pessoa_por_codigo(cfg, cod) or nu.pessoa_por_codigo(
            cfg, _cod_vendedor(cod))
        if not v or v.get("cargo") != "VENDEDOR":
            continue
        sup = nu.chefe_de(cfg, v["cod_protheus"])
        ger = nu.gerente_de(cfg, v["cod_protheus"])
        novo = {"supervisor": _texto(sup.get("nome")) or "(sem supervisor)",
                "cod_supervisor": _texto(sup.get("cod_protheus")),
                "gerente": _texto(ger.get("nome")) or "(sem gerente)",
                "cod_gerente": _texto(ger.get("cod_protheus")),
                "vendedor_ativo": v.get("ativo") is not False}
        if any(c.get(k) != x for k, x in novo.items()):
            c.update(novo)
            mudou += 1
    return mudou


def meses_de_casa(pessoa: dict) -> int:
    """O mes de casa do cadastro (1 = primeiro mes); 0 = nao informado."""
    try:
        n = int(float(str((pessoa or {}).get("meses_de_casa") or 0)
                      .replace(",", ".")))
    except ValueError:
        return 0
    return max(n, 0)


def zonas_dos_supervisores(caminho=None) -> dict:
    """{NOME DO SUPERVISOR: {"cod", "zonas", "extras"}} do planner_config:
    "zonas" = as dos vendedores ativos dele + as cadastradas na ficha dele
    ("extras")."""
    caminho = Path(caminho) if caminho else (
        Path(__file__).resolve().parent / CONFIG_DO_PLANNER)
    try:
        cfg = json.loads(caminho.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    codigo_da_zona = {z.get("id"): (z.get("codigo") or z.get("id"))
                      for z in cfg.get("zonas", [])}
    zonas_do_vend = defaultdict(set)
    for z in cfg.get("zonas", []):
        at = z.get("atendimento")
        if not isinstance(at, list):
            at = [{"vendedor": z.get("vendedor")}]
        for a in at:
            v = _texto(a.get("vendedor"))
            if v:
                zonas_do_vend[v].add(codigo_da_zona.get(z.get("id")))
    pessoas = cfg.get("pessoas", [])
    sups = [p for p in pessoas
            if p.get("cargo") == "SUPERVISOR" and p.get("ativo") is not False]
    equipe_de = {}
    for p in sups:
        cod = _texto(p.get("cod_protheus"))
        da_equipe = set()
        for v in pessoas:
            if (v.get("cargo") == "VENDEDOR" and v.get("ativo") is not False
                    and _texto(v.get("responde_a")) == cod):
                da_equipe |= zonas_do_vend.get(_texto(v.get("cod_protheus")),
                                               set())
        equipe_de[cod] = {z for z in da_equipe if z}
    # (08/10) A ZONA TEM UM SUPERVISOR SO: a zona cadastrada na ficha
    # (extra) nao vale se ja e de outro supervisor - pela equipe dele (o
    # vendedor dele atende a zona) ou porque outro a cadastrou antes. Ex.:
    # Z-MT-01/02 sao do SUPERVISOR MT (VAGO) pelo Paulo; cadastradas
    # tambem no Denylson, a venda do Paulo subia nos dois.
    ja_extra = set()
    saida = {}
    for p in sups:
        cod = _texto(p.get("cod_protheus"))
        da_equipe = equipe_de[cod]
        de_outros = set().union(*[z_ for c_, z_ in equipe_de.items()
                                  if c_ != cod]) if len(equipe_de) > 1 \
            else set()
        pedidas = {codigo_da_zona.get(z, z)
                   for z in p.get("zonas_supervisor") or []} - {""}
        extras = {z for z in pedidas - da_equipe
                  if z not in de_outros and z not in ja_extra}
        ja_extra |= extras
        zonas = da_equipe | extras
        if zonas:
            saida[_texto(p.get("nome")).upper()] = {
                "cod": _cod_vendedor(cod), "zonas": zonas,
                "extras": extras,
                "ignoradas": sorted(pedidas - da_equipe - extras)}
    return saida


def _extras_das_zonas_do_supervisor(linhas: list, realizado: dict,
                                    zonas_sup: dict) -> dict:
    """{supervisor: o que somar a ele} - nas zonas dele, toda venda feita
    por quem NAO e da equipe (a da equipe ja sobe pelo vendedor); e os
    clientes de fora da carteira da equipe entram em clientes, positivacao
    e cadastro."""
    if not zonas_sup:
        return {}
    equipe = defaultdict(set)
    for l in linhas:
        if l.get("cod_vendedor") and not l.get("fora_do_planner"):
            equipe[_texto(l.get("supervisor")).upper()].add(
                _cod_vendedor(l["cod_vendedor"]))
    saida = {}
    for nome, info in zonas_sup.items():
        time = equipe.get(nome, set()) | {info["cod"]}
        ex = {"faturado": 0.0, "devolvido": 0.0, "realizado": 0.0,
              "positivados": 0, "cadastros_no_mes": 0,
              "cadastros_com_compra": 0, "clientes": 0,
              "zonas": sorted(info["zonas"]),
              **{f"real_{k}": 0.0 for k, _, _ in CATEGORIAS}}
        # os clientes das zonas dele: de quem e a carteira (da equipe ou nao)
        da_zona = {}
        for l in linhas:
            if l.get("fora_do_planner") or l.get("cod_zona") not in info["zonas"]:
                continue
            cod = l.get("cod_cliente")
            dele = _cod_vendedor(l.get("cod_vendedor")) in time
            if cod not in da_zona:
                da_zona[cod] = [dele, l]
            elif dele:                       # outra loja do mesmo codigo
                da_zona[cod][0] = True
        for cod, (da_equipe, l) in da_zona.items():
            real = (realizado.get("clientes") or {}).get(cod) or {}
            if not da_equipe:
                # cliente de fora da carteira da equipe: entra inteiro
                # (positivacao e cadastro ja sobem da carteira nos outros)
                ex["clientes"] += 1
                ex["cadastros_no_mes"] += l.get("cadastrado_no_mes", 0)
                ex["cadastros_com_compra"] += l.get("cadastro_com_compra", 0)
                # (09/10) a positivacao agora e de quem vendeu: se a
                # equipe vendeu para ele, ja subiu pelo vendedor
                pv_ = real.get("por_vend") or {}
                da_eq_ = any((v_.get("liquido") or 0) > 0
                             for k_, v_ in pv_.items()
                             if _cod_vendedor(k_) in time)
                ex["positivados"] += 0 if da_eq_ else real.get("positivou", 0)
            # a VENDA: toda nota de quem nao e da equipe, seja o cliente da
            # carteira dela ou nao (a da equipe ja sobe pelo vendedor)
            for vend, v in (real.get("por_vend") or {}).items():
                if _cod_vendedor(vend) in time:
                    continue
                ex["faturado"] += v["faturado"]
                ex["devolvido"] += v["devolvido"]
                ex["realizado"] += v["liquido"]
                for k, _, _ in CATEGORIAS:
                    ex[f"real_{k}"] += v[f"real_{k}"]
        saida[nome] = ex
    return saida


def acompanhar(resultado: dict, realizado: dict, visitas=None,
               cadastros=None, hoje=None, feriados=(), par=None,
               zonas_supervisor=None, cad_visita=None) -> dict:
    """
    Junta a meta com o realizado e devolve os mesmos recortes, agora com
    META, REALIZADO, ATINGIMENTO e FALTA.

    A meta e do cliente-loja; o realizado vem por codigo de cliente (a
    ftPedidos nao traz a loja). Entao o realizado de um codigo e repartido
    entre as lojas dele na proporcao da meta - assim as duas pontas somam
    igual em qualquer recorte.
    """
    por_codigo: dict[str, list] = defaultdict(list)
    for c in resultado["clientes"]:
        por_codigo[c["cod_cliente"]].append(c)

    linhas = []
    vistos = set()
    for cod, lojas in por_codigo.items():
        real = realizado["clientes"].get(cod)
        vistos.add(cod)
        meta_total = sum(l["meta"] for l in lojas)
        for loja in lojas:
            fatia = ((loja["meta"] / meta_total) if meta_total
                     else 1.0 / len(lojas))
            linha = dict(loja)
            linha["fora_do_planner"] = False
            for campo in ("faturado", "devolvido", "liquido"):
                linha[campo] = (real[campo] * fatia) if real else 0.0
            for k, _, _ in CATEGORIAS:
                linha[f"real_{k}"] = (real[f"real_{k}"] * fatia) if real else 0.0
            linha["qtd_notas"] = real["qtd_notas"] if real else 0
            linha["vendedor_da_nota"] = real["vendedor_da_nota"] if real else ""
            # positivacao e do CLIENTE, nao da loja: conta uma vez so
            linha["positivou"] = (real["positivou"]
                                  if real and loja is lojas[0] else 0)
            linhas.append(linha)

    # A EQUIPE DE QUEM FATUROU E NAO ESTA NO PLANNER
    # O cliente pode estar fora do PLANNER por um motivo bobo - o bairro
    # dele ainda nao foi posto em nenhuma zona - e mesmo assim ele comprou.
    # Jogar isso numa linha solta faz o realizado do GERENTE nao fechar
    # com o do total. Entao, quando a nota diz QUAL VENDEDOR vendeu, o
    # faturamento sobe pela equipe DELE, com meta zero: aparece no
    # vendedor, no supervisor e no gerente certos.
    equipe = {}
    for c in resultado["clientes"]:
        if c["cod_vendedor"]:
            equipe.setdefault(c["cod_vendedor"], c)

    for cod, real in realizado["clientes"].items():
        if cod in vistos:
            continue
        dono = equipe.get(_texto(real.get("vendedor_da_nota")).zfill(6)) \
            or equipe.get(_texto(real.get("vendedor_da_nota")))
        sem_dono = dono is None
        linha = {
            "chave": f"{cod}-00", "cod_cliente": cod, "loja": "",
            "cliente": f"{FORA_DO_PLANNER} {cod}", "fantasia": "",
            "gerente": dono["gerente"] if dono else FORA_DO_PLANNER,
            "cod_gerente": dono["cod_gerente"] if dono else "",
            "supervisor": dono["supervisor"] if dono else FORA_DO_PLANNER,
            "cod_supervisor": dono["cod_supervisor"] if dono else "",
            "vendedor": dono["vendedor"] if dono else FORA_DO_PLANNER,
            "cod_vendedor": (dono["cod_vendedor"] if dono
                             else FORA_DO_PLANNER),
            "zona": FORA_DO_PLANNER, "cod_zona": FORA_DO_PLANNER,
            "segmento": (_segmento_do_codigo(realizado, cod)
                         or FORA_DO_PLANNER),
            "uf": dono["uf"] if dono else FORA_DO_PLANNER,
            "cidade": FORA_DO_PLANNER,
            "bairro": FORA_DO_PLANNER, "curva": "", "fat_m3m": 0.0,
            "fat_m6m": 0.0, "visitas": 0, "visitas_deposito": 0,
            "visitas_total": 0, "so_no_deposito": False,
            "peso": 0.0, "meta": 0.0, "meta_visita": 0.0,
            "conta_positivacao": 0, "meta_positivacao": 0.0,
            "ajustado": False, "fora_do_planner": True,
            "sem_dono": sem_dono,
            "faturado": real["faturado"], "devolvido": real["devolvido"],
            "liquido": real["liquido"], "qtd_notas": real["qtd_notas"],
            "vendedor_da_nota": real["vendedor_da_nota"],
            "positivou": real["positivou"],
        }
        for k, _, _ in CATEGORIAS:
            linha[f"meta_{k}"] = 0.0
            linha[f"real_{k}"] = real[f"real_{k}"]
        linhas.append(linha)

    # CADASTRO COM COMPRA: cliente CADASTRADO no mes que fez ALGUMA
    # venda no mes. A data de cadastro vem da BASE_CLIENTE (A1_DTCAD do
    # Protheus); a venda e a mesma positivacao que ja e apurada aqui.
    #
    # NAO se usa mais o A1_PRICOM (primeira compra): ele deixava de fora
    # quem foi cadastrado agora, comprou agora, mas ja tinha uma compra
    # antiga no Protheus - e nao e disso que se trata.
    comp_do_mes = _texto(realizado.get("competencia"))
    datas = cadastros or {}
    for linha in linhas:
        data = (datas.get(_texto(linha.get("cod_cliente")))
                or datas.get(_texto(linha.get("cod_cliente")).zfill(6)))
        novo = bool(data) and _mes_de(data) == comp_do_mes
        linha["cadastrado_no_mes"] = 1 if novo else 0
        linha["cadastro_com_compra"] = 1 if (novo and linha.get("positivou")) \
            else 0

    # A META DE CADA LINHA E A DO PAINEL, nao a soma dos clientes: cada
    # nivel tem a sua regra (o piso do vendedor, o rateio da UF...) e o
    # acompanhamento tem de medir contra a MESMA meta que foi dada.
    dias = dias_uteis_restantes(comp_do_mes, hoje, feriados)
    if zonas_supervisor is None:
        zonas_supervisor = zonas_dos_supervisores()
    extras_sup = _extras_das_zonas_do_supervisor(linhas, realizado,
                                                 zonas_supervisor)
    recortes = {r: _agrupar_acompanhamento(linhas, r) for r in RECORTES}
    _trocar_pelo_vendedor_da_nota(recortes, resultado, realizado)
    _aplicar_visitas(recortes, linhas, visitas or {}, cad_visita or {})
    for recorte in RECORTES:
        do_painel = {l["chave"]: l
                     for l in resultado.get("recortes", {}).get(recorte, [])}
        for linha in recortes[recorte]:
            fonte = do_painel.get(linha["chave"])
            if fonte is None:                 # faturou fora do PLANNER
                continue
            linha["meta"] = fonte["meta"]
            linha["meta_rh"] = fonte.get("meta_rh", fonte["meta"])
            linha["meta_calculada"] = fonte.get("meta_calculada", fonte["meta"])
            linha["faixa"] = fonte.get("faixa", "")
            linha["conta_na_meta"] = fonte.get("conta_na_meta", True)
            for campo in ("vendedores_fora", "zonas_fora", "meses_de_casa",
                          "faixa_rh"):
                if campo in fonte:
                    linha[campo] = fonte[campo]
            # A META DE VISITA e a de POSITIVACAO tambem vem do painel:
            # no supervisor elas ja descontam quem esta fora da meta do
            # mes. O REALIZADO nao: ele soma a carteira inteira.
            linha["meta_positivacao"] = fonte.get("meta_positivacao",
                                                  linha["meta_positivacao"])
            linha["meta_cadastro"] = fonte.get("meta_cadastro")
            if linha.get("meta_visita") is not None:
                linha["meta_visita"] = fonte.get("meta_visita",
                                                 linha["meta_visita"])
            for k, _, _ in CATEGORIAS:
                linha[f"meta_{k}"] = fonte[f"meta_{k}"]
            ex = (extras_sup.get(_texto(linha["chave"]).upper())
                  if recorte == "supervisor" else None)
            if ex:                    # os clientes das zonas do supervisor
                # so o RESULTADO: a meta fica a soma dos vendedores ativos
                for campo in ("faturado", "devolvido", "realizado",
                              "positivados", "cadastros_no_mes",
                              "cadastros_com_compra"):
                    linha[campo] = (linha.get(campo) or 0) + ex[campo]
                for k, _, _ in CATEGORIAS:
                    linha[f"real_{k}"] += ex[f"real_{k}"]
                linha["real_zonas_proprias"] = ex["realizado"]
                linha["clientes_zonas_proprias"] = ex["clientes"]
                linha["zonas_proprias"] = ", ".join(ex["zonas"])
                linha["conversao_cadastro"] = (
                    linha["cadastros_com_compra"] / linha["cadastros_no_mes"]
                    * 100.0 if linha.get("cadastros_no_mes") else 0.0)
                _refechar_acompanhamento(linha)
            linha["atingimento_positivacao"] = (
                linha["positivados"] / linha["meta_positivacao"] * 100.0
                if linha["meta_positivacao"] else 0.0)
            _fechar_visita(linha)
            _fechar_cadastro(linha)
            _refechar_acompanhamento(linha)
        for linha in recortes[recorte]:
            _fechar_gaps(linha, dias)
            _fechar_rh(linha, dias)
            # A REMUNERACAO VARIAVEL, pessoa a pessoa. So depois do
            # atingimento estar fechado - e dele que a faixa sai.
            linha.update(rv_da_linha(par, recorte, linha))
        recortes[recorte].sort(key=lambda x: (-x["meta"], -x["realizado"]))

    totais = {r: _total_acompanhamento(recortes[r]) for r in RECORTES}
    for recorte, linha in totais.items():
        _fechar_gaps(linha, dias)
        _fechar_rh(linha, dias)
        # no TOTAL a RV SE SOMA - e a folha daquele nivel. Diferente do
        # atingimento, que e uma divisao e nao se soma.
        tem_rv = any(l.get("rv_total") is not None
                     for l in recortes[recorte])
        for chave, _r, _a in KPIS_DA_RV:
            linha[f"rv_{chave}"] = (sum(l.get(f"rv_{chave}") or 0.0
                                        for l in recortes[recorte])
                                    if tem_rv else None)
        linha["rv_total"] = (sum(l.get("rv_total") or 0.0
                                 for l in recortes[recorte])
                             if tem_rv else None)
    geral = _fechar_acompanhamento("TOTAL", linhas)
    geral["meta_rh"] = (resultado.get("total") or {}).get("meta_rh")
    _fechar_gaps(geral, dias)
    _fechar_rh(geral, dias)
    return {
        "clientes": linhas,
        "recortes": recortes,
        "totais": totais,
        "total": geral,
        # a vista por FAMILIA DA PECA: a BAP inteira e cada pessoa. Nao
        # tem meta - e o mesmo faturamento aberto pelo que foi vendido.
        "familias": visao_por_familia(realizado, resultado, NIVEL_BAP),
        "familias_por_nivel": {
            nivel: {quem: visao_por_familia(realizado, resultado, nivel, quem)
                    for quem in pessoas_da_familia(realizado, resultado,
                                                   nivel)}
            for nivel in ("gerente", "supervisor", "vendedor")},
        "dias_restantes": dias,
        "dias_uteis_do_mes": len(dias_uteis_do_mes(comp_do_mes, feriados)),
        "competencia": realizado["competencia"],
        "mes": resultado.get("mes", ""),
        "sem_categoria": realizado.get("sem_categoria", 0),
        "com_csv": realizado.get("com_csv", False),
        "fora_do_planner": sum(1 for l in linhas if l["fora_do_planner"]),
        # os que nem pelo vendedor da nota deu para saber de quem sao
        "sem_dono": sum(1 for l in linhas if l.get("sem_dono")),
        "arquivo_planner": resultado.get("arquivo"),
        "arquivo_tabela": realizado.get("arquivo"),
    }


def _fechar_acompanhamento(rotulo: str, grupo: list) -> dict:
    linha = _fechar_linha(rotulo, grupo)
    linha["faturado"] = sum(c["faturado"] for c in grupo)
    linha["devolvido"] = sum(c["devolvido"] for c in grupo)
    linha["realizado"] = sum(c["liquido"] for c in grupo)
    # FATURAMENTO CARTEIRA: o que os CLIENTES desta linha faturaram, nao
    # importa quem bateu a nota. Nos recortes de pessoa o "realizado" e
    # trocado depois pelo que a PESSOA vendeu, e ai os dois numeros ficam
    # diferentes; nos demais recortes os dois sao a mesma coisa.
    linha["faturamento_carteira"] = linha["realizado"]
    linha["notas"] = sum(c["qtd_notas"] for c in grupo)
    linha["positivados"] = sum(c["positivou"] for c in grupo)
    # CADASTRO COM COMPRA: dois numeros, porque um so nao diz nada. O
    # primeiro e volume de prospeccao; o segundo, conversao.
    linha["cadastros_no_mes"] = sum(c.get("cadastrado_no_mes", 0)
                                    for c in grupo)
    linha["cadastros_com_compra"] = sum(c.get("cadastro_com_compra", 0)
                                        for c in grupo)
    linha["conversao_cadastro"] = (
        linha["cadastros_com_compra"] / linha["cadastros_no_mes"] * 100.0
        if linha["cadastros_no_mes"] else 0.0)
    linha["falta"] = linha["meta"] - linha["realizado"]
    linha["atingimento"] = (linha["realizado"] / linha["meta"] * 100.0
                            if linha["meta"] else 0.0)
    linha["atingimento_positivacao"] = (
        linha["positivados"] / linha["meta_positivacao"] * 100.0
        if linha["meta_positivacao"] else 0.0)
    _fechar_cadastro(linha)
    for k, _, _ in CATEGORIAS:
        linha[f"real_{k}"] = sum(c[f"real_{k}"] for c in grupo)
        linha[f"ating_{k}"] = (linha[f"real_{k}"] / linha[f"meta_{k}"] * 100.0
                               if linha[f"meta_{k}"] else 0.0)
    linha["fora_do_planner"] = all(c["fora_do_planner"] for c in grupo)
    return linha


def _aplicar_visitas(recortes: dict, clientes: list, visitas: dict,
                     cad_visita: dict | None = None) -> None:
    """
    Poe a VISITA REALIZADA (do CSV do mes) em quem visita: vendedor,
    supervisor e gerente. O vendedor casa pelo nome; o supervisor e o
    gerente sao a SOMA dos vendedores deles.

    Zona, cidade, bairro e cliente ficam SEM meta e SEM realizado de
    visita - eles nao visitam, sao visitados; misturar os dois so faria
    o numero parecer que existe.
    """
    feitas = {k: v for k, v in (visitas or {}).items() if k != "_nomes"}
    inteiro, curto = _casar_visitas(feitas)

    # quantas pessoas do PLANNER caem na mesma forma curta: se for mais
    # de uma, a forma curta nao serve para elas
    quantos_curtos = defaultdict(int)
    for linha in recortes["vendedor"]:
        quantos_curtos[chave_curta_de_nome(linha.get("nome")
                                           or linha["rotulo"])] += 1

    # o vendedor: casa pelo nome, e guarda de quem veio para somar acima
    do_vendedor = {}
    for linha in recortes["vendedor"]:
        nome = linha.get("nome") or linha["rotulo"]
        real = inteiro.get(chave_de_nome(nome))
        linha["visita_por_apelido"] = False
        if real is None:
            # o arquivo escreve o nome inteiro e o cadastro, o curto:
            # tenta PRIMEIRO NOME + ULTIMO SOBRENOME, mas so quando ele
            # aponta para uma pessoa so dos dois lados
            c = chave_curta_de_nome(nome)
            if c and quantos_curtos.get(c, 0) == 1 and c in curto:
                real = curto[c]
                linha["visita_por_apelido"] = True
        if real is None:
            # (10/11, check do Farol de Metas x Farol de Visita) o Planner
            # escreve o COMECO do nome e o arquivo, o nome inteiro
            # ("JUGLAISON RODRIGUES" x "JUGLAISON RODRIGUES DOS PRAZES"):
            # vale quando um nome so do arquivo comeca com o do Planner
            ch_ = chave_de_nome(nome)
            cand_ = [k for k in inteiro if ch_ and k.startswith(ch_ + " ")]
            if len(cand_) == 1:
                real = inteiro[cand_[0]]
                linha["visita_por_apelido"] = True
        linha["visitas_realizadas"] = float(real or 0.0)
        # (15/10, Alexandre) CADASTRO NOVO CONTA COMO VISITA: os clientes
        # que o vendedor cadastrou no mes (A1_DTCAD, A1_VEND) somam na
        # visita realizada - inclusive na RV de visita
        cad_ = float((cad_visita or {}).get(_texto(linha.get("chave"))
                                             .zfill(6), 0) or 0)
        linha["cadastros_como_visita"] = cad_
        linha["visitas_realizadas"] += cad_
        linha["visita_casou"] = real is not None
        if linha["chave"]:
            do_vendedor[linha["chave"]] = linha["visitas_realizadas"]

    equipe = defaultdict(set)
    chefe = {}
    for c in clientes:
        if not c.get("cod_vendedor"):
            continue
        equipe[("supervisor", c.get("supervisor", ""))].add(c["cod_vendedor"])
        equipe[("gerente", c.get("gerente", ""))].add(c["cod_vendedor"])
        chefe.setdefault(c["cod_vendedor"], True)
    for recorte in ("supervisor", "gerente"):
        for linha in recortes[recorte]:
            seus = equipe.get((recorte, linha["chave"]), set())
            linha["visitas_realizadas"] = sum(do_vendedor.get(v, 0.0)
                                              for v in seus)
            linha["visita_casou"] = bool(seus)

    # quem nao visita nao tem nem meta nem realizado de visita
    for recorte in RECORTES:
        if recorte in RECORTES_COM_VISITA:
            continue
        for linha in recortes[recorte]:
            linha["meta_visita"] = None
            linha["visitas_realizadas"] = None
            linha["visita_casou"] = False

    for recorte in RECORTES:
        for linha in recortes[recorte]:
            _fechar_visita(linha)


def _fechar_visita(linha: dict) -> None:
    meta = linha.get("meta_visita")
    real = linha.get("visitas_realizadas")
    if meta is None or real is None:
        linha["atingimento_visita"] = None
        return
    linha["atingimento_visita"] = (real / meta * 100.0) if meta else 0.0


def _fechar_cadastro(linha: dict) -> None:
    """O atingimento do CADASTRO COM COMPRA, quando a linha tem meta."""
    meta = linha.get("meta_cadastro")
    real = linha.get("cadastros_com_compra")
    if meta is None or real is None:
        linha["atingimento_cadastro"] = None
        return
    linha["atingimento_cadastro"] = (real / meta * 100.0) if meta else 0.0


def _refechar_acompanhamento(linha: dict) -> None:
    """Depois que a META da linha mudou, o que depende dela acompanha."""
    linha["falta"] = linha["meta"] - linha["realizado"]
    linha["atingimento"] = (linha["realizado"] / linha["meta"] * 100.0
                            if linha["meta"] else 0.0)
    for k, _, _ in CATEGORIAS:
        linha[f"ating_{k}"] = (linha[f"real_{k}"] / linha[f"meta_{k}"] * 100.0
                               if linha[f"meta_{k}"] else 0.0)


def _total_acompanhamento(linhas: list) -> dict:
    """A linha TOTAL de UMA aba do acompanhamento: a soma daquela aba."""
    soma = total_do_recorte(linhas, "TOTAL")
    # limite_disponivel e valor_em_atraso NAO sao do acompanhamento da
    # meta - sao da lista de oportunidade, que usa esta mesma soma. Sem
    # eles aqui, a linha TOTAL da lista de clientes mostrava 0,00 no
    # limite, ao lado de um rodape que dizia 4,5 milhoes.
    for campo in ("faturado", "devolvido", "realizado", "faturamento_carteira",
                  "notas", "positivados", "visitas_realizadas",
                  "cadastros_no_mes", "cadastros_com_compra",
                  "limite_disponivel", "valor_em_atraso"):
        soma[campo] = sum(l.get(campo) or 0 for l in linhas)
    soma["conversao_cadastro"] = (
        soma["cadastros_com_compra"] / soma["cadastros_no_mes"] * 100.0
        if soma["cadastros_no_mes"] else 0.0)
    if not any(l.get("meta_cadastro") is not None for l in linhas):
        soma["meta_cadastro"] = None
    _fechar_cadastro(soma)
    if not any(l.get("meta_visita") is not None for l in linhas):
        soma["meta_visita"] = None
        soma["visitas_realizadas"] = None
    _fechar_visita(soma)
    for k, _, _ in CATEGORIAS:
        soma[f"real_{k}"] = sum(l.get(f"real_{k}") or 0 for l in linhas)
    soma["fora_do_planner"] = False
    soma["atingimento_positivacao"] = (
        soma["positivados"] / soma["meta_positivacao"] * 100.0
        if soma["meta_positivacao"] else 0.0)
    _refechar_acompanhamento(soma)
    return soma


def _agrupar_acompanhamento(clientes: list, recorte: str) -> list:
    grupos: dict[str, list] = defaultdict(list)
    rotulos: dict[str, str] = {}
    for c in clientes:
        k = chave_da_linha(recorte, c)
        grupos[k].append(c)
        rotulos.setdefault(k, _rotulo(recorte, c))
    saida = []
    for k, grupo in grupos.items():
        linha = _fechar_acompanhamento(rotulos[k], grupo)
        linha["chave"] = k
        linha["recorte"] = recorte
        linha["codigo"], linha["nome"] = codigo_e_nome(recorte, grupo[0])
        # ATIVO e CONTA NA META viajam com a linha para a tela poder
        # esconder cadeira vaga e quem esta fora da meta do mes
        linha["vendedor_ativo"] = bool(grupo[0].get("vendedor_ativo", True))
        # NA VISAO VENDEDOR, DE QUEM ELE E: sem isto a folha do vendedor
        # obriga a ir ate a aba do supervisor para saber quem responde
        # por quem
        linha["cod_supervisor"], linha["supervisor"] = _chefe_do_grupo(recorte,
                                                                      grupo)
        saida.append(linha)
    return sorted(saida, key=lambda x: (-x["meta"], -x["realizado"]))


# --------------------------------------------------------------------------
# o Excel do acompanhamento: resumo gerencial + ANALITICO
# --------------------------------------------------------------------------
# AS OITO METAS, SEMPRE NESTA ORDEM, e cada uma com o seu quinteto
# META / REAL / ATING% / GAP / NEC. DIA coladinho - para ler de uma vez.
#
#   GAP MES ... o que falta para bater a meta no mes (meta - realizado).
#               Negativo quer dizer que ja passou.
#   NEC./DIA .. esse GAP dividido pelos DIAS UTEIS QUE AINDA FALTAM no
#               mes, contando hoje. E o numero que o vendedor leva para a
#               rua: "tenho de fazer isto por dia daqui ate o fim".
#               Mes ja fechado (ou ainda por comecar) nao tem dia
#               restante: ali a coluna fica VAZIA, em vez de mentir.
#
#   (rotulo, meta, realizado, atingimento, gap do mes, necessario/dia)
METAS_DO_ACOMPANHAMENTO = [
    ("VISITA", "meta_visita_int", "visitas_realizadas",
     "atingimento_visita", "gap_visita", "nec_visita"),
    ("POSITIVACAO", "meta_positivacao_int", "positivados",
     "atingimento_positivacao", "gap_positivacao", "nec_positivacao"),
    ("CAD. COMPRA", "meta_cadastro_int", "cadastros_com_compra",
     "atingimento_cadastro", "gap_cadastro", "nec_cadastro"),
    # no faturamento o GAP e a FALTA que sempre existiu - e o mesmo
    # numero, e ter duas colunas com ele so confundiria
    ("FAT TOTAL", "meta", "realizado", "atingimento", "falta", "nec_fat"),
    ("PECAS", "meta_pecas", "real_pecas", "ating_pecas", "gap_pecas",
     "nec_pecas"),
    ("LUBRIF.", "meta_lubrificante", "real_lubrificante",
     "ating_lubrificante", "gap_lubrificante", "nec_lubrificante"),
    ("BATERIA", "meta_bateria", "real_bateria", "ating_bateria",
     "gap_bateria", "nec_bateria"),
    ("PNEU", "meta_pneu", "real_pneu", "ating_pneu", "gap_pneu",
     "nec_pneu"),
]
# os indicadores que se CONTAM (gente, visita) - o resto e dinheiro
METAS_DE_CONTAGEM = {"VISITA", "POSITIVACAO", "CAD. COMPRA"}
# compatibilidade com quem so quer o trio
TRIO_DAS_METAS = [(r, m, real, at)
                  for r, m, real, at, _, _ in METAS_DO_ACOMPANHAMENTO]

COLUNAS_ACOMPANHAMENTO = (
    [("RECORTE", "recorte", 14, None),
     ("CODIGO", "codigo", 14, None),
     ("NOME", "nome", 34, None),
     # de quem o VENDEDOR responde. Vazio nos recortes que nao sao de
     # pessoa - zona e cidade nao tem supervisor.
     ("SUPERVISOR", "supervisor", 30, None),
     ("QTD CLI.", "clientes", 10, None)]
    + [c for rotulo, meta, real, ating, gap, nec in METAS_DO_ACOMPANHAMENTO
       for c in ((f"META {rotulo}", meta, 17,
                  "#,##0" if rotulo in METAS_DE_CONTAGEM else "#,##0.00"),
                 (f"REAL {rotulo}", real, 17,
                  "#,##0" if rotulo in METAS_DE_CONTAGEM else "#,##0.00"),
                 (f"ATING {rotulo} %", ating, 17, "#,##0.0"),
                 (f"GAP MES {rotulo}", gap, 18,
                  "#,##0" if rotulo in METAS_DE_CONTAGEM else "#,##0.00"),
                 (f"NEC./DIA {rotulo}", nec, 18,
                  "#,##0.0" if rotulo in METAS_DE_CONTAGEM
                  else "#,##0.00"))]
    # a META RH de faturamento (a que paga a RV), ao lado da comercial
    + [("META FAT TOTAL RH", "meta_rh", 17, "#,##0.00"),
       ("ATING FAT TOTAL RH %", "atingimento_rh", 19, "#,##0.0"),
       ("NEC./DIA FAT TOTAL RH", "nec_fat_rh", 20, "#,##0.00")]
    # A REMUNERACAO VARIAVEL: um valor por KPI e o total a pagar. Vem
    # depois dos indicadores porque e consequencia deles - primeiro o
    # atingimento, depois quanto ele paga.
    + [(f"RV {rotulo} R$", f"rv_{chave}", 15, "#,##0.00")
       for chave, rotulo, _ in KPIS_DA_RV]
    + [("RV TOTAL R$", "rv_total", 15, "#,##0.00")]
    + [("CADASTROS NO MES", "cadastros_no_mes", 17, None),
       ("CONVERSAO CADASTRO %", "conversao_cadastro", 21, "#,##0.0"),
       ("BASE VISITA", "base_visita", 13, None),
       ("BASE TOTAL", "base_carteira", 13, None),
       ("DIAS UTEIS QUE FALTAM", "dias_restantes", 22, None),
       ("FATURAMENTO CARTEIRA R$", "faturamento_carteira", 24, "#,##0.00"),
       ("FATURADO R$", "faturado", 16, "#,##0.00"),
       ("DEVOLVIDO R$", "devolvido", 16, "#,##0.00"),
       ("NOTAS", "notas", 9, None),
       ("CONTA NA META DO SUP.", "conta_na_meta_txt", 22, None),
       ("LINHA", "rotulo", 42, None)]
)

COLUNAS_ANALITICO = [
    ("COD_CLIENTE", "cod_cliente", 13, None),
    ("LOJA", "loja", 7, None),
    ("CLIENTE", "cliente", 40, None),
    ("NOME_FANTASIA", "fantasia", 28, None),
    ("COD_GERENTE", "cod_gerente", 13, None),
    ("GERENTE", "gerente", 24, None),
    ("COD_SUPERVISOR", "cod_supervisor", 15, None),
    ("SUPERVISOR", "supervisor", 24, None),
    ("COD_VENDEDOR", "cod_vendedor", 14, None),
    ("VENDEDOR", "vendedor", 26, None),
    ("COD_ZONA", "cod_zona", 11, None),
    ("ZONA", "zona", 28, None),
    ("UF", "uf", 5, None),
    ("CIDADE", "cidade", 22, None),
    ("BAIRRO", "bairro", 22, None),
    ("CURVA", "curva", 7, None),
    ("FAT_M3M R$", "fat_m3m", 15, "#,##0.00"),
    ("FAT_M3M ANTERIOR R$", "fat_m3m_anterior", 20, "#,##0.00"),
    ("SO NO SABADO", "so_no_deposito_txt", 14, None),
    ("VISITAS NA ROTA", "visitas", 16, None),
    ("VISITAS NO DEPOSITO", "visitas_deposito", 20, None),
    ("META FATURAMENTO R$", "meta", 20, "#,##0.00"),
    ("REALIZADO R$", "liquido", 17, "#,##0.00"),
    ("ATINGIMENTO %", "atingimento", 15, "#,##0.0"),
    ("FALTA R$", "falta", 16, "#,##0.00"),
    ("FATURADO R$", "faturado", 16, "#,##0.00"),
    ("DEVOLVIDO R$", "devolvido", 16, "#,##0.00"),
    ("NOTAS", "qtd_notas", 9, None),
    ("POSITIVOU", "positivou_txt", 11, None),
    ("META PECAS R$", "meta_pecas", 17, "#,##0.00"),
    ("REAL PECAS R$", "real_pecas", 17, "#,##0.00"),
    ("META BATERIA R$", "meta_bateria", 17, "#,##0.00"),
    ("REAL BATERIA R$", "real_bateria", 17, "#,##0.00"),
    ("META LUBRIFICANTE R$", "meta_lubrificante", 21, "#,##0.00"),
    ("REAL LUBRIFICANTE R$", "real_lubrificante", 21, "#,##0.00"),
    ("META PNEU R$", "meta_pneu", 16, "#,##0.00"),
    ("REAL PNEU R$", "real_pneu", 16, "#,##0.00"),
    ("QUEM FATUROU", "vendedor_da_nota", 18, None),
    ("META A MAO", "ajustado_txt", 12, None),
]


def _folha(wb, titulo, colunas, linhas, total=None):
    from openpyxl.styles import Alignment, Font, PatternFill
    ws = wb.create_sheet(titulo[:31])
    ws.append([t for t, _, _, _ in colunas])
    cabecalho = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)
    for i, (_, _, largura, _) in enumerate(colunas, start=1):
        ws.cell(1, i).fill = cabecalho
        ws.cell(1, i).font = branco
        ws.cell(1, i).alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
    for linha in linhas:
        ws.append([linha.get(k) for _, k, _, _ in colunas])
    if total is not None:
        ws.append([total.get(k) for _, k, _, _ in colunas])
        for j in range(1, len(colunas) + 1):
            ws.cell(ws.max_row, j).font = Font(bold=True, size=9)
    for j, (_, _, _, formato) in enumerate(colunas, start=1):
        if formato:
            for n in range(2, ws.max_row + 1):
                ws.cell(n, j).number_format = formato
    ws.freeze_panes = "A2"
    ultima = ws.max_row - (1 if total is not None else 0)
    if ultima > 1:
        ws.auto_filter.ref = (f"A1:{ws.cell(1, len(colunas)).column_letter}"
                              f"{ultima}")
    return ws


def gravar_excel_acompanhamento(ac: dict, par: dict, caminho) -> Path:
    """
    O arquivo que vai para o RH: uma aba por recorte com o resumo, MAIS a
    aba ANALITICO com o resultado cliente a cliente - e a aba PARAMETROS
    dizendo de onde cada numero saiu.
    """
    from openpyxl import Workbook

    caminho = Path(caminho)
    wb = Workbook()
    wb.remove(wb.active)

    for recorte in RECORTES:
        linhas = []
        for linha in ac["recortes"][recorte]:
            copia = _arredondar_metas(linha)
            copia["recorte"] = TITULO_DO_RECORTE[recorte]
            linhas.append(copia)
        total = _arredondar_metas(ac.get("totais", {}).get(recorte)
                                  or ac["total"])
        total["recorte"] = "TOTAL"
        total["rotulo"] = f"TOTAL DE {TITULO_DO_RECORTE[recorte]}"
        _folha(wb, TITULO_DO_RECORTE[recorte], COLUNAS_ACOMPANHAMENTO,
               linhas, total)

    # O ANALITICO: uma linha por cliente, com meta e realizado lado a lado
    analitico = []
    for c in sorted(ac["clientes"], key=lambda x: (-x["meta"], -x["liquido"])):
        linha = dict(c)
        linha["atingimento"] = (c["liquido"] / c["meta"] * 100.0
                                if c["meta"] else 0.0)
        linha["falta"] = c["meta"] - c["liquido"]
        linha["positivou_txt"] = "SIM" if c["positivou"] else ""
        linha["so_no_deposito_txt"] = "SIM" if c.get("so_no_deposito") else ""
        linha["ajustado_txt"] = "SIM" if c.get("ajustado") else ""
        analitico.append(linha)
    _folha(wb, "ANALITICO", COLUNAS_ANALITICO, analitico)

    # A FAMILIA DA PECA: a BAP inteira e depois pessoa a pessoa. Sem
    # meta de proposito - quem tem meta sao as quatro categorias.
    familias = []
    for l in (ac.get("familias") or []):
        familias.append({**l, "nivel": "BAP", "quem": "BAP INTEIRA"})
    for nivel in ("gerente", "supervisor", "vendedor"):
        for quem, linhas_f in (ac.get("familias_por_nivel") or {}).get(
                nivel, {}).items():
            for l in linhas_f:
                familias.append({**l, "nivel": TITULO_DO_RECORTE[nivel],
                                 "quem": quem})
    if familias:
        _folha(wb, "FAMILIA", COLUNAS_FAMILIA_EXCEL, familias)

    # A TABELA DA RV, do jeito que o RH confere: uma linha por faixa. O
    # valor que aparece em cada pessoa sai DAQUI, e nao de outra planilha.
    _rv = []
    for nivel, rotulo_nivel in NIVEIS_DA_RV:
        for kpi, rotulo_kpi, _campo in KPIS_DA_RV:
            for faixa in faixas_da_rv(par, nivel, kpi):
                ate = _numero(faixa.get("ate"))
                _rv.append({
                    "nivel": rotulo_nivel, "kpi": rotulo_kpi,
                    "de": _numero(faixa.get("de")),
                    # o teto nao e um numero que alguem atinge: e "dai
                    # para cima". Escrito assim, ninguem erra a leitura.
                    "ate": (None if ate >= TETO_DA_FAIXA else ate),
                    "valor": _numero(faixa.get("valor"))})
    if _rv:
        _folha(wb, "RV",
               [("NIVEL", "nivel", 16, None),
                ("INDICADOR", "kpi", 18, None),
                ("DE %", "de", 12, "#,##0.000"),
                ("ATE % (vazio = dai para cima)", "ate", 28, "#,##0.000"),
                ("PAGA R$", "valor", 15, "#,##0.00")], _rv)

    ws = wb.create_sheet("PARAMETROS")
    ws.append(["PARAMETRO", "VALOR"])
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 30
    for titulo, valor in (
            ("Competencia", ac.get("competencia", "")),
            ("Mes da rota", ac.get("mes", "")),
            ("PLANNER usado", str(ac.get("arquivo_planner") or "")),
            ("TABELA_BAP usada", str(ac.get("arquivo_tabela") or "")),
            ("Como a meta e calculada",
             "M3M atual x M3M anterior no cliente e no vendedor; "
             "rateio da META GERAL na UF e no gerente"),
            ("META GERAL (R$) - so no modo rateio",
             float(par.get("meta_geral") or 0)),
            ("Piso por CLIENTE (R$)", float(par.get("piso_cliente") or 0)),
            ("Piso por VENDEDOR (R$)", float(par.get("piso_vendedor") or 0)),
            ("Piso por ZONA (R$)", float(par.get("piso_zona") or 0)),
            ("O piso do cliente vale so para quem ja comprou",
             "SIM" if par.get("piso_so_com_faturamento", True) else "NAO"),
            ("META VISITA (% das visitas)", par.get("pct_visita")),
            ("POSITIVACAO (% dos clientes)", par.get("pct_positivacao")),
            ("Realizado = TIPO VND/VEA + DEV (a devolucao ja e negativa)", ""),
            ("Clientes que faturaram e nao estao no PLANNER",
             ac.get("fora_do_planner", 0)),
            ("Categoria dos produtos",
             "CATEGORIAS_PRODUTO.csv" if ac.get("com_csv")
             else "pelo FORNECEDOR (sem o CSV nao ha bateria nem pneu)"),
            ("Itens sem classificacao de categoria (foram para PECAS)",
             ac.get("sem_categoria", 0)),
    ):
        ws.append([titulo, valor])
    for chave, rotulo, _ in CATEGORIAS:
        ws.append([f"{rotulo} (% da meta de faturamento)",
                   (par.get("categorias") or {}).get(chave)])
    for uf, pcts in sorted((par.get("por_uf") or {}).items()):
        ws.append([f"UF {uf}", json.dumps(pcts, ensure_ascii=False)])
    for zona, pcts in sorted((par.get("por_zona") or {}).items()):
        ws.append([f"ZONA {zona}", json.dumps(pcts, ensure_ascii=False)])
    for forn, cat in sorted((par.get("categoria_por_fornecedor") or {}).items()):
        ws.append([f"FORNECEDOR {forn}", cat])

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def nome_do_acompanhamento(competencia: str = "") -> str:
    """
    O arquivo unico que vai para o RH: a meta, o realizado e o analitico
    daquele mes, num arquivo so. Nao se confunde com o
    ACOMPANHAMENTO_META_BAP.xlsx, que e o arquivo QUE FICA, com todos os
    meses.
    """
    return f"META_RH_BAP_{marca_do_mes(competencia)}.xlsx"


# ==========================================================================
# O ARQUIVO UNICO DAS METAS
# ==========================================================================
"""
Todas as metas moram num arquivo so, na pasta RELATORIOS:

    ACOMPANHAMENTO_META_BAP.xlsx
        202609    <- uma aba por MES, com o resumo de todos os recortes
        202610
        ANALITICO <- UMA aba so, com todos os meses e uma coluna MES para
                     voce filtrar

Gerar a meta de um mes REESCREVE a aba daquele mes e troca as linhas
daquele mes no ANALITICO - os outros meses continuam intactos. Assim o
historico se acumula sozinho, sem virar uma pasta cheia de arquivos.

O botao EXPORTAR PARA O RH e outra coisa: ele gera um arquivo separado,
do mes, com a meta E o realizado E o analitico - o que vai por e-mail.
"""


def _apagar_aba(wb, nome):
    if nome in wb.sheetnames:
        wb.remove(wb[nome])


def _analitico_das_linhas(clientes: list, competencia: str) -> list:
    saida = []
    for c in sorted(clientes, key=lambda x: -x["meta"]):
        linha = dict(c)
        linha["mes"] = competencia
        linha["positivou_txt"] = "SIM" if c.get("positivou") else ""
        linha["ajustado_txt"] = "SIM" if c.get("ajustado") else ""
        linha["so_no_deposito_txt"] = "SIM" if c.get("so_no_deposito") else ""
        linha["liquido"] = c.get("liquido", 0.0)
        linha["faturado"] = c.get("faturado", 0.0)
        linha["devolvido"] = c.get("devolvido", 0.0)
        linha["qtd_notas"] = c.get("qtd_notas", 0)
        linha["vendedor_da_nota"] = c.get("vendedor_da_nota", "")
        linha["atingimento"] = (linha["liquido"] / c["meta"] * 100.0
                                if c["meta"] else 0.0)
        linha["falta"] = c["meta"] - linha["liquido"]
        saida.append(linha)
    return saida


COLUNAS_ANALITICO_MES = [("MES", "mes", 10, None)] + COLUNAS_ANALITICO


def guardar_meta_do_mes(resultado: dict, par: dict, raiz,
                        competencia: str = "") -> Path:
    """
    Grava (ou regrava) a aba daquele mes no ACOMPANHAMENTO_META_BAP.xlsx e
    atualiza as linhas dele no ANALITICO. Os outros meses nao sao tocados.
    """
    from openpyxl import Workbook, load_workbook as _abrir

    raiz = Path(raiz)
    competencia = competencia or resultado.get("competencia", "")
    aba_mes = marca_do_mes(competencia)
    destino = raiz / RELATORIOS_SUB / ARQUIVO_ACOMPANHAMENTO
    destino.parent.mkdir(parents=True, exist_ok=True)

    # o que ja existe no ANALITICO dos OUTROS meses continua la
    antigas = []
    if destino.exists():
        try:
            velho = _abrir(destino, read_only=True, data_only=True)
            if ABA_ANALITICO in velho.sheetnames:
                ws = velho[ABA_ANALITICO]
                it = ws.iter_rows(values_only=True)
                cab = list(next(it))
                for r in it:
                    linha = dict(zip(cab, r))
                    if _texto(linha.get("MES")) != competencia:
                        antigas.append(linha)
            velho.close()
        except (OSError, ValueError, StopIteration):
            antigas = []

    wb = _abrir(destino) if destino.exists() else Workbook()
    if not destino.exists():
        wb.remove(wb.active)
    _apagar_aba(wb, aba_mes)
    _apagar_aba(wb, ABA_ANALITICO)

    # a aba do mes: todos os recortes empilhados, com a coluna RECORTE
    linhas = []
    for recorte in RECORTES:
        for linha in resultado["recortes"][recorte]:
            copia = _arredondar_metas(linha)
            copia["recorte"] = TITULO_DO_RECORTE[recorte]
            linhas.append(copia)
        fecha = _arredondar_metas(resultado.get("totais", {}).get(recorte)
                                  or resultado["total"])
        fecha["recorte"] = f"TOTAL {TITULO_DO_RECORTE[recorte]}"
        fecha["rotulo"] = f"TOTAL DE {TITULO_DO_RECORTE[recorte]}"
        linhas.append(fecha)
    # A META POR FAMILIA DA PECA (a BAP inteira; soma = meta comercial)
    fams = resultado.get("familias") or []
    for f in fams:
        linhas.append({"recorte": "FAMILIA", "codigo": "",
                       "nome": f["familia"], "rotulo": f["familia"],
                       "meta": f["meta"], "fat_m3m": f["m3m"],
                       "base_carteira": f["clientes_m3m"],
                       "faixa": "meta do cliente x peso da familia no M3M"})
    if fams:
        linhas.append({"recorte": "TOTAL FAMILIA", "codigo": "",
                       "rotulo": "TOTAL DE FAMILIA",
                       "meta": sum(f["meta"] for f in fams),
                       "fat_m3m": sum(f["m3m"] for f in fams)})
    # A META POR CATEGORIA BAP (linha leve, pesada, moto, pneu, bateria,
    # lubrificantes; soma = meta comercial)
    cats = resultado.get("categorias_bap") or []
    for f in cats:
        linhas.append({"recorte": "CATEGORIA", "codigo": "",
                       "nome": f["familia"], "rotulo": f["familia"],
                       "meta": f["meta"], "fat_m3m": f["m3m"],
                       "base_carteira": f["clientes_m3m"],
                       "faixa": "meta do cliente x peso da categoria no M3M"})
    if cats:
        linhas.append({"recorte": "TOTAL CATEGORIA", "codigo": "",
                       "rotulo": "TOTAL DE CATEGORIA",
                       "meta": sum(f["meta"] for f in cats),
                       "fat_m3m": sum(f["m3m"] for f in cats)})
    total = _arredondar_metas(resultado["total"])
    total["recorte"] = "TOTAL"
    total["rotulo"] = "BAP INTEIRA (a soma dos clientes)"
    _folha(wb, aba_mes, COLUNAS_EXCEL, linhas, total)

    # o ANALITICO: os meses de antes mais o de agora
    novas = _analitico_das_linhas(resultado["clientes"], competencia)
    # as antigas vem do arquivo (chaveadas pelo TITULO da coluna)
    antigas_ok = []
    for a in antigas:
        antigas_ok.append({chave: a.get(titulo)
                           for titulo, chave, _, _ in COLUNAS_ANALITICO_MES})
    _folha(wb, ABA_ANALITICO, COLUNAS_ANALITICO_MES, antigas_ok + novas)

    # as abas de mes ficam em ordem, e o ANALITICO no fim
    wb._sheets.sort(key=lambda f: ("2" if f.title == ABA_ANALITICO
                                   else "0" if f.title.isdigit() else "1",
                                   f.title))
    wb.save(destino)
    return destino


def meses_no_arquivo(raiz) -> list:
    """Os meses que ja estao gravados no ACOMPANHAMENTO_META_BAP.xlsx."""
    destino = Path(raiz) / RELATORIOS_SUB / ARQUIVO_ACOMPANHAMENTO
    if not destino.exists():
        return []
    try:
        wb = load_workbook(destino, read_only=True)
        nomes = sorted(n for n in wb.sheetnames if n.isdigit())
        wb.close()
        return nomes
    except (OSError, ValueError):
        return []


# ==========================================================================
# A BASE DE OPORTUNIDADE - a aba 3 vista como lista de ataque
# ==========================================================================
# A meta diz quanto falta; esta parte diz A QUEM IR ATRAS. Junta, por
# cliente: o que a meta ja sabe (meta, realizado, vendedor, zona), o que a
# BASE_CLIENTE sabe (limite disponivel, valor em atraso, dias sem compra,
# status, endereco) e o que a TABELA_BAP sabe (o ultimo item comprado).
ARQUIVO_BASE_CLIENTE = "BASE_CLIENTE.xlsx"


def _achar_base_cliente(raiz):
    raiz = Path(raiz)
    for tentativa in (raiz / RELATORIOS_SUB / ARQUIVO_BASE_CLIENTE,
                      raiz / ARQUIVO_BASE_CLIENTE):
        if tentativa.exists():
            return tentativa
    return None


def ler_cadastro_do_cliente(caminho) -> dict:
    """
    Da BASE_CLIENTE: o que a meta nao tem e a hora do ataque precisa.
    Chaveado por "codigo-loja" e tambem so pelo codigo (a ftPedidos nao
    traz loja).
    """
    caminho = Path(caminho) if caminho else None
    if not caminho or not caminho.exists():
        return {}
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
        ws = wb["BASE_CLIENTE"] if "BASE_CLIENTE" in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        cab = [_texto(c) for c in next(it)]
    except (OSError, ValueError, StopIteration, KeyError):
        return {}

    def em(nome):
        return cab.index(nome) if nome in cab else None

    i = {n: em(n) for n in (
        "COD_CLIENTE", "LOJA", "LIMITE_APROVADO", "LIMITE_DISPONIVEL",
        "EM_ABERTO", "VALOR_EM_ATRASO", "DIAS_ATRASO", "DIAS_SEM_COMPRA",
        "ULTIMA_COMPRA", "STATUS_CLIENTE", "ENDERECO", "NUMERO", "CONTATO",
        "DDD", "TELEFONE",
        "QTD_NOTAS", "MEDIA_MENSAL", "CURVA_RECEITA",
        # A1_DTCAD do Protheus: o dia em que a ficha foi aberta. E o que
        # diz se o cliente e NOVO - sem ela nao da para separar o cadastro
        # de ontem do cadastro de 2021 que nunca girou.
        "DATA_CADASTRO", "DATA_1A_COMPRA")}
    saida = {}
    for r in it:
        if i["COD_CLIENTE"] is None:
            break
        cod = _texto(r[i["COD_CLIENTE"]]).zfill(6)
        loja = _texto(r[i["LOJA"]]) if i["LOJA"] is not None else ""
        reg = {}
        for nome, pos in i.items():
            if pos is not None and pos < len(r):
                reg[nome.lower()] = r[pos]
        reg["cod_cliente"] = cod
        reg["loja"] = loja
        saida[f"{cod}-{loja or '00'}"] = reg
        saida.setdefault(cod, reg)          # sem loja, vale o primeiro
    wb.close()
    return saida


def datas_de_cadastro(caminho) -> dict:
    """
    {codigo do cliente: data de cadastro}, da BASE_CLIENTE.

    E o que falta para medir CADASTRO COM COMPRA por vendedor: o PLANNER
    nao carrega a data de cadastro do Protheus (A1_DTCAD), a BASE_CLIENTE
    carrega. Le so as duas colunas, para ser barato.
    """
    caminho = Path(caminho) if caminho else None
    if not caminho or not caminho.exists():
        return {}
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
        ws = wb["BASE_CLIENTE"] if "BASE_CLIENTE" in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        cab = [_texto(c) for c in next(it)]
    except (OSError, ValueError, StopIteration, KeyError):
        return {}
    if "COD_CLIENTE" not in cab or "DATA_CADASTRO" not in cab:
        wb.close()
        return {}
    i_cod, i_cad = cab.index("COD_CLIENTE"), cab.index("DATA_CADASTRO")
    saida = {}
    for r in it:
        if i_cad >= len(r):
            continue
        data = _data(r[i_cad])
        if data is None:
            continue
        saida[_texto(r[i_cod]).zfill(6)] = data
    wb.close()
    return saida


def ultimo_item_comprado(caminho_tabela, nomes=None) -> dict:
    """
    O ULTIMO item que cada cliente comprou, pela ftPedidos: codigo,
    descricao (do CATEGORIAS_PRODUTO.csv, quando ha) e quantidade.
    So conta venda - devolucao e transferencia nao entram.
    """
    caminho_tabela = Path(caminho_tabela)
    if not caminho_tabela.exists():
        return {}
    try:
        wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
        if "ftPedidos" not in wb.sheetnames:
            wb.close()
            return {}
        ws = wb["ftPedidos"]
        it = ws.iter_rows(values_only=True)
        cab = [_texto(c) for c in next(it)]
    except (OSError, ValueError, StopIteration, KeyError):
        return {}

    def em(*n):
        for x in n:
            if x in cab:
                return cab.index(x)
        return None

    i_cli, i_tipo = em("D2_CLIENTE"), em("TIPO")
    i_cod, i_qtd = em("D2_COD"), em("D2_QUANT")
    i_nf, i_em = em("DATA_NF"), em("D2_EMISSAO")
    i_val = em("VALOR TOTAL", "VALOR_TOTAL")
    if i_cli is None or i_cod is None:
        wb.close()
        return {}

    nomes = nomes or {}
    ultimo = {}
    for r in it:
        if i_tipo is not None and _texto(r[i_tipo]).upper() not in TIPOS_VENDA:
            continue
        cod = _texto(r[i_cli]).zfill(6)
        d = _data(r[i_nf] if i_nf is not None else None) \
            or _data(r[i_em] if i_em is not None else None)
        if not d:
            continue
        antes = ultimo.get(cod)
        if antes and antes["data"] >= d:
            continue
        prod = _texto(r[i_cod])
        ultimo[cod] = {
            "data": d, "produto": prod,
            "produto_nome": nomes.get(prod, ""),
            "quantidade": _numero(r[i_qtd]) if i_qtd is not None else 0.0,
            "valor": _numero(r[i_val]) if i_val is not None else 0.0,
        }
    wb.close()
    return ultimo


def nomes_de_produto(caminho_csv) -> dict:
    """{codigo -> descricao} do CATEGORIAS_PRODUTO.csv."""
    caminho_csv = Path(caminho_csv) if caminho_csv else None
    if not caminho_csv or not caminho_csv.exists():
        return {}
    import csv as _csv
    saida = {}
    try:
        with open(caminho_csv, encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            sep = ";" if amostra.count(";") > amostra.count(",") else ","
            for linha in _csv.DictReader(f, delimiter=sep):
                limpo = {_limpar_categoria(k): v for k, v in linha.items() if k}
                cod = _texto(limpo.get("COD PROD") or limpo.get("CODIGO")
                             or limpo.get("COD PRODUTO"))
                nome = _texto(limpo.get("PRODUTO") or limpo.get("DESCRICAO"))
                if cod and nome:
                    saida[cod] = nome
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return saida


# os filtros de oportunidade da aba 3
FLAGS = [
    ("com_limite", "APENAS CLIENTE COM LIMITE"),
    ("churn30", "CHURN 30 DIAS"),
    ("churn60", "CHURN 60 DIAS"),
    ("churn90", "CHURN 90 DIAS"),
    ("inativos", "INATIVOS"),
    ("em_atraso", "COM VALOR EM ATRASO"),
    # o contrario da de cima: so quem NAO deve nada. Marcar as duas juntas
    # nao traz ninguem, e esta certo - nao existe cliente que esteja em
    # atraso e adimplente ao mesmo tempo.
    ("adimplentes", "APENAS CLIENTES ADIMPLENTES"),
    ("sem_positivar", "AINDA NAO POSITIVOU NO MES"),
    ("cadastro_sem_compra", "CLIENTES CADASTRADOS NOS ULTIMOS 90 DIAS SEM COMPRA"),
]

# A ficha foi aberta ha pouco e ate agora nao rendeu nota nenhuma. E o
# cadastro NOVO que nao converteu - outra coisa, bem diferente, do cliente
# antigo que parou de comprar (esse e o CHURN / INATIVO).
DIAS_DE_CADASTRO_NOVO = 90

RECORTES_FILTRO = ["zona", "segmento", "cidade", "bairro", "vendedor",
                   "supervisor", "gerente", "uf"]
TODOS = "(todos)"


# ==========================================================================
# O RESUMO GERENCIAL DA BASE DE CLIENTES
# ==========================================================================
# A mesma leitura do painel que vai para a RRM: quantos clientes ha, quantos
# tem limite aprovado, quantos estao inadimplentes e - o numero que aponta
# acao - quantos tem limite APROVADO e nao compraram no mes.
#
# Vale para qualquer recorte: UF, CIDADE, ZONA, BAIRRO, SUPERVISOR,
# VENDEDOR ou GERENTE. As contas sao as mesmas; o que muda e por onde a
# linha e agrupada.
#
# AS DEFINICOES, para ninguem discutir numero sem saber o que ele mede:
#   COM LIMITE ......... limite APROVADO maior que zero (ou disponivel
#                        maior que zero, quando so esse vem preenchido)
#   INADIMPLENTE ....... valor em atraso maior que zero
#   LIMITE SEM COMPRA .. tem limite e NAO positivou no mes. E a lista mais
#                        barata de prospeccao que existe: o credito ja foi
#                        analisado e aprovado, e esta parado
#   LIMITE PARADO R$ ... o limite DISPONIVEL somado desses clientes - o
#                        quanto de compra ja esta liberado e nao saiu
#   POSITIVADOS ........ comprou no mes (nota emitida)
RECORTES_DA_BASE = ["segmento", "uf", "cidade", "zona", "bairro",
                    "supervisor", "vendedor", "gerente"]


def _tem_limite(linha) -> bool:
    return (_numero(linha.get("limite_aprovado")) > 0
            or _numero(linha.get("limite_disponivel")) > 0)


def _positivou(linha) -> bool:
    return bool(linha.get("positivou") or linha.get("positivados"))


def _bloco_da_base() -> dict:
    zerado = {"clientes": 0, "com_limite": 0, "inadimplentes": 0,
              "limite_sem_compra": 0, "positivados": 0,
              "limite_parado": 0.0, "limite_aprovado": 0.0,
              "em_atraso": 0.0, "sem_compra_90": 0}
    for letra in CURVAS_DA_BASE:
        zerado[f"curva_{letra}"] = 0
    return zerado


# as curvas na ordem em que elas aparecem no painel
CURVAS_DA_BASE = ["S", "A", "B", "C", "Z"]


def _somar_na_base(alvo: dict, linha: dict) -> None:
    alvo["clientes"] += 1
    curva = _texto(linha.get("curva")).upper()[:1]
    alvo[f"curva_{curva if curva in CURVAS_DA_BASE else 'Z'}"] += 1
    if _positivou(linha):
        alvo["positivados"] += 1
    atraso = _numero(linha.get("valor_em_atraso"))
    if atraso > 0:
        alvo["inadimplentes"] += 1
        alvo["em_atraso"] += atraso
    if _tem_limite(linha):
        alvo["com_limite"] += 1
        alvo["limite_aprovado"] += _numero(linha.get("limite_aprovado"))
        if not _positivou(linha):
            alvo["limite_sem_compra"] += 1
            alvo["limite_parado"] += _numero(linha.get("limite_disponivel"))
    dias = linha.get("dias_sem_compra")
    try:
        if dias is not None and float(dias) >= 90:
            alvo["sem_compra_90"] += 1
    except (TypeError, ValueError):
        pass


def _fechar_base(alvo: dict, rotulo: str, codigo: str = "") -> dict:
    alvo["rotulo"] = rotulo
    alvo["codigo"] = codigo
    total = alvo["clientes"]
    alvo["pct_positivados"] = round(_pct_da_base(alvo["positivados"],
                                                 total), 1)
    alvo["pct_com_limite"] = round(_pct_da_base(alvo["com_limite"], total), 1)
    # a inadimplencia se mede sobre quem TEM credito, nao sobre a base
    # inteira: cliente sem limite nao tem como ficar devendo em carteira
    alvo["pct_inadimplentes"] = round(
        _pct_da_base(alvo["inadimplentes"], alvo["com_limite"]), 1)
    alvo["pct_limite_parado"] = round(
        _pct_da_base(alvo["limite_sem_compra"], alvo["com_limite"]), 1)
    for campo in ("limite_parado", "limite_aprovado", "em_atraso"):
        alvo[campo] = round(alvo[campo], 2)
    return alvo


def _pct_da_base(parte, total) -> float:
    return (parte / total * 100.0) if total else 0.0


def resumo_da_base(linhas: list, recorte: str = "uf") -> dict:
    """
    O painel da base de clientes: o total geral, a distribuicao por curva
    e uma linha por item do recorte.

        {"total": {...}, "linhas": [...], "recorte": "uf"}

    `linhas` e a lista da oportunidade de cliente - a mesma que a aba 1
    mostra. Nada e filtrado aqui: o resumo e sempre da base inteira, para
    o numero do painel bater com o que se diz na reuniao.
    """
    recorte = recorte if recorte in RECORTES_DA_BASE else "uf"
    total = _bloco_da_base()
    por_chave = {}
    codigos = {}
    for l in linhas or []:
        _somar_na_base(total, l)
        chave = _texto(l.get(recorte)) or f"(sem {TITULO_DO_RECORTE.get(recorte, recorte).lower()})"
        alvo = por_chave.get(chave)
        if alvo is None:
            alvo = por_chave[chave] = _bloco_da_base()
            codigos[chave] = _texto(l.get(f"cod_{recorte}"))
        _somar_na_base(alvo, l)
    saida = [_fechar_base(v, k, codigos.get(k, ""))
             for k, v in por_chave.items()]
    saida.sort(key=lambda x: (-x["clientes"], x["rotulo"]))
    return {"recorte": recorte,
            "titulo": TITULO_DO_RECORTE.get(recorte, recorte.upper()),
            "total": _fechar_base(total, "TOTAL"),
            "linhas": saida}


COLUNAS_RESUMO_BASE = [
    ("CODIGO", "codigo", 14, None),
    ("TOTAL CLIENTES", "clientes", 15, "#,##0"),
    ("CURVA S", "curva_S", 10, "#,##0"),
    ("CURVA A", "curva_A", 10, "#,##0"),
    ("CURVA B", "curva_B", 10, "#,##0"),
    ("CURVA C", "curva_C", 10, "#,##0"),
    ("CURVA Z", "curva_Z", 10, "#,##0"),
    ("COM LIMITE", "com_limite", 13, "#,##0"),
    ("INADIMPLENTES", "inadimplentes", 15, "#,##0"),
    ("% INAD. (S/ LIMITE)", "pct_inadimplentes", 19, "#,##0.0"),
    ("EM ATRASO R$", "em_atraso", 16, "#,##0.00"),
    ("LIMITE SEM COMPRA", "limite_sem_compra", 19, "#,##0"),
    ("LIMITE PARADO R$", "limite_parado", 18, "#,##0.00"),
    ("POSITIVADOS", "positivados", 13, "#,##0"),
    ("% POSITIVADOS", "pct_positivados", 15, "#,##0.0"),
    ("SEM COMPRA 90+ DIAS", "sem_compra_90", 20, "#,##0"),
]


def nome_do_resumo_da_base(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"RESUMO_BASE_CLIENTE_BAP_{hoje:%Y%m%d}.xlsx"


def gravar_excel_resumo_da_base(linhas: list, caminho, competencia="",
                                hoje=None) -> Path:
    """Uma aba por recorte: UF, CIDADE, ZONA, SUPERVISOR, VENDEDOR..."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    caminho = Path(caminho)
    hoje = hoje or dt.date.today()
    wb = Workbook()
    azul = PatternFill("solid", fgColor="1F4E79")
    branco = Font(bold=True, color="FFFFFF", size=10)

    def _folha(ws, resumo):
        ws["A1"] = f"RESUMO GERENCIAL | BASE DE CLIENTES - POR {resumo['titulo']}"
        ws["A1"].font = Font(bold=True, size=13, color="1F4E79")
        t = resumo["total"]
        ws["A2"] = (f"{t['clientes']:,} clientes  |  {t['com_limite']:,} com "
                    f"limite  |  {t['inadimplentes']:,} inadimplentes  |  "
                    f"{t['limite_sem_compra']:,} com limite e sem compra"
                    + (f"  |  competencia {competencia}" if competencia else "")
                    + f"  |  apurado em {hoje:%d/%m/%Y}").replace(",", ".")
        ws["A2"].font = Font(size=10, italic=True)
        cabecalho = [(resumo["titulo"], "rotulo", 28, None)] + COLUNAS_RESUMO_BASE
        for i, (titulo, _, larg, _f) in enumerate(cabecalho, start=1):
            cel = ws.cell(3, i, titulo)
            cel.fill = azul
            cel.font = branco
            cel.alignment = Alignment(horizontal="center", vertical="center",
                                      wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = larg
        ws.row_dimensions[3].height = 30
        ws.freeze_panes = "B4"
        for l in resumo["linhas"] + [resumo["total"]]:
            ws.append([l.get(chave) for _, chave, _, _ in cabecalho])
        ultima = ws.max_row
        for linha in range(4, ultima + 1):
            for col, (_, _, _, fmt) in enumerate(cabecalho, start=1):
                cel = ws.cell(linha, col)
                cel.font = Font(size=9, bold=(linha == ultima))
                if fmt:
                    cel.number_format = fmt
        if ultima > 4:
            ws.auto_filter.ref = (f"A3:{get_column_letter(len(cabecalho))}"
                                  f"{ultima - 1}")

    primeiro = True
    for recorte in RECORTES_DA_BASE:
        resumo = resumo_da_base(linhas, recorte)
        if primeiro:
            ws = wb.active
            ws.title = TITULO_DO_RECORTE.get(recorte, recorte.upper())[:31]
            primeiro = False
        else:
            ws = wb.create_sheet(
                TITULO_DO_RECORTE.get(recorte, recorte.upper())[:31])
        _folha(ws, resumo)

    wl = wb.create_sheet("COMO_LER")
    regras = [
        ("COM LIMITE", "limite APROVADO maior que zero (ou disponivel maior "
                       "que zero, quando so esse vem preenchido)."),
        ("INADIMPLENTES", "valor em atraso maior que zero."),
        ("% INAD. (S/ LIMITE)",
         "inadimplentes dividido por COM LIMITE, nao pela base inteira: "
         "cliente sem limite nao tem como ficar devendo em carteira."),
        ("LIMITE SEM COMPRA",
         "tem limite aprovado e NAO positivou no mes. E a lista mais barata "
         "de prospeccao que existe - o credito ja foi analisado."),
        ("LIMITE PARADO R$",
         "o limite DISPONIVEL somado desses clientes: quanto de compra ja "
         "esta liberado e nao saiu."),
        ("POSITIVADOS", "comprou no mes, com nota emitida."),
        ("SEM COMPRA 90+ DIAS",
         "dias sem compra maior ou igual a 90 - o corte de churn."),
        ("CURVA", "a curva do cliente na base. Quem nao tem curva conta "
                  "como Z."),
        ("A BASE E SEMPRE INTEIRA",
         "o resumo nao segue os filtros da lista de clientes: ele e da base "
         "toda, para o numero do painel bater com o que se diz na reuniao."),
    ]
    for i, (a, b) in enumerate(regras, start=1):
        wl.cell(i, 1, a).font = Font(bold=True, size=10)
        wl.cell(i, 2, b).font = Font(size=10)
        wl.cell(i, 2).alignment = Alignment(wrap_text=True, vertical="top")
    wl.column_dimensions["A"].width = 24
    wl.column_dimensions["B"].width = 88

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def _so_digitos(valor) -> str:
    return "".join(c for c in _texto(valor) if c.isdigit())


def _contato_completo(linha: dict) -> str:
    """
    O telefone e o contato numa coluna so.

    O cadastro do Protheus poe coisas diferentes no A1_CONTATO: as vezes o
    nome de quem atende ("PORTAL LUBRIFIC"), as vezes o MESMO telefone de
    novo ("99138-0325" ao lado de "(096) 99138-0325"), as vezes um segundo
    numero. Repetir o mesmo numero duas vezes na mesma celula so ocupa
    espaco, entao o contato so entra quando acrescenta alguma coisa - e a
    comparacao e pelos DIGITOS, para "99138-0325" e "991380325" contarem
    como iguais.
    """
    fone = _texto(linha.get("fone"))
    contato = _texto(linha.get("contato"))
    if not contato:
        return fone
    if not fone:
        return contato
    d_fone, d_contato = _so_digitos(fone), _so_digitos(contato)
    if d_contato and (d_contato in d_fone or d_fone.endswith(d_contato)):
        return fone
    return f"{fone} - {contato}"


def montar_oportunidade(ac: dict, cadastro: dict, ultimo: dict) -> list:
    """
    Uma linha por cliente com TUDO junto - a lista que o vendedor leva
    para a rua. Nao filtra nada: quem filtra e filtrar_oportunidade().
    """
    saida = []
    for c in ac["clientes"]:
        cod = _texto(c.get("cod_cliente"))
        reg = cadastro.get(c.get("chave", "")) or cadastro.get(cod) or {}
        ult = ultimo.get(cod) or {}
        linha = dict(c)
        linha["limite_aprovado"] = _numero(reg.get("limite_aprovado"))
        linha["limite_disponivel"] = _numero(reg.get("limite_disponivel"))
        linha["em_aberto"] = _numero(reg.get("em_aberto"))
        linha["valor_em_atraso"] = _numero(reg.get("valor_em_atraso"))
        linha["dias_atraso"] = _numero(reg.get("dias_atraso"))
        linha["dias_sem_compra"] = reg.get("dias_sem_compra")
        linha["ultima_compra"] = reg.get("ultima_compra")
        linha["status_cliente"] = _texto(reg.get("status_cliente"))
        linha["endereco"] = _texto(reg.get("endereco"))
        linha["numero"] = _texto(reg.get("numero"))
        linha["contato"] = _texto(reg.get("contato"))
        linha["ddd"] = _texto(reg.get("ddd"))
        linha["telefone"] = _texto(reg.get("telefone"))
        # o numero pronto para discar, DDD e telefone juntos
        linha["fone"] = (f"({linha['ddd']}) {linha['telefone']}"
                         if linha["ddd"] and linha["telefone"]
                         else linha["telefone"] or linha["ddd"])
        linha["contato_completo"] = _contato_completo(linha)
        linha["curva"] = _texto(reg.get("curva_receita")) or c.get("curva", "")
        linha["data_cadastro"] = _data(reg.get("data_cadastro"))
        linha["dias_de_cadastro"] = _dias_ate_hoje(linha["data_cadastro"])
        linha["ult_produto"] = ult.get("produto", "")
        linha["ult_produto_nome"] = ult.get("produto_nome", "")
        linha["ult_quantidade"] = ult.get("quantidade", 0.0)
        linha["ult_valor"] = ult.get("valor", 0.0)
        linha["ult_data"] = ult.get("data")
        # a linha de CLIENTE do acompanhamento nao traz realizado/falta
        # prontos (eles nascem nas linhas agrupadas) - aqui eles entram,
        # para a lista poder ser ordenada e somada como as outras
        linha["realizado"] = _numero(c.get("liquido"))
        linha["falta"] = linha["meta"] - linha["realizado"]
        linha["atingimento"] = (linha["realizado"] / linha["meta"] * 100.0
                                if linha["meta"] else 0.0)
        linha["notas"] = c.get("qtd_notas", 0)
        linha["positivados"] = 1 if c.get("positivou") else 0
        saida.append(linha)
    saida.sort(key=lambda x: (-x["meta"], -x.get("limite_disponivel", 0.0)))
    return saida


def _dias_ate_hoje(data) -> int | None:
    """Quantos dias se passaram desde `data`. None quando nao ha data."""
    d = _data(data)
    if d is None:
        return None
    if hasattr(d, "date"):
        d = d.date()
    return (dt.date.today() - d).days


def _cadastro_novo(linha: dict, dias: int) -> bool:
    """A ficha do cliente foi aberta ha `dias` ou menos."""
    passados = linha.get("dias_de_cadastro")
    if passados is None:
        passados = _dias_ate_hoje(linha.get("data_cadastro"))
    return passados is not None and 0 <= passados <= dias


def _nunca_comprou(linha: dict) -> bool:
    """
    Nenhuma nota ate hoje.

    Tres provas, porque uma so falha: o STATUS da base, a falta de data
    de ultima compra e a contagem de notas. Basta o status dizer NUNCA
    COMPROU, ou nao haver data nenhuma de compra.
    """
    if _texto(linha.get("status_cliente")).upper().startswith("NUNCA"):
        return True
    if _data(linha.get("ultima_compra")) is not None:
        return False
    return _dias_sem(linha) < 0


def _dias_sem(linha) -> float:
    v = linha.get("dias_sem_compra")
    try:
        return float(v)
    except (TypeError, ValueError):
        return -1.0


def filtrar_oportunidade(linhas: list, recorte: str = "", alvo: str = "",
                         flags: dict = None) -> list:
    """
    Corta a lista pelo recorte escolhido (zona, cidade, bairro, vendedor...)
    e pelas flags marcadas. Sem recorte e sem flag, devolve tudo.

    As flags de CHURN sao FAIXAS e somam entre si: marcar 30 e 60 traz os
    dois grupos. Elas olham DIAS_SEM_COMPRA, nao o texto do status - assim
    a conta nao muda se o corte do churn for mudado nos parametros.
    """
    flags = flags or {}
    fora = list(linhas)
    if recorte and alvo and alvo != TODOS:
        fora = [l for l in fora if _texto(l.get(recorte)) == alvo
                or _texto(l.get(f"cod_{recorte}")) == alvo]
    if flags.get("com_limite"):
        fora = [l for l in fora if l.get("limite_disponivel", 0.0) > 0]
    if flags.get("em_atraso"):
        fora = [l for l in fora if l.get("valor_em_atraso", 0.0) > 0]
    if flags.get("adimplentes"):
        fora = [l for l in fora if not (l.get("valor_em_atraso") or 0.0) > 0]
    if flags.get("cadastro_sem_compra"):
        # DUAS CONDICOES, as duas obrigatorias: cadastro NOVO (ficha
        # aberta ha 90 dias ou menos) e NENHUMA compra ate agora. Cliente
        # sem data de cadastro na base nao entra - nao da para afirmar
        # que ele e novo, e chutar aqui encheria a lista de cadastro
        # antigo, que e justamente o que este filtro nao quer.
        fora = [l for l in fora
                if _cadastro_novo(l, DIAS_DE_CADASTRO_NOVO)
                and _nunca_comprou(l)]
    if flags.get("sem_positivar"):
        fora = [l for l in fora if not l.get("positivou")]
    faixas = []
    if flags.get("churn30"):
        faixas.append((31, 60))
    if flags.get("churn60"):
        faixas.append((61, 90))
    if flags.get("churn90"):
        faixas.append((91, 120))
    if flags.get("inativos"):
        faixas.append((121, 10 ** 9))
    if faixas:
        fora = [l for l in fora
                if any(a <= _dias_sem(l) <= b for a, b in faixas)]
    return fora


def alvos_do_recorte(linhas: list, recorte: str) -> list:
    """A lista da caixinha: o que existe naquele recorte, com o (todos)."""
    if not recorte:
        return [TODOS]
    vistos = {}
    for l in linhas:
        chave = _texto(l.get(recorte))
        if not chave:
            continue
        cod = _texto(l.get(f"cod_{recorte}"))
        vistos.setdefault(chave, f"{cod} - {chave}" if cod else chave)
    return [TODOS] + [vistos[k] for k in sorted(vistos)]


COLUNAS_OPORTUNIDADE = [
    # A FRENTE DA LISTA e o que o vendedor le na rua, nesta ordem: onde o
    # cliente fica, quem ele e, como falar com ele, quanto pode comprar e
    # o que levou da ultima vez. O resto vem depois.
    # ESTA ORDEM E A DA TELA, de proposito: o Excel que o vendedor
    # exporta tem de sair igual ao que ele acabou de ver. DDD, TELEFONE,
    # FONE e CONTATO viraram uma coluna so (CONTATO, ver
    # _contato_completo); LIMITE DISPONIVEL virou LIM. DISP.; o BAIRRO
    # passou para antes do NUMERO e a ZONA foi para o fim.
    ("UF", "uf", 5, None),
    ("CIDADE", "cidade", 22, None),
    ("COD.", "cod_cliente", 13, None),
    ("RAZAO SOCIAL", "cliente", 40, None),
    ("NOME FANTASIA", "fantasia", 30, None),
    ("SEGMENTO", "segmento", 24, None),
    ("ENDERECO", "endereco", 36, None),
    ("BAIRRO", "bairro", 24, None),
    ("NUMERO", "numero", 9, None),
    ("CONTATO", "contato_completo", 32, None),
    ("LIM. DISP. R$", "limite_disponivel", 16, "#,##0.00"),
    ("ULT. PRODUTO", "ult_produto", 18, None),
    ("ULT. COMPRA", "ult_produto_nome", 40, None),
    ("QTD", "ult_quantidade", 10, "#,##0.00"),
    ("STATUS", "status_cliente", 15, None),
    ("CURVA", "curva", 7, None),
    ("DIAS SEM COMPRA", "dias_sem_compra", 16, None),
    # --- o resto ---------------------------------------------------------
    ("DATA CADASTRO", "data_cadastro", 16, "DD/MM/YYYY"),
    ("DDD", "ddd", 7, None),
    ("TELEFONE", "telefone", 15, None),
    ("FONE", "fone", 20, None),
    ("CONTATO (CADASTRO)", "contato", 20, None),
    ("DATA DA ULTIMA COMPRA", "ultima_compra", 22, "DD/MM/YYYY"),
    ("ULT. VALOR R$", "ult_valor", 15, "#,##0.00"),
    ("LIMITE APROVADO R$", "limite_aprovado", 19, "#,##0.00"),
    ("EM ABERTO R$", "em_aberto", 15, "#,##0.00"),
    ("VALOR EM ATRASO R$", "valor_em_atraso", 19, "#,##0.00"),
    ("DIAS EM ATRASO", "dias_atraso", 15, None),
    ("META R$", "meta", 16, "#,##0.00"),
    ("REALIZADO R$", "realizado", 16, "#,##0.00"),
    ("ATINGIMENTO %", "atingimento", 15, "#,##0.0"),
    ("FALTA R$", "falta", 16, "#,##0.00"),
    ("POSITIVOU", "positivou_txt", 11, None),
    ("COD_ZONA", "cod_zona", 11, None),
    ("ZONA", "zona", 28, None),
    ("COD_VENDEDOR", "cod_vendedor", 14, None),
    ("VENDEDOR", "vendedor", 26, None),
    ("COD_SUPERVISOR", "cod_supervisor", 15, None),
    ("SUPERVISOR", "supervisor", 24, None),
    ("COD_GERENTE", "cod_gerente", 13, None),
    ("GERENTE", "gerente", 22, None),
]


def gravar_excel_oportunidade(linhas: list, caminho, titulo="") -> Path:
    """A base de cliente do jeito que ela vai para a rua."""
    from openpyxl import Workbook
    caminho = Path(caminho)
    wb = Workbook()
    wb.remove(wb.active)
    prontas = []
    for l in linhas:
        copia = dict(l)
        copia["positivou_txt"] = "SIM" if l.get("positivou") else ""
        prontas.append(copia)
    _folha(wb, "BASE_CLIENTE", COLUNAS_OPORTUNIDADE, prontas)
    ws = wb.create_sheet("FILTRO")
    ws["A1"] = "De onde veio esta lista"
    ws["A2"] = titulo or "base completa"
    ws["A3"] = f"{len(linhas)} cliente(s)"
    ws.column_dimensions["A"].width = 90
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def nome_da_base_de_oportunidade(competencia="") -> str:
    return f"BASE_OPORTUNIDADE_BAP_{marca_do_mes(competencia)}.xlsx"


# ==========================================================================
# AS VISITAS QUE FORAM MESMO FEITAS - um CSV por mes
# ==========================================================================
# A META DE VISITA precisa de algo contra o que ser medida: a TABELA_BAP
# tem nota fiscal, nao check-in. Quem tem o check-in e o arquivo de
# visitas, uma linha por vendedor e a coluna
# TOTALVISITADOSDENTROAGENDAFORAAGENDA com o que ele visitou no mes.
#
# ONDE ELE MORA  (mudou em 16/09/2026)
#   RELATORIOS\Visitas\AAAAMM.csv  -  202608.csv, 202609.csv...
#
#   UM ARQUIVO POR MES, com o nome sendo o proprio mes. Era um GRIDRCA.csv
#   unico, que servia para um mes so: ao trocar a competencia na tela, o
#   acompanhamento continuava mostrando a visita do mes anterior. Agora o
#   programa pega o arquivo DAQUELE mes, e cada mes fecha com o que foi
#   feito nele.
#
#   O GRIDRCA.csv solto na RELATORIOS continua sendo aceito, como ultimo
#   recurso, para quem ainda nao separou os meses.
#
# O casamento e PELO NOME do vendedor (o arquivo nao traz codigo), entao
# ele e feito com o nome normalizado - sem acento, sem pontuacao e sem
# palavra de ligacao (DA, DE, DOS...). Quem nao casar aparece na conta
# como visita zero, e ler_visitas_realizadas() devolve a lista dos nomes
# que sobraram, para a tela poder avisar.
ARQUIVO_GRIDRCA = "GRIDRCA.csv"
PASTA_DE_VISITAS = "Visitas"
# A COLUNA DO NUMERO, na ordem em que o programa procura. O relatorio ja
# mudou de formato uma vez, entao aqui vale a primeira que existir no
# arquivo, e nao uma so:
#   TOTALVISITAS ........................... o formato de hoje
#   TOTALVISITADOSDENTROAGENDAFORAAGENDA ... o formato antigo
# NAO usar VISITADOS nem VISITADOSFORAAGENDA: essas vem escritas como
# "70 / 0%", que e texto, e nao somam a visita fora de agenda.
COLUNAS_DE_VISITA = ("TOTALVISITAS", "TOTALVISITADOSDENTROAGENDAFORAAGENDA")
COLUNA_VISITAS = COLUNAS_DE_VISITA[0]
_LIGACAO = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def nome_do_arquivo_de_visita(competencia: str) -> str:
    """'2026-09' -> '202609.csv'. O nome do arquivo daquele mes."""
    return f"{marca_do_mes(competencia)}.csv"


def pasta_das_visitas(raiz):
    """A pasta RELATORIOS/Visitas, criada se ainda nao existir."""
    pasta = Path(raiz) / VISITAS_SUB
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return pasta


def cadastros_por_vendedor(caminho_tabela, competencia) -> dict:
    """
    (15/10, Alexandre) {codigo do vendedor (6 digitos): clientes
    cadastrados no mes} - da dClientesBap da TABELA_BAP (o cadastro do
    BAP Tools): A1_DTCAD no mes da competencia, pelo A1_VEND. Cliente
    (codigo) conta uma vez; linha apagada (D_E_L_E_T_ = *) nao conta.
    E o que entra como VISITA (cadastro novo do dia = visita).
    """
    caminho = Path(caminho_tabela) if caminho_tabela else None
    comp = normalizar_competencia(competencia) if competencia else ""
    if not caminho or not caminho.exists() or not comp:
        return {}
    try:
        import planner_nucleo as _nu                     # noqa: PLC0415
        lote_fora = _nu.datas_cadastro_lote_fora()
    except Exception:                                   # noqa: BLE001
        lote_fora = set()
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except (OSError, ValueError):
        return {}
    try:
        aba = next((n for n in wb.sheetnames
                    if _chave(n) == _chave("dClientesBap")), None)
        if not aba:
            return {}
        it = wb[aba].iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]

        def ix(*nomes):
            return next((cab.index(_chave(n)) for n in nomes
                         if _chave(n) in cab), None)
        i_cod, i_vend = ix("A1_COD", "CODIGO", "COD_CLIENTE"), ix("A1_VEND")
        i_cad, i_del = ix("A1_DTCAD"), ix("D_E_L_E_T_")
        if None in (i_cod, i_vend, i_cad):
            return {}
        vistos, saida = set(), defaultdict(int)
        for r in it:
            if i_del is not None and i_del < len(r) and \
                    _texto(r[i_del]) == "*":
                continue
            data = _data(r[i_cad]) if i_cad < len(r) else None
            if not data or _mes_de(data) != comp:
                continue
            # (21/10, Alexandre) cadastro em LOTE (16/10) nao e visita
            if data in lote_fora:
                continue
            cod, vend = _texto(r[i_cod]).zfill(6), _texto(r[i_vend])
            if not vend or cod in vistos:
                continue
            vistos.add(cod)
            saida[vend.zfill(6)] += 1
        # (22/10, Alexandre) a PROSPECCAO do Microsoft Forms (visita a
        # cliente fora da base, STATUS = CONTA) tambem e visita - no Farol
        # de Metas e na RV de visita, como o cadastro novo
        try:
            import prospeccao_forms as _pf              # noqa: PLC0415
            for (v6, d), n in _pf.contagem(caminho.parent.parent).items():
                if _mes_de(d) == comp and d not in lote_fora:
                    saida[_texto(v6).zfill(6)] += n
        except Exception:                               # noqa: BLE001
            pass
        return dict(saida)
    except (StopIteration, KeyError, ValueError):
        return {}
    finally:
        wb.close()


def achar_visitas_do_mes(raiz, competencia=""):
    """
    O CSV de visita DAQUELE mes. Procura, nesta ordem:

        1. RELATORIOS/Visitas/202609.csv   (o lugar certo)
        2. RELATORIOS/202609.csv            (se alguem largou fora da pasta)
        3. o GRIDRCA.csv solto              (o jeito antigo, ultimo recurso -
                                             so se foi salvo NAQUELE mes)

    Aceita o nome com separador - 2026-09.csv e 2026_09.csv sao o mesmo
    arquivo que 202609.csv. Sem competencia, so o GRIDRCA responde.
    """
    raiz = Path(raiz)
    marca = marca_do_mes(competencia) if competencia else ""
    if marca:
        for pasta in (raiz / VISITAS_SUB, raiz / RELATORIOS_SUB, raiz):
            if not pasta.exists():
                continue
            for arq in sorted(pasta.glob("*.csv")):
                if _so_letras(arq.stem) == marca:
                    return arq
    grid = achar_gridrca(raiz)
    # O GRIDRCA solto e uma FOTO de um mes so (o do dia em que foi salvo).
    # Mes sem arquivo proprio so usa ele se a foto for DAQUELE mes - antes
    # out/2026 pegava o GridRca de 14/09 e mostrava 45 visitas que eram
    # de setembro.
    if grid is not None and marca:
        from datetime import datetime as _dt            # noqa: PLC0415
        foto = _dt.fromtimestamp(grid.stat().st_mtime)
        if f"{foto.year:04d}{foto.month:02d}" != marca:
            return None
    return grid


def meses_com_visita(raiz) -> list:
    """Os meses que ja tem arquivo de visita, em AAAA-MM."""
    raiz = Path(raiz)
    achados = set()
    for pasta in (raiz / VISITAS_SUB, raiz / RELATORIOS_SUB):
        if not pasta.exists():
            continue
        for arq in pasta.glob("*.csv"):
            so = _so_letras(arq.stem)
            if len(so) == 6 and so.isdigit():
                competencia = normalizar_competencia(so)
                if competencia:
                    achados.add(competencia)
    return sorted(achados)


def achar_gridrca(raiz):
    """O arquivo unico do jeito antigo. Mantido para nao quebrar pasta velha."""
    raiz = Path(raiz)
    for pasta in (raiz / RELATORIOS_SUB, raiz):
        if not pasta.exists():
            continue
        for arq in sorted(pasta.glob("*.csv")):
            if _so_letras(arq.stem) == _so_letras(Path(ARQUIVO_GRIDRCA).stem):
                return arq
    return None


def _so_letras(texto) -> str:
    return re.sub(r"[^A-Z0-9]", "", _sem_acento(_texto(texto)).upper())


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def chave_de_nome(nome) -> str:
    """
    O nome do jeito que da para comparar: sem acento, sem pontuacao e sem
    as palavrinhas de ligacao. "Denylson da Silva Costa" e "DENYLSON
    SILVA COSTA" viram a mesma coisa.
    """
    limpo = re.sub(r"[^A-Z ]", " ", _sem_acento(_texto(nome)).upper())
    partes = [p for p in limpo.split() if p and p not in _LIGACAO]
    return " ".join(partes)


def chave_curta_de_nome(nome) -> str:
    """
    O PRIMEIRO NOME e o ULTIMO SOBRENOME - a forma reduzida.

    O relatorio de visita escreve o nome inteiro ("RODRIGO RIBEIRO
    LOPES", "FAYGA KETTE CAETANO DE SOUZA") e o cadastro do Planner, o
    nome curto ("RODRIGO LOPES", "FAYGA DE SOUZA"). Pelo nome inteiro
    eles nunca casam, e o vendedor aparece com visita zero sem ninguem
    perceber. Esta chave e a ponte.

    So e usada quando a comparacao pelo nome inteiro falha E a forma
    curta aponta para UMA pessoa so dos dois lados - ver _casar_visitas().
    """
    partes = chave_de_nome(nome).split()
    if len(partes) < 2:
        return " ".join(partes)
    return f"{partes[0]} {partes[-1]}"


def _casar_visitas(feitas: dict) -> tuple:
    """
    Devolve (mapa_inteiro, mapa_curto). O curto so tem os nomes que sao
    UNICOS na forma reduzida: se duas pessoas do arquivo viram a mesma
    chave curta, nenhuma das duas entra - adivinhar de quem e a visita
    seria pior do que deixar zero.
    """
    curto = {}
    repetido = set()
    for chave, valor in feitas.items():
        c = chave_curta_de_nome(chave)
        if not c or c == chave:
            continue
        if c in curto:
            repetido.add(c)
        curto[c] = valor
    for c in repetido:
        curto.pop(c, None)
    return feitas, curto


def ler_visitas_realizadas(caminho) -> dict:
    """
    Do GRIDRCA.csv: {chave do nome -> visitas no mes}. Devolve tambem, na
    chave especial "_nomes", o nome como esta escrito no arquivo, para a
    tela poder dizer quem nao casou.
    """
    caminho = Path(caminho) if caminho else None
    if not caminho or not caminho.exists():
        return {}
    import csv as _csv
    saida, nomes = {}, {}
    try:
        with open(caminho, encoding="utf-8-sig", newline="",
                  errors="replace") as f:
            amostra = f.read(8192)
            f.seek(0)
            sep = ";" if amostra.count(";") > amostra.count(",") else ","
            leitor = _csv.DictReader(f, delimiter=sep)
            titulos = {_so_letras(c): c for c in (leitor.fieldnames or [])}
            col_visitas = None
            for procurada in COLUNAS_DE_VISITA:
                col_visitas = titulos.get(_so_letras(procurada))
                if col_visitas:
                    break
            # a coluna do nome: a que se chama nome/vendedor/rca, ou, na
            # falta, a primeira coluna de texto do arquivo
            # SUPERVISOR nao entra nesta lista de proposito: o arquivo
            # novo traz as duas colunas, e quem visita e o vendedor
            col_nome = None
            for procurado in ("NOMERCA", "NOMEVENDEDOR", "NOME", "VENDEDOR",
                              "RCA", "REPRESENTANTE"):
                if procurado in titulos:
                    col_nome = titulos[procurado]
                    break
            if col_nome is None and leitor.fieldnames:
                col_nome = leitor.fieldnames[0]
            if not col_visitas or not col_nome:
                return {}
            for linha in leitor:
                nome = _texto(linha.get(col_nome))
                chave = chave_de_nome(nome)
                if not chave:
                    continue
                saida[chave] = saida.get(chave, 0.0) + _numero(
                    linha.get(col_visitas))
                nomes.setdefault(chave, nome)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    saida["_nomes"] = nomes
    return saida


# os recortes que TEM meta de visita: visita e da pessoa que anda na rua.
# Zona, cidade, bairro e cliente nao visitam ninguem - eles sao visitados.
RECORTES_COM_VISITA = ("gerente", "supervisor", "vendedor")


# ==========================================================================
# O PAINEL EXECUTIVO
# ==========================================================================
# Cinco indicadores, um peso para cada, e mes a mes: META, REAL,
# % ATING. META e % ATING PESO.
#
# A ESCADA DO PESO - e ela que traduz atingimento em pontos:
#
#       abaixo de 80% ...... 0% do peso
#       exatamente 80% ..... 50% do peso
#       a partir de 81% .... cada 1% vale 2,5 pontos percentuais
#       teto ............... 120% do peso (chega la com 108% da meta)
#
# Ou seja: 100% da meta = 100% do peso (50 + 20 x 2,5). Bater 108% ou
# mais entrega 120% - dali para cima nao sobe mais.
INDICADORES_EXECUTIVOS = [
    # (chave, rotulo, peso de fabrica, de onde vem o REAL, invertido?)
    ("faturamento", "FATURAMENTO TOTAL", 30.0, "auto", False),
    ("positivacao", "POSITIVACAO", 20.0, "auto", False),
    ("despesas", "DESPESAS", 15.0, "manual", True),
    ("pecas", "FATURAMENTO DE PECAS", 20.0, "auto", False),
    ("cadastro_compra", "CADASTRO COM COMPRA", 15.0, "auto", False),
]

# O QUE E "INVERTIDO": em DESPESAS, gastar MENOS que a meta e bom. Se o
# atingimento fosse real/meta, quem gastasse menos apareceria com 0% do
# peso - o contrario do que se quer premiar. Nesses o atingimento e
# meta/real.
PISO_DO_PESO = 80.0        # abaixo disso, zero
PESO_NO_PISO = 50.0        # o que se ganha ao encostar no piso
PONTOS_POR_PONTO = 2.5     # cada 1% acima do piso
TETO_DO_PESO = 120.0       # nao passa disso


def indicadores_padrao() -> list:
    return [{"chave": c, "rotulo": r, "peso": p, "fonte": f,
             "invertido": inv}
            for c, r, p, f, inv in INDICADORES_EXECUTIVOS]


def atingimento(real: float, meta: float, invertido: bool = False):
    """
    % de atingimento da meta. None quando nao ha meta - sem meta nao ha
    atingimento, e fingir zero seria pior.
    """
    meta = float(_numero(meta))
    real = float(_numero(real))
    if meta <= 0:
        return None
    if invertido:
        # despesa: gastar menos e melhor. Gasto zero nao e 'infinito bom'
        if real <= 0:
            return TETO_DO_PESO
        return meta / real * 100.0
    return real / meta * 100.0


def fator_do_peso(perc):
    """
    Quanto do peso aquele atingimento entrega, em %.

        79,9% -> 0      |  80% -> 50     |  90% -> 75
        100%  -> 100    |  108% -> 120   |  130% -> 120 (teto)
    """
    if perc is None:
        return None
    perc = float(perc)
    if perc < PISO_DO_PESO:
        return 0.0
    ganho = PESO_NO_PISO + (perc - PISO_DO_PESO) * PONTOS_POR_PONTO
    return min(TETO_DO_PESO, ganho)


def apurar_executivo(caminho_tabela, meses: list, categorias_csv=None,
                     base_cliente=None, analitico=None) -> dict:
    """
    O REAL de cada indicador, mes a mes, numa passada so pela TABELA_BAP.

    Devolve {"AAAA-MM": {"faturamento": .., "positivacao": ..,
                         "pecas": .., "cadastro_compra": ..}}

    DESPESAS nao sai daqui: ela nao existe na TABELA_BAP e continua
    sendo digitada na tela.

    analitico (08/10): uma lista; se vier, recebe a LINHA de cada coisa
    que entrou na conta (a mesma passada, entao o analitico bate com o
    real por construcao) - para a auditoria do Farol Indicadores
    Executivos. {"ind": "faturamento" | "positivacao" | "cadastro_compra",
    "mes", "data", ...}. PECAS e o faturamento com "pecas": True.
    """
    caminho_tabela = Path(caminho_tabela)
    if not caminho_tabela.exists():
        raise FileNotFoundError(f"TABELA_BAP nao encontrada: {caminho_tabela}")
    alvo = {m for m in meses if m}
    vazio = {"faturamento": 0.0, "positivacao": 0, "pecas": 0.0,
             # "cadastros" e o volume de prospeccao do mes; o
             # "cadastro_compra" e quanto disso virou venda
             "cadastros": 0, "cadastro_compra": 0}
    saida = {m: dict(vazio) for m in alvo}
    positivados = {m: set() for m in alvo}      # compraram (cadastro c/ compra)
    # (14/10, Alexandre) POSITIVACAO = comprou e NAO devolveu tudo no mes:
    # o liquido (venda - devolucao) do cliente no mes > 0
    liq_cli = defaultdict(float)
    categorias_csv = categorias_csv or {}

    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    if "ftPedidos" not in wb.sheetnames:
        wb.close()
        raise ValueError("A TABELA_BAP nao tem a aba ftPedidos - e dela que "
                         "sai o faturamento.")

    # a categoria de cada produto, do jeito que o acompanhamento ja faz
    categoria_do_produto = dict(categorias_csv)
    if "ProdutosBAP" in wb.sheetnames:
        ws = wb["ProdutosBAP"]
        it = ws.iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]

        def onde(*nomes):
            for n in nomes:
                if _chave(n) in cab:
                    return cab.index(_chave(n))
            return None

        i_id, i_cod = onde("ID_PRODUTO"), onde("Cód. Produto", "Cod. Produto")
        if i_id is not None and i_cod is not None:
            for r in it:
                pid, cod = _texto(r[i_id]), _texto(r[i_cod])
                if pid and cod and cod in categorias_csv:
                    categoria_do_produto.setdefault(pid, categorias_csv[cod])

    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    cab = [_chave(c) for c in next(it)]

    def coluna(*nomes):
        for n in nomes:
            if _chave(n) in cab:
                return cab.index(_chave(n))
        return None

    i_cli = coluna("D2_CLIENTE")
    i_tipo = coluna("TIPO")
    i_valor = coluna("VALOR TOTAL", "VALOR_TOTAL")
    i_nf = coluna("DATA_NF")
    i_dev = coluna("DATA_DEV")
    i_prod = coluna("ID_PRODUTO")
    i_cod_prod = coluna("D2_COD")
    i_fil = coluna("D2_FILIAL", "D2FILIAL")
    i_doc = coluna("D2_DOC", "NUM_NF")
    i_ped = coluna("D2_PEDIDO", "NUM_PEDIDO")
    i_nome = coluna("RAZÃO_SOCIAL", "RAZAO_SOCIAL")
    i_vend = coluna("C5_VEND1")
    pos_det = {}            # (mes, cliente) -> o resumo da positivacao

    def campo(r, i):
        return _texto(r[i]) if i is not None else ""
    if None in (i_cli, i_tipo, i_valor):
        wb.close()
        raise ValueError("A ftPedidos nao tem D2_CLIENTE, TIPO ou VALOR "
                         "TOTAL - nao da para medir o realizado.")

    for r in it:
        tipo = _texto(r[i_tipo]).upper()
        if tipo not in TIPOS_VENDA and tipo != TIPO_DEVOLUCAO:
            continue
        if i_nome is not None and e_cliente_interno(r[i_nome]):
            continue                    # (12/10) CNPJ interno: nao conta
        data = _data(r[i_nf] if i_nf is not None else None)
        if data is None and i_dev is not None:
            data = _data(r[i_dev])
        if data is None:
            continue
        mes = _mes_de(data)
        if mes not in saida:
            continue
        valor = r[i_valor]
        if not isinstance(valor, (int, float)):
            valor = _numero(valor)
        saida[mes]["faturamento"] += valor
        cod = _texto(r[i_cli])
        if cod:
            liq_cli[(mes, cod)] += valor
        if cod and valor > 0:
            positivados[mes].add(cod)
        cod_prod = _texto(r[i_cod_prod]) if i_cod_prod is not None else ""
        pid = _texto(r[i_prod]) if i_prod is not None else ""
        categoria = (categoria_do_produto.get(cod_prod)
                     or categoria_do_produto.get(pid) or CATEGORIA_PADRAO)
        if categoria == "pecas":
            saida[mes]["pecas"] += valor
        if analitico is not None:
            det = {"ind": "faturamento", "mes": mes, "data": data,
                   "filial": campo(r, i_fil), "doc": campo(r, i_doc),
                   "pedido": campo(r, i_ped), "tipo": tipo, "cli": cod,
                   "nome": campo(r, i_nome), "vend": campo(r, i_vend),
                   "prod": cod_prod or pid, "cat": categoria,
                   "valor": valor, "pecas": categoria == "pecas"}
            analitico.append(det)
            if cod and valor > 0:
                pd_ = pos_det.setdefault((mes, cod), {
                    "ind": "positivacao", "mes": mes, "data": data,
                    "filial": det["filial"], "cli": cod,
                    "nome": det["nome"], "vend": det["vend"],
                    "docs": set(), "valor": 0.0})
                pd_["data"] = min(pd_["data"], data)
                pd_["docs"].add(det["doc"])
                pd_["valor"] += valor

    # CADASTRO COM COMPRA: cadastrado no mes E com ALGUMA venda no mes.
    #
    # Antes a conta exigia A1_PRICOM (a primeira compra) no mesmo mes, e
    # isso deixava de fora quem foi cadastrado agora, comprou agora, mas
    # ja tinha uma compra antiga no Protheus - e deixava de fora todo
    # mundo com o A1_PRICOM em branco. Agora a venda e a mesma
    # positivacao apurada aqui em cima, na ftPedidos: quem comprou,
    # comprou.
    aba_cli = next((n for n in wb.sheetnames
                    if _chave(n) == _chave("dClientesBap")), None)
    if aba_cli:
        ws = wb[aba_cli]
        it = ws.iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]
        i_cad = cab.index(_chave("A1_DTCAD")) if _chave("A1_DTCAD") in cab \
            else None
        i_cod = next((cab.index(_chave(n)) for n in ("A1_COD", "CODIGO",
                                                     "COD_CLIENTE")
                      if _chave(n) in cab), None)

        def ix(n):
            return cab.index(_chave(n)) if _chave(n) in cab else None
        i_cnome, i_cvend, i_cfil = ix("A1_NOME"), ix("A1_VEND"), ix("A1_FILIAL")
        if i_cad is not None:
            for r in it:
                cadastro = _data(r[i_cad])
                if not cadastro:
                    continue
                mes = _mes_de(cadastro)
                if mes not in saida:
                    continue
                saida[mes]["cadastros"] += 1
                cod = _texto(r[i_cod]) if i_cod is not None else ""
                comprou = bool(cod and (cod in positivados[mes]
                                        or cod.zfill(6) in positivados[mes]))
                if comprou:
                    saida[mes]["cadastro_compra"] += 1
                if analitico is not None:
                    v = pos_det.get((mes, cod)) or pos_det.get(
                        (mes, cod.zfill(6))) or {}
                    analitico.append({
                        "ind": "cadastro_compra", "mes": mes, "data": cadastro,
                        "filial": campo(r, i_cfil), "cli": cod,
                        "nome": campo(r, i_cnome), "vend": campo(r, i_cvend),
                        "comprou": comprou, "valor": v.get("valor", 0.0)})
    wb.close()
    if analitico is not None:
        for (mes_, cod_), v in pos_det.items():
            liq = liq_cli.get((mes_, cod_), 0.0)
            if liq <= 0.005:
                continue                # comprou e devolveu tudo: nao conta
            v["docs"] = len(v["docs"])
            v["valor"] = round(liq, 2)
            analitico.append(v)

    for mes in saida:
        saida[mes]["positivacao"] = sum(
            1 for c in positivados[mes] if liq_cli.get((mes, c), 0.0) > 0.005)
        saida[mes]["faturamento"] = round(saida[mes]["faturamento"], 2)
        saida[mes]["pecas"] = round(saida[mes]["pecas"], 2)
    return saida


def montar_executivo(par: dict, real: dict = None) -> dict:
    """
    O painel pronto: uma linha por indicador, com o que foi digitado
    (peso, metas, despesas) cruzado com o que foi apurado.
    """
    exe = (par or {}).get("executivo") or {}
    indicadores = exe.get("indicadores") or indicadores_padrao()
    meses = list(exe.get("meses") or [])
    metas = exe.get("metas") or {}
    manuais = exe.get("reais") or {}
    real = real or {}

    linhas = []
    for ind in indicadores:
        chave = ind["chave"]
        peso = float(_numero(ind.get("peso")))
        invertido = bool(ind.get("invertido"))
        automatico = _texto(ind.get("fonte")).lower() != "manual"
        celulas = {}
        for mes in meses:
            meta = _numero((metas.get(chave) or {}).get(mes))
            if automatico and mes in real:
                valor = _numero(real[mes].get(chave))
                apurado = True
            else:
                # MES EM BRANCO NAO E MES ZERADO. No indicador digitado
                # (a DESPESA), campo vazio quer dizer "ainda nao apurei",
                # nao "gastei nada" - e como ela conta ao contrario,
                # tratar vazio como zero dava o TETO do peso para um mes
                # que nem aconteceu. Fica sem atingimento, entao.
                bruto = (manuais.get(chave) or {}).get(mes)
                apurado = bruto is not None and _texto(bruto) != ""
                valor = _numero(bruto)
            perc = atingimento(valor, meta, invertido) if apurado else None
            fator = fator_do_peso(perc)
            celulas[mes] = {
                "meta": meta, "real": valor if apurado else None,
                "apurado": apurado, "ating": perc,
                "ating_peso": None if fator is None else peso * fator / 100.0,
                "fator": fator,
            }
        linhas.append({**ind, "peso": peso, "automatico": automatico,
                       "meses": celulas})

    # a linha de TOTAL: o peso somado e os pontos somados mes a mes
    total = {"chave": "_total", "rotulo": "TOTAL",
             "peso": sum(l["peso"] for l in linhas), "automatico": True,
             "invertido": False, "meses": {}}
    for mes in meses:
        pontos = [l["meses"][mes]["ating_peso"] for l in linhas
                  if l["meses"][mes]["ating_peso"] is not None]
        total["meses"][mes] = {
            "meta": None, "real": None,
            "ating": (sum(pontos) / total["peso"] * 100.0
                      if total["peso"] and pontos else None),
            "ating_peso": sum(pontos) if pontos else None,
            "fator": None,
        }
    return {"linhas": linhas, "total": total, "meses": meses}


def acumulado_do_executivo(painel: dict, meses: list) -> dict:
    """
    O FECHAMENTO de um pedaco do ano - um trimestre, um semestre, o ano
    inteiro. Devolve, por indicador, a meta e o real SOMADOS dos meses e
    o atingimento em cima dessa soma.

    NAO E A MEDIA DOS PERCENTUAIS MENSAIS. Media de percentual nao
    fecha: um mes com meta de 100 mil e outro com meta de 1 milhao
    entrariam com o mesmo peso, e o trimestre diria uma coisa que a
    soma dos numeros desmente.

    MES SEM META NAO ENTRA, nem a meta nem o real. Senao o mes que
    ainda nao aconteceu - meta zero, real zero - derrubaria o
    trimestre inteiro para baixo.
    """
    meses = [m for m in (meses or [])]
    linhas = {}
    for linha in (painel or {}).get("linhas") or []:
        peso = float(_numero(linha.get("peso")))
        invertido = bool(linha.get("invertido"))
        meta = real = 0.0
        contados = 0
        for mes in meses:
            cel = (linha.get("meses") or {}).get(mes)
            if not cel or not cel.get("meta"):
                continue
            if not cel.get("apurado", True):
                continue          # mes ainda nao apurado nao entra
            meta += _numero(cel.get("meta"))
            real += _numero(cel.get("real"))
            contados += 1
        perc = atingimento(real, meta, invertido) if contados else None
        fator = fator_do_peso(perc)
        linhas[linha["chave"]] = {
            "meta": meta if contados else None,
            "real": real if contados else None,
            "ating": perc, "fator": fator,
            "ating_peso": None if fator is None else peso * fator / 100.0,
            "meses_com_meta": contados,
        }
    peso_total = sum(float(_numero(l.get("peso")))
                     for l in (painel or {}).get("linhas") or [])
    pontos = [c["ating_peso"] for c in linhas.values()
              if c["ating_peso"] is not None]
    return {
        "linhas": linhas,
        "meses": meses,
        "total": {
            "meta": None, "real": None,
            "ating": (sum(pontos) / peso_total * 100.0
                      if peso_total and pontos else None),
            "ating_peso": sum(pontos) if pontos else None,
            "fator": None,
            "meses_com_meta": max((c["meses_com_meta"]
                                   for c in linhas.values()), default=0),
        },
    }


def trimestres_do_executivo(painel: dict) -> list:
    """Os quatro blocos de tres meses, ja com o fechamento de cada um."""
    meses = list((painel or {}).get("meses") or [])
    saida = []
    for t in range(4):
        do_tri = meses[t * 3:(t + 1) * 3]
        if not do_tri:
            continue
        saida.append({"numero": t + 1, "meses": do_tri,
                      "fechamento": acumulado_do_executivo(painel, do_tri)})
    return saida


ARQUIVO_EXECUTIVO = "INDICADORES_EXECUTIVOS_BAP.xlsx"


def nome_do_executivo(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"INDICADORES_EXECUTIVOS_BAP_{hoje:%Y%m%d}.xlsx"


def gravar_excel_executivo(painel: dict, caminho) -> Path:
    """
    O painel numa folha so: INDICADOR e % PESO uma vez, e os quatro
    numeros repetindo mes a mes.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    caminho = Path(caminho)
    wb = Workbook()
    ws = wb.active
    ws.title = "PAINEL EXECUTIVO"
    meses = painel["meses"]

    azul = PatternFill("solid", fgColor="1F4E79")
    claro = PatternFill("solid", fgColor="DDEBF7")
    branco = Font(bold=True, color="FFFFFF")

    # duas linhas de cabecalho: o mes por cima dos quatro numeros dele
    ws.cell(1, 1, "INDICADOR").fill = azul
    ws.cell(1, 2, "% PESO").fill = azul
    for c in (1, 2):
        ws.cell(1, c).font = branco
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
        ws.cell(1, c).alignment = Alignment(horizontal="center",
                                            vertical="center")
    col = 3
    for mes in meses:
        ws.merge_cells(start_row=1, start_column=col, end_row=1,
                       end_column=col + 3)
        celula = ws.cell(1, col, rotulo_do_mes(mes))
        celula.fill = azul
        celula.font = branco
        celula.alignment = Alignment(horizontal="center")
        for j, titulo in enumerate(("META", "REAL", "% ATING. META",
                                    "% ATING PESO")):
            c = ws.cell(2, col + j, titulo)
            c.fill = claro
            c.font = Font(bold=True, color="1F4E79")
            c.alignment = Alignment(horizontal="center")
        col += 4

    linha = 3
    for l in list(painel["linhas"]) + [painel["total"]]:
        negrito = l["chave"] == "_total"
        ws.cell(linha, 1, l["rotulo"]).font = Font(bold=negrito)
        ws.cell(linha, 2, l["peso"] / 100.0).number_format = "0.0%"
        ws.cell(linha, 2).font = Font(bold=negrito)
        col = 3
        for mes in meses:
            cel = l["meses"][mes]
            inteiro = l["chave"] in ("positivacao", "cadastro_compra")
            formato = "#,##0" if inteiro else "#,##0.00"
            for j, campo, fmt in ((0, "meta", formato), (1, "real", formato),
                                  (2, "ating", "0.00%"),
                                  (3, "ating_peso", "0.00%")):
                v = cel[campo]
                if campo in ("ating", "ating_peso") and v is not None:
                    v = v / 100.0
                c = ws.cell(linha, col + j, v)
                c.number_format = fmt
                c.font = Font(bold=negrito)
            col += 4
        linha += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 10
    from openpyxl.utils import get_column_letter
    for i in range(3, col):
        ws.column_dimensions[get_column_letter(i)].width = 15
    ws.freeze_panes = "C3"

    # ---- o fechamento de cada trimestre, em lista ---------------------
    # Plana de proposito: TRIMESTRE na coluna, uma linha por indicador.
    # E o formato que o Power BI come sem pedir nada.
    wt = wb.create_sheet("FECHAMENTO TRIMESTRE")
    cabs = ["TRIMESTRE", "MESES", "INDICADOR", "% PESO", "META", "REAL",
            "% ATING. META", "% ATING PESO"]
    for j, titulo in enumerate(cabs, start=1):
        c = wt.cell(1, j, titulo)
        c.fill = azul
        c.font = branco
        c.alignment = Alignment(horizontal="center")
    verde = PatternFill("solid", fgColor="DDF0E2")
    rotulos = {l["chave"]: l["rotulo"] for l in painel["linhas"]}
    pesos = {l["chave"]: l["peso"] for l in painel["linhas"]}
    inteiros = ("positivacao", "cadastro_compra")
    linha = 2
    for bloco in trimestres_do_executivo(painel):
        nome = f"{bloco['numero']}o TRIMESTRE"
        janela = " ".join(rotulo_do_mes(m) for m in bloco["meses"])
        for chave, cel in bloco["fechamento"]["linhas"].items():
            formato = "#,##0" if chave in inteiros else "#,##0.00"
            wt.cell(linha, 1, nome)
            wt.cell(linha, 2, janela)
            wt.cell(linha, 3, rotulos.get(chave, chave))
            wt.cell(linha, 4, pesos.get(chave, 0) / 100.0).number_format = "0.0%"
            wt.cell(linha, 5, cel["meta"]).number_format = formato
            wt.cell(linha, 6, cel["real"]).number_format = formato
            for j, campo in ((7, "ating"), (8, "ating_peso")):
                v = cel[campo]
                wt.cell(linha, j,
                        None if v is None else v / 100.0).number_format = "0.00%"
            linha += 1
        t = bloco["fechamento"]["total"]
        wt.cell(linha, 1, nome)
        wt.cell(linha, 2, janela)
        wt.cell(linha, 3, "TOTAL DO TRIMESTRE")
        wt.cell(linha, 4, painel["total"]["peso"] / 100.0).number_format = "0.0%"
        for j, campo in ((7, "ating"), (8, "ating_peso")):
            v = t[campo]
            wt.cell(linha, j,
                    None if v is None else v / 100.0).number_format = "0.00%"
        for j in range(1, 9):
            wt.cell(linha, j).font = Font(bold=True)
            wt.cell(linha, j).fill = verde
        linha += 1
    for letra, larg in (("A", 15), ("B", 24), ("C", 26), ("D", 10),
                        ("E", 16), ("F", 16), ("G", 15), ("H", 15)):
        wt.column_dimensions[letra].width = larg
    wt.freeze_panes = "A2"

    wr = wb.create_sheet("COMO A CONTA E FEITA")
    for i, texto in enumerate([
            "A ESCADA DO PESO", "",
            f"abaixo de {PISO_DO_PESO:.0f}% da meta ... 0% do peso",
            f"exatamente {PISO_DO_PESO:.0f}% ............ "
            f"{PESO_NO_PISO:.0f}% do peso",
            f"a partir de {PISO_DO_PESO + 1:.0f}% ........... cada 1% vale "
            f"{PONTOS_POR_PONTO} pontos percentuais",
            f"teto ........................ {TETO_DO_PESO:.0f}% do peso "
            f"(chega la com {PISO_DO_PESO + (TETO_DO_PESO - PESO_NO_PISO) / PONTOS_POR_PONTO:.0f}% da meta)",
            "", "100% da meta entrega 100% do peso.", "",
            "% ATING PESO = peso do indicador x esse fator", "",
            "DESPESAS conta ao contrario: gastar MENOS que a meta e bom,",
            "entao ali o atingimento e meta / real.", "",
            "DE ONDE VEM O REAL", "",
            "FATURAMENTO TOTAL .... ftPedidos, VND + VEA menos DEV, no mes",
            "POSITIVACAO .......... clientes distintos que faturaram no mes",
            "FATURAMENTO DE PECAS . o mesmo faturamento, so a categoria PECAS",
            "CADASTRO COM COMPRA .. dClientesBap: A1_DTCAD no mes E",
            "                       alguma venda dele no MESMO mes",
            "DESPESAS ............. digitada na tela - nao existe na "
            "TABELA_BAP", "",
            "O FECHAMENTO DO TRIMESTRE", "",
            "A aba FECHAMENTO TRIMESTRE SOMA a meta e o real dos tres meses",
            "e calcula o atingimento em cima dessa soma. NAO e a media dos",
            "tres percentuais: media de percentual nao fecha - um mes com",
            "meta de 100 mil e outro com meta de 1 milhao entrariam com o",
            "mesmo peso.", "",
            "MES SEM META NAO ENTRA, nem a meta nem o real: senao o mes que",
            "ainda nao aconteceu derrubaria o trimestre inteiro."]):
        wr.cell(i + 1, 1, texto)
    wr.column_dimensions["A"].width = 84

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# ==========================================================================
# A META IMPORTADA DO EXCEL
# ==========================================================================
# A diretoria fecha a meta por CIDADE e por CATEGORIA. O arquivo tem
# cinco colunas:
#
#       ANO | MES | CIDADE | CATEGORIA | META
#
# Dali para baixo o programa nao INVENTA meta nenhuma: ele DISTRIBUI a
# meta da cidade entre os clientes dela, na proporcao do M3M de cada um,
# e as somas sobem sozinhas para bairro, zona, vendedor, supervisor, UF
# e gerente. A soma dos clientes de uma cidade fecha EXATAMENTE com o que
# foi importado para ela.
#
# Cidade que nao vier no arquivo continua pela mecanica antiga (o
# crescimento M3M x M3M anterior, com o piso) - assim uma importacao
# parcial nao deixa ninguem sem meta.
ARQUIVO_METAS = "METAS_BAP.xlsx"
COLUNAS_METAS = ("ANO", "MES", "CIDADE", "CATEGORIA", "META")
ARQUIVO_MODELO_META = "MODELO_META_BAP.xlsx"

# A UF de cada polo (a coluna CIDADE do modelo e da aba Filiais e o nome
# do POLO da filial, nao a cidade do cliente). Sao sete e nao mudam.
UF_DO_POLO = {
    "MANAUS": "AM", "BOAVISTA": "RR", "MACAPA": "AP", "BELEM": "PA",
    "SANTAREM": "PA", "SAOLUIS": "MA", "MATOGROSSO": "MT",
    "CUIABA": "MT", "IMPERATRIZ": "MA", "PARAUAPEBAS": "PA",
}

# como o nome da categoria pode vir escrito no arquivo
APELIDOS_DE_CATEGORIA = {
    "PECAS": "pecas", "PECA": "pecas", "PEÇAS": "pecas", "PEÇA": "pecas",
    # FILTRO e peca: e um item da linha, nao uma categoria a parte do
    # ponto de vista da meta (o programa tem quatro, nao cinco)
    "FILTRO": "pecas", "FILTROS": "pecas",
    "ACESSORIO": "pecas", "ACESSORIOS": "pecas",
    "BATERIA": "bateria", "BATERIAS": "bateria",
    "LUBRIFICANTE": "lubrificante", "LUBRIFICANTES": "lubrificante",
    "LUBRIF": "lubrificante", "OLEO": "lubrificante",
    "PNEU": "pneu", "PNEUS": "pneu",
}
# quando a linha nao diz a categoria (ou diz TOTAL), a meta e da cidade
# inteira e se reparte pelos percentuais da aba 1
CATEGORIA_TOTAL = ("", "TOTAL", "GERAL", "TODAS", "TODOS")


def chave_de_cidade(texto) -> str:
    """MANAUS, Manaus e ' manaus ' viram a mesma chave."""
    limpo = _texto(texto).upper()
    for de, para in (("Á", "A"), ("À", "A"), ("Â", "A"), ("Ã", "A"),
                     ("É", "E"), ("Ê", "E"), ("Í", "I"), ("Ó", "O"),
                     ("Ô", "O"), ("Õ", "O"), ("Ú", "U"), ("Ç", "C"),
                     ("¿", "")):
        limpo = limpo.replace(de, para)
    return re.sub(r"[^A-Z0-9]", "", limpo)


def chave_de_categoria(texto) -> str:
    """O nome da categoria como o programa a conhece. '' = a cidade toda."""
    bruto = _texto(texto).upper().strip()
    if bruto in CATEGORIA_TOTAL:
        return ""
    if bruto in APELIDOS_DE_CATEGORIA:
        return APELIDOS_DE_CATEGORIA[bruto]
    so_letras = re.sub(r"[^A-Z]", "", bruto)
    for apelido, chave in APELIDOS_DE_CATEGORIA.items():
        if re.sub(r"[^A-Z]", "", apelido) == so_letras:
            return chave
    # "PEÇAS - LINHA LEVE", "PEÇAS - LINHA PESADA", "PECAS MOTO": a meta
    # do programa tem QUATRO categorias, entao a linha nao importa - o
    # que manda e a primeira palavra
    primeira = re.sub(r"[^A-ZÇ ]", " ", bruto).split()
    if primeira:
        chave = APELIDOS_DE_CATEGORIA.get(primeira[0])
        if chave:
            return chave
    return "?"


def chave_de_polo(texto) -> str:
    """O polo da filial como chave. MATOGROSSO, SAO LUIS, BELEM..."""
    return chave_de_cidade(texto)


def uf_do_polo(polo) -> str:
    """A UF daquele polo. Sem saber, devolve vazio."""
    return UF_DO_POLO.get(chave_de_polo(polo), "")


def ler_polos_da_tabela(caminho_tabela) -> dict:
    """
    QUE CIDADE PERTENCE A QUE FILIAL, da aba Filiais da TABELA_BAP.

        {"polo_da_cidade": {chave_cidade: chave_polo},
         "polos": {chave_polo: nome como veio},
         "filiais": {chave_polo: COD_FILIAL},
         "cidades_do_polo": {chave_polo: [nomes]}}

    A aba lista CIDADE (o POLO da filial) e CIDADE_INTERIOR (a cidade de
    verdade). E dela que sai o vinculo - o modelo de meta vem por POLO e
    os clientes vem por CIDADE.
    """
    vazio = {"polo_da_cidade": {}, "polos": {}, "filiais": {},
             "cidades_do_polo": {}}
    caminho_tabela = Path(caminho_tabela) if caminho_tabela else None
    if not caminho_tabela or not caminho_tabela.exists():
        return vazio
    try:
        wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    except (OSError, ValueError):
        return vazio
    try:
        if "Filiais" not in wb.sheetnames:
            return vazio
        it = wb["Filiais"].iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]

        def onde(*nomes):
            for n in nomes:
                if _chave(n) in cab:
                    return cab.index(_chave(n))
            return None

        i_polo = onde("CIDADE")
        i_cid = onde("CIDADE_INTERIOR")
        i_fil = onde("FILIAL_BAP", "COD_FILIAL")
        if i_polo is None:
            return vazio
        saida = {"polo_da_cidade": {}, "polos": {}, "filiais": {},
                 "cidades_do_polo": {}}
        for r in it:
            nome_polo = _texto(r[i_polo])
            if not nome_polo:
                continue
            chave_p = chave_de_polo(nome_polo)
            saida["polos"].setdefault(chave_p, nome_polo.upper())
            if i_fil is not None and r[i_fil]:
                saida["filiais"].setdefault(chave_p, _texto(r[i_fil]))
            # o proprio polo tambem e uma cidade
            saida["polo_da_cidade"].setdefault(chave_p, chave_p)
            nome_cid = _texto(r[i_cid]) if i_cid is not None else ""
            if nome_cid:
                chave_c = chave_de_cidade(nome_cid)
                saida["polo_da_cidade"].setdefault(chave_c, chave_p)
                lista = saida["cidades_do_polo"].setdefault(chave_p, [])
                if nome_cid.upper() not in lista:
                    lista.append(nome_cid.upper())
        return saida
    except (OSError, ValueError, StopIteration):
        return vazio
    finally:
        wb.close()


def _polo_mais_perto(uf, cidade, polos_da_uf) -> str:
    """
    A cidade que nao esta na aba Filiais vai para o polo MAIS PROXIMO da
    mesma UF. Com um polo so na UF nem ha o que decidir; com dois (o PA
    tem BELEM e SANTAREM) e a distancia que resolve - e ela resolve bem:
    Castanhal cai em Belem, Itaituba cai em Santarem.
    """
    if not polos_da_uf:
        return ""
    if len(polos_da_uf) == 1:
        return polos_da_uf[0][0]
    try:
        import geografia as geo
    except ImportError:
        return polos_da_uf[0][0]
    melhor, menor = "", None
    for chave_p, nome_p in polos_da_uf:
        d = geo.distancia_cidades(uf, cidade, uf, nome_p)
        if d is None:
            continue
        if menor is None or d < menor:
            melhor, menor = chave_p, d
    return melhor or polos_da_uf[0][0]


def ligar_cidades_aos_polos(polos: dict, clientes: list) -> dict:
    """
    Fecha o mapa CIDADE -> POLO para a base inteira.

    Em ordem:
      1. o que a aba Filiais da TABELA_BAP diz, que e exato;
      2. o polo MAIS PROXIMO da mesma UF, pela coordenada da cidade;
      3. nada - a cidade fica sem polo e o cliente dela segue pelo
         crescimento, como sempre. O programa diz quantos foram.

    Sem o passo 2 a meta do polo cairia toda nas quatro cidades que a
    aba Filiais lista, e Parintins - que e do CD de Manaus - ficaria de
    fora da meta de Manaus.
    """
    polo_da_cidade = dict((polos or {}).get("polo_da_cidade") or {})
    nomes = dict((polos or {}).get("polos") or {})
    por_uf = defaultdict(list)
    for chave_p, nome_p in nomes.items():
        uf = UF_DO_POLO.get(chave_p, "")
        if uf:
            por_uf[uf].append((chave_p, nome_p))
    sem_polo = set()
    for c in clientes or []:
        cidade = _texto(c.get("cidade"))
        if not cidade:
            continue
        chave_c = chave_de_cidade(cidade)
        if chave_c in polo_da_cidade:
            continue
        uf = _texto(c.get("uf")).upper()
        escolhido = _polo_mais_perto(uf, cidade, por_uf.get(uf) or [])
        if escolhido:
            polo_da_cidade[chave_c] = escolhido
        else:
            sem_polo.add(chave_c)
    return {"polo_da_cidade": polo_da_cidade,
            "polos": nomes,
            "filiais": dict((polos or {}).get("filiais") or {}),
            "cidades_do_polo": dict((polos or {}).get("cidades_do_polo")
                                    or {}),
            "sem_polo": sorted(sem_polo)}


def _mes_do_cabecalho(valor):
    """
    O titulo da coluna de mes do modelo. Aceita a data (01/01/2026), o
    texto AAAA-MM, 'jan/26' e 'JANEIRO/2026'. Devolve 'AAAA-MM' ou ''.
    """
    if isinstance(valor, (dt.datetime, dt.date)):
        return f"{valor.year:04d}-{valor.month:02d}"
    bruto = _texto(valor)
    if not bruto:
        return ""
    normal = normalizar_competencia(bruto)
    if normal:
        return normal
    limpo = re.sub(r"[^A-Za-z0-9]", " ", bruto).upper().split()
    if len(limpo) == 2:
        nomes = [m.upper()[:3] for m in NOMES_DOS_MESES]
        pedaco = limpo[0][:3]
        if pedaco in nomes:
            ano = int(_numero(limpo[1]) or 0)
            if ano < 100:
                ano += 2000
            if 1900 < ano < 2200:
                return f"{ano:04d}-{nomes.index(pedaco) + 1:02d}"
    return ""


def ler_modelo_de_meta(caminho) -> dict:
    """
    O MODELO LARGO: uma linha por FILIAL x CATEGORIA e uma COLUNA POR
    MES. E o formato que a diretoria usa - o mesmo arquivo cobre o ano
    inteiro, e cada mes e uma coluna com o titulo na data.

        Dono | UF | ... | COD_FILIAL | CD_FILIAL | CIDADE |
        CIDADE_INTERIOR | CATEGORIA | CATEGORIA PRODUTOS |
        01/01/2024 | 01/02/2024 | ... | 01/12/2026

    A CIDADE aqui e o POLO da filial (MANAUS, BELEM, MATOGROSSO...), nao
    a cidade do cliente. Quem faz a ponte entre os dois e a aba Filiais
    da TABELA_BAP - ver ler_polos_da_tabela().

    Devolve a MESMA forma de ler_metas_importadas(), para o resto do
    programa nao precisar saber de que formato a meta veio.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de metas nao encontrado: {caminho}")
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            cabecalho = list(next(it))
        except StopIteration:
            raise ValueError("O arquivo de metas esta vazio.")
        cab = [_chave(c) for c in cabecalho]

        def onde(*nomes):
            for n in nomes:
                if _chave(n) in cab:
                    return cab.index(_chave(n))
            return None

        # as colunas de mes: titulo que e data ou que vira AAAA-MM
        meses_col = [(j, _mes_do_cabecalho(v))
                     for j, v in enumerate(cabecalho)]
        meses_col = [(j, m) for j, m in meses_col if m]
        if not meses_col:
            raise ValueError(
                "Nao achei nenhuma coluna de MES neste arquivo. No modelo, "
                "cada mes e uma coluna com a data no titulo (01/01/2026, "
                "01/02/2026...).")
        i_polo = onde("CIDADE")
        i_fil = onde("COD_FILIAL", "FILIAL_BAP")
        i_cat = onde("CATEGORIA PRODUTOS", "CATEGORIA_PRODUTOS",
                     "CATEGORIA")
        i_uf = onde("UF")
        if i_polo is None and i_fil is None:
            raise ValueError(
                "O modelo precisa da coluna CIDADE (o polo da filial) ou "
                "COD_FILIAL.\n\nAchei: "
                + ", ".join(str(c) for c in cabecalho if c)[:400])

        mapa: dict[str, dict] = {}
        polos: dict[str, str] = {}
        filiais: dict[str, str] = {}
        ufs: dict[str, str] = {}
        avisos: list[str] = []
        lidas = 0
        for n, r in enumerate(it, start=2):
            if r is None or all(v is None for v in r):
                continue
            nome_polo = _texto(r[i_polo]) if i_polo is not None else ""
            cod_fil = _texto(r[i_fil]) if i_fil is not None else ""
            chave_p = chave_de_polo(nome_polo or cod_fil)
            if not chave_p:
                avisos.append(f"linha {n}: sem CIDADE e sem COD_FILIAL - "
                              f"pulada")
                continue
            categoria = chave_de_categoria(
                r[i_cat] if i_cat is not None else "")
            if categoria == "?":
                avisos.append(f"linha {n}: categoria "
                              f"'{_texto(r[i_cat])}' desconhecida - pulada")
                continue
            polos.setdefault(chave_p, (nome_polo or cod_fil).upper())
            if cod_fil:
                filiais.setdefault(chave_p, cod_fil)
            if i_uf is not None and _texto(r[i_uf]):
                ufs.setdefault(chave_p, _texto(r[i_uf]).upper())
            tem_valor = False
            for j, competencia in meses_col:
                if j >= len(r):
                    continue
                valor = _numero(r[j])
                if not valor:
                    continue
                do_mes = mapa.setdefault(competencia, {})
                do_polo = do_mes.setdefault(chave_p, {})
                do_polo[categoria] = do_polo.get(categoria, 0.0) + valor
                tem_valor = True
            if tem_valor:
                lidas += 1
    finally:
        wb.close()

    if not lidas:
        raise ValueError(
            "O modelo nao tem nenhum valor de meta preenchido. Preencha "
            "pelo menos um mes de uma filial.")
    return {"mapa": mapa, "cidades": polos, "polos": polos,
            "filiais": filiais, "ufs": ufs,
            "linhas": lidas, "meses": sorted(mapa), "avisos": avisos[:40],
            "arquivo": str(caminho), "formato": "modelo",
            "por_polo": True}


def _e_modelo_largo(caminho) -> bool:
    """O arquivo e o MODELO (mes por coluna) ou a lista simples?"""
    try:
        wb = load_workbook(Path(caminho), read_only=True, data_only=True)
    except (OSError, ValueError):
        return False
    try:
        it = wb.active.iter_rows(values_only=True)
        cabecalho = list(next(it))
    except (StopIteration, ValueError):
        return False
    finally:
        wb.close()
    cab = [_chave(c) for c in cabecalho]
    # a lista simples tem ANO e MES como colunas; o modelo tem os meses
    # espalhados no cabecalho
    if _chave("ANO") in cab and _chave("MES") in cab:
        return False
    return sum(1 for v in cabecalho if _mes_do_cabecalho(v)) >= 2


def ler_metas(caminho) -> dict:
    """
    Le o arquivo de metas seja qual for o formato:

        MODELO LARGO ..... uma coluna por mes, a linha e FILIAL x
                           CATEGORIA (MODELO_META_BAP.xlsx)
        LISTA SIMPLES .... ANO | MES | CIDADE | CATEGORIA | META
                           (METAS_BAP.xlsx)

    Quem chama nao precisa saber qual e: a forma de saida e a mesma.
    """
    if _e_modelo_largo(caminho):
        return ler_modelo_de_meta(caminho)
    return ler_metas_importadas(caminho)


def ler_metas_importadas(caminho) -> dict:
    """
    Le o Excel de metas. Devolve

        {"mapa": {"AAAA-MM": {chave_cidade: {categoria|"": valor}}},
         "cidades": {chave: nome como veio}, "linhas": n,
         "meses": [...], "avisos": [...]}

    Linha sem ano, sem mes ou sem cidade e pulada com aviso - e melhor
    dizer o que ficou de fora do que somar errado calado.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de metas nao encontrado: {caminho}")
    wb = load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        cab = [_chave(c) for c in next(it)]
    except StopIteration:
        wb.close()
        raise ValueError("O arquivo de metas esta vazio.")

    def onde(*nomes):
        for n in nomes:
            if _chave(n) in cab:
                return cab.index(_chave(n))
        return None

    i_ano = onde("ANO")
    i_mes = onde("MES", "MÊS")
    i_cid = onde("CIDADE", "MUNICIPIO", "MUNICÍPIO")
    i_cat = onde("CATEGORIA", "LINHA")
    i_val = onde("META", "META EM RECEITA", "RECEITA", "VALOR")
    if None in (i_ano, i_mes, i_cid, i_val):
        wb.close()
        raise ValueError(
            "O arquivo de metas precisa das colunas ANO, MES, CIDADE, "
            "CATEGORIA e META na primeira linha.\n\nAchei: "
            + ", ".join(str(c) for c in cab if c))

    mapa: dict[str, dict] = {}
    cidades: dict[str, str] = {}
    avisos: list[str] = []
    lidas = 0
    for n, r in enumerate(it, start=2):
        if r is None or all(v is None for v in r):
            continue
        ano = int(_numero(r[i_ano]) or 0)
        mes = int(_numero(r[i_mes]) or 0)
        nome_cidade = _texto(r[i_cid])
        chave_cid = chave_de_cidade(nome_cidade)
        if not (1900 < ano < 2200) or not (1 <= mes <= 12) or not chave_cid:
            avisos.append(f"linha {n}: ANO, MES ou CIDADE em branco ou "
                          f"invalido - pulada")
            continue
        categoria = chave_de_categoria(
            r[i_cat] if i_cat is not None else "")
        if categoria == "?":
            avisos.append(f"linha {n}: categoria "
                          f"'{_texto(r[i_cat])}' desconhecida - pulada")
            continue
        valor = _numero(r[i_val])
        competencia = f"{ano:04d}-{mes:02d}"
        cidades.setdefault(chave_cid, nome_cidade.strip().upper())
        do_mes = mapa.setdefault(competencia, {})
        da_cidade = do_mes.setdefault(chave_cid, {})
        da_cidade[categoria] = da_cidade.get(categoria, 0.0) + valor
        lidas += 1
    wb.close()

    if not lidas:
        raise ValueError("O arquivo nao tem nenhuma linha de meta valida.")
    return {"mapa": mapa, "cidades": cidades, "linhas": lidas,
            "meses": sorted(mapa), "avisos": avisos[:40],
            "arquivo": str(caminho)}


def metas_do_mes(importadas: dict, competencia: str) -> dict:
    """A meta de cada cidade naquele mes: {chave_cidade: {cat: valor}}."""
    if not importadas:
        return {}
    return dict((importadas.get("mapa") or {}).get(
        normalizar_competencia(competencia) or "", {}))


def _meta_total_da_cidade(por_categoria: dict, par: dict) -> tuple:
    """
    O total da cidade e a fatia de cada categoria.

    Quando o arquivo traz uma linha por categoria, elas mandam. Quando
    traz so o total (categoria vazia ou TOTAL), ele se reparte pelos
    percentuais da aba 1.
    """
    do_total = float(por_categoria.get("", 0.0))
    por_cat = {c: float(por_categoria.get(c, 0.0))
               for c, _, _ in CATEGORIAS}
    soma_cat = sum(por_cat.values())
    if soma_cat > 0:
        return soma_cat + do_total, por_cat, do_total
    return do_total, por_cat, do_total


# as colunas do MODELO por filial, na mesma ordem do arquivo que a
# diretoria usa. As dez primeiras identificam a linha; da decima
# primeira em diante e um mes por coluna.
COLUNAS_MODELO_META = ("Dono", "UF", "UF_INT/CAP 2", "Canal", "COD_FILIAL",
                       "CD_FILIAL", "CIDADE", "CIDADE_INTERIOR",
                       "CATEGORIA", "CATEGORIA PRODUTOS")

# as categorias como elas aparecem no modelo. A coluna CATEGORIA e a
# familia; CATEGORIA PRODUTOS abre a peca em linha leve e pesada. As
# duas caem em "pecas" na hora de calcular - a meta do programa tem
# quatro categorias, nao seis.
CATEGORIAS_DO_MODELO = [
    ("PEÇAS", "PEÇAS - LINHA LEVE"),
    ("PEÇAS", "PEÇAS - LINHA PESADA"),
    ("FILTRO", "FILTRO"),
    ("OLEO", "OLEO"),
    ("BATERIA", "BATERIA"),
    ("PNEU", "PNEU"),
]

# as sete filiais BAP, para o modelo sair preenchido mesmo sem a
# TABELA_BAP na pasta
FILIAIS_PADRAO = [
    ("40101001", "26", "MATOGROSSO"), ("40101002", "28", "MANAUS"),
    ("40101003", "25", "MACAPÁ"), ("40101004", "29", "BOA VISTA"),
    ("40101005", "64", "BELÉM"), ("40101006", "91", "SÃO LUIS"),
    ("40101007", "27", "SANTARÉM"),
]


def filiais_do_modelo(caminho_tabela=None) -> list:
    """
    [(COD_FILIAL, CD_FILIAL, POLO)] - da TABELA_BAP quando ela estiver
    na pasta, e da lista de fabrica quando nao estiver.
    """
    polos = ler_polos_da_tabela(caminho_tabela) if caminho_tabela else {}
    nomes = polos.get("polos") or {}
    if not nomes:
        return list(FILIAIS_PADRAO)
    filiais = polos.get("filiais") or {}
    saida = []
    for chave_p, nome in sorted(nomes.items(), key=lambda x: x[1]):
        cod = filiais.get(chave_p, "")
        cd = next((c for f, c, p in FILIAIS_PADRAO
                   if chave_de_polo(p) == chave_p), "")
        saida.append((cod, cd, nome))
    return saida


def modelo_de_meta_por_filial(caminho, ano=None, dono="",
                              caminho_tabela=None) -> Path:
    """
    O MODELO por FILIAL x CATEGORIA, com UM MES POR COLUNA - o mesmo
    formato do arquivo que a diretoria fecha. E so digitar o valor na
    celula do mes e importar de volta.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    caminho = Path(caminho)
    ano = int(ano or dt.date.today().year)
    filiais = filiais_do_modelo(caminho_tabela)

    wb = Workbook()
    ws = wb.active
    ws.title = "METAS"
    azul = PatternFill("solid", fgColor="1F4E79")
    claro = PatternFill("solid", fgColor="DDEBF7")

    for j, titulo in enumerate(COLUNAS_MODELO_META, start=1):
        c = ws.cell(1, j, titulo)
        c.fill = azul
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    base = len(COLUNAS_MODELO_META)
    for m in range(1, 13):
        c = ws.cell(1, base + m, dt.date(ano, m, 1))
        c.number_format = "MMM/YY"
        c.fill = claro
        c.font = Font(bold=True, color="1F4E79")
        c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = f"{get_column_letter(base + 1)}2"

    linha = 2
    for cod, cd, polo in filiais:
        uf = uf_do_polo(polo)
        for categoria, produto in CATEGORIAS_DO_MODELO:
            valores = [dono, uf, "Bap", "Bap", cod, cd, polo, polo,
                       categoria, produto]
            for j, v in enumerate(valores, start=1):
                ws.cell(linha, j, v)
            for m in range(1, 13):
                ws.cell(linha, base + m).number_format = "#,##0.00"
            linha += 1
    for letra, larg in zip("ABCDEFGHIJ",
                           (14, 6, 13, 8, 13, 11, 16, 18, 12, 22)):
        ws.column_dimensions[letra].width = larg
    for m in range(1, 13):
        ws.column_dimensions[get_column_letter(base + m)].width = 13

    wl = wb.create_sheet("COMO PREENCHER")
    regras = [
        ("O QUE PREENCHER", "so as doze colunas de mes. O resto ja vem "
                            "pronto."),
        ("CIDADE", "e o POLO da filial (MANAUS, BELEM, MATOGROSSO...), "
                   "nao a cidade do cliente."),
        ("QUEM LIGA UM AO OUTRO",
         "a aba Filiais da TABELA_BAP: ela diz que CIDADE_INTERIOR "
         "pertence a que filial. A cidade que nao estiver la vai para o "
         "polo MAIS PROXIMO da mesma UF."),
        ("CATEGORIA PRODUTOS",
         "PEÇAS - LINHA LEVE, PEÇAS - LINHA PESADA e FILTRO caem todas "
         "em PECAS: a meta do programa tem quatro categorias (PECAS, "
         "BATERIA, LUBRIFICANTE e PNEU), nao seis. OLEO e LUBRIFICANTE."),
        ("COMO A META DESCE",
         "a meta da filial no mes se reparte entre os clientes dela na "
         "proporcao do FAT M3M de cada um. A soma dos clientes fecha "
         "EXATAMENTE com o que foi digitado aqui."),
        ("CLIENTE SEM M3M",
         "nao recebe meta de faturamento - nao ha por onde ratear. Ele "
         "continua com meta de VISITA e de POSITIVACAO."),
        ("O PISO POR CLIENTE",
         "nao vale na filial importada: se valesse, a soma estouraria a "
         "meta que voce fechou."),
        ("FILIAL SEM LINHA AQUI",
         "segue pelo crescimento (M3M atual x M3M anterior), como "
         "sempre. Da para importar so uma parte."),
    ]
    for i, (a, b) in enumerate(regras, start=1):
        wl.cell(i, 1, a).font = Font(bold=True, size=10)
        wl.cell(i, 2, b).font = Font(size=10)
        wl.cell(i, 2).alignment = Alignment(wrap_text=True, vertical="top")
    wl.column_dimensions["A"].width = 26
    wl.column_dimensions["B"].width = 86

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def modelo_de_metas(caminho, cidades=None, ano=None) -> Path:
    """
    O modelo para preencher: ANO, MES, CIDADE, CATEGORIA, META, ja com as
    linhas montadas para o ano inteiro. E so digitar a coluna META.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    caminho = Path(caminho)
    ano = int(ano or dt.date.today().year)
    cidades = [c for c in (cidades or []) if _texto(c)] or ["(digite a cidade)"]

    wb = Workbook()
    ws = wb.active
    ws.title = "METAS"
    azul = PatternFill("solid", fgColor="1F4E79")
    for j, titulo in enumerate(COLUNAS_METAS, start=1):
        c = ws.cell(1, j, titulo)
        c.fill = azul
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(horizontal="center")
    linha = 2
    for mes in range(1, 13):
        for cidade in cidades:
            for _, rotulo, _ in CATEGORIAS:
                ws.cell(linha, 1, ano)
                ws.cell(linha, 2, mes)
                ws.cell(linha, 3, _texto(cidade).upper())
                ws.cell(linha, 4, rotulo)
                ws.cell(linha, 5, 0).number_format = "#,##0.00"
                linha += 1
    for letra, largura in (("A", 8), ("B", 8), ("C", 26), ("D", 16),
                           ("E", 16)):
        ws.column_dimensions[letra].width = largura
    ws.freeze_panes = "A2"

    wr = wb.create_sheet("COMO PREENCHER")
    for i, texto in enumerate([
            "UMA LINHA POR ANO, MES, CIDADE E CATEGORIA.", "",
            "ANO ......... 2026",
            "MES ......... 1 a 12",
            "CIDADE ...... o nome como esta no cadastro (MANAUS, BELEM...).",
            "              Acento e maiuscula nao importam.",
            "CATEGORIA ... PECAS, BATERIA, LUBRIFICANTE ou PNEU.",
            "              Deixe TOTAL (ou em branco) para dar a meta da",
            "              cidade inteira - ela se reparte pelos",
            "              percentuais da aba 1.",
            "META ........ o valor em receita, so numero.", "",
            "O QUE O PROGRAMA FAZ COM ISSO", "",
            "Ele NAO inventa meta. Distribui a meta da cidade entre os",
            "clientes dela, na proporcao do M3M de cada um, e as somas",
            "sobem para bairro, zona, vendedor, supervisor, UF e gerente.",
            "A soma dos clientes de uma cidade fecha EXATAMENTE com o que",
            "voce importou para ela.", "",
            "Cliente sem M3M nenhum nao recebe meta de faturamento - ele",
            "entra pela POSITIVACAO, como sempre foi.", "",
            "Cidade que nao vier no arquivo continua pela mecanica antiga",
            "(crescimento M3M x M3M anterior, com o piso). Assim uma",
            "importacao parcial nao deixa ninguem sem meta.", "",
            "O PISO POR CLIENTE NAO VALE na cidade importada: se valesse,",
            "a soma estouraria a meta que a diretoria fechou."]):
        wr.cell(i + 1, 1, texto)
    wr.column_dimensions["A"].width = 76

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# --------------------------------------------------------------------------
# IMPRIMIR: a folha executiva
# --------------------------------------------------------------------------
# A tela nunca vai caber inteira quando sao oito metas em META/REAL/ATING.
# Entao a folha de impressao e outra coisa: um HTML em A4 DEITADO, com as
# colunas escolhidas, uma pagina por recorte, que abre no navegador - de
# la se imprime ou se salva em PDF. Sem instalar nada: o navegador ja
# esta na maquina, e uma biblioteca de PDF em Python seria mais um
# programa para manter em cada notebook do backoffice.
TIPOS_DE_COLUNA = ("texto", "dinheiro", "inteiro", "pct", "decimal", "data")


def _fmt_br(valor, casas=2) -> str:
    try:
        texto = f"{float(valor):,.{casas}f}"
    except (TypeError, ValueError):
        return ""
    return texto.replace(",", "@").replace(".", ",").replace("@", ".")


def _celula_impressa(valor, tipo: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo == "dinheiro":
        return _fmt_br(valor, 2)
    if tipo == "decimal":
        return _fmt_br(valor, 1)
    if tipo == "inteiro":
        try:
            return _fmt_br(int(round(float(valor))), 0)
        except (TypeError, ValueError):
            return ""
    if tipo == "pct":
        return _fmt_br(valor, 1) + "%"
    if tipo == "data":
        # sem isto a data sairia como "2026-08-15 00:00:00" na folha
        d = _data(valor)
        return f"{d:%d/%m/%Y}" if d is not None else ""
    return _texto(valor)


def _escapar(texto) -> str:
    return (_texto(texto).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _tamanho_da_folha(colunas: int, linhas: int) -> float:
    """
    O corpo da letra que faz a pagina fechar. Uma folha A4 deitada com
    margem de 8mm cabe cerca de 45 linhas a 9pt; daí para baixo a letra
    encolhe, ate o limite do que ainda se le (5,5pt).
    """
    tamanho = 9.0
    if colunas > 10:
        tamanho -= 0.5
    if colunas > 14:
        tamanho -= 0.5
    for teto, corpo in ((45, tamanho), (55, 7.5), (70, 6.5), (90, 5.5)):
        if linhas <= teto:
            return min(tamanho, corpo)
    return 5.0


def html_para_imprimir(blocos: list, titulo: str, subtitulo: str = "",
                       rodape: str = "") -> str:
    """
    blocos = [{"titulo": "VENDEDOR",
               "colunas": [(rotulo, chave, tipo), ...],
               "linhas": [dict, ...],
               "total": dict ou None}]
    Cada bloco vira UMA pagina.
    """
    partes = ["<!DOCTYPE html><html lang='pt-BR'><head>",
              "<meta charset='utf-8'>",
              f"<title>{_escapar(titulo)}</title>", "<style>",
              "@page { size: A4 landscape; margin: 8mm; }",
              "* { box-sizing: border-box; }",
              "body { font-family: Segoe UI, Arial, sans-serif; margin: 0;",
              "       color: #1B2B3A; }",
              ".folha { page-break-after: always; padding: 0 0 6mm 0; }",
              ".folha:last-child { page-break-after: auto; }",
              ".topo { border-bottom: 2px solid #14375E; margin-bottom: 4px;",
              "        padding-bottom: 3px; }",
              ".topo h1 { font-size: 13pt; margin: 0; color: #14375E; }",
              ".topo .sub { font-size: 8pt; color: #5A6B7B; }",
              "table { border-collapse: collapse; width: 100%; }",
              "th { background: #14375E; color: #fff; text-align: center;",
              "     padding: 2px 3px; border: 1px solid #14375E; }",
              "td { padding: 1px 3px; border: 1px solid #D5DCE4; }",
              "tr:nth-child(even) td { background: #F4F7FB; }",
              "tr.total td { background: #DCE9F8; font-weight: bold;",
              "              border-top: 2px solid #14375E; }",
              ".num { text-align: right; } .cen { text-align: center; }",
              ".pe { font-size: 7pt; color: #5A6B7B; margin-top: 3px; }",
              "@media screen { body { background: #E8EDF3; padding: 14px; }",
              "  .folha { background: #fff; padding: 14px; margin: 0 auto",
              "           14px auto; max-width: 1500px;",
              "           box-shadow: 0 1px 4px rgba(0,0,0,.2); }",
              "  .aviso { max-width: 1500px; margin: 0 auto 12px auto;",
              "           background: #FFF4D6; border: 1px solid #E0C56A;",
              "           padding: 10px 14px; font-size: 10pt; } }",
              "@media print { .aviso { display: none; } }",
              "</style></head><body>",
              "<div class='aviso'>Para imprimir ou salvar em PDF: "
              "<b>Ctrl+P</b> &rarr; Destino <b>Salvar como PDF</b> &rarr; "
              "Layout <b>Paisagem</b>. Cada recorte ja sai numa pagina.</div>"]
    for bloco in blocos:
        colunas = bloco.get("colunas") or []
        linhas = list(bloco.get("linhas") or [])
        total = bloco.get("total")
        corpo = _tamanho_da_folha(len(colunas),
                                  len(linhas) + (1 if total else 0))
        partes.append(f"<div class='folha' style='font-size:{corpo}pt'>")
        partes.append("<div class='topo'>"
                      f"<h1>{_escapar(titulo)} &mdash; "
                      f"{_escapar(bloco.get('titulo'))}</h1>"
                      f"<div class='sub'>{_escapar(subtitulo)}</div></div>")
        partes.append("<table><thead><tr>")
        for rotulo, _, _ in colunas:
            partes.append(f"<th>{_escapar(rotulo)}</th>")
        partes.append("</tr></thead><tbody>")
        for linha in linhas:
            partes.append("<tr>")
            for _, chave, tipo in colunas:
                classe = ("num" if tipo in ("dinheiro", "decimal") else
                          "cen" if tipo in ("inteiro", "pct") else "")
                partes.append(f"<td class='{classe}'>"
                              f"{_escapar(_celula_impressa(linha.get(chave), tipo))}"
                              f"</td>")
            partes.append("</tr>")
        if total:
            partes.append("<tr class='total'>")
            for _, chave, tipo in colunas:
                classe = ("num" if tipo in ("dinheiro", "decimal") else
                          "cen" if tipo in ("inteiro", "pct") else "")
                partes.append(f"<td class='{classe}'>"
                              f"{_escapar(_celula_impressa(total.get(chave), tipo))}"
                              f"</td>")
            partes.append("</tr>")
        partes.append("</tbody></table>")
        # o pe da pagina so aparece se tiver o que dizer - folha limpa
        # e folha que se le de uma vez
        if _texto(rodape):
            partes.append(f"<div class='pe'>{_escapar(rodape)}</div>")
        partes.append("</div>")
    partes.append("</body></html>")
    return "".join(partes)


# --------------------------------------------------------------------------
# A FOLHA DE CLIENTES DA OPORTUNIDADE - A4 deitada, para levar para a rua
# --------------------------------------------------------------------------
# So as colunas que o vendedor le em pe, na porta do cliente. Tudo o que
# e numero de gestao (meta, realizado, dias sem compra, status) fica no
# Excel - aqui atrapalharia.
COLUNAS_FOLHA_CLIENTE = [
    ("UF", "uf", "texto"),
    ("CIDADE", "cidade", "texto"),
    ("COD.", "cod_cliente", "texto"),
    ("RAZAO SOCIAL", "cliente", "texto"),
    ("NOME FANTASIA", "fantasia", "texto"),
    ("ENDERECO", "endereco", "texto"),
    ("BAIRRO", "bairro", "texto"),
    ("NUMERO", "numero", "texto"),
    ("CONTATO", "contato_completo", "texto"),
    ("LIM. DISP. R$", "limite_disponivel", "dinheiro"),
    ("CURVA", "curva", "texto"),
    ("CADASTRO", "data_cadastro", "data"),
]

# A PAGINACAO E DO NAVEGADOR, NAO NOSSA.
#
# A primeira versao cortava a lista em pedacos de N linhas e punha cada
# pedaco numa pagina. Nao funciona: razao social e endereco quebram em
# duas linhas quando sao compridos, entao 38 linhas ora cabem, ora
# estouram - e a pagina virava duas, com a segunda quase vazia.
#
# Aqui a tabela e UMA so e quem corta e o proprio navegador, na altura
# real do papel. O <thead> se repete sozinho no topo de cada pagina
# (comportamento padrao de impressao) e nenhuma linha e cortada ao meio.
def html_da_folha_de_clientes(linhas: list, subtitulo: str = "",
                              titulo: str = "LISTA DE CLIENTES",
                              colunas=None) -> str:
    # `colunas` deixa a TELA mandar: quem imprime passa as colunas na
    # ordem em que elas estao na tabela, para a folha sair igual ao que
    # a pessoa acabou de organizar. Sem isso, vale a lista padrao.
    colunas = list(colunas or COLUNAS_FOLHA_CLIENTE)
    total_limite = sum(l.get("limite_disponivel") or 0.0 for l in linhas)
    partes = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        f"<title>{_escapar(titulo)}</title><style>",
        "@page { size: A4 landscape; margin: 8mm; }",
        "* { box-sizing: border-box; }",
        "body { font-family: Segoe UI, Arial, sans-serif; margin: 0;",
        "       color: #1B2B3A; font-size: 7.5pt; }",
        ".topo { border-bottom: 2px solid #14375E; margin-bottom: 5px;",
        "        padding-bottom: 3px; }",
        ".topo h1 { font-size: 13pt; margin: 0; color: #14375E; }",
        ".topo .sub { font-size: 8pt; color: #5A6B7B; }",
        "table { border-collapse: collapse; width: 100%; }",
        "thead { display: table-header-group; }",   # repete em toda pagina
        "tr { page-break-inside: avoid; }",         # linha nao parte ao meio
        "th { background: #14375E; color: #fff; text-align: center;",
        "     padding: 3px; border: 1px solid #14375E; font-size: 7.5pt; }",
        "td { padding: 2px 3px; border: 1px solid #D5DCE4;",
        "     vertical-align: top; }",
        "tr:nth-child(even) td { background: #F4F7FB; }",
        "tr.total td { background: #DCE9F8; font-weight: bold;",
        "              border-top: 2px solid #14375E; }",
        ".num { text-align: right; } .cen { text-align: center; }",
        "@media screen { body { background: #EEF1F6; padding: 14px; }",
        "  .papel { background: #fff; padding: 16px; max-width: 1500px;",
        "           margin: 0 auto; box-shadow: 0 1px 4px rgba(0,0,0,.2); }",
        "  .aviso { max-width: 1500px; margin: 0 auto 12px auto;",
        "           background: #FFF4D6; border: 1px solid #E0C56A;",
        "           padding: 10px 14px; font-size: 10pt; } }",
        "@media print { .aviso { display: none; }",
        "  .papel { padding: 0; box-shadow: none; } }",
        "</style></head><body>",
        "<div class='aviso'>Para salvar em PDF: <b>Ctrl+P</b> &rarr; "
        "Destino <b>Salvar como PDF</b> &rarr; Layout <b>Paisagem</b>. "
        "O cabecalho se repete em cada pagina.</div>",
        "<div class='papel'>",
        f"<div class='topo'><h1>{_escapar(titulo)}</h1>",
        f"<div class='sub'>{_escapar(subtitulo)}</div></div>",
        "<table><thead><tr>",
    ]
    for rotulo, _, _ in colunas:
        partes.append(f"<th>{_escapar(rotulo)}</th>")
    partes.append("</tr></thead><tbody>")
    for linha in linhas:
        partes.append("<tr>")
        for _, chave, tipo in colunas:
            classe = ("num" if tipo in ("dinheiro", "decimal") else
                      "cen" if tipo in ("inteiro", "pct") else "")
            partes.append(f"<td class='{classe}'>"
                          f"{_escapar(_celula_impressa(linha.get(chave), tipo))}"
                          f"</td>")
        partes.append("</tr>")
    partes.append("<tr class='total'>")
    for _, chave, tipo in colunas:
        if chave == "uf":
            valor = "TOTAL"
        elif chave == "cliente":
            valor = f"{len(linhas)} cliente(s)"
        elif chave == "limite_disponivel":
            valor = _celula_impressa(total_limite, "dinheiro")
        else:
            valor = ""
        classe = "num" if tipo in ("dinheiro", "decimal") else ""
        partes.append(f"<td class='{classe}'>{_escapar(valor)}</td>")
    partes.append("</tr></tbody></table></div></body></html>")
    return "".join(partes)


def nome_da_folha_de_clientes(competencia: str = "") -> str:
    comp = normalizar_competencia(competencia) or ""
    pedaco = comp.replace("-", "") if comp else f"{dt.date.today():%Y%m%d}"
    return f"LISTA_CLIENTES_BAP_{pedaco}.html"


def gravar_folha_de_clientes(linhas: list, caminho, subtitulo: str = "",
                             colunas=None) -> Path:
    """A folha pronta para o Ctrl+P do navegador (A4 deitada)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        html_da_folha_de_clientes(linhas, subtitulo, colunas=colunas),
        encoding="utf-8")
    return caminho


def gravar_html_para_imprimir(blocos: list, caminho, titulo: str,
                              subtitulo: str = "", rodape: str = "") -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        html_para_imprimir(blocos, titulo, subtitulo, rodape),
        encoding="utf-8")
    return caminho


def gravar_excel_escolhido(blocos: list, caminho, titulo: str = "") -> Path:
    """O mesmo recorte de colunas da impressao, so que em Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    wb = Workbook()
    wb.remove(wb.active)
    cabecalho = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)
    formato = {"dinheiro": "#,##0.00", "inteiro": "#,##0", "pct": "#,##0.0",
               "decimal": "#,##0.0"}
    for bloco in blocos:
        colunas = bloco.get("colunas") or []
        ws = wb.create_sheet(_texto(bloco.get("titulo"))[:31] or "FOLHA")
        ws.append([r for r, _, _ in colunas])
        for i, (rotulo, _, _) in enumerate(colunas, start=1):
            ws.cell(1, i).fill = cabecalho
            ws.cell(1, i).font = branco
            ws.cell(1, i).alignment = Alignment(horizontal="center",
                                                wrap_text=True)
            ws.column_dimensions[ws.cell(1, i).column_letter].width = \
                max(11, min(34, len(rotulo) + 4))
        for linha in list(bloco.get("linhas") or []):
            ws.append([linha.get(c) for _, c, _ in colunas])
        if bloco.get("total"):
            ws.append([bloco["total"].get(c) for _, c, _ in colunas])
            for j in range(1, len(colunas) + 1):
                ws.cell(ws.max_row, j).font = Font(bold=True, size=9)
        for j, (_, _, tipo) in enumerate(colunas, start=1):
            if tipo in formato:
                for n in range(2, ws.max_row + 1):
                    ws.cell(n, j).number_format = formato[tipo]
        ws.freeze_panes = "A2"
    if not wb.sheetnames:
        wb.create_sheet("VAZIO")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def nome_da_folha(competencia: str = "", o_que: str = "META") -> str:
    marca = marca_do_mes(competencia) or marca_do_mes()
    return f"FOLHA_{o_que}_BAP_{marca}"


# --------------------------------------------------------------------------
# O RECORTE DA FOLHA: imprimir so o pedaco de alguem
# --------------------------------------------------------------------------
# "Me da a folha do supervisor Lais" - so as linhas dela, com os totais
# fechando nela. Tem uma sutileza: GERENTE, SUPERVISOR, VENDEDOR, ZONA e
# CLIENTE sao linhas INTEIRAS de uma pessoa so, entao basta escolher
# quais ficam; CIDADE, BAIRRO e UF misturam equipes (a mesma cidade tem
# cliente de dois vendedores), e ali a linha e REFEITA com os clientes
# que sobraram - senao o numero do outro entrava na folha dela.
NIVEIS_DA_FOLHA = ["gerente", "supervisor", "vendedor", "zona", "uf",
                   "cidade"]
NIVEIS_INTEIROS = {"gerente", "supervisor", "vendedor", "zona", "cliente"}
# quem responde por quem: 0 manda em 1, que manda em 2
POSTO_DA_PESSOA = {"gerente": 0, "supervisor": 1, "vendedor": 2}


def alvos_para_a_folha(fonte: dict, nivel: str) -> list:
    """[(chave, rotulo)] do nivel escolhido, para encher a caixinha."""
    if not fonte or nivel not in RECORTES:
        return []
    vistos = {}
    for linha in fonte.get("recortes", {}).get(nivel) or []:
        chave = linha.get("chave")
        if chave and chave not in vistos:
            vistos[chave] = linha.get("rotulo") or linha.get("nome") or chave
    return sorted(vistos.items(), key=lambda x: x[1])


def filtrar_para_a_folha(fonte: dict, nivel: str = "", chave: str = "",
                         acompanhamento: bool = False) -> dict:
    """
    Os mesmos recortes, so que com o pedaco de quem foi escolhido.

    LINHA A LINHA: se TODOS os clientes daquela linha sao do alvo, ela vai
    inteira, com a meta que o painel deu (o piso do vendedor, a regra do
    nivel). Se a linha tem cliente de outra equipe - a cidade com dois
    vendedores, o gerente inteiro quando se filtra um supervisor - ela e
    REFEITA so com os clientes que sobraram. Senao o numero do outro
    entrava na folha dele.
    """
    if not fonte or not nivel or not chave or nivel not in RECORTES:
        return fonte
    todos = fonte.get("clientes") or []
    clientes = [c for c in todos if chave_da_linha(nivel, c) == chave]
    quantos_todos = {r: defaultdict(int) for r in RECORTES}
    quantos_dele = {r: defaultdict(int) for r in RECORTES}
    for c in todos:
        for r in RECORTES:
            quantos_todos[r][chave_da_linha(r, c)] += 1
    for c in clientes:
        for r in RECORTES:
            quantos_dele[r][chave_da_linha(r, c)] += 1

    dias = fonte.get("dias_restantes") or 0
    recortes, totais = {}, {}
    for r in RECORTES:
        if not clientes:
            recortes[r] = []
            totais[r] = (_total_acompanhamento([]) if acompanhamento
                         else total_do_recorte([]))
            continue
        inteiras = {k for k, n in quantos_dele[r].items()
                    if n == quantos_todos[r].get(k)}
        do_painel = {l.get("chave"): l
                     for l in (fonte.get("recortes", {}).get(r) or [])}
        refeitas = {}
        if set(quantos_dele[r]) - inteiras:
            grupo = (_agrupar_acompanhamento(clientes, r) if acompanhamento
                     else _agrupar(clientes, r))
            for linha in grupo:
                linha["meta_calculada"] = linha["meta"]
                linha["faixa"] = "so a parte deste recorte"
                linha["meta_cadastro"] = None
                if acompanhamento:
                    linha["meta_visita"] = None
                    linha["visitas_realizadas"] = None
                    _fechar_visita(linha)
                    _fechar_cadastro(linha)
                refeitas[linha["chave"]] = linha
        linhas = []
        for k in quantos_dele[r]:
            if k in inteiras and k in do_painel:
                linhas.append(dict(do_painel[k]))
            elif k in refeitas:
                linhas.append(refeitas[k])
        linhas.sort(key=lambda l: -(l.get("meta") or 0))
        if acompanhamento:
            for linha in linhas:
                _fechar_gaps(linha, dias)
        recortes[r] = linhas
        totais[r] = (_total_acompanhamento(linhas) if acompanhamento
                     else total_do_recorte(linhas))
        if acompanhamento:
            _fechar_gaps(totais[r], dias)
    # QUEM ESTA ACIMA DELE NA HIERARQUIA vira ele mesmo: filtrando um
    # supervisor, a pagina do GERENTE e aquele supervisor - entao ela tem
    # de mostrar a MESMA meta, e nao a soma dos clientes (que e menor,
    # porque o piso do vendedor nao entra nela). Sem isto, a folha saia
    # com gerente 519 mil e supervisor 934 mil para a mesma carteira.
    if nivel in POSTO_DA_PESSOA:
        base = totais.get(nivel) or {}
        campos = (["meta", "meta_calculada", "meta_visita",
                   "meta_positivacao", "meta_cadastro", "visitas_realizadas"]
                  + [f"meta_{c}" for c, _, _ in CATEGORIAS])
        if acompanhamento:
            # O REALIZADO TAMBEM DESCE. Filtrando um supervisor, a pagina
            # do GERENTE e aquele supervisor: se so a meta viesse dele e o
            # realizado fosse refeito pelos clientes, a folha sairia com
            # FAT TOTAL diferente em duas paginas da MESMA carteira -
            # porque agora o FAT TOTAL de pessoa e o que ela VENDEU, e
            # isso nao se remonta a partir de cliente.
            campos += (["realizado", "faturamento_carteira", "faturado",
                        "devolvido", "notas"]
                       + [f"real_{c}" for c, _, _ in CATEGORIAS])
        for r, posto in POSTO_DA_PESSOA.items():
            if posto >= POSTO_DA_PESSOA[nivel] or not recortes.get(r):
                continue
            for linha in recortes[r]:
                for campo in campos:
                    if campo in base:
                        linha[campo] = base[campo]
                linha["faixa"] = (f"o mesmo que o "
                                  f"{TITULO_DO_RECORTE[nivel]} desta folha")
                if acompanhamento:
                    _fechar_visita(linha)
                    _fechar_cadastro(linha)
                    _refechar_acompanhamento(linha)
                    _fechar_gaps(linha, dias)
            totais[r] = (_total_acompanhamento(recortes[r]) if acompanhamento
                         else total_do_recorte(recortes[r]))
            if acompanhamento:
                _fechar_gaps(totais[r], dias)

    saida = dict(fonte)
    saida["recortes"] = recortes
    saida["totais"] = totais
    saida["clientes"] = clientes
    saida["filtro_nivel"] = nivel
    saida["filtro_chave"] = chave
    return saida
