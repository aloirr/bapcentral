"""Simulação (T-0017): renderiza a página de um farol a partir de um pacote JSON e grava o HTML
com o CSS embutido; `simular_png.mjs` tira os PNG (computador 1366 px e celular 390 px).

Uso: python web/simular_farol.py [pacote.json] [saida.html] [rid] [uf]
Sem pacote, usa a fixture fictícia dos testes. Nada é gravado fora da pasta temporária e da saída.

Como módulo: `paginas(pacote, [(perfil, "/farol/pv_pedidos?aba=pedidos"), ...])` devolve
`[(status, html)]`, cada página vista pelo perfil indicado (usuário fictício criado só na pasta temporária).
"""
from __future__ import annotations

import base64
import os
import re
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "tests"))

TOKEN = "t" * 40


def _csrf(c, url):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(url).text).group(1)


def paginas(pacote: dict, pedidos: list[tuple[str, str]]) -> list[tuple[int, str]]:
    """Cada pedido é (perfil, caminho). O HTML sai com o CSS embutido (para tirar o PNG sem servidor)."""
    css = (AQUI / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    js = (AQUI / "app" / "static" / "bc3.js").read_text(encoding="utf-8")           # RD-0006: lidos uma vez
    logo = base64.b64encode((AQUI / "app" / "static" / "logo_bap.png").read_bytes()).decode()
    saida: list[tuple[int, str]] = []
    with tempfile.TemporaryDirectory() as d:
        os.environ.update({"SESSION_SECRET": "simulacao-0123456789abcdef0123", "BAP_WEB_DADOS": d,
                           "BAP_WEB_TOKEN": TOKEN, "BAP_ADMIN_USUARIO": "admin.sim",
                           "BAP_ADMIN_SENHA_INICIAL": "senha-simulacao-1", "TZ": "America/Manaus"})
        time.tzset()
        from fastapi.testclient import TestClient

        from app.main import criar_app
        app = criar_app()
        with TestClient(app, base_url="https://testserver") as adm:
            r = adm.post("/api/pacote", json=pacote, headers={"Authorization": "Bearer " + TOKEN})
            if r.status_code != 200:
                raise SystemExit(f"pacote recusado: {r.text}")
            adm.post("/login", data={"usuario": "admin.sim", "senha": "senha-simulacao-1", "csrf": _csrf(adm, "/login")})
            adm.post("/senha", data={"atual": "senha-simulacao-1", "nova": "senha-simulacao-2",
                                     "confirma": "senha-simulacao-2", "csrf": _csrf(adm, "/senha")})
            sessoes = {"admin": adm}
            for perfil, url in pedidos:
                if perfil not in sessoes:
                    adm.post("/usuarios", data={"acao": "criar", "login": f"sim.{perfil}", "perfil": perfil,
                                                "senha": "senha-simulacao-3", "csrf": _csrf(adm, "/usuarios")})
                    c = TestClient(app, base_url="https://testserver")
                    c.post("/login", data={"usuario": f"sim.{perfil}", "senha": "senha-simulacao-3",
                                           "csrf": _csrf(c, "/login")})
                    c.post("/senha", data={"atual": "senha-simulacao-3", "nova": "senha-simulacao-4",
                                           "confirma": "senha-simulacao-4", "csrf": _csrf(c, "/senha")})
                    sessoes[perfil] = c
                r = sessoes[perfil].get(url)
                html = r.text.replace('<link rel="stylesheet" href="/static/estilo.css">', f"<style>{css}</style>")
                # T-0036: o JS (uma tela no PC, lista do celular) e o logo também vão dentro do HTML
                html = html.replace('<script src="/static/bc3.js"></script>', f"<script>{js}</script>")
                html = html.replace("/static/logo_bap.png", "data:image/png;base64," + logo)
                saida.append((r.status_code, html))
    return saida


def main(argv: list[str]) -> int:
    import json
    pacote = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 and argv[1] else None
    destino = Path(argv[2] if len(argv) > 2 else "farol.html")
    rid = argv[3] if len(argv) > 3 else "pl_inadimplencia"
    if pacote is None:
        from farol_fixture import pacote_farol
        pacote = pacote_farol()
    url = f"/farol/{rid}" + (f"?uf={argv[4]}" if len(argv) > 4 else "")
    (status, html), = paginas(pacote, [("admin", url)])
    destino.write_text(html, encoding="utf-8")
    print("gravado:", destino, "status", status)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
