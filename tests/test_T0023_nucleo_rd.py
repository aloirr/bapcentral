"""T-0023 v2: os achados RD-0132, RD-0136 e RD-0139 do núcleo, com uma regra
num lugar só.
- RN-POS-005: DT. FECHAMENTO = solicitação + 15 DU, e o prazo igual ao
  padrão fica em branco;
- RN-GER-012: o ticket vai com `max` 40, que vem do núcleo, e a garantia nova
  leva os padrões;
- RN-GER-002: os eventos de faturamento líquido (VND − DEV).

Trazido do modulo-farois (f0af112) e revisto pelo testes. Dados fictícios.
"""
from datetime import date

import relatorios_nucleo as rn



def test_RN_POS_005_prazo_padrao_txt_15_du_hoje_fora():
    # solicitacao seg 16/11/2026 + 15 DU = 07/12/2026
    assert rn.prazo_padrao_txt("16/11/2026") == "07/12/2026"
    assert rn.prazo_padrao_txt("") == ""
    assert rn.prazo_padrao_txt("xx") == ""


def test_RN_POS_005_prazo_igual_ao_padrao_fica_em_branco():
    c = {"dt_solicitacao": "16/11/2026", "dt_prazo": "07/12/2026"}
    assert rn.campos_garantia_a_gravar(c)["dt_prazo"] == ""
    c["dt_prazo"] = "10/12/2026"
    assert rn.campos_garantia_a_gravar(c)["dt_prazo"] == "10/12/2026"
    assert c["dt_prazo"] == "10/12/2026"            # pura: nao muda a entrada


def test_RN_GER_012_garantia_nova_leva_origem_e_padroes():
    assert rn.campos_garantia_a_gravar({}, novo=True)["origem"] == \
        "FAROL DE GARANTIAS"
    assert "origem" not in rn.campos_garantia_a_gravar({})
    assert rn.PADRAO_NOVA_GARANTIA == {"status": "ABERTO",
                                       "resultado": "PENDENTE"}


def test_RN_GER_012_ticket_max_40_vem_do_nucleo():
    import garantias as gm
    cols = {n: i for i, n in enumerate(
        [c[3] for c in rn.CAMPOS_EDICAO_GARANTIA])}
    ed = rn.edicao_garantia(cols, gm.STATUS, gm.RESULTADOS, "G-0001")
    por = {c["campo"]: c for c in ed["campos"]}
    assert por["ticket"]["max"] == 40


def test_RN_GER_002_eventos_liquidos_usam_o_liquido():
    class C:
        tabela = {"itens": [
            {"tipo": "VND", "valor": 100.0, "dt_nf": date(2026, 10, 6)},
            {"tipo": "DEV", "valor": 30.0, "dt_nf": date(2026, 10, 6)},
            {"tipo": "XXX", "valor": 9.0, "dt_nf": date(2026, 10, 6)}]}
    assert [v for _d, v in rn._eventos_faturamento(C)] == [100.0]
    assert [v for _d, v in rn._eventos_faturamento(C, liquido=True)] == [
        100.0, -30.0]
