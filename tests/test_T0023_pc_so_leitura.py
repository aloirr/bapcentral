"""T-0023, critério 6 do desenho (docs/desenho/T-0023.md §5): PC só leitura
nos 3 faróis do pós-venda (NCC, Devoluções e Garantias).

RN-GER-012 · A edição é só pela BAP Central web; a tela do PC fica só
leitura ("A edição agora é só pela BAP Central web."). Exceção (P2 A): o
CONTATO da garantia (nome e telefone) só se edita no PC, no DialogoGarantia,
e o "Salvar contato" grava só `contato_nome` e `contato_fone`, acrescentando
linha no diário (dado digitado é intocável, regra 7).

O que depende do código novo (`bap_relatorios.py` da branch
modulo-farois/T-0023-pc-so-leitura) pula, com o motivo, enquanto o
`EDICAO_SO_WEB` do main não tiver o `pl_ncc`.

A tela roda de verdade (VistaTabela.__init__, editar, abrir_garantia e
DialogoGarantia.salvar) com um Tk de mentira, sem janela. Nenhum teste lê nem
grava a pasta RELATORIOS/ real de diários: os diários são fictícios, em
tmp_path. As bases congeladas só entram pelo `montar` (leitura).
"""
import hashlib
import sys
import types
from datetime import date, datetime
from pathlib import Path

import pytest

import garantias as gm
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
MSG = "A edição agora é só pela BAP Central web."
# (rid, título da aba): os 3 lugares que ficam só leitura no PC
TRES = (("pl_ncc", "NCC pendentes"), ("pl_devolucoes", "Devoluções"),
        ("pl_garantias", "Garantias"))
CONTATO = ("contato_nome", "contato_fone")


# ======================================================= Tk de mentira
class _Coringa:
    """Qualquer widget: aceita qualquer chamada e qualquer atributo."""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Coringa()

    def __getattr__(self, nome):
        return _Coringa()


class _Var:
    """tk.StringVar sem Tk: guarda o valor."""

    def __init__(self, master=None, value=None, name=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _ModTk(types.ModuleType):
    def __getattr__(self, nome):
        return _Coringa


def _mod_tk(nome):
    m = _ModTk(nome)
    m.StringVar = _Var
    m.TclError = Exception
    return m


def _importar_br():
    """bap_relatorios; sem tkinter (Python sem Tk), com coringas só durante
    o import (os módulos tkinter* falsos saem do sys.modules depois)."""
    try:
        import tkinter  # noqa: F401
        falsos = ()
    except ImportError:
        falsos = ("tkinter", "tkinter.ttk", "tkinter.messagebox",
                  "tkinter.filedialog", "tkinter.font",
                  "tkinter.simpledialog", "tkinter.colorchooser")
        for nome in falsos:
            sys.modules[nome] = _mod_tk(nome)
    try:
        import bap_relatorios
    finally:
        for nome in falsos:
            sys.modules.pop(nome, None)
    return bap_relatorios


br = _importar_br()

NOVO = any(rid == "pl_ncc" for rid, _ in br.EDICAO_SO_WEB)
so_no_codigo_novo = pytest.mark.skipif(
    not NOVO, reason="o EDICAO_SO_WEB deste bap_relatorios não tem o pl_ncc: "
    "o PC só leitura da T-0023 ainda não entrou (branch "
    "modulo-farois/T-0023-pc-so-leitura)")


class _Botao:
    """ttk.Button que guarda o texto e o comando."""
    criados = []

    def __init__(self, *a, text="", command=None, **k):
        self.text, self.command = text, command
        _Botao.criados.append(self)

    def __getattr__(self, nome):
        return _Coringa()


class _Tabela:
    """bv.Tabela que guarda o ao_duplo_clique."""
    ao_duplo_clique = None

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, nome):
        return _Coringa()


@pytest.fixture(scope="module")
def pcs():
    """Os 3 faróis montados nas bases congeladas (só leitura)."""
    import bap_automation as ba                         # noqa: PLC0415
    return {rid: rn.montar(rid, RAIZ, hoje=HOJE,
                           params=ba.params_farol_web(rid, 2026, 11))
            for rid, _ in TRES}


@pytest.fixture
def tela(monkeypatch):
    """Monta a VistaTabela de verdade com o Tk de mentira; devolve
    (vista, botões criados, avisos do messagebox, Edicao abertas,
    DialogoGarantia abertos)."""
    avisos, edicoes, dialogos = [], [], []
    ttk_falso = _mod_tk("ttk_falso")
    ttk_falso.Button = _Botao
    monkeypatch.setattr(br, "tk", _mod_tk("tk_falso"))
    monkeypatch.setattr(br, "ttk", ttk_falso)
    monkeypatch.setattr(br, "caixa_de_filtro", _Coringa)
    monkeypatch.setattr(br.bv, "Tabela", _Tabela)
    monkeypatch.setattr(br.VistaTabela, "aplicar", lambda self, **k: None)
    monkeypatch.setattr(br.messagebox, "showinfo",
                        lambda titulo, msg, **k: avisos.append((titulo, msg)))
    monkeypatch.setattr(br, "Edicao", lambda *a, **k: edicoes.append(a))
    monkeypatch.setattr(br, "DialogoGarantia",
                        lambda *a, **k: dialogos.append(a))

    def _ver(rid, rel_pc, titulo):
        _Botao.criados = []
        t = next(t_ for t_ in rel_pc["tabelas"] if t_["titulo"] == titulo)
        janela = types.SimpleNamespace(
            gerais=[], gerais_escolha={}, nomes_params=[],
            _filtros_guardados=None, rel=dict(rel_pc, id=rid))
        v = br.VistaTabela(_Coringa(), t, janela)
        return v, list(_Botao.criados), avisos, edicoes, dialogos
    return _ver


# ================================================ os 3 lugares no EDICAO_SO_WEB
def test_RN_GER_012_mensagem_do_pc_so_leitura():
    assert br.MSG_EDICAO_SO_WEB == MSG


@so_no_codigo_novo
def test_RN_GER_012_os_3_lugares_do_pos_venda_no_edicao_so_web():
    assert set(TRES) <= br.EDICAO_SO_WEB
    # os da T-0021 continuam
    assert {("pv_pedidos", "Pedidos"), ("pl_entregas", "Entregas")} \
        <= br.EDICAO_SO_WEB


@so_no_codigo_novo
def test_RN_GER_012_toda_aba_editavel_dos_3_farois_esta_no_edicao_so_web(pcs):
    """O id e o título batem com o núcleo: nenhuma aba com `edicao` desses 3
    faróis escapa do bloqueio (um título diferente deixaria editar)."""
    for rid, titulo in TRES:
        editaveis = {t["titulo"] for t in pcs[rid]["tabelas"]
                     if t.get("edicao")}
        assert editaveis == {titulo}, rid
        assert all((rid, x) in br.EDICAO_SO_WEB for x in editaveis)
        # e nenhuma deixa acrescentar linha no PC (o botão "Novo")
        assert not any((t.get("edicao") or {}).get("novo")
                       for t in pcs[rid]["tabelas"]), rid


@so_no_codigo_novo
@pytest.mark.parametrize("rid, titulo", TRES)
def test_RN_GER_012_editar_mostra_o_aviso_e_nao_abre_a_edicao(
        monkeypatch, rid, titulo):
    avisos, abertas = [], []
    monkeypatch.setattr(br.messagebox, "showinfo",
                        lambda titulo_, msg, **k: avisos.append(msg))
    monkeypatch.setattr(br, "Edicao", lambda *a, **k: abertas.append(a))
    vista = types.SimpleNamespace(
        janela=types.SimpleNamespace(rel={"id": rid}),
        t={"titulo": titulo, "edicao": {"chave": 0, "campos": []}})
    br.VistaTabela.editar(vista, ["CHAVE FICTICIA"])
    assert avisos == [MSG] and abertas == []


@so_no_codigo_novo
@pytest.mark.parametrize("rid, titulo", TRES[:2])
def test_RN_GER_012_duplo_clique_na_ncc_e_nas_devolucoes_so_avisa(
        tela, pcs, rid, titulo):
    """Na tela de verdade: o duplo clique da aba cai no editar, que avisa."""
    v, botoes, avisos, edicoes, _dial = tela(rid, pcs[rid], titulo)
    assert v.tab.ao_duplo_clique == v.editar
    assert not any(b.text == "Novo" for b in botoes)
    v.tab.ao_duplo_clique(["CHAVE FICTICIA"])
    assert avisos == [("Editar", MSG)] and edicoes == []


@so_no_codigo_novo
def test_RN_GER_012_nova_garantia_so_avisa(tela, pcs):
    v, botoes, avisos, edicoes, dialogos = tela(
        "pl_garantias", pcs["pl_garantias"], "Garantias")
    nova = [b for b in botoes if b.text == "Nova garantia"]
    assert len(nova) == 1
    nova[0].command()
    assert avisos == [("Nova garantia", MSG)]
    assert dialogos == [] and edicoes == []
    # o caminho antigo (abrir_garantia sem linha = garantia nova) não abre
    v.abrir_garantia(None)
    assert dialogos == []


@so_no_codigo_novo
def test_RN_GER_012_duplo_clique_na_garantia_abre_so_o_contato(tela, pcs):
    """O duplo clique abre o DialogoGarantia (o contato), não a Edicao."""
    v, _b, avisos, edicoes, dialogos = tela(
        "pl_garantias", pcs["pl_garantias"], "Garantias")
    assert v.tab.ao_duplo_clique == v.abrir_garantia
    t = v.t
    linha = list(t["linhas"][0]) if t["linhas"] else [""] * (
        t["garantia"]["i_ticket"] + 1)
    v.tab.ao_duplo_clique(linha)
    assert len(dialogos) == 1 and edicoes == [] and avisos == []
    assert dialogos[0][2] == linha[t["garantia"]["i_ticket"]]


# ================================================ Salvar contato
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _diarios_ficticios(raiz: Path):
    """Uma garantia fictícia no diário e um diário fictício de NCC e de
    edições do pós-venda (só para o sha antes = depois)."""
    gm.gravar(raiz, "G-9001", {
        "dt_solicitacao": "03/11/2026", "cod_cliente": "900001",
        "cliente": "CLIENTE FICTICIO", "cod_produto": "PROD-FICT",
        "descricao": "PRODUTO FICTICIO", "qtd": "1",
        "contato_nome": "CONTATO FICTICIO", "contato_fone": "(00) 00000-0001",
        "status": "EM TRATATIVA", "resultado": "PENDENTE",
        "reclamacao": "reclamação fictícia", "observacao": "obs fictícia",
        "cli_cidade": "CIDADE FICTICIA"},
        agora=datetime(2026, 11, 3, 9))
    outros = []
    for sub, nome, txt in (
            ("_NCC", "NCC_PC_FICTICIO.csv",
             "quando;maquina;chave;campo;valor\n"
             "2026-11-03 09:00:00;PC_FICTICIO;NCC-FICT;status;ABERTA\n"),
            ("_EDICOES_POS_VENDA", "EDICOES_PC_FICTICIO.csv",
             "quando;maquina;chave;campo;valor\n"
             "2026-11-03 09:00:00;PC_FICTICIO;DEV-FICT;etapa;RECEBIDA\n")):
        p = raiz / "RELATORIOS" / sub / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
        outros.append(p)
    # o diário desta máquina: é nele que o salvar acrescenta
    return gm.pasta(raiz) / f"GARANTIAS_{gm.maquina()}.csv", outros


class _Texto:
    """tk.Text sem Tk."""

    def __init__(self, v):
        self.v = v

    def get(self, *a):
        return self.v


@so_no_codigo_novo
def test_RN_GER_012_salvar_contato_grava_so_o_contato(tmp_path, monkeypatch):
    diario, outros = _diarios_ficticios(tmp_path)
    antes = gm.ler(tmp_path)["G-9001"]
    bytes_antes = diario.read_bytes()
    n_antes = len(bytes_antes.splitlines())
    sha_outros = {p: _sha(p) for p in outros}
    monkeypatch.setattr(br, "AQUI", tmp_path)

    # a janela como a assistente deixou: o telefone novo e, se algum campo
    # fora do contato tivesse sido mexido, o valor mexido
    dg = br.DialogoGarantia.__new__(br.DialogoGarantia)
    vals = {c: antes.get(c, "") for c, _r, _t in br.DialogoGarantia.CAMPOS}
    vals.update(cod_cliente="900002", cliente="OUTRO CLIENTE FICTICIO",
                status="FINALIZADA", resultado="PROCEDENTE",
                ticket="G-9999", dt_prazo="31/12/2026", qtd="7",
                contato_fone="(00) 00000-0002")
    dg.vars = {c: _Var(value=v) for c, v in vals.items()}
    dg.vars_cli = {"cli_cidade": _Var(value="OUTRA CIDADE FICTICIA")}
    dg.textos = {c: _Texto("texto mexido") for c, _r in
                 br.DialogoGarantia.TEXTOS}
    dg.ticket, dg.novo = "G-9001", False
    dg.g = {"dados": lambda tk_: {"g": gm.ler(tmp_path).get(tk_, {})},
            "cliente_base": lambda cod: {}, "produto": lambda cod: ""}
    dg.base = {"_cod": "900001"}
    rotulos, recargas = [], []
    dg.lbl = types.SimpleNamespace(
        configure=lambda **k: rotulos.append(k.get("text")))
    dg.lbl_cli = types.SimpleNamespace(configure=lambda **k: None)
    dg.cab = types.SimpleNamespace(lbl_titulo=dg.lbl_cli)
    dg.janela = types.SimpleNamespace(carregar=lambda: recargas.append(1))
    monkeypatch.setattr(br.messagebox, "showerror",
                        lambda *a, **k: pytest.fail(f"erro na tela: {a}"))

    dg.salvar()

    assert tuple(br.DialogoGarantia.CAMPOS_PC) == CONTATO
    # só acrescenta: o arquivo de antes fica igual, byte a byte, no começo
    depois = diario.read_bytes()
    assert depois.startswith(bytes_antes)
    assert len(depois.splitlines()) == n_antes + 1          # +1 linha
    assert [p.name for p in gm.pasta(tmp_path).iterdir()] == [diario.name]
    agora = gm.ler(tmp_path)
    assert set(agora) == {"G-9001"}                 # o ticket não trocou
    g = agora["G-9001"]
    assert g["contato_fone"] == "(00) 00000-0002"
    assert g["contato_nome"] == antes["contato_nome"]
    for c in gm.CAMPOS:
        if c not in CONTATO:
            assert g.get(c, "") == antes.get(c, ""), c
    # NCC e edições do pós-venda: sha antes = sha depois
    assert {p: _sha(p) for p in outros} == sha_outros
    assert rotulos == ["Salvo · 1 campo(s) alterado(s)"] and recargas == [1]


@so_no_codigo_novo
def test_RN_GER_012_salvar_contato_sem_mudanca_nao_grava(tmp_path,
                                                         monkeypatch):
    diario, _outros = _diarios_ficticios(tmp_path)
    sha = _sha(diario)
    monkeypatch.setattr(br, "AQUI", tmp_path)
    antes = gm.ler(tmp_path)["G-9001"]
    dg = br.DialogoGarantia.__new__(br.DialogoGarantia)
    dg.vars = {c: _Var(value=antes.get(c, "")) for c in CONTATO}
    dg.vars["status"] = _Var(value="CANCELADA")          # fora do contato
    dg.ticket = "G-9001"
    dg.lbl = types.SimpleNamespace(configure=lambda **k: None)
    dg.janela = types.SimpleNamespace(carregar=lambda: None)
    dg.salvar()
    assert _sha(diario) == sha
