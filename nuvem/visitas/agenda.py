"""T-0045 (contrato visitas-nuvem v1.1, §2 e §3.1): quando o cron roda e quais dias baixa.

Só funções puras e constantes: sem rede, sem relógio, sem ambiente, sem disco. Importar este
arquivo não faz nada. O relógio e o `trabalho` (resposta do `GET /api/visitas/trabalho`) vêm de fora.
Fuso: America/Manaus (UTC-4 o ano todo); `agora` entra já em Manaus.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import visitas_nucleo as vn

MANAUS = vn.FUSO_MANAUS

AGENDA_HORA = "06:00"                                   # D2: a rodada automática baixa ONTEM
RETENTATIVAS_AGENDA = ("06h30", "07h00", "07h30")       # 2ª, 3ª e 4ª tentativa da agenda
NOVA_TENTATIVA = ("MAXIMA_FORA", "TELA_MUDOU", "NAVEGADOR_FALHOU", "SITE_RECUSOU", "RODADA_INTERROMPIDA",
                  "PARCIAL_TEMPO", "ERRO_INTERNO")
TENTATIVAS_DIA = {"agenda": 4, "pedido": 3, "retentativa": 1, "diagnostico": 2}      # RN-VIS-008
LOGINS_DIA_MAX = 8                                                                  # RN-VIS-008
JANELA = ("06:00", "21:59")                             # fora dela o cron sai sem falar com a Máxima
PEDIDO_MAX_DIAS = 7
PEDIDO_MAX_RODADAS = 3
RETENTATIVA_DIAS = 7                                    # RN-VIS-006: os últimos 7 dias


def hora(texto: str) -> time:
    """"06:00" ou "06h30" -> time."""
    h, m = texto.replace("h", ":").split(":")
    return time(int(h), int(m))


def _por_motivo(trabalho: dict) -> dict:
    return (trabalho.get("tentativas_hoje") or {}).get("por_motivo") or {}


def _abaixo_do_teto(trabalho: dict, motivo: str) -> bool:
    por = _por_motivo(trabalho)
    return int((por.get(motivo) or {}).get("n", 0)) < TENTATIVAS_DIA[motivo]


_dt = vn._quando_manaus          # a regra de hora do núcleo (sem cópia)


def _dia(ymd) -> date | None:
    try:
        return datetime.strptime(str(ymd), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _retentativa_pendente(indice: dict, hoje: date) -> list[date]:
    """Dias dos últimos 7 (sem hoje) baixados pela nuvem com vendedor faltando e ainda não refeitos."""
    achados = []
    for k in range(RETENTATIVA_DIAS, 0, -1):
        d = hoje - timedelta(days=k)
        item = (indice or {}).get(f"{d:%Y%m%d}")
        if (isinstance(item, dict) and item.get("origem") == "nuvem"
                and int(item.get("erros_vendedor") or 0) > 0 and not item.get("refeito")):
            achados.append(d)
    return achados


def deve_rodar(agora: datetime, trabalho: dict) -> str | None:
    """Contrato §3.1, na ordem: o motivo da rodada ("diagnostico", "pedido", "agenda", "retentativa") ou None."""
    agora = agora.astimezone(MANAUS) if agora.tzinfo else agora.replace(tzinfo=MANAUS)
    hoje = agora.date()
    if trabalho.get("pausado"):                                                              # 1
        return None
    if not (hora(JANELA[0]) <= agora.time().replace(tzinfo=None) <= hora(JANELA[1]).replace(second=59)):   # 2
        return None
    if int((trabalho.get("tentativas_hoje") or {}).get("total", 0)) >= LOGINS_DIA_MAX:       # 3
        return None
    diag = trabalho.get("diagnostico") or {}
    if diag.get("estado") == "pendente" and _abaixo_do_teto(trabalho, "diagnostico"):        # 4
        return "diagnostico"
    if trabalho.get("agenda") == "desligada" or diag.get("estado") != "ok":                  # 5
        return None
    ped = trabalho.get("pedido")                                                             # 6
    if (ped and int(ped.get("rodadas", 0)) < PEDIDO_MAX_RODADAS and _abaixo_do_teto(trabalho, "pedido")
            and dias_da_rodada("pedido", trabalho, hoje)):      # sem dia a baixar, o pedido não trava a fila
        return "pedido"
    indice = trabalho.get("indice") or {}
    ontem = hoje - timedelta(days=1)
    if not vn.dia_fechado_no_indice(indice, ontem) and _abaixo_do_teto(trabalho, "agenda"):  # 7
        ag = _por_motivo(trabalho).get("agenda") or {}
        n = int(ag.get("n", 0))
        agora_h = agora.time().replace(tzinfo=None)
        if n == 0 and agora_h >= hora(AGENDA_HORA):
            return "agenda"
        if 1 <= n <= len(RETENTATIVAS_AGENDA) and ag.get("codigo") in NOVA_TENTATIVA \
                and agora_h >= hora(RETENTATIVAS_AGENDA[n - 1]):
            return "agenda"
    if _retentativa_pendente(indice, hoje) and _abaixo_do_teto(trabalho, "retentativa"):     # 8
        return "retentativa"
    return None                                                                              # 9


def dias_da_rodada(motivo: str, trabalho: dict, hoje: date) -> list[date]:
    """Os dias que a rodada pede (contrato §3.1/§3.2), em ordem. Sem I/O. Lista vazia = nada a baixar.

    diagnostico: ontem só. agenda: ontem, se ainda aberto. pedido: de/ate/refazer, até PEDIDO_MAX_DIAS
    (com `refazer`, o dia já refeito depois do pedido, em rodada anterior do mesmo pedido, não repete).
    retentativa: os dias com erros_vendedor > 0 e refeito false nos últimos 7.
    """
    indice = trabalho.get("indice") or {}
    ontem = hoje - timedelta(days=1)
    if motivo == "diagnostico":
        return [ontem]
    if motivo == "agenda":
        return vn.dias_a_baixar(indice, ontem, ontem, hoje, False)
    if motivo == "retentativa":
        return _retentativa_pendente(indice, hoje)
    if motivo == "pedido":
        ped = trabalho.get("pedido") or {}
        de, ate = _dia(ped.get("de")), _dia(ped.get("ate"))
        if de is None or ate is None or ate < de:
            return []
        refazer = bool(ped.get("refazer"))
        dias = vn.dias_a_baixar(indice, de, ate, hoje, refazer)
        if refazer:
            em = _dt(ped.get("pedido_em"))
            if em is not None:
                dias = [d for d in dias if not _refeito_depois(indice.get(f"{d:%Y%m%d}"), em)]
        return dias[:PEDIDO_MAX_DIAS]
    return []


def _refeito_depois(item, em: datetime) -> bool:
    b = _dt((item or {}).get("baixado_em")) if isinstance(item, dict) else None
    return bool(b and b >= em and (item or {}).get("origem") == "nuvem")
