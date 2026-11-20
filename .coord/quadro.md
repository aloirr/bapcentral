# Quadro — BAP Tools

Atualizado em 20/11/2026 (Manaus). Dono: gerente-projetos.

**PAUSA:** o BapCentral está pausado por 72 h, até 23/11/2026 ~12:40 (Manaus), pelo R-20261120-123647-alexandre. Nada é retomado sem o Alexandre; nenhum deploy, nada vai ao PC; sem sessões filhas e sem rondas.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | — | — | concluída |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | concluida (PR #8, `5140af4`) | engenheiro-software | — | — | concluída |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | em_andamento (PRs #20 `878d1fb` e #21 `7abe5e9` abertos, 86 testes passando, sem revisão) | engenheiro-software + testes | PRs #20 e #21 | `ATUALIZAR_DO_GITHUB.bat`, `atualizar_do_github.py`, `tests/test_atualizar_do_github.py` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre); na volta: revisão, merge #20 e #21; ida ao PC só com o "instale" |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, `8cd54cb`; falta smoke_processos) | alexandre (governança) | BapCentral-Governanca (próxima sessão) | `.github/workflows/ci.yml` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre) |
| T-0005 | Pendências herdadas do Maestro Sistemas | concluida (10:15) | gerente-projetos | — | — | concluída |
| T-0006 | Plano da BAP Central na web (ADR 0001) | concluida (PR #7, `9afbe4d`) | engenheiro-software | — | — | concluída |
| T-0007 | Modo git no `coord.mjs` e fuso de Manaus nos ids | concluida (PR #2 `c96a153`, PR #5 `ff2f612`) | alexandre (governança) | — | — | concluída |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | concluida (PR #4, `4f4f504`) | alexandre (governança) | — | — | concluída |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | concluida (PR #11, `339a3ea`) | alexandre (governança) | — | — | concluída |
| T-0010 | Gerador do JSON da rota da Máxima: data final curta (RN-ROT-001) | em_revisao (no main: #9 `5afacae`, #12 `10d9ea0`, #10 `447510a`; PR #14 `a2a3d48` aprovado; PR #13 `1b83c87` com 1 🟡: tirar o skipif depois do #14) | engenheiro-dados + testes | PRs #13 e #14 | `bap_dados.py`, `tests/test_rota_exportar_protheus.py`, `tests/conftest.py` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre); na volta: merge do #14, ajuste do #13 sem o skipif, revisão rápida, merge; ida ao PC só com o "instale" |
| T-0011 | Fechar 3 furos antigos do guardião (todos os agentes) | aberta (autorizada no R-20261120-110202-alexandre; não começada) | alexandre (governança) | — | `.claude/hooks/**` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre) |
| T-0012 | Agentes corretor-redundancias, design-de-marca e designer-ux | aberta (autorizada no R-20261120-113248-alexandre; não começada) | alexandre (governança) + gerente-projetos | — | `.claude/agents/**`, `.coord/donos.json`, `CLAUDE.md`, `docs/produto/07-time-e-coordenacao.md` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre) |
| T-0013 | Web: onda 0 e primeira entrega (Painel · resultado e Painel · produtividade) | em_revisao (visual aprovado no R-20261120-122437-alexandre; PR #15 `0ed59ba` com 1 🟡 nas linhas 3 e 289; PR #16 `29c81c4` sem parecer; PR #17 `0a33bd9` corrigido, falta rever o delta; PR #18 `ade157e` sem parecer, falta `pytest web/tests` no CI; PR #19 `1b0e88b` precisa apontar para o main, acertar o conftest e conferir um xfail; nada no Render) | modulo-web + modulo-robo + engenheiro-software + testes + alexandre (governança: `render.yaml`) | PRs #15 a #19 | `web/**`, `bap_automation.py`, `docs/decisoes/0001-*`, `render.yaml`, `tests/conftest.py`, `tests/test_T0013_pacote_web.py` | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre); nenhum deploy nem "instale" |
| T-0014 | Web: visões prontas por UF e por supervisor para os filtros | aberta (autorizada no R-20261120-122437-alexandre; não começada) | modulo-robo + modulo-web | — | — | pausada até 23/11 ~12:40 (R-20261120-123647-alexandre); depois da entrega da T-0013 |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0015. A próxima ADR livre é a 0002 (a 0001 é a da T-0006).

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
