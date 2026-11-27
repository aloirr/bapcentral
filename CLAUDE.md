# BAP Central (BAP Tools) — guia do repositório para o Claude Code

> Repositório `aloirr/bapcentral` (20/11/2026). A BAP Central reúne os relatórios, o BAP Tools e, no roadmap, a versão web no Render, alimentada pela sincronização diária feita no PC pelas assistentes.
> **Catálogo fica fora daqui.** Tudo de catálogo, base unificada, base de produto, catálogo gráfico e catálogo digital mora no `aloirr/bapajudacatalogo`. Aqui fica só a cópia da base unificada que o BAP Tools lê (`BAP Ajuda 2.0/BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx`, congelada). Pedido de mudança no catálogo vira recado do po ao Alexandre, para o time do catálogo.

Programas da área comercial da **BAP AUTOPARTS** (Grupo PMZ, Manaus):
- o robô que baixa os dados do ERP;
- os faróis e o Painel do Diretor;
- metas e RV, rota (Planner) e pós-venda;
- e, no roadmap, a **BAP Central na web (Render)**.

Python 3.12; as telas atuais são Tkinter (Windows). Tudo em **português do Brasil** (respostas, recados, commits, docs). Horário para pessoas: **Manaus (UTC−4)**.

## Quem é você nesta sessão
- A variável **`BAP_AGENTE`** do ambiente do claude.ai/code diz o papel. O hook `SessionStart` (`.claude/hooks/papel-da-sessao.mjs`) imprime as instruções do agente no início da sessão.
  - Ambiente **BapCentral-PO** → `po`: conversa com o Alexandre.
  - Ambiente **BapCentral-GP** → `gerente-projetos`: comanda o time.
- Sem a variável, a sessão é **restrita**: os guardiões não deixam alterar nada.
- Os outros agentes rodam como **subagentes** chamados pelo gerente-projetos (ferramenta Agent).

## Documentos
- `docs/produto/` — 01 visão · 02 módulos · 03 regras (RN) · 04 arquitetura e dados · 05 roadmap · 06 integrações · 07 time e coordenação.
- `docs/legado/` — **congelado**: a memória do trabalho no Cowork até 20/11/2026. Inclui:
  - o diário do Maestro Sistemas;
  - `processo_bap_out2026.md`, `rotinas_time_comercial_out2026.md` e `INSTALACAO_ROTA_1710.md` (o **item 0 manda na rota**);
  - o histórico do BAP Tools.
- Decisões: `docs/decisoes/` (ADR). Status: `docs/status/`. Especificações do PO: `docs/produto/specs/`.

## Estrutura (igual à pasta de produção `Regionais - Leandro`)
- Raiz: programas `.py`/`.bat` e configurações `.json`.
- `RELATORIOS/`, `SISTEMA BAP/` e `BAP Ajuda 2.0/`: **bases, congeladas** (o dado vem do robô).
- `.coord/`: o time; `scripts/coord.mjs`: a CLI dos recados.
- `web/`: a versão web, quando nascer.

## Comandos
- `python -m compileall -q .` · `python smoke_relatorios.py` e `python smoke_processos.py` (um por vez) · `pytest tests/`
- Coordenação: `node scripts/coord.mjs` (caixa, enviar, lido, ler, fio, pendencias, dono, verificar).

## Recados (repositório próprio)
- O repositório **`aloirr/bapcentral-recados`** (privado) é a fonte única dos recados.
- O `coord.mjs` lê direto lá pela API do GitHub, com o token **`BAP_RECADOS_TOKEN`** do ambiente (fine-grained, só "Contents: read and write" nesse repositório).
- Na nuvem, o proxy barra a gravação pela API: recado e lido são gravados com `git` no clone do repositório de recados anexado à sessão, com push direto no `main` (decisão do Alexandre, R-20261120-092924-alexandre). O modo git do `coord.mjs` é a T-0007.
- O Alexandre também escreve pelo **formulário de issue "Recado"** do repositório de recados: a Action transforma em recado para o gerente-projetos.
- Recado é imutável: responda com recado novo. Nada de recado em commit do código.

## Regras inegociáveis
1. **Cada agente altera só os próprios caminhos** (`.coord/donos.json`). Para o resto, recado ao dono. O guardião (`.claude/hooks/guarda-donos.mjs` e `guarda-bash.mjs`) bloqueia; não contorne.
2. **Regra de negócio em função pura, com teste citando a RN** (`def test_RN_META_003_...`).
3. **`bap_dados.VERSAO` fica em 27.** Regra nova de cache = marca nova na assinatura do bloco.
4. **Datas:**
   - fuso America/Manaus;
   - dia útil = seg a sex, menos os feriados do Planner do mês;
   - **hoje fica fora do DU e da projeção**;
   - projeção = real ÷ DU fechados × DU do mês.
5. **Segredos só em variável de ambiente ou no cofre do Windows.** Nunca no código, em log, em recado ou em commit. **Proibido** ler `tomtom_config*.json`, `google_maps_config*.json`, `visitas_config.json`, `**/auth/**` e `.env`.
6. **Dados pessoais:** sem CNPJ, nome, telefone ou e-mail de cliente ou vendedor em log, fixture ou print de recado.
7. **Dado digitado é intocável:**
   - `_EDICOES_POS_VENDA`, `_NCC`, `_GARANTIAS`, `_AUTORIZACOES`;
   - `champions_config.json`, `transportadoras_config.json`, `painel_diretor_config.json`.
   - Planilha de acompanhamento: só acrescentar linha.
8. **Regras de negócio do Alexandre** (detalhe em `docs/produto/03-regras.md`):
   - **desafio comercial em tudo** (meta RH só no Exportar para o RH, no e-mail e na parcial de RV);
   - faturado = líquido de devolução, pela data da NF;
   - positivação = líquido > 0 no mês;
   - CNPJs internos (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA) e a conta 000040 fora;
   - estado = filial da nota;
   - inativo sem movimento oculto;
   - "BAP AUTOPARTS" nos materiais.
9. **TI da empresa:** nada que dependa de registro de aplicativo no Microsoft 365/Graph.
10. **"Simule" = mostrar antes.** Tela, PDF, e-mail ou número do Diretor: primeiro a simulação (PNG/PDF), depois o PR.
11. **Produção no PC:** a rotina diária (`atualizar_do_github.py --diario`, tarefa agendada às 06h30 no notebook do robô) leva os `.py`/`.bat` da raiz do `main` para a pasta de produção (a da EMPRESA, compartilhada com as assistentes, R-20261125-090000-alexandre; a pessoal ficou só como cópia), com backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_DIARIO_<MÊS><ANO>` e conferência byte a byte. Só instala se: (1) o commit tiver 2 h ou mais no `main`; (2) o PR de origem teve CI verde no head SHA; (3) a versão da web no `main` for igual à do `/saude`; (4) estiver na janela 06h00–07h30 de Manaus, com o robô parado; (5) a trava "instalado por fora" não tiver disparado. Falha = nada trocado + uma linha no log; pausa por `SISTEMA BAP\PAUSAR_ATUALIZACAO`. Os `.bat` de instalação, o `atualizar_do_github.py`, o `tarefa_bap.xml` e as configs continuam com o **"instale" do Alexandre** (ADR 0002).
12. **"MENOS É MAIS" (R-20261127-174849-alexandre, vale para todos os agentes):** toda página (tela da web, tela do PC, PDF, e-mail) fica **totalmente preenchida na horizontal antes de descer**: cartões, tabelas e blocos ocupam a largura útil, sem coluna vazia nem bloco solto, e só depois quebram para a linha de baixo. As páginas usam **tamanhos padrão** (mesma largura útil, grade, alturas de cartão, fontes e espaçamentos em todas) e seguem **padrão de mercado, a marca BAP AUTOPARTS (manual), sem redundância** e com o design do time. Toda simulação (regra 10) é conferida contra esta regra pelo designer-ux/revisor-ux, design-de-marca e corretor-redundancias; a de tela da web mostra 1366 px e 390 px, e a de tela do PC, PDF ou e-mail mostra o tamanho real. **Botões sempre embaixo e juntos** (R-20261127-175849-alexandre): cada bloco tem uma barra de botões só, no rodapé, com todos juntos (ação principal à esquerda, destrutivos à direita); as ações da página ficam na barra do rodapé da página; fora dela, só a busca e os links de linha. Vale também nos PDFs, onde couber. Na tela, a barra do rodapé da página fica **fixa embaixo, sempre à vista** (decisão 49, R-20261127-182559-alexandre). Numa grade de cartões, a **última linha estica os cartões até preencher a largura, sem buraco** (decisão 50; vale no Painel do Diretor, com 3 cartões por linha).

## Git e PR
- Branch `<agente>/T-nnnn-<assunto>`. Commit `T-nnnn: <resumo>` + trailer `Agente: <dono>`.
- **Um PR por dono e por lote.** Merge (squash) só pelo gerente-projetos, com:
  - CI verde no head SHA;
  - revisão do `revisor-codigo` sem 🔴;
  - `verificar` limpo.
- **Governança** (`.claude/**`, `.coord/donos.json`, `scripts/coord*.mjs`, `scripts/recados/**`, `.github/**`, `render.yaml`, `.gitignore` e os `.json` da raiz): só com o recado do Alexandre "autorizo o merge do PR #N no commit <sha>".
- **Proibido:** force push, push direto ao `main`, rebase do `main`, merge com CI vermelho, apagar histórico.

## Definição de pronto
- `compileall` e testes verdes. Smokes só com as falhas conhecidas (lista no agente `testes`).
- Critérios da tarefa demonstrados pelo `testes`, com valor × regra em todo número; **número do Diretor bate com o farol de origem**.
- Parecer do `revisor-codigo` sem 🔴 nem 🟡 em aberto, no head SHA do PR.
- Parecer do `corretor-redundancias` sem achado em aberto (toda tarefa) e, quando couber, do `designer-ux` (tela, PDF, e-mail) e do `design-de-marca` (identidade visual), no head SHA do PR.
- `node scripts/coord.mjs verificar --base origin/main` sem violação.
- Quadro, backlog e docs atualizados. Recado `entrega` ao `po` (cc `alexandre`) com "como testar em 5 passos".
