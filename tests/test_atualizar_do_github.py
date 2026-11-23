"""Testes do instalador ``atualizar_do_github.py`` (T-0003).

Regra 11 do CLAUDE.md: o codigo do ``main`` so vai para a producao com backup
``SISTEMA BAP/BACKUP_RELATORIOS/ANTES_<ASSUNTO>_<MES><ANO>`` e conferencia
byte a byte. Contrato: ``docs/desenho/T-0003.md`` ("Plano de teste").

Tudo em ``tmp_path``, sem rede, sem OneDrive, com dados de mentira (nenhum
dado pessoal). As datas sao controladas com ``os.utime``.
"""
from __future__ import annotations

import builtins
import hashlib
import os
import zipfile
from datetime import date
from pathlib import Path, PurePath

import pytest

import atualizar_do_github as atu

HOJE = date(2026, 11, 20)
T_MAIN = 1_790_000_000.0          # data "do commit" do main de mentira
T_PROD_VELHA = T_MAIN - 86_400    # producao instalada um dia antes

# Arquivos que NUNCA podem entrar (mesmo presentes no main de mentira).
EXCLUIDOS_NO_MAIN = [
    "config_geral.json",
    "champions_config.json",
    "transportadoras_config.json",
    "painel_diretor_config.json",
    "visitas_config.json",
    "tomtom_config.json",
    "tomtom_config_prod.json",
    "google_maps_config.json",
    "google_maps_config_2.json",
    ".env",
    "_EDICOES_POS_VENDA_2026.py",
    "_NCC_lancamentos.py",
    "_GARANTIAS.bat",
    "_AUTORIZACOES_nov.py",
    "RELATORIOS/base_relatorio.py",
    "SISTEMA BAP/sistema.py",
    "BAP Ajuda 2.0/ajuda.py",
    "auth/token.py",
    "web/app.py",
    "LEIAME.md",
    "dados.xlsx",
]


# --------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------

def _gravar(raiz: Path, rel: str, conteudo: str, mtime: float) -> Path:
    p = raiz / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _foto(raiz: Path) -> dict[str, tuple[str, float]]:
    """Hash e mtime de toda a arvore (arquivos e pastas)."""
    foto: dict[str, tuple[str, float]] = {}
    for p in sorted(raiz.rglob("*")):
        rel = p.relative_to(raiz).as_posix()
        h = _sha(p) if p.is_file() else "<pasta>"
        foto[rel] = (h, p.stat().st_mtime)
    return foto


def _data_por_mtime(origem: Path):
    return lambda rel: (origem / rel).stat().st_mtime


def _cenario(tmp_path: Path) -> tuple[Path, Path]:
    """main de mentira + producao antiga.

    main: ``app.py`` (alterado), ``rodar.bat`` (alterado), ``novo.py`` (novo),
    ``igual.py`` (igual) e todos os ``EXCLUIDOS_NO_MAIN``.
    producao: versao antiga de app/rodar, igual.py, e as bases/dados digitados
    com conteudo proprio (que nao pode mudar).
    """
    origem = tmp_path / "main"
    producao = tmp_path / "producao"
    _gravar(origem, "app.py", "print('app v2')\n", T_MAIN)
    _gravar(origem, "rodar.bat", "@echo v2\r\n", T_MAIN)
    _gravar(origem, "novo.py", "print('novo')\n", T_MAIN)
    _gravar(origem, "igual.py", "x = 1\n", T_MAIN)
    for rel in EXCLUIDOS_NO_MAIN:
        _gravar(origem, rel, f"MAIN-NAO-ENTRA {rel}\n", T_MAIN)

    _gravar(producao, "app.py", "print('app v1')\n", T_PROD_VELHA)
    _gravar(producao, "rodar.bat", "@echo v1\r\n", T_PROD_VELHA)
    _gravar(producao, "igual.py", "x = 1\n", T_PROD_VELHA)
    for rel in EXCLUIDOS_NO_MAIN:
        if rel.startswith(("web/", "LEIAME", "dados")):
            continue
        _gravar(producao, rel, f"PRODUCAO-ORIGINAL {rel}\n", T_PROD_VELHA)
    return origem, producao


def _planejar(origem: Path, producao: Path) -> atu.Plano:
    return atu.planejar(origem, producao, _data_por_mtime(origem))


# --------------------------------------------------------------------------
# 1. Simulacao nao altera nada
# --------------------------------------------------------------------------

def test_T0003_simulacao_nao_altera_nada(tmp_path):
    """Regra 11 do CLAUDE.md: --simular so mostra; hash e mtime iguais, sem backup."""
    origem, producao = _cenario(tmp_path)
    antes_prod, antes_main = _foto(producao), _foto(origem)

    plano = _planejar(origem, producao)
    cod = atu.executar(plano, producao, "T0003", simular=True, hoje=HOJE)

    assert cod == atu.CODIGO_OK
    assert _foto(producao) == antes_prod
    assert _foto(origem) == antes_main
    assert not (producao / "SISTEMA BAP" / "BACKUP_RELATORIOS").exists()


def test_T0003_simulacao_pela_linha_de_comando(tmp_path, capsys):
    """Regra 11 do CLAUDE.md: main(--simular) tambem nao grava nada."""
    origem, producao = _cenario(tmp_path)
    antes = _foto(producao)
    cod = atu.main(["--origem", str(origem), "--producao", str(producao),
                    "--assunto", "T0003", "--simular"])
    assert cod == atu.CODIGO_OK
    assert _foto(producao) == antes
    assert "SIMULACAO" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 2. Troca so .py/.bat da raiz
# --------------------------------------------------------------------------

def test_T0003_troca_so_py_e_bat_da_raiz(tmp_path):
    """Regra 11 do CLAUDE.md: so *.py/*.bat da raiz do main entram na producao."""
    origem, producao = _cenario(tmp_path)
    plano = _planejar(origem, producao)

    assert [r.name for r in plano.alterados] == ["app.py", "rodar.bat"]
    assert [r.name for r in plano.novos] == ["novo.py"]
    assert [r.name for r in plano.iguais] == ["igual.py"]
    assert [r.name for r in plano.a_trocar] == ["app.py", "rodar.bat", "novo.py"]

    cod = atu.executar(plano, producao, "T0003", simular=False, hoje=HOJE)
    assert cod == atu.CODIGO_OK
    for nome in ("app.py", "rodar.bat", "novo.py", "igual.py"):
        assert _sha(producao / nome) == _sha(origem / nome)
    for nome in ("app.py", "rodar.bat", "novo.py"):
        # o instalado recebe a data do main
        assert (producao / nome).stat().st_mtime == pytest.approx(T_MAIN)
    # igual.py nao foi tocado
    assert (producao / "igual.py").stat().st_mtime == pytest.approx(T_PROD_VELHA)
    # nada de web/, .md ou .xlsx
    assert not (producao / "web").exists()
    assert not (producao / "LEIAME.md").exists()
    assert not (producao / "dados.xlsx").exists()


def test_T0003_candidatos_lista_so_a_raiz(tmp_path):
    """Regra 11 do CLAUDE.md: candidatos() = *.py/*.bat da raiz, fora os excluidos."""
    origem, _ = _cenario(tmp_path)
    assert [r.name for r in atu.candidatos(origem)] == [
        "app.py", "igual.py", "novo.py", "rodar.bat"]


# --------------------------------------------------------------------------
# 3. Excluidos nunca entram (e nao sao lidos)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", EXCLUIDOS_NO_MAIN[:18])
def test_T0003_eh_excluido_bases_digitados_e_segredos(rel):
    """Regras 5, 7 e 11 do CLAUDE.md: .json, bases, digitados e segredos excluidos."""
    assert atu.eh_excluido(PurePath(rel)) is True


@pytest.mark.parametrize("rel", ["app.py", "rodar.bat", "RODAR_TESTE_BAP.bat",
                                 "smoke_relatorios.py"])
def test_T0003_eh_excluido_deixa_codigo_da_raiz(rel):
    """Regra 11 do CLAUDE.md: codigo comum da raiz nao e excluido."""
    assert atu.eh_excluido(PurePath(rel)) is False


def test_T0003_excluidos_nunca_entram_nem_sao_lidos(tmp_path, monkeypatch):
    """Regras 5, 7 e 11 do CLAUDE.md: excluidos do main nao sao abertos nem copiados."""
    origem, producao = _cenario(tmp_path)
    antes = {rel: (_sha(producao / rel), (producao / rel).stat().st_mtime)
             for rel in EXCLUIDOS_NO_MAIN if (producao / rel).exists()}

    abertos: list[Path] = []
    open_real = builtins.open

    def open_espiao(arquivo, *a, **k):
        if isinstance(arquivo, (str, os.PathLike)):
            abertos.append(Path(os.fspath(arquivo)).resolve())
        return open_real(arquivo, *a, **k)

    monkeypatch.setattr(builtins, "open", open_espiao)
    plano = _planejar(origem, producao)
    cod = atu.executar(plano, producao, "T0003", simular=False, hoje=HOJE)
    monkeypatch.undo()

    assert cod == atu.CODIGO_OK
    assert abertos, "o espiao de open() nao pegou nada (teste invalido)"
    proibidos = {(origem / rel).resolve() for rel in EXCLUIDOS_NO_MAIN}
    proibidos |= {(producao / rel).resolve() for rel in EXCLUIDOS_NO_MAIN}
    assert not (set(abertos) & proibidos)

    # nenhum excluido mudou na producao e nenhum foi criado
    for rel, (h, mt) in antes.items():
        assert _sha(producao / rel) == h
        assert (producao / rel).stat().st_mtime == mt
        assert "PRODUCAO-ORIGINAL" in (producao / rel).read_text(encoding="utf-8")
    for p in producao.rglob("*"):
        if p.is_file():
            assert "MAIN-NAO-ENTRA" not in p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 4. Backup antes da troca, conferido por hash
# --------------------------------------------------------------------------

def test_T0003_backup_antes_da_troca_conferido_por_hash(tmp_path, monkeypatch):
    """Regra 11 do CLAUDE.md: backup ANTES_<ASSUNTO>_<MES><ANO> = producao antiga."""
    origem, producao = _cenario(tmp_path)
    velhos = {n: _sha(producao / n) for n in ("app.py", "rodar.bat")}
    pasta = producao / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "ANTES_T0003_NOV2026"

    # Na primeira troca, o backup ja precisa existir e estar completo.
    estado_no_replace: list[dict[str, str]] = []
    replace_real = os.replace

    def replace_espiao(src, dst, *a, **k):
        if not estado_no_replace:
            estado_no_replace.append(
                {p.name: _sha(p) for p in pasta.iterdir()} if pasta.exists() else {})
        return replace_real(src, dst, *a, **k)

    monkeypatch.setattr(atu.os, "replace", replace_espiao)
    plano = _planejar(origem, producao)
    cod = atu.executar(plano, producao, "T0003", simular=False, hoje=HOJE)
    monkeypatch.undo()

    assert cod == atu.CODIGO_OK
    assert estado_no_replace == [velhos]
    assert sorted(p.name for p in pasta.iterdir()) == ["app.py", "rodar.bat"]
    for nome, h in velhos.items():
        assert _sha(pasta / nome) == h
        assert (pasta / nome).stat().st_mtime == pytest.approx(T_PROD_VELHA)
    # so os alterados vao para o backup (novo.py e igual.py nao)
    assert not (pasta / "novo.py").exists()
    assert not (pasta / "igual.py").exists()


def test_T0003_so_novos_nao_cria_backup(tmp_path):
    """Regra 11 do CLAUDE.md: sem arquivo substituido, nao ha o que guardar."""
    origem = tmp_path / "main"
    producao = tmp_path / "producao"
    producao.mkdir()
    _gravar(origem, "novo.py", "print('novo')\n", T_MAIN)
    cod = atu.executar(_planejar(origem, producao), producao, "T0003",
                       simular=False, hoje=HOJE)
    assert cod == atu.CODIGO_OK
    assert (producao / "novo.py").exists()
    assert not (producao / "SISTEMA BAP").exists()


# --------------------------------------------------------------------------
# 5. Trava "instalado por fora"
# --------------------------------------------------------------------------

def test_T0003_trava_producao_mais_nova_que_o_main(tmp_path):
    """Regra 11 do CLAUDE.md: producao alterada mais nova que o main -> 2, nada muda."""
    origem, producao = _cenario(tmp_path)
    os.utime(producao / "app.py", (T_MAIN + 60, T_MAIN + 60))
    antes = _foto(producao)

    plano = _planejar(origem, producao)
    assert [r.name for r in plano.mais_novos_na_producao] == ["app.py"]
    cod = atu.executar(plano, producao, "T0003", simular=False, hoje=HOJE)

    assert cod == atu.CODIGO_TRAVA
    assert _foto(producao) == antes
    assert not (producao / "novo.py").exists()
    assert not (producao / "SISTEMA BAP" / "BACKUP_RELATORIOS").exists()


def test_T0003_trava_pela_linha_de_comando(tmp_path):
    """Regra 11 do CLAUDE.md: main() devolve 2 na trava."""
    origem, producao = _cenario(tmp_path)
    os.utime(producao / "rodar.bat", (T_MAIN + 60, T_MAIN + 60))
    antes = _foto(producao)
    cod = atu.main(["--origem", str(origem), "--producao", str(producao),
                    "--assunto", "T0003"])
    assert cod == atu.CODIGO_TRAVA
    assert _foto(producao) == antes


def test_T0003_trava_tolerancia_de_2_segundos(tmp_path):
    """Regra 11 do CLAUDE.md: ate 2 s mais nova (FAT/OneDrive) nao trava."""
    origem, producao = _cenario(tmp_path)
    os.utime(producao / "app.py", (T_MAIN + 2, T_MAIN + 2))
    assert _planejar(origem, producao).mais_novos_na_producao == []
    os.utime(producao / "app.py", (T_MAIN + 2.5, T_MAIN + 2.5))
    assert [r.name for r in _planejar(origem, producao).mais_novos_na_producao] == ["app.py"]


def test_T0003_arquivo_igual_mais_novo_nao_trava(tmp_path):
    """Regra 11 do CLAUDE.md: a trava vale so para arquivo com conteudo diferente."""
    origem, producao = _cenario(tmp_path)
    os.utime(producao / "igual.py", (T_MAIN + 600, T_MAIN + 600))
    assert _planejar(origem, producao).mais_novos_na_producao == []


# --------------------------------------------------------------------------
# 6. Nome do backup e sufixo
# --------------------------------------------------------------------------

def test_T0003_nome_backup():
    """Regra 11 do CLAUDE.md: ANTES_<ASSUNTO>_<MES><ANO>."""
    assert atu.nome_backup("T0003", date(2026, 11, 20)) == "ANTES_T0003_NOV2026"
    assert atu.nome_backup("rota maxima", date(2027, 2, 1)) == "ANTES_ROTA_MAXIMA_FEV2027"
    with pytest.raises(ValueError):
        atu.nome_backup("  --  ", HOJE)


def test_T0003_pasta_backup_sufixo_quando_ja_existe(tmp_path):
    """Regra 11 do CLAUDE.md: pasta existente -> _2, _3 (nunca sobrescreve)."""
    base = tmp_path / "SISTEMA BAP" / "BACKUP_RELATORIOS"
    assert atu.pasta_backup(tmp_path, "T0003", HOJE) == base / "ANTES_T0003_NOV2026"
    (base / "ANTES_T0003_NOV2026").mkdir(parents=True)
    assert atu.pasta_backup(tmp_path, "T0003", HOJE) == base / "ANTES_T0003_NOV2026_2"
    (base / "ANTES_T0003_NOV2026_2").mkdir()
    assert atu.pasta_backup(tmp_path, "T0003", HOJE) == base / "ANTES_T0003_NOV2026_3"


def test_T0003_segunda_instalacao_no_mes_usa_sufixo(tmp_path):
    """Regra 11 do CLAUDE.md: o backup antigo fica intacto; o novo vai para _2."""
    origem, producao = _cenario(tmp_path)
    base = producao / "SISTEMA BAP" / "BACKUP_RELATORIOS"
    _gravar(base, "ANTES_T0003_NOV2026/app.py", "backup anterior\n", T_PROD_VELHA)
    cod = atu.executar(_planejar(origem, producao), producao, "T0003",
                       simular=False, hoje=HOJE)
    assert cod == atu.CODIGO_OK
    assert (base / "ANTES_T0003_NOV2026" / "app.py").read_text(encoding="utf-8") == "backup anterior\n"
    assert (base / "ANTES_T0003_NOV2026_2" / "app.py").read_text(encoding="utf-8") == "print('app v1')\n"


# --------------------------------------------------------------------------
# Bonus: falha na troca e caminho zip
# --------------------------------------------------------------------------

def test_T0003_falha_na_troca_restaura_producao(tmp_path, monkeypatch):
    """Regra 11 do CLAUDE.md: os.replace falha no meio -> 4 e producao como estava."""
    origem, producao = _cenario(tmp_path)
    antigos = {n: (_sha(producao / n), (producao / n).stat().st_mtime)
               for n in ("app.py", "rodar.bat", "igual.py")}
    replace_real = os.replace
    falhou: list[str] = []

    def replace_falho(src, dst, *a, **k):
        # falha uma vez, na troca do 2o arquivo (app.py ja foi trocado)
        if Path(dst).name == "rodar.bat" and not falhou:
            falhou.append("rodar.bat")
            raise PermissionError("arquivo aberto (simulado)")
        return replace_real(src, dst, *a, **k)

    monkeypatch.setattr(atu.os, "replace", replace_falho)
    cod = atu.executar(_planejar(origem, producao), producao, "T0003",
                       simular=False, hoje=HOJE)
    monkeypatch.undo()

    assert falhou == ["rodar.bat"]
    assert cod == atu.CODIGO_TROCA
    for nome, (h, mt) in antigos.items():
        assert _sha(producao / nome) == h
        assert (producao / nome).stat().st_mtime == pytest.approx(mt)
    assert not (producao / "novo.py").exists()
    assert not list(producao.glob(".*.atualizando.tmp"))


def test_T0003_falha_no_backup_nao_troca(tmp_path, monkeypatch):
    """Regra 11 do CLAUDE.md: backup falhou -> 3 e nada trocado."""
    origem, producao = _cenario(tmp_path)
    velhos = {n: _sha(producao / n) for n in ("app.py", "rodar.bat")}

    def copy2_falho(*a, **k):
        raise OSError("disco cheio (simulado)")

    monkeypatch.setattr(atu.shutil, "copy2", copy2_falho)
    cod = atu.executar(_planejar(origem, producao), producao, "T0003",
                       simular=False, hoje=HOJE)
    monkeypatch.undo()

    assert cod == atu.CODIGO_BACKUP
    for nome, h in velhos.items():
        assert _sha(producao / nome) == h
    assert not (producao / "novo.py").exists()


def test_T0003_zip_do_main_nao_extrai_excluidos(tmp_path, monkeypatch):
    """Regras 5, 7 e 11 do CLAUDE.md: do zip so saem *.py/*.bat da raiz do main."""
    arq = tmp_path / "fonte" / "main_de_mentira.zip"
    arq.parent.mkdir()
    with zipfile.ZipFile(arq, "w") as z:
        z.writestr("bapcentral-main/", "")
        z.writestr(zipfile.ZipInfo("bapcentral-main/app.py", (2026, 11, 19, 10, 0, 0)),
                   "print('app v2')\n")
        z.writestr(zipfile.ZipInfo("bapcentral-main/rodar.bat", (2026, 11, 19, 10, 0, 0)),
                   "@echo v2\r\n")
        for rel in EXCLUIDOS_NO_MAIN:
            z.writestr(f"bapcentral-main/{rel}", f"MAIN-NAO-ENTRA {rel}\n")

    lidos: list[str] = []
    open_real = zipfile.ZipFile.open

    def open_espiao(self, nome, *a, **k):
        lidos.append(nome.filename if isinstance(nome, zipfile.ZipInfo) else nome)
        return open_real(self, nome, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", open_espiao)
    destino = tmp_path / "baixado" / "main"
    datas = atu.baixar_main(destino, url=arq.resolve().as_uri())
    monkeypatch.undo()

    assert sorted(r.name for r in datas) == ["app.py", "rodar.bat"]
    assert sorted(p.name for p in destino.iterdir()) == ["app.py", "rodar.bat"]
    assert sorted(lidos) == ["bapcentral-main/app.py", "bapcentral-main/rodar.bat"]
    # data do item do zip (sem campo UT -> UTC)
    import calendar
    esperado = calendar.timegm((2026, 11, 19, 10, 0, 0, 0, 0, -1))
    assert datas[PurePath("app.py")] == pytest.approx(esperado)
