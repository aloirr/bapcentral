"""Testes da rotina diaria (T-0018, ADR 0002, regra 11 nova; R-20261124-214958-alexandre).

Os 5 limites (funcoes puras), o ``--diario`` ponta a ponta com a rede
substituida por monkeypatch, o ``--primeira-vez`` e o agendamento.
Sem rede, sem OneDrive, sem dado pessoal; tudo em ``tmp_path``.
O modo manual (trava 2 pela linha de comando, troca com restauracao, backup
por hash) ja esta coberto em ``test_atualizar_do_github.py`` (T-0003) e nao
se repete aqui.
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath

import pytest

import atualizar_do_github as atu

MANAUS = timezone(timedelta(hours=-4))
AGORA = datetime(2026, 11, 25, 6, 30, tzinfo=MANAUS)
SHA = "a" * 40
HEAD = "b" * 40
T_COMMIT = AGORA - timedelta(hours=9)


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """Qualquer conexao de rede derruba o teste (a API e o site vem por monkeypatch)."""
    import socket

    def proibido(*_a, **_k):
        raise AssertionError("teste da T-0018 tentou usar a rede")

    monkeypatch.setattr(socket.socket, "connect", proibido)
    monkeypatch.setattr(socket, "create_connection", proibido)


# --------------------------------------------------------------------------
# Limite 1: commit com 2 h ou mais
# --------------------------------------------------------------------------

def test_T0018_limite_1_commit_com_2h_passa():
    assert atu.commit_maduro(AGORA - timedelta(hours=2), AGORA)
    assert atu.commit_maduro(AGORA - timedelta(days=1), AGORA)


def test_T0018_limite_1_commit_novo_nao_passa():
    assert not atu.commit_maduro(AGORA - timedelta(hours=1, minutes=59), AGORA)
    assert not atu.commit_maduro(AGORA + timedelta(minutes=5), AGORA)  # futuro


def test_T0018_limite_1_data_iso_da_api_em_utc():
    d = atu.data_iso("2026-11-25T08:30:00Z")
    assert d == datetime(2026, 11, 25, 4, 30, tzinfo=MANAUS)
    assert atu.commit_maduro(d, AGORA)          # 06h30 - 04h30 = 2 h


def test_T0018_limite_1_data_sem_fuso_e_erro():
    with pytest.raises(ValueError):
        atu.commit_maduro(datetime(2026, 11, 25), AGORA)


# --------------------------------------------------------------------------
# Limite 2: CI verde no PR de origem
# --------------------------------------------------------------------------

def _pr(n, merge_sha, merged=True, base="main"):
    return {"number": n, "merged_at": "2026-11-24T20:00:00Z" if merged else None,
            "merge_commit_sha": merge_sha, "base": {"ref": base},
            "head": {"sha": HEAD}}


def test_T0018_limite_2_pr_de_origem_pelo_merge_commit():
    pulls = [_pr(1, "c" * 40), _pr(2, SHA), _pr(3, SHA, merged=False)]
    assert atu.pr_de_origem(pulls, SHA)["number"] == 2


def test_T0018_limite_2_sem_pr_proprio_mesclado_no_main_nao_vale():
    """Commit sem PR proprio nao herda o CI verde de outro PR (revisao PR #59)."""
    assert atu.pr_de_origem([_pr(1, "c" * 40)], SHA) is None
    assert atu.pr_de_origem([], SHA) is None
    assert atu.pr_de_origem([_pr(3, SHA, merged=False)], SHA) is None
    assert atu.pr_de_origem([_pr(4, SHA, base="outro")], SHA) is None


def test_T0018_limite_2_ci_verde():
    runs = [{"name": "conferir", "status": "completed", "conclusion": "success"},
            {"name": "extra", "status": "completed", "conclusion": "skipped"}]
    assert atu.ci_verde(runs) == (True, "verde")


@pytest.mark.parametrize("runs", [
    [],
    [{"name": "conferir", "status": "in_progress", "conclusion": None}],
    [{"name": "conferir", "status": "completed", "conclusion": "failure"}],
    [{"name": "conferir", "status": "completed", "conclusion": "cancelled"}],
    [{"name": "conferir", "status": "completed", "conclusion": "skipped"}],
])
def test_T0018_limite_2_ci_nao_verde(runs):
    ok, motivo = atu.ci_verde(runs)
    assert not ok and motivo


# --------------------------------------------------------------------------
# Limite 3: versao da web no main = /saude
# --------------------------------------------------------------------------

def test_T0018_limite_3_versao_do_init():
    assert atu.versao_do_init('"""web"""\nVERSAO = "0.2.0"\n') == "0.2.0"
    assert atu.versao_do_init("VERSAO = '1.0.1'") == "1.0.1"
    assert atu.versao_do_init("X = 1") is None


def test_T0018_limite_3_versoes_batem():
    assert atu.versoes_batem("0.2.0", "0.2.0")
    assert not atu.versoes_batem("0.3.0", "0.2.0")
    assert not atu.versoes_batem("0.2.0", None)
    assert not atu.versoes_batem(None, "0.2.0")


# --------------------------------------------------------------------------
# Limite 4: janela 06h00-07h30 Manaus e robo parado
# --------------------------------------------------------------------------

@pytest.mark.parametrize("hm,dentro", [
    ((5, 59), False), ((6, 0), True), ((6, 30), True), ((7, 30), True),
    ((7, 31), False), ((14, 0), False),
])
def test_T0018_limite_4_janela_manaus(hm, dentro):
    assert atu.dentro_da_janela(AGORA.replace(hour=hm[0], minute=hm[1])) is dentro


def test_T0018_limite_4_janela_converte_utc_para_manaus():
    utc = datetime(2026, 11, 25, 10, 30, tzinfo=timezone.utc)   # 06h30 Manaus
    assert atu.dentro_da_janela(utc)
    assert not atu.dentro_da_janela(datetime(2026, 11, 25, 6, 30, tzinfo=timezone.utc))


def test_T0018_limite_4_robo_rodando():
    assert not atu.robo_rodando(None)
    assert atu.robo_rodando(60)
    assert atu.robo_rodando(-5)                      # relogio torto: conservador
    assert not atu.robo_rodando(4 * 3600)            # trava presa (regra do robo)


def test_T0018_limite_4_idade_trava_sem_ler_conteudo(tmp_path):
    assert atu.idade_trava_robo(tmp_path, 1000.0) is None
    trava = tmp_path / atu.TRAVA_ROBO_REL
    trava.parent.mkdir(parents=True)
    trava.write_text("x", encoding="utf-8")
    os.utime(trava, (900.0, 900.0))
    assert atu.idade_trava_robo(tmp_path, 1000.0) == pytest.approx(100.0)


# --------------------------------------------------------------------------
# Exclusoes do --diario, log, versao, agendamento
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nome", [
    "instalar_bap.bat", "INSTALAR_PDF.bat", "REPARAR_PYTHON_BAP.bat",
    "VERIFICAR_REQUISITOS.bat", "ATUALIZAR_DO_GITHUB.bat",
    "INSTALAR_ROTINA_DIARIA.bat", "atualizar_do_github.py", "tarefa_bap.xml",
    "meta_config.json",
])
def test_T0018_diario_nunca_instala_instaladores_e_configs(nome):
    assert atu.so_com_instale(PurePath(nome))


def test_T0018_diario_instala_programas_comuns():
    assert not atu.so_com_instale(PurePath("bap_central.py"))
    assert not atu.so_com_instale(PurePath("executar_bap.bat"))


def test_RN_6_T0018_linha_log_sem_dado_pessoal():
    linha = atu.linha_log(AGORA, "diario", 11, "limite 2:\n CI  x", SHA)
    assert linha == "2026-11-25 06:30:00 | diario | codigo 11 | main aaaaaaa | limite 2: CI x"


def test_T0018_versao_instalada_ida_e_volta():
    texto = atu.texto_versao_instalada(SHA, AGORA, 3, "diario")
    assert texto.splitlines()[0] == SHA
    assert atu.sha_do_texto_versao(texto) == SHA
    assert atu.sha_do_texto_versao("lixo") is None


def test_T0018_agendar_0630_usuario_atual():
    cmd = atu.comando_agendar(Path("C:/BAP/Regionais - Leandro"))
    assert cmd[:2] == ["schtasks", "/Create"]
    assert cmd[cmd.index("/ST") + 1] == "06:30"
    assert cmd[cmd.index("/SC") + 1] == "DAILY"
    assert "/RU" not in cmd and "/RP" not in cmd       # usuario atual, sem senha
    tr = cmd[cmd.index("/TR") + 1]
    assert tr.endswith('atualizar_do_github.py" --diario') and tr.startswith("py -3.12 ")


def test_T0018_agendar_caminho_longo_e_erro():
    with pytest.raises(ValueError):
        atu.comando_agendar(Path("C:/" + "x" * 300))


def test_T0018_agendar_remover():
    assert atu.comando_remover()[:2] == ["schtasks", "/Delete"]


# --------------------------------------------------------------------------
# --diario ponta a ponta (rede por monkeypatch)
# --------------------------------------------------------------------------

def _zip_main(caminho: Path, arquivos: dict[str, bytes], sha: str, versao: str,
              quando: datetime, comentario: str | None = None) -> None:
    dt = quando.astimezone(timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(zipfile.ZipInfo(f"bapcentral-{sha}/{nome}", dt), dados)
        z.writestr(zipfile.ZipInfo(f"bapcentral-{sha}/web/app/__init__.py", dt),
                   f'VERSAO = "{versao}"\n')
        z.comment = (sha if comentario is None else comentario).encode()


def _commit(sha: str, data: datetime) -> dict:
    """Item da API de commits (``/commits/main`` e ``/commits?sha=main``), data em UTC."""
    return {"sha": sha, "commit": {"committer": {
        "date": data.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}}


@pytest.fixture
def rede(monkeypatch, tmp_path):
    """API falsa. Altere ``estado`` no teste para cada cenario."""
    estado = {
        "cota": 60, "sha": SHA, "data": T_COMMIT, "pulls": [_pr(7, SHA)],
        "runs": [{"name": "conferir", "status": "completed", "conclusion": "success"}],
        "versao_main": "0.2.0", "versao_site": "0.2.0",
        "arquivos": {"bap_central.py": b"novo\n", "instalar_bap.bat": b"novo bat\n"},
        "chamadas": [], "comentario": None, "fora_do_ar": False,
        # T-0056: HEAD do main (None = o proprio ``sha``) e a lista de commits
        # (None = so o HEAD). ``sha`` segue sendo o commit do zip e dos pulls.
        "head": None, "data_head": None, "lista": None, "lista_fora_do_ar": False,
    }

    def get_json(url, timeout=30):
        estado["chamadas"].append(url)
        if estado["fora_do_ar"]:
            raise atu.ErroApi("HTTP 503")
        if url.endswith("/rate_limit"):
            return {"resources": {"core": {"remaining": estado["cota"]}}}
        cabeca = _commit(estado["head"] or estado["sha"], estado["data_head"] or estado["data"])
        if url.endswith("/commits/main"):
            return cabeca
        if "/commits?sha=main" in url:                     # T-0056
            if estado["lista_fora_do_ar"]:
                raise atu.ErroApi("HTTP 503")
            return [cabeca] if estado["lista"] is None else estado["lista"]
        if url.endswith("/pulls"):
            return estado["pulls"]
        if "/check-runs" in url:
            return {"check_runs": estado["runs"]}
        raise AssertionError(url)

    original = atu.baixar_main
    monkeypatch.setattr(atu, "_get_json", get_json)
    monkeypatch.setattr(atu, "versao_do_site", lambda: estado["versao_site"])
    monkeypatch.setattr(atu, "baixar_main",
                        lambda destino, url, info=None: _baixar(original, estado,
                                                                tmp_path, destino, url, info))
    return estado


def _baixar(original, estado, tmp_path, destino, url, info):
    assert url.endswith(f"{estado['sha']}.zip")
    arq = tmp_path / "falso.zip"
    _zip_main(arq, estado["arquivos"], estado["sha"], estado["versao_main"], estado["data"],
              estado["comentario"])
    return original(destino, arq.resolve().as_uri(), info)


@pytest.fixture
def producao(tmp_path):
    p = tmp_path / "producao"
    p.mkdir()
    for nome, dados in (("bap_central.py", b"velho\n"), ("instalar_bap.bat", b"velho bat\n")):
        f = p / nome
        f.write_bytes(dados)
        velho = (T_COMMIT - timedelta(days=3)).timestamp()
        os.utime(f, (velho, velho))
    (p / "meta_config.json").write_bytes(b'{"digitado": 1}')
    return p


def _log(producao: Path) -> list[str]:
    arq = producao / atu.ARQ_LOG_REL
    return arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []


def test_RN_11_T0018_diario_instala_com_os_5_limites_e_backup(rede, producao):
    cod = atu.rodar_diario(producao, agora=AGORA)
    assert cod == atu.CODIGO_OK
    assert (producao / "bap_central.py").read_bytes() == b"novo\n"
    assert (producao / "instalar_bap.bat").read_bytes() == b"velho bat\n"   # so com instale
    assert (producao / "meta_config.json").read_bytes() == b'{"digitado": 1}'
    assert atu.sha_instalado(producao) == SHA
    backup = producao / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "ANTES_DIARIO_NOV2026"
    assert (backup / "bap_central.py").read_bytes() == b"velho\n"
    linhas = _log(producao)
    assert len(linhas) == 1 and "codigo 0" in linhas[0]
    assert "bap_central.py" in linhas[0] and "pendente de instale: instalar_bap.bat" in linhas[0]
    assert len(rede["chamadas"]) <= 4                    # cota de 60/h


def test_T0018_diario_mesmo_sha_ja_instalado_nao_baixa(rede, producao):
    atu.gravar_versao(producao, SHA, AGORA, 0, "diario")
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_OK
    assert (producao / "bap_central.py").read_bytes() == b"velho\n"
    assert not any("pulls" in u for u in rede["chamadas"])


def _sem_troca(producao: Path) -> bool:
    return ((producao / "bap_central.py").read_bytes() == b"velho\n"
            and not (producao / atu.ARQ_VERSAO_REL).exists())


@pytest.mark.parametrize("mexe,codigo", [
    pytest.param(lambda e: e.update(data=AGORA - timedelta(hours=1)),
                 atu.CODIGO_LIMITE_IDADE, id="limite_1_commit_com_1h"),
    pytest.param(lambda e: e.update(pulls=[]), atu.CODIGO_LIMITE_CI,
                 id="limite_2_sem_pr"),
    pytest.param(lambda e: e.update(pulls=[_pr(7, "c" * 40)]), atu.CODIGO_LIMITE_CI,
                 id="limite_2_pr_de_outro_commit"),
    pytest.param(lambda e: e.update(runs=[{"name": "conferir", "status": "completed",
                                           "conclusion": "failure"}]),
                 atu.CODIGO_LIMITE_CI, id="limite_2_ci_vermelho"),
    pytest.param(lambda e: e.update(versao_main="0.3.0"), atu.CODIGO_LIMITE_VERSAO_WEB,
                 id="limite_3_versao_diferente"),
    pytest.param(lambda e: e.update(versao_site=None), atu.CODIGO_LIMITE_VERSAO_WEB,
                 id="limite_3_site_sem_resposta"),
    pytest.param(lambda e: e.update(cota=2), atu.CODIGO_API, id="api_sem_cota"),
    pytest.param(lambda e: e.update(fora_do_ar=True), atu.CODIGO_API,
                 id="api_fora_do_ar"),
])
def test_T0018_diario_limite_falho_nao_troca_nada(rede, producao, mexe, codigo):
    mexe(rede)
    assert atu.rodar_diario(producao, agora=AGORA) == codigo
    assert _sem_troca(producao)
    linhas = _log(producao)
    assert len(linhas) == 1 and f"codigo {codigo}" in linhas[0]


def test_T0018_limite_4_diario_fora_da_janela_nem_consulta_a_api(rede, producao):
    cod = atu.rodar_diario(producao, agora=AGORA.replace(hour=8))
    assert cod == atu.CODIGO_LIMITE_JANELA and rede["chamadas"] == []
    assert _sem_troca(producao)


def test_T0018_limite_4_diario_robo_rodando(rede, producao):
    trava = producao / atu.TRAVA_ROBO_REL
    trava.parent.mkdir(parents=True)
    trava.write_text("x", encoding="utf-8")
    t = (AGORA - timedelta(minutes=10)).timestamp()
    os.utime(trava, (t, t))
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_LIMITE_ROBO
    assert rede["chamadas"] == [] and _sem_troca(producao)


def test_T0018_diario_pausado(rede, producao):
    pausa = producao / atu.ARQ_PAUSA_REL
    pausa.parent.mkdir(parents=True)
    pausa.write_text("", encoding="utf-8")
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_PAUSA
    assert _sem_troca(producao)


def test_T0018_limite_5_diario_instalado_por_fora(rede, producao):
    f = producao / "bap_central.py"
    t = (T_COMMIT + timedelta(hours=1)).timestamp()
    os.utime(f, (t, t))
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_TRAVA
    assert _sem_troca(producao)
    assert "limite 5: instalado por fora: bap_central.py" in _log(producao)[0]


@pytest.mark.parametrize("comentario", ["c" * 40, ""])
def test_T0018_diario_zip_de_outro_commit_ou_sem_comentario(rede, producao, comentario):
    rede["comentario"] = comentario
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_ERRO
    assert _sem_troca(producao)
    assert "codigo 1 " in _log(producao)[0]


def test_RN_11_T0018_diario_falha_na_troca_restaura(rede, producao, monkeypatch):
    real = atu._copiar_atomico

    def quebra(fonte, destino, mtime):
        if mtime is not None:              # a troca (a restauracao passa None)
            raise OSError("disco cheio")
        return real(fonte, destino, mtime)

    monkeypatch.setattr(atu, "_copiar_atomico", quebra)
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_TROCA
    assert _sem_troca(producao)
    assert "codigo 4" in _log(producao)[0]


def test_RN_4_T0018_diario_backup_com_mes_de_manaus(rede, producao):
    utc = datetime(2026, 12, 1, 10, 30, tzinfo=timezone.utc)   # 06h30 de 01/12 em Manaus
    rede["data"] = utc - timedelta(hours=9)
    assert atu.rodar_diario(producao, agora=utc) == atu.CODIGO_OK
    assert (producao / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "ANTES_DIARIO_DEZ2026").is_dir()


def test_RN_10_T0018_diario_simular_nao_grava(rede, producao):
    assert atu.rodar_diario(producao, simular=True, agora=AGORA) == atu.CODIGO_OK
    assert _sem_troca(producao)
    assert not (producao / "SISTEMA BAP").exists()          # nem backup, nem log


def test_T0018_diario_nao_aceita_origem(tmp_path):
    assert atu.main(["--diario", "--origem", str(tmp_path),
                     "--producao", str(tmp_path)]) == atu.CODIGO_ERRO


# --------------------------------------------------------------------------
# --primeira-vez
# --------------------------------------------------------------------------

def _origem(tmp_path: Path) -> Path:
    o = tmp_path / "origem"
    o.mkdir()
    (o / "bap_central.py").write_bytes(b"novo\n")
    t = T_COMMIT.timestamp()
    os.utime(o / "bap_central.py", (t, t))
    return o


def test_T0018_primeira_vez_exige_confirmar(tmp_path, producao):
    cod = atu.main(["--primeira-vez", "--origem", str(_origem(tmp_path)),
                    "--producao", str(producao)])
    assert cod == atu.CODIGO_ERRO and _sem_troca(producao)


def test_T0018_primeira_vez_nao_combina_com_diario(tmp_path, producao):
    assert atu.main(["--primeira-vez", "--diario", "--confirmar",
                     "--producao", str(producao)]) == atu.CODIGO_ERRO


def test_T0018_primeira_vez_ignora_trava_5_com_backup_total(tmp_path, producao):
    f = producao / "bap_central.py"
    t = (T_COMMIT + timedelta(hours=1)).timestamp()
    os.utime(f, (t, t))                                  # dispararia a trava 5
    (producao / "outro.py").write_bytes(b"so na producao\n")
    cod = atu.main(["--primeira-vez", "--confirmar", "--origem", str(_origem(tmp_path)),
                    "--producao", str(producao)])
    assert cod == atu.CODIGO_OK
    assert f.read_bytes() == b"novo\n"
    backups = list((producao / "SISTEMA BAP" / "BACKUP_RELATORIOS").iterdir())
    assert len(backups) == 1 and backups[0].name.startswith("ANTES_PRIMEIRA_VEZ_")
    guardados = {p.name: _h(p.read_bytes()) for p in backups[0].iterdir()}
    assert guardados == {"bap_central.py": _h(b"velho\n"),
                         "instalar_bap.bat": _h(b"velho bat\n"),
                         "outro.py": _h(b"so na producao\n")}
    assert (producao / "meta_config.json").read_bytes() == b'{"digitado": 1}'

