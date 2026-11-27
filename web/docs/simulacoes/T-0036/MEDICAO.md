# T-0036: medição da §15 (tela-bc3), no BC3 do `main` (T-0033)

Chromium (Playwright), deviceScaleFactor 2. PC = 1366×768; celular = 390×844. Pacote: `analista_fixture.pacote_coerente()`
(dados fictícios, 40 linhas por tabela, números que fecham entre si; a faixa sai das somas das tabelas). Perfil `analista`
nos 4 faróis e no menu; perfil `trade` na página inicial.

| Tela | Largura | Rolagem lateral da página (§15.1) | Rolagem lateral da tabela | A página rola (§15.2) | Altura da faixa | Números na faixa | Altura da barra das abas | Abas à vista | Colunas da grade (§15.4) |
|---|---|---|---|---|---|---|---|---|---|
| saldo (Pedido) | 1366 | 0 | 0 | não | 88 px | 4 | 44 px (1 linha) | 5 | 10 |
| saldo (Pedido) | 390 | 0 | 0 | lista (M3) | 195 px | 4 | 50 px | 3 + Mais | lista |
| markup (Pedido) | 1366 | 0 | 0 | não | 88 px | 6 | 44 px (1 linha) | 12 | 10 |
| markup (Pedido) | 390 | 0 | 0 | lista (M3) | 212 px | 6 | 50 px | 3 + Mais | lista |
| preco (Categoria) | 1366 | 0 | 0 | não | 88 px | 6 | 44 px (1 linha) | 6 | 10 |
| preco (Categoria) | 390 | 0 | 0 | não | 212 px | 6 | 50 px | 3 + Mais | lista |
| divergencias (Divergentes) | 1366 | 0 | 0 | não | 88 px | 6 | 44 px (1 linha) | 4 | 8 |
| divergencias (Divergentes) | 390 | 0 | 0 | lista (M3) | 187 px | 6 | 50 px | 3 + Mais | lista |
| menu do analista (Saldo, Resumo) | 1366 | 0 | — | não | 88 px | 4 | 44 px | 5 | — |
| menu do analista (☰ aberto) | 390 | 0 | — | não | 195 px | 4 | 50 px | 3 + Mais | — |
| início do trade | 1366 | 0 | — | não | 88 px | 0 | — | — | — |
| início do trade | 390 | 0 | — | não | 51 px | 0 | — | — | — |

- A faixa tem 88 px em todas as telas do PC (a mesma altura do `main`, §15.3). O 7º número do Markup e das Divergências fica no Resumo.
- O Markup (12 abas) cabe numa linha a 1366, com a busca em ícone.
- No celular, a página rola só pela lista que abre (M3, §7.4 do contrato e §8).
