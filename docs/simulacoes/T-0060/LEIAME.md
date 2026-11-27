# T-0060 · simulação final (decisões 43 e 48)

Cópia no scratchpad: wt-t0060b + `meta_nucleo.py` do commit 0d5a448 (modulo-metas). Nada gravado no repositório.
Base congelada; **hoje = 2026-11-19** (último dia com NF) [SUP: o 20/11 não tem dado]. Mês 11/2026, sem filtro.
O `hoje` do Metas foi fixado em 19/11 por monkeypatch só no script (bap_dados.py:1064 chama `mn.acompanhar` sem `hoje`: no PC vale o dia real).
Antes = main ba2f2a8 com o mesmo patch de `hoje`. A coluna "antes" de desafio/meta de visitas vem de uma árvore sem os .json de runtime: compare real, projeção e DU.
PNGs (1366 e 390, deviceScaleFactor 1): `painel_`, `estados_`, `metas_`, `diretor_`. Sem barra de botões nestas telas.

## Conta de conferência do pacote de 27/11
Real R$ 146.673 até agora; projeção 146.673 ÷ 18 × 19 = **R$ 154.821,5**; positivação 58.
O pacote diz R$ 154.826: a diferença de R$ 4,5 sugere que o real exato é ~R$ 146.678 (arredondamento do real) [SUP]. A fórmula do código é a mesma: real ÷ DU passados (hoje incluso) × DU do mês.
Na base congelada (19/11): 112.701 ÷ 13 × 19 = R$ 164.717 (Painel, Diretor e Metas iguais).

## Antes × depois
| Número | Antes | Depois | Valor × regra |
|---|---|---|---|
| Real (Painel) | R$ 112.701 · R$ 9.131/dia | "Real até 19/11" R$ 112.701 · R$ 8.669/dia · 13 de 19 DU | decisão 43: hoje é DU passado (112.701 ÷ 13) |
| Projeção (Painel) | R$ 173.494 | R$ 164.717 | 112.701 ÷ 13 × 19 |
| Ating. projetado | 12% | 11% | 164.717 ÷ desafio 1.500.000 |
| Projeção (Metas, faturamento) | R$ 173.494 | R$ 164.717 | igual ao Painel (meta_nucleo `hoje_conta=True`) |
| Projeção (Metas, positivação) | 68 | 63 | grupo A, hoje conta |
| Projeção (Metas, peças / cad.) | R$ 17.109 / 6 | R$ 16.099 / 6 | rótulo "· até hoje"; **lote 2: passa a até ontem** |
| Volume (projeção) | 3.848 | 3.649 | grupo A com volume (`VOLUME_COM_HOJE`) |
| Positivados | 45 | 45 | líquido > 0, sem 000040 |
| Pedidos faturados | 58 | 58 | chave filial+pedido, líquido > 0 (RN-GER-014) |
| Ticket por pedido | R$ 2.039 (bruto) | R$ 1.943 (líquido) | 112.701 ÷ 58 |
| Diretor: faturamento / positivação | R$ 110 mil / 43 · 12 de 19 DU | R$ 113 mil / 45 · 13 de 19 DU | `corte_a` = hoje; bate com o Painel |
| Diretor: grupo B | sem período | "Visitas · até 18/11", conversão, 1ª visita, aderência e jornada com "até 18/11"; markup e desconto "até hoje" | decisão 48 |
| Saldo, Faturado: soma das UF | R$ 118.254 (bruto) | R$ 112.701 (líquido; devolução R$ 5.552) | D2d |
| Metas, faturamento por UF (projeção) | PA 30.155 · MA 91.651 · AM 51.688 | PA 28.630 · MA 87.015 · AM 49.073 | real da filial da nota (PA 19.589) × 164.717 ÷ 112.701; soma = cartão |
| Pedidos por UF (`por_filial_da_nota`) | notas | AM 23 · PA 19 · MA 16 | pedidos faturados |
| Produtividade (Painel) | sem período | "Conversão · até 19/11", TMA, início, jornada, almoço "até 19/11" | período do Espelho do Farol de Visita |
| TMA | 0,25 h | 0,2647 h (00:15:53) | segundos lidos |

## Lote 2 (não feito agora)
- Peças e Cad. com compra do Metas: hoje "até hoje"; passa a até ontem.
- Corte do Espelho (TMA, jornada, conversão, início, almoço): hoje o Farol de Visita vai até 19/11; o Diretor corta em 18/11 (visitas 990 contra 1.074). Passa a até ontem.
- Itens 5 (conversão 8,2% × 9%) e 6 (DU parcial do dia nas Visitas): sem confirmação.
- Cadastros com compra: RRM mostra AM 1, Metas AM 0 (causa não achada) [SUP].
- **Engenheiro-dados:** `bap_dados.py:1064` chama `mn.acompanhar(...)` sem `hoje=`; usa a data real do PC. Passar o `hoje` do contexto.
- D2b (1 positivado fora da base cadastral): não aparece nesta base (45 = 45) [SUP: a diferença 55/54 é da produção].
