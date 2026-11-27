"""T-0054: quem edita o Farol de Entregas (e as "Notas com frete" do Fretes) no site.

Regras (docs/produto/03-regras.md):
- RN-POS-011 · Nas abas Entregas e Pendências dos meses anteriores do Farol de Entregas editam o admin e
  o pós-venda; os outros perfis veem sem editar (o gerente não edita, P1 A do R-20261127-103925-alexandre).
  O robô confere o perfil e grava com `pos_venda.gravar_edicoes`, só acrescentando no diário
  `_EDICOES_POS_VENDA` (regra 7). O mesmo vale para "Notas com frete" do Fretes (RN-POS-010, P2 A).
  A linha nova e os outros faróis seguem só do admin (RN-GER-012).
- Contrato `.coord/contratos/relatorio.md` §10.9.7: a mesma tabela na web (`edicoes.EDITA_LUGAR`) e no
  robô (`bap_automation.EDITA_LUGAR_WEB`); registro com `perfil` fora dela vai a `erro` com
  `MOTIVO_PERFIL_WEB`; registro sem `perfil` (fila de antes da T-0054) segue aceito; o
  `APLICADAS_WEB_<máquina>.jsonl` ganha `perfil_web`.

Condicionais: o lado do robô pula sem `ba.EDITA_LUGAR_WEB` e o da web pula sem `edicoes.pode_editar`
(a web e o robô entram em qualquer ordem). Dados só fictícios; tudo em pasta temporária.
"""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba
import pos_venda as pv

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
CONTRATO_MD = RAIZ / ".coord" / "contratos" / "relatorio.md"

# §10.9.7 (tabela do contrato) + a linha do Fretes (RN-POS-010, P2 A do R-20261127-103925-alexandre)
CONTRATO = {
    ("pl_entregas", "Entregas"): ("admin", "pos_venda"),
    ("pl_entregas", "Pendências dos meses anteriores"): ("admin", "pos_venda"),
    ("pl_fretes", "Notas com frete"): ("admin", "pos_venda"),
}
LINHA_FRETES = ("pl_fretes", "Notas com frete")
PERFIS = ("admin", "diretor", "gerente", "analista", "trade", "pos_venda", "pre_venda", "vendas")
SEM_EDICAO = ("gerente", "analista", "diretor", "vendas", "pre_venda", "trade")
LUGARES_ENTREGAS = (("pl_entregas", "Entregas"), ("pl_entregas", "Pendências dos meses anteriores"))
OUTROS_FAROIS = (("pv_pedidos", "Pedidos", "autorizacoes"), ("pl_devolucoes", "Devoluções", "pos_venda"),
                 ("pl_ncc", "NCC pendentes", "ncc"), ("pl_garantias", "Garantias", "garantias"))
TOKEN = "token-ficticio-t0054"
BASE = "https://web.exemplo.test"
CHAVE = "FILIAL TESTE|900501|1"
OPCOES = {"por": {"PRICE"}, "etapa": set(pv.ETAPAS_ENTREGA),
          "transportadora": {"TRANSPORTADORA TESTE 1"}}
VALORES_OK = {"etapa": "ENTREGUE", "entregue_em": "23/11/2026", "responsavel": "MOTORISTA TESTE",
              "transportadora": "TRANSPORTADORA TESTE 1"}
_SEM = object()


# ------------------------------------------------------------------ travas
def _robo():
    if not hasattr(ba, "EDITA_LUGAR_WEB") or not hasattr(ba, "MOTIVO_PERFIL_WEB"):
        pytest.skip("robô sem ba.EDITA_LUGAR_WEB (modulo-robo T-0054 fora do main)")
    return ba


@pytest.fixture
def edicoes_web():
    """`web/app/edicoes.py` importado da web desta árvore; o `app` de fora volta como estava depois."""
    if not (WEB / "app" / "edicoes.py").exists():
        pytest.skip("sem web/app/edicoes.py")
    antes = {m: sys.modules[m] for m in list(sys.modules) if m == "app" or m.startswith("app.")}
    for m in antes:
        del sys.modules[m]
    sys.path.insert(0, str(WEB))
    try:
        from app import edicoes                               # noqa: PLC0415
        if not hasattr(edicoes, "pode_editar") or not hasattr(edicoes, "EDITA_LUGAR"):
            pytest.skip("web sem edicoes.pode_editar (modulo-web T-0054 fora do main)")
        yield edicoes
    finally:
        sys.path.remove(str(WEB))
        for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
            del sys.modules[m]
        sys.modules.update(antes)


def _norm(tab):
    return {(str(r), str(t)): tuple(sorted(ps)) for (r, t), ps in tab.items()}


def _tabela_do_contrato():
    """As linhas da tabela do §10.9.7 no contrato desta árvore ({} se o §10.9.7 ainda não entrou)."""
    txt = CONTRATO_MD.read_text(encoding="utf-8") if CONTRATO_MD.exists() else ""
    m = re.search(r"^#### 10\.9\.7 .*?(?=^#{2,4} )", txt, re.M | re.S)
    if not m:
        return {}
    saida = {}
    for r, t, ps in re.findall(r'^\| `\("([^"]+)", "([^"]+)"\)` \| (.+?) \|$', m.group(0), re.M):
        saida[(r, t)] = tuple(sorted(re.findall(r"`([a-z_]+)`", ps)))
    return saida


def _reg(seq=1, perfil=_SEM, rid="pl_entregas", tabela="Entregas", modulo="pos_venda", valores=None,
         chave=CHAVE):
    r = {"tipo": "edicao", "seq": seq, "id": f"id-t54-{seq}", "quando": "2026-11-27 09:00:00",
         "usuario": "usuario.teste", "rid": rid, "tabela": tabela, "modulo": modulo, "chave": chave,
         "valores": dict(VALORES_OK) if valores is None else valores, "antes": {}, "status": "pendente"}
    if perfil is not _SEM:
        r["perfil"] = perfil
    return r


# ------------------------------------------------------------------ 1. a tabela: web = robô = contrato
def test_RN_POS_011_tabela_web_igual_robo_igual_contrato(edicoes_web):
    """§10.9.7: `edicoes.EDITA_LUGAR` (web) == `ba.EDITA_LUGAR_WEB` (robô) == o contrato (com o Fretes)."""
    robo = _robo()
    assert _norm(edicoes_web.EDITA_LUGAR) == _norm(robo.EDITA_LUGAR_WEB) == _norm(CONTRATO)
    assert tuple(edicoes_web.EDITA) == ("admin",)             # padrão fora da tabela (RN-GER-012)


def test_RN_POS_011_tabela_do_robo_igual_contrato():
    """O robô sozinho (web velha): a tabela é a do contrato e o motivo é a frase fixa do §10.9.7."""
    robo = _robo()
    assert _norm(robo.EDITA_LUGAR_WEB) == _norm(CONTRATO)
    assert robo.MOTIVO_PERFIL_WEB == "perfil sem edição neste farol"
    # só lugares que o robô já grava, mais o Fretes (entra com a T-0037; antes disso, recusado pelo lugar)
    assert set(robo.EDITA_LUGAR_WEB) - set(robo.EDICOES_WEB) <= {LINHA_FRETES}


def test_RN_POS_011_tabela_da_web_igual_contrato_e_pode_editar(edicoes_web):
    """A web sozinha (robô velho): a tabela é a do contrato e `pode_editar` é a única pergunta."""
    assert _norm(edicoes_web.EDITA_LUGAR) == _norm(CONTRATO)
    lugares = list(CONTRATO) + [(r, t) for r, t, _m in OUTROS_FAROIS] + [("pl_entregas", "Aba que não existe")]
    for lugar in lugares:
        for p in PERFIS:
            esperado = p in CONTRATO.get(lugar, ("admin",))
            assert edicoes_web.pode_editar(p, lugar) is esperado, (p, lugar)
    for p in SEM_EDICAO:                                       # o gerente (e os outros) não editam
        assert not any(edicoes_web.pode_editar(p, lg) for lg in CONTRATO), p


def test_RN_POS_011_contrato_na_arvore_bate_com_a_tabela_do_teste():
    """Quando o §10.9.7 estiver no contrato desta árvore, a tabela dele é a daqui; só a linha do Fretes
    pode faltar lá (acrescentada pelo P2 A depois do desenho)."""
    doc = _tabela_do_contrato()
    if not doc:
        pytest.skip("contrato sem o §10.9.7 nesta árvore (engenheiro-software T-0054 fora do main)")
    for lugar, ps in doc.items():
        assert _norm({lugar: CONTRATO.get(lugar, ())}) == {lugar: ps}, lugar
    assert set(CONTRATO) - set(doc) <= {LINHA_FRETES}


# ------------------------------------------------------------------ 2. robô: recusa de perfil
@pytest.mark.parametrize("perfil", SEM_EDICAO)
@pytest.mark.parametrize("lugar", LUGARES_ENTREGAS)
def test_RN_POS_011_robo_recusa_perfil_fora(perfil, lugar):
    robo = _robo()
    reg = _reg(perfil=perfil, rid=lugar[0], tabela=lugar[1])
    assert robo.validar_edicao_web(reg, OPCOES) == robo.MOTIVO_PERFIL_WEB
    gravou = []
    st = robo.aplicar_edicao_web(Path("/nao/usado"), reg, OPCOES, lambda *a: gravou.append(a) or 1)
    assert st == ("erro", robo.MOTIVO_PERFIL_WEB) and gravou == []       # nada é gravado


@pytest.mark.parametrize("rid, tabela, modulo", OUTROS_FAROIS)
def test_RN_POS_011_robo_recusa_pos_venda_fora_das_entregas(rid, tabela, modulo):
    """Os outros faróis seguem só do admin: o pós-venda em Pedidos, Devoluções, NCC e Garantias é recusado."""
    robo = _robo()
    reg = _reg(perfil="pos_venda", rid=rid, tabela=tabela, modulo=modulo, valores={"x": "1"})
    assert robo.validar_edicao_web(reg, OPCOES) == robo.MOTIVO_PERFIL_WEB
    gravou = []
    assert robo.aplicar_edicao_web(Path("/nao/usado"), reg, OPCOES,
                                   lambda *a: gravou.append(a) or 1) == ("erro", robo.MOTIVO_PERFIL_WEB)
    assert gravou == []


def test_RN_POS_011_robo_recusa_linha_nova_do_pos_venda():
    """A linha nova (§10.9.2, só a Garantia) segue só do admin."""
    robo = _robo()
    reg = _reg(perfil="pos_venda", rid="pl_garantias", tabela="Garantias", modulo="garantias",
               valores={"x": "1"}, chave="NOVO-0000t054")
    reg["novo"] = True
    assert robo.validar_edicao_web(reg, OPCOES) == robo.MOTIVO_PERFIL_WEB


# ------------------------------------------------------------------ 3. robô: aceita admin e pós-venda
@pytest.mark.parametrize("perfil", ("admin", "pos_venda"))
@pytest.mark.parametrize("lugar", LUGARES_ENTREGAS)
def test_RN_POS_011_aceita_admin_e_pos_venda(perfil, lugar):
    robo = _robo()
    reg = _reg(perfil=perfil, rid=lugar[0], tabela=lugar[1])
    assert robo.validar_edicao_web(reg, OPCOES) == ""
    gravou = []
    st = robo.aplicar_edicao_web(Path("/nao/usado"), reg, OPCOES, lambda *a: gravou.append(a) or 1)
    assert st == ("aplicada", "")
    ((_raiz, modulo, arquivo, aba, edicoes),) = gravou
    assert (modulo, aba) == ("pos_venda", pv.ABA_ENT) and arquivo.endswith(pv.ARQUIVO)
    assert list(edicoes) == [CHAVE]


def test_RN_POS_011_admin_igual_sem_perfil_em_todo_lugar():
    """O perfil `admin` não muda nada em lugar nenhum: o resultado é o mesmo do registro sem perfil."""
    robo = _robo()
    for (rid, tabela), lug in robo.EDICOES_WEB.items():
        for valores in (dict(VALORES_OK), {"por": "PRICE"}, {}):
            sem = _reg(rid=rid, tabela=tabela, modulo=lug["modulo"], valores=valores)
            com = _reg(perfil="admin", rid=rid, tabela=tabela, modulo=lug["modulo"], valores=valores)
            assert robo.validar_edicao_web(com, OPCOES) == robo.validar_edicao_web(sem, OPCOES), (rid, tabela)


def test_RN_POS_011_fretes_sem_lugar_no_robo_continua_recusado_pelo_lugar():
    """Enquanto o Fretes (T-0037) não estiver em `EDICOES_WEB`, a linha da tabela não abre nada."""
    robo = _robo()
    if LINHA_FRETES in robo.EDICOES_WEB:
        pytest.skip("o Fretes já está em EDICOES_WEB (T-0037 no robô)")
    for p in ("admin", "pos_venda", "gerente"):
        reg = _reg(perfil=p, rid=LINHA_FRETES[0], tabela=LINHA_FRETES[1])
        assert robo.validar_edicao_web(reg, OPCOES) == robo.MOTIVO_LUGAR_WEB


# ------------------------------------------------------------------ 4. a fila antiga e o perfil torto
@pytest.mark.parametrize("lugar", LUGARES_ENTREGAS)
def test_RN_POS_011_aceita_registro_sem_perfil(lugar):
    """§10.9.7: a fila de antes da T-0054 (sem `perfil`) continua aceita; `perfil` que não é um perfil
    (não string, vazio, maiúsculo) é recusado."""
    robo = _robo()
    assert robo.validar_edicao_web(_reg(rid=lugar[0], tabela=lugar[1]), OPCOES) == ""
    for torto in (None, 1, 0, True, ["admin"], ("admin",), {"perfil": "admin"}, "", "ADMIN", " admin",
                  "pos-venda", "pós_venda"):
        reg = _reg(perfil=torto, rid=lugar[0], tabela=lugar[1])
        assert robo.validar_edicao_web(reg, OPCOES) == robo.MOTIVO_PERFIL_WEB, repr(torto)


# ------------------------------------------------------------------ 5. o APLICADAS_WEB ganha perfil_web
class _Site:
    def __init__(self, linhas):
        self.linhas, self.confirmados = linhas, []

    def get(self, url, params=None, headers=None, timeout=None):
        ls = [x for x in self.linhas if x["seq"] > params["desde"]]
        return SimpleNamespace(status_code=200, json=lambda: {
            "epoca": "ep-t54", "linhas": ls, "ate_seq": ls[-1]["seq"] if ls else params["desde"], "mais": False})

    def post(self, url, json=None, headers=None, timeout=None):
        self.confirmados.append(json)
        return SimpleNamespace(status_code=200)


def test_RN_POS_011_perfil_web_no_aplicadas(tmp_path, monkeypatch):
    robo = _robo()
    monkeypatch.setenv("COMPUTERNAME", "MAQUINA-TESTE-T54")
    site = _Site([_reg(1, perfil="pos_venda"), _reg(2, perfil="gerente"), _reg(3),
                  _reg(4, perfil="admin", tabela="Pendências dos meses anteriores")])
    gravou, logs = [], []
    r = robo.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, logs.append,
                                     lambda *a: gravou.append(a) or 1, OPCOES)
    assert r == {"aplicadas": 3, "erros": 1, "pendentes": 0, "confirmado": True}
    assert len(gravou) == 3                                   # a do gerente não grava
    (conf,) = site.confirmados
    assert [(x["seq"], x["status"], x["motivo"]) for x in conf["resultados"]] == [
        (1, "aplicada", ""), (2, "erro", robo.MOTIVO_PERFIL_WEB), (3, "aplicada", ""), (4, "aplicada", "")]
    arq = tmp_path / robo.PASTA_EDICOES_WEB / "APLICADAS_WEB_MAQUINA-TESTE-T54.jsonl"
    regs = [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines()]
    assert [(x["seq"], x.get("perfil_web", "—"), x["status"]) for x in regs] == [
        (1, "pos_venda", "aplicada"), (2, "gerente", "erro"), (3, "—", "aplicada"), (4, "admin", "aplicada")]
    assert all("perfil" not in x for x in regs)               # a chave é `perfil_web`, não `perfil`
    assert not any(TOKEN in m or "MOTORISTA TESTE" in m or "900501" in m for m in logs)


# ------------------------------------------------------------------ 6. grava só acrescentando (regra 7)
def _xlsx_ficticia(raiz):
    arq = raiz / "RELATORIOS" / pv.ARQUIVO
    arq.parent.mkdir(parents=True)
    wb = pv.criar_arquivo()
    nomes = [c[1] for c in pv.COLUNAS_DA_ABA[pv.ABA_ENT]]
    ws = wb[pv.ABA_ENT]
    for i, (chave, cliente) in enumerate(((CHAVE, "CLIENTE TESTE 01"), ("FILIAL TESTE|900502|1", "CLIENTE TESTE 02"))):
        ws.cell(pv.PRIMEIRA + i, nomes.index("chave") + 1, chave)
        ws.cell(pv.PRIMEIRA + i, nomes.index("etapa") + 1, "EM TRÂNSITO")
        if "cliente" in nomes:
            ws.cell(pv.PRIMEIRA + i, nomes.index("cliente") + 1, cliente)
    wb.save(arq)
    return arq


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_RN_POS_011_grava_so_acrescentando(tmp_path, monkeypatch):
    """Máquina que não é a `MAQUINA_DO_POS_VENDA`: a edição do pós-venda vai só ao diário
    `_EDICOES_POS_VENDA` (N linhas a mais, as de antes byte a byte iguais) e a xlsx não muda."""
    robo = _robo()
    monkeypatch.setenv("COMPUTERNAME", "MAQUINA-TESTE-T54")
    assert pv.MAQUINA_DO_POS_VENDA and pv.maquina() != pv.MAQUINA_DO_POS_VENDA.strip().upper()
    assert not pv.pode_gravar_aqui()
    xlsx = _xlsx_ficticia(tmp_path)
    sha_xlsx = _sha(xlsx)
    diario = tmp_path / "RELATORIOS" / pv.PASTA_DIARIO / f"EDICOES_{pv.maquina()}.csv"

    # uma edição de antes (fila antiga, sem perfil): o diário nasce com cabeçalho + 1 linha
    assert robo.aplicar_edicao_web(tmp_path, _reg(1, valores={"etapa": "EM TRÂNSITO"}), OPCOES) == ("aplicada", "")
    antes = diario.read_bytes()
    n_antes = len(antes.splitlines())
    assert n_antes == 2

    # o pós-venda edita 4 campos: 4 linhas a mais, só acrescentadas
    assert robo.aplicar_edicao_web(tmp_path, _reg(2, perfil="pos_venda"), OPCOES) == ("aplicada", "")
    depois = diario.read_bytes()
    assert depois.startswith(antes)
    assert len(depois.splitlines()) == n_antes + len(VALORES_OK)
    with open(diario, encoding="utf-8-sig", newline="") as f:
        novas = list(csv.reader(f, delimiter=";"))[n_antes:]
    assert {(ln[1], ln[3], ln[4], ln[5]) for ln in novas} == {
        ("MAQUINA-TESTE-T54", pv.ABA_ENT, CHAVE, c) for c in VALORES_OK}
    assert {ln[5]: ln[6] for ln in novas}["entregue_em"] == "2026-11-23"

    # o gerente é recusado: nem uma linha a mais
    assert robo.aplicar_edicao_web(tmp_path, _reg(3, perfil="gerente"), OPCOES) == (
        "erro", robo.MOTIVO_PERFIL_WEB)
    assert diario.read_bytes() == depois

    assert _sha(xlsx) == sha_xlsx                             # a planilha não muda (regra 7)
    assert sorted(p.name for p in diario.parent.iterdir()) == [diario.name]   # só o diário desta máquina
