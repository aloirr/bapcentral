"""T-0017: Farol de Inadimplência sem CNPJs internos (RN-GER-004) nos títulos.
O filtro puro bd.titulos_sem_internos com os três internos está em
test_T0017_fotos_sem_internos.py; aqui ficam o cliente 000040 (continua no
farol) e o filtro no bloco "inadimplencia" do contexto. Dados fictícios."""
import bap_dados as bd
import relatorios_nucleo as rn


def _t(cod, nome):
    return {"cod": cod, "nome": nome, "saldo": 10.0}


def test_RN_GER_005_cliente_000040_continua_no_farol():
    ts = [_t("000040", "CLIENTE FICTICIO B"), _t("000002", "BAP AUTOPARTS")]
    assert [t["cod"] for t in bd.titulos_sem_internos(ts)] == ["000040"]


def test_RN_GER_004_bloco_inadimplencia_filtrado_no_contexto():
    b = rn._sem_internos("inadimplencia", {"fotos": [], "titulos": [
        _t("000002", "BAP AUTOPARTS"), _t("000001", "CLIENTE FICTICIO A"),
        _t("000003", "FRW COMERCIO"), _t("000004", "PMZ DISTRIBUIDORA SA"),
        _t("000040", "CLIENTE FICTICIO B")]})
    assert [t["cod"] for t in b["titulos"]] == ["000001", "000040"]
    assert b["fotos"] == []
