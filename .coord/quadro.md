# Quadro — BAP Tools

Atualizado em 24/11/2026, 19h10 (Manaus). Dono: gerente-projetos.

**24/11, noite — volta ao Claude Code na nuvem:** gerente fixo no ambiente BapCentral-GP (BAP_AGENTE=gerente-projetos), PO fixo no BapCentral-PO, guardiões e ronda de 20 min de volta. Sessões fixas em Opus 5.5 alto; tarefas e subagentes em Opus 5.5 médio (R-20261124-173350-gerente-projetos). O robô rodou no notebook do Alexandre: primeiro pacote no site às 18h07 (T-0013/T-0014 esperam a conferência dele).

**T-0017 (alta):** Farol de Inadimplência no main (#46 a #53, `94ac56d`), simulação aprovada (R-20261124-181912-alexandre). Aguardando o Alexandre: "aprovo deploy v0.2.0", depois "instale" (bap_automation.py, bap_dados.py, relatorios_nucleo.py) e a decisão do 000040 (R-20261124-184942-gerente-projetos). 2ª entrega (WhatsApp, Títulos e Por cliente) aguarda as 6 decisões do R-20261124-182438-gerente-projetos.

**Histórico — 22 e 23/11 no Cowork:** o Alexandre trabalhou numa sessão do Cowork (R-20261122-182900-alexandre e R-20261122-183000-alexandre), sem guardiões nem ronda; os 31 commits do período (646ff3c..b69fda7) foram conferidos commit a commit com o `verificar`: nenhuma violação de dono.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | — | — | concluída |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | concluida (PR #8, `5140af4`) | engenheiro-software | — | — | concluída |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | concluida (PR #20 `cf4eca6`, PR #21 `d0a518b`; 90 testes; parecer R-20261123-063245-revisor-codigo) | engenheiro-software + testes | — | — | concluída em 23/11; primeiro uso no PC só com o "instale" do Alexandre, depois do `--simular` na pasta de produção |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | concluida (#3 `8cd54cb`, #18 `7dc4022`, #27 `9dcfd08`, #43 `b101e16` conferidor das falhas conhecidas, #44 `38e9de4` smoke bloqueante com o "autorizo" do Alexandre) | alexandre (governança) + testes | — | — | concluída em 24/11 |
| T-0005 | Pendências herdadas do Maestro Sistemas | concluida (10:15) | gerente-projetos | — | — | concluída |
| T-0006 | Plano da BAP Central na web (ADR 0001) | concluida (PR #7, `9afbe4d`) | engenheiro-software | — | — | concluída |
| T-0007 | Modo git no `coord.mjs` e fuso de Manaus nos ids | concluida (PR #2 `c96a153`, PR #5 `ff2f612`) | alexandre (governança) | — | — | concluída |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | concluida (PR #4, `4f4f504`) | alexandre (governança) | — | — | concluída |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | concluida (PR #11, `339a3ea`) | alexandre (governança) | — | — | concluída |
| T-0010 | Gerador do JSON da rota da Máxima: data final curta (RN-ROT-001) | concluida (instalada na produção em 23/11, 7 arquivos byte a byte, backup ANTES_T0010_NOV2026; R-20261123-192521-gerente-projetos) | engenheiro-dados + modulo-farois + testes | — | — | concluída em 23/11 |
| T-0011 | Fechar 3 furos antigos do guardião (todos os agentes) | concluida (PR #32 `249380a`, autorizado no R-20261123-184340-alexandre) | alexandre (governança) | — | — | concluída em 23/11 |
| T-0012 | Agentes corretor-redundancias, design-de-marca e designer-ux | concluida (PR #33 `42b66f1`, autorizado no R-20261123-192835-alexandre; PR #34 `d44a13e`, doc 07 e definição de pronto) | alexandre (governança) + gerente-projetos | — | — | concluída em 23/11 |
| T-0013 | Web: onda 0 e primeira entrega (Painel · resultado e Painel · produtividade) | em_teste (v0.1.0 no ar em https://bap-central.onrender.com desde 23/11 21h19, R-20261123-212300-gerente-projetos; passo 4f instalado na produção com o bap_automation.py de 3623986) | modulo-web + modulo-robo + testes | — | — | falta o primeiro pacote do robô: instalação no notebook que roda o robô (instalar_bap.bat, cofre BAP_TOOLS e BAP_WEB) e o número da web igual ao do farol |
| T-0014 | Web: visões prontas por estado para o filtro (supervisor fica para depois) | em_teste (no main: #36 `0169ceb`, #35 `356b90d`, #37 `3623986`, #38 `df697f3`; simulação aprovada no R-20261123-195144-alexandre; bap_automation.py instalado na produção, R-20261123-213700-gerente-projetos) | modulo-robo + modulo-web + testes | — | — | junto com a T-0013: conferir o filtro por estado com o primeiro pacote |
| T-0015 | `.bat` com o final de linha do Windows (CRLF) no repositório | concluida (#28 `19c5110`, `.gitattributes`; #29 teste; #31 `8f31c54`, `ATUALIZAR_DO_GITHUB.bat` guardado em LF) | alexandre (governança) + testes | — | — | concluída em 23/11 |
| T-0016 | Rota por lugar respeita o sábado sem repetição (RN-ROT-002) e a cidade base (RN-ROT-003); smoke da rota limpo | concluida (#41 `a0f1ec2`, #40 `af3b8cf`, #42 `dd7e85d`; `planner_nucleo.py` instalado na produção com backup ANTES_T0016_NOV2026, byte a byte) | modulo-rota + testes + gerente-projetos | — | — | concluída em 24/11 |
| T-0017 | Os 4 faróis do PC no site: Inadimplência (entrega 1), depois Pedidos, Entregas e Visita | em_teste (entrega 1 no main: #46 `4793fd1`, #47 `89eb4ca`, #48 `a08ab86`, #49 `ec31d36`, #51 `0605f8b`, #50 `e56fe45`, #52 `73a8b4a` v0.2.0, #53 `94ac56d`; números PC × pacote batem, valor × regra) | engenheiro-software + modulo-robo + modulo-web + modulo-farois + engenheiro-dados + testes | — | — | deploy v0.2.0 e "instale" com o Alexandre; 2ª entrega (WhatsApp) 30/11 simulação, 02/12 entrega, após as decisões; Farol de Pedidos 26/11 |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0018. A próxima ADR livre é a 0002 (a 0001 é a da T-0006).

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
