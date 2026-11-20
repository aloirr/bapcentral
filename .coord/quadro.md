# Quadro — BAP Tools

Atualizado em 20/11/2026, 11:20 (Manaus). Dono: gerente-projetos.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | — | — | concluída |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | concluida (PR #8, `5140af4`) | engenheiro-software | — | — | concluída |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | em_andamento (desenho no branch; código depois do PR #4) | engenheiro-software | branch `engenheiro-software/T-0003-atualizar-do-github` | `ATUALIZAR_DO_GITHUB.bat`, `atualizar_do_github.py` | PR 12:30 |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, `8cd54cb`; falta smoke_processos) | alexandre (governança) | BapCentral-Governanca (próxima sessão) | `.github/workflows/ci.yml` | a definir depois da T-0011 |
| T-0005 | Pendências herdadas do Maestro Sistemas | concluida (10:15) | gerente-projetos | — | — | concluída |
| T-0006 | Plano da BAP Central na web (ADR 0001) | concluida (PR #7, `9afbe4d`) | engenheiro-software | — | — | concluída |
| T-0007 | Modo git no `coord.mjs` e fuso de Manaus nos ids | concluida (PR #2 `c96a153`, PR #5 `ff2f612`) | alexandre (governança) | — | — | concluída |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | em_revisao (doc 07 no main; PR #4 só T-0008, head `ff7297d`) | alexandre (governança) | BapCentral-Governanca, PR #4 | `.claude/agents/po.md`, `.claude/agents/gerente-projetos.md`, `.coord/donos.json` | parecer 11:30; merge com a autorização de governança |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | em_revisao (PR #11, head `7af30d8`) | alexandre (governança) | BapCentral-Governanca, PR #11 | `.claude/hooks/**` | parecer 12:15; merge com a autorização de governança |
| T-0010 | Gerador do JSON da rota da Máxima: data final curta (RN-ROT-001) | em_revisao (PRs #9 e #10 em ajuste; PR do modulo-farois) | modulo-rota + modulo-farois + testes | sessões filhas (BapCentral-GP) | `planner_nucleo.py`, `bap_planner.py`, `relatorios_nucleo.py` (exportação), `tests/test_rota_maxima.py` | merge 12:45; instale só com o "instale" |
| T-0011 | Fechar 3 furos antigos do guardião (todos os agentes) | aberta (autorizada no R-20261120-110202-alexandre) | alexandre (governança) | BapCentral-Governanca, depois da T-0009 | `.claude/hooks/**` | PR 13:15, se a T-0009 entrar até 12:30 |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0012. A próxima ADR livre é a 0002 (a 0001 é a da T-0006).

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
