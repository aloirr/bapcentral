# Quadro — BAP Tools

Atualizado em 20/11/2026, 10:12 (Manaus). Dono: gerente-projetos.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | BapCentral-GP | — | concluida às 10:03 |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | em_andamento (sessão filha, engenheiro-software) | engenheiro-software | sessão filha (BapCentral-GP) | `.coord/contratos/**`, `docs/desenho/T-0002.md` | PR 11:45 |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | em_andamento (sessão filha, engenheiro-software) | engenheiro-software | sessão filha (BapCentral-GP) | `ATUALIZAR_DO_GITHUB.bat` | PR 12:15 |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, 8cd54cb; falta smoke_processos) | engenheiro-software (proposta; governança) | BapCentral-Governanca (próxima sessão) | — | smoke_processos no CI 11:30 |
| T-0005 | Pendências herdadas do Maestro Sistemas (recado `20261109-1015`, Git na DT-AMADMBAP-03, robô de visitas) | aguardando_alexandre (R-20261120-100628-gerente-projetos) | gerente-projetos | BapCentral-GP | — | aguarda você |
| T-0006 | Plano da BAP Central na web (ADR: Render, login, renderizador do contrato) | em_andamento (sessão filha, engenheiro-software) | engenheiro-software + modulo-web | sessão filha (BapCentral-GP) | `docs/decisoes/0001-*` | PR 12:45 |
| T-0007 | Modo git no `coord.mjs` (proxy barra a API de escrita) e fuso de Manaus nos ids | em_andamento (desenho no main; código na sessão de governança) | engenheiro-software (proposta; governança) | BapCentral-Governanca, PR #5 (head 3d0525f) | `scripts/coord*.mjs` | PR pronto; merge aguarda você |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | em_andamento (doc 07 no main; governança na sessão de governança) | gerente-projetos (governança: texto ao Alexandre) | BapCentral-Governanca, PR #4 (head 2b093e6) | `.claude/agents/po.md`, `.claude/agents/gerente-projetos.md`, `.coord/donos.json` | PR pronto; merge aguarda você |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | aberta (autorizada no R-20261120-100513-alexandre) | gerente-projetos (governança) | BapCentral-Governanca, depois da T-0007 e da T-0008 | `.claude/hooks/**` | PR 11:40 |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0010. A próxima ADR é a 0001.

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
