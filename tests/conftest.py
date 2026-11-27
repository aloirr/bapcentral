"""Configuracao comum dos testes (pytest).

Os modulos do BAP Tools moram na raiz do repositorio: so a raiz entra no
sys.path (na frente), sem PYTHONPATH de fora. Para testar outra versao de um
modulo, copie o repositorio para um diretorio temporario e troque la.
"""
import sys
from pathlib import Path

RAIZ = str(Path(__file__).resolve().parent.parent)

while RAIZ in sys.path:
    sys.path.remove(RAIZ)
sys.path.insert(0, RAIZ)


# ---------------------------------------------------------------------------
# RELATORIOS/ é base congelada: nenhum teste grava lá. O montar do vc_painel
# (Painel do Diretor) grava o histórico do mês em
# RELATORIOS/painel_diretor_hist.json; na suíte, o histórico do repositório
# é lido de uma cópia numa pasta temporária, e a gravação vai para a cópia.
# Outra raiz (pasta fictícia de um teste) segue o caminho normal.
import shutil  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _historico_do_diretor_fora_do_repositorio(tmp_path_factory):
    import painel_diretor as pdr                        # noqa: PLC0415
    original = pdr._hist_path
    raiz_repo = Path(RAIZ).resolve()
    copia = tmp_path_factory.mktemp("hist_diretor") / pdr.ARQ_HIST
    real = original(raiz_repo)
    if real.exists():
        shutil.copy2(real, copia)

    def _hist_path(raiz):
        if Path(raiz).resolve() == raiz_repo:
            return copia
        return original(raiz)
    mp = pytest.MonkeyPatch()
    mp.setattr(pdr, "_hist_path", _hist_path)
    yield copia
    mp.undo()


# ---------------------------------------------------------------------------
# RD-0257 (T-0036): web/app (pacotes e tabelas) deste checkout para os testes
# que conferem o pacote do robô na validação da web; sai do sys.modules no fim.
@pytest.fixture()
def web_app():
    import types                                        # noqa: PLC0415
    web = str(Path(RAIZ) / "web")
    antes = set(sys.modules)
    sys.path.insert(0, web)
    try:
        from app import pacotes, tabelas                # noqa: PLC0415
        yield types.SimpleNamespace(pacotes=pacotes, tabelas=tabelas)
    finally:
        sys.path.remove(web)
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]
