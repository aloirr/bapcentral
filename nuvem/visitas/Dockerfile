# Cron job bap-visitas-maxima (T-0045, ADR 0004). Dono: engenheiro-software.
# Desenho: docs/desenho/T-0045-render-yaml.md, §3. Contexto de build = raiz do repositório (render.yaml, dockerContext: .).
# A tag da imagem e o playwright do requirements-visitas.txt andam juntos: trocar uma = trocar a outra.
# [SUPOSIÇÃO] v1.49.1-noble: Ubuntu 24.04, Python 3.12, Chromium e as bibliotecas do sistema já dentro.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# PYTHONPATH=/app: o pacote "nuvem" é namespace (PEP 420, sem nuvem/__init__.py);
# só nuvem/visitas/ entra na imagem, e ele é achado a partir de /app em qualquer diretório.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# tini como PID 1: recolhe os processos do Chromium e repassa o SIGTERM ao Python (contrato, §2).
# [SUPOSIÇÃO] a imagem roda como root até o USER abaixo, e o apt do Ubuntu 24.04 tem o tini.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-visitas.txt ./
# [SUPOSIÇÃO] --break-system-packages: o Python do Ubuntu 24.04 é "externally managed" (PEP 668).
RUN pip install --break-system-packages -r requirements-visitas.txt

# Lista FECHADA. Proibido copiar a raiz inteira (COPY ou ADD de "."): levaria as bases (RELATORIOS/, com dado de cliente) para a imagem.
# relatorios_nucleo + bap_dados: a limpeza da RN-GER-011 no filtro do Espelho (contrato, §3.6).
# painel_farol: o relatorios_nucleo importa pct_do_liquido dele no topo (só biblioteca padrão).
# PENDENTE (governança): painel_farol.py ainda falta no buildFilter do render.yaml;
# até entrar, mudar só nele não refaz a imagem. Os demais arquivos daqui já estão no buildFilter.
COPY visitas_maxima.py visitas_nucleo.py relatorios_nucleo.py bap_dados.py painel_farol.py ./
COPY nuvem/visitas/ ./nuvem/visitas/

# Trava da ordem (ADR 0004, adendo 1): sem o rodar.py no main, o BUILD falha e nenhuma imagem roda sem o código.
# Exige do modulo-robo: importar o rodar.py não faz nada (nem rede, nem navegador, nem leitura de segredo).
RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"

# Usuário sem privilégio que a imagem do Playwright já traz.
USER pwuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "nuvem.visitas.rodar"]
