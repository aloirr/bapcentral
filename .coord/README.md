# .coord — coordenação do time de agentes do BAP Tools

| Pasta/arquivo | Para quê | Quem altera |
|---|---|---|
| `donos.json` | Dono de cada caminho do repositório (a primeira regra vence) | Só o Alexandre |
| `quadro.md` | Quadro de tarefas | gerente-projetos |
| `tarefas/T-nnnn.md` | Uma tarefa: objetivo, critérios, agentes | gerente-projetos |
| `diario/<agente>.md` | Linha do tempo do agente | O próprio agente |
| `contratos/` | Contrato do relatório e funções públicas entre módulos | engenheiro-software |
| `modelos/` | Modelos de tarefa e recado | gerente-projetos |

**Recados** não ficam aqui: ficam no repositório **`aloirr/bapcentral-recados`**, lidos pelo `node scripts/coord.mjs`. Na nuvem, a gravação é com `git` no clone do repositório de recados, com push direto no `main` (R-20261120-092924-alexandre); o modo git do `coord.mjs` é a T-0007. A marca `/.coord/recados` e `/.coord/lidos` no `.gitignore` liga esse modo.

## O time

| Agente | Papel |
|---|---|
| `po` | Conversa com o Alexandre; transforma o que ele pede em recado ao gerente; devolve o andamento |
| `gerente-projetos` | Planeja, delega, cobra, faz PR e merge; não escreve código |
| `engenheiro-software` | Arquitetura, contratos, ADR, requisitos, instaladores e caminho para a web |
| `engenheiro-dados` | Cache e fotografia de dados, catálogo, Power BI, dados para o Render |
| `modulo-robo` | `bap_automation.py` e o que o robô grava |
| `modulo-farois` | `relatorios_nucleo.py`, telas, cartões, painéis, parciais, BAP Central |
| `modulo-posvenda` | Entregas, garantias, NCC, frete, inadimplência, autorizações, expositores |
| `modulo-rota` | Planner, roteirização, coordenadas, JSON da Máxima |
| `modulo-metas` | Gerador de Meta, RV, Exportar para o RH, saldo, kits |
| `modulo-web` | BAP Central na web (Render) |
| `testes` | Smokes, pytest, valor × regra |
| `revisor-codigo` | Revisão independente de todo PR |

## Sessões no claude.ai/code
- **BapCentral-PO** (`BAP_AGENTE=po`): é onde o Alexandre conversa. Abra quando quiser pedir, corrigir, aprovar ou saber o status.
- **BapCentral-GP** (`BAP_AGENTE=gerente-projetos`): sessão fixa do gerente ("BapCentral - Gerente Projeto"), com ronda a cada 20 min; a do po é a cada 10 min (R-20261120-093725-alexandre).
  - Ela chama os outros agentes como subagentes.
  - Quando a tarefa pede, abre outras sessões com `BAP_AGENTE=<agente>`.
- Nos dois ambientes vai também o **`BAP_RECADOS_TOKEN`** (token fine-grained só com "Contents: read and write" no `aloirr/bapcentral-recados`).

## CLI
- `node scripts/coord.mjs` (sem argumentos mostra a ajuda).
- `caixa <agente>`, `enviar ...`, `lido <agente> <id>`, `ler <id>`, `fio <id>`, `pendencias`, `dono <caminho>`, `verificar [<agente>] [--base origin/main] [--por-commit <faixa>] [--por-dono]`.
- Testes da CLI e dos guardiões: `node --test scripts/coord-recados.test.mjs scripts/coord-verificar.test.mjs .claude/hooks/guarda-agente.test.mjs .claude/hooks/guarda-recado.test.mjs`.
