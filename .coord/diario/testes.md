# Diário — testes

- 2026-11-20 — montagem do time (pacote do Maestro Sistemas)
- 2026-11-24 — T-0017 — entregas 3 a 5: 16 testes em tests/test_T0017_tres_farois.py (RN-GER-006/007, Visita hoje fora do DU por comportamento) e conferência PC × pacote NOV/26 (31/31 OK) em docs/testes/T-0017.md
- 2026-11-25 — T-0017 — entrega 2: tests/test_T0017_cobranca.py (30 testes, RN-POS-001 a 004) e conferência PC × pacote NOV/2026 sem diferença (539 + 193 linhas, fila 139)
- 2026-11-25 — T-0017 — entregas 3 a 5: +2 testes de Pendências anteriores por estado (PC com o relatório fictício; site sem o cartão no recorte); total BAP igual ao main nas bases (0), soma fecha
- 2026-11-25 — T-0017 — Pendências anteriores: 4 testes de comportamento (rn.entregas + chamar_kpis_de, casos a-d) no lugar do teste que replicava a lógica; 21 testes no arquivo, 238 em tests/, 122 na web
- 2026-11-25 — T-0017 — todas as abas: tests/test_T0017_abas_tres_farois.py (87 casos; RN-GER-011, linhas_padrao × VistaTabela._filtradas, recortes_em_linhas); 83 passam, 4 falham = achados (documento sem máscara no meio; R$ com 8 dígitos sem ponto)
- 2026-11-25 — T-0017 — reteste com modulo-farois 11cef9a e as decisões do gerente: 102 casos ✅; combinado de 4 branches 398 ✅ e 3 ❌ (tres_farois velhos + aviso de aba ausente no robô); web 122 ✅
- 2026-11-25 — T-0017 — rodada do pacote: tests/test_T0017_pacote_tres_farois.py (36; bases congeladas) e o teste de Pedidos reescrito; combinado de 4 branches 427 ✅, 9 ❌ (web recusa o pacote real, kpis_padrao sem detalhe, aba torta sem aviso no Visita), 1 skip; web 212 ✅; valor × regra de 25 cartões
- 2026-11-25 — T-0017 — regras novas (contrato 1b3d902): 7 testes velhos trocados pela regra nova; novos de colunas-fora, avisos, §10.7.3 sem skip, ponta a ponta, total normalizado e sem_documento; combinado 459 ✅ e 1 ❌ (achado 15: estado só com pendência fora do recorte); web 222 ✅; Entregas por UF = PC
- 2026-11-26 — T-0024/T-0026 — #82 com o main (533d650, CI verde); #97 com o main, os 3 testes de escopo pela lista exata (4 + Metas + lote 2), pacote real dos 10 faróis < 80% do teto e corte em 3 passos com o lote 2, valor × regra do lote 2 (2 xfail = recorte por estado da Base e do Planner, recado ao robô pelo gerente); a suíte não grava mais RELATORIOS/painel_diretor_hist.json (conftest); combinado com o robô 55513b7: 523 ✅, 2 xfail; web 310 ✅
