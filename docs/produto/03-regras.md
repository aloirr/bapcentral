# 03 — Regras de negócio (RN)

Fonte: as decisões do Alexandre registradas em `docs/legado/` (diário do Maestro Sistemas, seção 3; `processo_bap_out2026.md`; `INSTALACAO_ROTA_1710.md`, item 0). Este documento só **resume e numera**: em caso de dúvida, vale o legado até a RN ser escrita aqui.

## Gerais (RN-GER)
- RN-GER-001 · Desafio comercial em todo lugar (faróis, painéis, Campanhas). A meta RH só aparece no Exportar para o RH, no e-mail e na parcial de RV (29/10).
- RN-GER-002 · Faturado = faturado real: VND − DEV, pela data da NF (22/10).
- RN-GER-003 · Positivação = cliente com líquido > 0 no mês (14/10).
- RN-GER-004 · CNPJs internos (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA) fora do resultado.
- RN-GER-005 · A conta 000040 é de testes: fora de prospecção, indicação, pesquisa e e-mails. **000040 é o código do vendedor de teste.** Existe um cliente real com o código 000040: ele continua no Farol de Inadimplência e no saldo a receber (decisão 7 A do R-20261124-192008-alexandre).
- RN-GER-006 · Estado do faturamento = **filial da nota**: 0101002 AM, 0101004 RR, 0101005 + 0101007 PA, 0101006 MA, 0101003 AP e 0101001 MT (10/11). Clientes (carteira), fretes, Planner e expositores ficam na UF do cliente.
- RN-GER-007 · Dia útil = seg a sex, menos os feriados do Planner do mês. **Hoje fica fora do DU e da projeção** (05/11). Projeção = real ÷ DU fechados × DU do mês.
- RN-GER-008 · Vendedor INATIVO no Planner do mês e sem movimento fica oculto nas tabelas e parciais (06/11). Sem meta e sem RV (03/11).
- RN-GER-009 · Nome nos materiais: "BAP AUTOPARTS".
- RN-GER-010 · O cadastro em lote de 16/10 não conta como visita.
- RN-GER-011 · No site, nome e texto de cliente vão sem CPF/CNPJ (no começo, no meio ou no fim do nome) e o texto livre vai sem telefone, e-mail e documento (trocados por "[removido]"); o código do cliente fica (25/11, T-0017; base: regra 6 e o 2 A do R-20261124-192008-alexandre).
- RN-GER-012 · Edição só no site e só pelo admin, por enquanto. Chega ao PC pelo robô, que grava com a mesma função da tela do PC: o que a tela acrescenta como linha, o robô só acrescenta; o que a tela troca no lugar (DDR, Expositores e arquivo de configuração, RN-GER-016), o robô troca, e antes guarda o valor anterior e uma cópia do arquivo do dia, para dar para desfazer. A tela do PC fica só leitura nessa edição ("A edição agora é só pela BAP Central web."), menos o contato do cliente na garantia (nome e telefone), que continua só no PC, porque o site não mostra nem recebe telefone (regra 6; P2 A, R-20261127-013010-alexandre). O robô oficial é o notebook do Alexandre (25/11; "SO TEM EDIÇÃO NA WEB. NINGUEM MAIS MEXE NO PC. USUARIO QUE MEXE NISSO: ADMIN por enquanto.", R-20261125-104000-alexandre; troca no lugar, 27/11, T-0025 v2).
- RN-GER-013 · Pedido de cliente fora da base de clientes da BAP (o robô grava "NÃO LOCALIZADO NA BASE" no ftPedidos; hoje, os pedidos internos de MT) aparece no Farol de Pedidos como "CLIENTE FORA DA BASE", sem casar o código com zeros (o "6171" não vira o cliente "006171"); no site, a caixa "Ignorar fora da base" vem marcada e tira essas linhas, e os números do farol (calculados no PC) já vêm sem eles ("A", 26/11); não entra na demanda da Solicitação BAP (CD, lojas e FRW). Alexandre, 26/11: "mudar para cliente fora da base e deixar um checkbox no farol de pedidos para ignorar eles, pois são pedidos internos e não pode ir para solicitação de lojas".
- RN-GER-014 · Nos faróis novos do site, o diretor vê só o Resumo (cartões e gráficos); as abas de tabela ficam para admin, gerente e a área do farol (26/11, R-20261126-171559-alexandre; T-0023 v2 e T-0025 v2).
- RN-GER-015 · O TOTAL A PAGAR das Campanhas só aparece para admin, gerente e diretor. O corte é no servidor e vale também para o Excel, o PDF e os cartões (26/11, R-20261126-171559-alexandre; T-0025 v2). Os pontos que o compõem (PTS VÁLIDOS e PTS RELÂMPAGO) continuam visíveis para vendas (P4 A, R-20261127-014248-po, por delegação; o Alexandre pode trocar).
- RN-GER-016 · Um arquivo de configuração só passa a ser editável pelo site com um "autorizo" do Alexandre para aquele arquivo; a edição segue a RN-GER-012 (6 A do R-20261126-180314-alexandre; ADR 0005). O primeiro é o `champions_config.json` (T-0025 v2).
- RN-GER-017 · Perfis "analista" e "trade" no site (3 A do R-20261126-180314-alexandre; T-0036). O analista lê como o gerente: todos os faróis e abas, menos a meta RH (Acomp. RH e Exportar para o RH, RN-GER-001) e a edição (RN-GER-012); na Inadimplência, sem telefone e sem "Cobrar" (RN-POS-004). Os faróis do Analista Comercial (Saldo, Markup, Preço e Divergências) são de admin, gerente e analista; o diretor vê só o Resumo (RN-GER-014); o Excel de correção das Divergências é só do admin. O trade vê só o Trade Marketing (Expositores, com a T-0025 v2); até lá, uma página "ainda não há farol". Matriz em `docs/desenho/T-0036.md` §2 (P1 A, padrão adotado; pode ser trocado sem retrabalho).
- RN-GER-018 · Acesso aos faróis por usuário (27/11, R-20261127-060328-alexandre; P1 B do R-20261127-060912-alexandre; P2, P3 e P4 A do R-20261127-064432-alexandre; T-0050). O perfil dá o padrão: o usuário vê os faróis do perfil. Na tela Usuários, só o admin, usuário a usuário, tira faróis do perfil e libera faróis além dele (e o Painel Executivo), na criação e na edição; a tela mostra separados os do perfil e os liberados. O site guarda só as exceções ao perfil, e farol novo do perfil chega marcado (P3 A). O menu e o servidor seguem a lista: fora dela é 403, inclusive no Excel, no PDF, no CSV e na parcial. Liberar o farol libera a tela; num farol liberado, o usuário vê o Resumo, como o diretor (P4 A). As restrições de dado continuam pelo perfil: as abas de tabela (RN-GER-014), o TOTAL A PAGAR (RN-GER-015), a meta RH (RN-GER-001), a edição só do admin (RN-GER-012), o Cobrar (RN-POS-004), telefone e documento nunca no site (RN-GER-011). Usuários e Trocar senha não entram na lista. Cada mudança fica num registro só de acréscimo (quando, quem mudou, o usuário, o farol e + ou −), sem dado de cliente.
- RN-GER-019 · Dados do cliente no pedido pela loja da filial (27/11, R-20261127-095026-alexandre e R-20261127-095245-alexandre; T-0053). A aba de pedidos traz só o código do cliente, sem a loja, e um código pode ter lojas em estados diferentes. No pedido, nome, UF, cidade, limite e saldo vêm da loja do código cuja UF é a da filial do pedido; código com uma loja só usa essa loja. Sem loja única na UF da filial, o pedido não herda dados de outra loja: a UF é a da filial, sem cidade, limite nem saldo; o nome fica se for igual entre as lojas dessa UF, senão "(loja não identificada)"; o crédito sai "Crédito não apurado" e entra em "Crédito a analisar". Enquanto o saldo por loja não vier do robô, a loja que não é a de maior limite também sai com "Crédito não apurado". Os cartões e o filtro por estado não mudam (contam pela filial do pedido).

## Rota (RN-ROT): item 0 do `docs/legado/INSTALACAO_ROTA_1710.md`
- Teto 12/dia; sexta 12 desde NOV/26.
- Ordem do mês: S, A e com limite primeiro, depois B, C e o resto.
- Dia foco: segunda bateria, terça moto.
- Fayga e Rodrigo: base seg/ter, interior de quarta em diante.
- Roteirização por lugar, com dia compacto de 5 km.
- 1º sábado = depósito do excedente; o recálculo não reescreve o passado.
- RN-ROT-002 · O sábado do excedente (depósito) não repete cliente que já tem visita de segunda a sexta na mesma semana com o mesmo vendedor; a visita repetida sai do sábado, com aviso (R-20261124, T-0016).
- RN-ROT-003 · Nos 10 primeiros dias úteis (`dias_cidade_base`) só a região da base (cidade base + até `raio_base_km`), também na roteirização por lugar; exceções: agenda importada e Fayga/Rodrigo (base seg/ter) (R-20261124, T-0016).
- Cliente INATIVO no Protheus sai da rota.
- RN-ROT-001 · JSON da rota para a Máxima: data final de cada linha = próxima visita + periodicidade − 1 (em vez de 3000-01-01); inativo, CNPJ interno (pelo nome, como o `meta_nucleo`) e conta 000040 fora; o sábado-depósito entra com a mesma data final (20/11; R-20261120-102022, -104729 e -111303-alexandre; T-0010).

## Visitas (RN-VIS)
- RN-VIS-001 · Aderência à rota (Farol de Visita, aba "Aderência dia a dia"): verde a partir de 80%, amarelo de 50% a menos de 80%, vermelho abaixo de 50%. A mesma regra pinta a linha (% acumulada) e cada dia, no PC e no site (regra que já existia na tela do PC, registrada na T-0033; `relatorios_nucleo.tom_aderencia`/`faixa_aderencia`).

## Metas e RV (RN-MET)
- NOV/26: desafio de R$ 1,5 mi.
- Meses de casa: 60/80/100/120 mil, com piso de 120 mil e teto RH de 120 mil.
- Meta de visita = 12 por dia útil (interior 6 / base 12); a meta RH é 90% dela.
- O atingimento da RV é arredondado a 3 casas antes da faixa.

## Pós-venda (RN-POS)
- SLA de entrega em dias corridos; DT. PREVISTA a partir da data do pedido.
- RN-POS-005 · Garantia: DT. FECHAMENTO = solicitação + 15 dias úteis.
- RN-POS-006 · NCC: SLA de 3 dias úteis.
- RN-POS-007 · Nota com frete: nota VND dos últimos 12 meses, pela data da NF, de cliente fora de `CIDADES_SEM_FRETE`; a UF é a do cliente (RN-GER-006) (T-0037).
- RN-POS-008 · VLR FRETE: o FRETE REAL informado na entrega; sem ele, VLR NF × % da transportadora (o % da cidade, se houver), com piso no FRETE MÍNIMO; sem transportadora, o % padrão (T-0037).
- RN-POS-009 · Cartões do Fretes: o "% do faturado" usa o faturado líquido de devolução (RN-GER-002; P3 B, por delegação ao po) e, no recorte por UF, o dos clientes da UF; PC e site mudam juntos (T-0037).
- RN-POS-010 · Edição do Fretes: só no site e só pelo admin (RN-GER-012); edita a mesma linha da aba ENTREGAS do Farol de Entregas (ETAPA, TRANSPORTADORA, DT. PREVISTA, DT. REAL e RESPONSÁVEL; o VLR FRETE (REAL) só no Farol de Entregas, P2 A); o robô grava com `pos_venda.gravar_edicoes`, só acrescentando no diário; o cadastro de transportadoras é só lido (RN-GER-016) (T-0037).
- Frete: o mínimo vale quando o % da nota dá menos.
- RN-POS-001 · Cobrança no WhatsApp (PC e site): a fila é o cliente INADIMPLENTE da aba "Por cliente" com títulos VENCIDOS, ordenada pelo valor em atraso; a mensagem e o número são montados pelo PC (celular: 55 + DDD + 9 dígitos; fixo sai com aviso; número repetido ou ausente fica vazio, com aviso); a pessoa envia pelo link (sem disparo automático).
- RN-POS-002 · Situação da cobrança: ENVIADO HOJE, ENVIADO dd/mm (menos de 7 dias) ou PULADO HOJE, pelo último registro do cliente em qualquer diário.
- RN-POS-003 · Diário da cobrança só acrescenta (dado digitado, regra 7). O registro feito no site volta ao PC nas rodadas de 08h e 14h, num arquivo próprio (COBRANCA_WEB.csv), sem repetir registro (chave `id`); o site avisa "situação do PC até hh:mm". Telefone corrigido no site vale só para aquele envio e fica no diário. O diário do site é apagado 30 dias depois de confirmado pelo robô; o Render guarda os 7 últimos pacotes (R-20261124-192008-alexandre, 3 A, 4 A, 5 A).
- RN-POS-004 · Quem vê no site o Farol de Inadimplência: admin e pós-venda veem Títulos e Por cliente e cobram; gerente vê as tabelas sem telefone e sem o botão; diretor vê só cartões e gráficos. CNPJ não vai ao site (cliente pelo código). Sem exportar tabelas no site nesta entrega (1 A, 2 A, 6 A).
