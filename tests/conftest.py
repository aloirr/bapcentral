"""conftest mínimo: põe a raiz do repositório no sys.path.

Os testes usam só dados fictícios (CLAUDE.md regra 6) e não leem
RELATORIOS/ nem SISTEMA BAP/.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
