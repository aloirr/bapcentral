# Quadro — BAP Tools

Atualizado em 20/11/2026, 10:05 (Manaus). Dono: gerente-projetos.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados |
|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | em_andamento (formulário aceita a conta aloirr no main; falta a issue de teste do crit. 5) | gerente-projetos | BapCentral-GP | `.coord/**` |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | aberta | engenheiro-software | — | `.coord/contratos/**`, `docs/desenho/**` |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | aberta | engenheiro-software | — | `ATUALIZAR_DO_GITHUB.bat` |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, 8cd54cb; falta smoke_processos) | engenheiro-software (proposta; governança) | — | — |
| T-0005 | Pendências herdadas do Maestro Sistemas (recado `20261109-1015`, Git na DT-AMADMBAP-03, robô de visitas) | aberta | gerente-projetos | — | — |
| T-0006 | Plano da BAP Central na web (ADR: Render, login, renderizador do contrato) | aberta | engenheiro-software + modulo-web | — | `docs/decisoes/**`, `web/**` |
| T-0007 | Modo git no `coord.mjs` (proxy barra a API de escrita) e fuso de Manaus nos ids | bloqueada (D1 aprovada; falta a sessão de governança com BAP_AGENTE=alexandre) | engenheiro-software (proposta; governança) | BapCentral-GP | `docs/desenho/T-0007*` |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | em_revisao (doc 07 no PR; governança aguarda a sessão do Alexandre) | gerente-projetos (governança: texto ao Alexandre) | BapCentral-GP | `docs/produto/07-time-e-coordenacao.md` |

**Reservas:** a próxima tarefa é a T-0009. A próxima ADR é a 0001.

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
