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
- 2026-11-27 — T-0035 — pacote por farol: 4 combinações robô × web em uvicorn com as bases congeladas ✅ (47 cartões iguais nos dois formatos); herança e selo conforme a ADR §4.4 A; tetos dos anexos robô = web; testes do robô trazidos (o vazio fortalecido) e tests/test_T0035_robo_web.py contra a web real; pico 82 MB no formato 2 contra 94–96 MB no 1; achados: _lote_web sem Manaus (robô, 🟢), pico_mb herda o lançador (web, 🟡)
- 2026-11-27 — T-0035 — reteste dos 2 achados (robô f88a5ed, web 7799904): fuso do lote ✅ (xfail tirado), pico_mb = VmHWM com lançador de 300 MB ✅; tests/ 546 ✅ 5 skip; web 329 ✅
