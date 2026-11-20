# Rotinas do time comercial BAP — decididas em 14/10/2026

Fonte: Alexandre, 14/10/2026 (atualizado com as decisões de 24/10 e 27/10/2026). Dono deste documento: `treinamentos` (quando mudar, avisa o `bap-tools` por recado).

**Onde está aplicado:**

- **Onboardings** (Vendedor, Supervisão, Backoffice, Trade): desde 14/10. A análise de mercado diária entrou em 25/10; os 10 passos de 27/10 e o fechamento em 3 etapas, em 27/10.
- **Farol DDR:** `farol_ddr_config.json`, valendo a partir do Farol de **NOV/2026**. O de outubro não muda. Instalado pelo `bap-tools` no desktop em 18/10.
- **BAP Central:** quadrados Faturamento, CRM e Pós-venda, e Logística de Entrega e Qualidade, cada um com os horários de envio dos faróis. Instalado em 18/10.

Onboardings são institucionais: só cargos, sem nome de colaborador (decidido em 14/10/2026). O VDE interno não aparece em nenhum onboarding nem no Farol DDR. Nos materiais, o nome da empresa é sempre **BAP AUTOPARTS** (regra de 23/10).

## Time de vendas
- **Segunda, 13:00–15:00:** RPS do gerente com os supervisores. Pauta: Resultado D-1; follow-up dos planos de ação dos indicadores; agenda de rota da semana; performance por vendedor, categoria, família e Top 30 clientes.
- **Quarta, 16:00–18:00:** capacitação contínua (supervisores e vendedores). Pedidos do dia transmitidos antes das 16:00.
- **Todo dia: análise de mercado** (Alexandre, 24/10; substitui a pesquisa de mercado de quinta). É o passo 9 dos 10 passos da visita: pesquisa dos itens do Dia Foco do dia, lançada no BAP Ajuda (botão "Pesquisa de mercado", ainda não publicado).
- **Dia Foco em ciclo de 3 semanas** (Alexandre, 24/10; sai o ímpar/par). Semana 1 = 26 a 30/10/2026, semana 2 = 02 a 06/11, semana 3 = 09 a 13/11, e repete. Segunda: baterias e lubrificantes; terça: linha moto (todas as semanas). Semana 1: qua freio, qui direção e transmissão, sex elétrica + linha pesada (kit 2). Semana 2: qua arrefecimento, qui suspensão, sex filtros + linha pesada (kit 1). Semana 3: qua dia do motor, qui dia da rodagem, sex palhetas e acessórios. [SUPOSIÇÃO: distribuição das linhas proposta pelo analista.]

### Os 10 passos da visita (ordem e falas de 27/10/2026, Alexandre; fonte `analista_geradores/passos_v4.py`, lista P4)

| # | Passo | Pergunta-chave | Feito quando |
|---|---|---|---|
| 1 | Check-in | — | check-in a 100 m |
| 2 | Apresentar | "Qual produto ou linha tem mais girado essa semana?" | pergunta do giro feita |
| 3 | Verificar o giro | — | share anotado |
| 4 | Sondar oportunidade | "Em quais produtos ou linhas você tem perdido venda, e por quê?" | perda e motivo |
| 5 | Vende quem oferece | "Como tem sido a procura por esta linha e pela nossa marca BAP em seu estabelecimento?" e "Tenho disponíveis as aplicações dos veículos que mais vendem. Vamos completar seu mix com elas?" | cliente pegou a amostra |
| 6 | Fechamento (sem oferta de expositor) | "Fechamos com esses itens?" e, se não fechar, "O que falta pra fechar hoje?" | pedido ou motivo |
| 7 | Merchandising | — (cartazete, adesivo de visita de rota, status e meta de giro do expositor de quem já tem) | foto do cartazete |
| 8 | Reforço material de apoio | — (tirar dúvidas do catálogo com o time e checar se estão usando) | time usando o catálogo |
| 9 | Análise de mercado | — (itens do Dia Foco, todo dia, no BAP Ajuda) | pesquisa enviada |
| 10 | Indicou, ganhou | "Conhece alguém que trabalha com a linha de produtos que te apresentei e ainda não compra BAP?" | indicação + check-out |

- **Fechamento em 3 etapas:** pedir ("Fechamos com esses itens?"); se não fechar, perguntar o que falta ("O que falta pra fechar hoje?"); se for algo que o vendedor resolve, "Se eu resolver isso, fechamos?" (só em treinamento e matinal, não vai no card). Sem pedido, o vendedor anota o motivo: preço · prazo ou limite · estoque · já tem fornecedor · sem necessidade.
- **Indicou, ganhou:** se o indicado se cadastrar e comprar, quem indicou ganha uma mochila exclusiva BAP. A indicação não conta como prospecção (só conta quando o vendedor vai ao indicado e registra no formulário de prospecção).
- **Acompanhamento do supervisor:** ficha `FICHA_ACOMPANHAMENTO_CAMPO_BAP_8.pdf` (analista, 27/10): nota 3, 2 ou 1 por passo (máximo 30), 12 clientes no dia, feedback a cada 4 clientes e, no passo 6, o motivo de não fechar marcado. O supervisor soma os motivos da semana e leva à RPS de segunda. Não há segunda ficha.
- Falas e "feito quando": matinal `MATINAL_BAP_2026-10-26_11.pptx` (slides 21 e 22) e card `CARD_10_PASSOS_VISITA_BAP_11.png`.

### Calendário da capacitação de quarta (proposta, a confirmar com o Alexandre)
- 28/10: Freio (semana 1) · 04/11: Arrefecimento e suspensão (semana 2) · 11/11: Motor e rodagem (semana 3) · 18/11: Direção, transmissão e elétrica (semana 1). [SUPOSIÇÃO: proposta da matinal de 26/10, seguindo o Dia Foco da semana.]

## Assistentes (substitui a divisão de 03/10)
- **Juliana Almeida — Assistente de Faturamento:** recebe os pedidos, pede coleta nas lojas, dá entrada no estoque FRW, pede QR code, cuida do Farol de Pedidos, pede descontos ao gerente (código de autorização), envia 2ª via de boleto e cuida do SLA de faturamento e da logística de separação e coleta. Pedido cancelado ou devolvido: devolve os produtos ao estoque PMZ.
  - Envia o **Farol de Pedidos às 10h, 14h e 16h e no fechamento**.
  - Farol DDR: 16 atividades / 76 pontos por dia, mais segunda (painel da semana). No BAP Central, o Farol de Estoque FRW também fica no quadrado dela.
- **Mayara Santos — Assistente de CRM e Pós-venda:** tudo do Máxima (força de venda), incluindo colocar os clientes na base do Máxima. Faróis de Visita, Roteirização, Giro e Clientes. Acompanha os indicadores principais e a performance por Top 30, categoria, família e produto. Valida a roteirização. Dá suporte às demais assistentes.
  - Envia o **Farol de Visita às 9h, 11h, 14h e 16h e no fechamento**.
  - Farol DDR: 16 / 72, mais sexta (relatório da semana) e virada do mês (validar a roteirização no Máxima).
- **Estefanie Pacheco — Assistente de Logística de Entrega e Qualidade:** da nota faturada até o cliente. Também cuida de garantias, NCC (notas de compensação de crédito) e devoluções (quando houver).
  - Faz a pesquisa de satisfação em até 72h da entrega: nota de 1 a 10 para o atendimento do vendedor, a entrega e a qualidade do produto, mais sugestões, críticas e elogios.
  - Cuida da inadimplência, com ligações semanais para toda a base de inadimplentes.
  - Apoia o controle do estoque FRW (o que não foi devolvido e está parado) e apoia a Analista de Trade em expositores e orçamentos de trade.
  - Envia o **Farol de Entregas 1x por dia às 10h**, o **Farol de Inadimplência toda segunda às 11h** e o **Farol de Garantias toda terça às 11h**.
  - Farol DDR: 13 / 57, mais segunda 11h, terça 11h e sexta (base de inadimplentes ligada e relatório da semana). Devoluções entram como "Quando houver", sem pontos no dia.
- **Analista Comercial (Leandro):** Farol DDR 14 / 64, mais o último dia útil (fechamento da RV e envio ao RH, que veio da Mayara). Desde 25/10 o "Farol de pesquisa de mercado" do bloco 08:30–09:00 usa a análise diária do time no BAP Ajuda (não mais a pesquisa de quinta).
- **Analista de Trade:** continua no Farol DDR, no grupo Trade Marketing, com a rotina de antes. Não aparece no onboarding de backoffice; tem onboarding próprio.

## Nomes no sistema
- No BAP Central, o botão do farol de devoluções se chama "Farol de Devoluções", e NCC tem botão próprio. No onboarding de backoffice: "Devoluções e NCC".
- Dentro dos relatórios, os menus dos faróis ainda usam os nomes antigos das áreas (Pré-venda e Faturamento, Vendas e CRM, Pós-venda e Logística). Só os quadrados do BAP Central mudaram.

## Suposições a confirmar
- A RV mensal (fechamento e envio ao RH) saiu da lista da Mayara e foi para o Analista Comercial.
- A capacitação de quarta foi aplicada só ao time de vendas, não ao backoffice.
- A pesquisa de satisfação ainda não tem meta.
- Horários de cada atividade nas rotinas das assistentes (fora os envios de farol, que são do Alexandre).
- Devoluções da Estefanie como "Quando houver", sem pontos no dia.
- Analista de Trade mantido no Farol DDR, no grupo Trade Marketing.
- Calendário de temas da capacitação de quarta (proposta acima).
- Texto do bloco 08:30–09:00 do Analista Comercial: "Farol de análise de mercado (preço e concorrência), com a análise diária do time no BAP Ajuda" [SUPOSIÇÃO de 27/10].

## Registro
- 14/10/2026 · rotinas decididas pelo Alexandre e aplicadas nos onboardings.
- 18/10/2026 · `bap-tools` aplicou no Farol DDR (a partir de NOV/26) e no BAP Central (recado `20261018-1359_de-bap-tools_para-treinamentos.md`). Onboarding de backoffice alinhado ao sistema: "Devoluções e NCC" e devoluções "Quando houver" na rotina da Logística e Qualidade.
- 25/10/2026 · `treinamentos` (recados do analista de 23, 24 e 25/10): pesquisa de mercado de quinta virou análise de mercado diária (passo 9); 10 passos da visita versão 4; Dia Foco em 3 semanas; ficha de acompanhamento única (a do analista); calendário de capacitação proposto; nome BAP AUTOPARTS. Onboardings de vendedor e supervisão refeitos com os 10 passos v4 (sem o SPIN antigo); backoffice sem a pesquisa de quinta.
- 27/10/2026 · `treinamentos` (recados do analista `20261027-0915` e `20261027-1042`): 10 passos com a ordem e as falas de 27/10 (4 Sondar, 5 Vende quem oferece, 6 Fechamento sem expositor, 7 Merchandising, 8 Reforço material de apoio), fechamento em 3 etapas com os 5 motivos e ficha versão 8. Aplicado nos 4 onboardings, nos 3 treinamentos e nos 3 materiais de apoio, salvos em `Treinamentos e materiais de trade\`. Aviso ao `bap-tools` (`20261027-1145_de-treinamentos_para-bap-tools.md`).
