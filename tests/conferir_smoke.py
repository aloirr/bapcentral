"""T-0004 - confere a saida do smoke_processos.py contra as falhas conhecidas.

Uso no CI: python tests/conferir_smoke.py smoke.log
Sai 0 quando o smoke passou ou quando TODA falha e conhecida; sai 1 quando
aparece falha nova ou o smoke quebrou antes do resumo.

Falhas conhecidas (lista do agente testes):
- [3] ftPedidos: "celulas conferidas contra o Excel: N diferenca(s)" - o
  ftPedidos congelado difere do Excel salvo (pedido antigo, sem dono ainda).
"""
import re
import sys

CONHECIDAS = (
    re.compile(r"^\d+ celulas conferidas contra o Excel: \d+ diferenca\(s\)$"),
)
SUCESSO = "OK - Farol, pos-venda, TABELA_BAP"


def conferir(texto: str) -> tuple[bool, list[str]]:
    """(ok, falhas novas). Sem resumo e sem a linha de sucesso: quebrou."""
    if SUCESSO in texto:
        return True, []
    m = re.search(r"^(\d+) FALHA\(S\):\n((?:  - .*\n?)*)", texto, re.M)
    if not m:
        return False, ["o smoke parou antes do resumo (erro ou excecao)"]
    falhas = [l[4:].rstrip() for l in m.group(2).splitlines() if l.strip()]
    if len(falhas) != int(m.group(1)):
        return False, ["o resumo do smoke nao bate com a contagem"]
    novas = [f for f in falhas if not any(p.match(f) for p in CONHECIDAS)]
    return not novas, novas


def main(argv) -> int:
    texto = open(argv[1], encoding="utf-8", errors="replace").read()
    ok, novas = conferir(texto)
    if ok:
        print("smoke_processos: so falhas conhecidas (ou nenhuma).")
        return 0
    print("smoke_processos: falha NOVA fora da lista do agente testes:")
    for f in novas:
        print("  - " + f)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
