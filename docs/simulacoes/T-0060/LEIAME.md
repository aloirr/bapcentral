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
| Real (Painel) | R$ 112.701 · R$ 9.131/dia | "Real · até 19/11" R$ 112.701 · R$ 8.669/dia · 13 de 19 DU | decisão 43: hoje é DU passado (112.701 ÷ 13) |
| Projeção (Painel) | R$ 173.494 | R$ 164.717 | 112.701 ÷ 13 × 19 |
| Ating. projetado | 12% | 11% | 164.717 ÷ desafio 1.500.000 |
| Projeção (Metas, faturamento) | R$ 173.494 | R$ 164.717 | igual ao Painel (meta_nucleo `hoje_conta=True`) |
| Projeção da positivação (Metas × Diretor) | Metas 68 · Diretor 68 | **66 nos dois** (45 ÷ 13 × 19 = 65,8) | o Metas subtraía a positivação de hoje (`real_proj = n_pos − hoje`, relatorios_nucleo, cartão Positivação); agora `projecao_ritmo(real, corrido)` é a conta única |
| Projeção (Metas, peças / cad.) | R$ 17.109 / 6 | R$ 16.099 / 6 | sem sufixo: o cartão vai até o dia do cabeçalho; **lote 2: passa a até ontem** |
| Volume (projeção) | 3.848 | 3.649 | grupo A com volume (`VOLUME_COM_HOJE`) |
| Positivados | 45 | 45 | líquido > 0, sem 000040 |
| Pedidos faturados | 58 | 58 | chave filial+pedido, líquido > 0 (RN-GER-014) |
| Ticket por pedido (Painel, aba Itens) | R$ 2.039 (bruto) | R$ 1.943 (líquido) | fórmula: faturamento líquido ÷ pedidos faturados = 112.701 ÷ 58. Não é o ticket do Diretor (÷ positivados) |
| Diretor: faturamento / positivação | R$ 110 mil / 43 · 12 de 19 DU | R$ 113 mil / 45 · 13 de 19 DU | `corte_a` = hoje; bate com o Painel |
| Visitas (Metas) | "Visitas" 1.074 | "Visitas" 1.074 (sem sufixo: soma até 19/11, o dia do cabeçalho) | **lote 2: passa a até ontem** (o Diretor corta em 18/11: 990; a diferença 1.074 × 990 é o corte do Espelho) |
| Ticket do Diretor/RRM | "Ticket médio" | "Ticket por cliente" | fórmula: faturamento líquido ÷ positivados (R$ 113 mil ÷ 45 = R$ 2,5 mil) |
| Diretor: grupo B | sem período | "Visitas · até 18/11", conversão, 1ª visita, aderência e jornada com "até 18/11"; markup e desconto sem rótulo (já vão até o dia do cabeçalho) | decisão 48 |
| Saldo, Faturado: soma das UF | R$ 118.254 (bruto) | R$ 112.701 (líquido; devolução R$ 5.552) | D2d |
| Metas, faturamento por UF (projeção) | PA 30.155 · MA 91.651 · AM 51.688 | PA 28.630 · MA 87.015 · AM 49.073 | real da filial da nota (PA 19.589) × 164.717 ÷ 112.701; soma = cartão |
| Pedidos por UF (`por_filial_da_nota`) | notas | AM 23 · PA 19 · MA 16 | pedidos faturados |
| Produtividade (Painel) | sem período | sem sufixo por cartão: a data aparece uma vez, em "Visitas" e "Aderência ao Planner até 19/11" | período do Espelho do Farol de Visita (o título da aba "Produtividade" é chave da aba e não foi renomeado) |
| TMA | 0,25 h | 0,2647 h (00:15:53) | segundos lidos |

## Lote 2 (não feito agora)
- Peças e Cad. com compra do Metas: hoje "até hoje"; passa a até ontem.
- Corte do Espelho (TMA, jornada, conversão, início, almoço): hoje o Farol de Visita vai até 19/11; o Diretor corta em 18/11 (visitas 990 contra 1.074). Passa a até ontem.
- Itens 5 (conversão 8,2% × 9%) e 6 (DU parcial do dia nas Visitas): sem confirmação.
- Cadastros com compra: RRM mostra AM 1, Metas AM 0 (causa não achada) [SUP].
- **Engenheiro-dados:** `bap_dados.py:1064` chama `mn.acompanhar(...)` sem `hoje=`; usa a data real do PC. Passar o `hoje` do contexto.
- D2b (1 positivado fora da base cadastral): não aparece nesta base (45 = 45) [SUP: a diferença 55/54 é da produção].

- Cad. com compra de RR "—" (Metas): não é só texto; a fonte é a tabela do farol, que não tem linha de RR. Padronizar para 0 muda o dado da barra: lote 2.
- Última linha do Diretor (Jornada sozinha) e os cartões do Metas que não ocupam a largura toda: decisão 50 / regra 12, ficam para a T-0059 parte 2.

- Rodapé das barras: ponto como milhar; nas barras de projeção o rodapé compara com a projeção do cartão (R$ 164.717), não com o real. Isso é só da simulação.
- Código: `PROJECAO_COM_HOJE`, `VOLUME_COM_HOJE`, `base_projecao`, o ramo (a), `esperado_b`, `_hoje_uf` e a tira de `estados_do_cartao` foram apagados; `_hoje_fora_do_du` agora devolve sempre False e os `_de_hoje(...)` viraram no-op (limpeza em outra tarefa).

## Correções do designer, corretor e revisor (mesmo commit)
- Sufixo de período só no que difere do cabeçalho ("dados até 19/11 · 13 de 19 DU"): grupo B do Diretor e da RRM ("até 18/11"), pela constante `GRUPO_B_CARTOES` e `sufixo_periodo` em `relatorios_nucleo`. Markup, desconto, Peças, Cad. e Visitas do Metas: sem sufixo.
- Diretor: `dados_ate`/`ndp` voltaram ao sentido antigo (ontem, grupo B); `dados_ate_a`/`ndp_a` são do grupo A (hoje no DU; o rótulo de data vem da última NF). Peças e cadastros por UF da RRM e do cartão fecham com o cartão (mesmo corte); a projeção de peças não mudou.
- Pedidos e cadastros do cartão do Diretor: `pedidos_faturados_ate` e `clientes_positivados_ate` (líquido > 0, sem 000040).
- Barras de projeção por UF: rodapé compara com a projeção do cartão.
- Real: "Real + pedidos · até dd/mm" quando há pedidos em aberto somados.
- Meta RH e parcial de RV: `_resta_b(ac)` usa `dias_restantes_b` do acompanhamento (modulo-metas); sem o campo, cai em `dias_restantes` [SUP].
- Último DU do mês (`metas_*.png`): com hoje contando e `dias_restantes` = 0, o cartão do Metas diz "último dia: faltam R$ 1.387.299" (Nec./dia), e "mês fechado" só depois do último DU. O `_ultimo_dia(ac)` precisa do campo `dias_restantes_b` do modulo-metas (> 0 no último DU); sem ele o cartão cai em "mês fechado". O texto "mês fechado" do Metas é do `relatorios_nucleo._cartao_indicador` (meu); o do Painel Executivo "Projeção · mês fechado" (linha ~9099) e o da parcial (~11518) seguem iguais.

## Rodada com o meta_nucleo do 7c76164
- Simulação refeita com o `meta_nucleo.py` do 7c76164 (`dias_restantes_b`, visita no grupo B, `hoje_conta`) e os PNGs do Diretor depois da mudança do último DU. Nenhum número da tabela mudou.
- `_ultimo_dia` disparou com o campo real: com hoje = 30/11 (último DU), `dias_restantes` = 0, `dias_restantes_b` = 1 e o cartão diz "último dia: faltam R$ 1.387.299".
- Código morto removido: `_hoje_fora_do_du`, `_du_fechados`, `_de_hoje` e os acumuladores "hoje"/"vol_hoje"/"vhoje" (24 pontos em `relatorios_nucleo.py` e 2 em `visao_executiva.py`).
- Para o engenheiro-dados: o bloco `meta@AAAA-MM` do `bap_dados.carregar` ficou em cache sem `dias_restantes_b` (na simulação o campo só apareceu depois de apagar o `.pkl`). A assinatura do bloco precisa de uma marca nova quando o `meta_nucleo` muda (VERSAO fica 27).

## Mudou depois da aprovação de 380a819
- Markup, média/DU (Diretor): R$ 2,1 mil → R$ 2,0 mil. Volta ao número do main: as duas pontas ficam até ontem, sem misturar margem até hoje com DU até ontem (RN-GER-007).
- Desconto, média/DU (Diretor): R$ 1,8 mil → R$ 1,7 mil. Mesmo motivo (RN-GER-007).
- Visitas, Nec./dia (Metas): 91,0 → 78,0. Visita é do grupo B (RN-GER-007), então o cartão passa a usar os mesmos DU da tabela (`dias_rh`).

Não mudaram: Real 112.701, projeção 164.717, positivação 66, ticket, volume e barras por UF.
Regenerados só `diretor_*` e `metas_*` (meta_nucleo do 7c76164). No caso do último DU, o Metas diz "Falta hoje · R$ 1.387.299" (era "último dia: faltam ...").

## Parcial de RV (grupo B)
Parcial do gerente (BAP inteira), base congelada, hoje = 19/11. Antes = main 7b4f488 (com o meta 7c76164); depois = head. PNGs: `parcial_rv_1366.png` e `parcial_rv_390.png`. Parcial de RV é inteira do grupo B (RN-GER-007): DU e % corrido do B, projeção sobre o real até ontem.

| Número | Antes (main) | Depois | Valor × regra |
|---|---|---|---|
| Projeção da visita (tabela e e-mail) | 1.570 | 1.566 | visitas até ontem ÷ 12 DU fechados × 19: o real de 19/11 (visitas de hoje, do Espelho) sai da projeção; bate com o Diretor (1.568) a 1 visita [SUP: arredondamento do cartão de cadastro] |
| Projeção da visita (cartão) | 1.447 | 1.566 | no main o cartão e a tabela divergiam; agora é uma conta só |
| Projeção do faturamento (tabela) | R$ 164.717 | R$ 173.494 | 109.575 (real até ontem) ÷ 12 × 19 |
| Projeção do faturamento (cartão desafio e meta RH) | R$ 160.148 | R$ 173.494 | idem; cartão = tabela |
| Nec./dia do faturamento | R$ 231.216 | R$ 198.186 | falta R$ 1.387.299 ÷ 7 DU (B: hoje ainda a vencer) |
| Projeção da positivação | 66 (tabela) · 63 (cartão) | 68 | 43 positivados até ontem ÷ 12 × 19 |
| Nec./dia da positivação | 19,7 | 16,9 | 118 ÷ 7 DU |
| Nec./dia da visita | 52,5 | 78,0 | 546 ÷ 7 DU (a meta de visita do "antes" vem de uma árvore sem os .json de runtime: 1.389 contra 1.620; compare só as projeções) |
| Projeção das peças | R$ 15.793 | R$ 16.900 | peças até ontem ÷ 12 × 19 (Peças é B na RN-GER-007; o corte do Metas fica no lote 2) |
| Nec./dia das peças | R$ 98.164 | R$ 84.141 | ÷ 7 DU |
| Cad. com compra: projeção | 6 | 6 | cadastros não separam hoje (SEM_SEPARAR_HOJE); lote 2 |
| Cad. com compra: Nec./dia | 29,3 | 25,1 | ÷ 7 DU |
| Subtítulo | "6 dia(s) útil(eis) até o fim do mês" | "7 dia(s) útil(eis)" | hoje ainda é dia a vencer no B |

## Mudou depois da aprovação (visita única)
- Visitas (Diretor): 990 → 989; projeção 1.568 → 1.566; média/DU 82,5 → 82,4. O Diretor passa a usar a mesma conta do Farol de Visita (`visitas_de_hoje`, cadastro conta como visita, só vendedores ativos): real do Farol até 19/11 = 1.074, menos as 85 visitas de hoje = 989, igual ao Diretor. Projeção = 989 ÷ 12 DU × 19.
- Parcial de RV, gerente: projeção de visita 1.566 (igual ao Diretor), Nec./dia 78,0 (546 ÷ 7 DU do B); projeções de faturamento R$ 173.494, positivação 68 e peças R$ 16.900 como na seção "Parcial de RV (grupo B)".
- Parcial de RV, supervisor (1º supervisor da base): projeção de visita 689 (105%) → 635 (97%). Regra: o filtro de supervisor e vendedor comparava o código Máxima com códigos Protheus e as visitas de hoje davam 0; agora `cod_protheus`, e a projeção parte das visitas até ontem (RN-GER-007).
