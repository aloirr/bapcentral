"""Configuracao do pytest: deixa os modulos da raiz do repositorio importaveis
(relatorios_nucleo, planner_nucleo, meta_nucleo...) a partir de tests/."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
