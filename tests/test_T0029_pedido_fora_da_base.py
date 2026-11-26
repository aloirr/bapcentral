"""T-0029: RN-GER-013 — pedido de cliente fora da base de clientes da BAP (RAZÃO_SOCIAL "NÃO LOCALIZADO NA
BASE" no ftPedidos) é pedido interno: fica no Farol de Pedidos como CLIENTE FORA DA BASE (sem casar o código com
zeros, o "6171" não vira outro cliente) e não entra na demanda da Solicitação BAP. Dados fictícios."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _modulo(nome):
    try:
        return importlib.import_module(nome)
    except Exception:  # noqa: BLE001
        import pytest
        pytest.skip(f"{nome} não importa neste ambiente")


def test_RN_GER_013_reconhece_cliente_fora_da_base():
    rn = _modulo("relatorios_nucleo")
    assert rn.fora_da_base("NÃO LOCALIZADO NA BASE")
    assert rn.fora_da_base("  nao localizado na base ")
    assert not rn.fora_da_base("CLIENTE FICTICIO 01")
    assert not rn.fora_da_base("")
    assert not rn.fora_da_base(None)


def test_RN_GER_013_itens_fora_da_base_ficam_na_tabela_dos_farois():
    rn = _modulo("relatorios_nucleo")
    base = {"clientes": {"006171": {"nome": "CLIENTE FICTICIO 6171", "fantasia": ""}},
            "itens": [
                {"tipo": "VEA", "cliente": "006171", "razao": "NÃO LOCALIZADO NA BASE", "pedido": "900241"},
                {"tipo": "VEA", "cliente": "006171", "razao": "CLIENTE FICTICIO 6171", "pedido": "900300"},
            ]}
    fica = rn._sem_internos("tabela", base)  # noqa: SLF001
    assert [i["pedido"] for i in fica["itens"]] == ["900241", "900300"]
    assert rn.NOME_FORA_DA_BASE == "CLIENTE FORA DA BASE"


def test_RN_GER_013_solicitacao_nao_usa_pedido_fora_da_base_como_demanda():
    ba = _modulo("bap_automation")
    assert ba.pedido_fora_da_base("NÃO LOCALIZADO NA BASE")
    assert ba.pedido_fora_da_base("Nao Localizado na Base")
    assert not ba.pedido_fora_da_base("CLIENTE FICTICIO 01")
    assert not ba.pedido_fora_da_base(None)
