"""T-0045 (ADR 0004 §7 e adendo 1; desenho `docs/desenho/T-0045-render-yaml.md` §3, último item): a imagem do cron
`bap-visitas-maxima` (`nuvem/visitas/Dockerfile`, `.dockerignore` e o `buildFilter` do `render.yaml`).

Regra: RN-VIS-007 (nenhum dado de cliente na imagem: lista FECHADA no `COPY`) e RN-VIS-005 (a trava do build:
sem o `rodar.py`, a imagem não sai).

O Dockerfile e o `.dockerignore` entram num PR do engenheiro-software: enquanto não estiverem no main, cada teste
que precisa deles FALHA com a mensagem dizendo o que falta (não pula). Sem Docker e sem rede: o "build" é simulado
numa pasta temporária só com os arquivos do `COPY`.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DOCKERFILE = RAIZ / "nuvem" / "visitas" / "Dockerfile"
DOCKERIGNORE = RAIZ / ".dockerignore"
SERVICO = "bap-visitas-maxima"


def _ler(caminho: Path) -> str:
    if not caminho.is_file():
        pytest.fail(f"{caminho.relative_to(RAIZ)} não existe: ele entra no PR do engenheiro-software (desenho "
                    "T-0045-render-yaml §3); este teste só passa com o arquivo no main.")
    return caminho.read_text(encoding="utf-8")


def _instrucoes(texto: str) -> list[tuple[str, str]]:
    """[(INSTRUÇÃO, argumentos)], juntando as linhas com `\\` e sem comentários."""
    out, atual = [], ""
    for linha in texto.splitlines():
        s = linha.strip()
        if not atual and (not s or s.startswith("#")):
            continue
        atual += " " + s.rstrip("\\").strip()
        if not s.endswith("\\"):
            cmd, _, resto = atual.strip().partition(" ")
            out.append((cmd.upper(), resto.strip()))
            atual = ""
    return out


def _copias(texto: str) -> list[tuple[list[str], str]]:
    """[(origens, destino)] de cada COPY/ADD (forma de lista JSON ou de palavras; sem as opções --x)."""
    out = []
    for cmd, args in _instrucoes(texto):
        if cmd not in ("COPY", "ADD"):
            continue
        if args.startswith("["):
            partes = json.loads(args)
        else:
            partes = [p for p in args.split() if not p.startswith("--")]
        out.append((partes[:-1], partes[-1]))
    return out


def _arquivos_do_copy(texto: str) -> list[str]:
    """Os arquivos (relativos à raiz, o `dockerContext: .`) que os COPY levam para a imagem."""
    arqs = []
    for origens, _ in _copias(texto):
        for o in origens:
            p = RAIZ / o
            if p.is_dir():
                arqs += sorted(str(x.relative_to(RAIZ)).replace(os.sep, "/") for x in p.rglob("*")
                               if x.is_file() and "__pycache__" not in x.parts)
            else:
                arqs.append(o.strip("/"))
    return arqs


def _rx_glob(padrao: str) -> re.Pattern:
    """Padrão no estilo do Docker/Render: `**` = qualquer coisa (com `/`), `*` e `?` sem `/`."""
    p = padrao.strip().lstrip("/").rstrip("/")
    rx, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif p.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif p[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif p[i] == "?":
            rx, i = rx + "[^/]", i + 1
        else:
            rx, i = rx + re.escape(p[i]), i + 1
    return re.compile(rf"^{rx}$")


def _casa_ou_pai(rx: re.Pattern, caminho: str) -> bool:
    partes = caminho.split("/")
    return any(rx.match("/".join(partes[:k])) for k in range(1, len(partes) + 1))


def _dockerignore_exclui(padroes: list[str], caminho: str) -> bool:
    excluido = False
    for p in padroes:
        neg = p.startswith("!")
        if _casa_ou_pai(_rx_glob(p[1:] if neg else p), caminho):
            excluido = not neg
    return excluido


def _sem_comentario(linha: str) -> str:
    """Tira o `# comentário` do fim da linha (o render.yaml não usa `#` dentro de valores)."""
    return re.sub(r"\s+#.*$", "", linha).rstrip() if not linha.lstrip().startswith("#") else ""


def _build_filter() -> list[str]:
    """`buildFilter.paths` do serviço `bap-visitas-maxima`, lido só com a biblioteca padrão (o CI não tem PyYAML).

    Leitura por indentação: o bloco do serviço vai do `- ...` que contém `name: bap-visitas-maxima` até o próximo
    item da lista `services`; dentro dele, os itens `- x` logo abaixo de `buildFilter:` → `paths:`."""
    linhas = [_sem_comentario(l) for l in (RAIZ / "render.yaml").read_text(encoding="utf-8").splitlines()]
    inicios = [i for i, l in enumerate(linhas) if re.match(r"^  - \S", l)]  # itens de `services:`
    blocos = [linhas[a:b] for a, b in zip(inicios, inicios[1:] + [len(linhas)])]
    serv = [b for b in blocos
            if any(re.fullmatch(rf"""\s*(?:- )?name:\s*["']?{re.escape(SERVICO)}["']?""", l) for l in b)]
    assert len(serv) == 1, f"o render.yaml não tem o serviço {SERVICO}"
    paths, estado, ind_bf, ind_p = [], "fora", 0, 0
    for l in serv[0]:
        if not l.strip():
            continue
        ind = len(l) - len(l.lstrip())
        if estado == "fora":
            if l.strip() == "buildFilter:":
                estado, ind_bf = "bf", ind
        elif estado == "bf":
            if ind <= ind_bf:
                break
            if l.strip() == "paths:":
                estado, ind_p = "paths", ind
        elif estado == "paths":
            if ind <= ind_p and not l.lstrip().startswith("- "):
                break
            if ind < ind_p:
                break
            m = re.fullmatch(r"""\s*- \s*["']?(.+?)["']?""", l)
            if not m:
                break
            paths.append(m.group(1))
    return paths


# ---------------------------------------------------------------------------------------------- o texto do Dockerfile
def test_RN_VIS_007_dockerfile_sem_copy_nem_add_da_raiz():
    """Lista FECHADA: nada de `COPY .`/`ADD .` (levaria RELATORIOS/, com dado de cliente) nem curinga na raiz."""
    texto = _ler(DOCKERFILE)
    copias = _copias(texto)
    assert copias, "o Dockerfile não tem COPY"
    assert not [c for c, _ in _instrucoes(texto) if c == "ADD"], "ADD na imagem: use COPY com a lista fechada"
    for origens, _ in copias:
        for o in origens:
            assert o.strip() not in (".", "./", "*", "/", "..") and not o.startswith(("*", "./*", "../")), o
            assert not any(ch in o for ch in "*?["), f"curinga no COPY: {o}"
            assert not o.startswith(("RELATORIOS", "SISTEMA BAP", "BAP Ajuda", ".coord", "docs", "web", "tests")), o


def test_RN_VIS_005_trava_do_import_antes_do_user_e_depois_do_copy():
    texto = _ler(DOCKERFILE)
    ins = _instrucoes(texto)
    trava = [i for i, (c, a) in enumerate(ins)
             if c == "RUN" and re.fullmatch(r"""python3? -c ["']import nuvem\.visitas\.rodar, nuvem\.visitas\.agenda["']""",
                                            a)]
    users = [i for i, (c, _) in enumerate(ins) if c == "USER"]
    copia_nuvem = [i for i, (c, a) in enumerate(ins) if c == "COPY" and "nuvem/visitas" in a]
    assert len(trava) == 1, 'falta o RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"'
    assert users and trava[0] < users[0], "a trava tem de rodar antes do USER"
    assert copia_nuvem and copia_nuvem[-1] < trava[0], "a trava tem de vir depois do COPY do nuvem/visitas/"
    assert ins[users[-1]][1] not in ("root", "0"), "a imagem não pode rodar como root"


def test_RN_VIS_005_tini_e_o_pid_1_e_o_cmd_e_o_rodar():
    """Contrato §2: o tini recolhe o Chromium e repassa o SIGTERM; o processo é o `python -m nuvem.visitas.rodar`."""
    ins = _instrucoes(_ler(DOCKERFILE))
    ent = [a for c, a in ins if c == "ENTRYPOINT"]
    cmd = [a for c, a in ins if c == "CMD"]
    assert ent and "tini" in json.loads(ent[-1])[0]
    assert cmd and json.loads(cmd[-1]) == ["python", "-m", "nuvem.visitas.rodar"]


def test_RN_VIS_005_tag_da_imagem_e_a_versao_do_playwright():
    ins = _instrucoes(_ler(DOCKERFILE))
    froms = [a for c, a in ins if c == "FROM"]
    assert len(froms) == 1, froms
    m = re.fullmatch(r"mcr\.microsoft\.com/playwright/python:v(\d+\.\d+\.\d+)-[a-z]+", froms[0])
    assert m, f"imagem fora do padrão do desenho: {froms[0]}"
    req = (RAIZ / "requirements-visitas.txt").read_text(encoding="utf-8")
    versoes = re.findall(r"^\s*playwright==(\S+)", req, re.M)
    assert versoes == [m.group(1)], (versoes, m.group(1))


# ---------------------------------------------------------------------------- COPY × buildFilter × .dockerignore
@pytest.mark.xfail(strict=True, reason="buildFilter sem painel_farol.py: governança do Alexandre")
def test_RN_VIS_005_todo_arquivo_do_copy_esta_no_build_filter():
    """Mudou um arquivo da imagem (ou o próprio Dockerfile) = a imagem refaz. Sem isso, o cron roda código velho."""
    texto = _ler(DOCKERFILE)
    filtros = [_rx_glob(p) for p in _build_filter()]
    arqs = _arquivos_do_copy(texto) + ["nuvem/visitas/Dockerfile"]
    fora = [a for a in arqs if not any(rx.match(a) for rx in filtros)]
    assert fora == [], f"arquivos da imagem fora do buildFilter do render.yaml: {fora}"


def test_RN_VIS_005_build_filter_cobre_o_que_ja_estava_combinado():
    """A parte do buildFilter que não depende do painel_farol.py (a outra fica no xfail acima)."""
    filtros = [_rx_glob(p) for p in _build_filter()]
    for a in ("nuvem/visitas/rodar.py", "nuvem/visitas/agenda.py", "nuvem/visitas/Dockerfile", "visitas_maxima.py",
              "visitas_nucleo.py", "relatorios_nucleo.py", "bap_dados.py", "requirements-visitas.txt", ".dockerignore"):
        assert any(rx.match(a) for rx in filtros), a
    assert not any(rx.match("RELATORIOS/x.xlsx") or rx.match("web/app/main.py") for rx in filtros)


def test_RN_VIS_005_dockerignore_nao_exclui_o_que_o_copy_usa():
    texto = _ler(DOCKERFILE)
    padroes = [s.strip() for s in _ler(DOCKERIGNORE).splitlines() if s.strip() and not s.strip().startswith("#")]
    arqs = _arquivos_do_copy(texto)
    assert arqs
    for a in arqs:
        assert (RAIZ / a).is_file(), f"o COPY leva um arquivo que não existe: {a}"
    excluidos = [a for a in arqs if _dockerignore_exclui(padroes, a)]
    assert excluidos == [], f".dockerignore tira do contexto o que o COPY usa: {excluidos}"
    # e tira as bases e o que é sensível
    for a in ("RELATORIOS/Visitas/x.xlsx", "SISTEMA BAP/x.json", "BAP Ajuda 2.0/x.xlsx", ".git/HEAD", ".env",
              "tests/x.py", "web/app/main.py", "docs/x.md"):
        assert _dockerignore_exclui(padroes, a), a


def test_RN_VIS_007_nenhum_fixture_ou_dado_dentro_de_nuvem_visitas():
    """A pasta `nuvem/visitas/` entra inteira na imagem: só código e o Dockerfile."""
    pasta = RAIZ / "nuvem" / "visitas"
    if not pasta.is_dir():
        pytest.fail("nuvem/visitas/ não existe: entra no PR do modulo-robo (T-0045).")
    arqs = [p for p in pasta.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for p in arqs:
        rel = str(p.relative_to(pasta))
        assert p.suffix == ".py" or rel == "Dockerfile", f"arquivo que não é código em nuvem/visitas/: {rel}"
        assert not p.name.endswith(".dockerignore"), rel
    assert not [p for p in pasta.rglob("*") if p.is_dir() and p.name not in ("__pycache__",)], \
        "subpasta em nuvem/visitas/ (fixture ou dado?)"


# ----------------------------------------------------------------------- o build simulado, só com a lista do COPY
def _imagem_simulada(tmp_path: Path) -> Path:
    texto = _ler(DOCKERFILE)
    app = tmp_path / "app"
    for a in _arquivos_do_copy(texto):
        destino = app / a
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes((RAIZ / a).read_bytes())
    return app


def _python_isolado(app: Path, codigo: str, cwd: Path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BAP_", "PYTHON"))}
    env["PYTHONPATH"] = str(app)
    # -I ignora o PYTHONPATH; o Dockerfile usa PYTHONPATH=/app, então a pasta entra pelo sys.path, sem o repositório
    return subprocess.run([sys.executable, "-I", "-B", "-c", f"import sys; sys.path.insert(0, {str(app)!r})\n" + codigo],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


def test_RN_VIS_005_trava_do_build_passa_so_com_os_arquivos_do_copy(tmp_path):
    """O `RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"` do Dockerfile, sem Docker: só a lista
    do COPY numa pasta temporária, sem o repositório no caminho."""
    app = _imagem_simulada(tmp_path)
    r = _python_isolado(app, "import nuvem.visitas.rodar, nuvem.visitas.agenda\n"
                             "import os\n"
                             f"assert os.path.realpath(nuvem.visitas.rodar.__file__).startswith({str(app)!r})\n"
                             "print('ok')", cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-2000:]


def test_RN_VIS_007_filtro_do_espelho_e_montar_dia_rodam_so_com_os_arquivos_do_copy(tmp_path):
    """O caminho que a nuvem chama de verdade (o `filtrar_espelho` do §3.6, que importa o `relatorios_nucleo` na
    hora, e o `montar_dia` do `Robo.rodar`) com só a lista do COPY. Um import que falta aqui só apareceria no
    Render, com todo vendedor perdido."""
    from tests import visitas_nuvem_fixture as fx
    d = date(2026, 11, 26)
    origem = fx.espelho_xlsx(tmp_path / "origem.xlsx", d)
    app = _imagem_simulada(tmp_path)
    codigo = f"""
from datetime import date, datetime
from pathlib import Path
import visitas_nucleo as vn, visitas_maxima as vm
res = vn.filtrar_espelho(Path({str(origem)!r}), Path({str(tmp_path / "destino.xlsx")!r}))
assert res["achados"] == [], res
raiz = Path({str(tmp_path / "raiz")!r})
arq = vm.arquivo_analitico(raiz, "VENDEDOR FICTICIO UM", date(2026, 11, 26), datetime(2026, 11, 27, 6, 7))
arq.parent.mkdir(parents=True, exist_ok=True)
arq.write_bytes(Path({str(tmp_path / "destino.xlsx")!r}).read_bytes())
assert vn.montar_dia(raiz, date(2026, 11, 26), {{}}) == 1
vn.anotar_baixado(raiz, "20261126")
print("ok")
"""
    r = _python_isolado(app, codigo, cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-2000:]
