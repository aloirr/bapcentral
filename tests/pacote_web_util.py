"""Ajudantes comuns dos testes do pacote web (RD-0257, T-0036).

Funções puras sobre o farol como o robô monta; sem dado de cliente.
"""
import bap_automation as ba


def tam_sem_anexos(f: dict) -> int:
    """Bytes do farol como o robô manda o corpo (`_json_farol_web`, JSON
    compacto), sem os anexos (`_ANEXOS_FAROL_WEB`): a medida do teto por
    farol (§10.8.7)."""
    return len(ba._json_farol_web({k: v for k, v in f.items()
                                   if k not in ba._ANEXOS_FAROL_WEB}))


def col(t: dict, nome: str) -> list:
    """Os valores da coluna `nome` da tabela `t` (colunas em dict ou texto)."""
    i = [c["nome"] if isinstance(c, dict) else c
         for c in t["colunas"]].index(nome)
    return [ln[i] for ln in t["linhas"]]
