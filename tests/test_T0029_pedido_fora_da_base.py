"""T-0029: RN-GER-013 — pedido de cliente fora da base de clientes da BAP (RAZÃO_SOCIAL "NÃO LOCALIZADO NA
BASE" no ftPedidos) é pedido interno: fora do Farol de Pedidos, dos Pedidos em aberto, dos indicadores e da
demanda da Solicitação BAP. Dados fictícios."""
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


def test_RN_GER_013_itens_fora_da_base_saem_da_tabela_dos_farois():
    rn = _modulo("relatorios_nucleo")
    base = {"clientes": {"006171": {"nome": "CLIENTE FICTICIO 6171", "fantasia": ""}},
            "itens": [
                {"tipo": "VEA", "cliente": "006171", "razao": "NÃO LOCALIZADO NA BASE", "pedido": "900241"},
                {"tipo": "VEA", "cliente": "006171", "razao": "CLIENTE FICTICIO 6171", "pedido": "900300"},
                {"tipo": "EXC", "cliente": "006300", "razao": "NÃO LOCALIZADO NA BASE", "pedido": "900233"},
            ]}
    fora = rn._sem_internos("tabela", base)  # noqa: SLF001
    # o pedido do código "6171" (virou 006171) não aparece com o nome do cliente real; o do cliente real fica
    assert [i["pedido"] for i in fora["itens"]] == ["900300"]


def test_RN_GER_013_solicitacao_nao_usa_pedido_fora_da_base_como_demanda():
    ba = _modulo("bap_automation")
    assert ba.pedido_fora_da_base("NÃO LOCALIZADO NA BASE")
    assert ba.pedido_fora_da_base("Nao Localizado na Base")
    assert not ba.pedido_fora_da_base("CLIENTE FICTICIO 01")
    assert not ba.pedido_fora_da_base(None)
