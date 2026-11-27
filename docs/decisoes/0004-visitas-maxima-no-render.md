# ADR 0004 — "Atualizar visitas" da Máxima no Render: o navegador roda num cron job à parte, e a senha fica só nele

- **Status:** **aceita** em 27/11/2026 (decisões D1 a D5, §0). O código ainda não existe. O `render.yaml` muda num PR de governança à parte (§9). **Adendo 1** (27/11): a D4 foi revista (o mesmo login do notebook) e a governança 2 vem antes do código.
- **Data:** 2026-11-27 (proposta, versão final e revisão do PR #137)
- **Tarefa:** T-0045 · **Autor:** engenheiro-software
- **Contrato:** `.coord/contratos/visitas-nuvem.md` **v1**. Esta ADR diz **o porquê e as decisões**; o contrato diz **o como** (rotas, corpos, constantes, códigos e textos). Quando os dois parecerem dizer a mesma coisa, vale o contrato.
- **Depende de:**
  - ADR 0001: web no Render, modelo M2, perfis (§4.5), adendos 2, 4 e 5;
  - ADR 0002: rotina diária (regra 11) e o limite 3 (`/saude`);
  - ADR 0003 e o contrato do relatório §10.8: o pacote por farol. Ele continua sendo o único caminho do `vc_visitas` até a tela (§5.3).
- **Consumidores:**
  - modulo-robo: `visitas_maxima.py` (o `Robo`), `bap_automation.py` (a importação na volta de 30 min), `atualizar_visitas.bat` (sem mudança) e a pasta nova `nuvem/visitas/`;
  - modulo-rota: `visitas_nucleo.py` (funções puras: `dias_a_baixar`, `juntar_baixado`, `filtrar_espelho`, `achar_dado_pessoal`);
  - modulo-web: `web/app/` (API, tela "Atualizar visitas", `/saude`);
  - testes; designer-ux (simulação da tela, regra 10).
- **Recados:**
  - R-20261126-182728-alexandre: a opção C, contra a recomendação do po (texto literal no recado);
  - R-20261126-224331-gerente-projetos: o desenho e as 5 decisões levadas ao Alexandre;
  - R-20261127-005437-alexandre: as decisões;
  - R-20261126-175814-gerente-projetos: o plano da migração (T-0043 "Pedir rodada", a volta de 30 min);
  - `recados/anexos/T-0033/inventario-pc-site.md`, item 24 e §2.3;
  - pareceres do PR #137: `recados/anexos/T-0045/revisao-codigo-pr137.md` e `redundancias-pr137.md` (RD-0072 a RD-0081).

## 0. O que ficou decidido

Numeração única desta ADR, do contrato e do desenho: **D1 a D5**.

| # | Pergunta | O que vale | Recomendação do time |
|---|---|---|---|
| D1 | onde o navegador roda no Render | um **cron job à parte**, `bap-visitas-maxima`, Docker, plano de 2 GB pago pelo tempo rodado (custo no §4). O site `bap-central` continua no Starter | A |
| D2 | quando roda sozinho | às **06h00 de Manaus**, todo dia, baixando **ontem**, mais o botão | A |
| D3 | quem aperta "Atualizar visitas" no site | **admin e gerente** | A |
| D4 | que login da Máxima o site usa | um **usuário próprio do robô**, criado pelo Alexandre na Máxima, com o mínimo de leitura do Painel Auditoria. Usuário e senha só como variáveis secretas do cron, criadas por ele no painel do Render | A |
| D5 | print da tela quando dá erro na nuvem | **sem print**: só o código do erro e a fase | B |

Texto literal (R-20261127-005437-alexandre, com a numeração do po, 2 a 6 = D1 a D5): "2 A / 3 A / 4 A / 5 A / 6 B".

**Escolhas técnicas desta ADR** (do time, não do Alexandre; explicadas abaixo):
- **antes de ligar:** um **diagnóstico real no Render** (confirmação, captcha, bloqueio, dado pessoal, memória e tempo). A agenda nasce desligada e só o admin a liga, depois do "ok" do Alexandre (§3.1);
- **"Baixar de novo", "Retomar", "Rodar diagnóstico" e "Ligar a agenda" só para o admin.** A D3 fala só do "Atualizar visitas"; esta divisão vai explícita na simulação do designer-ux (§9, item 4), para o Alexandre ver;
- **entrega ao site:** rotas próprias com token próprio (`BAP_VISITAS_TOKEN`) e um **lote por dia**, não o pacote por farol do §10.8 (§5.3);
- **o lote leva só as colunas permitidas do Espelho**, limpas e com varredura de dado pessoal (§7, RN-VIS-007);
- **teto diário de logins na Máxima** (§3.1, RN-VIS-008);
- **um índice só de "dia baixado"**, que o PC e a nuvem alimentam (§5.1);
- **botão fora de hora:** uma **fila no disco do site**, que o cron lê a cada 10 min, não a API do Render (§3.3);
- **o token do cron** é sorteado pelo Render (`generateValue`) e copiado para o cron pelo Blueprint: o Alexandre só cria os 2 segredos da Máxima (§2.4).

## 1. Contexto

**Hoje, no PC** (`visitas_maxima.py`, chamado pelo `atualizar_visitas.bat` ou pelo botão do Farol de Visita):
1. pede usuário e senha da Máxima na hora (a senha nunca é gravada) e abre o Edge/Chrome pelo Playwright;
2. entra no maxGestão > Painel Auditoria e marca todas as filiais, supervisores e representantes;
3. **baixa**, dia a dia e vendedor a vendedor, o Espelho de Rotas em Excel: `RELATORIOS/Visitas/ANALITICO/<VENDEDOR>/VISITA-<VENDEDOR>-DD-MM-AAAA-HH-MM.xlsx`;
4. **monta**, com esses Excel, `diario/AAAAMMDD.csv` (`visitas_nucleo.montar_dia`), `AAAAMM.csv` (`montar_mes`), `ACOMPANHAMENTO_VISITAS_BAP.xlsx` (`atualizar_acompanhamento`, só acrescenta linha) e `VISITAS_POR_CLIENTE.xlsx` (`atualizar_por_cliente`, retrato refeito);
5. junta a Prospecção do Forms (`prospeccao_forms.atualizar`), que lê o Excel de respostas **sincronizado pelo OneDrive no PC**.

**No site,** o Farol de Visita (`vc_visitas`) mostra o que o robô mandou no pacote, montado no PC a partir desses arquivos (`bap_automation._FONTE_BAIXADO_WEB`). Hoje o PC **não** baixa visitas sozinho: o "Atualizar visitas" é manual. A agenda das 06h00 não repete uma tarefa agendada que já existe.

**O que muda com a opção C:** só o passo 3 (o navegador e a senha) vai para o Render. Os passos 4 e 5 **continuam no PC**, com o mesmo código, por três motivos:
- a Prospecção depende do OneDrive do PC; lê-la do Render exigiria o Graph (regra 9);
- a aderência ao Planner lê as rotas exportadas que estão no PC (`visitas_nucleo._RX_ROTA_PLANNER`);
- o `ACOMPANHAMENTO_VISITAS_BAP.xlsx` é a planilha de acompanhamento da regra 7 (só acrescentar). Ela fica com um dono só, o PC.

**Números de hoje** (da pasta `RELATORIOS/Visitas`, sem nome):
- 15 representantes por dia (17 pastas no ANALITICO);
- 1.622 Excel em 111 dias, com 22 a 51 KB cada (mediana de 26 KB): cerca de 0,4 MB por dia;
- tempo por dia no PC, pelo `_baixados.json` (out–nov/2026): de 77 a 310 s, em geral de 107 a 152 s;
- o robô do PC roda na volta de 30 min, das 07h às 21h (ATIVAR_ROBO_30MIN), e o web do Render é o Starter de 512 MB (`render.yaml`).

## 2. Onde roda o Playwright no Render (D1)

### 2.1 Memória e CPU estimadas

Tudo [SUPOSIÇÃO]: não há Playwright neste ambiente e não se mede sem a Máxima. A conta vem do Chromium sem tela com uma SPA pesada (o maxGestão é React com MUI DataGrid, e o visualizador do Espelho é um gerador de relatório em JavaScript). A medida real sai do diagnóstico.

| Parte | Memória (pico) |
|---|---|
| Python e o `Robo` | 40–60 MB |
| Driver do Playwright (Node) | 50–80 MB |
| Chromium: processo principal, GPU e utilitários | 100–150 MB |
| Aba do maxGestão (grade com 15 linhas) | 150–250 MB |
| Visualizador do Espelho (aba ou iframe) e o download | 80–200 MB |
| **Total do navegador** | **cerca de 420 a 740 MB** |
| O site de hoje (`uvicorn`, 1 processo, com o pacote; ADR 0003, §1) | 70–140 MB, com pico perto de 512 MB no recebimento |

- **Não cabe no Starter de 512 MB junto com o site:** quando falta memória, o Render derruba o processo inteiro, e o site cairia junto com a rodada.
- **CPU:** o navegador passa quase todo o tempo esperando a Máxima. Com 1 CPU (Standard), o tempo fica perto do PC [SUPOSIÇÃO].

### 2.2 As opções que foram ao Alexandre

| | Opção | Custo/mês a mais | Por que não (ou por que sim) |
|---|---|---|---|
| W1 | no próprio serviço web (`bap-central`) | +US$ 18 (Starter → Standard) | o navegador disputa memória com o site, a senha fica no serviço que atende a internet, o site troca de runtime para Docker e todo deploy mata a rodada |
| W2 | worker sempre ligado | +US$ 7 a 25 | paga 24 h para usar cerca de 15 min por dia e, sem o disco do site, precisa da mesma API da W3 |
| **W3** | **cron job à parte** (`type: cron`, Docker) | **§4** | **escolhida (D1):** isolado do site, paga só o tempo rodado, a senha fica só nele, o Render roda uma execução por vez e o deploy do site não interrompe a rodada |

As características do Render que a W3 usa, todas [SUPOSIÇÃO] e conferidas no diagnóstico e no painel, estão no `docs/desenho/T-0045-render-yaml.md`, §2.1.

### 2.3 Plano do cron: Standard, e o diagnóstico decide se muda

- **Standard (2 GB, 1 CPU).** Pago pelo tempo rodado, a diferença para o Starter é de centavos no mês, e o Standard tira o risco de faltar memória.
- Com **pico abaixo de 350 MB** no diagnóstico, ele desce para o Starter; acima de 1.600 MB, sobe para o Pro (os dois por PR de governança).

### 2.4 O `render.yaml` e a imagem (proposta de governança)

O texto exato está em `docs/desenho/T-0045-governanca.diff` (adendo 1; substituiu o `T-0045-render-yaml.diff` do PR #137), explicado no `docs/desenho/T-0045-render-yaml.md`. As decisões por trás:
- **um serviço novo só para o navegador**, e **os 2 segredos da Máxima só nele** (`sync: false`): o `bap-central`, que atende a internet, nunca os recebe;
- **o token do cron sorteado pelo Render** no site e copiado pelo Blueprint: ninguém do time vê o valor, e o Alexandre não tem um terceiro segredo para criar;
- **imagem com lista fechada de arquivos** (proibido `COPY . .`): as bases (`RELATORIOS/`, com dado de cliente) nunca entram na imagem;
- **usuário sem privilégio** dentro do contêiner.

**Donos:** o `Dockerfile` e o `nuvem/**` hoje são "sem-dono"; as linhas do `.coord/donos.json` estão no desenho, §3 (governança 1, §9). Até elas entrarem, o `Dockerfile` fica como texto.

**Sem dependência nova no PC:** o robô DT-AMADMBAP-03 importa com `requests` e a biblioteca padrão. O Playwright e o `openpyxl` já estão no `requirements.txt` do PC. Nada de pyarrow nem de Git. Na imagem, o `requirements-visitas.txt` leva o Playwright e o `openpyxl`, e o `COPY` leva o `relatorios_nucleo.py` e o `bap_dados.py` (a limpeza do §7; desenho, §3).

## 3. Quando roda e quem aperta (D2, D3)

### 3.1 Agenda e teto do dia

- **Um cron só,** de 10 em 10 min das 06h00 às 21h50 de Manaus. A cada volta, ele pergunta ao site se há trabalho e decide com uma função pura (contrato, §3.1). A volta sem trabalho sai em segundos.
- **Às 06h00, todo dia** (sábado e domingo também, como o PC), baixa **ontem**, que fecha o dia. Falha que permite nova tentativa tenta de novo às 06h30, 07h00 e 07h30.
- **A agenda nasce desligada.** O primeiro trabalho do cron, com as variáveis presentes, é o diagnóstico. Só o admin liga a agenda, com diagnóstico `ok` e o robô do PC novo no ar (é ele que conta ao site os dias que o PC já fechou, §5.1).
- **Teto diário de logins (RN-VIS-008): 8 por dia, somando todos os motivos,** e um teto por motivo (agenda 4 = 1 + 3 retentativas; pedido 3; retentativa 1; diagnóstico 2). O site conta **na concessão**, porque cada concessão é um login, mesmo que a rodada caia depois. Por que 8:
  - **risco de bloqueio:** sem teto, uma falha que deixa tentar de novo dispararia a cada 10 min até 21h50, cerca de 96 logins por dia. 8 é cerca de 3 vezes o uso normal (1 agenda e 1 ou 2 botões), em horários espaçados, e a senha recusada nunca tenta de novo (RN-VIS-005);
  - **custo:** o teto põe um limite em dinheiro no pior mês, e sem ele a conta passaria do dobro (§4);
  - **o dia normal não chega perto:** 1 agenda e 1 botão são 2 logins.
- **Retentativa (RN-VIS-006):** marcada como feita já na concessão, para ficar uma só mesmo que falhe.

### 3.2 Botão "Atualizar visitas" no site

- Fica no Farol de Visita. Pede um período, com padrão "dias ainda abertos até hoje" e **no máximo 7 dias**; período maior continua no PC (até 93 dias).
- **Quem aperta:** `admin` e `gerente` (D3). Os outros perfis veem o estado e não veem o botão. O corte é feito no servidor, com teste de 403 por perfil (ADR 0001, §4.5).
- **O botão do PC continua** (decisão do R-20261126-182728 até a entrega, e depois como reserva). O desligamento dele segue a T-0044: 2 semanas iguais e o "ok" do Alexandre.

### 3.3 Como o botão dispara uma rodada fora de hora: fila no site (escolhida) × API do Render

| | Como | Tempo até começar | Por que |
|---|---|---|---|
| **Fila (escolhida)** | o botão grava o pedido no disco do site; o cron, que acorda de 10 em 10 min, lê na pergunta de trabalho | até 10 min | nenhum segredo novo no site; o site só guarda o pedido; o mesmo caminho serve à agenda, à retentativa e ao diagnóstico |
| API do Render | o site chama `POST /v1/cron-jobs/<id>/runs` com uma chave da API do Render | cerca de 1 min | **recusada:** a chave da API do Render é da conta inteira [SUPOSIÇÃO: o Render não tem chave restrita a um serviço]. Com ela, quem invadir o site lê as variáveis de todos os serviços, **inclusive a senha da Máxima**, e pode apagar serviços. Isso desfaz o "senha só no cron" da D1 |

- **Custo da fila:** 96 voltas por dia sem trabalho, de cerca de 30 s cada (a partida do contêiner [SUPOSIÇÃO: cobrada]), são cerca de 1.440 min por mês, ou cerca de US$ 0,85 no Standard. É o maior item da conta: a duração real é conferida no painel antes do "ok" do diagnóstico (contrato, §6).
- O "Trigger Run" do painel do Render continua servindo ao Alexandre para não esperar os 10 min no diagnóstico [SUPOSIÇÃO: nome do botão no painel].

### 3.4 Duas rodadas que se cruzam

O site guarda uma **concessão** (lease): só uma rodada ativa por vez, gravada em disco para sobreviver ao deploy, renovada a cada vendedor (RN-VIS-004).

| Caso | O que acontece |
|---|---|
| Botão apertado durante uma rodada | o pedido entra na fila (no máximo 1 pendente). Apertar de novo mostra "Já pedido às HHhMM". Ele é atendido na volta seguinte ao fim da rodada |
| Agenda das 06h00 e um pedido juntos | uma rodada só, com os dias dos dois |
| Duas execuções do cron ao mesmo tempo (atraso do Render) | a segunda recebe 409 ao pedir a concessão e sai |
| Rodada morta (memória, tempo) | a concessão vence, e o site grava `RODADA_INTERROMPIDA`. Os dias já enviados ficam, e a nova tentativa baixa só o que falta |
| Pedido maior que uma rodada (45 min, §4) | a rodada para no fim de um dia, e o pedido continua na volta seguinte, até 3 rodadas |
| "Atualizar visitas" do PC durante a rodada do site | o PC consulta o estado do site e pede confirmação (texto no contrato, §4.5). Se a pessoa seguir, os dois gravam com nomes diferentes, e vale o Excel mais novo por vendedor e dia (`espelhos_do_periodo`, regra de hoje). [SUPOSIÇÃO: a Máxima pode aceitar uma sessão só por usuário; com o usuário próprio do robô (D4), o PC usa outro login e o risco cai] |

## 4. Tempo de cada rodada, limites e custo

| Etapa | No PC (medido) | No Standard [SUPOSIÇÃO] |
|---|---|---|
| Login, maxGestão, Painel Auditoria e filtros | cerca de 1 a 2 min | 1,5 a 3 min |
| Um dia (15 vendedores) | 77 a 310 s, em geral de 107 a 152 s | 2,5 a 5 min |
| **Agenda (1 dia)** | — | **cerca de 5 a 8 min** |
| **Botão com 7 dias** | — | **cerca de 20 a 40 min** |
| **Diagnóstico (1 dia, 2 vendedores)** | — | **cerca de 3 a 5 min** (teto de 15) |

- **Tempo-limite da rodada:** 45 min, conferido no fim de cada dia; o que faltar continua na volta seguinte. Um vigia liga o `parar` do `Robo` e, se ele não parar, encerra o processo com saída de erro. O teto do Render (12 h) nunca é o freio. Os valores estão no contrato, §2.
- **Do fim da rodada até a tela:** até 30 min para o robô do PC importar (§5.1), mais a rodada do robô (cerca de 9 min): **até cerca de 40 min**. Na tela, o "baixado em" do farol muda nessa volta.
- **Conta do custo (Standard):** a agenda dá 30 × 8 min; 10 botões de 25 min por mês; e as voltas sem trabalho do §3.3. São cerca de 1.900 min por mês, **cerca de US$ 1 a 3 por mês** [SUPOSIÇÃO: preço a conferir no painel].
- **Pior mês com o teto do §3.1:** 8 logins por dia × até 45 min = 360 min por dia; × 30 dias = 10.800 min × ~US$ 0,00058 = cerca de US$ 6,30, mais cerca de US$ 0,85 das voltas sem trabalho (§3.3): **cerca de US$ 7 por mês**. Sem teto, 96 logins × 8 min por dia dariam cerca de 23.000 min, ou cerca de US$ 13 por mês.

## 5. Como as visitas chegam ao site e voltam ao PC sem perder dado

### 5.1 O caminho

```
cron (Render) --POST lote do dia--> site (disco) <--GET na volta de 30 min-- robô do PC
                                                 --grava ANALITICO, monta, confirma + fechados_pc-->
robô do PC --pacote por farol (§10.8, com o vc_visitas novo)--> site --> Farol de Visita
```

1. **Na nuvem,** a cada dia completo, o cron filtra os Excel (§7) e manda ao site um **lote do dia** (cerca de 0,5 MB). Formato e respostas: contrato, §3.4 e §3.6.
2. **No site,** o lote fica em disco com o mesmo armazém de `epoca` e `seq` da fila de edições (`web/app/edicoes.Fila`), reaproveitado, não copiado. O site **nunca abre, mostra nem serve** o Excel ao navegador.
3. **No PC,** o robô traz os lotes na volta de 30 min, antes de montar o pacote (`bap_automation.sincronizar_visitas_web`; passos no contrato, §4.4), com **o mesmo laço `desde`/`epoca`/confirmar das edições**, extraído para uma função só, e monta com as mesmas funções do botão do PC (`depois_de_baixar`): uma regra num lugar só. Assim, o pacote dessa rodada já sai com as visitas novas.
4. **Um índice só de "dia baixado".** O PC tem o seu (`diario/_baixados.json`) e o site tem o `indice`. Para que nenhum lado baixe de novo o que o outro fechou:
   - **nuvem → PC:** a importação anota o dia com o `baixado_em` da nuvem; o `plano` do botão do PC já pula dia fechado;
   - **PC → nuvem:** o robô do PC manda, em toda volta, os dias que ele fechou (`fechados_pc`, contrato §4.3), e o site junta no `indice` pela mesma função pura (`juntar_baixado`, vale a hora maior). A nuvem decide só por esse `indice`;
   - **a janela que sobra:** o PC conta ao site o que fechou em até 30 min. Um dia baixado no PC nesse intervalo pode ser baixado de novo pela nuvem uma vez; o PC grava com outro nome e vale o mais novo (regra de hoje). É por isso que a agenda só liga com o robô do PC novo no ar (§3.1).
5. **Excel aberto** (`ACOMPANHAMENTO_VISITAS_BAP.xlsx` aberto por alguém): os arquivos do dia já ficaram gravados, e o acompanhamento devolve "aberto no Excel" (comportamento de hoje). Na volta seguinte, ele acrescenta o que faltou, porque a função é idempotente.
6. **O Farol de Visita e o Farol de Metas do PC** leem `RELATORIOS/Visitas` como hoje e não mudam. O Excel da nuvem tem só as colunas permitidas (§7), e o `ler_espelho` lê dele o mesmo que do Excel do PC (teste do contrato, §3.6).

### 5.2 Regras novas

O po registra no `docs/produto/03-regras.md`; os testes citam. Quando estiverem lá, a fonte passa a ser o `03-regras.md`.
- **RN-VIS-002:** o dia está fechado quando foi baixado num dia depois dele, **pela hora da baixa** (nuvem ou PC), em Manaus. A importação não fecha o dia. Entre a hora do PC e a da nuvem, vale a maior (`juntar_baixado`, função pura), e o PC e o site usam o mesmo resultado (§5.1, item 4).
- **RN-VIS-003:** a importação só acrescenta. Ela nunca sobrescreve nem apaga Excel do `ANALITICO`, e o acompanhamento só ganha linha de dia fechado (regra 7).
- **RN-VIS-004:** uma rodada da nuvem por vez (concessão de 10 min). O pedido do botão espera na fila.
- **RN-VIS-005:** senha recusada, confirmação, captcha ou bloqueio pedidos pela Máxima **pausam** as rodadas da nuvem até o "Retomar" do admin. Não há segunda tentativa de login.
- **RN-VIS-006:** dia com vendedor que falhou é baixado de novo **uma vez**, com sucesso ou falha. Depois disso, ele fica como está ("Baixar de novo" pelo admin ou pelo PC).
- **RN-VIS-007:** do Espelho, só as colunas da lista de permitidas saem do contêiner, e o nome do cliente e o texto livre saem limpos pela RN-GER-011. CNPJ, CPF, telefone, e-mail ou valor fora do formato que sobrarem **não sobem** e pausam a agenda e o botão. O "Retomar" fica registrado com o id da decisão do Alexandre e volta ao diagnóstico.
- **RN-VIS-008:** no máximo 8 logins da nuvem na Máxima por dia de Manaus, com teto por motivo; chegou ao teto, a nuvem para até o dia seguinte, e o botão do PC continua.

### 5.3 Por que um lote próprio, e não o pacote por farol do §10.8

| | Lote do dia em rotas próprias (escolhido) | O cron manda o `vc_visitas` pelo §10.8 |
|---|---|---|
| Quem monta o farol | o PC, como hoje (Planner, Prospecção, acompanhamento) | o cron teria de montar o `vc_visitas` sem o Planner nem a Prospecção (que só existem no PC): sairia um farol diferente do PC, contra o "número bate com o farol de origem" |
| Token | `BAP_VISITAS_TOKEN`, que só abre as rotas do cron | o `BAP_WEB_TOKEN`, que troca o pacote inteiro do site: um vazamento no cron estragaria todos os faróis |
| Excel no PC | volta ao `ANALITICO`, e os faróis do PC enxergam | não voltaria; o PC ficaria sem a visita baixada na nuvem |
| Atraso até a tela | até cerca de 40 min (§4), e o robô do PC precisa estar ligado | alguns minutos |

O atraso é o preço; montar o farol no Render fica para uma ADR futura, se o Planner e a Prospecção forem para o site.

## 6. Falhas: as saídas que dependem do Alexandre

Os códigos, o texto no site e o que acontece em seguida estão no contrato, §5. Aqui ficam só os casos que viram decisão:
- **Confirmação, captcha ou bloqueio no diagnóstico:** a agenda não é ligada, e o caso vira ADR nova com duas saídas: a liberação, na Máxima, dos IPs de saída do Render (publicados por região), ou a volta à opção A do po (senha no cofre do notebook do robô).
- **Dado pessoal no Espelho (`DADO_PESSOAL`, no diagnóstico ou numa rodada):** nada sobe, e o po leva ao Alexandre a coluna e o tipo (nunca o valor). A limpeza da RN-GER-011 já é o desenho (contrato §3.6); o achado é o que sobrou dela. As saídas: (a) a coluna sai da lista de permitidas, com o efeito no `montar_dia` medido pelo teste de igualdade; (b) a limpeza passa a cobrir aquela coluna; (c) o Alexandre aceita aquele tipo naquela coluna. As três mudam o contrato (v2) e o código do cron: retomar sem a mudança só acha o mesmo dado de novo. **O id do recado no "Retomar" é registro, não controle:** o site não confere se o recado existe nem quem o escreveu, e qualquer admin pode digitar um id bem formado. O controle é o diagnóstico de novo, rodado no código novo, antes de a agenda voltar.
- **O que o usuário nunca vê:** a senha, o usuário da Máxima, o texto cru do erro da Máxima, a URL com `PWE=` (o `url_limpa` já mascara) e o valor de qualquer célula do Espelho.

## 7. Segurança

- **A senha só no cron:** `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` ficam **só no `bap-visitas-maxima`**, nunca no `bap-central`, que atende a internet. O Alexandre cria os valores no painel; o time nunca vê nem pede o valor. Nada disso vai em código, `render.yaml`, log, recado ou commit. O cron lê os 2 segredos antes de abrir o Playwright; o que é proibido no cron (ambiente e código) está numa lista só, no contrato, §1.
- **Cookies e sessão:** contexto novo a cada rodada, sem `storage_state`. O contêiner do cron é descartado no fim, e o cron não tem disco. **Nada da sessão da Máxima é guardado**, nem no disco do site.
- **Logs sem dado pessoal (regra 6):**
  - o `Robo` hoje escreve o nome do vendedor no log ("NOME ✔"). O modulo-robo troca o `log` por **eventos** (`evento`, `fase`, `dia`, `n`, `codigo`) e uma função `texto_do_evento` de dois modos: no PC, com nome (a janela de hoje); na nuvem, sem nome;
  - um filtro final mascara o usuário e a senha, se aparecerem;
  - teste com nomes fictícios: nenhum nome entra no log da nuvem.
- **Tokens:** `BAP_VISITAS_TOKEN` é novo, sorteado pelo Render, e só abre as rotas do cron. Ele não envia pacote nem lê edições nem lotes. A comparação é em tempo constante. O robô do PC usa o `BAP_WEB_TOKEN` de hoje.
- **Sem chave da API do Render no site** (§3.3).
- **Dado de cliente no disco do Render (regra 6):** o Espelho traz código, nome e endereço de cliente, e pode trazer outras colunas (observação, por exemplo) com telefone ou e-mail digitados. O adendo 5 da ADR 0001 já leva código e nome de cliente do `vc_visitas` ao Render; o endereço é novo. Por isso:
  - **lista de permitidas, não de proibidas:** o lote leva só as colunas que o `ler_espelho` usa (contrato, §3.6). Coluna nova da Máxima nunca sai do contêiner por engano;
  - **limpar com a regra que o site já usa, e só depois procurar:** o cadastro traz CPF ou CNPJ no nome do cliente com frequência (84 em 2.216 nomes no Pedidos, `.coord/contratos/relatorio.md`); sem a limpeza da RN-GER-011, a nuvem pausaria quase todo dia;
  - **varredura do que sobrou** (RN-VIS-007): é melhor parar a nuvem e usar o PC por uns dias do que guardar dado pessoal no Render;
  - o diagnóstico faz o mesmo antes de ligar a agenda, e mostra as colunas que ficaram de fora;
  - o lote é **só trânsito**: nenhuma rota o mostra, e ele sai pela retenção (`LOTE_GUARDA_DIAS`).
- **Conta da Máxima (D4):** um usuário próprio do robô, com o mínimo de leitura do Painel Auditoria. Um vazamento do painel do Render expõe só esse usuário, que o Alexandre desativa na Máxima.
- **Regra 9:** nada de Microsoft 365 ou Graph. A Prospecção continua lida no PC.

## 8. Testes (agente testes; nomes com a RN)

- `test_RN_VIS_002_dia_fecha_pela_hora_da_baixa_nao_da_importacao`, `test_RN_VIS_002_juntar_baixado_vale_a_maior`, `test_RN_VIS_002_fechados_pc_entra_no_indice_e_a_nuvem_nao_baixa_de_novo`, `test_RN_VIS_002_erro_no_confirmar_tira_so_a_parte_da_nuvem`;
- `test_RN_VIS_003_importacao_nunca_sobrescreve_grava_com_sufixo`, `test_RN_VIS_003_mesmo_sha_pula`, `test_RN_VIS_003_nome_com_barra_ou_ponto_ponto_recusado`, `test_RN_VIS_003_acompanhamento_so_acrescenta`;
- `test_RN_VIS_004_segunda_concessao_409`, `test_RN_VIS_004_concessao_vencida_libera`, `test_RN_VIS_004_concessao_sobrevive_ao_reinicio`;
- `test_RN_VIS_005_senha_recusada_pausa_sem_segunda_tentativa`, `test_RN_VIS_005_classificar_login_captcha_confirmacao_bloqueio`, `test_RN_VIS_005_retomar_so_admin`;
- `test_RN_VIS_006_vendedor_que_falhou_tenta_uma_vez`, `test_RN_VIS_006_refeito_marcado_na_concessao_mesmo_com_falha`;
- `test_RN_VIS_007_filtro_deixa_so_as_permitidas`, `test_RN_VIS_007_ler_espelho_igual_antes_e_depois_do_filtro`, `test_RN_VIS_007_permitidas_igual_ao_contrato`, `test_RN_VIS_007_cnpj_cpf_telefone_email_e_formato_achados`, `test_RN_VIS_007_achado_nao_sobe_e_pausa`, `test_RN_VIS_007_retomar_registra_recado_e_volta_ao_diagnostico`, `test_RN_VIS_007_cliente_e_justificativa_limpos_antes_da_varredura`, `test_RN_VIS_007_diagnostico_com_achado_nao_liga_agenda`, `test_RN_VIS_007_saida_sem_valor_de_celula`;
- `test_RN_VIS_008_teto_por_motivo`, `test_RN_VIS_008_teto_da_soma_trava_tudo`, `test_RN_VIS_008_conta_na_concessao`, `test_RN_VIS_008_zera_na_virada_do_dia_de_manaus`, `test_RN_VIS_008_429_no_teto`;
- `deve_rodar`: diagnóstico pendente; agenda desligada; 06h00 com ontem aberto; ontem fechado pelo PC; pausado; pedido; fora da janela; retentativas às 06h30, 07h00 e 07h30 só com código de `NOVA_TENTATIVA`; nenhuma 5ª tentativa da agenda;
- laço do PC: os testes de `sincronizar_edicoes_web` rodam também no `puxar_fila_web` com o `aplicar` das visitas;
- perfis: 403 no botão para `diretor`, `pos_venda`, `pre_venda` e `vendas`; 403 no refazer, retomar, diagnóstico e agenda para o `gerente`;
- token: `BAP_VISITAS_TOKEN` não abre `/api/pacote*`, `/api/edicoes` nem `/api/visitas/lotes`; `BAP_WEB_TOKEN` não abre `/api/visitas/rodada*`;
- segredo: log com usuário, senha e nomes fictícios; `DEBUG=pw:api` recusado; o `environ` sem a senha depois da leitura; nenhum `screenshot` no caminho da nuvem;
- saída do processo: só 0 ou 1 (inclusive o vigia);
- imagem: o `Dockerfile` não tem `COPY . .` nem `ADD .`;
- códigos: todo `fim` traz um código da lista do contrato, §5, e o `STATUS_DO_CODIGO` cobre todos;
- ponta a ponta sem rede: Excel de exemplo **sem dado pessoal** (fixture gerada) → filtro → lote → importação → `diario/AAAAMMDD.csv` igual ao do PC com o mesmo Excel sem filtro (a limpeza só toca o nome e a justificativa, que o CSV do dia não usa);
- **diagnóstico no Render** (contrato, §6): o resultado vai ao Alexandre antes de ligar a agenda;
- **conferência de 5 dias úteis:** o mesmo dia baixado pelo PC e pela nuvem dá o mesmo `ler_espelho` por vendedor.

## 9. Plano por dono e ordem (a única fonte da ordem)

| # | Dono | O quê | Tamanho | Depende de |
|---|---|---|---|---|
| 1 | engenheiro-software | esta ADR; o contrato `visitas-nuvem.md` v1; `requirements-visitas.txt`; a proposta do `render.yaml` e o texto do `Dockerfile` (`docs/desenho/T-0045-render-yaml.md` e `.diff`), todos no PR #137 | feito | decisões |
| 2 | Alexandre (pelo po) | **governança 1:** as linhas do `.coord/donos.json` (desenho, §3). Na Máxima: o usuário próprio do robô | — | 1 |
| 3 | modulo-rota | `visitas_nucleo`: `dias_a_baixar(indice, de, ate, hoje, refazer)` (sai do `visitas_maxima.plano` e do `dia_fechado`), `juntar_baixado`, `filtrar_espelho` e `achar_dado_pessoal` (contrato, §3.6) | M (4 h) | 1 |
| 4 | designer-ux | simulação da tela "Atualizar visitas" (PNG, antes × depois), regra 10, ao Alexandre pelo po, com a divisão admin × gerente do §0 explícita | P (1 h) | 1 |
| 5 | modulo-web | contrato §3, §4.1 a §4.3, §4.5 e §7: rotas do cron e do robô, concessão, teto do dia, fila (`edicoes.Fila` parametrizada), diagnóstico e agenda em disco, `validar_lote`, `fechados_pc`, retenção, `/saude`, a tela no Farol de Visita, perfis, a versão nova do site | G (8 h) | 1, 4 |
| 6 | modulo-robo | `visitas_maxima.Robo`: canal do navegador configurável (na nuvem, o Chromium da imagem), log por eventos sem nome, `ao_fechar_dia(d, resultado)`, `classificar_login`, códigos fixos por fase, `foto=False` na nuvem; `depois_de_baixar` fora do `executar`. O botão do PC continua igual, mais o aviso do §3.4 | M (5 h) | 1, 3 |
| 7 | engenheiro-software | o `nuvem/visitas/Dockerfile` e o `.dockerignore` (o texto do item 1) | P | 2 |
| 8 | modulo-robo | `nuvem/visitas/`: `rodar.py` (vigia, diagnóstico, filtro antes do envio, cliente HTTP da biblioteca padrão), `agenda.py` (`deve_rodar`) e `__init__.py`; `bap_automation.puxar_fila_web` (extraído do `sincronizar_edicoes_web`) e `sincronizar_visitas_web` na volta de 30 min, com o `fechados_pc` e o 404 da web antiga | M (7 h) | 2, 3, 5 (no ar), 6 |
| 9 | testes | §8, a fixture sem dado pessoal e a matriz web nova × robô antigo | M (6 h) | 3, 5, 6, 8 |
| 10 | Alexandre (pelo po) | **governança 2:** o `render.yaml` num **PR próprio do Alexandre** (`alexandre/T-0045-render-yaml`), só depois dos itens 5, 7 e 8 no `main`, com o "autorizo" do po por delegação. No mesmo sync do Blueprint, ele preenche os 2 segredos que o Render pede (`sync: false`), para não haver voltas com `CONFIG_FALTANDO` | — | 5, 7, 8, 9 |
| 11 | modulo-robo + testes | acompanhar o **diagnóstico** (automático na primeira volta) e levar o resultado ao Alexandre; com o "ok", o admin liga a agenda; depois, a conferência de 5 dias úteis | P (2 h) + acompanhamento | 10 |

- **Ordem:** 1 → 2 → (3 ∥ 4 ∥ 5) → 6 → (7 ∥ 8) → 9 → 10 → 11.
- **Web antes do robô:** o PR do item 5 vai ao ar antes do "instale" da parte do PC do item 8 e antes do `render.yaml`.
- **Se o `render.yaml` entrar antes do código:** o build do cron fica vermelho no painel até o código chegar; o site não cai.
- **modulo-rota** entra só no item 3: a aderência ao Planner fica no PC e não muda.
- **Total:** cerca de 35 h de time, mais o diagnóstico.

## 10. Consequências e riscos

- **A Máxima pode estranhar o IP do Render** (EUA, Oregon) e pedir confirmação a cada login, ou bloquear. É o maior risco [SUPOSIÇÃO]. O diagnóstico mostra isso antes de ligar a agenda; as saídas estão no §6.
- **O Espelho pode trazer dado pessoal** que a limpeza não pega (num endereço, por exemplo). A nuvem para no primeiro achado, e o PC segue como reserva até a decisão do §6. Pode haver falso positivo (um número com cara de telefone); o custo é usar o PC por uns dias, nunca guardar o dado.
- **`relatorios_nucleo.py` na imagem:** ele muda com frequência, e cada mudança refaz a imagem do cron (`buildFilter`). Se os minutos de build pesarem, as funções da RN-GER-011 vão para um módulo pequeno (pedido ao dono do `relatorios_nucleo`).
- **Sessão única na Máxima** [SUPOSIÇÃO]: com o usuário próprio do robô, o PC e a nuvem usam logins diferentes. O aviso do §3.4 continua para quem usar o mesmo login.
- **Os termos de uso da Máxima** valem para a automação no Render como valem hoje no PC. Essa confirmação é do Alexandre.
- **Imagem Docker grande:** cada mudança no código das visitas refaz cerca de 2 GB de imagem. O `buildFilter` limita isso ao código da nuvem. Os minutos de build entram na franquia do Render [SUPOSIÇÃO].
- **Atraso até a tela:** §4 e §5.3; o robô do PC precisa estar ligado.
- **Dois caminhos de baixa** (PC e nuvem) **com um só jeito de montar e um só índice:** os arquivos e as funções são os mesmos (`depois_de_baixar`, `juntar_baixado`). A divergência fica limitada ao navegador e é vista na conferência de 5 dias.
- **Rede privada sem TLS:** o Bearer do cron trafega em claro dentro da rede privada do Render. É a rede da própria conta [SUPOSIÇÃO]; se o diagnóstico mostrar que o cron não alcança o `hostport`, a troca é para a URL pública com HTTPS (PR de governança).
- **Preços do Render não conferidos:** todos os valores em dólar são [SUPOSIÇÃO] e são confirmados no painel antes do "autorizo".
- **`bap_dados.VERSAO` fica em 27:** nada aqui toca o cache dos núcleos.

## Adendo 1 (27/11/2026): a nuvem com um passo só do Alexandre, o `render.yaml` antes do código e a D4 revista

- **Recados:** R-20261127-094157-alexandre (a nuvem, opção B, com um passo de governança só) e R-20261127-094656-alexandre (o mesmo login do notebook, "1 B").

**1. Ordem do §9 (corrige o item 10).**
- As governanças 1 e 2 vão **juntas**, num PR só do Alexandre (`alexandre/T-0045-governanca`), aplicando o `docs/desenho/T-0045-governanca.diff`. Frase e passos: `docs/desenho/T-0045-governanca.md`.
- O item 10 deixa de depender dos itens 5, 7, 8 e 9: ele depende **só do item 1** e entra junto com o item 2. A ordem passa a ser 1 → (2 + 10) → 8 → 7 → 9 → 11. O item 11 depende de 7, 8 e 9 no `main` e dos 2 segredos preenchidos.
- **O primeiro build do cron falha** (falta o `nuvem/visitas/Dockerfile`). É aceito: build falho não gera imagem, nada roda e não há execução a cobrar [SUPOSIÇÃO: o Render cobra o cron pelo tempo rodado]. O site não cai: ele só faz um deploy pela variável nova `BAP_VISITAS_TOKEN`. Com `autoDeploy: true` e o `buildFilter` (`nuvem/visitas/**`), o Render refaz o build sozinho quando o código entra.

**2. Nenhuma imagem roda sem o código.**
- O PR do modulo-robo com o `nuvem/visitas/` (`rodar.py`, `agenda.py`, `__init__.py`) entra **antes** do PR do `Dockerfile` e do `.dockerignore`. O `Dockerfile` é a chave que liga o build.
- **Trava no `Dockerfile`** (desenho, §3): `RUN python -c "import nuvem.visitas.rodar, nuvem.visitas.agenda"`. Se o `Dockerfile` chegar antes do código, o build falha de novo e nada roda. Importar o `rodar.py` não pode fazer nada (nem rede, nem navegador, nem segredo); o agente testes confere.

**3. D4 revista: o cron usa o mesmo login da Máxima do notebook.**
- O Alexandre preenche `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` com o usuário e a senha que o robô do notebook já usa. Nenhum agente, recado ou chat vê os dois.
- **Risco aceito pelo Alexandre:** se a Máxima bloquear o acesso vindo do Render, o notebook pode ser bloqueado também. Um vazamento do painel do Render expõe esse login, e a troca da senha na Máxima vale para os dois lugares: no notebook e no Render (sem isso, a nuvem para com `MAXIMA_SENHA`).
- **Sessão única na Máxima** [SUPOSIÇÃO]: com o mesmo login, uma rodada da nuvem pode derrubar a sessão do notebook, e vice-versa. O aviso do §3.4 vale sempre.
- **Uma tentativa só, sem insistir.** O que já garante:
  - contrato `visitas-nuvem.md`, §5.1: o `classificar_login` (`visitas_maxima.py`) nunca resolve captcha, nunca repete o login e nunca espera um humano;
  - contrato, §5: `MAXIMA_SENHA`, `MAXIMA_CONFIRMACAO`, `MAXIMA_CAPTCHA` e `MAXIMA_BLOQUEIO` **pausam**, e no diagnóstico não há nova tentativa;
  - contrato, §3.1, passo 1: pausado → o cron não pede trabalho;
  - código: `web/app/visitas.py`, `PAUSAM` e o `fim` (o código pausa a nuvem), a concessão recusada com 423 enquanto pausado, e o `diagnostico.estado = "falhou"`, que só volta a `pendente` pelo "Pedir diagnóstico" do admin; testes `test_RN_VIS_005_*` em `web/tests/test_T0045_visitas.py`.
- **A brecha que fica:** o `TENTATIVAS_DIA["diagnostico"]` é 2, e o "Retomar" de um `MAXIMA_*` não pede recado. Um segundo login no mesmo dia só acontece com 2 cliques do admin ("Retomar" e "Pedir diagnóstico"). **Regra até a mudança:** depois de um `MAXIMA_*`, o time não aperta nenhum dos dois sem o "ok" do Alexandre e avisa o po na hora. **Proposta** (pendência, ao gerente): o "Retomar" dos `MAXIMA_*` passa a pedir o recado do Alexandre, como o `DADO_PESSOAL` (RN-VIS-005; contrato §4 e `web/app/visitas.retomar`, modulo-web).
