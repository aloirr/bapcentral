# ADR 0004 — "Atualizar visitas" da Máxima no Render: o navegador roda num cron job à parte, e a senha fica só nele

- **Status:** **aceita** em 27/11/2026 (R-20261127-005437-alexandre: 2 A, 3 A, 4 A, 5 A, 6 B, que são as decisões D1 a D5 do §10). O código ainda não existe. O `render.yaml` muda num PR de governança à parte, com o "autorizo" do po por delegação (§2.4).
- **Data:** 2026-11-27 (proposta e versão final)
- **Tarefa:** T-0045 · **Autor:** engenheiro-software
- **Contrato:** `.coord/contratos/visitas-nuvem.md` **v1**: rotas, corpos, códigos de erro, tempos e os nomes das variáveis. Esta ADR diz o porquê; o contrato diz o formato.
- **Depende de:**
  - ADR 0001: web no Render, modelo M2, perfis (§4.5), adendos 2, 4 e 5;
  - ADR 0002: rotina diária (regra 11) e o limite 3 (`/saude`);
  - ADR 0003 e o contrato do relatório §10.8: o pacote por farol. Ele continua sendo o único caminho do `vc_visitas` até a tela (§5.3).
- **Consumidores:**
  - modulo-robo: `visitas_maxima.py` (o `Robo`), `bap_automation.py` (a importação na volta de 30 min), `atualizar_visitas.bat` (sem mudança) e a pasta nova `nuvem/visitas/`;
  - modulo-rota: `visitas_nucleo.py` (2 funções puras);
  - modulo-web: `web/app/` (API, tela "Atualizar visitas", `/saude`);
  - testes; designer-ux (simulação da tela, regra 10).
- **Recados:**
  - R-20261126-182728-alexandre: a opção C, contra a recomendação do po (texto literal no recado);
  - R-20261126-224331-gerente-projetos: o desenho e as 5 decisões levadas ao Alexandre;
  - R-20261127-005437-alexandre: as decisões;
  - R-20261126-175814-gerente-projetos: o plano da migração (T-0043 "Pedir rodada", a volta de 30 min);
  - `recados/anexos/T-0033/inventario-pc-site.md`, item 24 e §2.3.

## 0. O que ficou decidido

| # | Decisão do Alexandre | O que vale |
|---|---|---|
| D1 (2 A) | onde roda | um **cron job à parte** no Render, `bap-visitas-maxima`, Docker, plano de 2 GB cobrado por minuto (cerca de US$ 1 a 3 por mês [SUPOSIÇÃO: preço a conferir no painel]). O site `bap-central` continua no Starter |
| D2 (3 A) | quando roda sozinho | às **06h00 de Manaus**, todo dia, baixando **ontem** |
| D3 (4 A) | quem aperta "Atualizar visitas" no site | **admin e gerente**. "Baixar de novo", "Retomar", "Rodar diagnóstico" e "Ligar a agenda" só o admin |
| D4 (5 A) | login da Máxima | um **usuário próprio do robô**, criado pelo Alexandre na Máxima, com o mínimo de leitura do Painel Auditoria. Usuário e senha só como variáveis secretas do cron, criadas por ele no painel do Render |
| D5 (6 B) | print da tela no erro | **sem print**: só o código do erro e a fase (contrato, §5) |
| — | antes de ligar | um **diagnóstico real no Render** (contrato, §6): confirmação, captcha, bloqueio, memória e tempo. A agenda nasce desligada e só o admin a liga, depois do "ok" do Alexandre |

E três escolhas técnicas desta versão final, explicadas abaixo:
- **entrega das visitas ao site:** rotas próprias com token próprio (`BAP_VISITAS_TOKEN`) e um **lote por dia** com os Excel, não o pacote por farol do §10.8 (§5.3);
- **botão fora de hora:** uma **fila no disco do site**, que o cron lê a cada 10 min, não a API do Render (§3.3);
- **o token do cron** é sorteado pelo Render (`generateValue`) e copiado para o cron pelo Blueprint: o Alexandre só cria os 2 segredos da Máxima (§2.4).

## 1. Contexto

**Hoje, no PC** (`visitas_maxima.py`, chamado pelo `atualizar_visitas.bat` ou pelo botão do Farol de Visita):
1. pede usuário e senha da Máxima na hora (a senha nunca é gravada) e abre o Edge/Chrome pelo Playwright;
2. entra no maxGestão > Painel Auditoria e marca todas as filiais, supervisores e representantes;
3. **baixa**, dia a dia e vendedor a vendedor, o Espelho de Rotas em Excel: `RELATORIOS/Visitas/ANALITICO/<VENDEDOR>/VISITA-<VENDEDOR>-DD-MM-AAAA-HH-MM.xlsx`;
4. **monta**, com esses Excel, `diario/AAAAMMDD.csv` (`visitas_nucleo.montar_dia`), `AAAAMM.csv` (`montar_mes`), `ACOMPANHAMENTO_VISITAS_BAP.xlsx` (`atualizar_acompanhamento`, só acrescenta linha) e `VISITAS_POR_CLIENTE.xlsx` (`atualizar_por_cliente`, retrato refeito);
5. junta a Prospecção do Forms (`prospeccao_forms.atualizar`), que lê o Excel de respostas **sincronizado pelo OneDrive no PC**.

**No site,** o Farol de Visita (`vc_visitas`) mostra o que o robô mandou no pacote, montado no PC a partir desses arquivos (`bap_automation._FONTE_BAIXADO_WEB`).

**O que muda com a opção C:** só o passo 3 (o navegador e a senha) vai para o Render. Os passos 4 e 5 **continuam no PC**, com o mesmo código, por três motivos:
- a Prospecção depende do OneDrive do PC; lê-la do Render exigiria o Graph (regra 9);
- a aderência ao Planner lê as rotas exportadas que estão no PC (`visitas_nucleo._RX_ROTA_PLANNER`);
- o `ACOMPANHAMENTO_VISITAS_BAP.xlsx` é a planilha de acompanhamento da regra 7 (só acrescentar). Ela fica com um dono só, o PC.

**Números de hoje** (da pasta `RELATORIOS/Visitas`, sem nome):
- 15 representantes por dia (17 pastas no ANALITICO);
- 1.622 Excel em 111 dias, com 22 a 51 KB cada (mediana de 26 KB): cerca de 0,4 MB por dia;
- tempo por dia no PC, pelo `_baixados.json` (out–nov/2026): de 77 a 310 s, em geral de 107 a 152 s;
- o robô do PC roda na volta de 30 min, das 07h às 21h (ATIVAR_ROBO_30MIN), e o web do Render é o Starter de 512 MB (`render.yaml`).

## 2. Onde roda o Playwright no Render (D1 = A)

### 2.1 Memória e CPU estimadas

Tudo [SUPOSIÇÃO]: não há Playwright neste ambiente e não se mede sem a Máxima. A conta vem do Chromium sem tela com uma SPA pesada (o maxGestão é React com MUI DataGrid, e o visualizador do Espelho é um gerador de relatório em JavaScript). A medida real sai do diagnóstico (contrato, §6).

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
| **W3** | **cron job à parte** (`type: cron`, Docker) | **cerca de US$ 1 a 3** | **escolhida (D1 = A):** isolado do site, paga só o minuto rodado, a senha fica só nele, o Render roda uma execução por vez e o deploy do site não interrompe a rodada |

Características do Render que a W3 usa, todas [SUPOSIÇÃO: conhecidas da documentação do Render, que não pôde ser aberta desta sessão; conferidas no diagnóstico e no painel]:
- o cron job aceita `runtime: docker`, os planos `starter`, `standard` e `pro`, e **não aceita disco**;
- a cobrança é por segundo de execução, com mínimo de US$ 1 por mês por cron job. Standard (2 GB, 1 CPU) cerca de US$ 0,00058 por minuto; Starter (512 MB, 0,5 CPU) cerca de US$ 0,00016;
- o `schedule` é uma expressão cron em **UTC**;
- uma execução dura no máximo 12 h, e a próxima não começa enquanto a anterior roda;
- o cron fala com o web pela rede privada da mesma região (`fromService ... property: hostport`), sem TLS dentro da rede do Render;
- o Blueprint aceita `generateValue: true` e `fromService ... envVarKey` para copiar uma variável de outro serviço.

### 2.3 Plano do cron: Standard, e o diagnóstico decide se desce

- **Standard (2 GB, 1 CPU).** Por minuto, a diferença para o Starter é de centavos no mês, e o Standard tira o risco de faltar memória.
- Com **pico abaixo de 350 MB** no diagnóstico, ele desce para o Starter; acima de 1.600 MB, sobe (os dois, PR de governança).

### 2.4 O `render.yaml` (proposta de governança, branch `engenheiro-software/T-0045-render-yaml`)

O texto exato está em `docs/desenho/T-0045-render-yaml.md` nessa branch. Resumo:
- **serviço novo `bap-visitas-maxima`:** `type: cron`, `runtime: docker`, `plan: standard`, `region: oregon` (a do site), `schedule: "*/10 10-23,0-1 * * *"` (UTC = de 10 em 10 min, das 06h00 às 21h50 de Manaus), `dockerfilePath: ./nuvem/visitas/Dockerfile`, `dockerContext: .` e `buildFilter` com só o código dele;
- **variáveis do cron:** `TZ` e `PYTHONUNBUFFERED` (valor fixo), `BAP_WEB_HOSTPORT` e `BAP_VISITAS_TOKEN` (`fromService`), `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` (`sync: false`, **os dois únicos segredos** que o Alexandre cria);
- **no `bap-central`, uma linha só:** `BAP_VISITAS_TOKEN` com `generateValue: true`. O Render sorteia o valor, e ninguém do time o vê.

**Imagem Docker:** parte da oficial do Playwright para Python (`mcr.microsoft.com/playwright/python:v<versão>-noble`, Ubuntu 24.04 com Python 3.12), com o Chromium e as bibliotecas do sistema já dentro.
- A versão do pip fica fixada no `requirements-visitas.txt` (engenheiro-software), igual à da imagem.
- O `Dockerfile` copia **uma lista fechada de arquivos** (`requirements-visitas.txt`, `visitas_maxima.py`, `visitas_nucleo.py`, `nuvem/visitas/`). **`COPY . .` é proibido**, porque levaria as bases (`RELATORIOS/`, com dado de cliente) para a imagem. Um teste confere.
- Roda como o usuário sem privilégio da imagem (`pwuser`).

**Donos (governança, `.coord/donos.json`, antes do código do cron):**
- `nuvem/visitas/Dockerfile` → **engenheiro-software** (base técnica, como os `requirements*.txt`);
- `nuvem/**` → **modulo-robo** (o `rodar.py` e a agenda são o robô).
- Hoje os dois caminhos são "sem-dono", e o guardião bloqueia. Por isso o `Dockerfile` está **como texto** no desenho e só entra no repositório depois dessas linhas.

**Sem dependência nova no PC:** o robô DT-AMADMBAP-03 importa com `requests` e a biblioteca padrão. O Playwright e o `openpyxl` já estão no `requirements.txt` do PC. Nada de pyarrow nem de Git.

## 3. Quando roda e quem aperta (D2 = A, D3 = A)

### 3.1 Agenda

- **Um cron só,** de 10 em 10 min das 06h00 às 21h50 de Manaus. A cada volta, ele pergunta ao site se há trabalho (`GET /api/visitas/trabalho`) e decide com a função pura `deve_rodar(agora, trabalho)` (contrato, §3.1). A volta sem trabalho sai em segundos.
- **Às 06h00, todo dia** (sábado e domingo também, como o PC), baixa **ontem**, que fecha o dia. Com `MAXIMA_FORA`, `SITE_FORA` ou rodada interrompida, tenta de novo às 06h30, 07h00 e 07h30.
- **A agenda nasce desligada.** O primeiro trabalho do cron, com as variáveis presentes, é o diagnóstico. Só o admin liga a agenda, e só com diagnóstico `ok`.

### 3.2 Botão "Atualizar visitas" no site

- Fica no Farol de Visita. Pede um período, com padrão "dias ainda abertos até hoje" e **no máximo 7 dias**; período maior continua no PC (até 93 dias).
- **Quem aperta:** `admin` e `gerente`. Os outros perfis veem o estado e não veem o botão. O corte é feito no servidor, com teste de 403 por perfil (ADR 0001, §4.5).
- **O botão do PC continua** (decisão do R-20261126-182728 até a entrega, e depois como reserva). O desligamento dele segue a T-0044: 2 semanas iguais e o "ok" do Alexandre.

### 3.3 Como o botão dispara uma rodada fora de hora: fila no site (escolhida) × API do Render

| | Como | Tempo até começar | Por que |
|---|---|---|---|
| **Fila (escolhida)** | o botão grava o pedido em `/var/data/visitas/estado.json`; o cron, que acorda de 10 em 10 min, lê no `GET /api/visitas/trabalho` | até 10 min | nenhum segredo novo no site; o site só guarda o pedido; o mesmo caminho serve à agenda, à retentativa e ao diagnóstico |
| API do Render | o site chama `POST /v1/cron-jobs/<id>/runs` com uma chave da API do Render | cerca de 1 min | **recusada:** a chave da API do Render é da conta inteira [SUPOSIÇÃO: o Render não tem chave restrita a um serviço]. Com ela, quem invadir o site lê as variáveis de todos os serviços, **inclusive a senha da Máxima**, e pode apagar serviços. Isso desfaz o "senha só no cron" da D1 |

- **Custo da fila:** 96 voltas por dia sem trabalho, de cerca de 30 s cada (a partida do contêiner [SUPOSIÇÃO: cobrada]), são cerca de 1.440 min por mês, ou cerca de US$ 0,85 no Standard.
- O "Trigger Run" do painel do Render continua servindo ao Alexandre para não esperar os 10 min no diagnóstico [SUPOSIÇÃO: nome do botão no painel].

### 3.4 Duas rodadas que se cruzam

O site guarda uma **concessão** (lease): só uma rodada ativa por vez, gravada em disco (`/var/data/visitas/estado.json`) para sobreviver ao deploy. A concessão vale 10 min e é renovada a cada vendedor.

| Caso | O que acontece |
|---|---|
| Botão apertado durante uma rodada | o pedido entra na fila (no máximo 1 pendente). Apertar de novo mostra "Já pedido às HHhMM". Ele é atendido na volta seguinte ao fim da rodada |
| Agenda das 06h00 e um pedido juntos | uma rodada só, com os dias dos dois |
| Duas execuções do cron ao mesmo tempo (atraso do Render) | a segunda recebe 409 ao pedir a concessão e sai |
| Rodada morta (memória, tempo) | a concessão vence em 10 min, e o site grava `RODADA_INTERROMPIDA`. Os dias já enviados ficam, e a volta seguinte baixa só o que falta |
| Pedido maior que uma rodada (45 min, §4) | a rodada para no fim de um dia (`PARCIAL_TEMPO`), e o pedido continua na volta seguinte, até 3 rodadas |
| "Atualizar visitas" do PC durante a rodada do site | o PC consulta `GET /api/visitas/estado` e avisa: "O site está baixando agora; baixar aqui também pode derrubar a sessão da Máxima. Continuar?" Se a pessoa seguir, os dois gravam com nomes diferentes, e vale o Excel mais novo por vendedor e dia (`espelhos_do_periodo`, regra de hoje). [SUPOSIÇÃO: a Máxima pode aceitar uma sessão só por usuário; com o usuário próprio do robô (D4), o PC usa outro login e o risco cai] |

## 4. Tempo de cada rodada e limites

| Etapa | No PC (medido) | No Standard [SUPOSIÇÃO] |
|---|---|---|
| Login, maxGestão, Painel Auditoria e filtros | cerca de 1 a 2 min | 1,5 a 3 min |
| Um dia (15 vendedores) | 77 a 310 s, em geral de 107 a 152 s | 2,5 a 5 min |
| **Agenda (1 dia)** | — | **cerca de 5 a 8 min** |
| **Botão com 7 dias** | — | **cerca de 20 a 40 min** |
| **Diagnóstico (1 dia, 2 vendedores)** | — | **cerca de 3 a 5 min** (teto de 15) |

- **Tempo-limite da rodada:** 45 min (`RODADA_MAX_MIN`), conferido no fim de cada dia; o que faltar continua na volta seguinte. Um vigia liga o `parar` do `Robo` aos 55 min e encerra o processo aos 58 min. O teto do Render (12 h) nunca é o freio. Os valores estão no contrato, §2.
- **Do fim da rodada até a tela:** até 30 min para o robô do PC importar (§5), mais a rodada do robô (cerca de 9 min). Na tela, o "baixado em" do farol muda nessa volta.
- **Conta do custo (Standard):** a agenda dá 30 × 8 min; 10 botões de 25 min por mês; e as voltas sem trabalho do §3.3. São cerca de 1.900 min por mês, **cerca de US$ 1 a 3 por mês** [SUPOSIÇÃO: preço por minuto a conferir no painel].

## 5. Como as visitas chegam ao site e voltam ao PC sem perder dado

### 5.1 O caminho

```
cron (Render) --POST lote do dia--> site (/var/data/visitas/lotes) <--GET na volta de 30 min-- robô do PC
                                                                    --grava ANALITICO, monta, confirma-->
robô do PC --pacote por farol (§10.8, com o vc_visitas novo)--> site --> Farol de Visita
```

1. **Na nuvem,** a cada dia completo, o cron manda ao site um **lote do dia**: um JSON com gzip que leva `dia`, `baixado_em` (Manaus), `extras`, `equipe`, as contagens e os Excel (nome, sha256 e conteúdo em base64). São cerca de 0,5 MB por dia. Formato e respostas: contrato, §3.4.
2. **No site,** o lote fica em disco com um `seq` crescente e uma `epoca`, no mesmo desenho da fila de edições (`web/app/edicoes.py`). A gravação é atômica. O site **nunca abre, mostra nem serve** o Excel ao navegador.
3. **No PC,** o robô traz os lotes na volta de 30 min, **antes de montar o pacote**, no mesmo ponto do `sincronizar_edicoes_web` (`bap_automation.passo_pacote_web`). Assim, o pacote dessa rodada já sai com as visitas novas. A função nova é `sincronizar_visitas_web(raiz, base, token, log)` (contrato, §4.5), que nunca levanta e nunca derruba a rodada:
   1. `GET /api/visitas/lotes?desde=<seq>` e o lote, com a conferência do sha256 de cada arquivo. Um arquivo que não confere recusa o lote ("recusado:sha256"), e a nuvem baixa o dia de novo;
   2. **grava os Excel no `ANALITICO`,** sempre por `.tmp` + `os.replace`:
      - o nome tem de casar com `visitas_nucleo._RX_ARQ_ANALITICO`, sem `/`, `\` ou `..`;
      - a pasta é o `nome_limpo` do vendedor;
      - já existe com o mesmo sha256: pula (idempotente);
      - já existe com outro conteúdo: grava com o sufixo `-2`, `-3`… (`arquivo_analitico`).
      - **Nunca sobrescreve nem apaga.**
   3. `gravar_equipe_maxima` (mescla); `anotar_baixado` do dia **com o `baixado_em` da nuvem**, não com a hora da importação (RN-VIS-001); `montar_dia(raiz, d, extras)`; `montar_mes` dos meses tocados, anotado com o maior `baixado_em` do mês;
   4. uma vez por importação, o mesmo fim do botão do PC: `atualizar_acompanhamento` (só acrescenta dia fechado), `atualizar_por_cliente` e `prospeccao_forms.atualizar`. Esse fim sai do `visitas_maxima.executar` para uma função só, `depois_de_baixar(raiz, log)`, chamada pelo botão do PC e pela importação (uma regra num lugar só);
   5. registra em `RELATORIOS/_VISITAS_WEB/IMPORTADOS_VISITAS_WEB.jsonl` (só acréscimo) e confirma com `POST /api/visitas/lotes/confirmar`. Confirmação que falha é repetida na volta seguinte, e o `.jsonl` impede gravar duas vezes.
4. **Excel aberto** (`ACOMPANHAMENTO_VISITAS_BAP.xlsx` aberto por alguém): os arquivos do dia já ficaram gravados, e o acompanhamento devolve "aberto no Excel" (comportamento de hoje). Na volta seguinte, ele acrescenta o que faltou, porque a função é idempotente.
5. **O Farol de Visita e o Farol de Metas do PC** leem `RELATORIOS/Visitas` como hoje e não mudam. Os arquivos ficam iguais aos que o botão do PC grava.

### 5.2 Regras novas

O po registra no `docs/produto/03-regras.md`; os testes citam.
- **RN-VIS-001:** o dia está fechado quando foi baixado num dia depois dele, **pela hora da baixa** (nuvem ou PC), em Manaus. A importação não fecha o dia. Entre a hora do PC e a da nuvem, vale a maior (`juntar_baixado`, função pura).
- **RN-VIS-002:** a importação só acrescenta. Ela nunca sobrescreve nem apaga Excel do `ANALITICO`, e o acompanhamento só ganha linha de dia fechado (regra 7).
- **RN-VIS-003:** uma rodada da nuvem por vez (concessão de 10 min). O pedido do botão espera na fila.
- **RN-VIS-004:** senha recusada, confirmação, captcha ou bloqueio pedidos pela Máxima **pausam** as rodadas da nuvem até o "Retomar" do admin. Não há segunda tentativa de login.
- **RN-VIS-005:** dia com vendedor que falhou é baixado de novo **uma vez** na volta seguinte. Depois disso, ele fica como está ("Baixar de novo" pelo admin ou pelo PC).

### 5.3 Por que um lote próprio, e não o pacote por farol do §10.8

| | Lote do dia em rotas próprias (escolhido) | O cron manda o `vc_visitas` pelo §10.8 |
|---|---|---|
| Quem monta o farol | o PC, como hoje (Planner, Prospecção, acompanhamento) | o cron teria de montar o `vc_visitas` sem o Planner nem a Prospecção (que só existem no PC): sairia um farol diferente do PC, contra o "número bate com o farol de origem" |
| Token | `BAP_VISITAS_TOKEN`, que só abre as rotas do cron | o `BAP_WEB_TOKEN`, que troca o pacote inteiro do site: um vazamento no cron estragaria todos os faróis |
| Excel no PC | volta ao `ANALITICO`, e os faróis do PC enxergam | não voltaria; o PC ficaria sem a visita baixada na nuvem |
| Atraso até a tela | até cerca de 40 min, e o robô do PC precisa estar ligado | alguns minutos |

O atraso é o preço; montar o farol no Render fica para uma ADR futura, se o Planner e a Prospecção forem para o site.

## 6. Falhas: o que o usuário vê e o que fica no PC

A lista fechada dos códigos, com o texto de cada um no site, está no contrato, §5. Os casos principais:

| Caso | Código | O que fica no PC | Depois |
|---|---|---|---|
| **A Máxima pede confirmação** (código por SMS ou e-mail, novo dispositivo, termo, troca de senha) | `MAXIMA_CONFIRMACAO` | nada muda; o botão do PC funciona | **pausa** (RN-VIS-004). O cron nunca espera um humano |
| **Captcha** | `MAXIMA_CAPTCHA` | idem | **pausa**. O cron nunca tenta resolver |
| **Bloqueio** (conta bloqueada, acesso negado, HTTP 403 no login) | `MAXIMA_BLOQUEIO` | idem | **pausa** e o caso vai ao Alexandre |
| **Senha errada ou vencida** | `MAXIMA_SENHA` | nada | **pausa** imediata, sem segunda tentativa, para não bloquear a conta. Só o Alexandre troca no painel do Render |
| **A tela da Máxima mudou** | `TELA_MUDOU` + fase | os dias completos chegam; nada é apagado | 2 rodadas seguidas na mesma fase pausam a agenda. A correção é do modulo-robo, testada no PC com "Mostrar o navegador" |
| **Um vendedor falhou** | `PARCIAL_VENDEDOR` | o dia chega com os outros | nova tentativa uma vez (RN-VIS-005) |
| **A Máxima está fora** | `MAXIMA_FORA` | nada | agenda: até 3 novas tentativas, de 30 em 30 min; botão: o pedido sai da fila |
| **Falta de memória ou de tempo no Render** | `NAVEGADOR_FALHOU` ou `RODADA_INTERROMPIDA` | os dias já enviados chegam | a volta seguinte baixa o que falta. 2 seguidas aparecem no `/saude`, e o plano é revisto |
| **Site fora ou em deploy** | `SITE_FORA` (só no log do Render) | nada | o dia volta a ser baixado depois (sem disco, a nuvem não guarda) |
| **Robô do PC parado** | — ("Baixado às 06h08 · esperando o PC importar") | nada até o robô voltar | os lotes esperam no site até 30 dias; nada se perde |

- **Confirmação ou captcha no diagnóstico:** a agenda não é ligada, e o caso vira ADR nova com duas saídas: a liberação, na Máxima, dos IPs de saída do Render (publicados por região), ou a volta à opção A do po (senha no cofre do notebook do robô).
- **Sem print (D5 = B):** a nuvem não tira print em nenhum caso. O código e a fase bastam; o print continua só no PC (`Visitas/_erros`), quando a pessoa usa o botão do PC.
- **O que o usuário nunca vê:** a senha, o usuário da Máxima, o texto cru do erro da Máxima, a URL com `PWE=` (o `url_limpa` já mascara).

## 7. Segurança

- **A senha só no cron:** `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` (`sync: false`) ficam **só no `bap-visitas-maxima`**, nunca no `bap-central`, que atende a internet.
  - O Alexandre cria os valores no painel. O time nunca vê nem pede o valor. Nada disso vai em código, `render.yaml`, log, recado ou commit.
  - O cron lê com `os.environ.pop(...)` **antes** de abrir o Playwright, para que o driver (processo filho) não herde a senha.
  - A senha vai só no `fill` do login e em seguida vira `None` (como o `Robo.rodar` já faz).
- **Proibido no cron:**
  - `DEBUG=pw:*`, porque o `pw:api` imprime o texto do `fill`; o `rodar.py` recusa partir com ele (`CONFIG_INSEGURA`);
  - trace, vídeo, HAR, `page.on("console")` e print de tela.
  - Os testes conferem tudo isso.
- **Cookies e sessão:** contexto novo a cada rodada, sem `storage_state`. O contêiner do cron é descartado no fim, e o cron não tem disco. **Nada da sessão da Máxima é guardado**, nem no disco do site.
- **Logs sem dado pessoal (regra 6):**
  - o `Robo` hoje escreve o nome do vendedor no log ("NOME ✔"). O modulo-robo troca o `log` por **eventos** (`evento`, `fase`, `dia`, `n`, `codigo`) e uma função `texto_do_evento` de dois modos: no PC, com nome (a janela de hoje); na nuvem, sem nome;
  - um filtro final mascara o usuário e a senha, se aparecerem;
  - teste com nomes fictícios: nenhum nome entra no log da nuvem.
- **Tokens:** `BAP_VISITAS_TOKEN` é novo, sorteado pelo Render, e só abre as rotas do cron. Ele não envia pacote nem lê edições nem lotes. A comparação é em tempo constante. O robô do PC usa o `BAP_WEB_TOKEN` de hoje.
- **Sem chave da API do Render no site** (§3.3).
- **Dado de cliente no disco do Render:** o Espelho traz código, nome e endereço de cliente. O adendo 5 da ADR 0001 já leva código e nome de cliente do `vc_visitas` ao Render; o endereço é novo. Por isso:
  - o lote é **só trânsito**: nenhuma rota o mostra, e ele sai 7 dias depois de importado;
  - o diagnóstico confere, só pelo cabeçalho, se o Espelho tem CNPJ ou telefone (`espelho_colunas`). Se tiver, o lote continua só em trânsito, e isso vai ao Alexandre.
- **Conta da Máxima (D4 = A):** um usuário próprio do robô, com o mínimo de leitura do Painel Auditoria. Um vazamento do painel do Render expõe só esse usuário, que o Alexandre desativa na Máxima.
- **Regra 9:** nada de Microsoft 365 ou Graph. A Prospecção continua lida no PC.

## 8. Testes (agente testes; nomes com a RN)

- `test_RN_VIS_001_dia_fecha_pela_hora_da_baixa_nao_da_importacao`, `test_RN_VIS_001_juntar_baixado_vale_a_maior`;
- `test_RN_VIS_002_importacao_nunca_sobrescreve_grava_com_sufixo`, `test_RN_VIS_002_mesmo_sha_pula`, `test_RN_VIS_002_nome_com_barra_ou_ponto_ponto_recusado`, `test_RN_VIS_002_acompanhamento_so_acrescenta`;
- `test_RN_VIS_003_segunda_concessao_409`, `test_RN_VIS_003_concessao_vencida_libera`, `test_RN_VIS_003_concessao_sobrevive_ao_reinicio`;
- `test_RN_VIS_004_senha_recusada_pausa_sem_segunda_tentativa`, `test_RN_VIS_004_classificar_login_captcha_confirmacao_bloqueio`, `test_RN_VIS_004_retomar_so_admin`;
- `test_RN_VIS_005_vendedor_que_falhou_tenta_uma_vez`;
- `deve_rodar`: diagnóstico pendente; agenda desligada; 06h00 com ontem aberto; pausado; pedido; fora da janela; retentativa às 06h30;
- perfis: 403 no botão para `diretor`, `pos_venda`, `pre_venda` e `vendas`; 403 no refazer, retomar, diagnóstico e agenda para o `gerente`;
- token: `BAP_VISITAS_TOKEN` não abre `/api/pacote*`, `/api/edicoes` nem `/api/visitas/lotes`; `BAP_WEB_TOKEN` não abre `/api/visitas/rodada*`;
- segredo: log com usuário, senha e nomes fictícios; `DEBUG=pw:api` recusado; o `environ` sem a senha depois da leitura; nenhum `screenshot` no caminho da nuvem;
- imagem: o `Dockerfile` não tem `COPY . .` nem `ADD .`;
- códigos: todo `fim` traz um código da lista do contrato, §5;
- ponta a ponta sem rede: Excel de exemplo **sem dado pessoal** (fixture gerada) → lote → importação → `diario/AAAAMMDD.csv` igual ao do PC com o mesmo Excel.
- **Diagnóstico no Render** (contrato, §6): o resultado vai ao Alexandre antes de ligar a agenda.
- **Conferência de 5 dias úteis:** o mesmo dia baixado pelo PC e pela nuvem dá o mesmo cabeçalho do Espelho por vendedor.

## 9. Plano por dono e ordem

| # | Dono | O quê | Tamanho | Depende de |
|---|---|---|---|---|
| 1 | engenheiro-software | esta ADR final; contrato `visitas-nuvem.md` v1; `requirements-visitas.txt`; proposta do `render.yaml` e o texto do `Dockerfile` (branch `engenheiro-software/T-0045-render-yaml`) | feito | decisões |
| 2 | Alexandre (pelo po) | **governança 1:** as duas linhas do `.coord/donos.json` (§2.4: `nuvem/visitas/Dockerfile` → engenheiro-software; `nuvem/**` → modulo-robo). Na Máxima: o usuário próprio do robô | — | 1 |
| 3 | modulo-rota | `visitas_nucleo`: as funções puras `dias_a_baixar(indice, de, ate, hoje, refazer)` (sai do `visitas_maxima.plano` e do `dia_fechado`) e `juntar_baixado` | P (2 h) | 1 |
| 4 | designer-ux | simulação da tela "Atualizar visitas" (PNG, antes × depois), regra 10, ao Alexandre pelo po | P (1 h) | 1 |
| 5 | modulo-web | contrato §3, §4.1 a §4.4, §4.6 e §7: rotas do cron e do robô, concessão, fila, diagnóstico e agenda em disco, `validar_lote`, retenção, `/saude`, a tela no Farol de Visita, perfis, a versão nova do site | G (8 h) | 1, 4 |
| 6 | modulo-robo | `visitas_maxima.Robo`: canal do navegador configurável (na nuvem, o Chromium da imagem), log por eventos sem nome, `ao_fechar_dia(d, resultado)`, `classificar_login`, códigos fixos por fase, `foto=False` na nuvem; `depois_de_baixar` fora do `executar`. O botão do PC continua igual, mais o aviso do §3.4 | M (5 h) | 1, 3 |
| 7 | engenheiro-software | o `nuvem/visitas/Dockerfile` (o texto do item 1) | P | 2 |
| 8 | modulo-robo | `nuvem/visitas/`: `rodar.py` (com o vigia, o diagnóstico e o cliente HTTP da biblioteca padrão), `agenda.py` (`deve_rodar`) e `__init__.py`; `bap_automation.sincronizar_visitas_web` na volta de 30 min, com o 404 da web antiga | M (6 h) | 2, 5 (no ar), 6 |
| 9 | testes | §8, a fixture sem dado pessoal e a matriz web nova × robô antigo | M (5 h) | 3, 5, 6, 8 |
| 10 | Alexandre (pelo po) | **governança 2:** "autorizo" do PR do `render.yaml`, que só entra **depois** dos itens 5, 7 e 8 no `main` (senão o primeiro build do cron falha). Depois do merge, cria os 2 segredos no painel | — | 5, 7, 8, 9 |
| 11 | modulo-robo + testes | acompanhar o **diagnóstico** (automático na primeira volta com as variáveis) e levar o resultado ao Alexandre; com o "ok", o admin liga a agenda; depois, a conferência de 5 dias úteis | P (2 h) + acompanhamento | 10 |

- **Ordem:** 1 → 2 → (3 ∥ 4 ∥ 5) → 6 → (7 ∥ 8) → 9 → 10 → 11.
- **Web antes do robô:** o PR do item 5 vai ao ar antes do "instale" da parte do PC do item 8 e antes do `render.yaml`.
- **modulo-rota** entra só no item 3: a aderência ao Planner fica no PC e não muda.
- **Total:** cerca de 32 h de time, mais o diagnóstico.

## 10. Decisões do Alexandre (registro)

Do que se tratava: como a atualização das visitas da Máxima vai rodar no Render, que é a opção C já escolhida.

| # | Pergunta | Escolha | Recomendação do time |
|---|---|---|---|
| D1 | onde o navegador roda no Render | **A**: um cron job à parte, cobrado por minuto, cerca de US$ 1 a 3 por mês; o site continua no plano de US$ 7 | A |
| D2 | quando roda sozinho | **A**: às 06h00, todo dia, baixando ontem, mais o botão | A |
| D3 | quem aperta "Atualizar visitas" no site | **A**: admin e gerente | A |
| D4 | que login da Máxima o site usa | **A**: um usuário próprio do robô | A |
| D5 | print da tela quando dá erro na nuvem | **B**: sem print, só o código | B |

Texto literal (R-20261127-005437-alexandre, com a numeração do po: 2 a 6 = D1 a D5): "2 A / 3 A / 4 A / 5 A / 6 B".

Ainda com o Alexandre, pelo po, e na ordem do §9: as linhas do `donos.json`; o usuário da Máxima; o "autorizo" do `render.yaml`; os 2 segredos no painel; o "ok" do diagnóstico.

## 11. Consequências e riscos

- **A Máxima pode estranhar o IP do Render** (EUA, Oregon) e pedir confirmação a cada login, ou bloquear. É o maior risco [SUPOSIÇÃO]. O diagnóstico mostra isso antes de ligar a agenda; as saídas estão no §6.
- **Sessão única na Máxima** [SUPOSIÇÃO]: com o usuário próprio do robô, o PC e a nuvem usam logins diferentes. O aviso do §3.4 continua para quem usar o mesmo login.
- **Os termos de uso da Máxima** valem para a automação no Render como valem hoje no PC. Essa confirmação é do Alexandre.
- **Imagem Docker grande:** cada mudança no código das visitas refaz cerca de 2 GB de imagem. O `buildFilter` limita isso ao código da nuvem. Os minutos de build entram na franquia do Render [SUPOSIÇÃO].
- **Atraso até a tela:** da baixa ao farol do site, até cerca de 40 min (§4), e o robô do PC precisa estar ligado (§5.3).
- **Dois caminhos de baixa** (PC e nuvem) **com um só jeito de montar:** os arquivos e as funções são os mesmos (`depois_de_baixar`). A divergência fica limitada ao navegador e é vista na conferência de 5 dias.
- **Rede privada sem TLS:** o Bearer do cron trafega em claro dentro da rede privada do Render. É a rede da própria conta [SUPOSIÇÃO]; se o diagnóstico mostrar que o cron não alcança o `hostport`, a troca é para a URL pública com HTTPS (PR de governança).
- **Preços do Render não conferidos:** todos os valores em dólar são [SUPOSIÇÃO] e são confirmados no painel antes do "autorizo".
- **`bap_dados.VERSAO` fica em 27:** nada aqui toca o cache dos núcleos.
