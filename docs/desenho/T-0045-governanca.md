# T-0045 — O passo único de governança do Alexandre (serviço de visitas na nuvem)

- **Autor:** engenheiro-software · **Data:** 27/11/2026
- **Recados:** R-20261127-094157-alexandre (a nuvem, com um passo só) e R-20261127-094656-alexandre (o mesmo login da Máxima do notebook).
- **O diff:** `docs/desenho/T-0045-governanca.diff`, um só, que aplica com `git apply` sobre o `origin/main` atual (conferido até o 85bc589). Ele leva:
  - **G1:** as 3 linhas do `.coord/donos.json` (`nuvem/visitas/Dockerfile` e `.dockerignore` → engenheiro-software; `nuvem/**` → modulo-robo), depois de `atualizar_do_github.py` e antes de `web/**` e `docs/**`;
  - **G2:** o `render.yaml` com o cron `bap-visitas-maxima` e o `BAP_VISITAS_TOKEN` do site (explicado no `docs/desenho/T-0045-render-yaml.md`);
  - **G3** (carona da T-0036, R-20261127-054626-po): a linha 40 do `.claude/agents/revisor-ux.md`, alinhada à decisão (na faixa, só a data; o "Dados de …, horário de Manaus" só no `title`).
- **Conferido:** `git apply --check` num worktree limpo do `origin/main`; o `donos.json` aplicado é JSON válido (131 regras); o `render.yaml` aplicado é YAML válido; `node scripts/coord.mjs dono` com o arquivo aplicado dá `nuvem/visitas/rodar.py` → modulo-robo, `nuvem/visitas/Dockerfile` e `.dockerignore` → engenheiro-software; `podeAlterar` deixa cada dono e bloqueia o outro; os 120 testes de `scripts/*.test.mjs` passam.

## (a) A frase do Alexandre

Use **depois que o po avisar** que este desenho está no `main`. Abra uma sessão no ambiente **BapCentral-Governanca** (`BAP_AGENTE=alexandre`, o mesmo do PR #57), com o repositório de recados anexado, e cole:

> Atualize o origin/main, crie a branch alexandre/T-0045-governanca a partir dele, rode git apply docs/desenho/T-0045-governanca.diff (se falhar, pare e me diga o erro, sem editar nada à mão), faça um commit só com a mensagem "T-0045: governança do serviço de visitas na nuvem", a linha "Inclui a linha 40 do revisor-ux (T-0036, R-20261127-054626-po)" no corpo e o trailer "Agente: alexandre", confira que git diff --name-only origin/main..HEAD lista só .claude/agents/revisor-ux.md, .coord/donos.json e render.yaml (se listar outro arquivo, pare e me diga, sem dar push nem enviar o recado), dê push sem force, abra o PR para o main e, com o número N desse PR e o SHA completo do head dele, envie o recado com node scripts/coord.mjs enviar --de alexandre --para gerente-projetos --cc po --tipo resposta --tarefa T-0045 --prioridade alta --assunto "Autorizo o merge do PR #N (governança T-0045)" --corpo "autorizo o merge do PR #N no commit <sha>", trocando N e <sha> pelos valores reais, e me mostre o número, o SHA e o id do recado.

- O merge continua com o gerente-projetos: CI verde nesse SHA, revisor-codigo sem 🔴 e `verificar` limpo. Commit novo no PR = novo "autorizo".

## (b) No Render, depois do merge (no máximo 4 passos)

1. Abra o painel do Render, em **Blueprints**, no Blueprint da BAP Central. Se aparecer uma sincronização pendente, confirme (o Render mostra o serviço novo `bap-visitas-maxima`). Se ele já pedir `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` nessa tela, preencha ali, como no passo 3, e pule o passo 2.
2. Abra o serviço **bap-visitas-maxima** > **Environment**.
3. Preencha `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` com **o mesmo usuário e a mesma senha da Máxima que o robô do notebook já usa**, e clique em **Save Changes**. Não precisa criar usuário na Máxima.
4. Diga ao po só "preenchi". O usuário e a senha nunca vão para chat, recado ou print.

**O time faz sozinho:**
- o código (`nuvem/visitas/`, modulo-robo) e depois o `Dockerfile` e o `.dockerignore` (engenheiro-software), cada um no seu PR. O Render refaz o build sozinho (`autoDeploy` com `buildFilter`);
- o diagnóstico automático na primeira volta, a leitura do resultado (tela do admin e `/saude`), os testes e o acompanhamento;
- o po leva o resultado do diagnóstico ao Alexandre. Com o "ok" dele, o admin liga a agenda pelo site.
- Pendência (gerente): o contrato, §6, ainda pede ao Alexandre a duração de 3 voltas sem trabalho no painel. Proposta: sai dos passos dele, porque o custo já foi informado.

## (c) Ordem e risco

**Ordem nova** (ADR 0004, adendo 1; corrige o §9, item 10): 1 → (2 + 10, este PR do Alexandre) → 8 (`nuvem/visitas/`, modulo-robo) → 7 (`Dockerfile` e `.dockerignore`, engenheiro-software) → 9 (testes) → 11 (diagnóstico).

**O primeiro build do cron falha, e isso é aceitável.**
- Sem o `nuvem/visitas/Dockerfile`, o build falha em segundos. Sem imagem, o cron não roda e não há execução a cobrar [SUPOSIÇÃO: o Render cobra o cron pelo tempo rodado; os segundos do build falho entram na franquia de build].
- O site não cai. Ele só faz um deploy normal pela variável nova `BAP_VISITAS_TOKEN`, que não muda a versão do `/saude`.
- Com `autoDeploy: true` e o `buildFilter` (`nuvem/visitas/**`), o Render refaz o build sozinho no commit em que o código e o `Dockerfile` entrarem. Se não refizer [SUPOSIÇÃO], o engenheiro-software faz um commit pequeno no `.dockerignore`, que está no `buildFilter`, e o build sai sem clique do Alexandre.
- **Dentro do Blueprint** não há saída melhor. Não conheço campo que crie o cron já suspenso [SUPOSIÇÃO]. Tirar o cron do `render.yaml` agora exigiria um segundo passo do Alexandre, e ele pediu um só.
- Se o sync do Blueprint recusar o serviço por falta do `Dockerfile` [SUPOSIÇÃO: o Render não confere arquivos no sync], o `Dockerfile` entra logo (a trava abaixo o deixa seguro) e o sync é repetido. Esse é o único caso com um clique a mais.

**Nenhuma imagem roda sem o código:**
- **A ordem dos PRs:** o PR do modulo-robo com o `rodar.py`, o `agenda.py` e o `__init__.py` entra antes. O PR do `Dockerfile` vem depois e é a chave que liga o build. O gerente só faz o merge do item 7 com o item 8 no `main`.
- **A trava no `Dockerfile`** (desenho `T-0045-render-yaml.md`, §3): `RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"`. Se a ordem falhar, o build falha também e nada roda. Isso exige do modulo-robo que importar o `rodar.py` não faça nada (nem rede, nem navegador, nem segredo). O agente testes confere.
- O mesmo PR para os dois não serve: são dois donos, e o guardião barra.

**Login da Máxima (D4 revista):** se a Máxima bloquear o acesso vindo do Render, o notebook pode ser bloqueado também. O diagnóstico faz uma tentativa só, e a pausa segura as seguintes: as garantias e a brecha que fica estão na ADR 0004, adendo 1, item 3.
