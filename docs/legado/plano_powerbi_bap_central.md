# Plano · BAP Central no Power BI

Criado em 31/10/2026 pelo Maestro Sistemas (pedido do Alexandre: "preciso começar a migrar essa BAP Central para o Power BI; como monto esse passo a passo"). Status: **piloto (passo 4) testado e aprovado em 31/10; tela v2 e robô (4f) prontos em 31/10 ~06h45**: `DOCUMENTOS BAP\POWER BI\BAP_PILOTO.pbip` + CSV em `RELATORIOS\POWERBI\`; pacote em `claude/pacotes/powerbi_piloto/`. O resto do plano continua proposta.

## 1. Princípio

O Python continua sendo o **motor**: robô, Planner, rota, meta, regras de cálculo, edições e e-mails. O Power BI vira a **vitrine**: os faróis de leitura.

- A BAP Central já foi feita assim: cada botão das assistentes abre um relatório **só de leitura** (`bap_relatorios`). Essa é a parte que migra.
- **Regra de ouro:** cada regra de negócio fica num lugar só. As regras complexas (aderência à rota, meta até a data, jornada, SLA, campanhas, positivação) continuam no `relatorios_nucleo.py`. O Python exporta tabelas **já calculadas**, e o Power BI só soma, filtra e desenha. Refazer essas regras em DAX daria dois números diferentes para a mesma pergunta.
- Atenção ao histórico: em 04/10 o **Farol de Pedidos saiu do Power BI e foi para o Python**, porque a autorização é digitada nele. Esse farol só volta ao BI com a edição resolvida (passo 7).

## 2. O que migra e o que fica

| Botão da BAP Central | id | Vai para o Power BI? |
|---|---|---|
| **Faturamento (Juliana)** | | |
| Farol de Pedidos | `pv_pedidos` | Sim, a leitura. A autorização continua no Python. |
| Painel de indicadores | `pv_indicadores` | Sim |
| Farol de Estoque FRW | `pl_frw` | Sim |
| Farol DDR | `farol_pv/vc/pl` | Sim. O cadastro continua no BAP Analista. |
| **CRM e Pós-venda (Mayara)** | | |
| Farol de Metas Equipe | `vc_meta` | Sim |
| Farol Roteirização | `vc_planner` | Sim, a leitura. O Planner continua no Python. |
| Farol de Clientes | `vc_base` | Sim |
| Farol de Visita | `vc_visitas` | Sim, com as tabelas prontas do Python. |
| Campanhas BAP | `vc_champions` | Sim, a leitura. Parâmetros e Exportar campanha continuam no Python. |
| Farol de Giro de Produtos | `pl_giro` | Sim. A curva e a sugestão já existem no modelo PMZ: reaproveitar. |
| **Logística de Entrega e Qualidade (Estefanie)** | | |
| Farol de Entregas | `pl_entregas` | Sim, a leitura. Editar a entrega continua no Python. |
| Farol de Garantias | `pl_garantias` | Sim, a leitura. |
| Farol de Devoluções | `pl_devolucoes` | Sim |
| Farol de Inadimplência | `pl_inadimplencia` | Sim. O "Enviar por e-mail" continua no Python. |
| Farol de NCC | `pl_ncc` | Sim, a leitura. A COMPENSAR e DT. ÚLT. MOV. continuam no Python. |
| **Trade** | | |
| Farol de Expositores | `tm_expositores` | Sim |
| **Analista** | | |
| Painel Executivo e Painel do Diretor | `vc_painel` | Sim (piloto) |
| Farol de Saldo, Markup e Preço | `vc_saldo`, `vc_markup`, `vc_preco` | Sim |
| BAP Analista, BAP Tools, Kits promocionais, Parcial BAP, Atualizar dados | — | **Não.** São ações e cadastros, não relatórios. |

**Observação:** a fase 2 dos faróis (menu de 26 para 18, simulação em 06/11) define a lista final. Migrar só os 18 que ficarem.

## 3. Passo a passo

**Passo 0 · Decisões (Alexandre, antes de começar)**
- Licença: **Pro** (decidido 31/10).
1. Workspace: no tenant da PMZ, ao lado do modelo PMZ que já existe.
2. Licença: Pro para cada pessoa que vê, ou workspace Premium/PPU. [SUPOSIÇÃO] Assistentes e supervisores precisam de Pro, se não houver Premium.
3. Quem vê o quê: as assistentes veem tudo. Supervisor e vendedor só veem os seus (RLS pelo e-mail do Planner)?
4. Gateway: o `ftEstoquePMZ` é DirectQuery e já usa um. [SUPOSIÇÃO] Os arquivos do OneDrive/SharePoint atualizam pelo conector de pasta do SharePoint, sem gateway e sem registro de aplicativo (respeita a regra do TI).

**Passo 1 · Inventário (@bap-tools, 1 a 2 dias)**
- Planilha `MAPA_MIGRACAO_POWERBI.xlsx`, uma linha por aba de cada farol, com:
  - fontes (abas da TABELA_BAP, ESTOQUE_BAP, BASE_CLIENTE, pós-venda, Espelho, Planner, configs);
  - colunas, cartões, filtros e recortes;
  - função de cálculo no `relatorios_nucleo`;
  - o que é editável;
  - horário de envio e quem usa.
- Sai também a lista de **medidas comuns**: faturado real, positivação, desafio comercial, DU, projeção, GAP e % ating. projetado, MoM e M3M.

**Passo 2 · Camada de dados: o Python exporta para o BI (@bap-tools)**
- Módulo novo `exportar_bi.py`, chamado no fim de cada rodada do robô (como o passo 4e) e pelo "Atualizar dados".
- Grava em `RELATORIOS\POWERBI\`, um arquivo por tabela, em CSV UTF-8 com `;` [SUPOSIÇÃO: CSV não exige biblioteca nova na máquina do robô; Parquet seria mais leve].
- **Dimensões:**
  - `dCalendario`: dia útil, feriados, semana, mês e DU do mês;
  - `dVendedor`: Planner (cargo, supervisor, admissão, e-mail, ativo, filial);
  - `dCliente`: BASE_CLIENTE, com segmento, curva, zona, coordenadas e se é interno;
  - `dProduto`: ESTOQUE_BAP, com CATEGORIA, SISTEMA, FAMÍLIA, LINHA e custo da bateria com sucata;
  - `dFilial`.
- **Fatos:**
  - `fVenda`: líquido VND − DEV por NF e item;
  - `fPedidoAberto`;
  - `fMeta`: desafio comercial, com a meta RH em coluna separada;
  - `fVisita`: Espelho + prospecção válida, com o lote de 16/10 fora;
  - `fRota`: programado no Planner por dia;
  - `fEntrega`, `fDevolucao`, `fTitulo`, `fNCC`, `fGarantia`, `fCampanha`, `fDDR`, `fGiro`;
  - `fPainelDiretor`: os 16 cartões já calculados.
- **Regra:** o que o Python já calcula sai calculado (aderência, jornada, almoço, SLA, situação, pontos).
- Teste: o total de cada tabela bate com o farol Python do mesmo dia.

**Passo 3 · Modelo e medidas no Power BI (Alexandre)**
- Modelo estrela ligado ao modelo PMZ, com a mesma `dProduto` e a mesma `dFilial`.
- Aproveitar o que já existe: curva ABC/Z, sugestão de compra e venda diária.
- Medidas-base, uma vez só:
  - `Faturado` (real);
  - `Positivação` (líquido > 0, CNPJs internos fora);
  - `Desafio`, `DU passados` e `DU mês`;
  - `Projeção`, `GAP meta`, `% Ating. projetado`, `MoM` e `M3M`.
- Esse é o **padrão de cartão** que o Alexandre fixou em 30/10.
- Tema BAP com o visual dos faróis: cartões compactos, uma linha de filtros no topo e sem linha inteira vermelha.

**Passo 4 · Piloto: Painel do Diretor + Farol de Inadimplência (1 semana)**
- Por que estes dois:
  - o Painel do Diretor já tem os 16 números calculados (`painel_diretor.calcular`);
  - a Inadimplência é só leitura e de uma fonte só (`ftTitulos`).
- Dá para provar exportação, atualização agendada, visual e permissão sem regra nova.
- Critério para passar: os números batem 100% com o Python por 5 dias úteis seguidos (@revisor-codigo compara).
- **31/10: 1º teste ok** no Power BI Desktop. Os 16 cartões e as 6 medidas da Inadimplência bateram com o Python, e os filtros funcionaram. Falta: instalar o `exportar_bi.py` no robô, trocar o `PastaBI` pelo SharePoint, publicar e contar os 5 dias.
- **31/10 ~06h45:**
  - tela nova v2 (executiva) no `.pbip`;
  - bug do Painel do Diretor no mês sem dado corrigido;
  - passo 4f do robô pronto em `claude/pacotes/powerbi_robo/`, aguardando o ok para instalar.

**Passo 5 · Atualização**
- O robô roda na DT-AMADMBAP-03. A atualização agendada do dataset fica uns 30 min depois de cada rodada [SUPOSIÇÃO: o Pro permite 8 por dia].
- Mostrar no relatório "Dados de dd/mm hh:mm", lido do `ultimo_resumo.json`.

**Passo 6 · Ondas (cada onda roda em paralelo com o Python por 2 semanas)**
1. **Executivo:** Painel Executivo, Metas, Saldo, Markup e Preço.
2. **Faturamento:** Pedidos (leitura), Painel de indicadores e Estoque FRW.
3. **Logística:** Entregas, Garantias, Devoluções, Inadimplência e NCC (leitura).
4. **CRM e Trade:** Visita, Roteirização, Clientes, Giro, Campanhas, Expositores e DDR.

**Passo 7 · Edição e envios (o que o BI não faz)**
- **Edições** (autorização, entrega, previsão, frete real, NCC, garantia) continuam num **BAP Central enxuto**, só com Editar, Planner, Meta, Enviar por e-mail, Parcial e Atualizar.
- Alternativa futura: Power Apps dentro do BI. [SUPOSIÇÃO] Depende de licença e do TI; testar antes de prometer.
- **Parciais e e-mails** (PDF para WhatsApp, RH, inadimplência) continuam no Python. A assinatura de e-mail do Power BI serve para o Diretor e para os gestores.

**Passo 8 · Central no Power BI**
- App do workspace com uma seção por quadrado (Faturamento, CRM e Pós-venda, Logística, Trade, Analista).
- Página inicial com os botões, como a BAP Central.

**Passo 9 · Desligar**
- Cada farol só sai do Python depois de 2 semanas igual ao BI e do ok do Alexandre.
- O código fica: só sai o botão da BAP Central.

## 4. Calendário sugerido [SUPOSIÇÃO]

| Quando | O quê |
|---|---|
| Até 07/11 | Passo 0 e inventário |
| 06/11 | Lista final dos 18 faróis (fase 2) |
| 10 a 21/11 | Exportação, modelo e piloto (alinhado com a fase 3 dos faróis, padrão único até 27/11) |
| Dezembro | Ondas 1 e 2 |
| Janeiro | Ondas 3 e 4, app e BAP Central enxuto |

## 5. Riscos

- **Dois números para a mesma coisa:** evitado pela regra de ouro, com teste de bate-número a cada onda.
- **Mudança de regra no meio** (frequente): mudou no Python, a tabela exportada muda junto, sem retrabalho no BI.
- **Licença e permissão:** quem não tem Pro não vê.
- **OneDrive atrasado** entre máquinas: o BI lê o arquivo da nuvem, então vale o do robô.
- **Desempenho:** o `Vol_BAP_Alocacao_Total` já é lento no modelo PMZ. As tabelas novas são importadas, não DirectQuery.
