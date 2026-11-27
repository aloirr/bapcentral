# T-0037 — Farol de Fretes com edição na web: relato da sessão de tarefa

- **Sessão de tarefa:** https://claude.ai/code/session_01QvB2STi3xq4ykrr1HFRGBM (papel gerente-projetos, aberta pela sessão fixa).
- **Por que este arquivo:** o `send_message` à sessão fixa foi recusado ("só sessões do mesmo canal"), por isso o relato fica aqui.
- **Onde fica:** branch `gerente-projetos/T-0037-regras`, a mesma das RN-POS-007 a 010 no `03-regras.md`. Saiu da branch do engenheiro para manter um PR por dono.
- **Atualizado em:** 27/11/2026 (Manaus).

## Heads (main base: f3c4569, com #144–#146)

| Branch | Head | Estado |
|---|---|---|
| `engenheiro-software/T-0037-desenho` | 5ddee2c → (correção RD-k e "VND" no contrato) | revisor-codigo: 🟡 em correção |
| `modulo-farois/T-0037-fretes` | 74e128a → (RD-j e multi-UF) | revisor-codigo: aprovado |
| `modulo-robo/T-0037-fretes` | dc2bf4a → (🟢 formatação) | revisor-codigo: aprovado |
| `modulo-web/T-0037-fretes` | 8dadf98 → (RD-f, RD-g, RD-h) | revisor-codigo, revisor-ux e design-de-marca: aprovados |
| `testes/T-0037-fretes` | 3c07ecb → (merge do main, RD-i e rodada do lote) | revisor-codigo: aprovado |
| `gerente-projetos/T-0037-regras` | 04c13fd + este relato | RN-POS-007 a 010 |

Os SHAs finais entram aqui quando as correções terminarem.

## Decisões (por delegação do po: "Aprove as telas e siga")

- **P1 A:** só o mês do pacote nas 4 abas.
- **P2 A:** o VLR FRETE (REAL) fica só no Farol de Entregas; o robô recusa o `frete_real` no Fretes.
- **P3 B:** o "% do faturado" passa a usar o faturado líquido de devolução. Na BAP inteira, NOV/26: 54,76% → 57,46%, pelas bases do repositório. MA: 90,5%.
- **P4 A:** o perfil `pos_venda` vê as 4 abas. Só o admin edita; o diretor vê só o Resumo.

## Pergunta em aberto

- **Futura (RN-GER-016):** tornar o `transportadoras_config.json` editável pela web? Só com o "autorizo" do Alexandre para esse arquivo. Na T-0037 ele é só lido.

## Pontos para o PR (gerente fixo)

- O DDR falha no `smoke_relatorios` porque falta a planilha de 11/2026; acontece igual no main. Incluir na lista de falhas conhecidas.
- Para depois (🟢):
  - um indício visual de que a grade do PC tem mais colunas (SLA e RESPONSÁVEL ficam no popup);
  - o logo e as fontes não carregam no PNG da simulação, porque ela abre por `file://` (`web/simular_*`). No site real estão certos.

## PNGs

Na branch `modulo-web/T-0037-fretes`, em `docs/web/simulacoes/T-0037/`:
- `resumo-pc.png` e `resumo-cel.png`;
- `notas-pc.png`, `notas-cel.png` e `notas-cel-inteira.png`;
- `editar-pc.png` e `editar-cel.png`;
- `sem-chave-pc.png`, `sem-chave-cel.png` e `sem-chave-cel-inteira.png`.

Todos em 1366 e 390 de largura, com deviceScaleFactor 2 e dados fictícios.
