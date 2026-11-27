"""T-0057: a janela do robo mostra o andamento e o log recebe as mesmas linhas.

Pedido do Alexandre (R-20261127-162233-alexandre): "mostrar o andamento na tela,
alem de gravar no log". O executar_bap.bat chama `bap_automation.py --espelho "%LOG%"`;
o main() roda o proprio robo como filho (`rodar_com_espelho`) e `espelhar_linhas`
copia cada linha, em bytes, para a tela e para o log (aberto em "ab"). As linhas do
.bat passam pela sub-rotina `:linha` (echo na tela e no log).

Sem rede e sem dado pessoal: o filho e um `python -c` com texto ficticio.
"""
import io
import re
import sys
from pathlib import Path

import pytest

import bap_automation as ba

_AQUI = Path(__file__).resolve().parent.parent
RAIZ = _AQUI if (_AQUI / "bap_automation.py").exists() else Path.cwd()
BAT = RAIZ / "executar_bap.bat"


class _Fluxo(io.BytesIO):
    """BytesIO que conta os flush (o espelho tem de dar flush a cada linha)."""

    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


# ---------------------------------------------------------------- 1. espelhar_linhas
def test_T0057_log_recebe_as_mesmas_linhas_da_tela():
    linhas = ["Início da coleta\r\n".encode("utf-8"),
              "Relatório de preços: ação concluída\r\n".encode("utf-8"),
              b"linha sem quebra final"]
    tela, log = _Fluxo(), _Fluxo()
    ba.espelhar_linhas(iter(linhas), [tela, log])
    assert tela.getvalue() == log.getvalue() == b"".join(linhas)
    assert tela.flushes >= len(linhas) and log.flushes >= len(linhas)


# ---------------------------------------------------------------- 2. filho real
_FILHO = (
    "import sys\n"
    "sys.stdout.buffer.write('andamento: relatório 1 de 2\\r\\n'.encode('utf-8')); sys.stdout.flush()\n"
    "sys.stderr.buffer.write('aviso: ação demorada\\r\\n'.encode('utf-8')); sys.stderr.flush()\n"
    "sys.stdout.buffer.write(b'andamento: fim\\r\\n'); sys.stdout.flush()\n"
    "sys.exit({codigo})\n"
)


def _rodar_filho(tmp_path, codigo):
    log = tmp_path / "agendador.log"
    antigo = "rodada anterior: FIM - codigo de saida: 0\r\n".encode("utf-8")
    log.write_bytes(antigo)
    tela = io.BytesIO()
    rc = ba.rodar_com_espelho([sys.executable, "-c", _FILHO.format(codigo=codigo)],
                              str(log), tela=tela)
    return rc, tela.getvalue(), antigo, log.read_bytes()


@pytest.mark.parametrize("codigo", [0, 3])
def test_T0057_codigo_de_saida_do_robo_se_preserva_e_log_igual_a_tela(tmp_path, codigo):
    rc, tela, antigo, conteudo = _rodar_filho(tmp_path, codigo)
    assert rc == codigo
    assert conteudo == antigo + tela, "log antigo alterado ou tela e log divergem"
    texto = tela.decode("utf-8")
    assert "relatório 1 de 2" in texto and "ação demorada" in texto and "andamento: fim" in texto
    assert "\r\n" in texto


def test_T0057_filho_sem_buffer_e_em_utf8(tmp_path):
    capturado = {}

    class _Proc:
        stdout = iter([])
        returncode = 0

        def wait(self):
            return 0

    def popen_falso(*_a, **kw):
        capturado.update(kw)
        return _Proc()

    rc = ba.rodar_com_espelho(["robo"], str(tmp_path / "agendador.log"),
                              tela=io.BytesIO(), popen=popen_falso)
    assert rc == 0
    env = capturado["env"]
    assert env.get("PYTHONUNBUFFERED") == "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"


# ---------------------------------------------------------------- 3. falha ao iniciar
def test_T0057_falha_ao_iniciar_o_robo_aparece_na_tela_e_no_log(tmp_path):
    def popen_quebrado(*_a, **_k):
        raise OSError("executavel ficticio ausente")

    log = tmp_path / "agendador.log"
    log.write_bytes(b"antes\r\n")
    tela = io.BytesIO()
    rc = ba.rodar_com_espelho(["nao-existe"], str(log), tela=tela, popen=popen_quebrado)
    assert rc == 1
    assert b"FALHA ao iniciar o robo" in tela.getvalue()
    assert log.read_bytes() == b"antes\r\n" + tela.getvalue()


# ---------------------------------------------------------------- 4. _sem_espelho
def test_T0057_sem_espelho_tira_o_par_e_mantem_a_ordem():
    assert ba._sem_espelho(["--simular", "--espelho", "x.log", "--relatorio", "precos"]) == \
        ["--simular", "--relatorio", "precos"]
    assert ba._sem_espelho(["--espelho=x.log", "--verboso", "--completa"]) == ["--verboso", "--completa"]
    assert ba._sem_espelho(["--completa", "--espelho", "SISTEMA BAP\\logs\\agendador.log"]) == ["--completa"]
    assert ba._sem_espelho([]) == []


# ---------------------------------------------------------------- 5. executar_bap.bat
def _linhas_bat():
    linhas = BAT.read_bytes().decode("utf-8", "replace").splitlines()
    corte = next(i for i, l in enumerate(linhas) if l.strip().lower() == ":linha")
    return linhas[:corte], linhas[corte:]


def test_T0057_bat_nenhum_echo_fora_de_linha_grava_so_no_log():
    corpo, _ = _linhas_bat()
    for n, l in enumerate(corpo, 1):
        s = l.strip()
        low = s.lower()
        if not s or low.startswith("rem"):
            continue
        assert '>> "sistema bap\\logs\\agendador.log"' not in low, f"linha {n}: {s}"
        assert '>> "%log%"' not in low, f"linha {n}: {s}"
        if re.search(r"\becho\b", low) and low != "@echo off":
            # unica excecao: o eco de antes de existir a pasta do log
            assert "pasta" in low and "nao encontrada" in low, f"echo fora de :linha na linha {n}: {s}"


def test_T0057_bat_sub_rotina_linha_ecoa_na_tela_e_no_log():
    _, sub = _linhas_bat()
    corpo = [l.strip().lower() for l in sub[1:] if l.strip()]
    fim = next(i for i, l in enumerate(corpo) if l.startswith("exit /b"))
    corpo = corpo[:fim]
    assert any(l.startswith("echo(") for l in corpo), "sub-rotina sem echo na tela"
    assert any('>> "%log%"' in l and "echo(" in l for l in corpo), "sub-rotina sem echo no log"


def test_T0057_bat_chama_o_robo_com_espelho_sem_redirecionar():
    corpo, _ = _linhas_bat()
    chamadas = [i for i, l in enumerate(corpo) if "bap_automation.py" in l and "--espelho" in l]
    assert len(chamadas) == 1, "esperada uma chamada do robo com --espelho"
    i = chamadas[0]
    chamada = corpo[i]
    assert '--espelho "%LOG%"' in chamada
    assert ">" not in chamada and "|" not in chamada, f"chamada redirecionada: {chamada}"
    assert corpo[i + 1].strip().lower() == "set codigo=%errorlevel%"
    assert any(l.strip().lower() == "exit /b %codigo%" for l in corpo)
