# Quadro — BAP Tools

Atualizado em 26/11/2026, 18h30 (Manaus). Dono: gerente-projetos.

**26/11, 18h30 — PAUSA até 22h30 (R-20261126-182227-alexandre):** nada pela metade, nada instalado, ronda apagada, subagentes parados com o trabalho em branch (heads na passagem R-20261126-182500-gerente-projetos). Decisões de 26/11: 8 do plano = A (R-20261126-180314), manual da marca do BapAjuda com as 9 lacunas = A, ADR 0003 §4.4 = A (R-20261126-182227).

**26/11, 17h40 — retomada na nuvem (R-20261126-173916-alexandre):** de 25/11 03h50 a 26/11 17h o trabalho foi na sessão "BAPCentral - Cowork" (outra conta, sem guardiões nem ronda). Os 33 commits do período (42a020e..c8f6004) foram conferidos com o `verificar --por-commit`: nenhuma violação de dono; #112 (T-0021) e #116 (T-0029) juntaram vários donos num squash só. Passagem: R-20261126-173917-po. Decisões de 25 e 26/11: pasta de produção da EMPRESA (R-20261125-090000), robô oficial no notebook do Alexandre (R-20261125-104000), BC3/M3 e RN-GER-013 (R-20261126-171559). Plano e previsões: R-20261126-174414-gerente-projetos.

**24/11, noite — volta ao Claude Code na nuvem:** gerente fixo no ambiente BapCentral-GP (BAP_AGENTE=gerente-projetos), PO fixo no BapCentral-PO, guardiões e ronda de 20 min de volta. Sessões fixas em Opus 5.5 alto; tarefas e subagentes em Opus 5.5 médio (R-20261124-173350-gerente-projetos). O robô rodou no notebook do Alexandre: primeiro pacote no site às 18h07 (T-0013/T-0014 esperam a conferência dele).

**T-0017 (alta):** detalhes na linha da tabela e em `.coord/tarefas/T-0017.md`.

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
| T-0017 | Os 4 faróis do PC no site com todas as abas | concluida (#69–#76 no main, 25/11; site v0.3.0) | engenheiro-software + modulo-robo + modulo-web + modulo-farois + testes | — | — | concluída em 25/11 |
| T-0018 | Rotina diária de atualização da produção (`--diario`, 06h30) | concluida (#59, #60, #61; #77 regra 11 com a pasta da EMPRESA, R-20261125-090000-alexandre) | engenheiro-software + testes + alexandre (governança) | — | — | robô oficial no notebook do Alexandre (R-20261125-104000) |
| T-0019 | Agente revisor-ux (UX, redundância e marca) | concluida (#78, autorizado no R-20261125-183000-alexandre) | alexandre (governança) | — | — | concluída em 25/11 |
| T-0020 | Visual C da BAP, tabelas de baixo lado a lado, repetições cortadas (web) | concluida (#79) | modulo-web | — | — | concluída em 25/11 (R-20261125-174000-alexandre) |
| T-0021 | Edição do Farol de Pedidos e Entregas na web (só admin), CSVs do Protheus, edições chegam ao PC pelo robô | concluida (v4: #109–#112; v1 nunca entrou) | modulo-web + modulo-robo + engenheiro-software + testes | — | — | concluída em 26/11 |
| T-0022 | Painel Executivo (12 abas) e Farol de Metas Equipe na web | concluida (#101, #104) | modulo-web + modulo-robo + testes | — | — | falta o Painel no BC3 (passo 3 da passagem) |
| T-0023 | Faróis de Garantias, Devoluções e NCC na web (edição só admin) | em_andamento (PRs #102, #103, #105, #106 empilhados na T-0021 v1: refazer sobre o main com as decisões de 26/11) | modulo-web + modulo-robo + modulo-farois + testes | — | — | simulação 27/11 06h |
| T-0024 | Faróis do lote 2 na web (indicadores, Clientes, Roteirização, Giro, Estoque FRW) | em_andamento (#89 web 34c07e9 no BC3 com GRADE, reteste do designer-ux pendente; #91 robô 9753598 com vc_base por UF e Planner sem recorte; #97 testes 034ce39 verde no combinado) | modulo-web + modulo-robo + testes | — | — | simulação ao po após o reteste; merge #91 → #97 → #89 |
| T-0025 | Farol DDR, Campanhas e Expositores na web | em_andamento (PRs #93, #98, #100, #107 empilhados na T-0021 v1: refazer; diretor só Resumo, TOTAL A PAGAR só admin/gerente/diretor, champions_config.json pela web só admin) | modulo-web + modulo-robo + modulo-farois + testes | — | — | simulação 27/11 06h |
| T-0026 | Paridade dos 4 faróis na web (parcial em imagem, Excel/PDF, 5 abas da Inadimplência) | em_revisao (#80, #81 no main; #82 c9a9343 com o caso positivo pedido pelo revisor: falta CI e revisão nesse head) | modulo-web + modulo-robo + testes | — | — | merge após revisão |
| T-0027 | Parcial com a marca, Excel sem NaN, corte do pacote grande, RN-GER-012, robô do pós-venda | concluida (#90, #92, #94, #95, #96, #99) | modulo-robo + modulo-web + modulo-posvenda + testes | — | — | concluída em 25/11 |
| T-0028 | Farol de Pedidos sem rolagem, popup do pedido, tabelas de baixo lado a lado | concluida (#114) | modulo-web | — | — | concluída em 26/11 |
| T-0029 | RN-GER-013: pedido de cliente fora da base | concluida (#116, #117, #118, #120, #122) | modulo-farois + modulo-robo + modulo-web + testes + gerente | — | — | parte do robô chega pela rotina diária |
| T-0030 | Farol de Pedidos no visual BC3 (PC numa tela; celular M3) | concluida (#115) | modulo-web | — | — | concluída em 26/11 |
| T-0031 | Todos os faróis no BC3 e no formato do Farol de Pedidos | concluida (#123, c8f6004) | modulo-web | — | — | concluída em 26/11 |
| T-0032 | Botões das parciais como no PC, caixa fora da base com o nome antigo; correção do celular | concluida (#124 8cda492, entrou sem simulação; #126 4e1abd8 correção do celular, com o ok do Alexandre) | modulo-web | — | — | concluída em 26/11; botão "Cobrar no WhatsApp" sai na T-0033 (7 A) |
| T-0033 | Revisão geral de todos os faróis (marca, UX, redundância), grade × popup, contrato visual BC3, manual da marca | em_andamento (contrato tela-bc3 04c38e5; web modulo-web/T-0033-revisao-geral f42ee18 WIP, 23 testes a atualizar; #127 marca na cobrança aprovado; manual da marca design-de-marca c8c60fc aprovado — tirar "RASCUNHO") | engenheiro-software + modulo-web + modulo-posvenda + design-de-marca + testes | — | — | previsão refeita na retomada de 22h30 |
| T-0034 | Página inicial = Painel Executivo no BC3/M3; Usuários e Senha no BC3; pré-venda/pós-venda/vendas abrem no 1º farol da área | aberta | modulo-web + testes | — | — | depois da T-0033 |
| T-0035 | Pacote por farol (ADR 0003) | em_andamento (contrato e97761f; web 527004f v0.4.0; robô 5231f19; testes b116d1f WIP; achados de anexos e corte do Entregas para o robô) | engenheiro-software + modulo-web + modulo-robo + testes | — | — | selo "Desatualizado" aprovado (§4.4 A) |
| — | Farol de Fretes com edição (passo 5) | aberta | — | — | — | próxima leva (decisão de 26/11) |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Tarefas à parte (sem número ainda):** cobrança usar `relatorios_nucleo.sem_documento` (modulo-posvenda); tela do PC usar `solicitacao_bap.tipos_colunas` (modulo-farois); RD-0030 (filtro de linhas copiado da tela); RD-0031 (fuso de Manaus em 3 funções); RD-0014 (constante 000040).

**Reservas:** a próxima tarefa é a T-0036 (T-0036 a T-0044 reservadas pelo plano R-20261126-175814). A próxima ADR livre é a 0004.

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
