"""T-0010 - exportacao da rota para a Maxima (layout Protheus ERP_MXSROTACLI).

RN-ROT-001 (docs/produto/03-regras.md; R-20261120-102022, -104729 e
-111303-alexandre):
- fica fora do JSON o cliente INTERNO, identificado pelo nome como no
  meta_nucleo.e_cliente_interno (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA)
  - RN-GER-004 - e a conta 000040 (RN-GER-005);
- a exportacao pelo Farol (relatorios_nucleo._exportar_protheus_da_rota)
  repassa nome e fantasia ao gerador (PR #12);
- a VISITA_SEMANAL chega a cada visita do bloco base do bap_dados (PR #14,
  marca b5). A leitura dela pelo Farol saiu do PR #12 e nao e testada aqui.

Carteira 100% ficticia: codigos 999xxx, nomes inventados, sem CNPJ, telefone
nem e-mail. "BAP AUTOPARTS LTDA" e o nome da propria empresa (o caso interno).
"""
import datetime as dt
from types import SimpleNamespace

import bap_dados
import planner_nucleo
import relatorios_nucleo

# segunda-feira de dezembro/2026 (nao e o 1o sabado, que e deposito)
SEGUNDA = dt.date(2026, 12, 7)
VENDEDOR = "999900 - VENDEDOR FICTICIO"


def _visita(cod, nome, fantasia="", curva="C", ordem=1):
    """Uma visita no formato de ctx.base["visitas"] (o que o Farol
    Roteirizacao recebe do bap_dados)."""
    return {"cod": cod, "loja": "01", "cod_cliente": cod, "loja_cru": "01",
            "cod_vend": "999900", "vendedor": VENDEDOR, "data": SEGUNDA,
            "ordem": ordem, "chave": f"{cod}-01", "curva": curva,
            "semana": "Semana 2", "nome": nome, "fantasia": fantasia}


def _carteira():
    return [
        _visita("999001", "BAP AUTOPARTS LTDA", "BAP FICTICIO", ordem=1),
        _visita("999002", "AUTOPECAS FICTICIA UM LTDA",
                "FICTICIA UM", curva="C", ordem=2),
        _visita("999003", "AUTOPECAS FICTICIA DOIS LTDA",
                "FICTICIA DOIS", curva="C", ordem=3),
    ]


def _ctx(visitas):
    """O ctx minimo que _exportar_protheus_da_rota usa: so ctx.base."""
    return SimpleNamespace(base={"visitas": visitas, "clientes": []})


def _por_codcli(linhas):
    return {x["codcli"]: x for x in linhas}


def test_RN_ROT_001_repassa_nome_e_fantasia(monkeypatch):
    capturado = {}

    def falso(cfg, clientes, chaves=None, compromisso=None, linhas=None):
        capturado["linhas"] = linhas
        return []

    monkeypatch.setattr(planner_nucleo, "linhas_protheus", falso)
    relatorios_nucleo._exportar_protheus_da_rota(_ctx(_carteira()))()

    rota = {r["COD_CLIENTE"]: r for r in capturado["linhas"]}
    assert set(rota) == {"999001", "999002", "999003"}
    assert rota["999001"].get("NOME_CLIENTE") == "BAP AUTOPARTS LTDA"
    assert rota["999001"].get("NOME_FANTASIA") == "BAP FICTICIO"
    assert rota["999002"].get("NOME_CLIENTE") == "AUTOPECAS FICTICIA UM LTDA"
    assert rota["999002"].get("NOME_FANTASIA") == "FICTICIA UM"


def test_RN_ROT_001_interno_pelo_nome_fica_fora():
    saida = relatorios_nucleo._exportar_protheus_da_rota(_ctx(_carteira()))()
    codcli = _por_codcli(saida)
    # RN-GER-004: o interno sai pelo NOME, mesmo com clientes=[] (sem cadastro)
    assert "99900101" not in codcli
    # os outros dois seguem no arquivo
    assert set(codcli) == {"99900201", "99900301"}


def test_RN_ROT_001_farol_repassa_visita_semanal_com_7():
    # a visita semanal (bap_dados marca b5) chega ao gerador pelo Farol:
    # periodicidade 7 e data final = proxima visita + 7 - 1
    carteira = _carteira()
    carteira[1]["visita_semanal"] = "SIM"       # 999002, curva C
    carteira[2]["visita_semanal"] = ""          # 999003, curva C
    saida = relatorios_nucleo._exportar_protheus_da_rota(_ctx(carteira))()
    codcli = _por_codcli(saida)

    semanal, normal = codcli["99900201"], codcli["99900301"]
    assert semanal["periodicidade"] == "7"
    assert semanal["dtfinal"] == planner_nucleo.dtfinal_protheus(SEGUNDA, 7)
    assert semanal["dtfinal"].startswith("2026-12-13")
    # a curva C sem a marca segue a periodicidade da curva
    per_c = planner_nucleo.periodicidade_maxima(
        planner_nucleo.periodicidade_da_curva("C"))
    assert per_c != 7
    assert normal["periodicidade"] == str(per_c)


# --------------------------------------------------------------------------
# VISITA_SEMANAL no bloco base do bap_dados (PR #14, marca b5)
# --------------------------------------------------------------------------
# os campos de cada visita do bloco base ANTES da marca b5 (bap_dados no
# main de 20/11/2026): a b5 so acrescenta "visita_semanal"
CAMPOS_ANTES_B5 = {
    "data", "dia", "semana", "ordem", "visita", "de", "cod", "loja",
    "cod_cliente", "loja_cru", "cod_vend", "chave", "nome", "fantasia", "uf",
    "cidade", "bairro", "zona", "vendedor", "supervisor", "segmento", "curva",
    "limite_disp", "atraso", "endereco", "numero", "contato",
    "dias_sem_compra"}


def _linha_rota(cod, nome, semanal):
    """Uma linha no formato de planner_nucleo.rota_do_mes (as chaves de
    planner_nucleo._linha_da_rota), com dados ficticios."""
    return {
        "SEMANA": "Semana 2", "DIA_DO_MES": SEGUNDA.day, "DATA": SEGUNDA,
        "DIA_DA_SEMANA": "SEGUNDA", "ORDEM_DE_VISITA": 1,
        "VISITA_NO_MES": 1, "VISITAS_DO_CLIENTE": 4,
        "ZONA": "ZONA FICTICIA", "COD_ZONA": "Z99", "ZONA_ID": "z99",
        "UF_ZONA": "AM", "SUPERVISOR": "SUPERVISOR FICTICIO",
        "CONTA_SUPERVISOR": "SIM", "VENDEDOR_ATIVO": "SIM",
        "COD_VENDEDOR": "999900", "VENDEDOR": "VENDEDOR FICTICIO",
        "COD_CLIENTE": cod, "LOJA": "01", "CHAVE_CLIENTE": f"{cod}-01",
        "NOME_CLIENTE": nome, "NOME_FANTASIA": "", "SEGMENTO": "VAREJO",
        "SUBSEGMENTO": "", "UF": "AM", "CIDADE": "Manaus", "BAIRRO": "Centro",
        "ENDERECO": "RUA FICTICIA", "NUMERO": "100", "CONTATO": "",
        "TELEFONE": "", "DIAS_SEM_COMPRA": 10, "LIMITE_DISPONIVEL": 1000.0,
        "VALOR_EM_ATRASO": 0.0, "INADIMPLENTE": "NAO", "CURVA_RECEITA": "S",
        "STATUS_CLIENTE": "ATIVO", "STATUS_PLANNER": "ATIVO",
        "LATITUDE": None, "LONGITUDE": None, "PRECISAO_GEO": "",
        "COD_ULTIMO_VENDEDOR": "999900", "AREA": "", "PRIORIDADE_ROTA": "",
        "VISITA_SEMANAL": semanal,
    }


def test_RN_ROT_001_visita_semanal_chega_ao_bloco(tmp_path, monkeypatch):
    # base minima ficticia: so o arquivo precisa existir (a leitura e falsa)
    (tmp_path / bap_dados.RELATORIOS).mkdir(parents=True)
    (tmp_path / bap_dados.RELATORIOS / "BASE_CLIENTE.xlsx").write_bytes(b"")
    rota = [_linha_rota("999101", "AUTOPECAS FICTICIA SEMANAL", "SIM"),
            _linha_rota("999102", "AUTOPECAS FICTICIA NORMAL", ""),
            _linha_rota("999103", "AUTOPECAS FICTICIA SEM CHAVE", None)]
    del rota[2]["VISITA_SEMANAL"]

    monkeypatch.setattr(bap_dados, "_cfg_planner",
                        lambda raiz: tmp_path / "planner_config.json")
    monkeypatch.setattr(planner_nucleo, "carregar_config",
                        lambda arq: {"pessoas": [], "zonas": []})
    monkeypatch.setattr(planner_nucleo, "ler_base_cliente", lambda arq: [])
    for nome in ("aplicar_parametros", "migrar_areas_antigas",
                 "sincronizar_areas"):
        monkeypatch.setattr(planner_nucleo, nome, lambda cfg, cl: None)
    monkeypatch.setattr(planner_nucleo, "indicadores", lambda cfg, cl: {})
    monkeypatch.setattr(planner_nucleo, "rota_do_mes", lambda cfg, cl: rota)

    visitas = {v["cod"]: v for v in bap_dados._bloco_base(tmp_path)["visitas"]}

    assert set(visitas) == {"999101", "999102", "999103"}
    assert visitas["999101"]["visita_semanal"] == "SIM"
    assert visitas["999102"]["visita_semanal"] == ""
    assert visitas["999103"]["visita_semanal"] == ""
    # a b5 so acrescenta a chave: os outros campos ficam como eram
    for v in visitas.values():
        assert set(v) == CAMPOS_ANTES_B5 | {"visita_semanal"}
    sem, nor = visitas["999101"], visitas["999102"]
    diferentes = {k for k in CAMPOS_ANTES_B5 if sem[k] != nor[k]}
    assert diferentes == {"cod", "cod_cliente", "chave", "nome"}
    assert nor == {
        "data": SEGUNDA, "dia": "SEGUNDA", "semana": "Semana 2", "ordem": 1,
        "visita": 1, "de": 4, "cod": "999102", "loja": "01",
        "cod_cliente": "999102", "loja_cru": "01", "cod_vend": "999900",
        "chave": "999102-01", "nome": "AUTOPECAS FICTICIA NORMAL",
        "fantasia": "", "uf": "AM", "cidade": "MANAUS", "bairro": "CENTRO",
        "zona": "Z99", "vendedor": "999900 - VENDEDOR FICTICIO",
        "supervisor": "SUPERVISOR FICTICIO", "segmento": "VAREJO",
        "curva": "S", "limite_disp": 1000.0, "atraso": 0.0,
        "endereco": "RUA FICTICIA", "numero": "100", "contato": "",
        "dias_sem_compra": 10, "visita_semanal": ""}
