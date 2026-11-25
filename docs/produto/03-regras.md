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

## Metas e RV (RN-MET)
- NOV/26: desafio de R$ 1,5 mi.
- Meses de casa: 60/80/100/120 mil, com piso de 120 mil e teto RH de 120 mil.
- Meta de visita = 12 por dia útil (interior 6 / base 12); a meta RH é 90% dela.
- O atingimento da RV é arredondado a 3 casas antes da faixa.

## Pós-venda (RN-POS)
- SLA de entrega em dias corridos; DT. PREVISTA a partir da data do pedido.
- Garantia: DT. FECHAMENTO = solicitação + 15 dias úteis.
- NCC: SLA de 3 dias úteis.
- Frete: o mínimo vale quando o % da nota dá menos.
- RN-POS-001 · Cobrança no WhatsApp (PC e site): a fila é o cliente INADIMPLENTE da aba "Por cliente" com títulos VENCIDOS, ordenada pelo valor em atraso; a mensagem e o número são montados pelo PC (celular: 55 + DDD + 9 dígitos; fixo sai com aviso; número repetido ou ausente fica vazio, com aviso); a pessoa envia pelo link (sem disparo automático).
- RN-POS-002 · Situação da cobrança: ENVIADO HOJE, ENVIADO dd/mm (menos de 7 dias) ou PULADO HOJE, pelo último registro do cliente em qualquer diário.
- RN-POS-003 · Diário da cobrança só acrescenta (dado digitado, regra 7). O registro feito no site volta ao PC nas rodadas de 08h e 14h, num arquivo próprio (COBRANCA_WEB.csv), sem repetir registro (chave `id`); o site avisa "situação do PC até hh:mm". Telefone corrigido no site vale só para aquele envio e fica no diário. O diário do site é apagado 30 dias depois de confirmado pelo robô; o Render guarda os 7 últimos pacotes (R-20261124-192008-alexandre, 3 A, 4 A, 5 A).
- RN-POS-004 · Quem vê no site o Farol de Inadimplência: admin e pós-venda veem Títulos e Por cliente e cobram; gerente vê as tabelas sem telefone e sem o botão; diretor vê só cartões e gráficos. CNPJ não vai ao site (cliente pelo código). Sem exportar tabelas no site nesta entrega (1 A, 2 A, 6 A).
