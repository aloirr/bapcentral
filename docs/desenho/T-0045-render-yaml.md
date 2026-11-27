# T-0045 — Proposta de governança: o cron job `bap-visitas-maxima` no `render.yaml` e o `Dockerfile`

- **Autor:** engenheiro-software · **Data:** 27/11/2026 (revisado no PR #137)
- **Base:** ADR 0004 (aceita) e o contrato `.coord/contratos/visitas-nuvem.md` v1, neste PR.
- **Decisões:** D1 (cron job à parte, plano de 2 GB pago pelo tempo rodado) e D4 revista (o mesmo login da Máxima do notebook, só como variável secreta), ADR 0004, §0 e adendo 1.
- **Texto exato do `render.yaml` e das linhas do `.coord/donos.json`:** `docs/desenho/T-0045-governanca.diff` (um diff só, que substitui o antigo `T-0045-render-yaml.diff`; frase e ordem no `docs/desenho/T-0045-governanca.md`). Este arquivo explica o diff sem repetir o YAML.

## 1. Por que esta proposta é um diff, e não o `render.yaml` alterado

- O `render.yaml` e o `.coord/donos.json` são do **alexandre** (`.coord/donos.json`). O guardião bloqueia o engenheiro-software nesses arquivos, e o protocolo manda não contornar.
- Por isso, este PR leva **só arquivos do engenheiro-software**: este desenho e o `.diff` ao lado.
- O `render.yaml` entra **num PR próprio do Alexandre** (`alexandre/T-0045-governanca`, junto com as linhas do `donos.json`), como no PR #57, **antes** do `Dockerfile` e do `nuvem/visitas/` (ADR 0004, adendo 1). O merge segue com o "autorizo o merge do PR #N no commit <sha>" do po, por delegação.

## 2. O que o diff muda no `render.yaml`

**No `bap-central` (o site): uma variável a mais, `BAP_VISITAS_TOKEN`, com `generateValue: true`.**
- O Render sorteia o valor, e ninguém do time o vê. O cron recebe o mesmo valor pelo `fromService`.
- Variável nova no site = **um deploy do site** no sync do Blueprint (alguns segundos fora do ar, como em todo deploy).
- O comentário do topo passa a contar os segredos dos 2 serviços.

**Serviço novo `bap-visitas-maxima` (no fim do `services:`):**
- `type: cron`, `runtime: docker`, `plan: standard`, `region: oregon` (a mesma do site, para a rede privada).
- **Horário:** `schedule` em UTC, de 10 em 10 min das 10h00 às 01h50 UTC. Manaus é UTC−4 o ano todo (sem horário de verão): 10h00 UTC = 06h00 de Manaus; 01h50 UTC = 21h50. A agenda das 06h00 (D2) e o teto do dia são decididos pelo código (`deve_rodar`, contrato §3.1), não pelo `schedule`: o `schedule` só acorda o cron para ver se há trabalho.
- **`buildFilter`:** só o que entra na imagem ou muda o build (`nuvem/visitas/**`, `visitas_maxima.py`, `visitas_nucleo.py`, `relatorios_nucleo.py`, `bap_dados.py`, `requirements-visitas.txt`, `.dockerignore`). Sem ele, todo commit no `main` refaria a imagem de cerca de 2 GB.
- **Variáveis:** as do contrato, §1. **Nenhum valor secreto:** os 2 únicos segredos (`BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA`) estão com `sync: false`: o Render cria a variável vazia e pede o valor no sync do Blueprint.
- **Sem `disk`:** o cron job não aceita disco (§2.1). Tudo que fica vai ao site pela API (contrato, §3).
- **Sem `dockerCommand`:** vale o `CMD` do `Dockerfile`.

### 2.1 Características do Render que a ADR 0004 usa (a fonte é esta tabela)

A documentação do Render (`render.com/docs`) não abriu desta sessão (o proxy recusou o domínio). Os campos vêm do Blueprint que o repositório já usa e do que conheço da especificação. Tudo o que está marcado é conferido no primeiro sync (erro de campo aparece no painel antes de criar o serviço) ou no diagnóstico.

| Campo ou fato | Situação |
|---|---|
| `type: cron`, `schedule`, `runtime: docker`, `dockerfilePath`, `dockerContext`, `buildFilter.paths`, `envVars`, `sync: false`, `fromService ... property: hostport` | conhecidos da especificação do Blueprint [SUPOSIÇÃO] |
| o cron job aceita os planos `starter`, `standard` e `pro`, e **não aceita disco** | [SUPOSIÇÃO] |
| `plan: standard` = 2 GB e 1 CPU; `starter` = 512 MB e 0,5 CPU | [SUPOSIÇÃO] |
| cobrança pelo tempo rodado: ~US$ 0,00058 por minuto no Standard, ~US$ 0,00016 no Starter, mínimo de US$ 1/mês por cron job | [SUPOSIÇÃO]: o Alexandre confere em Render > Pricing antes do "autorizo" |
| `schedule` em UTC; uma execução por vez (a próxima não começa enquanto a anterior roda); teto de 12 h por execução | [SUPOSIÇÃO] |
| o cron alcança o site pela rede privada da mesma região (`hostport`), sem TLS dentro da rede do Render | [SUPOSIÇÃO]: o diagnóstico mostra. Se não alcançar, troca para a URL pública com HTTPS |
| `generateValue: true` e `fromService ... envVarKey` | [SUPOSIÇÃO]. Plano B, se o Render recusar o `envVarKey` no cron: `sync: false` nos dois serviços, e o Alexandre cola nos dois **o mesmo valor de 32 bytes aleatórios, gerado no PC dele** (`python -c "import secrets; print(secrets.token_urlsafe(32))"`), nunca em recado |
| `autoDeploy: true` no cron | igual ao site (ADR 0001, adendo 4) |

## 3. O `Dockerfile` e o `.dockerignore` (texto; entram no repositório depois do `donos.json`)

**Dono proposto:** **engenheiro-software**, como base técnica (a imagem, a versão do Playwright, o `requirements-visitas.txt`). O código que roda dentro (`nuvem/visitas/rodar.py`, `agenda.py`, `__init__.py`) é do **modulo-robo**. Não é do modulo-web: o cron não é o site e não fica em `web/` (o site tem `rootDir: web`, e código do cron ali faria o site refazer deploy a cada mudança do cron).

Hoje `nuvem/**` e `.dockerignore` são "sem-dono", e o guardião bloqueia. **As 3 linhas do `.coord/donos.json`** (`nuvem/visitas/Dockerfile` e `.dockerignore` → engenheiro-software; `nuvem/**` → modulo-robo, nessa ordem, porque a primeira que casa vence) estão só no `docs/desenho/T-0045-governanca.diff`.

Texto: `nuvem/visitas/Dockerfile` e `.dockerignore` (o arquivo manda). As decisões:

- **Imagem:** `mcr.microsoft.com/playwright/python:v<versão>-noble`, com a mesma versão do `playwright==` do `requirements-visitas.txt` (trocar uma = trocar a outra). [SUPOSIÇÃO] `v1.49.1-noble`: Ubuntu 24.04, Python 3.12 e Chromium já dentro; o `pip` usa `--break-system-packages` (PEP 668).
- **Lista fechada no `COPY`:** `requirements-visitas.txt`, `visitas_maxima.py`, `visitas_nucleo.py`, `relatorios_nucleo.py`, `bap_dados.py`, `painel_farol.py` e `nuvem/visitas/`. Proibido copiar a raiz inteira: levaria as bases (`RELATORIOS/`, com dado de cliente) para a imagem. Todo arquivo do `COPY` tem de estar no `buildFilter`; se o `rodar.py` precisar de outro arquivo, ele entra nos dois, e nunca uma pasta inteira.
- **`painel_farol.py`:** o `relatorios_nucleo.py` importa `pct_do_liquido` dele no topo; sem ele, a trava de import quebra o build. O `painel_farol.py` só importa a biblioteca padrão. **Pendente (governança):** ele ainda falta no `buildFilter` do `render.yaml`; até entrar, mudar só nele não refaz a imagem.
- **Pacote `nuvem` sem `__init__.py` (decisão do gerente, 27/11):** `nuvem` é pacote namespace (PEP 420, Python 3.12); só `nuvem/visitas/__init__.py` existe. A imagem leva só `nuvem/visitas/`, que é o que o `buildFilter` (`nuvem/visitas/**`) cobre; um `nuvem/__init__.py` ficaria fora do filtro. O `ENV PYTHONPATH=/app` faz `import nuvem.visitas.rodar` achar o pacote em qualquer diretório. Se um dia for preciso um `nuvem/__init__.py`, ele entra no `COPY` e no `buildFilter` juntos.
- **tini como PID 1:** recolhe os processos do Chromium e repassa o SIGTERM ao Python (contrato, §2). [SUPOSIÇÃO] o apt do Ubuntu 24.04 tem o tini, e a imagem roda como root até o `USER pwuser`.
- **Trava de import (ADR 0004, adendo 1):** `RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"` antes do `USER`: sem o código no `main`, o build falha e nada roda. Importar o `rodar.py` não pode fazer nada (nem rede, nem navegador, nem segredo).
- **Imports no topo:** o `visitas_nucleo.py` importa o `xlsx_rapido`, o `meta_nucleo` e o `pastas_bap` só dentro de funções de montagem, que a nuvem não chama; o `ler_espelho` cai no `openpyxl` quando não acha o `xlsx_rapido` (por isso ele está no `requirements-visitas.txt`). O `relatorios_nucleo.py` importa no topo a biblioteca padrão, o `bap_dados` e o `painel_farol`; o `bap_dados.py` e o `painel_farol.py`, só a biblioteca padrão (importar não carrega `pandas`, `openpyxl`, `meta_nucleo` nem `pastas_bap`).
- **`.dockerignore` (raiz, porque o `dockerContext` é `.`):** tira as bases, os arquivos sensíveis (regra 5: `**/auth/`, `**/.env`, `**/*_config*.json`) e o resto do contexto, o que encurta o envio ao builder. Nenhuma linha casa com o que o `COPY` precisa; a proteção da imagem continua sendo a lista fechada.
- Teste (agente testes): o `Dockerfile` não tem `COPY .` nem `ADD .`; tem o `RUN python -c "import nuvem.visitas.rodar, ..."` antes do `USER`; importar o `nuvem.visitas.rodar` não chama rede nem lê `BAP_MAXIMA_*`; não existe `*.dockerignore` nem fixture com dado em `nuvem/visitas/` (a pasta entra inteira na imagem); a tag da imagem é a mesma versão do `playwright==` do `requirements-visitas.txt`; todo arquivo do `COPY` está no `buildFilter`.

## 4. Ordem do merge

ADR 0004, §9 (itens 2, 7, 8, 10 e 11).
