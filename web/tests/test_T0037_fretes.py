"""T-0037: Farol de Fretes na web (contrato §10.12): abas, perfis, edição só do admin, linha sem chave e a marca
"Aguardando o PC" nos dois faróis que editam a mesma linha. Dados fictícios."""
import copy

from conftest import postar
from fretes_fixture import TIT, pacote_fretes
from test_T0021_edicao import _criar, _entrar_como, _form, _link_editar, _linhas_fila

from app import edicoes, render, tabelas

URL = "/farol/pl_fretes?aba=notas"


def _pacote_ok(admin):
    assert postar(admin, pacote_fretes()).status_code == 200
    return admin


def _como(admin, perfil):
    login = _criar(admin, perfil)
    _entrar_como(admin, login)                                    # o mesmo cliente troca de usuário (como na T-0021)
    return admin


def test_RN_POS_010_lugar_e_entradas_do_fretes():
    assert edicoes.LUGARES[("pl_fretes", TIT)] == "pos_venda"
    assert "pl_fretes" in render.FAROIS                            # o BC3 vale para todos os faróis (#146)
    assert "pl_fretes" in dict(render.GRUPOS_MENU)["Pós-venda"]
    assert [t for _, t in tabelas.ABAS["pl_fretes"]] == [TIT, "Por UF", "Por cidade", "Por transportadora"]


def test_RN_POS_010_pacote_com_as_4_abas_aceito_e_as_abas_aparecem(admin):
    _pacote_ok(admin)
    html = admin.get("/farol/pl_fretes").text
    for nome in ("Notas", "UF", "Cidade", "Transportadora"):       # ABA_CURTA (T-0033): o título do pacote não muda
        assert f">{nome}<" in html
    for aba in ("notas", "uf", "cidade", "transportadora"):
        assert admin.get(f"/farol/pl_fretes?aba={aba}").status_code == 200


def test_RN_POS_010_edicao_fora_do_lugar_recusada(admin):
    p = pacote_fretes()
    t = p["relatorios"]["pl_fretes"]["tabelas"]
    t[1]["edicao"] = copy.deepcopy(t[0]["edicao"])                 # "Por UF" não edita
    assert postar(admin, p).status_code == 422


def test_RN_GER_012_so_o_admin_edita_e_gerente_e_posvenda_veem(admin):
    _pacote_ok(admin)
    assert 'class="bt-ed"' in admin.get(URL).text
    logins = [_criar(admin, perfil) for perfil in ("gerente", "pos_venda")]
    for login in logins:
        c = admin
        _entrar_como(c, login)
        pag = c.get(URL)
        assert pag.status_code == 200 and 'class="bt-ed"' not in pag.text
        assert c.get("/farol/pl_fretes/editar?tab=Notas%20com%20frete&chave=x").status_code == 403
        assert c.post("/farol/pl_fretes/editar", data={}).status_code == 403


def test_RN_GER_014_diretor_so_o_resumo(admin):
    _pacote_ok(admin)
    c = _como(admin, "diretor")
    assert c.get("/farol/pl_fretes").status_code == 200
    assert c.get(URL).status_code == 403


def test_RN_POS_010_edita_so_os_5_campos_e_so_acrescenta(admin, amb):
    _pacote_ok(admin)
    campos, form = _form(admin, _link_editar(admin.get(URL).text))
    assert "c_frete_real" not in form and "c_etapa" in form and "c_responsavel" in form
    r = admin.post("/farol/pl_fretes/editar", follow_redirects=False,
                   data=dict(campos, c_etapa="EM TRÂNSITO", c_responsavel="MOTORISTA FICTICIO 2"))
    assert r.status_code == 303
    (reg,) = _linhas_fila(amb)
    assert reg["rid"] == "pl_fretes" and reg["modulo"] == "pos_venda" and reg["tabela"] == TIT
    assert set(reg["valores"]) <= {"etapa", "responsavel", "transportadora", "prevista_manual", "entregue_em"}
    assert reg["valores"]["etapa"] == "EM TRÂNSITO"
    campos2, _ = _form(admin, _link_editar(admin.get(URL).text))
    assert admin.post("/farol/pl_fretes/editar", data=dict(campos2, c_etapa="CANCELADA")).status_code in (200, 303)
    fila = _linhas_fila(amb)
    assert len(fila) == 2 and fila[0] == reg                       # a fila só acrescenta


def test_RN_POS_010_valor_fora_das_opcoes_recusado(admin, amb):
    _pacote_ok(admin)
    campos, _ = _form(admin, _link_editar(admin.get(URL).text))
    r = admin.post("/farol/pl_fretes/editar", data=dict(campos, c_etapa="ETAPA INVENTADA"))
    assert r.status_code == 400 and _linhas_fila(amb) == []


def test_RN_POS_010_linha_sem_chave_mostra_a_mensagem_do_lugar(admin):
    _pacote_ok(admin)
    html = admin.get(URL).text
    assert edicoes.MSG_SEM_CHAVE_POR_LUGAR[("pl_fretes", TIT)] in html
    assert edicoes.MSG_SEM_CHAVE not in html
    assert edicoes.MSG_SEM_CHAVE in admin.get("/farol/pl_entregas?aba=entregas").text   # o Entregas segue com a dele


def test_RN_POS_010_marca_aguardando_vale_nos_dois_farois(admin, amb):
    _pacote_ok(admin)
    campos, _ = _form(admin, _link_editar(admin.get(URL).text))
    chave = campos["chave"]
    admin.post("/farol/pl_fretes/editar", data=dict(campos, c_etapa="EM TRÂNSITO"))
    assert "Aguardando o PC" in admin.get(URL).text
    p = pacote_fretes()                                           # a mesma nota existe no Farol de Entregas
    p["relatorios"]["pl_entregas"]["tabelas"][0]["edicao"]["chaves"][1] = chave
    assert postar(admin, p).status_code == 200
    assert "Aguardando o PC" in admin.get("/farol/pl_entregas?aba=entregas").text
    f = edicoes.Fila(amb)
    assert ("Entregas", chave) in f.situacao("pl_entregas") and (TIT, chave) in f.situacao("pl_fretes")
    f.registrar(usuario="x", rid="pl_entregas", tabela="Entregas", modulo="pos_venda", chave="OUTRA|1|1",
                valores={"etapa": "ENTREGUE"}, antes={})
    assert (TIT, "OUTRA|1|1") in f.situacao("pl_fretes")          # e o contrário: Entregas marca o Fretes


def test_RN_GER_012_pacote_sem_fretes_continua_aceito(admin):
    p = pacote_fretes()
    del p["relatorios"]["pl_fretes"]
    assert postar(admin, p).status_code == 200


def test_RN_POS_010_formulario_mostra_a_data_real_da_fixture(admin):
    _pacote_ok(admin)
    url = "/farol/pl_fretes/editar?tab=Notas%20com%20frete&chave=FILIAL%20FICTICIA%7C700102%7C1"
    assert 'value="2026-11-10"' in admin.get(url).text           # DT. REAL = 10/11/2026 (ISO no campo)


def test_RN_POS_010_marca_do_fretes_vai_ao_entregas_e_nao_a_devolucao(amb, monkeypatch):
    """IRMAOS é lista explícita (desenho §4.4): a Devolução também é `pos_venda`, mas é outra aba do PC."""
    dev = ("pl_devolucoes", "Devoluções")
    monkeypatch.setitem(edicoes.LUGARES, dev, "pos_venda")        # mesmo com a Devolução no LUGARES (T-0023)
    assert not any(dev in g for g in edicoes.IRMAOS)
    assert edicoes.IRMAOS == (frozenset({("pl_fretes", TIT), ("pl_entregas", "Entregas"),
                                         ("pl_entregas", "Pendências dos meses anteriores")}),)
    f = edicoes.Fila(amb)
    ch = "FILIAL FICTICIA|700109|1"
    f.registrar(usuario="x", rid="pl_fretes", tabela=TIT, modulo="pos_venda", chave=ch,
                valores={"etapa": "EM TRÂNSITO"}, antes={})
    assert ("Entregas", ch) in f.situacao("pl_entregas")
    assert ("Pendências dos meses anteriores", ch) in f.situacao("pl_entregas")
    assert f.situacao("pl_devolucoes") == {}                       # a Devolução de mesma chave não é marcada


def test_RN_POS_010_grade_do_fretes_ate_10_colunas_e_popup_sem_repetir():
    g = tabelas.GRADE[("pl_fretes", TIT)]
    assert g["chave"] == "NF" and g["chave"] in g["grade"] and len(g["grade"]) <= 10
    for c in ("ETAPA", "TRANSPORTADORA", "ENTREGAR ATÉ", "ENTREGUE"):   # as editáveis ficam na grade (§7.1)
        assert c in g["grade"]
    no_popup = [c for _, cs in g["blocos"] for c in cs]
    assert "RESPONSÁVEL" in no_popup and not set(no_popup) & set(g["grade"])
    cols = {c[0] for c in tabelas.COLUNAS[TIT]}
    assert set(g["grade"]) | set(no_popup) <= cols


def test_RN_POS_010_aba_curta_e_dica_da_busca(admin):
    assert tabelas.aba_curta(TIT) == "Notas" and tabelas.aba_curta("Por transportadora") == "Transportadora"
    assert tabelas.dica_busca("pl_fretes", TIT, 50) == "Buscar NF ou cliente"
    assert tabelas.dica_busca("pl_entregas", "Entregas", 50) is None   # os faróis antigos seguem com a dica padrão
    _pacote_ok(admin)
    assert 'placeholder="Buscar NF ou cliente"' in admin.get(URL).text



# ---- parecer de UX da simulação v2 (R1, A1, A5)
def test_UX_R1_so_cor_da_paleta_da_marca_nos_graficos():
    from app import marca
    verde = marca.TOKENS["--grafico-1"]
    cinza = marca.TOKENS["--grafico-3"]
    assert render._cor(verde, cinza) == verde
    assert render._cor("#1F4FD1", cinza) == cinza and render._cor("#2F6FB5", cinza) == cinza   # o AZUL do PC
    assert render._cor("azul", cinza) == cinza
    b = render._bloco_barras({"grafico": {"rotulos": ["A"], "series": [{"nome": "n", "cor": "#1F4FD1", "valores": [3]}]}})
    assert b["cols"][0]["barras"][0]["cor"] == cinza
    h = render._bloco_hbarras({"rotulos": ["A", "B"], "valores": [1, 2], "cores": ["#1F4FD1", verde]})
    assert [x["cor"] for x in h["linhas"]] == [cinza, verde]


def test_UX_A1_grafico_do_resumo_ocupa_a_largura_toda(admin):
    _pacote_ok(admin)
    html = admin.get("/farol/pl_fretes").text
    assert "graf-larga" in html and "gb-larga" in html
    assert '<span class="r-l">DEZ/25</span><span class="r-c">DEZ</span>' in html       # todos os meses; 3 letras no celular
    assert "#1F4FD1" not in html
    g = {"grafico": {"rotulos": ["JAN/26", "FEV/26"], "series": [{"nome": "n", "valores": [1, 2]}]}, "colspan": 3}
    assert render._bloco_barras(g)["larga"] is True
    _, out = render._blocos({"blocos": [{"tipo": "barras", "row": 0, "col": 0, **g},
                                        {"tipo": "barras", "row": 1, "col": 0, **g}]})
    assert not any(x["larga"] for x in out)                       # com 2 gráficos, os outros faróis seguem como estavam


def test_UX_A5_popup_da_nota_diz_NF_em_maiusculas(admin):
    _pacote_ok(admin)
    assert 'data-tit="NF 700101"' in admin.get(URL).text


def test_RN_GER_017_analista_ve_o_fretes_como_o_gerente_e_nao_edita(admin):
    """P1 = A: o analista lê como o gerente (as 4 abas e o Resumo) e não edita (só o admin edita)."""
    assert "analista" in render.FAROIS["pl_fretes"][1] and "analista" in tabelas.VE_TABELAS["pl_fretes"]
    assert "analista" not in edicoes.EDITA
    _pacote_ok(admin)
    _entrar_como(admin, _criar(admin, "analista"))
    for aba in ("", "?aba=notas", "?aba=uf", "?aba=cidade", "?aba=transportadora"):
        assert admin.get("/farol/pl_fretes" + aba).status_code == 200, aba
    assert 'class="bt-ed"' not in admin.get(URL).text
    assert admin.get("/farol/pl_fretes/editar?tab=Notas%20com%20frete&chave=x").status_code == 403
    assert admin.post("/farol/pl_fretes/editar", data={}).status_code == 403


def test_RN_POS_009_resumo_do_fretes_titulos_total_frases_e_rotulos_do_pc(admin):
    """Y5: o Resumo (saída do robô) traz as 3 tabelas "(NOV/26)", o TOTAL igual ao cartão "Notas com frete",
    as 2 frases e os rótulos do PC; o cartão "Sem transportadora" bate com a linha da tabela."""
    import re
    _pacote_ok(admin)
    html = admin.get("/farol/pl_fretes").text
    for t in ("Por UF (NOV/26)", "Por cidade (NOV/26)", "Por transportadora (NOV/26)"):
        assert t in html
    from fretes_fixture import blocos_resumo, farol_fretes
    bl, frases = blocos_resumo()
    kp = {k["rotulo"]: k for k in farol_fretes()["kpis"]}
    notas = int(kp["Notas com frete"]["valor"])
    tabs = [b for b in bl if b["tipo"] == "tabela"]
    assert [b["titulo"] for b in tabs] == ["Por UF (NOV/26)", "Por cidade (NOV/26)", "Por transportadora (NOV/26)"]
    for b in tabs:
        assert b["total"][1] == notas == sum(x[1] for x in b["linhas"])                 # TOTAL = cartão
    assert len({tuple(b["total"]) for b in tabs}) == 1                                  # as 3 fecham igual
    assert [x[1] for x in frases] == ["PA concentra 56% do valor das notas com frete.",
                                      "TRANSP. GAMA leva 34% do valor."]
    for fr in [x[1] for x in frases]:
        assert fr in html
    rot = {b["titulo"]: [x[0] for x in b["linhas"]] for b in tabs}
    assert "Sem UF" in rot["Por UF (NOV/26)"]
    assert {"SERRA BONITA / Sem UF", "Sem cidade / MA"} <= set(rot["Por cidade (NOV/26)"])
    por_transp = {x[0]: x[1] for x in next(b for b in tabs if b["titulo"].startswith("Por transp"))["linhas"]}
    assert por_transp["Sem acompanhamento"] == 1
    assert por_transp["Sem transportadora"] == int(kp["Sem transportadora"]["valor"]) == 1   # cartão = linha
    for r in ("Sem UF", "SERRA BONITA / Sem UF", "Sem transportadora", "Sem acompanhamento"):
        assert r in html and not re.search(r"\(sem\)", html, re.I)


def test_UX_A8_cores_do_pc_viram_o_token_do_mesmo_papel():
    """O âmbar de "atenção" do PC (AMARELO) não pode virar o cinza neutro (atingimento, rota, CHURN)."""
    from app import marca
    t = marca.TOKENS
    h = render._bloco_hbarras({"rotulos": ["ok", "atenção", "alerta", "neutro"], "valores": [1, 2, 3, 4],
                               "cores": ["#62BB47", "#C98A00", "#B3261E", "#A7B0AA"]})
    assert [x["cor"] for x in h["linhas"]] == [t["--verde-marca"], t["--grafico-2"], t["--alerta"], t["--grafico-3"]]
    assert len({x["cor"] for x in h["linhas"]}) == 4                  # os estados continuam distintos
    h2 = render._bloco_hbarras({"rotulos": ["a"], "valores": [1], "cores": ["#59BA61"]})
    assert h2["linhas"][0]["cor"] == t["--verde-marca"]
