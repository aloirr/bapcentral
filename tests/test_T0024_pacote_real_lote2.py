"""T-0024: o pacote web inteiro (Painel + os 10 faróis de FAROIS_WEB, com os
recortes por estado do Painel e das Metas, como o coletar_relatorios_web faz)
montado com as BASES CONGELADAS do repositório (NOV/2026, hoje = 24/11/2026).

- Tamanho: abaixo do teto do robô (WEB_PACOTE_TETO_MB = 20), com margem de 20%
  (o robô mediu 13,68 MiB; aqui o alarme toca antes de chegar perto do teto).
- Corte (contrato 10.7.8): quando precisa, o passo 3 tira as tabelas dos
  faróis do lote 2 também, com um aviso só por farol; cartões e recortes ficam.
- Valor x regra: o número do farol na web é o do PC (sem recalcular) e, no
  recorte por estado, a soma dos estados é o total (RN-GER-006).

Nenhum valor de célula é impresso: as mensagens de falha só têm id, título e
números agregados (regra 6 do CLAUDE.md).
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
LOTE2 = ("pv_indicadores", "vc_base", "vc_planner", "pl_giro", "pl_frw")
TETO_MB = 20
MARGEM = 0.8                    # o pacote real fica abaixo de 80% do teto
MB = 1024 * 1024
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."


def _tam(p):
    return len(json.dumps(p, ensure_ascii=False).encode("utf-8"))


@pytest.fixture(scope="module")
def real():
    """(rels do PC, pacote) como o coletar_relatorios_web monta, com hoje fixo."""
    rels = {"vc_painel": rn.montar("vc_painel", RAIZ, hoje=HOJE,
                                   params=dict(PARAMS))}
    rels["vc_painel_uf"] = ba.montar_por_uf_web(
        "vc_painel", rels["vc_painel"], RAIZ, PARAMS, HOJE)
    for rid in ba.FAROIS_WEB:
        rels[rid] = rn.montar(rid, RAIZ, hoje=HOJE,
                              params=ba.params_farol_web(rid, 2026, 11),
                              tela=(rid == ba.RID_META_WEB))
        if rid == ba.RID_META_WEB:
            rels[rid + "_uf"] = ba.montar_por_uf_web(rid, rels[rid], RAIZ,
                                                     PARAMS, HOJE)
    return rels, ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)


# ------------------------------------------------------------------- tamanho
def test_T0024_pacote_real_com_os_10_farois_cabe_no_teto_com_margem(real):
    _rels, p = real
    assert ba.WEB_PACOTE_TETO_MB == TETO_MB
    assert set(LOTE2) <= set(p["relatorios"])
    tam = _tam(p)
    assert tam < TETO_MB * MB
    assert tam < MARGEM * TETO_MB * MB, f"{tam / MB:.2f} MiB"
    # cabe: o corte devolve o mesmo pacote, sem aviso de corte
    assert ba._cortar_pacote_web(p) is p
    assert not [a for r in p["relatorios"].values()
                for a in r.get("avisos") or [] if "caber no pacote" in a]


# --------------------------------------------------------------------- corte
def test_T0024_corte_passo_3_tira_as_tabelas_do_lote_2_e_cabe(real):
    """Teto logo abaixo do pacote depois do passo 2: só o passo 3 resolve.
    Todo farol de tabelas (os 3 da T-0017 e os 5 do lote 2) sai sem
    `tabelas`, com um aviso só de abas fora (todas as abas, na ordem do PC);
    os cartões e os recortes por estado ficam; a Inadimplência não muda; o
    pacote de entrada não muda."""
    _rels, p = real
    antes = json.dumps(p, ensure_ascii=False, sort_keys=True)
    # como na T-0017: cada teto fica 1 byte abaixo do pacote do passo anterior
    p1 = ba._cortar_pacote_web(p, teto_mb=(_tam(p) - 1) / MB)
    p2 = ba._cortar_pacote_web(p, teto_mb=(_tam(p1) - 1) / MB)
    assert _tam(p) > _tam(p1) > _tam(p2)
    for rid in LOTE2:            # passos 1 e 2 não mexem no lote 2
        assert p2["relatorios"][rid].get("tabelas") == \
            p["relatorios"][rid].get("tabelas"), rid
    teto_bytes = _tam(p2) - 1
    p3 = ba._cortar_pacote_web(p, teto_mb=teto_bytes / MB)
    assert _tam(p3) <= teto_bytes
    rels_w, rels_c = p["relatorios"], p3["relatorios"]
    for rid in ba.RIDS_TABELAS_WEB:
        if not rels_w[rid].get("tabelas"):
            continue
        assert "tabelas" not in rels_c[rid], rid
        assert rels_c[rid]["kpis"] == rels_w[rid]["kpis"], rid
        assert rels_c[rid].get("recortes") == rels_w[rid].get("recortes"), rid
        fora = [a for a in rels_c[rid].get("avisos") or []
                if a.startswith(AVISO_ABAS_FORA.split("{")[0])]
        assert len(fora) == 1, rid
        if rid in LOTE2:        # livres: a ordem é a das abas do PC
            assert fora[0] == AVISO_ABAS_FORA.format(lista=", ".join(
                t["titulo"] for t in rels_w[rid]["tabelas"])), rid
        assert rels_c[rid]["avisos"][0] == fora[0], rid      # abas fora 1º
    assert rels_c["pl_inadimplencia"] == rels_w["pl_inadimplencia"]
    assert json.dumps(p, ensure_ascii=False, sort_keys=True) == antes


def test_T0024_corte_com_teto_minimo_nao_levanta_e_tira_tudo_que_pode(real):
    _rels, p = real
    p_min = ba._cortar_pacote_web(p, teto_mb=0.01)
    for rid in ba.RIDS_TABELAS_WEB:
        assert "tabelas" not in p_min["relatorios"][rid], rid
    assert _tam(p_min) < _tam(p)


# --------------------------------------------------------------- valor x regra
def test_RN_GER_006_cartoes_do_lote_2_na_web_sao_os_do_pc(real):
    """O farol da web não recalcula: cartão (rótulo, valor, detalhe) igual ao
    do PC, e cada tabela leva todas as linhas do PC."""
    rels, p = real
    for rid in LOTE2:
        pc, web = rels[rid], p["relatorios"][rid]
        assert web.get("forma") == "farol", rid
        assert [(k["rotulo"], k["valor"], k.get("detalhe") or "")
                for k in web["kpis"]] == [
            (k["rotulo"], k["valor"], k.get("detalhe") or "")
            for k in pc.get("kpis") or []], rid
        por_titulo = {t.get("titulo"): t for t in pc.get("tabelas") or []}
        for t in web.get("tabelas") or []:
            n_web = len(t.get("linhas") or [])
            n_pc = len(por_titulo[t["titulo"]].get("linhas") or [])
            assert n_web == n_pc, (rid, t["titulo"], n_web, n_pc)


def _numero(v):
    """'1.774.629 un.' -> 1774629.0; 'R$ 6.521' -> 6521.0; % e dias -> None."""
    s = str(v or "").replace("R$", "").strip().split(" ")[0]
    if not re.fullmatch(r"-?[\d.]+(,\d+)?", s):
        return None
    return float(s.replace(".", "").replace(",", "."))


ADITIVOS = {"pl_giro": ("Estoque FRW + PMZ", "Em ruptura", "Curva A parada",
                        "Comprar"),
            "pl_frw": ("SKUs em estoque", "Pedir", "Devolver à PMZ",
                       "Sem venda em 6 meses")}


@pytest.mark.parametrize("rid", sorted(ADITIVOS))
def test_RN_GER_006_estoque_soma_dos_estados_e_o_total_do_farol(real, rid):
    """Estado = filial (estoque). Cartão de contagem/quantidade: a soma dos
    recortes por estado é o cartão do farol inteiro."""
    _rels, p = real
    web = p["relatorios"][rid]
    total = {k["rotulo"]: _numero(k["valor"]) for k in web["kpis"]}
    ufs = (web.get("recortes") or {})
    assert len(ufs) >= 2, rid
    for rotulo in ADITIVOS[rid]:
        soma = sum(_numero(k["valor"]) for u in ufs.values()
                   for k in u["kpis"] if k["rotulo"] == rotulo)
        assert soma == total[rotulo], (rid, rotulo, soma, total[rotulo])


@pytest.mark.xfail(reason="T-0024 (robô): o recorte por estado da Base de "
                   "clientes sai das linhas da aba Clientes e não do filtro "
                   "UF do PC; AM na web 1.501 x 1.416 no PC (recado ao "
                   "modulo-robo)")
def test_RN_GER_006_vc_base_recorte_do_estado_bate_com_o_filtro_uf_do_pc(real):
    """A Base de clientes tem o filtro UF no PC: o cartão do estado na web é
    o do PC com UF = o estado (mesma regra do Painel e das Metas)."""
    _rels, p = real
    web = p["relatorios"]["vc_base"]
    params = ba.params_farol_web("vc_base", 2026, 11)
    for uf in sorted(web.get("recortes") or {}):
        pc = rn.montar("vc_base", RAIZ, hoje=HOJE, params=dict(params, UF=uf))
        assert [(k["rotulo"], k["valor"]) for k in
                web["recortes"][uf]["kpis"]] == [
            (k["rotulo"], k["valor"]) for k in pc.get("kpis") or []], uf


@pytest.mark.xfail(reason="T-0024 (robô): no Planner o cartão do estado "
                   "usa os cartões da aba Por cliente; o mesmo rótulo "
                   "'Visitas no mês' soma 7.116 nos estados e é 4.168 no "
                   "farol (recado ao modulo-robo)")
def test_RN_GER_006_vc_planner_mesmo_rotulo_soma_dos_estados_e_o_total():
    """Cartão com o mesmo rótulo no farol e no recorte: a soma dos estados é o
    total do farol (quantidades)."""
    r = rn.montar("vc_planner", RAIZ, hoje=HOJE,
                  params=ba.params_farol_web("vc_planner", 2026, 11))
    web = ba.montar_pacote_web({"vc_planner": r}, 2026, 11,
                               raiz=RAIZ)["relatorios"]["vc_planner"]
    total = {k["rotulo"]: _numero(k["valor"]) for k in web["kpis"]}
    ufs = web.get("recortes") or {}
    assert ufs
    comuns = {k["rotulo"] for u in ufs.values() for k in u["kpis"]} & set(total)
    assert comuns
    for rotulo in comuns:
        if total[rotulo] is None:
            continue
        soma = sum(_numero(k["valor"]) or 0 for u in ufs.values()
                   for k in u["kpis"] if k["rotulo"] == rotulo)
        assert soma == total[rotulo], (rotulo, soma, total[rotulo])
