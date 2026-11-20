"""
BAP CHAMPIONS (28/10/2026, Alexandre) - o jogo de pontos do time comercial,
todo mes. Os PARAMETROS ficam em champions_config.json (na pasta do BAP) e
sao cadastrados/alterados no proprio relatorio (BAP Relatorios > BAP
CHAMPIONS > Parametros).

PONTOS
  Faturamento (base do jogo), a cada R$ 1.000 vendidos (liquido, VND - DEV,
  pela data da NF, por quem vendeu - a mesma conta da RV):
      Vendedor 30 · Supervisor 15 (a equipe dele) · Aux. Tecnico 10 (a
      equipe do supervisor que ele apoia)
  Vitoria no confronto da semana (jogos cadastrados): +200 (vendedor e
      supervisor). Vence quem fizer mais pontos na semana (seg a dom).
  Aceleradores
      Vendedor ...... SKU de PECAS vendido (codigo distinto no mes) +5;
                      cliente novo (cadastrado no mes) com pedido +20
      Supervisor .... SKU novo vendido (codigo que a equipe nunca tinha
                      vendido) +2; cliente positivado pela equipe +5
      Aux. Tecnico .. SLA de entrega (mes fechado) +200; SLA de
                      faturamento (mes fechado) +200 - da equipe do
                      supervisor que ele apoia
  Trava: atingiu >= 80% da desafio comercial de faturamento -> pontos LIBERADOS;
      abaixo -> BLOQUEADOS. Vendedor: a meta dele; supervisor: a da
      equipe; Aux. Tecnico: a do supervisor que ele apoia.
Este modulo so le e grava o cadastro; a conta esta em
relatorios_nucleo.bap_champions.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path

ARQUIVO = "champions_config.json"

VENDEDOR, SUPERVISOR, AUX = "VENDEDOR", "SUPERVISOR", "AUX. TÉCNICO"
# (30/10, Alexandre) o CNPJ da empresa na planilha da premiacao (Exportar
# campanha): sempre o mesmo
CNPJ_EMPRESA = "60077737000244"

PADRAO = {
    "nome": "BAP CHAMPIONS",
    # pontos a cada R$ 1.000 vendidos
    "pontos_por_mil": {VENDEDOR: 30.0, SUPERVISOR: 15.0, AUX: 10.0},
    "bonus_confronto": 200.0,
    "acel_vendedor": {"sku_pecas": 5.0, "cliente_novo": 20.0},
    "acel_supervisor": {"sku_novo": 2.0, "positivado": 5.0},
    "acel_aux": {"sla_entrega": 200.0, "sla_faturamento": 200.0},
    # trava: % da desafio comercial de faturamento que libera os pontos
    "trava_pct": 80.0,
    # o que e "bater o SLA" no mes fechado [SUPOSICAO: 90% no prazo]
    "sla_faturamento_dias": 2,          # dias uteis do pedido a nota
    "sla_faturamento_meta_pct": 90.0,   # % dos pedidos faturados no prazo
    "sla_entrega_meta_pct": 90.0,       # % das entregas no prazo
    # a categoria do "SKU de pecas"
    "categoria_pecas": "PEÇAS",
    # os Aux. Tecnicos (assistentes do backoffice) e o supervisor que cada
    # um apoia (codigo do Protheus); sem supervisor = sem pontos
    "aux": [{"nome": "Juliana Almeida", "supervisor": ""},
            {"nome": "Mayara Santos", "supervisor": ""},
            {"nome": "Estefanie Pacheco", "supervisor": ""}],
    # os jogos da semana: semana = a segunda-feira (AAAA-MM-DD)
    "jogos": [],
    # quem nao joga (codigo do vendedor/supervisor) [SUPOSICAO: a conta de
    # teste 000040]
    "fora_do_jogo": ["000040"],
    # (28/10, Alexandre) CAMPANHA RELAMPAGO: nos dias da campanha, a cada
    # R$ 4.000 em PEDIDOS do dia o vendedor ganha 250 e o supervisor 150
    # (pela equipe); DESAFIO DO DIA: se a BAP vender R$ 100 mil no dia,
    # vendedores ganham 400 e supervisores 300. Elegibilidade: o vendedor
    # nao pode zerar a venda no dia. Pontos troca pontos (fora do placar
    # do BAP Champions). Feita em 30 e 31/07/2026.
    "relampago": [{"nome": "Campanha Relâmpago",
                   "dias": ["2026-07-30", "2026-07-31"],
                   "bloco": 4000.0, "pts_vendedor": 250.0,
                   "pts_supervisor": 150.0, "meta_bap_dia": 100000.0,
                   "bonus_vendedor": 400.0, "bonus_supervisor": 300.0}],
    # (28/10, Alexandre) EQUIPE E METAS DO MES cadastradas a mao: quando o
    # mes tem lista aqui, o jogo usa ESTA equipe e ESTA meta (no lugar do
    # Planner/Gerador de Meta). Supervisor: a soma das metas da equipe
    # [SUPOSICAO]. Julho/2026 (passado pelo Alexandre em 28/10); o codigo
    # da Lua de Jesus nao veio ("#####") [SUPOSICAO: em branco].
    "equipes_mes": {"2026-07": [
        {"regiao": "AM/RR", "supervisor": "Luan Tavares De Souza",
         "cod": "000035", "vendedor": "MARCOS AURELIO DA SILVA",
         "meta": 120000.0},
        {"regiao": "MT", "supervisor": "Alexandre Guerreiro",
         "cod": "000008", "vendedor": "PAULO UBIRATAN CURVO DE LIMA",
         "meta": 120000.0},
        {"regiao": "MA", "supervisor": "Veronica Dos Santos Oliveira",
         "cod": "000034", "vendedor": "ANDERSON LIMA SILVA",
         "meta": 80000.0},
        {"regiao": "MA", "supervisor": "Veronica Dos Santos Oliveira",
         "cod": "", "vendedor": "LUA DE JESUS COSTA BALDEZ",
         "meta": 80000.0},
        {"regiao": "MA", "supervisor": "Veronica Dos Santos Oliveira",
         "cod": "000031", "vendedor": "JOCIMAR SOARES FRANCA JUNIOR",
         "meta": 80000.0},
        {"regiao": "PA", "supervisor": "Lais Priscila Leal Maciel",
         "cod": "000041", "vendedor": "EDSON NEVES DO NASCIMENTO",
         "meta": 60000.0},
        {"regiao": "MT/RR/AP", "supervisor": "Alexandre Guerreiro",
         "cod": "000014", "vendedor": "ENRICSON OLIVEIRA DA SILVA",
         "meta": 100000.0},
        {"regiao": "PA", "supervisor": "Lais Priscila Leal Maciel",
         "cod": "000012", "vendedor": "LUIS ALBERTO DA SILVA CASEIRO",
         "meta": 60000.0},
        {"regiao": "AM/RR", "supervisor": "Luan Tavares De Souza",
         "cod": "000015", "vendedor": "THIAGO LIMA GOMES",
         "meta": 60000.0},
        {"regiao": "PA", "supervisor": "Lais Priscila Leal Maciel",
         "cod": "000029", "vendedor": "CRIZANTO CRUZ DE ALMEIDA",
         "meta": 60000.0},
        {"regiao": "PA", "supervisor": "Lais Priscila Leal Maciel",
         "cod": "000006", "vendedor": "LAIS PRISCILA LEAL MACIEL",
         "meta": 0.0}]},
    "alterado_em": "",
    "alterado_por": "",
}


# os numeros de cada campanha relampago (rotulo da tela)
CAMPOS_RELAMPAGO = {
    "bloco": "A cada R$ (pedidos do dia)",
    "pts_vendedor": "Vendedor ganha (pts por bloco)",
    "pts_supervisor": "Supervisor ganha (pts por bloco da equipe)",
    "meta_bap_dia": "Desafio: a BAP vender no dia (R$)",
    "bonus_vendedor": "Desafio: vendedores ganham (pts)",
    "bonus_supervisor": "Desafio: supervisores ganham (pts)"}


def caminho(raiz) -> Path:
    return Path(raiz) / ARQUIVO


def _mesclar(base: dict, novo: dict) -> dict:
    saida = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        # equipes_mes: o que foi gravado vale inteiro (mes apagado nao volta)
        if isinstance(v, dict) and isinstance(saida.get(k), dict) and \
                k != "equipes_mes":
            saida[k] = {**saida[k], **v}
        else:
            saida[k] = v
    return saida


def ler(raiz) -> dict:
    """O cadastro (o padrao por baixo: chave nova sempre tem valor)."""
    try:
        dados = json.loads(caminho(raiz).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    return _mesclar(PADRAO, dados if isinstance(dados, dict) else {})


def numero(v, padrao=0.0) -> float:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def moeda(v, padrao=None):
    """R$ 120.000,00 / 120000 / 120000.5 -> numero (None se nao der)."""
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or "").upper().replace("R$", "").replace(" ", "").strip()
    if not t:
        return padrao
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return padrao


def validar(cfg: dict) -> list:
    """Os problemas do cadastro (lista vazia = ok)."""
    erros = []
    for k, d in (("pontos_por_mil", cfg.get("pontos_por_mil")),
                 ("acel_vendedor", cfg.get("acel_vendedor")),
                 ("acel_supervisor", cfg.get("acel_supervisor")),
                 ("acel_aux", cfg.get("acel_aux"))):
        for a, v in (d or {}).items():
            if numero(v, -1) < 0:
                erros.append(f"{k} › {a}: número inválido ({v})")
    for k in ("bonus_confronto", "trava_pct", "sla_faturamento_dias",
              "sla_faturamento_meta_pct", "sla_entrega_meta_pct"):
        if numero(cfg.get(k), -1) < 0:
            erros.append(f"{k}: número inválido ({cfg.get(k)})")
    if not 0 <= numero(cfg.get("trava_pct"), -1) <= 200:
        erros.append("trava_pct: entre 0 e 200%")
    vistos = set()
    for j in cfg.get("jogos") or []:
        try:
            seg = date.fromisoformat(str(j.get("semana"))[:10])
        except ValueError:
            erros.append(f"jogo com semana inválida: {j.get('semana')}")
            continue
        if seg.weekday() != 0:
            erros.append(f"jogo de {seg:%d/%m}: a semana começa na segunda")
        if not j.get("a") or not j.get("b") or j.get("a") == j.get("b"):
            erros.append(f"jogo de {seg:%d/%m}: escolha dois jogadores "
                         f"diferentes")
        for x in (j.get("a"), j.get("b")):
            if (seg, x) in vistos:
                erros.append(f"{x} tem dois jogos na semana de {seg:%d/%m}")
            vistos.add((seg, x))
    for a in cfg.get("aux") or []:
        if not str(a.get("nome") or "").strip():
            erros.append("Aux. Técnico sem nome")
    for comp, ls in (cfg.get("equipes_mes") or {}).items():
        try:
            date.fromisoformat(f"{comp}-01")
        except ValueError:
            erros.append(f"Equipe do mês: mês inválido {comp} (AAAA-MM)")
        for x in ls or []:
            if not str(x.get("vendedor") or "").strip():
                erros.append(f"Equipe de {comp}: vendedor sem nome")
            if moeda(x.get("meta"), -1) < 0:
                erros.append(f"Equipe de {comp} › {x.get('vendedor')}: "
                             f"meta inválida ({x.get('meta')})")
    for c in cfg.get("relampago") or []:
        nome = str(c.get("nome") or "").strip() or "(sem nome)"
        if not c.get("dias"):
            erros.append(f"Campanha relâmpago {nome}: sem dias")
        for d in c.get("dias") or []:
            try:
                date.fromisoformat(str(d)[:10])
            except ValueError:
                erros.append(f"Campanha relâmpago {nome}: dia inválido {d}")
        for k in CAMPOS_RELAMPAGO:
            if numero(c.get(k), -1) < 0:
                erros.append(f"Campanha relâmpago {nome} › {k}: número "
                             f"inválido ({c.get(k)})")
        if numero(c.get("bloco"), 0) <= 0:
            erros.append(f"Campanha relâmpago {nome}: o valor do bloco "
                         f"(R$) tem de ser maior que zero")
    return erros


def gravar(raiz, cfg: dict, por: str = "") -> Path:
    """Grava o cadastro inteiro (arquivo temporario + troca: nunca fica
    pela metade)."""
    erros = validar(cfg)
    if erros:
        raise ValueError("\n".join(erros))
    cfg = _mesclar(PADRAO, cfg)
    cfg["alterado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cfg["alterado_por"] = por
    cfg["jogos"] = sorted(cfg.get("jogos") or [],
                          key=lambda j: (str(j.get("semana")),
                                         str(j.get("tipo")), str(j.get("a"))))
    arq = caminho(raiz)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(arq)
    return arq
