# T-0045 — Proposta de governança: o cron job `bap-visitas-maxima` no `render.yaml` e o `Dockerfile`

- **Autor:** engenheiro-software · **Data:** 27/11/2026
- **Base:** ADR 0004 (aceita) e o contrato `.coord/contratos/visitas-nuvem.md` v1, na branch `engenheiro-software/T-0045-visitas-render`.
- **Decisões:** R-20261127-005437-alexandre (2 A: cron job à parte, plano de 2 GB por minuto; 5 A: usuário próprio da Máxima, só como variável secreta).

## 1. Por que esta proposta é um diff, e não o `render.yaml` alterado

- O `render.yaml` e o `.coord/donos.json` são do **alexandre** (`.coord/donos.json`). O guardião bloqueia o engenheiro-software nesses arquivos, e o protocolo manda não contornar.
- Por isso, esta branch leva **só arquivos do engenheiro-software**:
  - este desenho;
  - `docs/desenho/T-0045-render-yaml.diff`, que aplica limpo sobre o `origin/main` a32b610 (`git apply docs/desenho/T-0045-render-yaml.diff`).
- Quem tem a identidade do Alexandre aplica o diff no `render.yaml`, no mesmo PR ou num PR próprio, como no PR #57. O merge segue com o "autorizo o merge do PR #N no commit <sha>" do po, por delegação.

## 2. O que muda no `render.yaml`

**No `bap-central` (o site), uma linha só:**

```yaml
      - key: BAP_VISITAS_TOKEN
        generateValue: true  # T-0045: o Render sorteia; só abre as rotas do cron (/api/visitas/trabalho e /rodada*)
```

- O Render sorteia o valor, e ninguém do time o vê. O cron recebe o mesmo valor pelo `fromService`.
- Variável nova no site = **um deploy do site** no sync do Blueprint (alguns segundos fora do ar, como em todo deploy).

**Serviço novo (no fim do `services:`):**

```yaml
  - type: cron
    name: bap-visitas-maxima
    runtime: docker
    plan: standard           # 2 GB, 1 CPU, cobrado por minuto [SUPOSIÇÃO: ~US$ 0,00058/min, mínimo US$ 1/mês; confirmar no painel]
    region: oregon           # a mesma do bap-central (rede privada)
    schedule: "*/10 10-23,0-1 * * *"   # UTC: de 10 em 10 min, das 06h00 às 21h50 de Manaus (UTC-4)
    dockerfilePath: ./nuvem/visitas/Dockerfile
    dockerContext: .
    autoDeploy: true
    buildFilter:             # só refaz a imagem quando o código dela muda
      paths:
        - nuvem/visitas/**
        - visitas_maxima.py
        - visitas_nucleo.py
        - requirements-visitas.txt
    envVars:
      - key: TZ
        value: America/Manaus
      - key: PYTHONUNBUFFERED
        value: "1"
      - key: BAP_WEB_HOSTPORT
        fromService:
          type: web
          name: bap-central
          property: hostport
      - key: BAP_VISITAS_TOKEN
        fromService:         # o valor sorteado no bap-central [SUPOSIÇÃO: envVarKey aceito no cron]
          type: web
          name: bap-central
          envVarKey: BAP_VISITAS_TOKEN
      - key: BAP_MAXIMA_USUARIO
        sync: false          # o Alexandre cria no painel (usuário próprio do robô, decisão 5 A)
      - key: BAP_MAXIMA_SENHA
        sync: false          # o Alexandre cria no painel; só neste serviço
```

- **Nenhum valor secreto.** Os 2 únicos segredos (`BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA`) estão com `sync: false`: o Render cria a variável vazia e pede o valor no painel.
- **Horário:** Manaus é UTC−4 o ano todo (sem horário de verão). 10h00 UTC = 06h00 de Manaus; 01h50 UTC = 21h50. A agenda das 06h00 (decisão 3 A) é decidida pelo código (`deve_rodar`), não pelo `schedule`: o `schedule` só acorda o cron para ver se há trabalho.
- **`buildFilter`:** sem ele, todo commit no `main` refaria a imagem de cerca de 2 GB.
- **Sem `disk`:** o cron job do Render não aceita disco [SUPOSIÇÃO]. Tudo que fica vai ao site pela API (contrato, §3).
- **Sem `dockerCommand`:** vale o `CMD` do `Dockerfile`.

### 2.1 O que confere com a documentação do Render, e o que é [SUPOSIÇÃO]

A documentação do Render (`render.com/docs`) não abriu desta sessão (o proxy recusou o domínio). Os campos vêm do Blueprint que o repositório já usa e do que conheço da especificação:

| Campo ou fato | Situação |
|---|---|
| `type: cron`, `schedule`, `runtime: docker`, `dockerfilePath`, `dockerContext`, `buildFilter.paths`, `envVars`, `sync: false`, `fromService ... property: hostport` | conhecidos da especificação do Blueprint [SUPOSIÇÃO: conferir no primeiro sync; erro de campo aparece no painel antes de criar o serviço] |
| `generateValue: true` e `fromService ... envVarKey` | [SUPOSIÇÃO]. Se o Render recusar o `envVarKey` no cron, a troca é `sync: false` nos dois serviços e o Alexandre põe o mesmo valor (qualquer texto longo) nos dois |
| `plan: standard` (2 GB, 1 CPU) no cron | [SUPOSIÇÃO] nome e tamanho do plano |
| preço por minuto (~US$ 0,00058 no Standard, ~US$ 0,00016 no Starter) e o mínimo de US$ 1/mês | [SUPOSIÇÃO]: o Alexandre confere em Render > Pricing antes do "autorizo" |
| `schedule` em UTC; uma execução por vez; teto de 12 h por execução | [SUPOSIÇÃO] |
| o cron alcança o site pela rede privada (`hostport`) | [SUPOSIÇÃO]: o diagnóstico mostra. Se não alcançar, troca para a URL pública com HTTPS |
| `autoDeploy: true` no cron | igual ao site (ADR 0001, adendo 4) |

## 3. O `Dockerfile` (texto; entra no repositório depois do `donos.json`)

**Dono proposto:** **engenheiro-software**, como base técnica (a imagem, a versão do Playwright, o `requirements-visitas.txt`). O código que roda dentro (`nuvem/visitas/rodar.py`, `agenda.py`, `__init__.py`) é do **modulo-robo**. Não é do modulo-web: o cron não é o site e não fica em `web/` (o site tem `rootDir: web`, e código do cron ali faria o site refazer deploy a cada mudança do cron).

Hoje `nuvem/**` é "sem-dono", e o guardião bloqueia. As linhas para o `.coord/donos.json` (governança, antes das regras gerais; a primeira que casa vence):

```json
{ "padrao": "nuvem/visitas/Dockerfile", "dono": "engenheiro-software" },
{ "padrao": "nuvem/**", "dono": "modulo-robo" },
```

Texto do `nuvem/visitas/Dockerfile`:

```dockerfile
# Cron job bap-visitas-maxima (T-0045, ADR 0004). Dono: engenheiro-software.
# A tag da imagem e o playwright do requirements-visitas.txt andam juntos.
# [SUPOSIÇÃO] v1.49.1-noble: Ubuntu 24.04, Python 3.12, Chromium e as bibliotecas do sistema já dentro.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-visitas.txt ./
# [SUPOSIÇÃO] --break-system-packages: o Python do Ubuntu 24.04 é "externally managed" (PEP 668).
RUN pip install --break-system-packages -r requirements-visitas.txt

# Lista FECHADA. Proibido "COPY . ." ou "ADD .": levaria as bases (RELATORIOS/, com dado de cliente) para a imagem.
COPY visitas_maxima.py visitas_nucleo.py ./
COPY nuvem/visitas/ ./nuvem/visitas/

# Usuário sem privilégio que a imagem do Playwright já traz.
USER pwuser

CMD ["python", "-m", "nuvem.visitas.rodar"]
```

- O `visitas_nucleo.py` importa o `xlsx_rapido`, o `meta_nucleo` e o `pastas_bap` só dentro de funções de montagem, que a nuvem não chama. Se o `rodar.py` precisar de alguma delas, o arquivo entra na lista do `COPY` e no `buildFilter`, e nunca uma pasta inteira.
- Teste (agente testes): o `Dockerfile` não tem `COPY .` nem `ADD .`, e a tag da imagem é a mesma versão do `playwright==` do `requirements-visitas.txt`.

## 4. Ordem do merge (para o primeiro build não falhar)

1. **Governança 1:** as duas linhas do `.coord/donos.json` (§3).
2. **Código no `main`:** a web do contrato (modulo-web), o `nuvem/visitas/` (modulo-robo) e o `Dockerfile` (engenheiro-software). O `requirements-visitas.txt` já está na branch da ADR.
3. **Governança 2: este `render.yaml`.** Com o merge, o Blueprint cria o `bap-visitas-maxima` e põe o `BAP_VISITAS_TOKEN` no site.
4. O Alexandre preenche `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` no painel. Até lá, cada volta do cron sai em segundos com `CONFIG_FALTANDO`.
5. A primeira volta com as variáveis faz o **diagnóstico** (contrato, §6). A agenda só liga com o "ok" do Alexandre.

Se o `render.yaml` entrar antes do item 2, o Render tenta construir a imagem sem o `Dockerfile` e o build falha no painel. Nada quebra no site, mas o serviço fica vermelho até o código chegar.
