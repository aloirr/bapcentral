"""T-0045 (ADR 0004, contrato visitas-nuvem v1): rotas do cron, concessão, tetos, pausa, lote, fila, perfis e /saude.
Tudo fictício: nenhum nome, CNPJ, telefone ou e-mail real. O relógio do site é trocado por `visitas.agora`."""
import base64
import gzip
import hashlib
import io
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import visitas
from app.main import criar_app
from app.visitas import MANAUS
from conftest import TOKEN, entrar, token_form

VTOKEN = secrets.token_urlsafe(32)
HOJE = datetime(2026, 11, 27, 9, 0, 0, tzinfo=MANAUS)         # sexta-feira, em Manaus
H = {"Authorization": f"Bearer {VTOKEN}"}
HP = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def relogio(monkeypatch):
    r = {"t": HOJE}
    monkeypatch.setattr(visitas, "agora", lambda: r["t"])
    return r


@pytest.fixture
def v(amb, monkeypatch, relogio):
    monkeypatch.setenv("BAP_VISITAS_TOKEN", VTOKEN)
    with TestClient(criar_app(), base_url="https://testserver") as c:
        c.app_dados = amb
        yield c


def conceder(v, motivo="agenda", dias=("20261126",)):
    return v.post("/api/visitas/rodada", json={"motivo": motivo, "pedido": None, "dias": list(dias),
                                               "versao_robo": "t"}, headers=H)


def fim(v, rid, codigo="OK", **kw):
    corpo = {"codigo": codigo, "fase": None, "dias_ok": [], "dias_faltando": [], "erros_vendedor": 0,
             "duracao_s": 5, "pico_mb": None, "achados": None, "medidas": None, **kw}
    return v.post(f"/api/visitas/rodada/{rid}/fim", json=corpo, headers=H)


def rodada_e_fim(v, relogio, motivo="agenda", codigo="OK", **kw):
    r = conceder(v, motivo)
    assert r.status_code == 201, r.text
    f = fim(v, r.json()["id"], codigo, **kw)
    assert f.status_code == 200, f.text
    relogio["t"] += timedelta(seconds=2)           # o id da rodada é a hora de início: nunca repete
    return r.json()["id"]


def xlsx(textos):
    """Excel mínimo e fictício: só o que a varredura lê (sharedStrings)."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
    return b.getvalue()


def lote(rid, dia="20261126", textos=("RCA", "CLIENTE", "CLIENTE FICTICIO 1"), erros=0, mudar=None):
    ex = xlsx(textos)
    corpo = {"versao": 1, "rodada": rid, "dia": dia, "baixado_em": "2026-11-27T06:07:41-04:00",
             "vendedores": 1, "erros_vendedor": erros,
             "equipe": {"filiais": {}, "supervisores": {}, "representantes": {}}, "extras": {},
             "arquivos": [{"pasta": "VEND_FICT", "nome": f"VISITA-VEND_FICT-{dia[6:]}-{dia[4:6]}-{dia[:4]}-06-07.xlsx",
                           "sha256": hashlib.sha256(ex).hexdigest(), "bytes": len(ex),
                           "b64": base64.b64encode(ex).decode()}]}
    if mudar:
        mudar(corpo)
    return corpo


def enviar(v, rid, corpo, dia="20261126", sha=None, enc="gzip", tipo="application/json", token=VTOKEN):
    bruto = json.dumps(corpo, separators=(",", ":")).encode()
    h = {"Authorization": f"Bearer {token}", "Content-Type": tipo, "X-BAP-SHA256": sha or hashlib.sha256(bruto).hexdigest()}
    if enc:
        h["Content-Encoding"] = enc
    return v.post(f"/api/visitas/rodada/{rid}/dia/{dia}", content=gzip.compress(bruto), headers=h)


def logar(v, admin, login, perfil):
    """Cria o usuário pelo admin e devolve um cliente logado com ele."""
    admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil, "senha": "senha-inicial-77",
                                  "csrf": token_form(admin, "/usuarios")})
    c = TestClient(admin.app, base_url="https://testserver")
    assert entrar(c, login, "senha-inicial-77").status_code == 303
    c.post("/senha", data={"atual": "senha-inicial-77", "nova": "senha-nova-forte-88", "confirma": "senha-nova-forte-88",
                           "csrf": token_form(c, "/senha")})
    return c


# ---------------------------------------------------------------- constantes e códigos (contrato §2 e §5)
def test_constantes_do_contrato():
    assert visitas.TENTATIVAS_DIA == {"agenda": 4, "pedido": 3, "retentativa": 1, "diagnostico": 2}
    assert visitas.LOGINS_DIA_MAX == 8 and visitas.CONCESSAO_MIN == 10 and visitas.PEDIDO_MAX_DIAS == 7
    assert visitas.LOTE_GZ_MAX == 8 * 1024 * 1024 and visitas.ARQUIVO_MAX == 2 * 1024 * 1024 and visitas.ARQUIVOS_MAX == 60


PAUSAM_CONTRATO = ("MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA", "MAXIMA_BLOQUEIO", "DADO_PESSOAL")


def test_RN_VIS_005_007_todo_codigo_tem_status_e_os_que_pausam():
    assert set(visitas.STATUS_DO_CODIGO) == set(visitas.CODIGOS)
    assert set(visitas.PAUSAM) == set(PAUSAM_CONTRATO)
    assert visitas.STATUS_DO_CODIGO["PARCIAL_VENDEDOR"] == "parcial" and visitas.STATUS_DO_CODIGO["OK"] == "ok"


def test_RN_VIS_002_espelho_juntar_baixado_empate_e_dia_fechado():
    """Espelho de visitas_nucleo.juntar_baixado: a maior hora vale; no empate, a NUVEM (o PC anota a hora da nuvem)."""
    n = {"20261126": {"baixado_em": "2026-11-27T06:07:41-04:00", "erros_vendedor": 2, "refeito": False}}
    j = visitas.juntar_baixado(n, {"20261126": "2026-11-27T07:12:03-04:00"})["20261126"]
    assert j == {"baixado_em": "2026-11-27T07:12:03-04:00", "origem": "pc"}                 # PC maior: sem erros da nuvem
    assert visitas.juntar_baixado(n, {"20261126": "2026-11-26T20:00:00-04:00"})["20261126"]["origem"] == "nuvem"
    e = visitas.juntar_baixado(n, {"20261126": "2026-11-27T06:07:41-04:00"})["20261126"]      # empate: nuvem, com os erros
    assert e["origem"] == "nuvem" and e["erros_vendedor"] == 2 and e["refeito"] is False
    assert visitas.juntar_baixado(None, {"20261126": "2026-11-27T06:00:00"})["20261126"]["baixado_em"] == "2026-11-27T06:00:00-04:00"
    assert visitas.juntar_baixado({"20261126": "lixo"}, None) == {}
    assert visitas.dia_fechado_no_indice({"20261126": "2026-11-27T06:07:41-04:00"}, datetime(2026, 11, 26).date())
    assert not visitas.dia_fechado_no_indice({"20261127": "2026-11-27T21:00:00-04:00"}, datetime(2026, 11, 27).date())
    hoje = datetime(2026, 11, 27).date()
    assert [d.day for d in visitas.dias_a_baixar({"20261125": "2026-11-26T08:00:00-04:00"}, hoje - timedelta(days=3), hoje + timedelta(days=2), hoje)] == [24, 26, 27]


def test_RN_VIS_002_importado_pelo_pc_com_a_mesma_hora_mantem_os_erros_da_nuvem(v, relogio):
    """O caso comum (RN-VIS-006): o PC devolve no `fechados_pc` a hora da própria nuvem; o dia segue de origem nuvem."""
    r = conceder(v).json()
    enviar(v, r["id"], lote(r["id"], erros=2))
    ep = v.get("/api/visitas/lotes?desde=0", headers=HP).json()["epoca"]
    v.post("/api/visitas/lotes/confirmar", json={"epoca": ep, "resultados": [{"seq": 1, "status": "aplicada", "motivo": ""}],
                                                 "fechados_pc": {"20261126": "2026-11-27T06:07:41-04:00"}}, headers=HP)
    ind = v.get("/api/visitas/trabalho", headers=H).json()["indice"]["20261126"]
    assert ind["origem"] == "nuvem" and ind["erros_vendedor"] == 2


# ---------------------------------------------------------------- token (401)
@pytest.mark.parametrize("metodo,url", [("get", "/api/visitas/trabalho"), ("post", "/api/visitas/rodada"),
                                        ("post", "/api/visitas/rodada/R20261127T060000/progresso"),
                                        ("post", "/api/visitas/rodada/R20261127T060000/dia/20261126"),
                                        ("post", "/api/visitas/rodada/R20261127T060000/fim")])
def test_cron_token_errado_ou_ausente_401(v, metodo, url):
    for h in ({}, {"Authorization": "Bearer errado"}, HP):          # o token do robô do PC também não abre o cron
        assert getattr(v, metodo)(url, headers=h).status_code == 401


def test_sem_variavel_o_cron_nao_entra(amb, relogio):
    with TestClient(criar_app(), base_url="https://testserver") as c:
        assert c.get("/api/visitas/trabalho", headers=H).status_code == 401


def test_token_do_cron_nao_abre_o_resto(v):
    assert v.get("/api/visitas/lotes", headers=H).status_code == 401
    assert v.get("/api/edicoes", headers=H).status_code == 401
    assert v.post("/api/pacote", json={}, headers=H).status_code == 401
    assert v.get("/api/visitas/trabalho", headers=HP).status_code == 401


# ---------------------------------------------------------------- concessão (RN-VIS-004)
def test_RN_VIS_004_uma_rodada_por_vez_e_vence_sem_progresso(v, relogio):
    r = conceder(v)
    assert r.status_code == 201 and r.json()["id"].startswith("R20261127T090000")
    rid = r.json()["id"]
    c2 = conceder(v, "pedido")
    assert c2.status_code == 409 and c2.json()["id"] == rid
    relogio["t"] += timedelta(minutes=9)
    p = v.post(f"/api/visitas/rodada/{rid}/progresso", json={"fase": "grade", "dia": "20261126", "feitos": 7, "total": 15}, headers=H)
    assert p.status_code == 200                                      # renovou por mais 10 min
    relogio["t"] += timedelta(minutes=9)
    assert v.post(f"/api/visitas/rodada/{rid}/progresso", json={"fase": "envio"}, headers=H).status_code == 200
    relogio["t"] += timedelta(minutes=11)                            # passou de 10 min sem progresso
    assert v.post(f"/api/visitas/rodada/{rid}/progresso", json={"fase": "envio"}, headers=H).status_code == 409
    assert v.get("/api/visitas/trabalho", headers=H).json()["rodada_ativa"] is None
    assert visitas_rodadas(v)[0]["codigo"] == "RODADA_INTERROMPIDA"
    assert fim(v, rid, "OK").status_code == 409                       # `fim` tardio de concessão vencida
    assert v.post("/api/visitas/rodada/R20200101T000000/progresso", json={"fase": "grade"}, headers=H).status_code == 404


def visitas_rodadas(v):
    return [json.loads(x) for x in reversed((v.app_dados / "visitas" / "rodadas.jsonl").read_text().splitlines())]


def test_concessao_corpo_invalido_400(v):
    for c in ({"motivo": "outro", "dias": ["20261126"]}, {"motivo": "agenda", "dias": []},
              {"motivo": "agenda", "dias": ["2026-11-26"]}, {"motivo": "diagnostico", "dias": ["20261125", "20261126"]},
              {"motivo": "pedido", "dias": [f"2026112{i}" for i in range(0, 8)] + ["20261130"]}, [1]):
        assert v.post("/api/visitas/rodada", json=c, headers=H).status_code == 400


# ---------------------------------------------------------------- tetos (RN-VIS-008)
def test_RN_VIS_008_teto_por_motivo(v, relogio):
    for _ in range(3):
        rodada_e_fim(v, relogio, "pedido")
    r = conceder(v, "pedido")
    assert r.status_code == 429 and r.json() == {"erro": "teto do dia", "motivo": "pedido"}
    assert conceder(v, "agenda").status_code == 201                  # os outros motivos seguem
    t = v.get("/api/visitas/trabalho", headers=H).json()["tentativas_hoje"]
    assert t["dia"] == "20261127" and t["total"] == 4 and t["por_motivo"]["pedido"]["n"] == 3


def test_RN_VIS_008_teto_da_soma_8_e_o_dia_seguinte_zera(v, relogio):
    for m in ("agenda", "agenda", "agenda", "agenda", "pedido", "pedido", "pedido", "retentativa"):
        rodada_e_fim(v, relogio, m)
    t = v.get("/api/visitas/trabalho", headers=H).json()["tentativas_hoje"]
    assert t["total"] == 8
    r = conceder(v, "diagnostico")                                   # o motivo está abaixo do teto, a soma não
    assert r.status_code == 429 and r.json()["motivo"] == "diagnostico"
    relogio["t"] = HOJE + timedelta(days=1)
    assert v.get("/api/visitas/trabalho", headers=H).json()["tentativas_hoje"] == {"dia": "20261128", "total": 0, "por_motivo": {}}
    assert conceder(v, "diagnostico").status_code == 201


def test_RN_VIS_008_a_tentativa_conta_na_concessao_e_guarda_o_codigo(v, relogio):
    rodada_e_fim(v, relogio, "agenda", "MAXIMA_FORA")
    t = v.get("/api/visitas/trabalho", headers=H).json()["tentativas_hoje"]
    assert t["por_motivo"]["agenda"]["n"] == 1 and t["por_motivo"]["agenda"]["codigo"] == "MAXIMA_FORA"
    assert t["por_motivo"]["agenda"]["ultima_em"].endswith("-04:00")
    # a rodada que cai sem `fim` também gastou o login
    r = conceder(v, "agenda").json()
    relogio["t"] += timedelta(minutes=11)
    t = v.get("/api/visitas/trabalho", headers=H).json()["tentativas_hoje"]
    assert t["total"] == 2 and t["por_motivo"]["agenda"]["codigo"] == "RODADA_INTERROMPIDA"


def test_RN_VIS_006_retentativa_marca_refeito_na_concessao(v, relogio):
    r = conceder(v).json()
    assert enviar(v, r["id"], lote(r["id"], erros=2)).status_code == 200
    assert fim(v, r["id"], "PARCIAL_VENDEDOR", erros_vendedor=2, dias_ok=["20261126"]).status_code == 200
    ind = v.get("/api/visitas/trabalho", headers=H).json()["indice"]["20261126"]
    assert ind["erros_vendedor"] == 2 and ind["refeito"] is False
    relogio["t"] += timedelta(seconds=2)
    assert conceder(v, "retentativa").status_code == 201
    assert v.get("/api/visitas/trabalho", headers=H).json()["indice"]["20261126"]["refeito"] is True


# ---------------------------------------------------------------- pausa (RN-VIS-005/007)
@pytest.mark.parametrize("codigo", PAUSAM_CONTRATO)
def test_RN_VIS_005_codigo_que_pausa_trava_a_nuvem(v, relogio, codigo):
    ach = [{"coluna": "ENDERECO", "tipo": "telefone", "n": 1}] if codigo == "DADO_PESSOAL" else None
    r = conceder(v).json()
    f = fim(v, r["id"], codigo, achados=ach, fase="filtro" if ach else None)
    assert f.status_code == 200 and f.json() == {"ok": True, "pausado": True}
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"]["codigo"] == codigo
    relogio["t"] += timedelta(hours=1)
    c = conceder(v, "pedido")
    assert c.status_code == 423 and c.json() == {"erro": "pausado", "codigo": codigo}
    assert fim(v, r["id"], codigo, achados=ach, fase="filtro" if ach else None).json()["pausado"] is True   # `fim` repetido responde igual


def test_RN_VIS_005_pausa_so_sai_pelo_retomar_do_admin(v, admin, relogio):
    r = conceder(v).json()
    fim(v, r["id"], "MAXIMA_SENHA")
    ger = logar(v, admin, "ger.um", "gerente")
    assert ger.post("/visitas/retomar", data={"csrf": token_form(ger, "/visitas/atualizar")}).status_code == 403
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"]
    relogio["t"] += timedelta(days=2)                                 # nem o tempo tira a pausa
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"]["codigo"] == "MAXIMA_SENHA"
    x = admin.post("/visitas/retomar", data={"csrf": token_form(admin, "/visitas/atualizar")}, follow_redirects=False)
    assert x.status_code == 303 and v.get("/api/visitas/trabalho", headers=H).json()["pausado"] is None
    assert conceder(v).status_code == 201


def test_RN_VIS_007_retomar_dado_pessoal_pede_o_recado_e_volta_ao_diagnostico(v, admin, relogio):
    r = conceder(v, "diagnostico").json()
    fim(v, r["id"], "DADO_PESSOAL", fase="filtro", achados=[{"coluna": "ENDERECO", "tipo": "email", "n": 1}])
    assert v.get("/api/visitas/trabalho", headers=H).json()["diagnostico"]["estado"] == "falhou"
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/retomar", data={"csrf": csrf, "recado": "qualquer coisa"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"]["codigo"] == "DADO_PESSOAL"   # sem recado válido: nada muda
    admin.post("/visitas/retomar", data={"csrf": csrf, "recado": "R-20261127-101010-alexandre"})
    t = v.get("/api/visitas/trabalho", headers=H).json()
    assert t["pausado"] is None and t["diagnostico"]["estado"] == "pendente"
    reg = [json.loads(x) for x in (v.app_dados / "visitas" / "pedidos.jsonl").read_text().splitlines()]
    assert reg[-1]["retomar"] and reg[-1]["recado"] == "R-20261127-101010-alexandre" and reg[-1]["perfil"] == "admin"
    assert "admin.teste" not in json.dumps(reg)                       # perfil, nunca o usuário


def test_RN_VIS_005_tela_mudou_duas_vezes_na_mesma_fase_pausa(v, relogio):
    rodada_e_fim(v, relogio, "agenda", "TELA_MUDOU", fase="grade")
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"] is None
    rodada_e_fim(v, relogio, "agenda", "TELA_MUDOU", fase="grade")
    t = v.get("/api/visitas/trabalho", headers=H).json()
    assert t["pausado"]["codigo"] == "TELA_MUDOU"


def test_fim_corpo_invalido_400(v):
    r = conceder(v).json()
    base = {"fase": None, "dias_ok": [], "dias_faltando": [], "erros_vendedor": 0, "duracao_s": 1, "pico_mb": None,
            "achados": None, "medidas": None}
    for c in ({**base, "codigo": "INVENTADO"}, {**base, "codigo": "TELA_MUDOU"},                       # fase obrigatória
              {**base, "codigo": "OK", "achados": [{"coluna": "ENDERECO", "tipo": "cnpj", "n": 1, "valor": "x"}]},
              {**base, "codigo": "OK", "achados": [{"coluna": "rua das flores", "tipo": "cnpj", "n": 1}]},   # rótulo, nunca valor
              {**base, "codigo": "OK", "fase": "inventada"}):
        assert v.post(f"/api/visitas/rodada/{r['id']}/fim", json=c, headers=H).status_code == 400
    assert v.post("/api/visitas/rodada/R20200101T000000/fim", json={**base, "codigo": "OK"}, headers=H).status_code == 404


# ---------------------------------------------------------------- lote (§3.4)
def test_lote_ok_idempotente_e_entra_no_indice(v, relogio):
    r = conceder(v).json()
    a = enviar(v, r["id"], lote(r["id"]))
    assert a.status_code == 200 and a.json() == {"ok": True, "seq": 1, "arquivos": 1}
    assert enviar(v, r["id"], lote(r["id"])).json()["seq"] == 1       # mesmo id + dia + sha256: o mesmo seq
    assert (v.app_dados / "visitas" / "lotes" / "1.json.gz").is_file()
    ind = v.get("/api/visitas/trabalho", headers=H).json()["indice"]["20261126"]
    assert ind["origem"] == "nuvem" and ind["baixado_em"] == "2026-11-27T06:07:41-04:00"


def test_lote_recusas(v, relogio):
    r = conceder(v).json()
    rid = r["id"]
    assert enviar(v, rid, lote(rid), sha="0" * 64).status_code == 422
    assert enviar(v, rid, lote(rid), enc="").status_code == 415
    assert enviar(v, rid, lote(rid), tipo="text/plain").status_code == 415
    assert enviar(v, "R20200101T000000", lote(rid)).status_code == 404
    assert enviar(v, rid, lote(rid), dia="20261128").status_code == 422          # futuro e diferente do corpo
    assert enviar(v, rid, lote(rid, mudar=lambda c: c["arquivos"][0].update(nome="VISITA-OUTRA-26-11-2026-06-07.xlsx"))).status_code == 422
    assert enviar(v, rid, lote(rid, mudar=lambda c: c["arquivos"][0].update(pasta="../x"))).status_code == 422
    assert enviar(v, rid, lote(rid, mudar=lambda c: c["arquivos"][0].update(sha256="a" * 64))).status_code == 422
    mau = enviar(v, rid, lote(rid, mudar=lambda c: c.update(arquivos=[])))
    assert mau.status_code == 422 and "arquivos" in mau.json()["detalhes"]
    assert not (v.app_dados / "visitas" / "lotes" / "1.json.gz").exists()        # nada foi gravado
    relogio["t"] += timedelta(minutes=11)
    assert enviar(v, rid, lote(rid)).status_code == 409                           # concessão vencida


def test_lote_grande_demais_413(v, monkeypatch):
    r = conceder(v).json()
    monkeypatch.setattr(visitas, "LOTE_GZ_MAX", 200)
    big = lote(r["id"], textos=["X" * 4000])
    assert enviar(v, r["id"], big).status_code == 413


@pytest.mark.parametrize("texto,tipo", [("fulano@exemplo.com.br", "email"), ("12.345.678/0001-95", "cnpj"),
                                        ("123.456.789-09", "cpf"), ("(92) 99999-1234", "telefone"),
                                        ("12345678000195", "cnpj")])
def test_RN_VIS_007_lote_com_dado_pessoal_nao_e_gravado_e_pausa(v, relogio, texto, tipo):
    r = conceder(v).json()
    x = enviar(v, r["id"], lote(r["id"], textos=("RCA", "CLIENTE", texto)))
    assert x.status_code == 422 and x.json()["erro"] == "dado pessoal"
    assert x.json()["achados"] == [{"coluna": "CELULA", "tipo": tipo, "n": 1}]                # rótulo, tipo e n; nunca o valor
    assert texto not in x.text and "12345678" not in x.text                     # nunca o valor
    assert not (v.app_dados / "visitas" / "lotes").exists() or not list((v.app_dados / "visitas" / "lotes").glob("*.json.gz"))
    assert v.get("/api/visitas/lotes", headers=HP).json()["linhas"] == []
    assert v.get("/api/visitas/trabalho", headers=H).json()["pausado"]["codigo"] == "DADO_PESSOAL"
    assert texto not in (v.app_dados / "visitas" / "rodadas.jsonl").read_text()


@pytest.mark.parametrize("coluna", ["KM DIST", "BONIF", "OBSERVACAO"])
def test_RN_VIS_007_coluna_fora_da_lista_recusa_o_lote(v, relogio, coluna):
    r = conceder(v).json()
    x = enviar(v, r["id"], lote(r["id"], textos=("RCA", coluna)))
    assert x.status_code == 422 and v.get("/api/visitas/trabalho", headers=H).json()["pausado"]["codigo"] == "DADO_PESSOAL"


# ---------------------------------------------------------------- robô do PC (§4.1 a §4.3)
def test_robo_lista_baixa_confirma_e_o_erro_tira_a_nuvem_do_indice(v, relogio):
    r = conceder(v).json()
    enviar(v, r["id"], lote(r["id"]))
    assert v.get("/api/visitas/lotes?desde=0").status_code == 401
    ls = v.get("/api/visitas/lotes?desde=0", headers=HP).json()
    assert ls["ate_seq"] == 1 and ls["mais"] is False and ls["epoca"]
    assert set(ls["linhas"][0]) == {"seq", "dia", "rodada", "baixado_em", "arquivos", "bytes_gz", "sha256", "status"}
    assert ls["linhas"][0]["status"] == "pendente"
    c = v.get("/api/visitas/lote/1", headers=HP)
    assert c.status_code == 200 and c.headers["content-encoding"] == "gzip"
    assert c.headers["x-bap-sha256"] == ls["linhas"][0]["sha256"] and v.get("/api/visitas/lote/9", headers=HP).status_code == 404
    pc = {"20261125": "2026-11-26T07:00:00-04:00"}
    assert v.post("/api/visitas/lotes/confirmar", json={"epoca": ls["epoca"], "resultados": []}, headers=HP).status_code == 400   # sem fechados_pc
    assert v.post("/api/visitas/lotes/confirmar", json={"epoca": "outra", "resultados": [], "fechados_pc": pc}, headers=HP).status_code == 409
    ok = v.post("/api/visitas/lotes/confirmar", json={"epoca": ls["epoca"], "fechados_pc": pc, "resultados": [
        {"seq": 1, "status": "erro", "motivo": "sha256"}]}, headers=HP)
    assert ok.status_code == 200
    t = v.get("/api/visitas/trabalho", headers=H).json()
    assert "20261126" not in t["indice"] and t["indice"]["20261125"]["origem"] == "pc"
    assert t["fechados_pc_em"] == "2026-11-27T09:00:00-04:00"
    assert v.post("/api/visitas/lotes/confirmar", json={"epoca": ls["epoca"], "fechados_pc": pc, "resultados": [
        {"seq": 1, "status": "erro", "motivo": "texto livre"}]}, headers=HP).status_code == 400


def test_retencao_do_corpo_confirmado_e_nao_confirmado(v, relogio):
    r = conceder(v).json()
    enviar(v, r["id"], lote(r["id"]))
    ep = v.get("/api/visitas/lotes?desde=0", headers=HP).json()["epoca"]
    arq = v.app_dados / "visitas" / "lotes" / "1.json.gz"
    relogio["t"] += timedelta(days=20)
    v.post("/api/visitas/lotes/confirmar", json={"epoca": ep, "fechados_pc": {}, "resultados": []}, headers=HP)
    assert arq.is_file()                                              # 20 dias sem confirmar: ainda guarda (30)
    relogio["t"] += timedelta(days=11)
    v.post("/api/visitas/lotes/confirmar", json={"epoca": ep, "fechados_pc": {}, "resultados": []}, headers=HP)
    assert not arq.exists()
    assert v.get("/saude").json()["visitas"]["lotes_sem_confirmar_vencidos"] == 1


# ---------------------------------------------------------------- tela (perfis, 403, ações)
def test_tela_perfis_ver_e_apertar(v, admin):
    pagina = admin.get("/visitas/atualizar")
    assert pagina.status_code == 200 and "Atualizar visitas" in pagina.text and "Desligada" in pagina.text
    assert "Ligar a agenda" in pagina.text and "Baixar de novo" in pagina.text
    ger = logar(v, admin, "ger.dois", "gerente")
    tg = ger.get("/visitas/atualizar")
    assert tg.status_code == 200 and 'action="/visitas/atualizar"' in tg.text
    for oculto in ("Ligar a agenda", "Baixar de novo", "Rodar diagnóstico", "Retomar"):
        assert oculto not in tg.text                                  # gerente só aperta o botão (4 A)
    dir_ = logar(v, admin, "dir.um", "diretor")
    td = dir_.get("/visitas/atualizar")
    assert td.status_code == 200 and 'action="/visitas/atualizar"' not in td.text
    assert logar(v, admin, "pre.um", "pre_venda").get("/visitas/atualizar").status_code == 403
    assert logar(v, admin, "pos.um", "pos_venda").get("/visitas/atualizar").status_code == 403


def test_tela_posts_403_por_perfil_e_sem_sessao(v, admin):
    sem = TestClient(admin.app, base_url="https://testserver")
    for url in ("/visitas/atualizar", "/visitas/refazer", "/visitas/retomar", "/visitas/diagnostico", "/visitas/agenda"):
        assert sem.post(url, data={}, follow_redirects=False).status_code == 303          # sem login: vai ao /login
    ger = logar(v, admin, "ger.tres", "gerente")
    csrf = token_form(ger, "/visitas/atualizar")
    for url in ("/visitas/refazer", "/visitas/retomar", "/visitas/diagnostico", "/visitas/agenda"):
        assert ger.post(url, data={"csrf": csrf, "de": "2026-11-26", "ate": "2026-11-26", "ligar": "1"}).status_code == 403
    ven = logar(v, admin, "ven.um", "vendas")
    assert ven.post("/visitas/atualizar", data={"csrf": token_form(ven, "/visitas/atualizar"),
                                                "de": "2026-11-26", "ate": "2026-11-27"}).status_code == 403
    assert admin.post("/visitas/agenda", data={"ligar": "1", "csrf": "errado"}).status_code == 403   # sem o CSRF
    assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"] is None


def test_gerente_pede_e_o_pedido_vai_ao_cron(v, admin, relogio):
    ger = logar(v, admin, "ger.quatro", "gerente")
    csrf = token_form(ger, "/visitas/atualizar")
    x = ger.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-27"}, follow_redirects=False)
    assert x.status_code == 303
    p = v.get("/api/visitas/trabalho", headers=H).json()["pedido"]
    assert p["de"] == "20261124" and p["ate"] == "20261127" and p["refazer"] is False and p["perfil"] == "gerente"
    assert "ger.quatro" not in json.dumps(p)
    assert "Já há um pedido" in ger.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-26", "ate": "2026-11-27"},
                                          follow_redirects=True).text
    # pedido que continua e encerra: 3 concessões do motivo pedido = o teto; o botão sai da fila no fim OK
    r = conceder(v, "pedido").json()
    assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"]["rodadas"] == 1
    fim(v, r["id"], "OK")
    assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"] is None


def test_periodo_do_pedido_validado_no_servidor(v, admin):
    csrf = token_form(admin, "/visitas/atualizar")
    for de, ate in (("2026-11-01", "2026-11-27"), ("2026-11-27", "2026-11-26"), ("2026-11-27", "2026-11-28"), ("x", "y")):
        admin.post("/visitas/atualizar", data={"csrf": csrf, "de": de, "ate": ate})
        assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"] is None, (de, ate)
    admin.post("/visitas/refazer", data={"csrf": csrf, "de": "2026-11-25", "ate": "2026-11-25"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"]["refazer"] is True


def test_agenda_so_liga_com_diagnostico_ok_e_pc_novo(v, admin, relogio):
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/agenda", data={"csrf": csrf, "ligar": "1"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["agenda"] == "desligada"        # diagnóstico pendente
    rodada_e_fim(v, relogio, "diagnostico", "OK")
    assert v.get("/api/visitas/trabalho", headers=H).json()["diagnostico"]["estado"] == "ok"
    admin.post("/visitas/agenda", data={"csrf": csrf, "ligar": "1"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["agenda"] == "desligada"        # PC novo ainda não confirmou
    ep = v.get("/api/visitas/lotes?desde=0", headers=HP).json()["epoca"]
    v.post("/api/visitas/lotes/confirmar", json={"epoca": ep, "fechados_pc": {}, "resultados": []}, headers=HP)
    admin.post("/visitas/agenda", data={"csrf": csrf, "ligar": "1"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["agenda"] == "ligada"
    assert "Desligar a agenda" in admin.get("/visitas/atualizar").text
    admin.post("/visitas/agenda", data={"csrf": csrf, "ligar": "0"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["agenda"] == "desligada"
    relogio["t"] += timedelta(hours=25)                                # o PC novo calou: a agenda não liga
    admin.post("/visitas/agenda", data={"csrf": csrf, "ligar": "1"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["agenda"] == "desligada"


def test_diagnostico_volta_a_pendente(v, admin, relogio):
    rodada_e_fim(v, relogio, "diagnostico", "MAXIMA_FORA")
    assert v.get("/api/visitas/trabalho", headers=H).json()["diagnostico"]["estado"] == "falhou"
    admin.post("/visitas/diagnostico", data={"csrf": token_form(admin, "/visitas/atualizar")})
    assert v.get("/api/visitas/trabalho", headers=H).json()["diagnostico"]["estado"] == "pendente"


def test_tela_mostra_o_ultimo_codigo_sem_print_e_o_limite(v, admin, relogio):
    rodada_e_fim(v, relogio, "agenda", "PARCIAL_VENDEDOR", erros_vendedor=1, dias_ok=["20261126"])
    t = admin.get("/visitas/atualizar").text
    assert "Código para o suporte: PARCIAL_VENDEDOR" in t and "Faltou a visita de 1 vendedor em 26/11. Peça de novo esse dia." in t
    assert "Parcial" in t
    assert "<img" not in t.split("<main")[1].split("</main>")[0]                 # nada de print da Máxima (6 B)
    for m in ("agenda", "agenda", "agenda", "pedido", "pedido", "pedido", "retentativa"):
        rodada_e_fim(v, relogio, m)
    t = admin.get("/visitas/atualizar").text
    assert "Limite de hoje" in t and "8 de 8" in t


def test_tela_pausada_mostra_o_texto_e_o_retomar_so_ao_admin(v, admin, relogio):
    r = conceder(v).json()
    fim(v, r["id"], "MAXIMA_CAPTCHA")
    t = admin.get("/visitas/atualizar").text
    assert "Desde " in t and "A Máxima pediu uma confirmação" in t and "Retomar" in t
    ger = logar(v, admin, "ger.cinco", "gerente")
    tg = ger.get("/visitas/atualizar").text
    assert "Desde " in tg and ">Retomar<" not in tg


# ---------------------------------------------------------------- /saude e disco
def test_saude_visitas_sem_dado_sensivel(v, relogio):
    s = v.get("/saude").json()
    assert s["visitas"] == {"agenda": "desligada", "diagnostico": "pendente", "ultima_rodada": None, "codigo": None,
                            "pausado": None, "rodada_ativa": None, "fase": None, "lotes_a_importar": 0,
                            "tentativas_hoje": 0, "lotes_sem_confirmar_vencidos": 0}
    r = conceder(v).json()
    v.post(f"/api/visitas/rodada/{r['id']}/progresso", json={"fase": "grade", "dia": "20261126", "feitos": 1, "total": 9}, headers=H)
    enviar(v, r["id"], lote(r["id"]))
    s = v.get("/saude").json()["visitas"]
    assert s["rodada_ativa"] == r["id"] and s["fase"] == "grade" and s["tentativas_hoje"] == 1 and s["lotes_a_importar"] == 1
    assert VTOKEN not in json.dumps(v.get("/saude").json())


def test_estado_em_disco_sem_segredo_nem_usuario(v, admin, relogio):
    rodada_e_fim(v, relogio, "agenda", "OK")
    admin.post("/visitas/atualizar", data={"csrf": token_form(admin, "/visitas/atualizar"), "de": "2026-11-27", "ate": "2026-11-27"})
    tudo = "".join(p.read_text(errors="ignore") for p in (v.app_dados / "visitas").iterdir() if p.is_file())
    assert VTOKEN not in tudo and "admin.teste" not in tudo and TOKEN not in tudo
    assert re.search(r'"perfil": "admin"', (v.app_dados / "visitas" / "pedidos.jsonl").read_text())


# ---------------------------------------------------------------- T-0045 v2: pareceres (código, UX, redundâncias)
def test_segunda_guarda_teto_total_de_descompressao_413(v, relogio, monkeypatch):
    """Zip com membros que somam mais que o teto: 413 com código, sem gravar (bomba de descompressão)."""
    r = conceder(v).json()
    monkeypatch.setattr(visitas, "DESCOMPRESSAO_MAX", 1000)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml", "<sst><si><t>" + "A" * 5000 + "</t></si></sst>")
    ex = b.getvalue()
    corpo = lote(r["id"], mudar=lambda c: c["arquivos"][0].update(sha256=hashlib.sha256(ex).hexdigest(), bytes=len(ex),
                                                                   b64=base64.b64encode(ex).decode()))
    x = enviar(v, r["id"], corpo)
    assert x.status_code == 413 and x.json() == {"erro": "lote grande demais", "codigo": "DESCOMPRESSAO_TETO"}
    assert v.get("/api/visitas/lotes", headers=HP).json()["linhas"] == []


def test_segunda_guarda_teto_somado_entre_arquivos_do_lote(monkeypatch):
    monkeypatch.setattr(visitas, "DESCOMPRESSAO_MAX", 3000)
    ex = xlsx(["A" * 1500])
    orc = [visitas.DESCOMPRESSAO_MAX]
    visitas.achar_no_excel(ex, orc)                                    # o primeiro cabe
    with pytest.raises(visitas.ErroVisitas) as e:
        for _ in range(3):
            visitas.achar_no_excel(ex, orc)                             # o total estoura, mesmo cada um sendo pequeno
    assert e.value.status == 413 and e.value.corpo["codigo"] == "DESCOMPRESSAO_TETO"


def test_segunda_guarda_membros_demais_413():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for i in range(visitas.ZIP_MEMBROS_MAX + 1):
            z.writestr(f"x/{i}.txt", "a")
    with pytest.raises(visitas.ErroVisitas) as e:
        visitas.achar_no_excel(b.getvalue())
    assert e.value.status == 413


def test_RN_VIS_007_segunda_guarda_le_celula_numerica_e_entidade_xml():
    def com(sheet, shared="<sst/>"):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("xl/sharedStrings.xml", shared)
            z.writestr("xl/worksheets/sheet1.xml", sheet)
        return b.getvalue()
    assert ("cpf", "") in visitas.achar_no_excel(com('<worksheet><c><v>12345678901</v></c></worksheet>'))
    assert ("email", "") in visitas.achar_no_excel(com("<w/>", "<sst><si><t>fulano&#64;exemplo.com.br</t></si></sst>"))
    assert ("telefone", "") in visitas.achar_no_excel(com('<w><is><t>(92) 99999-1234</t></is></w>'))
    assert visitas.achar_no_excel(com('<w><c><v>123456</v></c><c><v>1234.5</v></c></w>', "<sst><si><t>CLIENTE FICTICIO</t></si></sst>")) == []


def test_paridade_minima_dos_regex_com_o_contrato():
    """Os 4 regex são espelho dos `_RX_*` do visitas_nucleo (o teste de paridade na raiz compara o texto)."""
    assert visitas.RE_PESSOAL["email"].pattern == r"[\w.+-]+@[\w-]+(\.[\w-]+)+"
    assert visitas.TIPOS_ACHADO == ("email", "cnpj", "cpf", "telefone", "formato") and tuple(visitas.RE_PESSOAL) == visitas.TIPOS_ACHADO[:4]
    assert visitas.COLUNAS_PROIBIDAS == ("KM DIST", "BONIF", "OBSERVACAO")


def test_UX_pausa_desabilita_o_botao_e_escreve_o_motivo_uma_vez(v, admin, relogio):
    r = conceder(v).json()
    fim(v, r["id"], "MAXIMA_CONFIRMACAO")
    t = admin.get("/visitas/atualizar").text
    assert t.count("A Máxima pediu uma confirmação") == 1                      # a frase fica só na caixa vermelha
    assert "Pausou" in t and "motivo acima" not in t and t.count(">Retomar<") == 1
    assert re.search(r'<button type="submit" class="bt-neutro" disabled title="Pausado: o admin retoma antes.">Atualizar visitas', t)
    assert t.count('class="bt-principal"') == 1                                               # só o Retomar é principal
    assert "Código para o suporte: MAXIMA_CONFIRMACAO" in t and "Situação" in t
    assert "Pausado desde" not in t and t.count("Desde ") == 1                                 # a pausa não se repete (RD-0125)
    assert visitas.TRAVADO["pausado"] in t                                                     # a mesma redação do erro do servidor
    admin.post("/visitas/atualizar", data={"csrf": token_form(admin, "/visitas/atualizar"), "de": "2026-11-27", "ate": "2026-11-27"})
    assert v.get("/api/visitas/trabalho", headers=H).json()["pedido"] is None   # o servidor também recusa


def test_UX_tela_um_periodo_um_titulo_e_hora_num_formato_so(v, admin, relogio):
    rodada_e_fim(v, relogio, "agenda", "OK")
    t = admin.get("/visitas/atualizar").text
    corpo = t.split("<main")[1]
    assert corpo.count('name="de"') == 1 and corpo.count('name="ate"') == 1                    # um par De/Até
    assert 'formaction="/visitas/refazer"' in corpo and ">Baixar de novo<" in corpo
    assert "<h2>Período</h2>" in corpo and "<h2>Atualizar visitas</h2>" not in corpo
    assert "Acessos à Máxima hoje" in t and "Agenda diária" in t and "ENTRADAS" not in t
    assert re.search(r"27/11 0\dh\d\d", t) and not re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", corpo)


def test_UX_link_e_item_do_menu_so_para_admin_e_gerente(v, admin):
    ger = logar(v, admin, "ger.seis", "gerente")
    ven = logar(v, admin, "ven.dois", "vendas")
    assert 'href="/visitas/atualizar"' in ger.get("/").text and 'href="/visitas/atualizar"' in admin.get("/").text
    assert 'href="/visitas/atualizar"' not in ven.get("/").text                  # o vendedor não vê o atalho
    from app import render
    nav = lambda p: [i["nome"] for g in render.menu_lateral(p, {"vc_visitas": 1}, None) for i in g["itens"]]
    assert "Atualizar visitas" in nav("gerente") and "Atualizar visitas" not in nav("vendas")
    ativo = ger.get("/visitas/atualizar").text
    assert re.search(r'<a href="/visitas/atualizar" class="on" aria-current="page">Atualizar visitas', ativo)


def test_tela_do_admin_mostra_o_diagnostico_com_contagens_sem_nome_de_coluna(v, admin, relogio):
    medidas = {"tempos_s": {"login": 21.4, "maxgestao": 9.8, "filtros": 30.2, "vendedor": [44.0, 51.3]}, "fonte_pico": "cgroup",
               "chromium": "x", "espelho": {"colunas_fora": ["KM DIST", "BONIF", "OBSERVACAO"], "limpos": {"CLIENTE": 3, "JUSTIFICATIVA": 1}}}
    rodada_e_fim(v, relogio, "diagnostico", "OK", pico_mb=618.0, medidas=medidas, duracao_s=180)
    t = admin.get("/visitas/atualizar").text
    for esperado in ("Duração", "180 s", "618 MB", "21 s", "44 s e 51 s", "Colunas retiradas", "Células limpas", "Achados", "sem problema"):
        assert esperado in t, esperado
    assert "KM DIST" not in t and "BONIF" not in t                               # só a contagem
    ger = logar(v, admin, "ger.sete", "gerente")
    assert "Células limpas" not in ger.get("/visitas/atualizar").text           # o diagnóstico é do admin


def test_textos_com_acao_e_sem_jargao():
    for c, (_, txt) in visitas.CODIGOS.items():
        assert "Render" not in txt and "etapa" not in txt.lower() and "Excel com erro" not in txt, c
    assert visitas.texto_do_codigo("NADA_A_FAZER", {}) == "Já estava em dia."
    assert "2 vendedores" in visitas.texto_do_codigo("PARCIAL_VENDEDOR", {"erros_vendedor": 2, "dias": ["20261125"]})
    assert visitas.texto_do_codigo("MAXIMA_FORA", {"proxima": "06h30"}) == "A Máxima não respondeu. Tentamos de novo às 06h30."
    assert visitas.texto_do_codigo("SITE_FORA", {}) == "O site não respondeu. Tente mais tarde."
    assert set(visitas.STATUS_DO_CODIGO) == set(visitas.CODIGOS)


def test_formatadores_de_dia():
    assert visitas.dia_br("20261127") == "27/11"
    assert visitas.dia_iso("20261127") == "2026-11-27"
    assert visitas.ymd_do_form("27/11/2026") == "20261127" and visitas.ymd_do_form("2026-11-27") == "20261127"
    assert visitas.ymd_do_form("11/27/2026x") == "" and visitas.ymd_do_form(None) == ""
    assert visitas.dia_hora("2026-11-27T06:06:00-04:00") == "27/11 06h06" and visitas.dia_hora("lixo") == ""


def test_o_pedido_aceita_a_data_do_formulario_com_hifen(v, admin, relogio):
    admin.post("/visitas/atualizar", data={"csrf": token_form(admin, "/visitas/atualizar"), "de": "2026-11-26", "ate": "2026-11-27"})
    p = v.get("/api/visitas/trabalho", headers=H).json()["pedido"]
    assert p["de"] == "20261126" and p["ate"] == "20261127"


def test_UX_data_e_input_date_com_limite_e_o_servidor_aceita_aaaa_mm_dd(v, admin, relogio):
    t = admin.get("/visitas/atualizar").text.split("<main")[1]
    assert 'type="date" name="de" value="2026-11-21" max="2026-11-27"' in t        # calendário nativo, com limite
    admin.post("/visitas/atualizar", data={"csrf": token_form(admin, "/visitas/atualizar"), "de": "2026-11-26", "ate": "2026-11-27"})
    p = v.get("/api/visitas/trabalho", headers=H).json()["pedido"]
    assert p["de"] == "20261126" and p["ate"] == "20261127"
    from pathlib import Path
    js = "".join(f.read_text(encoding="utf-8") for f in (Path(visitas.__file__).parent / "static").glob("*.js"))
    assert "toLocaleDateString" not in js                                           # as datas em texto saem do servidor


def test_UX_diagnostico_fica_num_bloco_fechado_e_a_etapa_vira_palavra(v, admin, relogio):
    rodada_e_fim(v, relogio, "diagnostico", "OK", pico_mb=600.0, duracao_s=90)
    t = admin.get("/visitas/atualizar").text
    assert '<details class="vz-det"><summary>Detalhes do diagnóstico</summary>' in t and "<details class=\"vz-det\" open" not in t
    r = conceder(v).json()
    for fase, esperado in (("login", "Entrando na Máxima"), ("maxgestao", "Entrando na Máxima"),
                           ("grade", "Baixando o dia 26/11"), ("envio", "Enviando")):
        v.post(f"/api/visitas/rodada/{r['id']}/progresso", json={"fase": fase, "dia": "20261126", "feitos": 2, "total": 5}, headers=H)
        t = admin.get("/visitas/atualizar").text
        faixa = t.split("vz-faixa")[1][:260]
        assert esperado in faixa and fase not in faixa.lower().replace("baixando", "").replace("entrando", "")
    assert "(2 de 5)" in t


def test_site_descompressao_e_codigo_do_contrato_v1_1():
    assert visitas.STATUS_DO_CODIGO["DESCOMPRESSAO_TETO"] == "parcial" and "DESCOMPRESSAO_TETO" not in visitas.NOVA_TENTATIVA
    assert visitas.DESCOMPRESSAO_MAX == 50 * 1024 * 1024
    assert "Excel grande demais" in visitas.texto_do_codigo("DESCOMPRESSAO_TETO", {"dias": ["20261126"]})


# ---------------------------------------------------------------- lote 2: nenhum 2º login no dia (RN-VIS-005) e pedido parado
def trab(v):
    return v.get("/api/visitas/trabalho", headers=H).json()


def fechar_no_pc(v, dias):
    """O robô do PC confirma que fechou `dias` (cada um com a baixa na manhã seguinte)."""
    ep = v.get("/api/visitas/lotes?desde=0", headers=HP).json()["epoca"]
    pc = {d: f"{d[:4]}-{d[4:6]}-{int(d[6:]) + 1:02d}T07:00:00-04:00" for d in dias}
    assert v.post("/api/visitas/lotes/confirmar", json={"epoca": ep, "fechados_pc": pc, "resultados": []},
                  headers=HP).status_code == 200


@pytest.mark.parametrize("codigo", ["MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA", "MAXIMA_BLOQUEIO"])
def test_RN_VIS_005_retomar_e_diagnostico_no_mesmo_dia_nao_dao_2o_login(v, admin, relogio, codigo):
    r = conceder(v).json()
    fim(v, r["id"], codigo)
    assert trab(v)["login_barrado"] == {"dia": "20261127", "codigo": codigo}
    csrf = token_form(admin, "/visitas/atualizar")
    txt = admin.post("/visitas/retomar", data={"csrf": csrf}, follow_redirects=True).text
    assert "Retomado." in txt and "amanhã" not in txt.split("Sem acesso à Máxima hoje")[0]
    assert trab(v)["pausado"] is None                                  # o Retomar continua preciso e aceito
    txt = admin.post("/visitas/diagnostico", data={"csrf": csrf}, follow_redirects=True).text
    assert "Diagnóstico pedido." in txt and "Sem acesso à Máxima hoje" in txt          # a faixa, não o sufixo da resposta
    relogio["t"] += timedelta(hours=1)
    for motivo in ("diagnostico", "agenda", "pedido", "retentativa"):
        c = conceder(v, motivo)
        assert c.status_code == 429 and c.json() == {"erro": "login barrado hoje", "motivo": motivo}
    assert trab(v)["tentativas_hoje"]["total"] == 1                    # nenhuma tentativa nova foi gasta
    relogio["t"] += timedelta(days=1)                                  # amanhã tudo volta, sem ninguém mexer
    assert trab(v)["login_barrado"] is None
    assert conceder(v).status_code == 201


def test_RN_VIS_005_o_botao_do_pedido_fica_travado_e_a_tela_explica(v, admin, relogio):
    r = conceder(v).json()
    fim(v, r["id"], "MAXIMA_BLOQUEIO")
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/retomar", data={"csrf": csrf})
    t = visitas.Visitas(v.app_dados).tela(relogio["t"])
    assert t["pode_apertar"] is False and t["motivo_travado"] == visitas.TRAVADO["login"]
    pag = admin.get("/visitas/atualizar").text
    assert "Sem acesso à Máxima hoje" in pag and "Use o Atualizar visitas do PC; amanhã o site volta sozinho." in pag
    assert "recusou" not in pag.split("Últimas rodadas")[0]            # a faixa é neutra (vale também para a rodada parada no login)
    assert "Use o Atualizar visitas do PC" in pag and "disabled" in pag and "RN-" not in pag
    x = admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-26", "ate": "2026-11-27"}, follow_redirects=True)
    assert visitas.TRAVADO["login"] in x.text and trab(v)["pedido"] is None
    relogio["t"] += timedelta(days=1)
    assert visitas.Visitas(v.app_dados).tela(relogio["t"])["pode_apertar"] is True


def test_RN_VIS_005_fim_perdido_na_fase_login_vence_e_nao_ha_novo_login_as_06h30(v, relogio):
    relogio["t"] = datetime(2026, 11, 27, 6, 0, 0, tzinfo=MANAUS)
    r = conceder(v).json()                                             # a rodada some sem `fim`
    relogio["t"] += timedelta(minutes=30)                              # a concessão venceu; a agenda volta às 06h30
    c = conceder(v)
    assert c.status_code == 429 and c.json() == {"erro": "login barrado hoje", "motivo": "agenda"}
    assert trab(v)["login_barrado"] == {"dia": "20261127", "codigo": "RODADA_INTERROMPIDA"}
    assert visitas_rodadas(v)[0]["id"] == r["id"] and visitas_rodadas(v)[0]["codigo"] == "RODADA_INTERROMPIDA"
    relogio["t"] += timedelta(days=1)
    assert conceder(v).status_code == 201


def test_RN_VIS_005_vencida_na_fase_login_do_progresso_tambem_barra(v, relogio):
    r = conceder(v).json()
    assert v.post(f"/api/visitas/rodada/{r['id']}/progresso", json={"fase": "login"}, headers=H).status_code == 200
    relogio["t"] += timedelta(minutes=11)
    assert conceder(v).status_code == 429


def test_RN_VIS_005_vencida_em_fase_posterior_continua_com_nova_tentativa(v, relogio):
    r = conceder(v).json()
    assert v.post(f"/api/visitas/rodada/{r['id']}/progresso", json={"fase": "maxgestao"}, headers=H).status_code == 200
    relogio["t"] += timedelta(minutes=11)                              # o login foi confirmado: vale a nova tentativa
    assert conceder(v).status_code == 201
    assert trab(v)["login_barrado"] is None


def test_RN_VIS_005_o_dia_do_bloqueio_e_o_do_inicio_da_concessao(v, relogio):
    relogio["t"] = datetime(2026, 11, 27, 23, 55, 0, tzinfo=MANAUS)
    conceder(v)
    relogio["t"] += timedelta(minutes=10)                              # vence já em 28/11, mas a concessão é de 27/11
    assert trab(v)["login_barrado"] is None
    est = json.loads((v.app_dados / "visitas" / "estado.json").read_text())
    assert est["login_barrado"]["dia"] == "20261127"
    assert conceder(v).status_code == 201                              # 28/11 não está barrado


def test_RN_VIS_005_codigo_comum_nao_barra_o_login(v, relogio):
    rodada_e_fim(v, relogio, "agenda", "MAXIMA_FORA")
    assert trab(v)["login_barrado"] is None
    assert conceder(v).status_code == 201


def test_RN_VIS_004_pedido_sem_dia_a_baixar_nao_entra_na_fila(v, admin, relogio):
    fechar_no_pc(v, ["20261124", "20261125"])
    csrf = token_form(admin, "/visitas/atualizar")
    x = admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-25"}, follow_redirects=True)
    assert "24/11 a 25/11 já estão em dia." in x.text and trab(v)["pedido"] is None
    assert "nada a baixar" not in x.text                               # a mensagem já diz; a 1ª linha da lista não repete
    ult = visitas_rodadas(v)[0]
    assert ult["motivo"] == "pedido" and ult["codigo"] == "NADA_A_FAZER" and ult["status"] == "ok" and ult["dias"] == []
    assert re.match(r"^P\d{8}T\d{6}$", ult["id"]) and ult["em"] == "2026-11-27T09:00:00-04:00"
    assert "perfil" in (v.app_dados / "visitas" / "pedidos.jsonl").read_text()          # o pedido fica registrado
    assert trab(v)["tentativas_hoje"]["total"] == 0                                      # nenhum login gasto
    pag = admin.get("/visitas/atualizar").text
    assert "Pedido de 24/11 a 25/11: nada a baixar." in pag and ult["de"] == "20261124" and ult["ate"] == "20261125"
    y = admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-26", "ate": "2026-11-27"}, follow_redirects=True)
    assert "Pedido enviado." in y.text and trab(v)["pedido"]["de"] == "20261126"        # a fila não ficou presa


def test_RN_VIS_004_pedido_na_fila_que_ficou_sem_dia_sai_e_o_novo_e_aceito(v, admin, relogio):
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-25"})
    pid = trab(v)["pedido"]["id"]
    fechar_no_pc(v, ["20261124", "20261125"])                          # o PC fechou os dias depois do pedido
    assert trab(v)["pedido"] is None
    ult = visitas_rodadas(v)[0]
    assert ult["id"] == pid and ult["codigo"] == "NADA_A_FAZER" and ult["motivo"] == "pedido"
    assert trab(v)["tentativas_hoje"]["total"] == 0
    relogio["t"] += timedelta(seconds=2)                               # o id do pedido é a hora: nunca repete
    y = admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-26", "ate": "2026-11-27"}, follow_redirects=True)
    assert "Pedido enviado." in y.text and trab(v)["pedido"]["id"] != pid


def test_RN_VIS_004_pedido_com_dia_aberto_continua_na_fila(v, admin, relogio):
    fechar_no_pc(v, ["20261124"])
    admin.post("/visitas/atualizar", data={"csrf": token_form(admin, "/visitas/atualizar"),
                                           "de": "2026-11-24", "ate": "2026-11-25"})
    assert trab(v)["pedido"]["de"] == "20261124"
    assert not (v.app_dados / "visitas" / "rodadas.jsonl").exists()


def test_RN_VIS_004_pedido_refazer_sai_quando_a_nuvem_refez_os_dias_depois_do_pedido(v, admin, relogio):
    fechar_no_pc(v, ["20261124", "20261125"])
    relogio["t"] = datetime(2026, 11, 27, 6, 0, 0, tzinfo=MANAUS)
    admin.post("/visitas/refazer", data={"csrf": token_form(admin, "/visitas/atualizar"),
                                         "de": "2026-11-24", "ate": "2026-11-25"})
    assert trab(v)["pedido"]["refazer"] is True                        # `refazer` ignora o dia fechado: fica na fila
    relogio["t"] = datetime(2026, 11, 27, 9, 0, 0, tzinfo=MANAUS)
    r = conceder(v, "pedido", ("20261124", "20261125")).json()
    assert enviar(v, r["id"], lote(r["id"], dia="20261124"), dia="20261124").status_code == 200      # baixado_em 06h07, depois do pedido
    assert enviar(v, r["id"], lote(r["id"], dia="20261125"), dia="20261125").status_code == 200
    fim(v, r["id"], "PARCIAL_TEMPO")                                   # este código manteria o pedido na fila
    assert trab(v)["pedido"] is None                                   # mas os dois dias já foram refeitos: não repete
    ult = visitas_rodadas(v)[0]
    assert ult["codigo"] == "NADA_A_FAZER" and ult["id"].startswith("P")



def test_RN_VIS_004_situacao_e_saude_ignoram_o_pedido_sem_dia(v, admin, relogio):
    fechar_no_pc(v, ["20261124"])
    csrf = token_form(admin, "/visitas/atualizar")
    assert "Em dia" not in admin.get("/visitas/atualizar").text.split("Últimas rodadas")[0]       # sem rodada real: "—"
    admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-24"})
    pag = admin.get("/visitas/atualizar").text
    assert "Pedido de 24/11: nada a baixar." in pag and "Em dia" not in pag.split("Últimas rodadas")[0]
    assert visitas.Visitas(v.app_dados).saude(relogio["t"])["codigo"] is None
    relogio["t"] += timedelta(seconds=2)
    rodada_e_fim(v, relogio, "agenda", "MAXIMA_FORA")
    relogio["t"] += timedelta(seconds=2)
    admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-24"})   # outro pedido sem dia
    sa = visitas.Visitas(v.app_dados).saude(relogio["t"])
    assert sa["codigo"] == "MAXIMA_FORA"                                # a última rodada REAL, não a do pedido
    assert "Erro" in admin.get("/visitas/atualizar").text.split("Últimas rodadas")[0]


def test_RN_VIS_005_primeira_linha_da_lista_nao_repete_o_texto_do_login_barrado(v, admin, relogio):
    r = conceder(v).json()
    fim(v, r["id"], "MAXIMA_BLOQUEIO")
    admin.post("/visitas/retomar", data={"csrf": token_form(admin, "/visitas/atualizar")})
    pag = admin.get("/visitas/atualizar").text
    lista = pag.split("Últimas rodadas")[1]
    assert "Código para o suporte: MAXIMA_BLOQUEIO" in lista and "A Máxima bloqueou o acesso do site" not in lista
    assert visitas.Visitas(v.app_dados).tela(relogio["t"])["login_barrado"] == {"dia": "20261127", "codigo": "MAXIMA_BLOQUEIO"}


def test_RN_VIS_005_a_marca_vai_para_a_primeira_rodada_real_mesmo_com_pedido_sem_dia_no_topo(v, admin, relogio):
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-25"})   # fica na fila
    r = conceder(v, "agenda").json()
    fim(v, r["id"], "MAXIMA_BLOQUEIO")
    admin.post("/visitas/retomar", data={"csrf": csrf})
    fechar_no_pc(v, ["20261124", "20261125"])                          # o pedido sai da fila: a linha dele fica no topo
    lista = admin.get("/visitas/atualizar").text.split("Últimas rodadas")[1]
    assert lista.index("nada a baixar") < lista.index("MAXIMA_BLOQUEIO")
    assert "A Máxima bloqueou o acesso do site" not in lista


def test_RN_VIS_004_mensagem_de_outra_acao_nao_apaga_o_texto_do_pedido_sem_dia(v, admin, relogio):
    fechar_no_pc(v, ["20261124", "20261125"])
    csrf = token_form(admin, "/visitas/atualizar")
    admin.post("/visitas/atualizar", data={"csrf": csrf, "de": "2026-11-24", "ate": "2026-11-25"})
    outra = admin.post("/visitas/diagnostico", data={"csrf": csrf}, follow_redirects=True).text
    assert "Diagnóstico pedido." in outra and "Pedido de 24/11 a 25/11: nada a baixar." in outra
