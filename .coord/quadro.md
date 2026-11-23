# Quadro — BAP Tools

Atualizado em 23/11/2026 (Manaus). Dono: gerente-projetos.

**RETOMADA:** a pausa de 20/11 acabou. O Alexandre retomou o BapCentral numa sessão do Cowork em 22/11/2026 (R-20261122-182900-alexandre e R-20261122-183000-alexandre): sem os guardiões do Claude Code, sem agendamento, ronda ou timer; GitHub operado pelo site; merge de governança pela delegação de 20/11. Nada vai ao PC sem o "instale"; nada no Render sem o ok dele.

| Tarefa | Título | Status | Dono | Onde | Caminhos travados | Previsão (Manaus) |
|---|---|---|---|---|---|---|
| T-0001 | Conferir a montagem: CLI, guardiões, recados no GitHub, sessões PO e GP | concluida (10:03) | gerente-projetos | — | — | concluída |
| T-0002 | Contrato do relatório (`.coord/contratos/relatorio.md`) e mapa dos módulos | concluida (PR #8, `5140af4`) | engenheiro-software | — | — | concluída |
| T-0003 | `ATUALIZAR_DO_GITHUB.bat`: levar o `main` para a pasta de produção com backup e byte a byte | concluida (PR #20 `cf4eca6`, PR #21 `d0a518b`; 90 testes; parecer R-20261123-063245-revisor-codigo) | engenheiro-software + testes | — | — | concluída em 23/11; primeiro uso no PC só com o "instale" do Alexandre, depois do `--simular` na pasta de produção |
| T-0004 | CI: `compileall` + `verificar` + `smoke_processos` no PR | em_andamento (YAML corrigido no main, `8cd54cb`; falta smoke_processos) | alexandre (governança) | BapCentral-Governanca (próxima sessão) | `.github/workflows/ci.yml` | retomada em 22/11 (R-20261122-182900-alexandre) |
| T-0005 | Pendências herdadas do Maestro Sistemas | concluida (10:15) | gerente-projetos | — | — | concluída |
| T-0006 | Plano da BAP Central na web (ADR 0001) | concluida (PR #7, `9afbe4d`) | engenheiro-software | — | — | concluída |
| T-0007 | Modo git no `coord.mjs` e fuso de Manaus nos ids | concluida (PR #2 `c96a153`, PR #5 `ff2f612`) | alexandre (governança) | — | — | concluída |
| T-0008 | Como o time fala com o Alexandre: 4 blocos, recado ao po de tudo, po sem editar nada | concluida (PR #4, `4f4f504`) | alexandre (governança) | — | — | concluída |
| T-0009 | Guardião aceita `de: alexandre` do po só no clone dos recados | concluida (PR #11, `339a3ea`) | alexandre (governança) | — | — | concluída |
| T-0010 | Gerador do JSON da rota da Máxima: data final curta (RN-ROT-001) | aguardando_alexandre (no main: #9 `5afacae`, #12 `10d9ea0`, #10 `447510a`, #14 `646ff3c`, #23 `ce93876`, #13 `b45b9d8`; simulação na produção no R-20261123-092245-gerente-projetos) | engenheiro-dados + modulo-farois + testes | — | — | recomendação aprovada (R-20261123-092906-alexandre): instalar só os 5 da T-0010 + os 2 do instalador; falta a palavra "instale" |
| T-0011 | Fechar 3 furos antigos do guardião (todos os agentes) | aberta (autorizada no R-20261120-110202-alexandre; não começada) | alexandre (governança) | — | `.claude/hooks/**` | retomada em 22/11 (R-20261122-182900-alexandre) |
| T-0012 | Agentes corretor-redundancias, design-de-marca e designer-ux | aberta (autorizada no R-20261120-113248-alexandre; não começada) | alexandre (governança) + gerente-projetos | — | `.claude/agents/**`, `.coord/donos.json`, `CLAUDE.md`, `docs/produto/07-time-e-coordenacao.md` | retomada em 22/11 (R-20261122-182900-alexandre) |
| T-0013 | Web: onda 0 e primeira entrega (Painel · resultado e Painel · produtividade) | aguardando_alexandre (código no main: #15 `66aacf4`, #16 `e8a9e5d`, #25 `5251f93`, #17 `9b72edf`, #18 `7dc4022`; #19 fechado, substituído pelo #25; testes da web no CI; nada no Render) | modulo-web + modulo-robo + engenheiro-software + testes + alexandre (governança) | — | — | Render: o Alexandre cria os 4 segredos e dá o "aprovo deploy v0.1.0"; passo 4f no PC só com o "instale" e o BAP_WEB_URL/TOKEN no cofre do robô |
| T-0014 | Web: visões prontas por UF e por supervisor para os filtros | aberta (autorizada no R-20261120-122437-alexandre; não começada) | modulo-robo + modulo-web | — | — | retomada em 22/11 (R-20261122-182900-alexandre); depois da entrega da T-0013 |
| T-0015 | `.bat` com o final de linha do Windows (CRLF) no repositório | aberta (autorizada no R-20261123-092906-alexandre; não começada) | engenheiro-software + alexandre (governança: `.gitattributes`, caminho sem dono) | — | `*.bat`, `.gitattributes` | depois da T-0013; antes do primeiro uso completo do `ATUALIZAR_DO_GITHUB.bat` |

**Previsões:** a hora é a do último status do gerente ao po, e cada "Status HHhMM" do po leva a hora nova e o motivo quando ela muda (R-20261120-092924-alexandre).

**Reservas:** a próxima tarefa é a T-0016. A próxima ADR livre é a 0002 (a 0001 é a da T-0006).

**Legenda de status:** aberta · em_andamento · em_teste · em_revisao · aguardando_alexandre · concluida · bloqueada.
