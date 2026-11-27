# T-0060 · simulação antes × depois (decisão 43: hoje conta)

Bases congeladas; **hoje = 2026-11-19** (último dia com NF; o 20/11 não tem dado) [SUP]. Mês 11/2026, sem filtro.
Antes = main ba2f2a8 (hoje fora do DU). Depois = worktree (`relatorios_nucleo.PROJECAO_COM_HOJE = True`; `VOLUME_COM_HOJE = True`).
PNGs (1366 e 390): `painel_*.png` (cartões do Painel), `estados_*.png` (barras por UF, Saldo e Metas, com cartão × soma dos estados).
RR: sem venda no mês nas duas bases (Saldo em branco, Metas R$ 0).

| Número | Antes | Depois | Valor × regra |
|---|---|---|---|
| Real do Painel | R$ 112.701 | "Real até 19/11" R$ 112.701 · 13 de 19 DU | decisão 43: um Real só, sem "até ontem / + hoje" |
| R$/dia | R$ 9.131 | R$ 8.669 | 112.701 ÷ 13 DU (antes 109.575 ÷ 12) |
| Projeção | R$ 173.494 | R$ 164.717 | 112.701 ÷ 13 × 19 |
| Ating. projetado | 25% [antes: base 693 mil, árvore sem config; ver nota] | 11% | projeção ÷ desafio R$ 1.500.000 (comparável: 173.494 ÷ 1.5 mi = 11,6%) |
| Volume | 2.497 (proj. 3.848) | 2.497 (proj. 3.649) | hoje entra; fator 19/13 |
| Positivados | 45 | 45 (nada de "43 até 18/11") | líquido > 0 no mês, sem 000040 |
| Pedidos faturados (aba Itens) | 58 | 58 | chave filial+pedido, líquido > 0, sem 000040 |
| Ticket por pedido | R$ 2.039 (bruto) | R$ 1.943 | líquido 112.701 ÷ 58 |
| Pedidos (Farol de Pedidos) | "Pedidos" 113 | "Pedidos digitados" 113 | só rótulo |
| Diretor: Faturamento líquido | R$ 110 mil (até 18/11, 12 DU) | R$ 113 mil (13 de 19 DU) | `painel_diretor` corte_a = hoje; bate com o Executivo |
| Diretor: Positivação | 43 | 45 | idem |
| Saldo, Faturado: soma das barras UF | R$ 118.254 (bruto) | R$ 112.701 (PA 19.589 · MA 59.536 · AM 33.576) | D2d: devolução R$ 5.552 separa bruto e líquido |
| Metas, Faturamento por UF | PA 21.286 · MA 64.695 · AM 36.486 | iguais | fator agora sem corte de hoje; soma = cartão |
| Cadastros com compra (RRM) | PA 3 · MA 1 · AM 1 | iguais, agora exige líquido > 0 | item 4; Metas mostra AM 0 (causa não achada) |
| TMA | 0,25 h (15 min) | 0,2647 h (00:15:53) | item 7 |

Nota: a coluna "Antes" do desafio/ating. veio de uma árvore sem os .json de runtime; compare a projeção, o real e o R$/dia, que não dependem disso.

## Ainda NÃO bate
O Farol de Metas mostra "Projeção do mês R$ 122.466" porque `meta_nucleo.dias_uteis_restantes` conta hoje como dia que falta (`d >= hoje`). Com a decisão 43 isso tem de ser `d > hoje` (modulo-metas); depois disso a projeção do Metas e a do Diretor (164.717) coincidem.
Grupo B (hoje fora, sem rótulo novo de período nos cartões de TMA/TMD/jornada, markup): não rotulei [pendente].
