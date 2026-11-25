"""Blocos `tabela` fictícios do Painel/faróis, com todos os tipos de coluna e valores vazios, negativos e texto."""
from farol_fixture import farol_entregas


def blocos_tabela():
    tipos = ["texto", "int", "moeda", "moeda2", "pct", "pct1", "num", "num1", "num2", "dia", "hora", "data", "valor"]
    cols = [{"nome": f"COL {t.upper()}", "tipo": t} for t in tipos] + [{"nome": "OCULTA", "tipo": "int", "oculta": True}]
    linhas = [
        ["A", 1250, 1250000.4, 1250.5, 85.34, 85.36, 1250.0, 3.46, 3.456, "2026-11-19", "08:15", "2026-11-19", 7],
        ["B", 0, -1500.7, -2.5, 0.0, 100.0, 0.5, 0.0, 0.0, None, "—", None, 12.5],
        ["C", None, None, "", "", None, "", None, "", "", None, "", None],
        ["D", "texto", "x", "y", "z", "w", "v", "u", "t", "19/11", "0:12:30", "s", "r"],
        ["E", 12.5, 999.999, 0.004, 99.95, 0.05, 1234567.89, 1234.5, 0.125, "2026-01-05", "17:00", "2026-12-31", 3],
    ]
    linhas = [ln + [9] for ln in linhas]
    total = ["TOTAL", 4, 1.5e6, 99.5, 50.5, 60.25, 12.0, 1.0, 2.0, None, "09:00", None, 5, 1]
    simples = {"tipo": "tabela", "titulo": "Bloco simples", "colunas": cols, "linhas": linhas}
    com_total = {"tipo": "tabela", "titulo": "Bloco com total", "colunas": cols, "linhas": linhas, "total": total}
    fr = farol_entregas()["painel"]["blocos"][0]            # "Frete por estado" do farol de Entregas
    return [simples, com_total, fr]
