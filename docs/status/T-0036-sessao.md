# T-0036 — relato da sessão de tarefa ao gerente fixo

Sessão de tarefa: https://claude.ai/code/session_01QvB2SU9Wtp5KdywcGtq7PR. O `send_message` para a sessão fixa falhou ("só sessões do mesmo canal"), por isso o relato fica aqui.

## Estado (27/11/2026, Manaus)

| Branch | Head | Estado |
|---|---|---|
| `engenheiro-software/T-0036-desenho` | 9ff7cb8 | main mesclado; o contrato do Analista virou **§10.11** (o §10.9 e o §10.10 do main são da T-0023/T-0025); a matriz inclui os 7 faróis do §10.10; o analista abre no Farol de Saldo (tela-bc3 §14); o grupo do menu se chama "Trade" |
| `gerente-projetos/T-0036-regras` | 84e9aae | **RN-GER-017** (perfis analista e trade) em `docs/produto/03-regras.md`; a RN-GER-014 já era "diretor só Resumo" |
| `modulo-farois/T-0036-correcao-codigo` | 5445a26 | main mesclado sem conflito; compileall verde |
| `modulo-robo/T-0036-pacotes` | — | merge do main em andamento |
| `modulo-web/T-0036-analista` | — | merge do main, BC3/manual e PNGs novos em andamento |
| `testes/T-0036-testes` | 6eb9e71 | espera o robô e a web |

Próximo passo: os testes (valor × regra, com a RN citada) e depois as revisões (revisor-codigo, corretor-redundancias, revisor-ux e design-de-marca).

## Perguntas (padrão adotado entre parênteses; nenhuma bloqueia)

- **P1:** o analista vê os outros faróis? A: sim, como o gerente · B: só os 4 do Analista e o Painel. (A)
- **P2:** como o cliente aparece nos 4 faróis? A: só o código · B: o nome sem CPF/CNPJ, com adendo à ADR 0001. (A)
- **P3:** o analista vê o TOTAL A PAGAR das Campanhas? A: não (RN-GER-015 como está) · B: sim, e o analista entra na RN-GER-015. (A)

## PNGs

Em `web/docs/simulacoes/T-0036/`, na branch da web, quando ela for refeita no BC3.
