"""T-0054: o pós-venda edita o Farol de Entregas no site; o robô grava no PC, só acrescentando linha.

Regras (docs/produto/03-regras.md):
- RN-POS-011: no Farol de Entregas ("Entregas" e "Pendências dos meses anteriores") editam o `admin`
  e o `pos_venda`; os outros perfis não. Os 6 campos e as listas são os do PC. O robô grava pela
  `pos_venda.gravar_edicoes` e, no notebook do robô, isso é só acrescentar linha no diário.
- RN-POS-010: o "Notas com frete" do Farol de Fretes segue a mesma tabela de quem edita.
- RN-GER-018: provada no web/tests/test_T0054_entregas_edicao.py (farol liberado sem edição).
Contrato: `.coord/contratos/relatorio.md` §10.9.7. Desenho: `docs/desenho/T-0054.md`.

Complementa `web/tests/test_T0054_entregas_edicao.py` (do modulo-web), sem repetir o que ele prova:
- a tabela da web = a do robô = a do contrato (lida do §10.9.7);
- a matriz perfil × lugar igual na web (`pode_editar`) e no robô (`validar_edicao_web`); nos outros
  faróis o robô segue só do admin, e o `perfil` "admin" dá o mesmo resultado que a fila antiga;
- o `perfil` que não é um perfil (não texto, vazio, maiúsculo) recusado; o registro sem `perfil` aceito;
- os 6 campos do pacote que o ROBÔ monta, conferidos pela web com as janelas de data do PC;
- o laço web → robô → PC com a `edicoes.Fila` de verdade (só biblioteca padrão, roda no CI da raiz):
  o robô só acrescenta (diário, APLICADAS_WEB), recusa o perfil fora e aceita a fila antiga;
- dado pessoal no RESPONSÁVEL recusado nos dois lados, sem eco no motivo nem no log;
- com a web HTTP de verdade: o POST do pós-venda chega ao PC pelo robô (o 403 dos outros
  perfis fica no web/tests/test_T0054_entregas_edicao.py e na matriz `mesma_decisao` daqui).

Tudo em pasta temporária (tmp_path), nunca nas bases reais. Dados fictícios: "CLIENTE TESTE 01",
"MOTORISTA TESTE", NF 9001xx, filial "FILIAL TESTE". Sem pulo condicional próprio: a ordem do merge é
web → robô → testes. O teste HTTP usa o fixture web_mod da T-0035: só roda onde há FastAPI (local); é pulado
nos dois CIs (o da raiz não instala FastAPI e o da web só roda web/tests).
"""
import ast
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba
import pos_venda as pv
import relatorios_nucleo as rn
import transportadoras as tr
# transição T-0037: até o #169 (testes/T-0037-fretes)
from escopo_farois_web import fretes_no_robo

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
CONTRATO = RAIZ / ".coord" / "contratos" / "relatorio.md"
HOJE = date(2026, 11, 27)
ENT, PEND = ("pl_entregas", "Entregas"), ("pl_entregas", "Pendências dos meses anteriores")
FRETES = ("pl_fretes", "Notas com frete")
MAQ_ROBO = "ROBO-TESTE-54"
BASE_FALSA = "https://web.exemplo.test"
TOKEN_FALSO = "token-ficticio-t0054"
CAD = {"transportadoras": [{"nome": "TRANSPORTADORA TESTE 1", "ufs": ["AM"]},
                           {"nome": "TRANSPORTADORA TESTE 2", "ufs": ["PA"]}]}
OPCOES = {"por": set(rn.QUEM_AUTORIZA), "etapa": set(pv.ETAPAS_ENTREGA),
          "transportadora": set(tr.nomes(CAD)), "_hoje": HOJE}
NOMES = ["NF", "CLIENTE", "UF", "CIDADE", "VLR NF", "LOCAL/FRETE", "VLR FRETE", "ETAPA", "TRANSPORTADORA",
         "DT. PREVISTA", "DT. REAL", "RESPONSÁVEL", "VLR REAL FRETE"]
CH0, CH1 = "FILIAL TESTE|900101|1", "FILIAL TESTE|900102|1"
LINHAS = [["900101", "CLIENTE TESTE 01", "AM", "MANAUS", 1000.0, "FRETE", 50.0, "EM TRÂNSITO", "", None, None, "",
           None, CH0],
          ["900102", "CLIENTE TESTE 02", "PA", "BELÉM", 2000.0, "RETIRA", 0.0, "AGUARDANDO COLETA", "", None, None,
           "", None, CH1]]
PESSOAIS = ["MOTORISTA TESTE 123.456.789-09", "MOTORISTA TESTE 12.345.678/0001-90",
            "MOTORISTA TESTE (92) 99123-4567", "MOTORISTA TESTE motorista@exemplo.test"]


def _br(d):
    return f"{d:%d/%m/%Y}"


# ------------------------------------------------------------------ a web (só biblioteca padrão)
@pytest.fixture(scope="module")
def ed():
    """web/app/edicoes de verdade (sem FastAPI); sai do sys.path e do sys.modules no fim (padrão do T-0045)."""
    antes = set(sys.modules)
    sys.path.insert(0, str(WEB))
    try:
        from app import edicoes                                   # noqa: PLC0415
        yield edicoes
    finally:
        sys.path.remove(str(WEB))
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


def _perfis_da_web():
    """`usuarios.PERFIS` da web, lido pela AST (o módulo puxa o render; aqui só a lista importa)."""
    arv = ast.parse((WEB / "app" / "usuarios.py").read_text(encoding="utf-8"))
    for n in arv.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PERFIS" for t in n.targets):
            return tuple(ast.literal_eval(n.value))
    raise KeyError("PERFIS")


PERFIS = _perfis_da_web()


def _tabela_do_contrato():
    """A tabela "Quem edita, por lugar" do §10.9.7 do contrato: {(rid, tabela): (perfis,)}."""
    txt = CONTRATO.read_text(encoding="utf-8")
    sec = txt.split("#### 10.9.7", 1)[1].split("\n### ", 1)[0].split("\n#### ", 1)[0]
    out = {}
    for m in re.finditer(r'^\| `\("([^"]+)", "([^"]+)"\)` \| ([^|\n]+) \|$', sec, re.M):
        antes_do_parenteses = m.group(3).split("(")[0]
        out[(m.group(1), m.group(2))] = tuple(p for p in re.findall(r"`(\w+)`", antes_do_parenteses))
    return out


# ------------------------------------------------------------------ 1. quem edita
def test_RN_POS_011_tabela_web_igual_robo_igual_contrato(ed):
    contrato = _tabela_do_contrato()
    assert contrato == {ENT: ("admin", "pos_venda"), PEND: ("admin", "pos_venda"),
                        FRETES: ("admin", "pos_venda")}
    assert ed.EDITA_LUGAR == ba.EDITA_LUGAR_WEB == contrato
    assert ba.MOTIVO_PERFIL_WEB == "perfil sem edição neste farol"   # a frase do §10.9.7
    assert set(p for ps in contrato.values() for p in ps) <= set(PERFIS)
    # só lugares que o robô já grava, mais o Fretes (entra com a T-0037; até lá, recusado pelo lugar)
    # transição T-0037: até o #169 (testes/T-0037-fretes): antes do robô da T-0037 sobra o Fretes; depois, nada
    assert set(ba.EDITA_LUGAR_WEB) - set(ba.EDICOES_WEB) == (set() if fretes_no_robo(ba) else {FRETES})


_SEM = object()


def _reg(lugar, perfil=_SEM, valores=None, chave=CH0, modulo="pos_venda", seq=1):
    r = {"tipo": "edicao", "seq": seq, "id": f"id-t54-{seq}", "quando": "2026-11-27 09:00:00",
         "usuario": "login.teste", "rid": lugar[0], "tabela": lugar[1], "modulo": modulo, "chave": chave,
         "valores": {"etapa": "ENTREGUE"} if valores is None else valores, "antes": {}, "status": "pendente"}
    if perfil is not _SEM:
        r["perfil"] = perfil
    return r


@pytest.mark.parametrize("perfil", PERFIS)
@pytest.mark.parametrize("lugar", [ENT, PEND])
def test_RN_POS_011_mesma_decisao_na_web_e_no_robo(ed, perfil, lugar):
    """Valor × regra: edita ⇔ perfil ∈ {admin, pos_venda}; a web (`pode_editar`) e o robô
    (`validar_edicao_web`) dão a mesma resposta para os 8 perfis da web."""
    esperado = perfil in ("admin", "pos_venda")
    assert ed.pode_editar(perfil, lugar) is esperado
    assert ba.validar_edicao_web(_reg(lugar, perfil), OPCOES) == ("" if esperado else ba.MOTIVO_PERFIL_WEB)


OUTROS_FAROIS = (("pv_pedidos", "Pedidos", "autorizacoes"), ("pl_devolucoes", "Devoluções", "pos_venda"),
                 ("pl_ncc", "NCC pendentes", "ncc"), ("pl_garantias", "Garantias", "garantias"))


@pytest.mark.parametrize("rid, tabela, modulo", OUTROS_FAROIS)
def test_RN_POS_011_robo_outros_farois_seguem_so_do_admin(rid, tabela, modulo):
    """RN-GER-012 fora das Entregas: no robô, todo perfil que não é admin é recusado pelo perfil, antes de
    gravar. (A web: `test_RN_POS_011_tabela_e_pode_editar` do web/tests.)"""
    for p in PERFIS:
        if p == "admin":
            continue
        reg = _reg((rid, tabela), p, {"x": "1"}, modulo=modulo)
        gravou = []
        assert ba.aplicar_edicao_web(Path("/nao/usado"), reg, OPCOES, lambda *a: gravou.append(a) or 1) == (
            "erro", ba.MOTIVO_PERFIL_WEB), p
        assert gravou == []


def test_RN_POS_011_admin_igual_sem_perfil_em_todo_lugar():
    """O perfil `admin` não muda nada em lugar nenhum do robô: o resultado é o do registro sem perfil."""
    for (rid, tabela), lug in ba.EDICOES_WEB.items():
        for valores in ({"etapa": "ENTREGUE", "responsavel": "MOTORISTA TESTE"}, {"por": "PRICE"}, {}):
            sem = _reg((rid, tabela), valores=valores, modulo=lug["modulo"])
            com = _reg((rid, tabela), "admin", valores=valores, modulo=lug["modulo"])
            assert ba.validar_edicao_web(com, OPCOES) == ba.validar_edicao_web(sem, OPCOES), (rid, tabela)


@pytest.mark.parametrize("lugar", [ENT, PEND])
def test_RN_POS_011_perfil_torto_recusado_e_fila_antiga_segue(lugar):
    """§10.9.7: a fila de antes da T-0054 (sem `perfil`) segue aceita; `perfil` que não é um perfil é recusado."""
    assert ba.validar_edicao_web(_reg(lugar), OPCOES) == ""          # sem a chave `perfil`
    for torto in (None, 1, 0, True, ["admin"], ("admin",), {"perfil": "admin"}, "", "ADMIN", " admin",
                  "pos-venda", "pós_venda", "root"):
        assert ba.validar_edicao_web(_reg(lugar, torto), OPCOES) == ba.MOTIVO_PERFIL_WEB, repr(torto)


@pytest.mark.parametrize("perfil", PERFIS)
def test_RN_POS_011_linha_nova_robo_recusa_nas_entregas_e_perfil_fora(perfil):
    """O pós-venda edita a linha, não cria (§10.9.2 e §10.9.7). Robô: a linha nova nas Entregas não existe
    (recusa pelo lugar) e, na Garantia, o perfil fora é recusado. O `pode_criar` da web fica no web/tests."""
    novo = dict(_reg(ENT, perfil), chave="NOVO-0A1B2C3D", novo=True)
    m = ba.validar_edicao_web(novo, OPCOES)
    assert m == (ba.MOTIVO_LUGAR_WEB if perfil in ("admin", "pos_venda") else ba.MOTIVO_PERFIL_WEB)
    gar = dict(_reg(("pl_garantias", "Garantias"), perfil, {"status": "ABERTO"}, modulo="garantias"),
               chave="NOVO-0A1B2C3D", novo=True)
    if perfil != "admin":
        assert ba.validar_edicao_web(gar, OPCOES) == ba.MOTIVO_PERFIL_WEB


def test_RN_POS_010_notas_com_frete_robo_recusa_pelo_lugar():
    """"Notas com frete" (T-0037): enquanto o lugar não entra em `EDICOES_WEB`, o robô recusa pelo lugar
    (nada é gravado) para qualquer perfil. A tabela de quem edita fica no teste do contrato.
    transição T-0037: até o #169 (testes/T-0037-fretes): com o robô da T-0037, a mesma tabela das
    Entregas (RN-POS-010 + RN-POS-011): edita ⇔ perfil ∈ {admin, pos_venda}; o frete_real cai pelo lugar
    (quem edita) ou pelo perfil (o resto)."""
    if not fretes_no_robo(ba):
        for p in PERFIS:
            assert ba.validar_edicao_web(_reg(FRETES, p), OPCOES) == ba.MOTIVO_LUGAR_WEB, p
        return
    for p in PERFIS:
        edita = p in ("admin", "pos_venda")
        assert ba.validar_edicao_web(_reg(FRETES, p), OPCOES) == ("" if edita else ba.MOTIVO_PERFIL_WEB), p
        m = ba.validar_edicao_web(_reg(FRETES, p, {"frete_real": "50,00"}), OPCOES)
        assert m == (ba.MOTIVO_LUGAR_WEB if edita else ba.MOTIVO_PERFIL_WEB), p


# ------------------------------------------------------------------ 2. os 6 campos (o pacote do robô, conferido pela web)
def _spec(titulo="Entregas"):
    ix = {n: i for i, n in enumerate(NOMES)}
    ctx = SimpleNamespace(raiz=Path("/nao/usado"), hoje=HOJE,
                          posvenda={"entregas": [{"responsavel": "motorista teste"}]})
    ed_pc = rn._entrega_editavel(ctx, len(NOMES), {
        "etapa": ix["ETAPA"], "transportadora": ix["TRANSPORTADORA"], "entregue_em": ix["DT. REAL"],
        "prevista_manual": ix["DT. PREVISTA"], "responsavel": ix["RESPONSÁVEL"],
        "frete_real": ix["VLR REAL FRETE"]}, CAD, uf_col=ix["UF"], cidade_col=ix["CIDADE"],
        frete=(ix["VLR NF"], ix["LOCAL/FRETE"], ix["VLR FRETE"]))
    return ba.edicao_web("pl_entregas", titulo, ed_pc, [list(x) for x in LINHAS],
                         [{"nome": n} for n in NOMES], NOMES)


def _form(edm, k, **campos):
    spec = _spec()
    return edm.valores_do_form(spec, k, LINHAS[k], NOMES, {"c_" + c: v for c, v in campos.items()}, hoje=HOJE)


@pytest.mark.parametrize("titulo", ["Entregas", "Pendências dos meses anteriores"])
def test_RN_POS_011_web_aceita_o_pacote_do_robo_e_as_janelas_do_pc(ed, titulo):
    """A web aceita a `edicao` que o robô monta, com as janelas de data do PC. Os 6 campos e as listas do
    pacote ficam no test_RN_GER_012_spec_das_entregas_vem_da_tabela_do_pc (T-0021)."""
    spec = _spec(titulo)
    assert ed.erro_spec("pl_entregas", titulo, spec, NOMES, len(LINHAS)) is None
    assert spec["chaves"] == [CH0, CH1]
    c = {x["campo"]: x for x in spec["campos"]}
    prev = c["prevista_manual"]["opcoes"]                           # hoje..+45 e os 15 dias passados
    assert prev == rn.datas_de_previsao(HOJE) and len(prev) == 46 + 15
    assert prev[0] == _br(HOJE) and _br(HOJE + timedelta(45)) in prev and _br(HOJE - timedelta(15)) in prev
    assert _br(HOJE + timedelta(46)) not in prev and _br(HOJE - timedelta(16)) not in prev
    real = c["entregue_em"]["opcoes"]                               # os 30 dias até hoje
    assert real == [_br(HOJE - timedelta(i)) for i in range(30)]
    assert [x["campo"] for x in ed.campos_da_linha(spec, 1)] == [
        "etapa", "transportadora", "prevista_manual", "entregue_em", "responsavel"]   # RETIRA: sem frete real


@pytest.mark.parametrize("campo, valor, k, erro", [
    ("etapa", "ENTREGUE PARCIAL", 0, "ETAPA: escolha uma opção da lista."),
    ("transportadora", "TRANSPORTADORA TESTE 1", 1, "TRANSPORTADORA: escolha uma opção da lista."),  # não atende PA
    ("prevista_manual", _br(HOJE + timedelta(46)), 0, "DT. PREVISTA (ENTREGA): data fora das permitidas"),
    ("prevista_manual", _br(HOJE - timedelta(16)), 0, "DT. PREVISTA (ENTREGA): data fora das permitidas"),
    ("entregue_em", _br(HOJE + timedelta(1)), 0, "DT. REAL (ENTREGA): data fora das permitidas"),
    ("entregue_em", _br(HOJE - timedelta(30)), 0, "DT. REAL (ENTREGA): data fora das permitidas"),
    ("entregue_em", "31/02/2026", 0, "DT. REAL (ENTREGA): data"),
    ("frete_real", "-0,01", 0, "VLR FRETE (REAL): "),          # negativo: recusado (número ≥ 0)
    ("responsavel", "M" * 61, 0, "RESPONSÁVEL (MOTORISTA): até 60 caracteres."),
])
def test_RN_POS_011_web_recusa_fora_das_listas_e_janelas(ed, campo, valor, k, erro):
    mudou, _antes, e = _form(ed, k, **{campo: valor})
    assert mudou == {} and e.startswith(erro), e


def test_RN_POS_011_web_aceita_os_limites_e_formata_como_o_pc(ed):
    mudou, antes, e = _form(ed, 0, etapa="ENTREGUE", transportadora="TRANSPORTADORA TESTE 1",
                            prevista_manual=_br(HOJE + timedelta(45)), entregue_em=_br(HOJE - timedelta(29)),
                            responsavel="motorista teste", frete_real="0")
    assert e == ""
    assert mudou == {"etapa": "ENTREGUE", "transportadora": "TRANSPORTADORA TESTE 1",
                     "prevista_manual": _br(HOJE + timedelta(45)), "entregue_em": _br(HOJE - timedelta(29)),
                     "responsavel": "MOTORISTA TESTE", "frete_real": "0,00"}          # 0 ≥ 0 vale
    assert antes["etapa"] == "EM TRÂNSITO"
    mudou, _a, e = _form(ed, 0, prevista_manual=_br(HOJE - timedelta(15)), entregue_em=_br(HOJE))
    assert e == "" and set(mudou) == {"prevista_manual", "entregue_em"}
    # nota sem FRETE (RETIRA): o VLR FRETE (REAL) nem entra
    mudou, _a, e = _form(ed, 1, frete_real="99,00", etapa="ENTREGUE")
    assert e == "" and mudou == {"etapa": "ENTREGUE"}
    # e o robô aceita o que a web formatou (as mesmas regras do outro lado)
    mudou, _a, _e = _form(ed, 0, etapa="ENTREGUE", transportadora="TRANSPORTADORA TESTE 1",
                          prevista_manual=_br(HOJE + timedelta(45)), entregue_em=_br(HOJE - timedelta(29)),
                          responsavel="motorista teste", frete_real="321,50")
    assert ba.validar_edicao_web(_reg(ENT, "pos_venda", mudou), OPCOES) == ""


# ------------------------------------------------------------------ 3 e 4. o laço web → robô → PC, só acrescentando
class SiteFila:
    """O site falso do robô, por cima da `edicoes.Fila` de verdade (GET /api/edicoes e o confirmar)."""

    def __init__(self, fila):
        self.fila, self.chamadas = fila, []

    def get(self, url, params=None, headers=None, timeout=None):
        assert url == f"{BASE_FALSA}/api/edicoes" and headers["Authorization"] == f"Bearer {TOKEN_FALSO}"
        self.chamadas.append(("GET", params["desde"]))
        corpo = self.fila.desde(int(params["desde"]))
        return SimpleNamespace(status_code=200, json=lambda: corpo)

    def post(self, url, json=None, headers=None, timeout=None):
        assert url == f"{BASE_FALSA}/api/edicoes/confirmar"
        self.chamadas.append(("POST", json))
        self.fila.confirmar(json["epoca"], json["resultados"])
        return SimpleNamespace(status_code=200)


def _pc_com_historico(tmp_path, monkeypatch):
    """Um PC fictício (o notebook do robô) com diário, diário de outra máquina, planilha e APLICADAS de antes."""
    pc = tmp_path / "pc"
    rel = pc / "RELATORIOS"
    rel.mkdir(parents=True)
    pasta = rel / pv.PASTA_DIARIO
    monkeypatch.setenv("COMPUTERNAME", pv.MAQUINA_DO_POS_VENDA)          # o pós-venda gravou antes
    pv.registrar_no_diario(pasta, [("ENTREGAS", "FILIAL TESTE|900001|1", "etapa", "ENTREGUE")], "app",
                           quando="2026-11-19 10:00:00")
    monkeypatch.setenv("COMPUTERNAME", MAQ_ROBO)                         # daqui em diante, o robô
    assert not pv.pode_gravar_aqui() and pv.maquina() != pv.MAQUINA_DO_POS_VENDA.upper()
    pv.registrar_no_diario(pasta, [("ENTREGAS", "FILIAL TESTE|900002|1", "etapa", "EM TRÂNSITO"),
                                   ("ENTREGAS", "FILIAL TESTE|900002|1", "responsavel", "MOTORISTA TESTE")],
                           "app", quando="2026-11-20 08:00:00")
    wb = pv.criar_arquivo()
    nomes = [c[1] for c in pv.COLUNAS_DA_ABA[pv.ABA_ENT]]
    ws = wb[pv.ABA_ENT]
    for i, ch in enumerate((CH0, CH1)):
        ws.cell(pv.PRIMEIRA + i, nomes.index("chave") + 1, ch)
        ws.cell(pv.PRIMEIRA + i, nomes.index("etapa") + 1, "EM TRÂNSITO")
    xlsx = pc / ba.EDICOES_WEB[ENT]["arquivo"]
    wb.save(xlsx)
    apl = pc / ba.PASTA_EDICOES_WEB / f"APLICADAS_WEB_{MAQ_ROBO}.jsonl"
    apl.parent.mkdir(parents=True)
    apl.write_text(json.dumps({"quando": "2026-11-20 08:00:00", "epoca": "ep-antiga", "seq": 7,
                               "id": "id-antigo", "status": "aplicada", "motivo": ""}) + "\n", encoding="utf-8")
    meu = pasta / f"EDICOES_{MAQ_ROBO}.csv"
    outro = pasta / f"EDICOES_{pv.MAQUINA_DO_POS_VENDA}.csv"
    return pc, {"meu": meu, "outro": outro, "xlsx": xlsx, "apl": apl}


def _bytes(arqs):
    return {k: Path(a).read_bytes() for k, a in arqs.items()}


def _csv(arq):
    with open(arq, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def test_RN_POS_011_robo_so_acrescenta_recusa_perfil_fora_e_aceita_fila_antiga(ed, tmp_path, monkeypatch):
    pc, arqs = _pc_com_historico(tmp_path, monkeypatch)
    antes = _bytes(arqs)
    n_meu = len(_csv(arqs["meu"]))
    fila = ed.Fila(tmp_path / "site")
    mudou, ant, e = _form(ed, 0, etapa="ENTREGUE", transportadora="TRANSPORTADORA TESTE 1",
                          prevista_manual=_br(HOJE + timedelta(3)), entregue_em=_br(HOJE - timedelta(1)),
                          responsavel="motorista teste", frete_real="321,50")
    assert e == ""
    reg = dict(usuario="pos.teste", rid="pl_entregas", modulo="pos_venda")
    fila.registrar(**reg, tabela="Entregas", chave=CH0, valores=mudou, antes=ant, perfil="pos_venda")      # seq 1
    fila.registrar(**reg, tabela=PEND[1], chave=CH1, valores={"etapa": "CANCELADA"}, antes={}, perfil="admin")
    fila.registrar(**reg, tabela="Entregas", chave=CH1, valores={"etapa": "EM TRÂNSITO"}, antes={})       # sem perfil
    for p in ("gerente", "diretor"):                                     # forjados: a web não gravaria
        fila.registrar(**reg, tabela="Entregas", chave=CH1, valores={"etapa": "CANCELADA"}, antes={}, perfil=p)
    fila.registrar(usuario="pos.teste", rid="pv_pedidos", tabela="Pedidos", modulo="autorizacoes",
                   chave="101002|012345", valores={"por": sorted(rn.QUEM_AUTORIZA)[0]}, antes={}, perfil="pos_venda")
    assert "perfil" not in fila.desde(0)["linhas"][2]                    # a fila antiga não tem a chave

    site, logs = SiteFila(fila), []
    r = ba.sincronizar_edicoes_web(pc, BASE_FALSA, TOKEN_FALSO, site, logs.append, opcoes=OPCOES)
    assert r == {"aplicadas": 3, "erros": 3, "pendentes": 0, "confirmado": True}
    assert [x["status"] for x in fila.desde(0)["linhas"]] == ["aplicada"] * 3 + ["erro"] * 3   # o site vê
    (conf,) = [c[1] for c in site.chamadas if c[0] == "POST"]
    status = {x["seq"]: (x["status"], x["motivo"]) for x in conf["resultados"]}
    assert status == {1: ("aplicada", ""), 2: ("aplicada", ""), 3: ("aplicada", ""),
                      4: ("erro", ba.MOTIVO_PERFIL_WEB), 5: ("erro", ba.MOTIVO_PERFIL_WEB),
                      6: ("erro", ba.MOTIVO_PERFIL_WEB)}

    depois = _bytes(arqs)
    assert depois["outro"] == antes["outro"]                             # o diário da outra máquina intacto
    assert depois["xlsx"] == antes["xlsx"]                               # a planilha nem é aberta no robô
    assert depois["meu"].startswith(antes["meu"]) and len(depois["meu"]) > len(antes["meu"])
    assert depois["apl"].startswith(antes["apl"])
    novas = _csv(arqs["meu"])[n_meu:]
    assert all(ln[1] == MAQ_ROBO and ln[2] == "app" and ln[3] == "ENTREGAS" for ln in novas)
    # valor × regra: o diário traz o valor no formato do PC (data ISO, número do valor_digitado, maiúsculas)
    assert sorted((ln[4], ln[5], ln[6]) for ln in novas) == sorted([
        (CH0, "etapa", "ENTREGUE"), (CH0, "transportadora", "TRANSPORTADORA TESTE 1"),
        (CH0, "prevista_manual", (HOJE + timedelta(3)).isoformat()),
        (CH0, "entregue_em", (HOJE - timedelta(1)).isoformat()),
        (CH0, "responsavel", "MOTORISTA TESTE"), (CH0, "frete_real", "321.5"),
        (CH1, "etapa", "CANCELADA"), (CH1, "etapa", "EM TRÂNSITO")])
    assert len(novas) == 6 + 1 + 1                                        # nada dos 3 recusados
    apl = [json.loads(x) for x in arqs["apl"].read_text(encoding="utf-8").splitlines()]
    assert apl[0]["id"] == "id-antigo" and len(apl) == 1 + 6
    assert [(a["seq"], a["status"], a.get("perfil_web")) for a in apl[1:]] == [
        (1, "aplicada", "pos_venda"), (2, "aplicada", "admin"), (3, "aplicada", None),
        (4, "erro", "gerente"), (5, "erro", "diretor"), (6, "erro", "pos_venda")]
    assert "perfil_web" not in apl[3]                                     # a fila antiga segue sem a chave

    assert not any("pos.teste" in m or "900101" in m or "MOTORISTA" in m or TOKEN_FALSO in m for m in logs)


# ------------------------------------------------------------------ 5. sem dado pessoal
@pytest.mark.parametrize("texto", PESSOAIS)
def test_RN_POS_011_responsavel_com_dado_pessoal_recusado_sem_eco(ed, tmp_path, monkeypatch, texto):
    mudou, _a, e = _form(ed, 0, responsavel=texto)
    assert mudou == {} and e == "RESPONSÁVEL (MOTORISTA): sem CPF, CNPJ, telefone ou e-mail."
    m = ba.validar_edicao_web(_reg(ENT, "pos_venda", {"responsavel": texto}), OPCOES)
    assert m == ba.motivo_texto_web()
    # forjado na fila (a web não deixaria): o robô recusa, nada vai ao diário e o motivo/log não ecoam o dado
    pc, arqs = _pc_com_historico(tmp_path, monkeypatch)
    antes = _bytes(arqs)
    fila = ed.Fila(tmp_path / "site")
    fila.registrar(usuario="pos.teste", rid="pl_entregas", tabela="Entregas", modulo="pos_venda", chave=CH0,
                   valores={"responsavel": texto}, antes={}, perfil="pos_venda")
    site, logs = SiteFila(fila), []
    r = ba.sincronizar_edicoes_web(pc, BASE_FALSA, TOKEN_FALSO, site, logs.append, opcoes=OPCOES)
    assert r["erros"] == 1 and r["aplicadas"] == 0
    assert _bytes(arqs)["meu"] == antes["meu"] and _bytes(arqs)["xlsx"] == antes["xlsx"]
    dado = texto.replace("MOTORISTA TESTE ", "")
    (conf,) = [c[1] for c in site.chamadas if c[0] == "POST"]
    assert all(dado not in x["motivo"] for x in conf["resultados"])
    assert not re.search(r"\d{3}|@", " ".join(x["motivo"] for x in conf["resultados"]))
    assert not any(dado in m for m in logs)


# ------------------------------------------------------------------ 3 (HTTP). a web de verdade → robô → PC
# o harness da web real (TestClient) é o da T-0035/T-0024; só roda com FastAPI (ver a docstring do módulo)
from test_T0024_lote2_robo_web import _usuario  # noqa: E402
from test_T0035_robo_web import BASE, TOKEN, _Requests, _web, web_mod  # noqa: E402,F401

URL_ENT = "/farol/pl_entregas?aba=entregas"


def _tok(c, url):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(url).text).group(1)


def _campos(c, url):
    html = c.get(url).text
    return {k: v.replace("&amp;", "&") for k, v in
            re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html)}


def test_RN_POS_011_http_pos_venda_chega_ao_pc(web_mod, monkeypatch, tmp_path):
    cli, dados, _m = _web(web_mod, "web54", monkeypatch)
    monkeypatch.syspath_prepend(str(WEB / "tests"))
    from edicao_fixture import pacote_editavel                    # noqa: PLC0415
    assert cli.post("/api/pacote", json=pacote_editavel(),
                    headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    link = re.findall(r'class="bt-ed" href="([^"]+)"', cli.get(URL_ENT).text)[0].replace("&amp;", "&")
    fila_dir = dados / "edicoes"

    def fila():
        return [json.loads(x) for a in sorted(fila_dir.glob("EDICOES_WEB_*.jsonl"))
                for x in a.read_text(encoding="utf-8").splitlines()] if fila_dir.is_dir() else []

    pvd = _usuario(cli, "pos_venda")
    assert pvd.get(link).status_code == 200
    r = pvd.post("/farol/pl_entregas/editar", data=dict(_campos(pvd, link), csrf=_tok(pvd, "/senha"),
                                                         c_etapa="ENTREGUE", c_responsavel="motorista teste"),
                 follow_redirects=False)
    assert r.status_code == 303
    (reg,) = fila()
    assert reg["perfil"] == "pos_venda" and reg["valores"] == {"etapa": "ENTREGUE", "responsavel": "MOTORISTA TESTE"}

    # o robô puxa da web de verdade e grava no PC fictício (notebook do robô: só o diário)
    monkeypatch.setenv("COMPUTERNAME", MAQ_ROBO)
    pc = tmp_path / "pc54"
    logs = []
    res = ba.sincronizar_edicoes_web(pc, BASE, TOKEN, _Requests(cli), logs.append,
                                     opcoes={**OPCOES, "transportadora": set()})
    assert res == {"aplicadas": 1, "erros": 0, "pendentes": 0, "confirmado": True}
    linhas = _csv(pc / "RELATORIOS" / pv.PASTA_DIARIO / f"EDICOES_{MAQ_ROBO}.csv")[1:]
    assert sorted((ln[4], ln[5], ln[6]) for ln in linhas) == [
        (reg["chave"], "etapa", "ENTREGUE"), (reg["chave"], "responsavel", "MOTORISTA TESTE")]
    assert not (pc / ba.EDICOES_WEB[ENT]["arquivo"]).exists()           # a planilha não é criada nem tocada
    (apl,) = [json.loads(x) for x in next((pc / ba.PASTA_EDICOES_WEB).glob("APLICADAS_WEB_*.jsonl"))
              .read_text(encoding="utf-8").splitlines()]
    assert apl["perfil_web"] == "pos_venda" and apl["status"] == "aplicada"
    st = cli.get("/api/edicoes?desde=0", headers={"Authorization": f"Bearer {TOKEN}"}).json()["linhas"]
    assert [x["status"] for x in st] == ["aplicada"]
