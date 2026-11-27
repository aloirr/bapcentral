"""T-0050 (RN-GER-018): acesso aos faróis por usuário, na tela Usuários (só admin).

O perfil dá o padrão; o admin tira ou libera farol a farol. Dados 100% fictícios.
Decisões do Alexandre: P1 B (libera além do perfil), P2 A (Painel na lista), P3 A (farol novo segue o perfil),
P4 A (o liberado vê só o Resumo: sem as tabelas de clientes e sem Exportar).
"""
import ast
import json
import re
from pathlib import Path

import pytest
from conftest import postar, token_form
from farol_fixture import pacote_tres_farois
from test_farois import _usuario

from app import acesso, render, usuarios

PERFIS = ("admin", "gerente", "analista", "diretor", "trade", "pre_venda", "vendas", "pos_venda")
LISTA = acesso.rids_da_lista()
MAIN = Path(__file__).parent.parent / "app" / "main.py"


def _salvar(admin, alvo, marcados):
    return admin.post("/usuarios", data={"acao": "acesso", "login": alvo, "lista": "1", "farol": list(marcados),
                                         "csrf": token_form(admin, "/usuarios")})


def _com(admin, login, perfil, menos=(), mais=()):
    """Usuário `login` do `perfil`, com as exceções dadas, já logado."""
    c = _usuario(admin, login, perfil)
    if menos or mais:
        marc = (acesso.padrao_do_perfil(perfil) - set(menos)) | set(mais)
        r = _salvar(admin, login, marc)
        assert r.status_code == 200, r.text
    return c


def _tela(c, rid):
    return c.get("/painel" if rid == acesso.PAINEL else f"/farol/{rid}").status_code


# ------------------------------------------------------------------ a função pura
def test_RN_GER_018_pode_ver_perfil_mais_excecoes():
    u = {"perfil": "vendas", "acesso": {"menos": ["vc_planner"], "mais": ["pv_pedidos"]}}
    assert acesso.pode_ver(u, "vc_visitas")                     # padrão
    assert not acesso.pode_ver(u, "vc_planner")                 # tirado
    assert acesso.pode_ver(u, "pv_pedidos")                     # liberado
    assert "pv_pedidos" in acesso.visiveis("vendas", u["acesso"]) - acesso.padrao_do_perfil("vendas")   # liberado
    assert acesso.contagem(u) == (1, 1)
    assert not acesso.pode_ver(u, "pl_entregas")                # fora do perfil e sem exceção
    assert acesso.pode_ver({"perfil": "vendas"}, "vc_planner")   # sem o campo: o perfil puro (nada a migrar)


def test_RN_GER_018_rid_inexistente_inerte():
    u = {"perfil": "vendas", "acesso": {"menos": ["nao_existe"], "mais": ["outro_que_nao_existe"]}}
    assert not acesso.pode_ver(u, "nao_existe") and not acesso.pode_ver(u, "outro_que_nao_existe")
    assert not acesso.pode_ver({"perfil": "admin"}, "xx") and not acesso.perfil_ve("admin", "xx")
    assert acesso.pode_ver(u, "vc_visitas")                     # a exceção inerte não atrapalha ninguém
    assert "outro_que_nao_existe" not in [r for r, _ in acesso.farois_do_usuario(u)]
    with pytest.raises(ValueError):
        acesso.excecoes("vendas", {"nao_existe"})
    # inerte e guardado: ao gravar, o rid desconhecido do acesso antigo fica
    antigo = {"menos": ["nao_existe"], "mais": ["outro_que_nao_existe"]}
    n = acesso.excecoes("vendas", acesso.padrao_do_perfil("vendas"), antigo)
    assert n == {"menos": ["nao_existe"], "mais": ["outro_que_nao_existe"]}


def test_RN_GER_018_farol_novo_segue_o_perfil(monkeypatch):
    u = {"perfil": "vendas", "acesso": {"menos": ["vc_planner"], "mais": []}}
    monkeypatch.setitem(render.FAROIS, "vc_novo", ("Farol Novo", render.LEITURA_GERAL + ("vendas",)))
    assert acesso.pode_ver(u, "vc_novo") and "vc_novo" in acesso.rids_da_lista()        # P3 A: chega marcado
    assert not acesso.pode_ver({"perfil": "pre_venda", "acesso": {}}, "vc_novo")


def test_RN_GER_018_painel_e_o_menu_seguem_a_lista():
    todos = {r: {} for r in render.FAROIS}
    u = {"perfil": "gerente", "acesso": {"menos": ["vc_painel", "vc_saldo"], "mais": []}}
    g = render.menu_lateral("gerente", todos, None, painel=acesso.pode_ver(u, "vc_painel"), vistos=acesso.farois_do_usuario(u))
    nomes = [i["nome"] for x in g for i in x["itens"]]
    assert "Painel Executivo" not in nomes and "Saldo" not in nomes and "Markup" in nomes
    v = {"perfil": "vendas", "acesso": {"menos": [], "mais": ["vc_painel", "pv_pedidos"]}}
    g = render.menu_lateral("vendas", todos, None, painel=acesso.pode_ver(v, "vc_painel"), vistos=acesso.farois_do_usuario(v))
    nomes = [i["nome"] for x in g for i in x["itens"]]
    assert "Painel Executivo" in nomes and "Pedidos" in nomes
    # página inicial: quem tem o Painel pelo perfil abre nele; o liberado abre no 1º farol da área
    assert render.pagina_inicial("vendas", acesso.farois_do_usuario(v), False) == "/farol/vc_visitas"
    assert render.pagina_inicial("gerente", acesso.farois_do_usuario(u), False) == "/farol/pv_pedidos"


def test_RN_GER_018_mudancas_e_origem():
    antes = {"menos": [], "mais": []}
    m = acesso.mudancas("vendas", antes, {"menos": ["vc_planner"], "mais": ["pv_pedidos"]})
    assert ("vc_planner", "-", "perfil") in m and ("pv_pedidos", "+", "liberado") in m and len(m) == 2
    assert acesso.mudancas("vendas", {"menos": ["vc_planner"], "mais": []}, antes) == [("vc_planner", "+", "perfil")]
    assert acesso.mudancas("vendas", {"menos": [], "mais": ["pv_pedidos"]}, antes) == [("pv_pedidos", "-", "liberado")]
    assert acesso.mudancas("vendas", antes, antes) == []


# ------------------------------------------------------------------ 403 por perfil x usuário (padrão, tirado, liberado)
def test_RN_GER_018_matriz_perfil_x_usuario(admin):
    """Cada perfil, em 2 usuários: o padrão (só o perfil) e o personalizado (tira tudo menos o 1º do perfil; libera todo o resto)."""
    for perfil in PERFIS:
        padrao = _usuario(admin, f"mx.{perfil.replace('_', '')}", perfil)
        pad = [r for r in LISTA if acesso.perfil_ve(perfil, r)]
        for rid in LISTA:
            assert _tela(padrao, rid) == (200 if rid in pad else 403), (perfil, rid, "padrão")
        fora = [r for r in LISTA if r not in pad]
        mantidos = pad[:1] + fora
        pers = _com(admin, f"mp.{perfil.replace('_', '')}", perfil,
                    menos=pad[1:], mais=[] if perfil == "admin" else fora)
        for rid in LISTA:
            assert _tela(pers, rid) == (200 if rid in mantidos else 403), (perfil, rid, "personalizado")
            if rid != acesso.PAINEL:
                esperado = 200 if rid in mantidos else 403
                assert pers.get(f"/farol/{rid}/linhas").status_code in ((esperado,) if esperado == 403 else (200, 403)), (perfil, rid)


def test_RN_GER_018_admin_tira_farol_de_si_mas_nao_usuarios(admin):
    adm = _com(admin, "adm.dois", "admin", menos=[r for r in LISTA if r != "vc_base"])
    assert _tela(adm, "vc_base") == 200 and _tela(adm, "vc_painel") == 403 and _tela(adm, "pv_pedidos") == 403
    assert adm.get("/usuarios").status_code == 200 and adm.get("/senha").status_code == 200   # fora da lista
    assert "usuarios" not in acesso.rids_da_lista() and "senha" not in acesso.rids_da_lista()
    r = adm.get("/", follow_redirects=False)
    assert r.headers["location"] == "/farol/vc_base"            # sem o Painel, abre no 1º farol que vê


def test_RN_GER_018_rotas_com_rid_fixo_tirado_e_403_ate_para_o_admin(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    adm = _com(admin, "adm.tres", "admin", menos=["pv_pedidos", "an_divergencias", "pl_inadimplencia", "vc_visitas"])
    assert adm.get("/farol/pv_pedidos/csv/qualquer.csv").status_code == 403
    assert adm.get("/farol/an_divergencias/correcao.xlsx").status_code == 403
    assert adm.get("/farol/pv_pedidos/editar?tab=x&chave=y").status_code == 403
    assert adm.post("/farol/pv_pedidos/editar", data={"csrf": "x"}).status_code == 403
    assert adm.post("/farol/pl_inadimplencia/cobranca", data={"csrf": "x"}).status_code == 403
    assert adm.get("/visitas/atualizar").status_code == 403
    assert adm.get("/farol/pv_pedidos/exportar?aba=pedidos&formato=xlsx").status_code == 403
    assert adm.get("/farol/pv_pedidos/parcial.png?q=acum").status_code == 403
    assert adm.get("/farol/vc_visitas/parcial").status_code == 403
    # o que ele não tirou segue
    assert adm.get("/farol/pl_entregas/exportar?aba=entregas&formato=xlsx").status_code in (200, 404)


def test_RN_GER_018_liberado_ve_so_o_resumo(admin):
    """P4 A: o liberado abre a tela (Resumo); as abas de tabela, o Exportar, o CSV e a edição dão 403."""
    assert postar(admin, pacote_tres_farois()).status_code == 200
    v = _com(admin, "lib.vendas", "vendas", mais=["pv_pedidos", "pl_entregas", "pl_inadimplencia"])
    for rid in ("pv_pedidos", "pl_entregas", "pl_inadimplencia"):
        assert v.get(f"/farol/{rid}").status_code == 200, rid                      # o Resumo
        assert v.get(f"/farol/{rid}?aba=resumo").status_code == 200
    for rid, aba in (("pv_pedidos", "pedidos"), ("pv_pedidos", "solicitacao"), ("pl_entregas", "entregas"),
                     ("pl_inadimplencia", "cliente"), ("pl_inadimplencia", "cobrar")):
        assert v.get(f"/farol/{rid}?aba={aba}").status_code == 403, (rid, aba)
        assert v.get(f"/farol/{rid}/linhas?aba={aba}").status_code == 403, (rid, aba)
        assert v.get(f"/farol/{rid}/exportar?aba={aba}&formato=xlsx").status_code == 403, (rid, aba)
    assert v.get("/farol/pv_pedidos/exportar?todas=1&formato=xlsx").status_code == 403
    assert v.get("/farol/pv_pedidos/csv/qualquer.csv").status_code == 403
    assert v.get("/farol/pv_pedidos/editar?tab=x&chave=y").status_code == 403
    assert v.post("/farol/pl_inadimplencia/cobranca", data={"csrf": "x"}).status_code == 403
    assert "Exportar" not in v.get("/farol/pv_pedidos").text
    assert "telefone" not in v.get("/farol/pl_inadimplencia").text.lower()
    assert v.get("/farol/pl_entregas/parcial.png?q=acum").status_code == 403       # a de Entregas lista cliente
    # os cortes de dado seguem pelo perfil: o diretor continua só no Resumo (RN-GER-014)
    d = _com(admin, "lib.diretor", "diretor", mais=[])
    assert d.get("/farol/pv_pedidos?aba=pedidos").status_code == 403


def test_RN_GER_018_painel_liberado_abre_completo_e_nao_vira_pagina_inicial(admin):
    v = _com(admin, "lib.painel", "vendas", mais=["vc_painel"])
    assert v.get("/painel").status_code == 200
    assert v.get("/", follow_redirects=False).headers["location"] == "/farol/vc_visitas"
    g = _com(admin, "tir.painel", "gerente", menos=["vc_painel"])
    assert g.get("/painel").status_code == 403
    assert _usuario(admin, "pad.painel", "gerente").get("/", follow_redirects=False).headers["location"] == "/painel"


def test_RN_GER_018_trade_sem_farol_e_liberado(admin):
    t = _usuario(admin, "trade.um", "trade")
    assert "ainda não estão no site" in t.get("/").text
    t2 = _com(admin, "trade.dois", "trade", mais=["pv_pedidos"])
    assert t2.get("/", follow_redirects=False).headers["location"] == "/farol/pv_pedidos"
    assert t2.get("/farol/pv_pedidos").status_code == 200 and t2.get("/farol/vc_visitas").status_code == 403


def test_RN_GER_018_corte_por_cima_com_excecao(admin):
    """Tirar e devolver o farol não dá Cobrar a quem o perfil não dá (RN-POS-004); a tela do liberado não mostra telefone (RN-GER-011)."""
    assert postar(admin, pacote_tres_farois()).status_code == 200
    g = _com(admin, "corte.gerente", "gerente", menos=["pl_inadimplencia"])
    assert g.get("/farol/pl_inadimplencia").status_code == 403
    assert _salvar(admin, "corte.gerente", acesso.padrao_do_perfil("gerente")).status_code == 200
    assert g.get("/farol/pl_inadimplencia").status_code == 200 and g.get("/farol/pl_inadimplencia?aba=cobrar").status_code == 403
    v = _com(admin, "corte.vendas", "vendas", mais=["pl_inadimplencia"])
    assert "telefone" not in v.get("/farol/pl_inadimplencia").text.lower()


def test_RN_GER_018_vc_painel_nao_e_rota_de_farol(admin):
    """O Painel está na lista de acesso, mas só abre por /painel: em /farol/vc_painel é 403 (nunca 500)."""
    for url in ("/farol/vc_painel", "/farol/vc_painel/linhas", "/farol/vc_painel/editar", "/farol/vc_painel/exportar?formato=xlsx"):
        assert admin.get(url).status_code == 403, url
    assert admin.post("/farol/vc_painel/editar", data={"csrf": "x"}).status_code == 403
    assert admin.get("/painel").status_code == 200


def test_RN_GER_018_atualizar_visitas_so_de_quem_tem_o_farol_pelo_perfil(admin):
    assert _com(admin, "vis.pre", "pre_venda", mais=["vc_visitas"]).get("/visitas/atualizar").status_code == 403
    assert _com(admin, "vis.trade", "trade", mais=["vc_visitas"]).get("/visitas/atualizar").status_code == 403
    assert _usuario(admin, "vis.vendas", "vendas").get("/visitas/atualizar").status_code == 200


# ------------------------------------------------------------------ tela, registro e erros
def test_RN_GER_018_tela_usuarios_e_confirmacao(admin):
    _usuario(admin, "tela.um", "vendas")
    r = _salvar(admin, "tela.um", (acesso.padrao_do_perfil("vendas") - {"vc_planner"}) | {"vc_painel"})
    assert r.status_code == 200
    assert "Acesso de tela.um salvo. Liberado: Painel Executivo. Tirado: Roteirização." in r.text
    assert "1 farol tirado" in r.text and "1 farol liberado" in r.text
    assert "Do perfil" in r.text and "Liberar além do perfil" in r.text and "Alterado em" in r.text
    assert re.search(r"Alterado em \d\d/\d\d/\d{4} \d\d:\d\d por ", r.text)
    # o Usuários e o Trocar senha não têm caixa
    assert 'name="farol" value="usuarios"' not in r.text and 'name="farol" value="senha"' not in r.text


def test_RN_GER_018_nenhum_farol_marcado_e_400(admin):
    _usuario(admin, "vazio.um", "vendas")
    r = _salvar(admin, "vazio.um", [])
    assert r.status_code == 400
    assert "vazio.um: marque ao menos um farol. Para tirar todo o acesso, use Desativar." in r.text
    # o trade sem farol e sem nada liberado grava normalmente
    _usuario(admin, "vazio.trade", "trade")
    assert _salvar(admin, "vazio.trade", []).status_code == 200


def test_RN_GER_018_rid_desconhecido_no_formulario_e_400(admin):
    _usuario(admin, "desc.um", "vendas")
    r = _salvar(admin, "desc.um", ["vc_visitas", "nao_existe"])
    assert r.status_code == 400 and "A lista de faróis mudou." in r.text


def test_RN_GER_018_so_admin_e_csrf(admin):
    g = _usuario(admin, "so.gerente", "gerente")
    assert g.post("/usuarios", data={"acao": "acesso", "login": "so.gerente", "lista": "1",
                                     "farol": ["vc_visitas"], "csrf": "x"}).status_code == 403
    assert g.get("/usuarios").status_code == 403
    r = admin.post("/usuarios", data={"acao": "acesso", "login": "so.gerente", "lista": "1",
                                      "farol": ["vc_visitas"], "csrf": "errado"})
    assert r.status_code == 403
    assert _tela(g, "pv_pedidos") == 200                        # nada mudou


def test_RN_GER_018_criar_com_faroi_marcados(admin):
    padrao = acesso.padrao_do_perfil("pre_venda")
    r = admin.post("/usuarios", data={"acao": "criar", "login": "novo.um", "perfil": "pre_venda", "senha": "senha-de-teste-12",
                                      "lista": "1", "farol": sorted((padrao - {"pv_indicadores"}) | {"vc_painel"}),
                                      "csrf": token_form(admin, "/usuarios")})
    assert r.status_code == 200 and "1 farol tirado" in r.text and "1 farol liberado" in r.text
    # sem JS (sem `lista`): as caixas são só as liberadas; o perfil entra sempre
    r = admin.post("/usuarios", data={"acao": "criar", "login": "novo.dois", "perfil": "pre_venda", "senha": "senha-de-teste-12",
                                      "farol": ["vc_painel"], "csrf": token_form(admin, "/usuarios")})
    assert r.status_code == 200 and "novo.dois" in r.text
    linha = r.text.split("novo.dois")[1].split("</li>")[0]
    assert "1 farol liberado" in linha and "tirado" not in linha.replace('class="selo f-tag selo-tirado">tirado', "")


def test_RN_GER_018_desativado_guarda_excecoes_e_sem_campo(admin):
    _com(admin, "des.um", "vendas", mais=["pv_pedidos"])
    t = token_form(admin, "/usuarios")
    assert admin.post("/usuarios", data={"acao": "desativar", "login": "des.um", "csrf": t}).status_code == 200
    r = admin.post("/usuarios", data={"acao": "ativar", "login": "des.um", "csrf": token_form(admin, "/usuarios")})
    linha = r.text.split("des.um")[1].split("</li>")[0]
    assert "1 farol liberado" in linha                           # as exceções ficaram
    # o `usuarios.json` de hoje (sem `acesso`) segue o perfil
    assert acesso.pode_ver({"perfil": "vendas", "ativo": True}, "vc_visitas")


def _linhas_registro(amb):
    arq = amb / "usuarios_acesso.jsonl"
    return arq.read_bytes() if arq.exists() else b""


def test_RN_GER_018_registro_so_de_acrescimo(admin, amb):
    _usuario(admin, "reg.um", "vendas")
    assert _linhas_registro(amb) == b""
    _salvar(admin, "reg.um", (acesso.padrao_do_perfil("vendas") - {"vc_planner"}) | {"pv_pedidos"})
    a = _linhas_registro(amb)
    regs = [json.loads(x) for x in a.decode().splitlines()]
    assert {(r["rid"], r["mudanca"], r["origem"]) for r in regs} == {("vc_planner", "-", "perfil"), ("pv_pedidos", "+", "liberado")}
    for r in regs:
        assert set(r) == {"quando", "lote", "quem", "alvo", "perfil", "rid", "mudanca", "origem", "acao"}
        assert r["alvo"] == "reg.um" and r["perfil"] == "vendas" and r["acao"] == "editar" and r["quem"]
        assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-04:00$", r["quando"])
    assert len({r["lote"] for r in regs}) == 1
    # salvar sem mudança efetiva: nenhuma linha
    _salvar(admin, "reg.um", (acesso.padrao_do_perfil("vendas") - {"vc_planner"}) | {"pv_pedidos"})
    assert _linhas_registro(amb) == a
    # devolver o do perfil e tirar a liberação: o arquivo só cresce, as linhas antigas ficam idênticas
    _salvar(admin, "reg.um", acesso.padrao_do_perfil("vendas"))
    b = _linhas_registro(amb)
    assert b.startswith(a) and len(b) > len(a)
    novos = [json.loads(x) for x in b[len(a):].decode().splitlines()]
    assert {(r["rid"], r["mudanca"], r["origem"]) for r in novos} == {("vc_planner", "+", "perfil"), ("pv_pedidos", "-", "liberado")}
    assert len({r["lote"] for r in novos}) == 1 and novos[0]["lote"] != regs[0]["lote"]
    # criar com exceção também registra (acao criar); nada de dado de cliente: só estas chaves
    admin.post("/usuarios", data={"acao": "criar", "login": "reg.dois", "perfil": "trade", "senha": "senha-de-teste-12",
                                  "lista": "1", "farol": ["pv_pedidos"], "csrf": token_form(admin, "/usuarios")})
    ult = json.loads(_linhas_registro(amb).decode().splitlines()[-1])
    assert ult["acao"] == "criar" and ult["alvo"] == "reg.dois" and ult["origem"] == "liberado"


def test_RN_GER_018_falha_de_gravacao_503_e_desfeito(admin, amb, monkeypatch):
    _usuario(admin, "falha.um", "vendas")
    from app import usuarios as u

    def quebra(self):
        raise OSError("disco")
    with monkeypatch.context() as m:
        m.setattr(u.Usuarios, "_salvar", quebra)
        r = _salvar(admin, "falha.um", acesso.padrao_do_perfil("vendas") | {"pv_pedidos"})
    assert r.status_code == 503 and "Não deu para salvar agora. Tente de novo em 1 minuto." in r.text
    linhas = [json.loads(x) for x in _linhas_registro(amb).decode().splitlines()]
    assert linhas[-1]["acao"] == "desfeito" and linhas[-1]["lote"] == linhas[0]["lote"]
    assert _tela(_usuario(admin, "falha.dois", "vendas"), "pv_pedidos") == 403            # nada vazou para a memória


# ------------------------------------------------------------------ estrutural
def test_RN_GER_018_estrutural_nenhuma_checagem_direta_do_perfil_no_farol():
    """Nenhum `FAROIS[rid][1]` nem `VERES` em checagem fora de acesso.py; toda rota de farol passa por `acesso`."""
    fonte = MAIN.read_text(encoding="utf-8")
    assert not re.search(r"FAROIS\[[^\]]+\]\[1\]", fonte) and "VERES" not in fonte
    assert not re.search(r"perfil\s+(not\s+)?in\s+(render\.)?FAROIS", fonte)
    for arq in (MAIN.parent / "render.py", MAIN.parent / "usuarios.py", MAIN.parent / "visitas.py"):
        assert not re.search(r"in\s+(render\.)?FAROIS\[[^\]]+\]\[1\]", arq.read_text(encoding="utf-8")), arq.name
    arvore = ast.parse(fonte)
    guardas = ("exige(", "exige_farol(", "acesso.pode_ver(", "parciais_de(", "tabelas_para_exportar(", "acao_visitas(")
    visto = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in no.decorator_list:
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post")
                    and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
                caminho = d.args[0].value
                if caminho.startswith(("/farol/", "/painel", "/visitas/")):
                    corpo = ast.get_source_segment(fonte, no)
                    visto.append(caminho)
                    assert any(g in corpo for g in guardas), f"{caminho}: sem checagem de acesso ao farol"
    assert len(visto) >= 14, visto                  # as rotas de farol, painel e visitas foram achadas


def test_RN_GER_018_estrutural_acesso_e_puro():
    fonte = (MAIN.parent / "acesso.py").read_text(encoding="utf-8")
    for proibido in ("open(", "Path(", "json.", "request", "import os"):
        assert proibido not in fonte
