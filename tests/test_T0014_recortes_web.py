"""T-0014 (passo 4f do robô): visões prontas por estado.

Critério 1: o pacote leva as visões por UF com os números do farol de origem.
A visão de um estado é cópia da barra que o PC já desenha para esse estado em
cada cartão (RN-GER-006: estado = filial da nota); nada é recalculado. Sem
filtro por supervisor (R-20261123-191448-alexandre).

Dados 100% fictícios.
"""
import json

import pytest

ba = pytest.importorskip("bap_automation")
if not hasattr(ba, "recortes_por_uf"):
    pytest.skip("recortes_por_uf ainda não está no bap_automation (PR do modulo-robo)",
                allow_module_level=True)


def _cartao(chave, titulo, valor, barras, legenda_b="atingimento"):
    return {"chave": chave, "titulo": titulo, "valor": valor,
            "legenda": "projeção do mês",
            "aneis": [["MTD", 98.0, "R$ 1,0 mi"], ["MÊS", 95.0, "R$ 2,0 mi"]],
            "faixa": [["out", "+5%", "ok", "R$ 1,9 mi"]],
            "estados": ({"barras": barras, "legenda": legenda_b}
                        if barras is not None else None),
            "ajuda": "texto de ajuda"}


def _cartoes():
    return [
        _cartao("fat", "Faturamento líquido · proj.", "R$ 2,0 mi", [
            ["PA", 900000.0, "R$ 900 mil", "101%", "ok"],
            ["MA", 600000.0, "R$ 600 mil", "92%", "atencao"],
            ["AM", 500000.0, "R$ 500 mil", "80%", "alerta"],
            ["RR", None, "", "", ""]]),
        _cartao("pos", "Positivação", "350", [
            ["PA", 150.0, "150", "", ""],
            ["MA", 120.0, "120", "+4%", "ok"],
            ["AM", 80.0, "80", "", ""],
            ["RR", None, "", "", ""]]),
        _cartao("inad", "Inadimplência", "R$ 10 mil", None),
    ]


def test_RN_GER_006_recorte_por_uf_copia_a_barra_do_estado():
    r = ba.recortes_por_uf(_cartoes())
    assert set(r) == {"uf"}                              # só estado, sem supervisor
    assert list(r["uf"]) == ["PA", "MA", "AM"]          # RR sem dado não vira visão
    pa = r["uf"]["PA"]["cartoes"]
    assert [c["chave"] for c in pa] == ["fat", "pos", "inad"]   # mesma ordem do PC
    fat = pa[0]
    assert fat["valor"] == "R$ 900 mil"                  # o texto da barra do PC
    assert fat["legenda"] == "101% · atingimento"        # o % da barra + o que ele é
    assert fat["estados"] is None                         # sem barra única (repetiria o número)
    assert fat["aneis"] == [] and fat["faixa"] == []    # não há anel/faixa por estado
    assert fat["titulo"] == "Faturamento líquido · proj."
    assert r["uf"]["MA"]["cartoes"][1]["legenda"] == "+4% · atingimento"
    assert r["uf"]["PA"]["cartoes"][1]["legenda"] == ""  # barra sem % = sem legenda


def test_RN_GER_006_cartao_sem_barra_do_estado_fica_com_traco():
    r = ba.recortes_por_uf(_cartoes())
    inad = r["uf"]["AM"]["cartoes"][2]
    assert inad["valor"] == "—" and inad["estados"] is None and inad["legenda"] == ""


def test_T0014_numero_do_recorte_bate_com_a_barra_de_origem():
    cartoes = _cartoes()
    r = ba.recortes_por_uf(cartoes)
    for uf, vis in r["uf"].items():
        for c_orig, c_rec in zip(cartoes, vis["cartoes"]):
            barra = next((b for b in ((c_orig.get("estados") or {}).get("barras") or [])
                          if b[0] == uf and b[1] is not None), None)
            assert c_rec["valor"] == (barra[2] if barra else "—")


def test_T0014_selecionar_abas_leva_os_recortes_e_e_json():
    vis = "res"
    rel = {"titulo": "Visão comercial (fictício)", "paineis": [{
        "titulo": "Painel · resultado", "kpis_export": [],
        "painel": {"blocos": [{"tipo": "rrm", "visao": vis,
                               "dados": {vis: _cartoes(), "sub": {vis: "x"}}}]}}]}
    sel = ba.selecionar_abas_web(rel)
    rec = sel["abas"]["resultado"]["recortes"]
    assert set(rec) == {"uf"} and set(rec["uf"]) == {"PA", "MA", "AM"}
    json.dumps(ba._para_json(sel), allow_nan=False)


def test_T0014_sem_cartoes_sem_recorte():
    assert ba.recortes_por_uf(None) == {"uf": {}}
    assert ba.recortes_por_uf([{"titulo": "x", "valor": "1"}]) == {"uf": {}}
