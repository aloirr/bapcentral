"""T-0017 - RN-GER-011: nome digitado pelo vendedor (Prospeccao e Indicacao)
vai ao site sem documento E sem telefone/e-mail (achado 🟡 do revisor,
25/11). Dados ficticios."""
import bap_automation as ba


def test_RN_GER_011_nome_digitado_sem_telefone_nem_email():
    fn = ba._funcoes_limpeza_web()["nome_sem_contato"]
    saida = fn("OFICINA TESTE (92) 99123-4567 contato@exemplo.com")
    assert "99123" not in saida and "4567" not in saida
    assert "@" not in saida and "OFICINA TESTE" in saida


def test_RN_GER_011_prospeccao_e_indicacao_usam_nome_sem_contato():
    cols = ba._COLUNAS_LIMPAS_WEB
    assert cols[("vc_visitas", "Prospecção")]["ESTABELECIMENTO"] == \
        "nome_sem_contato"
    ind = cols[("vc_visitas", "Indicação")]
    assert ind["INDICADO"] == ind["CLIENTE QUE INDICOU"] == "nome_sem_contato"
