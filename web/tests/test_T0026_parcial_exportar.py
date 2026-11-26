"""T-0026: parcial em imagem (PNG do PC), PDF da parcial, Excel/PDF das tabelas e as 5 abas de resumo da
Inadimplência. Fixture fictícia (nenhum dado real)."""
import base64
import io
import struct
import zipfile
import zlib
from copy import deepcopy

import pytest
from conftest import postar
from farol_fixture import pacote_tres_farois
from test_abas import _cli_de


def _png(w=8, h=6):
    raw = b"".join(b"\x00" + bytes([200, 220, 200]) * w for _ in range(h))
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def _pacote(png=None):
    p = pacote_tres_farois()
    b64 = base64.b64encode(png or _png()).decode()
    for rid in ("pv_pedidos", "pl_entregas", "vc_visitas"):
        p["relatorios"][rid]["parciais"] = {q: {"rotulo": q, "png": b64} for q in ("acum", "d1", "hoje")}
    return p


def test_RN_WEB_parcial_png_invalido_recusado(admin):
    p = _pacote(b"nao e png")
    assert postar(admin, p).status_code == 422
    p = _pacote()
    p["relatorios"]["pv_pedidos"]["parciais"]["semana"] = p["relatorios"]["pv_pedidos"]["parciais"]["acum"]
    assert postar(admin, p).status_code == 422


def test_parcial_png_pdf_e_pagina(admin):
    assert postar(admin, _pacote()).status_code == 200
    for rid in ("pv_pedidos", "pl_entregas", "vc_visitas"):
        r = admin.get(f"/farol/{rid}/parcial.png?q=d1")
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n" and r.headers["cache-control"] == "no-store"
        assert admin.get(f"/farol/{rid}/parcial.pdf?q=acum").content[:5] == b"%PDF-"
        assert "Copiar imagem" in admin.get(f"/farol/{rid}/parcial").text
    assert "Parcial para o WhatsApp" in admin.get("/farol/pv_pedidos").text


def test_parcial_perfil_fora_403_e_entregas_so_quem_ve_tabela(admin):
    assert postar(admin, _pacote()).status_code == 200
    assert _cli_de(admin, "vendas").get("/farol/pv_pedidos/parcial.png?q=acum").status_code == 403
    assert _cli_de(admin, "diretor").get("/farol/pl_entregas/parcial.png?q=acum").status_code == 403   # lista cliente
    assert _cli_de(admin, "diretor").get("/farol/pv_pedidos/parcial.png?q=acum").status_code == 200
    assert _cli_de(admin, "pos_venda").get("/farol/pl_entregas/parcial.png?q=hoje").status_code == 200
    assert admin.get("/farol/xx/parcial.png").status_code == 403


def test_exportar_excel_e_pdf(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    r = admin.get("/farol/pv_pedidos/exportar?aba=pedidos&formato=xlsx")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "xl/worksheets/sheet1.xml" in z.namelist() and b"<sheetData>" in z.read("xl/worksheets/sheet1.xml")
    assert admin.get("/farol/vc_visitas/exportar?aba=dia&formato=pdf").content[:5] == b"%PDF-"
    todas = zipfile.ZipFile(io.BytesIO(admin.get("/farol/pv_pedidos/exportar?todas=1&formato=xlsx").content))
    assert len([n for n in todas.namelist() if n.startswith("xl/worksheets/")]) >= 2
    assert admin.get("/farol/pv_pedidos/exportar?todas=1&formato=pdf").status_code == 400


def test_exportar_respeita_perfil(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    assert _cli_de(admin, "diretor").get("/farol/pv_pedidos/exportar?aba=pedidos&formato=xlsx").status_code == 403
    assert _cli_de(admin, "vendas").get("/farol/pv_pedidos/exportar?aba=pedidos&formato=xlsx").status_code == 403
    assert _cli_de(admin, "pre_venda").get("/farol/pv_pedidos/exportar?aba=pedidos&formato=xlsx").status_code == 200


def test_excel_nao_vira_formula():
    from app import exportar
    t = {"titulo": "T", "cols": [("A", "texto")], "linhas": [["=1+1"]], "total": None}
    z = zipfile.ZipFile(io.BytesIO(exportar.xlsx([t])))
    xml = z.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" not in xml and 'inlineStr' in xml and "=1+1" in xml
