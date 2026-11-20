# ROTA 1710 — Instalação e regras atualizadas do Planner BAP (18/10/2026)

Texto para usar numa sessão com acesso ao computador. Ele descreve o que instalar, como conferir e as regras da rota que valem.

## 0. REGRAS EM VIGOR (atualizado em 03/11/2026 — ordem do mês por prioridade, sexta 12, feriados de NOV, dia foco seg/ter, Fayga e Rodrigo na base seg/ter) — leia isto primeiro

Este quadro manda sobre qualquer outro texto deste documento ou de outro documento do projeto. O teto de 15 por dia e 8 na sexta, que aparece na simulação da manhã de 18/10, **foi cancelado** e não vale.

| Regra | Em vigor |
|---|---|
| **Ordem do mês (03/11, Alexandre)** | "Curva S, A e clientes com limite devem ocupar as primeiras visitas do mês. Depois de ocupados, preencher com curva B, C e etc., sempre seguindo a proximidade por geolocalização e bairros." Grupos: **0 = S, A ou com limite** (aprovado ou disponível > 0); 1 = B; 2 = C; 3 = o resto (D, Z). Cada grupo vai na ordem geográfica, um depois do outro, e os dias são enchidos nessa ordem (`planner_nucleo.grupo_do_mes`, `ordem_por_prioridade`). A regra da cidade base continua: nos 10 primeiros dias úteis só a região da base, e dentro de cada grupo a base vem primeiro. Na semana remontada por lugar, a cidade/região com cliente do grupo 0 vai antes; o que não cabe sai pelo grupo mais baixo (nunca o S/A/limite antes); a vaga do dia também prefere o grupo 0. Vendedor do interior (1 cidade por dia): primeiro as cidades com cliente do grupo 0, depois as outras; a cidade não é partida em duas viagens [SUPOSIÇÃO]. O TOP 30 sem limite segue a curva dele [SUPOSIÇÃO]. A frequência não mudou (S e A semanal; TOP 30 e limite do vendedor da capital, semanal). Vale de **NOV/26** em diante (junto com a roteirização por lugar; Mecânica da rota item 28) |
| **Dia foco (03/11, Alexandre)** | "Segunda foco clientes bateria e terça foco clientes motopeças para os vendedores da capital, Ananindeua e Castanhal." Vale para quem tem a cidade base numa capital, em Ananindeua ou em Castanhal (Thiago, Valmir, Paulo Augusto, Edson, Leandro, Juglaison, Fayga, Rodrigo), de **NOV/26** em diante, **na cidade base** [SUPOSIÇÃO]. **Cliente de bateria** = segmento DISTRIBUIDOR DE BATERIAS ou quem já comprou bateria (aba HIST_DETALHADO da BASE_CLIENTE); depois AUTOPEÇAS, AUTOCENTER e POSTO E TROCA DE ÓLEO [SUPOSIÇÃO]. **Cliente de moto** = segmento MOTOPEÇAS [SUPOSIÇÃO]. O dia é montado antes do resto da semana, no lugar com mais clientes do foco, compacto (até 5 km): cliente do foco (o da semana, depois o da carteira, o menos visitado antes — o cliente de bateria pode voltar toda segunda), depois quem já estava na semana, depois quem pode comprar bateria e ainda não teve visita no mês; sobrando vaga, a carteira perto com o foco antes; faltando, prospecção. Nunca 2x na semana (`planner_nucleo.foco_do_dia`, `nivel_do_foco`, `_montar_dia_foco`; Mecânica da rota item 29) |
| **Fayga e Rodrigo (03/11, Alexandre)** | "A zona da Fayga e Rodrigo: sempre eles estarão nas bases segunda e terça. Interior de quarta em diante." Segunda e terça só a cidade base (Ananindeua, Castanhal); de quarta em diante (inclusive o último sábado) só as outras cidades da carteira, uma por dia: primeiro a que tem mais cliente ainda sem visita no mês que cabe num dia compacto. Para os dois **não vale** a regra dos 10 primeiros dias úteis na base (`BASE_SEG_TER`) |
| **Roteirização por lugar (27/10, Alexandre)** | Geolocalização e proximidade em camadas: **cidade › bairro › rua (endereço) › número**. **Cada cidade é um dia cheio: 1 cidade por dia**, capital ou interior. Região longe dentro da mesma cidade (ilha/distrito, salto de mais de 10 km entre bairros — ex. Mosqueiro em Belém) é dia próprio [SUPOSIÇÃO 10 km]. **Dia compacto (27/10, reclamação da supervisora sobre Marco + Marambaia + Coqueiro + Icoaraci no mesmo dia):** bairro a mais de **5 km** do centro do dia fecha o dia (vai para o dia seguinte), mesmo sem o dia cheio; o mesmo nome de bairro em dois lugares a mais de 5 km vira dois blocos (`rota_lugar.RAIO_DIA_KM`, `_partir_bairro`) [SUPOSIÇÃO 5 km]. Vaga do dia = clientes da carteira da mesma cidade/região **a até 5 km do centro do dia** (`RAIO_VAGA_KM`; menos visitados no mês primeiro, depois o grupo do mês); sem cliente, **prospecção** naquela cidade. Cidade que não coube na semana vai para a semana seguinte. Dia com calendário (Rota por cidade/agenda importada) fica com as cidades do calendário [SUPOSIÇÃO]. **Automático no Planner de NOV/26 em diante** (`planner_nucleo.POR_LUGAR_DESDE`, `rota_lugar.py`; Mecânica da rota item 27). Em outubro só a Fayga e o Edson (28–31/10) foram refeitos assim; a quinta 29/10 do Edson foi corrigida em 27/10 12h (dia compacto) |
| Teto do dia | **12 clientes** |
| Sexta | **12 clientes — dia normal desde NOV/26** (03/11, Alexandre: "mude a sexta para 12 clientes normais"). Até OUT/26 era prospecção, com 6 da carteira |
| Feriados de NOV/26 | **02/11 e 20/11**, sem expediente (03/11, Alexandre: "dia 02 é feriado também e sem expediente") |
| Vendedor do interior, numa cidade do interior | **6 clientes por dia**; no dia da **cidade base, 12**. Desde 21/10 vale no recálculo automático (calendário da Rota por cidade; dia com duas cidades = a 1ª) |
| Último sábado | dia normal de rota, teto 12 |
| 1º sábado | depósito do excedente, sem teto |
| Cidade base | 10 primeiros dias úteis só na cidade base + cidades até 50 km; exceções: agenda importada e, de NOV/26, Fayga e Rodrigo (base seg/ter, interior qua em diante) |
| Visita semanal | TOP 30 (faturamento 6 meses) e clientes com limite, só para o vendedor da capital, a até 50 km da capital |
| Frequência dos demais | pela curva: S e A semanal, B quinzenal, C mensal, Z uma vez se sobrar lugar |
| Mesmo cliente | nunca 2 vezes na semana nem no dia |
| Roraima | com o Thiago, zona "Só no sábado do excedente" |
| Dias que já passaram | **Recálculo normal não reescreve o passado** (21/10): os dias antes de hoje ficam como estavam programados. Só **quando o Alexandre pede para refazer**, o passado vira o **realizado** do vendedor (Espelho da Máxima), completado até a meta do dia (12; sexta 6 até OUT e 12 desde NOV; interior 6 / base 12), desde a admissão |
| Meta de visita do mês | **12 por dia útil** desde a admissão = o **total a visitar** (seg a sex, sem feriado; sexta também 12); vendedor do interior **6**, e **12 no dia da cidade base**. **Meta de visita (RH) = 90%** desse total (26/10, PC Empresa) |
| Cadastro novo como visita | conta como visita, **menos o lote de 16/10/2026** (A1_DTCAD; 112 clientes) em todos os relatórios (parâmetro `datas_cadastro_lote_fora`) |
| Data de admissão | no cadastro (aba 2); a rota e a meta de visita começam nela; mês de casa automático pela admissão de **OUT/26** em diante. Desde 21/10 = 1ª visita na Máxima: Paulo Augusto 07/10, Leandro 13/10, Valmir 14/10, Juglaison 16/10; Fayga e Rodrigo 16/09 |
| Meta de faturamento de OUT/26 | **travada** como estava em 21/10 (decisão do Alexandre): parâmetro `metas_travadas` do Gerador de Meta |
| Equipe (03/11) | **Valmir (000049) saiu: INATIVO no Planner de NOV** (cadeira vaga; zonas AM-SUL e AM-OESTE sem vendedor de verdade até alguém assumir). |
| Equipe (21/10) | **MT encerrado**: saíram o Paulo Ubiratan (000008), o Supervisor MT (vago) e o 000040 ALEXANDRE LOHAN (zonas MT e Amapá sem vendedor → padrão 000000). Roraima continua com o Thiago até a vaga ser preenchida [SUPOSIÇÃO]. **[Achado 03/11]** o 000040 ainda está como VENDEDOR ativo no Planner (copiado para NOV) |
| Medida da rota | **aderência** = programados do Planner no dia que foram visitados (Farol de Visita), não a agenda da Máxima |
| Base de clientes no .json (Protheus/Máxima) | **TODOS ATIVO** (20/10). Quem vê o cliente é o vendedor atrelado (A1_VEND). Sem vendedor (zona/segmento sem vendedor, cadeira vaga ou provisória, inativado na aba Base cliente) = **vendedor padrão 000000 e supervisor padrão 000037** (aba Parâmetros) |
| **Cancelada** | "no mínimo um dia por cidade do interior". Os 12 clientes por cidade do interior são só **indicador** da parcial (CLI. P/ CIDADE), não regra de rota |

**O que está instalado no desktop (DESKTOP-PRUKJF6), 21/10 22h30:**
- Parâmetros do Planner: **12 / 6**, `teto_interior` 6 e `datas_cadastro_lote_fora` ["2026-10-16"].
- Agenda de outubro **refeita em 21/10** (pedido do Alexandre) e gravada como **rota fixa**:
  - 01 a 21/10 = realizado (785 visitas) + completado até a meta do dia (363), desde a admissão;
  - 22 a 31/10 = regra normal com o teto do interior (644 visitas; a carteira das cidades já foi visitada em boa parte);
  - excedente (1.821) no **1º sábado do mês, 03/10** (decisão do Alexandre: não vai para o sábado 24).
- O mês inteiro está em `RELATORIOS\Roteirizacao\ROTA_PROTHEUS_2026-10_AJUSTADA_20261021_2200.json` (vale sobre os envios antigos até 21/10 na aderência) e a base em `BASE_CLIENTES_PROTHEUS_20261021_2200.json` (3.675 clientes, todos ATIVO, 1.076 no padrão). **Importar na Máxima é decisão do Alexandre.**
- PLANNER do mês: `RELATORIOS\Roteirizacao\PLANNER_BAP_2026-10_20261021.xlsx` (é dele que sai a meta).
- Aderência de 01 a 20/10 contra a agenda refeita: **69% (709 de 1.034)**.
- **27/10 (PC Pessoal):** roteirização por lugar instalada (`rota_lugar.py` novo, `planner_nucleo.py`, `email_rota.py` com o último sábado no PDF/e-mail, `smoke_relatorios.py`); semana 28–31/10 da Fayga e do Edson refeita por lugar na rota fixa; `RELATORIOS\Roteirizacao\ROTA_PROTHEUS_VENDEDOR_FAYGA_E_EDSON_A_PARTIR_28-10_20261027.json` (74 visitas, para importar) e `ROTA_PROTHEUS_2026-10_20261027_1050.json` (mês inteiro, aderência). Backup `BACKUP_RELATORIOS\ANTES_ROTA_POR_LUGAR_OUT2026`.
- **27/10 12h (PC Pessoal): dia compacto** (`rota_lugar.py` 8.095, `planner_nucleo.py` 303.383, `smoke_relatorios.py` 201.125); Edson quinta 29/10 sem Marco (Invencível) e Marambaia (Fiel), com Point da Borracharia e Braga Acessórios; coordenada do Car Black (010434-1) corrigida para a Rod. Augusto Montenegro 02, Icoaraci (-1.3286641 / -48.4494167, Google Maps); `ROTA_PROTHEUS_VENDEDOR_EDSON_A_PARTIR_29-10_20261027.json` (28 visitas, para importar) e `ROTA_PROTHEUS_2026-10_20261027_1200.json` (mês inteiro); PDF do Edson trocado em `ROTA_SEMANA_20261026_FAYGA_EDSON`. Backup `BACKUP_RELATORIOS\ANTES_DIA_COMPACTO_OUT2026`.
- **03/11 (desktop, Maestro Sistemas / @bap-tools): ordem do mês por prioridade, sexta 12 e Planner de NOVEMBRO criado.**
  - `planner_nucleo.py` 303.750 → 310.744; `smoke_relatorios.py` 249.464 → 251.048 (check novo "Ordem do mês (NOV)"); `planner_config.json` 678.128 → 71.716 (agora = novembro, o mês vigente); `SISTEMA BAP\PLANNER_MESES\planner_config_2026-11.json` 71.716 (novo: cópia de outubro com mês 2026-11, feriados 02 e 20/11, sexta 12, sem a rota fixa de outubro). O `planner_config_2026-10.json` não foi mexido (outubro continua com a rota fixa e sexta 6).
  - Backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_ORDEM_PRIORIDADE_NOV2026`; novos e backup conferidos byte a byte.
  - Padrão de fábrica `visitas_sexta` 6 → 12.
  - **A rota de novembro ainda não foi calculada:** o Alexandre abre o Planner (Novembro), Recalcular, Exportar.
- **03/11 (desktop, Maestro Sistemas / @bap-tools): dia foco (seg bateria, ter moto) e Fayga/Rodrigo na base seg/ter.**
  - `planner_nucleo.py` 310.744 → 325.637; `smoke_relatorios.py` 251.048 → 252.968 (check "Dia foco (NOV)"); backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_DIA_FOCO_NOV2026`; novos e backup conferidos (md5). Config não mudou (02/11 e 20/11 já estavam como feriado). Cache da base `VERSAO_CACHE` 8 (lê a compra de bateria da aba HIST_DETALHADO).
  - Simulação NOV (BASE de 02–03/11): visitas em dia de rota 1.899 → 1.907; depósito 07/11 2.317 → 2.359; 0 dia com 2 cidades; 0 cliente 2x na semana; maior distância ao centro do dia 9,4 km. Segundas com cliente de bateria / terças com cliente de moto (antes → agora): Thiago 4→46 / 10→48 de 48; Valmir 4→34 / 15→48; Paulo Augusto 4→48 / 12→48; Edson 15→35 / 11→46; Leandro 23→44 / 0 (São Luís sem motopeças); Juglaison 16→32 / 0→4; Fayga 6→8 (+12 que podem comprar) / 6→18; Rodrigo 6→16 / 2→8. Fayga: os 47 de Ananindeua visitados só seg/ter; interior passou a ter Abaetetuba, Santo Antônio do Tauá, Acará e Vigia. Rodrigo: terça em Castanhal só 2–4 (a carteira de lá tem 17 e ninguém repete na semana). Simulação (BASE e COORDENADAS de 02–03/11): 1.899 visitas em dias de rota (antes 1.760), 218 nas sextas (antes 90), depósito 07/11 2.317 (Roraima + excedente), nenhuma visita em 02 e 20/11, 0 dia com 2 cidades, maior distância ao centro do dia 9,9 km. S/A/limite: 1ª visita até o 4º dia útil para Thiago, Paulo Augusto e Fayga (antes até o 9º–13º).
- **03/11 (desktop): equipe e meta de NOVEMBRO.** Valmir (000049) **INATIVO** no Planner de NOV (cadeira vaga: as zonas AM-SUL e AM-OESTE continuam dele, a carteira fica sem vendedor de verdade); Paulo Ubiratan já estava fora desde 21/10. Planner de NOV recalculado (completo, rota fixa de 03/11 em diante) e `RELATORIOS\Roteirizacao\PLANNER_BAP_2026-11_20261103.xlsx` gerado (o de OUT foi para `BKP_RELATORIOS_PLANNER`, como o Planner faz). `meta_config.json`: competência 2026-11 e **desafio comercial de NOV R$ 1.500.000** (`metas_gerais`). Metas pela mecânica aprovada, **não travadas** [SUPOSIÇÃO: travar depois do ok]: desafio Anderson 400,8 mil, Jocimar 163,7, Valmir (cadeira vaga) 131,1, Thiago 124,4, Edson 120, 000040 120, Fayga 100, Rodrigo 100, Paulo Augusto 80, Leandro 80, Juglaison 80; meta RH 120/120/120/120/120/120/100/100/80/80/80; supervisores (desafio/RH) Denylson 724,5/400, Laís 440/440 (inclui o 000040), Francisco 335,5/200 (Valmir fora da meta dele); visita 90% de 12/DU (19 DU; interior 6 e base 12); positivação 25% da base visitada; cadastro 20 por vendedor; categorias peças 40%, bateria 25%, lubrificante 30%, pneu 15%. Resumo em `DOCUMENTOS BAP\CLAUDE OUTPUTS\META_BAP_NOV2026.xlsx`. Backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_EQUIPE_META_NOV2026`.
- Tela "Mecânica da rota" (`planner_nucleo.py`): itens 18 a 29 (29 = dia foco seg/ter e Fayga/Rodrigo na base seg/ter; 28 = ordem do mês e sexta 12; 27 = roteirização por lugar; 23 = interior 6 / base 12; 24 = recalcular não reescreve o passado; 25 = meta de visita 12 por dia útil; 26 = lote de cadastro fora).
- Pastas: tudo o que o Planner exporta fica em `RELATORIOS\Roteirizacao` desde 20/10.

**O que o Planner ainda NÃO faz sozinho (pendente):**
- refazer o passado com o realizado é feito pelo BAP Tools, sob pedido (não tem botão);
- o teto do interior vale só para quem tem calendário (Rota por cidade / agenda importada);
- descontar da frequência as visitas já feitas (no refazer, o BAP Tools desconta).

**Recalcular (só os alterados ou completo):** desde 21/10 os dias antes de hoje **não mudam** (ficam como estavam programados); só de hoje em diante a rota é refeita.

## 1. Contexto

- Programa: **Planner BAP** (Python/Tkinter), dentro do BAP Analista › Roteirização.
- Pasta do BAP (OneDrive, a mesma nas duas máquinas):
  - notebook: `C:\Users\alexandre.guerreiro\OneDrive - PMZ DISTRIBUIDORA SA\1 - PMZ\2025\IM PMZ\Regionais - Leandro`
  - desktop (DESKTOP-PRUKJF6, usuário domon): `C:\Users\domon\OneDrive - PMZ DISTRIBUIDORA SA\1 - PMZ\2025\IM PMZ\Regionais - Leandro`
- Configuração do Planner: `planner_config.json` (raiz) e `PLANNER_MESES\planner_config_AAAA-MM.json` (uma por mês).
- Base de clientes: `RELATORIOS\BASE_CLIENTE.xlsx` + `RELATORIOS\COORDENADAS_CLIENTES.json`. As coordenadas ficam no JSON: 3.361 de 3.658 clientes com ponto, atualizado em 14/10. Ao simular, copie sempre os dois arquivos.

## 2. Regras de trabalho (do Alexandre)

- Responder sempre em português; entregar completo, com as premissas sinalizadas.
- **Sempre fazer backup antes de trocar arquivo** (pasta `BACKUP_RELATORIOS\ANTES_..._OUT2026`).
- Planilhas de acompanhamento: só acrescentar linha, nunca alterar linha gravada.
- "Simule" = simular e mostrar antes; instalar só com aprovação.
- Parâmetros e cadastros são do analista (Leandro). Esta instalação foi pedida pelo Alexandre.
- Não subir o `VERSAO` do `bap_dados.py`.
- O TI não aprova nada: sem Graph e sem registro de aplicativo.
- Nunca guardar ou digitar senha.

## 3. Arquivos do pacote (`ROTA_1710.zip` → pasta `rota_1710`)

| Arquivo | O que faz |
|---|---|
| `novo\planner_nucleo.py` | Regras novas da rota (cidade base, visita semanal, TOP 30 por 6 meses, zona só no sábado do excedente) |
| `novo\bap_planner.py` | Tela: cidade base pela lista de cidades da base de clientes; 4 parâmetros novos; aba Rota por cidade bloqueia outra cidade nos dias da base; caixa "Só no sábado do excedente" na aba Zonas |
| `novo\agenda_cidades.py` | A agenda importada libera as datas dela da regra da cidade base |
| `novo\smoke_relatorios.py` | Teste ajustado |
| `aplicar_patch.py` + `patch_smoke_processos.json` | Coloca os 3 testes novos no `smoke_processos.py` sem trocar o arquivo |
| `ajustar_config.py` | Grava na configuração: cidades base, parâmetros, Roraima, Thiago, São Luís e, opcionalmente, Manaus |
| `INSTALAR_ROTA.bat` | Faz tudo: backup, cópia, configuração, patch do teste |

**Atenção:** o pacote grava 15/8 nos parâmetros. No desktop isso já foi corrigido para 12/6 (e, desde NOV/26, sexta 12). Se o pacote for instalado em outra máquina, voltar os parâmetros para 12/12 logo depois.

## 4. Passo a passo (histórico — já instalado no desktop)

1. Feche o BAP Analista, o Planner e os faróis.
2. Descompacte e ponha a pasta `rota_1710` **dentro** da pasta do BAP.
3. Rode `rota_1710\INSTALAR_ROTA.bat`.
   - Ele faz backup em `BACKUP_RELATORIOS\ANTES_ROTA_BASE_SEMANAL_OUT2026` de: `planner_nucleo.py`, `bap_planner.py`, `agenda_cidades.py`, `smoke_relatorios.py`, `smoke_processos.py`, `planner_config.json` e `PLANNER_MESES\planner_config_2026-10.json` (e meses seguintes, se existirem).
   - Ele pergunta: **"Aplicar também a nova divisão de bairros de Manaus?"**
     - **S**: aplica a divisão sugerida em 18/10 (item 6.6).
     - **N**: Manaus fica como está.
   - O `ajustar_config.py` imprime, arquivo por arquivo, tudo o que mudou. Conferir as linhas que começam com "ATENCAO".
4. Volte os parâmetros para **12 / 6** (item 0; desde NOV/26 a sexta é 12).
5. Rode `RODAR_TESTE_BAP.bat` e confira se `logs\smoke_processos_ultimo.txt` e `logs\smoke_relatorios_ultimo.txt` terminam sem FALHA nova.
6. Confira os números (item 5).
7. Exporte o PLANNER e os JSON (rota e base) só depois de conferir.

**Desfazer:** copiar de volta os arquivos de `BACKUP_RELATORIOS\ANTES_ROTA_BASE_SEMANAL_OUT2026`. Os `PLANNER_MESES_planner_config_*.json` voltam para `PLANNER_MESES\` sem o prefixo.

## 5. Conferência da simulação v6 (OUT/2026, base de 15/10, com a divisão de Manaus) — feita com 15/8, só referência

Os números de visitas abaixo foram simulados com teto 15 e sexta 8 e **não valem mais**. A carteira e os semanais continuam como referência.

| Vendedor | Carteira | Clientes semanais | Visitas em dia útil (15/8) | Clientes visitados em dia útil (15/8) | Só no sábado do excedente (15/8) |
|---|---|---|---|---|---|
| Thiago | 1.011 (Manaus 511 + Roraima 500) | 39 | 295 | 139 | 872 |
| Valmir | 566 | 32 | 295 | 167 | 399 |
| Paulo Augusto | 511 | 43 | 295 | 123 | 388 |
| Edson | 112 | 37 | 250 | 112 | 0 |
| Fayga | 91 | 30 | 214 | 91 | 0 |
| Leandro | 74 | 34 | 247 | 74 | 0 |
| Juglaison | 65 | 43 | 271 | 65 | 0 |
| Anderson | 151 | 0 | 222 | 139 | 12 |
| Paulo Ubiratan | 130 | 0 | 220 | 130 | 0 |
| Jocimar | 60 | 0 | 76 | 60 | 0 |
| Rodrigo | 42 | 0 | 98 | 42 | 0 |

Sem a divisão de Manaus: Valmir 911, Thiago 367 + 500, Paulo Augusto 310.

O que tem de valer depois de qualquer recálculo:
- nenhum cliente de fora da região da base nos 10 primeiros dias úteis;
- nenhum dia acima do teto (**12; sexta 12 desde NOV/26**);
- nenhum cliente duas vezes na mesma semana;
- nenhum cliente de Roraima em dia útil.

Base no Protheus (.json da base de clientes), simulação de 18/10: 2.813 com vendedor e 845 sem vendedor, com o vendedor padrão 000000 (Amapá 414, PA 209, interior do AM 205, outros 17). Desde 20/10 **todos vão ATIVO** (antes os 845 iam INATIVO). Roraima continua com o Thiago.

## 6. O que muda na configuração

1. **Cidade base** (cadastro, aba 2): Fayga **ANANINDEUA**, Rodrigo **CASTANHAL**, Anderson **IMPERATRIZ**, Jocimar **SAO BENTO**. Os outros continuam: Thiago, Valmir e Paulo Augusto em Manaus; Edson em Belém; Leandro e Juglaison em São Luís; Paulo Ubiratan em Cuiabá.
2. **Parâmetros (em vigor):**

   | Parâmetro | Valor |
   |---|---|
   | Visitas por dia | **12** |
   | Visitas na sexta | **12** desde NOV/26 (até OUT/26: 6) |
   | Dias úteis só na cidade base | 10 |
   | Raio da cidade base | 50 km |
   | Top clientes com visita semanal | 30 |
   | Raio da capital para a visita semanal | 50 km |
   | Excedente no sábado | SIM |

3. **Roraima** (zona RR): continua com o Thiago, marcada **"Só no sábado do excedente"**. Os 500 clientes ficam ATIVOS na carteira e na base dele, mas vão todos para o 1º sábado e não ocupam dia de rota.
4. **Thiago 100% Manaus**: o calendário dele na Rota por cidade (Manaus todos os dias) sai, e ele passa para a rota automática como vendedor da capital.
5. **São Luís**: Cidade Operária, Jardim São Cristóvão, Jardim São Cristóvão II, São Cristóvão e Forquilha passam do Leandro (MA-SAOLUIS) para o Juglaison (Z-MA-04). Leandro fica com 74 clientes e Juglaison com 65.
6. **Manaus (aplicada no desktop)**:
   - **Para o Thiago (AM-NORTE):** Flores, Aleixo, Parque 10 (todas as grafias) e Parque das Laranjeiras.
   - **Para o Paulo Augusto (AM-LESTE):** Distrito Industrial (todas as grafias), Raiz, Crespo, Vila Buriti, São Francisco, Betânia, Morro da Liberdade, Colônia Oliveira Machado (grafias), São Lázaro, Santa Luzia e Colônia do Antônio Aleixo.
   - **Com o Valmir:** Zona Oeste, Centro, Cachoeirinha, Praça 14, Educandos, Adrianópolis, Chapada, São Geraldo e N. S. das Graças.
7. **Data de admissão** (cadastro, aba 2; gravada em 18/10): Paulo Ubiratan 01/12/2025; Anderson e Jocimar 01/04/2026; Edson e Thiago 01/07/2026; Fayga e Rodrigo 01/08/2026; Juglaison, Valmir, Paulo Augusto e Leandro 01/10/2026. [SUPOSIÇÃO: dia 01 quando o Alexandre deu só o mês.]

## 7. Regras da rota (como ficam)

1. **Quem entra:** cliente com zona e com vendedor naquela zona e segmento. Cliente inativado à mão na aba Base cliente fica fora. Cliente sem vendedor (e o inativado à mão) vai no .json da base **ATIVO**, com o vendedor padrão 000000 e o supervisor padrão 000037 (20/10): nenhum vendedor da equipe vê. Todo cliente vai ATIVO; quem decide se o vendedor vê é o vendedor atrelado.
2. **Agenda do mês:** dias úteis menos feriados, mais o **último sábado**, que é dia normal de rota com o mesmo teto. O **1º sábado** recebe o excedente, sem teto. Os sábados do meio ficam livres. No mês da **admissão**, a rota do vendedor começa no dia dela.
3. **Teto do dia:** **12 clientes**. **Sexta:** desde NOV/26 é dia normal, **12** (até OUT/26 era prospecção, com 6 da carteira). **Vendedor do interior numa cidade do interior: 6 por dia**, e **12 no dia da cidade base** (no código desde 21/10, pelo calendário da Rota por cidade).
4. **Cidade base:** nos **10 primeiros dias úteis** o vendedor roda só a cidade base do cadastro e as cidades até **50 km** dela (linha reta). O resto da carteira entra a partir do 11º dia útil. **De NOV/26, Fayga e Rodrigo:** segunda e terça na base, quarta em diante no interior, o mês todo (item 0).
   - A regra também vale para o calendário da Rota por cidade: a cidade de fora sai desses dias e a base entra. A aba marca esses dias com "base" e não deixa arrastar outra cidade para eles.
   - **Exceção:** só a **agenda importada** (Importar agenda de cidade), que fica como foi importada.
   - Se faltar cliente na região da base, o dia fica abaixo do teto e o resto é prospecção.
5. **TOP 30:** os 30 clientes do vendedor com **maior faturamento nos últimos 6 meses**, só quem comprou. Empate: o maior limite aprovado. É o mesmo TOP 30 da parcial e dos contatos do celular. Quem tem menos de 30 compradores fica com menos.
6. **Cliente com limite:** limite de crédito aprovado ou disponível maior que zero.
7. **Visita semanal:**
   - **Vendedor da capital** (80% ou mais da carteira a até 50 km da capital da UF dele e não marcado como do interior): o TOP 30 e os clientes com limite que estão a até 50 km da capital são visitados **toda semana**, uma vez por semana, montados antes de todo o resto. O teto vale sempre; na semana curta nem todos cabem.
   - **Quem viaja:** esses clientes não são semanais, só entram primeiro na fila.
   - **Hoje são da capital:** Thiago, Valmir, Paulo Augusto, Edson, Fayga, Leandro e Juglaison. **Viajam:** Anderson, Jocimar, Rodrigo e Paulo Ubiratan.
   - O vendedor da capital com mais de uma zona roda as zonas juntas, o mês inteiro.
8. **Frequência pelos demais:** pela curva. S e A toda semana, B a cada 15 dias, C uma vez no mês, Z uma vez se sobrar lugar.
   - A visita semanal **substitui** a da curva, não soma.
   - Na Máxima vai `periodicidade` 7 para os semanais.
9. **Dia foco (NOV/26):** segunda = clientes de bateria e terça = clientes de motopeças, na cidade base, para quem tem a base numa capital, em Ananindeua ou em Castanhal (item 0).
9b. **Fila para ocupar os dias:** semanais, depois a prioridade de quem viaja (TOP 30 e limite), depois a curva e o faturamento. Quem não cabe vai para o 1º sábado (excedente). **Desde NOV/26 (03/11):** a ordem dos dias segue o grupo do mês — S, A e com limite primeiro, depois B, C e o resto, cada grupo na ordem geográfica (item 0).
10. **Zona "Só no sábado do excedente"** (aba Zonas): os clientes ficam ATIVOS com o vendedor, mas vão todos para o 1º sábado. Não entram no TOP 30 da rota nem na conta de "vendedor da capital". Hoje só Roraima (Thiago) tem essa marcação.
11. **Geografia:**
    - A rota segue o caminho mais curto entre os clientes, pela latitude e longitude. Sem coordenada, usa o endereço vizinho mais próximo, depois o centro do bairro, depois o da cidade.
    - O vendedor fecha uma cidade antes de passar para a próxima, e cidade a mais de 25 km das cidades do dia começa outro dia.
    - **Vendedor do interior:** uma cidade por dia.
    - **De NOV/26 em diante (27/10): roteirização por lugar** — cidade › bairro › rua › número; 1 cidade por dia para todos (capital e interior); região longe dentro da cidade é dia próprio; dia compacto (bairro a mais de 5 km do centro do dia fecha o dia; vaga só até 5 km); a semana de cada vendedor é remontada depois que o Planner escolhe quem entra (desde 03/11: a cidade/região com S/A/limite primeiro, depois a base, as cidades até 50 km e as longes). Ver item 0.
12. **Travas:** o mesmo cliente nunca tem duas visitas na mesma semana nem duas no mesmo dia; o teto vale sempre. Sobrando lugar no dia, repete clientes da cidade do dia (o que teve menos visitas primeiro).
13. **Calendário da Rota por cidade:** manda nos dias em que a cidade foi posta, respeitando a regra da cidade base. Cidade sem dia vai para o dia mais próximo com vaga, até 80 km.
14. **Recalcular:** "só os alterados" mantém a rota de quem não mudou; "completo" refaz todos. Desde 21/10, nos dois, **os dias antes de hoje ficam como estavam** (só de hoje em diante muda; quem já estava programado na semana não volta na mesma semana).
15. **Dias que já passaram, quando o Alexandre pede para refazer:** a agenda vira o realizado do vendedor (Espelho da Máxima), completado até a meta do dia (12; sexta 6 até OUT e 12 desde NOV; interior 6 / base 12) com a regra normal do Planner para aquele dia, desde a admissão. Do dia seguinte em diante, a rota segue as regras, descontando o que já foi visitado. Outubro foi refeito assim em 18/10 e em 21/10 (01 a 21/10).
15b. **Meta de visita (21/10):** 12 por dia útil desde a admissão; interior 6, e 12 no dia da cidade base (a cidade do dia = a da rota guardada; nos dias refeitos, onde ele visitou). Outubro: total 1.932 (Thiago, Edson, Fayga 252; Paulo Augusto, Rodrigo 204; Anderson e Leandro 168; Valmir 156; Jocimar 144; Juglaison 132). Desde 26/10: esse é o total a visitar; a meta de visita (RH) = 90% dele.
16. **Aderência (como a rota é medida):** no Farol de Visita, AGENDADOS = clientes programados no Planner para o vendedor no dia (a rota exportada que valia naquele dia; desde 18/10, o arquivo AJUSTADA até 18/10); VISITADOS = Espelho da Máxima + cadastros novos do dia; % ADERÊNCIA = programados visitados; % FORA DE ROTA = visitas a quem não estava programado; % PED. NA ROTA = pedido do Farol de Pedidos em cliente visitado no dia. A agenda da Máxima não é usada (junta importações antigas).
17. **Cancelada:** a regra de "no mínimo um dia por cidade do interior". A meta de 12 clientes cadastrados por cidade do interior continua só como indicador na parcial (CLI. P/ CIDADE).

## 8. Em aberto (decisões do Alexandre, não instaladas)

- **Importar na Máxima** o `ROTA_PROTHEUS_2026-10_AJUSTADA_20261021_2200.json` (e a `BASE_CLIENTES_PROTHEUS_20261021_2200.json`) e mandar um envio só por semana, antes do domingo.
- **845 clientes sem vendedor** (Amapá, Santarém, Parauapebas, interior do AM, A DEFINIR): desde 20/10 vão ATIVO com o vendedor padrão 000000 / supervisor 000037 (ninguém da equipe vê). Para um vendedor ver, é preciso dar vendedor à zona/segmento (ou "Só no sábado do excedente" com um vendedor).
- ~~Paulo Ubiratan~~: saiu (MT encerrado em 21/10).
- **Anderson:** o dia 22/10 mistura Carolina, Riachão, Pastos Bons e Timon. Ajustar o calendário.
- **Rodrigo, Jocimar e Anderson** ficam abaixo da meta de 19 a 31/10 porque a carteira das cidades da agenda já foi visitada; as vagas que sobram são para cadastro novo, ou rever o calendário deles.
- **Recursos do Planner** (item 0): refazer a partir de uma data, teto 6 automático no interior, descontar o realizado.
- **Melhorias sugeridas:**
  - visita semanal só para quem comprou (o cliente com limite que nunca comprou passaria a quinzenal);
  - encher o dia com quem está no sábado do excedente antes de repetir cliente comum;
  - corrigir os nomes de bairro no Protheus (Distrito Industrial com 9 grafias, Colônia Oliveira Machado com 5, Cachoeirinha, Jorge Texeira, Reden O);
  - campanha de reativação por telefone para a Zona Sul de Manaus (540 clientes sem compra em 6 meses).

## 9. Status da instalação (18/10/2026)

- **ROTA 1710 instalada no desktop (DESKTOP-PRUKJF6) em 18/10**, com a divisão de Manaus (**S**). Backup em `BACKUP_RELATORIOS\ANTES_ROTA_BASE_SEMANAL_OUT2026`, junto com o `LOG_INSTALACAO_ROTA_1710.txt`. Não apareceu nenhuma linha "ATENCAO".
- Mudou: `planner_nucleo.py`, `bap_planner.py`, `agenda_cidades.py`, `smoke_relatorios.py`, `smoke_processos.py` (com o patch), `planner_config.json` e `PLANNER_MESES\planner_config_2026-10.json`. O `VERSAO` do `bap_dados.py` não foi mexido (continua 27).
- **Depois, no mesmo dia (BAP Tools, PC Pessoal):**
  - 12h20 — parâmetros 12/6 e agenda de outubro refeita (realizado + regra), gravada como rota fixa; backup `ANTES_AGENDA_AJUSTADA_OUT2026`.
  - 13h10 — data de admissão no Planner; backup `ANTES_ADMISSAO_OUT2026`.
  - 13h40 — texto das regras do Planner (Mecânica da rota, itens 18 a 21) e padrão do teto = 12; backup `ANTES_REGRAS_PLANNER_OUT2026`.
- Falhas de teste que já existiam (também com os arquivos antigos): `[3] ftPedidos` com 30 diferenças contra o Excel; `smoke_relatorios` para no teste dos contatos porque o `contatos_vcf.py` não existe na pasta.
- Diferença conhecida: 102 clientes de Manaus ficam fora da rota (Distrito Industrial, 72 de INDÚSTRIA e 20 de FROTISTA, quase todos nunca compraram). A zona não tem vendedor para esses segmentos (regra 7.1).
- **Não fazer:** PLANNER COMPLETO (apaga a agenda ajustada de outubro).

## 10. Histórico da decisão de 18/10 (tarde)

- O Alexandre voltou atrás no teto: continuam **12 clientes por dia e 6 na sexta**, porque as metas de visita já foram feitas com esses números. (03/11: a sexta passou a 12 de NOV/26 em diante.)
- **Vendedor do interior:** meta de 6 clientes por dia numa cidade do interior; valem visita da base ou cadastro novo.
- Pediu para refazer a rota de 19 a 31/10 com as regras novas, mantendo a agenda importada do interior e sem repetir quem já foi visitado. A simulação `Claude outputs\SIMULACAO_ROTA_19a31OUT2026_12CLI.xlsx` foi substituída pela agenda ajustada instalada às 12h20 (item 0).
