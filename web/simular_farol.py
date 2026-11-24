"""Simulação (T-0017): renderiza a página de um farol a partir de um pacote JSON e grava o HTML
com o CSS embutido; `simular_png.mjs` tira os PNG (computador 1366 px e celular 390 px).

Uso: python web/simular_farol.py [pacote.json] [saida.html] [rid]
Sem pacote, usa a fixture fictícia dos testes. Nada é gravado fora da pasta temporária e da saída.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "tests"))


def main(argv: list[str]) -> int:
    pacote = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 and argv[1] else None
    saida = Path(argv[2] if len(argv) > 2 else "farol.html")
    rid = argv[3] if len(argv) > 3 else "pl_inadimplencia"
    if pacote is None:
        from farol_fixture import pacote_farol
        pacote = pacote_farol()
    with tempfile.TemporaryDirectory() as d:
        os.environ.update({"SESSION_SECRET": "simulacao-0123456789abcdef0123", "BAP_WEB_DADOS": d,
                           "BAP_WEB_TOKEN": "t" * 40, "BAP_ADMIN_USUARIO": "admin.sim",
                           "BAP_ADMIN_SENHA_INICIAL": "senha-simulacao-1", "TZ": "America/Manaus"})
        time.tzset()
        from fastapi.testclient import TestClient
        from app.main import criar_app
        with TestClient(criar_app(), base_url="https://testserver") as c:
            r = c.post("/api/pacote", json=pacote, headers={"Authorization": "Bearer " + "t" * 40})
            if r.status_code != 200:
                print("pacote recusado:", r.text)
                return 1
            import re
            tk = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text).group(1)
            c.post("/login", data={"usuario": "admin.sim", "senha": "senha-simulacao-1", "csrf": tk})
            tk = re.search(r'name="csrf" value="([^"]+)"', c.get("/senha").text).group(1)
            c.post("/senha", data={"atual": "senha-simulacao-1", "nova": "senha-simulacao-2",
                                   "confirma": "senha-simulacao-2", "csrf": tk})
            html = c.get(f"/farol/{rid}" + (f"?uf={argv[4]}" if len(argv) > 4 else "")).text
    css = (AQUI / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/static/estilo.css">', f"<style>{css}</style>")
    saida.write_text(html, encoding="utf-8")
    print("gravado:", saida)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
