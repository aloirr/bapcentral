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
DialogoGarantia.salvar) com um Tk de mentira, sem janela; o __init__ do
DialogoGarantia também com o Tk real (pula sem tela). Nenhum teste lê nem
grava a pasta RELATORIOS/ real de diários: os diários são fictícios, em
tmp_path. As bases congeladas só entram pelo `montar` (leitura).
"""
import sys
import types
from datetime import date
from pathlib import Path

import pytest

import garantias as gm
import relatorios_nucleo as rn
from garantias_ficticias import (CONTATO, QUANDO, TICKET, diario_ficticio,
                                 linhas_novas, sha)

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
MSG = "A edição agora é só pela BAP Central web."
# (rid, título da aba): os 3 lugares que ficam só leitura no PC
TRES = (("pl_ncc", "NCC pendentes"), ("pl_devolucoes", "Devoluções"),
        ("pl_garantias", "Garantias"))


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
        # o "from tkinter import messagebox" pega o atributo do pai: sem isto
        # viria o _Coringa (classe) e o monkeypatch do showinfo não pegaria
        for nome in falsos[1:]:
            setattr(sys.modules["tkinter"], nome.split(".")[1],
                    sys.modules[nome])
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

    def __init__(self, *a, text="", command=None, style=None, **k):
        self.text, self.command, self.style = text, command, style
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
    nova = [b for b in botoes if b.text.startswith("Nova garantia")]
    # o botão diz onde se faz ("na web") e é neutro (sem o verde de ação)
    assert [b.text for b in nova] == ["Nova garantia (na web)"]
    assert nova[0].style is None
    nova[0].command()
    assert avisos == [("Nova garantia", MSG)]
    assert dialogos == [] and edicoes == []


@so_no_codigo_novo
def test_RN_GER_012_duplo_clique_na_garantia_abre_o_detalhe_so_leitura(
        tela, pcs):
    """O duplo clique abre o DialogoGarantia (só leitura, fora o contato),
    não a Edicao."""
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
def _diarios_ficticios(raiz: Path):
    """Uma garantia fictícia no diário e um diário fictício de NCC e de
    edições do pós-venda (só para o sha antes = depois)."""
    gm.gravar(raiz, TICKET, {
        "dt_solicitacao": "03/11/2026", "cod_cliente": "900001",
        "cliente": "CLIENTE FICTICIO", "cod_produto": "PROD-FICT",
        "descricao": "PRODUTO FICTICIO", "qtd": "1",
        "contato_nome": "CONTATO FICTICIO", "contato_fone": "(00) 00000-0001",
        "status": "EM TRATATIVA", "resultado": "PENDENTE",
        "reclamacao": "reclamação fictícia", "observacao": "obs fictícia",
        "cli_cidade": "CIDADE FICTICIA"},
        agora=QUANDO)
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


@so_no_codigo_novo
def test_RN_GER_012_salvar_contato_grava_so_o_contato(tmp_path, monkeypatch):
    diario, outros = _diarios_ficticios(tmp_path)
    antes = gm.ler(tmp_path)[TICKET]
    bytes_antes = diario.read_bytes()
    n_antes = len(bytes_antes.splitlines())
    sha_outros = {p: sha(p.read_bytes()) for p in outros}
    monkeypatch.setattr(br, "AQUI", tmp_path)

    # a janela como a assistente deixou: o telefone novo e, se algum campo
    # fora do contato tivesse sido mexido, o valor mexido
    dg = br.DialogoGarantia.__new__(br.DialogoGarantia)
    vals = {c: antes.get(c, "") for c, *_ in br.DialogoGarantia.CAMPOS}
    vals.update(cod_cliente="900002", cliente="OUTRO CLIENTE FICTICIO",
                status="FINALIZADA", resultado="PROCEDENTE",
                ticket="G-9999", dt_prazo="31/12/2026", qtd="7",
                contato_fone="(00) 00000-0002")
    dg.vars = {c: _Var(value=v) for c, v in vals.items()}
    dg.ticket = TICKET
    rotulos, recargas = [], []
    dg.lbl = types.SimpleNamespace(
        configure=lambda **k: rotulos.append(k.get("text")))
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
    assert set(agora) == {TICKET}                 # o ticket não trocou
    g = agora[TICKET]
    assert g["contato_fone"] == "(00) 00000-0002"
    assert g["contato_nome"] == antes["contato_nome"]
    for c in gm.CAMPOS:
        if c not in CONTATO:
            assert g.get(c, "") == antes.get(c, ""), c
    # NCC e edições do pós-venda: sha antes = sha depois
    assert {p: sha(p.read_bytes()) for p in outros} == sha_outros
    assert rotulos == ["Salvo · 1 campo(s) alterado(s)"] and recargas == [1]


@so_no_codigo_novo
def test_RN_GER_012_salvar_contato_sem_mudanca_nao_grava(tmp_path,
                                                         monkeypatch):
    diario, _outros = _diarios_ficticios(tmp_path)
    sha_antes = sha(diario.read_bytes())
    monkeypatch.setattr(br, "AQUI", tmp_path)
    antes = gm.ler(tmp_path)[TICKET]
    dg = br.DialogoGarantia.__new__(br.DialogoGarantia)
    dg.vars = {c: _Var(value=antes.get(c, "")) for c in CONTATO}
    dg.vars["status"] = _Var(value="CANCELADA")          # fora do contato
    dg.ticket = TICKET
    rotulos, recargas = [], []
    dg.lbl = types.SimpleNamespace(
        configure=lambda **k: rotulos.append(k.get("text")))
    dg.janela = types.SimpleNamespace(carregar=lambda: recargas.append(1))
    dg.salvar()
    assert sha(diario.read_bytes()) == sha_antes
    # sem mudança: avisa "Nada mudou" e não recarrega a janela
    assert rotulos == ["Nada mudou"] and recargas == []


@so_no_codigo_novo
def test_RN_GER_012_salvar_contato_nao_acrescenta_status_nem_fechamento(
        tmp_path, monkeypatch):
    """FINALIZADA sem dt_fechamento: o Salvar contato acrescenta só as 2
    linhas do contato (pelo gm.gravar ganharia a data de hoje); a dedução
    por status fica no teste do gravar_contato."""
    diario = diario_ficticio(tmp_path, "FINALIZADA")
    bytes_antes = diario.read_bytes()
    antes = gm.ler(tmp_path)[TICKET]
    assert antes["status"] == "FINALIZADA" and not antes.get("dt_fechamento")
    monkeypatch.setattr(br, "AQUI", tmp_path)

    dg = br.DialogoGarantia.__new__(br.DialogoGarantia)
    vals = {c: antes.get(c, "") for c, *_ in br.DialogoGarantia.CAMPOS}
    vals.update(contato_nome="OUTRO CONTATO FICTICIO",
                contato_fone="(00) 00000-0002")
    dg.vars = {c: _Var(value=v) for c, v in vals.items()}
    dg.ticket = TICKET
    rotulos = []
    dg.lbl = types.SimpleNamespace(
        configure=lambda **k: rotulos.append(k.get("text")))
    dg.janela = types.SimpleNamespace(carregar=lambda: None)
    monkeypatch.setattr(br.messagebox, "showerror",
                        lambda *a, **k: pytest.fail(f"erro na tela: {a}"))

    dg.salvar()

    novas = linhas_novas(bytes_antes, diario.read_bytes())
    assert sorted(r["campo"] for r in novas) == sorted(CONTATO)
    assert {r["ticket"] for r in novas} == {TICKET}
    g = gm.ler(tmp_path)[TICKET]
    assert g["contato_nome"] == "OUTRO CONTATO FICTICIO"
    assert g["contato_fone"] == "(00) 00000-0002"
    assert g["status"] == "FINALIZADA" and not g.get("dt_fechamento")
    for c in gm.CAMPOS:
        if c not in CONTATO:
            assert g.get(c, "") == antes.get(c, ""), c
    assert rotulos == ["Salvo · 2 campo(s) alterado(s)"]


# ================================== a janela da garantia com Tk de verdade
def _tk_real():
    """O tkinter de verdade com tela; senão pula com o motivo."""
    try:
        import tkinter as tk                            # noqa: PLC0415
        from tkinter import ttk                         # noqa: PLC0415
    except ImportError:
        pytest.skip("sem tkinter neste Python (rode com /usr/bin/python3.12 "
                    "e xvfb-run)")
    if br.tk is not tk:
        pytest.skip("o bap_relatorios foi importado com o Tk de mentira")
    try:
        raiz = tk.Tk()
    except tk.TclError as erro:
        pytest.skip(f"sem tela para o Tk ({erro}); rode com xvfb-run")
    raiz.withdraw()
    return tk, ttk, raiz


@so_no_codigo_novo
def test_RN_GER_012_janela_da_garantia_so_o_contato_editavel_tk_real(
        tmp_path, monkeypatch):
    """O __init__ do DialogoGarantia de verdade: Entry readonly (estilo
    Leitura.TEntry) em tudo, menos contato_nome e contato_fone (normal,
    Contato.TEntry, rótulo "✎ editável"); os textos disabled; sem
    Combobox; botão "Salvar contato" (sem "Salvar"); o aviso da web.
    O cadastro do cliente (Fantasia, Telefone, Cidade...) segue preenchido
    depois do gc.collect(): o StringVar sem referência some e o campo
    esvazia (regressão achada pelo revisor-ux no 456f033)."""
    import gc                                           # noqa: PLC0415
    tk, ttk, raiz = _tk_real()
    try:
        br.bv.aplicar_tema(raiz)
        _diarios_ficticios(tmp_path)
        monkeypatch.setattr(br, "AQUI", tmp_path)
        # base fictícia: todo campo do cadastro com valor
        base = {"_nome": "CLIENTE FICTICIO",
                **{k: f"{rotulo.upper()} FICTICIO"
                   for k, rotulo in gm.CAMPOS_CLIENTE}}
        g = {"dados": lambda tk_: {
                 "g": gm.ler(tmp_path).get(tk_, {}),
                 "base": base,
                 "situacao": gm.situacao(gm.ler(tmp_path).get(tk_, {}),
                                         HOJE)},
             "campos_cliente": list(gm.CAMPOS_CLIENTE)}
        dg = br.DialogoGarantia(raiz, g, TICKET)
        gc.collect()
        dg.update()

        def filhos(w):
            for c in w.winfo_children():
                yield c
                yield from filhos(c)
        ws = list(filhos(dg))
        nome_var = {str(v): k for k, v in dg.vars.items()}
        entradas = [w for w in ws if isinstance(w, (ttk.Entry, tk.Entry))]
        editaveis = {nome_var.get(str(w.cget("textvariable")), "?"): w
                     for w in entradas
                     if str(w.cget("state")) not in ("readonly", "disabled")}
        assert set(editaveis) == set(CONTATO)
        assert {str(w.cget("style")) for w in editaveis.values()} \
            == {"Contato.TEntry"}
        so_leitura = [w for w in entradas if w not in editaveis.values()]
        assert so_leitura and {str(w.cget("style")) for w in so_leitura} \
            == {"Leitura.TEntry"}
        # o ticket, o status e o cadastro do cliente estão entre os readonly
        lidos = {nome_var.get(str(w.cget("textvariable"))) for w in so_leitura}
        assert {"ticket", "status", "resultado", "cod_cliente",
                "cliente"} <= lidos
        # o cadastro do cliente: os Entry fora do self.vars (cli_*) e o
        # cód./nome; nenhum vazio depois do gc.collect()
        cadastro = [w for w in so_leitura
                    if str(w.cget("textvariable")) not in nome_var]
        assert len(cadastro) >= len(gm.CAMPOS_CLIENTE)
        vazios = [i for i, w in enumerate(cadastro) if not w.get().strip()]
        assert vazios == [], f"{len(vazios)} campo(s) do cadastro vazio(s)"
        for c in ("cod_cliente", "cliente"):
            w = next(w for w in so_leitura
                     if nome_var.get(str(w.cget("textvariable"))) == c)
            assert w.get().strip(), c
        textos = [w for w in ws if isinstance(w, tk.Text)]
        assert len(textos) == len(br.DialogoGarantia.TEXTOS)
        assert all(str(w.cget("state")) == "disabled" for w in textos)
        assert not any(isinstance(w, ttk.Combobox) for w in ws)
        botoes = {str(w.cget("text")) for w in ws
                  if isinstance(w, (ttk.Button, tk.Button))}
        assert "Salvar contato" in botoes and "Salvar" not in botoes
        rotulos = [str(w.cget("text")) for w in ws
                   if isinstance(w, (tk.Label, ttk.Label))]
        assert any(MSG in r for r in rotulos)
        assert sorted(r for r in rotulos if "✎ editável" in r) == sorted(
            ["Contato · nome ✎ editável", "Contato · telefone ✎ editável"])
        dg.destroy()
    finally:
        raiz.destroy()
