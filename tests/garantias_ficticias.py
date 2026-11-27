"""Ajudantes dos testes da garantia no PC (T-0023): o diário fictício e a
leitura do que o "Salvar contato" / gravar_contato acrescentou.

Usado por tests/test_T0023_pc_so_leitura.py e
tests/test_T0023_garantias_gravar_contato.py. Dados fictícios, sempre numa
pasta temporária (tmp_path): nada lê nem grava a pasta RELATORIOS/ real.
"""
import csv
import hashlib
from datetime import datetime
from pathlib import Path

import garantias as gm

CONTATO = ("contato_nome", "contato_fone")
TICKET = "G-9001"
QUANDO = datetime(2026, 11, 3, 9)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def diario_ficticio(raiz, status="EM TRATATIVA", dt_fechamento="") -> Path:
    """Garantia fictícia gravada linha a linha (gm._anexar, sem a dedução
    do gm.gravar): dá para ter FINALIZADA sem dt_fechamento e aberta com.
    Devolve o diário desta máquina (é nele que o salvar acrescenta)."""
    campos = {"dt_solicitacao": "03/11/2026", "cod_cliente": "900001",
              "cliente": "CLIENTE FICTICIO", "qtd": "1",
              "contato_nome": "CONTATO FICTICIO",
              "contato_fone": "(00) 00000-0001", "status": status}
    if dt_fechamento:
        campos["dt_fechamento"] = dt_fechamento
    gm._anexar(raiz, TICKET, campos, agora=QUANDO)
    return gm.pasta(raiz) / f"GARANTIAS_{gm.maquina()}.csv"


def linhas_novas(antes: bytes, depois: bytes) -> list:
    """As linhas acrescentadas no diário; o começo do arquivo tem de ser o
    de antes, byte a byte (mesmo sha): só acrescenta (regra 7)."""
    assert depois.startswith(antes)
    assert sha(depois[:len(antes)]) == sha(antes)
    return list(csv.DictReader(depois[len(antes):].decode("utf-8")
                               .splitlines(),
                               fieldnames=gm.CAMPOS_CSV, delimiter=";"))
