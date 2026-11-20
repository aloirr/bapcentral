# Quadro — BAP Tools

Atualizado em 20/11/2026 (Manaus). Dono: gerente-projetos.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | — | — | concluída |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | concluida (PR #8, `5140af4`) | engenheiro-software | — | — | concluída |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | em_andamento (desenho no branch; código depois do PR #4) | engenheiro-software | branch `engenheiro-software/T-0003-atualizar-do-github` | `ATUALIZAR_DO_GITHUB.bat`, `atualizar_do_github.py` | PR depois do merge do PR #4 |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, `8cd54cb`; falta smoke_processos) | alexandre (governança) | BapCentral-Governanca (próxima sessão) | `.github/workflows/ci.yml` | a definir depois da T-0011 |
| T-0005 | Pendências herdadas do Maestro Sistemas | concluida (10:15) | gerente-projetos | — | — | concluída |
| T-0006 | Plano da BAP Central na web (ADR 0001) | concluida (PR #7, `9afbe4d`) | engenheiro-software | — | — | concluída |
| T-0007 | Modo git no `coord.mjs` e fuso de Manaus nos ids | concluida (PR #2 `c96a153`, PR #5 `ff2f612`) | alexandre (governança) | — | — | concluída |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | em_revisao (doc 07 no main; PR #4 só T-0008, head `ff7297d`) | alexandre (governança) | BapCentral-Governanca, PR #4 | `.claude/agents/po.md`, `.claude/agents/gerente-projetos.md`, `.coord/donos.json` | merge com a autorização de governança (pedida ao po) |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | em_revisao (PR #11, head `765602d`) | alexandre (governança) | BapCentral-Governanca, PR #11 | `.claude/hooks/**` | merge com a autorização de governança (pedida ao po) |
| T-0010 | Gerador do JSON da rota da Máxima: data final curta (RN-ROT-001) | em_revisao (PRs #9, #10 e #12 aprovados; #13 e #14 em ajuste/revisão) | modulo-rota + modulo-farois + engenheiro-dados + testes | sessões filhas (BapCentral-GP e BapCentral-Dados) | `planner_nucleo.py`, `bap_planner.py`, `relatorios_nucleo.py` (exportação), `bap_dados.py`, `tests/test_rota_maxima.py`, `tests/test_rota_exportar_protheus.py`, `tests/conftest.py` (também no PR #19 da T-0013, que entra depois do PR #10), `smoke_relatorios.py` | merge do lote hoje; o "instale" só com a frase do Alexandre |
| T-0011 | Fechar 3 furos antigos do guardião (todos os agentes) | aberta (autorizada no R-20261120-110202-alexandre) | alexandre (governança) | BapCentral-Governanca, depois da T-0009 | `.claude/hooks/**` | PR depois do merge do PR #11 |
| T-0012 | Agentes corretor-redundancias, design-de-marca e designer-ux | aberta (autorizada no R-20261120-113248-alexandre) | alexandre (governança) + gerente-projetos | BapCentral-Governanca, depois do PR #4 | `.claude/agents/**`, `.coord/donos.json`, `CLAUDE.md`, `docs/produto/07-time-e-coordenacao.md` | PR depois do merge do PR #4 |
| T-0013 | Web: onda 0 e primeira entrega (Painel · resultado e Painel · produtividade) | em_revisao (PRs #15, #16, #17, #18 e #19; visual aprovado no R-20261120-122437-alexandre) | modulo-web + modulo-robo + engenheiro-software + testes + alexandre (governança: `render.yaml`) | sessões filhas (BapCentral-GP e BapCentral-Governanca) | `web/**`, `bap_automation.py`, `docs/decisoes/0001-*`, `render.yaml`, `tests/conftest.py` (depois do PR #10), `tests/test_T0013_pacote_web.py` | no ar hoje, com "aprovo deploy v0.1.0" |
| T-0014 | Web: visões prontas por UF e por supervisor para os filtros | aberta (autorizada no R-20261120-122437-alexandre) | modulo-robo + modulo-web | — | — | depois da entrega da T-0013 |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0015. A próxima ADR livre é a 0002 (a 0001 é a da T-0006).

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
