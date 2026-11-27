# T-0058 — Simulação: faturado por estado (Pedidos e Saldo) antes × depois

Simulação da regra 10 ("simule = mostrar antes"). Bases congeladas, hoje = 27/11/2026 (Manaus). Tarefa autorizada no recado de 27/11 (item 32).

- **Defeito:** no recorte por estado, o farol só descontava a devolução dos pares (filial, vendedor) que venderam no mês. Isso quebra a RN-GER-002: faturado = VND − DEV, pela data da NF.
- **Depois:** o farol desconta toda a devolução da filial do recorte. O TOTAL não muda.
- **Formato:** os faróis mostram R$ inteiros e o Painel (`por_filial_da_nota`) mostra centavos. Valores em R$. Só UF e totais.

| Mês | UF | pv_pedidos antes | pv_pedidos depois | vc_saldo antes | vc_saldo depois | Painel | depois = Painel |
|---|---|---|---|---|---|---|---|
| AGO/26 | PA | 46.799 | **33.834** | 46.799 | **33.834** | 33.833,74 | sim |
| AGO/26 | MA | 200.106 | 200.106 | 200.106 | 200.106 | 200.105,60 | sim |
| AGO/26 | AM | 38.294 | 38.294 | 38.294 | 38.294 | 38.294,11 | sim |
| AGO/26 | RR | 1.349 | 1.349 | 1.349 | 1.349 | 1.349,00 | sim |
| AGO/26 | soma 4 UFs | 286.548 | 273.583 | 286.548 | 273.583 | 273.582,45 | |
| AGO/26 | TOTAL | 324.767 | 324.767 | 324.767 | 324.767 | 324.766,93 | |
| SET/26 | PA | 54.624 | **48.166** | 54.624 | **48.166** | 48.166,49 | sim |
| SET/26 | MA | 84.885 | 84.885 | 84.885 | 84.885 | 84.884,74 | sim |
| SET/26 | AM | 62.163 | 62.163 | 62.163 | 62.163 | 62.163,45 | sim |
| SET/26 | RR | 12.879 | 12.879 | 12.879 | 12.879 | 12.879,04 | sim |
| SET/26 | soma 4 UFs | 214.551 | 208.093 | 214.551 | 208.093 | 208.093,72 | |
| SET/26 | TOTAL | 237.208 | 237.208 | 237.208 | 237.208 | 237.208,39 | |
| OUT/26 | PA | 36.641 | 36.641 | 36.641 | 36.641 | 36.641,11 | sim |
| OUT/26 | MA | 61.919 | 61.919 | 61.919 | 61.919 | 61.918,64 | sim |
| OUT/26 | AM | 44.842 | 44.842 | 44.842 | 44.842 | 44.842,29 | sim |
| OUT/26 | RR | 0 | 0 | n/d | n/d | 0,00 | sem venda (ver abaixo) |
| OUT/26 | soma 4 UFs | 143.402 | 143.402 | 143.402 | 143.402 | 143.402,04 | |
| OUT/26 | TOTAL | 148.970 | 148.970 | 148.970 | 148.970 | 148.970,04 | |
| NOV/26 | PA | 19.589 | 19.589 | 19.589 | 19.589 | 19.588,66 | sim |
| NOV/26 | MA | 59.536 | 59.536 | 59.536 | 59.536 | 59.536,32 | sim |
| NOV/26 | AM | 33.576 | 33.576 | 33.576 | 33.576 | 33.576,45 | sim |
| NOV/26 | RR | n/d | n/d | n/d | n/d | 0,00 | sem venda (ver abaixo) |
| NOV/26 | soma 4 UFs | 112.701 | 112.701 | 112.701 | 112.701 | 112.701,43 | |
| NOV/26 | TOTAL | 112.701 | 112.701 | 112.701 | 112.701 | 112.701,43 | |

## Leitura
- Só o **PA** muda:
  - AGO/26: −12.965 (2 notas de devolução de vendedor sem venda no mês na filial).
  - SET/26: −6.458.
- MA, AM e RR não mudam. O **TOTAL** não muda em nenhum mês.
- **Depois**, cada estado bate com o Painel (diferença só de arredondamento) e a soma dos estados fecha com o Painel por filial.
- **RR em OUT/26 e NOV/26:** a UF não tem venda no mês, então não existe recorte por UF e o farol mostra n/d ou 0. O Painel mostra 0,00. Não há devolução envolvida, então não é o defeito da T-0058.
- **Fora do escopo:** um estado que só tem devolução no mês, sem nenhuma venda, também não ganha recorte. Se for preciso, vira outra tarefa.
