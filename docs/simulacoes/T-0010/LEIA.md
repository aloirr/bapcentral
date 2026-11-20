# T-0010 - Simulação do JSON da rota da Máxima (antes x depois)
**Entrega ao Alexandre: só `antes_depois.png`** (regra de 20/11, 10:24: simulação = uma imagem). Planilha e este LEIA são anexo técnico para a revisão.
Só simulação: nenhum .py do repositório foi alterado. Carteira 100% fictícia (Cliente NN, Vendedor A/B/T, CNPJ 00.000.000/NNNN-01).

## Regra
- ANTES (código atual): cada visita do mês vira uma linha com `dtfinal` = 3000-01-01.
- DEPOIS: `dtfinal` = `dtproxvisita` + periodicidade - 1 dia (periodicidade 7, 14, 30 ou 45 da curva).
- DEPOIS também não exporta: sábado-depósito (1º sábado), CNPJ interno, conta 000040. Inativo já sai da rota desde 10/11.

## Como foi simulado
- `simular.py` monta 331 clientes (2 vendedores + conta 000040) e roda a `planner_nucleo.gerar_rota` e a `linhas_protheus` reais para nov e dez/2026 (hoje = 20/11, 25/12 feriado).
- DEPOIS = cópia local de `linhas_protheus` no scratchpad, com a regra nova e os filtros.
- Remessa antiga = rota de novembro de 09/11 (sem 2 clientes que entraram depois), dtfinal 3000, ainda ativa.
- Agenda da Máxima de 23/11 a 31/12: cada linha repete a cada `periodicidade` dias de `dtproxvisita` até `dtfinal`.
- `gerar_saida.py` produz a planilha (abas RESUMO, ANTES, ANTES+REMESSA_ANTIGA, DEPOIS, DEPOIS+REMESSA_ANTIGA); `antes_depois.png` é a imagem única da entrega.

## Suposições [SUPOSIÇÃO]
- A Máxima repete a partir de `dtproxvisita` (não de `dtinicio`) e inclui o dia de `dtfinal`.
- A repetição da Máxima ignora feriado e fim de semana; o que cair neles aparece em "dia não útil".
- CNPJ interno é reconhecido pelo nome (cópia de `meta_nucleo.e_cliente_interno`); a rota não tem CNPJ.
- Sábado-depósito = visita no 1º sábado do mês (parâmetro `excedentes_no_sabado` ligado).

## Resultado (compromissos de 23/11 a 31/12)
- ANTES 2795 (753 duplicados) | ANTES + remessa antiga 4393 (2091 duplicados) | DEPOIS 713 (0 duplicados).
- DEPOIS com a remessa antiga ainda ativa: 2311. A correção só funciona se a remessa antiga for desativada na Máxima.
- Com `dtfinal` curto, cada linha gera uma única ocorrência: a periodicidade vira informativa.
