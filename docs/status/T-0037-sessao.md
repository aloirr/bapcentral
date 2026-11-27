# T-0037 — Farol de Fretes com edição na web: relato da sessão de tarefa

- **Sessão de tarefa:** https://claude.ai/code/session_01QvB2STi3xq4ykrr1HFRGBM (papel gerente-projetos, aberta pela sessão fixa).
- **Por que este arquivo:** o `send_message` para a sessão fixa foi recusado ("só sessões do mesmo canal"). O relato fica aqui, atualizado a cada marco.
- **Última atualização:** 27/11/2026 (Manaus).

## Heads (antes → depois do merge do main 8f0600e)

| Branch | Antes | Depois | Estado |
|---|---|---|---|
| `engenheiro-software/T-0037-desenho` | 90807eb | 49fd388 | desenho adaptado ao §10.9, BC3, RN-GER-012/014/016 |
| `modulo-farois/T-0037-fretes` | c818503 | (em curso) | merge + % do faturado líquido (P3 B) |
| `modulo-robo/T-0037-fretes` | 3864370 | (em curso) | merge + `CAMPOS_LUGAR_WEB` |
| `modulo-web/T-0037-fretes` | 1636275 | (a fazer) | merge, `GRADE`, `IRMAOS` explícito, PNGs novos |
| `testes/T-0037-fretes` | 4b88b4b | (a fazer) | merge, RN-POS-009 líquido, marca Fretes × Devolução |

## Etapas

1. Desenho: **feito** (49fd388).
2. Faróis e robô: em curso.
3. Web e simulação PNG (1366 e 390, deviceScaleFactor 2): a fazer.
4. Testes (valor × regra, RN citada): a fazer.
5. Revisões (revisor-codigo, corretor-redundancias, revisor-ux, design-de-marca): a fazer.
6. PR e merge: **com o gerente fixo** (esta sessão não abre PR).

## Decisões (por delegação do po, R-20261127-013010-alexandre)

- P1 A: só o mês do pacote nas 4 abas; o gráfico mostra 12 meses.
- P2 A: o VLR FRETE (REAL) se edita só no Farol de Entregas.
- P3 B: o "% do faturado" usa o faturado líquido de devolução, no PC e na web, no mesmo lote.
- P4 A: o perfil `pos_venda` vê as 4 abas; editar continua só com o admin (RN-GER-012).

## Perguntas em aberto

- **Futura (RN-GER-016):** o `transportadoras_config.json` editável pela web? Só com o "autorizo" do Alexandre para esse arquivo. Na T-0037 o cadastro é só lido.

## PNGs

(nenhum ainda)
