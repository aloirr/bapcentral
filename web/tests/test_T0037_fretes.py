"""T-0037: Farol de Fretes na web (contrato §10.11): abas, perfis, edição só do admin, linha sem chave e a marca
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
    assert "pl_fretes" in render.FAROIS and "pl_fretes" in render.BC3
    assert "pl_fretes" in dict(render.GRUPOS_MENU)["Pós-venda"]
    assert [t for _, t in tabelas.ABAS["pl_fretes"]] == [TIT, "Por UF", "Por cidade", "Por transportadora"]
    assert tabelas.VE_TABELAS["pl_fretes"] == ("admin", "gerente", "pos_venda")


def test_RN_POS_010_pacote_com_as_4_abas_aceito_e_as_abas_aparecem(admin):
    _pacote_ok(admin)
    html = admin.get("/farol/pl_fretes").text
    for nome in (TIT, "Por UF", "Por cidade", "Por transportadora"):
        assert nome in html
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


def test_RN_GER_012_diretor_so_o_resumo(admin):
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
