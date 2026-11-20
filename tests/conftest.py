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
