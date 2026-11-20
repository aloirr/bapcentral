"""Configuracao comum dos testes (pytest).

Os modulos do BAP Tools moram na raiz do repositorio. Sem PYTHONPATH, a raiz
entra no sys.path. Com PYTHONPATH (ex.: um worktree com a implementacao de
outro branch), vale o que veio de fora: `python -m pytest` poe o diretorio
atual na frente do PYTHONPATH, entao as pastas do PYTHONPATH voltam para o
inicio do sys.path.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

_fora = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
if _fora:
    for _p in reversed(_fora):
        _p = str(Path(_p).resolve())
        while _p in sys.path:
            sys.path.remove(_p)
        sys.path.insert(0, _p)
elif str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
