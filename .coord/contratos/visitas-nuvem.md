# Contrato das visitas na nuvem — v1 (T-0045, ADR 0004)

- **Dono:** engenheiro-software. **Escrito em:** 27/11/2026.
- **Decisões de origem:** R-20261126-182728-alexandre (opção C) e R-20261127-005437-alexandre (2 A, 3 A, 4 A, 5 A, 6 B).
- **Quem usa:**
  - o cron job `bap-visitas-maxima` (modulo-robo, `nuvem/visitas/`);
  - o site `bap-central` (modulo-web, `web/app/`);
  - o robô do PC (modulo-robo, `bap_automation.sincronizar_visitas_web`);
  - os testes (agente testes).
- **Versão:** renomear ou tirar chave, rota, código de erro ou variável deste contrato = v2, com ADR e recado aos consumidores. Acrescentar chave opcional ou código novo = v1 (aviso aos consumidores).

## 1. Variáveis de ambiente (só os nomes; nenhum valor aqui)

| Serviço | Nome | Origem | Para quê |
|---|---|---|---|
| `bap-visitas-maxima` (cron) | `TZ` | `render.yaml`: `America/Manaus` | o "hoje", o `baixado_em` e o `HH-MM` do nome do Excel em Manaus |
| | `PYTHONUNBUFFERED` | `render.yaml`: `1` | o log aparece na hora no painel do Render |
| | `BAP_WEB_HOSTPORT` | `render.yaml`: `fromService` do `bap-central`, `property: hostport` | o endereço do site na rede privada (`http://<hostport>`) |
| | `BAP_VISITAS_TOKEN` | `render.yaml`: `fromService` do `bap-central`, `envVarKey: BAP_VISITAS_TOKEN` | o Bearer das rotas do cron (§3) |
| | `BAP_MAXIMA_USUARIO` | **segredo** (`sync: false`), criado pelo Alexandre no painel | o usuário próprio do robô na Máxima (decisão 5 A) |
| | `BAP_MAXIMA_SENHA` | **segredo** (`sync: false`), criado pelo Alexandre no painel | a senha desse usuário. **Só neste serviço** |
| `bap-central` (site) | `BAP_VISITAS_TOKEN` | `render.yaml`: `generateValue: true` (o Render sorteia) | confere o Bearer das rotas do cron |

- **Proibido no cron:** `DEBUG` que contenha `pw`, `PWDEBUG` e `PLAYWRIGHT_*` de trace ou vídeo. Com qualquer um deles, o `rodar.py` sai com `CONFIG_INSEGURA` antes de abrir o navegador.
- **Leitura dos segredos:** o `rodar.py` lê `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` com `os.environ.pop(...)` **antes** de abrir o Playwright (o driver, processo filho, não herda). A senha vai só no `fill` do login e em seguida vira `None`.
- **O robô do PC não ganha variável nova:** ele usa o `BAP_WEB_TOKEN` e a URL do site de hoje.

## 2. Constantes (no código, com teste; não são variáveis de ambiente)

| Nome | Valor | Onde | Regra |
|---|---|---|---|
| `AGENDA_HORA` | `06:00` (Manaus) | `nuvem/visitas/agenda.py` | decisão 3 A: a rodada automática baixa **ontem** |
| `RETENTATIVAS_AGENDA` | 06h30, 07h00, 07h30 | idem | só para `MAXIMA_FORA`, `SITE_FORA` e `RODADA_INTERROMPIDA` |
| `JANELA` | 06h00 a 21h59 (Manaus) | idem | fora dela o cron sai sem falar com a Máxima. O pedido do botão feito fora da janela espera as 06h00 |
| `CONCESSAO_MIN` | 10 | `web/app/visitas.py` | a concessão vence sem `progresso` em 10 min (RN-VIS-003) |
| `RODADA_MAX_MIN` | 45 | `nuvem/visitas/rodar.py` | conferido **no fim de cada dia**: passou, a rodada fecha `parcial` com `PARCIAL_TEMPO` |
| `RODADA_TETO_MIN` | 55 | idem | vigia (thread): aos 55 min liga o `parar` do `Robo`; aos 58 min, `os._exit(3)`. O site marca `RODADA_INTERROMPIDA` quando a concessão vence |
| `DIAGNOSTICO_MAX_MIN` | 15 | idem | o diagnóstico (§6) para aqui, com o que mediu |
| `PEDIDO_MAX_DIAS` | 7 | web e cron | período maior que 7 dias continua no PC (até 93) |
| `PEDIDO_MAX_RODADAS` | 3 | cron | um pedido que não cabe em 45 min continua nas voltas seguintes, até 3 rodadas |
| `HTTP_TEMPO_S` | 30 (15 no `GET /api/visitas/trabalho`) | cron | por requisição ao site |
| `HTTP_TENTATIVAS` | 3, com 30 s entre elas | cron | depois disso, `SITE_FORA` |
| `LOTE_GZ_MAX` | 8 MB | web | teto do corpo gzip do lote do dia |
| `ARQUIVO_MAX` | 2 MB | web | teto de cada Excel decodificado |
| `ARQUIVOS_MAX` | 60 | web | Excel por lote |
| `LOTE_GUARDA_DIAS` | 7 depois de confirmado; 30 sem confirmação | web | retenção em `/var/data/visitas/lotes/` |

Os tempos internos do `Robo` (login 45 s, `goto` 60 s, seletores de 40 s) continuam os do PC.

## 3. API do cron (Bearer `BAP_VISITAS_TOKEN`)

Regras comuns:
- `Authorization: Bearer <BAP_VISITAS_TOKEN>`, comparação em tempo constante (`hmac.compare_digest`). Token errado = 401. Este token **só** abre as rotas desta seção: não envia pacote, não lê edições, não lê lotes.
- O cron fala com `http://$BAP_WEB_HOSTPORT` (rede privada do Render).
- Corpos JSON em UTF-8, `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"))`.
- **Nenhum nome de vendedor ou de cliente vai na URL** (o Render registra o caminho). Datas na URL só como `AAAAMMDD`.
- `<id>` da rodada = `^R\d{8}T\d{6}$` (o início em Manaus).
- Datas e horas: ISO 8601 com `-04:00`.

### 3.1 `GET /api/visitas/trabalho`

```json
{"versao": 1, "agora": "2026-11-27T06:00:04-04:00",
 "agenda": "desligada",
 "diagnostico": {"estado": "pendente", "em": null, "codigo": null},
 "pausado": null,
 "pedido": {"id": "P20261127T091503", "de": "20261124", "ate": "20261127", "refazer": false,
            "pedido_em": "2026-11-27T09:15:03-04:00", "perfil": "gerente", "rodadas": 0},
 "indice": {"20261126": {"baixado_em": "2026-11-27T06:07:41-04:00", "erros_vendedor": 0, "refeito": false}},
 "falhas_seguidas": {"fase": null, "n": 0},
 "rodada_ativa": null}
```

| Chave | Tipo | Regra |
|---|---|---|
| `agenda` | `"desligada"` ou `"ligada"` | começa `desligada`. Só o admin liga, e só depois de um diagnóstico `ok` (§6) |
| `diagnostico.estado` | `"pendente"`, `"ok"` ou `"falhou"` | começa `pendente`. O admin pode pedir de novo (volta a `pendente`) |
| `pausado` | `null` ou `{"codigo": str, "desde": iso}` | RN-VIS-004. Com pausa, o cron só sai |
| `pedido` | `null` ou objeto | no máximo **1** pendente (o botão). `perfil` é só o perfil, nunca o usuário |
| `indice` | `{AAAAMMDD: {...}}` | os dias que a **nuvem** já entregou nos últimos 40 dias. `baixado_em` = o do lote mais novo do dia |
| `falhas_seguidas` | objeto | as rodadas seguidas que terminaram em `TELA_MUDOU` na mesma fase |
| `rodada_ativa` | `null` ou `{"id", "vence_em"}` | a concessão em vigor |

O cron decide com a função pura `deve_rodar(agora, trabalho) -> Motivo | None` (`nuvem/visitas/agenda.py`), nesta ordem:
1. `pausado` → `None`;
2. fora da `JANELA` → `None`;
3. `diagnostico.estado == "pendente"` → `"diagnostico"`;
4. `agenda == "desligada"` → `None` (o pedido do botão também espera a agenda ligada);
5. `pedido` → `"pedido"`;
6. `agora >= 06:00` e ontem fora do `indice` → `"agenda"` (com `RETENTATIVAS_AGENDA` depois de falha que permite nova tentativa);
7. dia com `erros_vendedor > 0` e `refeito == false` nos últimos 7 dias → `"retentativa"` (RN-VIS-005, uma vez);
8. senão → `None`.

Os dias da rodada saem de `visitas_nucleo.dias_a_baixar(indice, de, ate, hoje, refazer)` (função pura, modulo-rota). **Hoje** entra só pelo botão, e o dia fica aberto (RN-VIS-001).

### 3.2 `POST /api/visitas/rodada`

```json
{"motivo": "agenda", "pedido": null, "dias": ["20261126"], "versao_robo": "2026.11.27"}
```

| Resposta | Quando |
|---|---|
| 201 `{"id": "R20261127T060012", "vence_em": iso}` | concessão dada (RN-VIS-003) |
| 409 `{"erro": "rodada ativa", "id": str}` | já há concessão em vigor. O cron sai sem erro |
| 423 `{"erro": "pausado", "codigo": str}` | pausa gravada depois do `trabalho` |
| 400 | corpo fora do formato, `motivo` fora da lista, mais de `PEDIDO_MAX_DIAS` dias (o diagnóstico leva 1) |

### 3.3 `POST /api/visitas/rodada/<id>/progresso`

```json
{"fase": "grade", "dia": "20261126", "feitos": 7, "total": 15}
```

- Renova a concessão por `CONCESSAO_MIN`. O cron manda a cada vendedor e a cada troca de fase.
- 200 `{"vence_em": iso}` · 404 `{"erro": "rodada desconhecida"}` · 409 `{"erro": "concessão vencida"}`. Com 404 ou 409, o cron para no fim do vendedor e sai sem `fim`.
- `fase` ∈ `login`, `inicio`, `maxgestao`, `menu`, `filtros`, `grade`, `espelho`, `salvar`, `envio`.

### 3.4 `POST /api/visitas/rodada/<id>/dia/<AAAAMMDD>` (o lote do dia)

- **Cabeçalhos:** `Content-Type: application/json`; `Content-Encoding: gzip`; `X-BAP-SHA256: <sha256 hex dos bytes JSON descomprimidos>`.
- **Quando:** o cron manda cada dia **assim que ele termina** (`Robo.ao_fechar_dia`), não no fim da rodada. Dia sem nenhum Excel não é mandado.
- **Corpo:**

```json
{"versao": 1, "rodada": "R20261127T060012", "dia": "20261126",
 "baixado_em": "2026-11-27T06:07:41-04:00",
 "vendedores": 15, "erros_vendedor": 0,
 "equipe": {"filiais": {}, "supervisores": {}, "representantes": {}},
 "extras": {"<nome_chave>": {"gps": true, "versao": "<versão do app>"}},
 "arquivos": [{"pasta": "<nome_limpo>", "nome": "VISITA-<nome_limpo>-26-11-2026-06-07.xlsx",
               "sha256": "<hex do Excel>", "bytes": 26123, "b64": "<base64 do Excel>"}]}
```

| Chave | Regra |
|---|---|
| `baixado_em` | a hora em que o **último Excel do dia** foi salvo na nuvem. É ela que fecha o dia (RN-VIS-001), não a hora da importação |
| `vendedores`, `erros_vendedor` | quantos a grade mostrou e quantos falharam. Só números |
| `equipe` | os 3 dicionários que o `Robo._ler_equipe` lê nos filtros, no formato dos argumentos de `visitas_nucleo.gravar_equipe_maxima` |
| `extras` | o que `Robo` devolve em `extras` (chave = `visitas_nucleo.nome_chave`), para `visitas_nucleo.montar_dia` |
| `arquivos[].pasta` | `visitas_maxima.nome_limpo(nome)`; sem `/`, `\`, `..` nem caractere de controle |
| `arquivos[].nome` | casa com `visitas_nucleo._RX_ARQ_ANALITICO`, começa com `VISITA-<pasta>-` e a data `DD-MM-AAAA` é o `<AAAAMMDD>` da URL |

- **O site confere** (função pura `validar_lote(dia_url, corpo) -> list[str]`, modulo-web): as regras da tabela; `dia` igual ao da URL; dia válido e não futuro; até `ARQUIVOS_MAX` arquivos; cada Excel até `ARQUIVO_MAX` e com o `sha256` certo. O site **nunca abre** o Excel e **nunca** o serve ao navegador.
- **Idempotência:** o mesmo `<id>` + dia + `X-BAP-SHA256` devolve o mesmo `seq`, sem gravar de novo.

| Resposta | Quando |
|---|---|
| 200 `{"ok": true, "seq": int, "arquivos": int}` | gravado em `/var/data/visitas/lotes/<seq>.json.gz` (por `.tmp` + `os.replace`) |
| 400 | dia mal formado, corpo que não é JSON |
| 401 | token |
| 404 | rodada desconhecida |
| 409 | concessão vencida |
| 413 `{"erro": "lote grande demais"}` | acima de `LOTE_GZ_MAX`, de `ARQUIVO_MAX` ou de `ARQUIVOS_MAX` |
| 415 | `Content-Type` ou `Content-Encoding` errado |
| 422 `{"erro": "sha256"}` ou `{"erro": "esquema inválido", "detalhes": [...]}` | até 10 detalhes, **sem nome**: só a chave e o índice (`arquivos[3].nome`) |

### 3.5 `POST /api/visitas/rodada/<id>/fim`

```json
{"status": "parcial", "codigo": "PARCIAL_VENDEDOR", "fase": null,
 "dias_ok": ["20261126"], "dias_faltando": [], "erros_vendedor": 1,
 "duracao_s": 412, "pico_mb": 618.0, "medidas": null}
```

- `status` ∈ `ok`, `parcial`, `erro`. `codigo` da tabela do §5. `fase` quando o código pede.
- `medidas` só no diagnóstico (§6); `null` nas outras.
- 200 `{"ok": true, "pausado": bool}`. O site grava em `rodadas.jsonl` (só acréscimo), solta a concessão e aplica a pausa do §5. O `fim` repetido responde igual.

## 4. API do robô do PC (Bearer `BAP_WEB_TOKEN`) e tela

### 4.1 `GET /api/visitas/lotes?desde=<seq>`

```json
{"epoca": "e7c1…", "ate": 42,
 "lotes": [{"seq": 41, "dia": "20261126", "rodada": "R20261127T060012",
            "baixado_em": "2026-11-27T06:07:41-04:00", "arquivos": 15, "bytes_gz": 402311, "sha256": "<hex>"}]}
```

- No máximo 20 lotes por resposta, em ordem de `seq`. `epoca` muda quando o disco do site recomeça: o robô volta a `desde=0` e o registro `.jsonl` do PC impede gravar duas vezes.
- O robô novo trata o **404 da web antiga** como "sem visitas da nuvem" e segue.

### 4.2 `GET /api/visitas/lote/<seq>`

- Devolve o corpo do §3.4 como foi gravado (`Content-Encoding: gzip`, `X-BAP-SHA256`). 404 quando saiu pela retenção.

### 4.3 `POST /api/visitas/lotes/confirmar`

```json
{"epoca": "e7c1…", "resultado": {"41": "importado", "40": "recusado:sha256"}}
```

- `recusado:<motivo>` ∈ `sha256`, `nome`, `pasta`, `dia`. O site marca o dia como **não entregue** no `indice` (a nuvem baixa de novo). 200 `{"ok": true}`.

### 4.4 `GET /api/visitas/estado`

```json
{"rodada_ativa": true, "fase": "grade", "desde": "2026-11-27T09:20:00-04:00", "pausado": false, "agenda": "ligada"}
```

- Para o aviso do botão do PC: "O site está baixando agora; baixar aqui também pode derrubar a sessão da Máxima. Continuar?"

### 4.5 Importação no PC: `bap_automation.sincronizar_visitas_web(raiz, base, token, log) -> dict`

- Chamada na volta de 30 min, **antes de montar o pacote**, no ponto do `sincronizar_edicoes_web`. Nunca levanta exceção e nunca derruba a rodada.
- Passos e regras: ADR 0004, §5.1 (RN-VIS-001 e RN-VIS-002). Grava o Excel no `ANALITICO` por `.tmp` + `os.replace`; mesmo `sha256` = pula; nome que já existe com outro conteúdo = sufixo `-2`, `-3`… (`visitas_maxima.arquivo_analitico`). **Nunca sobrescreve nem apaga.**
- Fim comum: `visitas_maxima.depois_de_baixar(raiz, log)`, a mesma função do botão do PC.
- Registro: `RELATORIOS/_VISITAS_WEB/IMPORTADOS_VISITAS_WEB.jsonl`, só acréscimo, uma linha por lote: `{"seq", "epoca", "dia", "arquivos", "status", "em"}`. Sem nome.
- Devolve `{"lotes": int, "arquivos": int, "dias": [AAAAMMDD], "erro": str | None}`.

### 4.6 Tela (sessão e perfil; corte no servidor, ADR 0001, §4.5)

| Rota | Perfis | O quê |
|---|---|---|
| `GET /visitas/atualizar` | todos os que veem o Farol de Visita | estado, última rodada (código e texto do §5), lotes à espera do PC, histórico de 10 rodadas |
| `POST /visitas/atualizar` `{de, ate}` | `admin`, `gerente` (decisão 4 A) | grava o pedido. Padrão: os dias abertos até hoje; no máximo 7 |
| `POST /visitas/refazer` `{de, ate}` | `admin` | o mesmo, com `refazer: true` (baixa de novo dia fechado) |
| `POST /visitas/retomar` | `admin` | tira a pausa (RN-VIS-004) |
| `POST /visitas/diagnostico` | `admin` | volta o diagnóstico a `pendente` |
| `POST /visitas/agenda` `{ligar}` | `admin` | liga ou desliga a agenda. Ligar só com diagnóstico `ok` |

- Os outros perfis recebem 403, com teste por perfil.
- `/saude` ganha `visitas: {"agenda", "diagnostico", "ultima_rodada", "status", "codigo", "pausado", "lotes_a_importar"}`, sem dado pessoal.

## 5. Códigos de erro (decisão 6 B: sem print de tela, só o código)

A nuvem **não tira print** em nenhum caso. O código e a fase bastam; a investigação com imagem é feita no PC, com "Mostrar o navegador". A mensagem crua da Máxima **nunca** é copiada para o código, o log ou o site.

| Código | `status` | Quando | Depois (quem decide: o site, no `fim`) | Texto no site |
|---|---|---|---|---|
| `OK` | ok | todos os dias e vendedores vieram | — | "Atualizado às HHhMM." |
| `NADA_A_FAZER` | ok | a concessão veio, mas `dias_a_baixar` voltou vazio | — | (não aparece) |
| `PARCIAL_VENDEDOR` | parcial | algum vendedor falhou; os outros vieram | nova tentativa uma vez (RN-VIS-005) | "N Excel com erro (DD/MM)." Nome do vendedor só na tela, para admin e gerente, a partir do lote |
| `PARCIAL_TEMPO` | parcial | passou de `RODADA_MAX_MIN` no fim de um dia | o resto na volta seguinte, até `PEDIDO_MAX_RODADAS` | "Parte dos dias veio; o resto vem na próxima volta." |
| `MAXIMA_SENHA` | erro | a Máxima recusou usuário ou senha | **pausa** (RN-VIS-004), sem segunda tentativa | "A Máxima recusou o usuário ou a senha. Só o Alexandre troca no painel do Render; depois, o admin clica em Retomar." |
| `MAXIMA_CONFIRMACAO` | erro | a Máxima pediu código por SMS ou e-mail, confirmação de novo dispositivo, aceite de termo ou troca de senha | **pausa** | "A Máxima pediu uma confirmação que o site não faz sozinho. As atualizações do site estão pausadas. Use o Atualizar visitas do PC; o admin retoma aqui depois." |
| `MAXIMA_CAPTCHA` | erro | apareceu captcha (iframe ou elemento conhecido) | **pausa** | o mesmo texto do `MAXIMA_CONFIRMACAO` |
| `MAXIMA_BLOQUEIO` | erro | conta bloqueada, acesso negado ou HTTP 403 na página de login | **pausa** | "A Máxima bloqueou o acesso vindo do site. Use o botão do PC; o caso vai ao Alexandre." |
| `MAXIMA_FORA` | erro | tempo esgotado no `goto` do login, ou HTTP 5xx | agenda: `RETENTATIVAS_AGENDA`; botão: o pedido sai da fila | "A Máxima não respondeu. Tentamos de novo às HHhMM." / "Tente mais tarde." |
| `TELA_MUDOU` | erro | `ErroRobo` numa fase (`fase` obrigatória) | 2 rodadas seguidas na mesma fase **pausam a agenda** | "A tela da Máxima mudou (etapa: <fase>). Os dias que já vieram estão salvos. Use o botão do PC até a correção." |
| `NAVEGADOR_FALHOU` | erro | o Chromium não abriu ou caiu (`Target closed`, falta de memória) | volta seguinte; 2 seguidas aparecem no `/saude` | "O navegador do site parou. O que veio está salvo." |
| `SITE_RECUSOU` | parcial | o site respondeu 413 ou 422 a um lote | o dia fica fora do `indice` e é baixado de novo uma vez | "Um dia não foi aceito pelo site (DD/MM)." |
| `SITE_FORA` | — | o cron não fala com o site depois de `HTTP_TENTATIVAS` | só no log do Render; o site vê `RODADA_INTERROMPIDA` | — |
| `RODADA_INTERROMPIDA` | erro | **gravado pelo site**: a concessão venceu sem `fim` | o que falta na volta seguinte | "A rodada parou sem terminar (memória ou tempo do serviço). O que veio está salvo." |
| `CONFIG_FALTANDO` | erro | falta `BAP_MAXIMA_USUARIO`, `BAP_MAXIMA_SENHA`, `BAP_VISITAS_TOKEN` ou `BAP_WEB_HOSTPORT` | sai sem abrir o navegador; cada volta repete (custa segundos) | "Faltam as variáveis do serviço de visitas no Render." (o nome da variável só no log do Render) |
| `CONFIG_INSEGURA` | erro | `DEBUG` com `pw`, `PWDEBUG` ou trace ligado | sai sem abrir o navegador | "O serviço de visitas está com depuração ligada e não roda assim." |
| `ERRO_INTERNO` | erro | exceção não prevista (`fase` obrigatória) | volta seguinte | "Erro inesperado (etapa: <fase>)." No log, só o nome da classe da exceção, nunca a mensagem |

- **Pausa** = `pausado` gravado; o cron sai sem tocar na Máxima até o "Retomar" do admin. O botão do PC continua funcionando.
- **Saída do processo:** 0 para `ok`, `parcial`, sem trabalho e pausado; 1 para `erro`. Assim o painel do Render marca a execução falhada.
- **Log do cron** (o único lugar visível no Render): uma linha por evento, `evento=<nome> fase=<fase> dia=<AAAAMMDD> n=<int> codigo=<CÓDIGO>`. Sem nome de vendedor ou cliente, sem usuário, sem senha, sem URL com `PWE=`. Um filtro final troca o usuário e a senha por `***` se aparecerem.

### 5.1 A Máxima pede confirmação ou captcha: a regra

- A detecção é a função pura `classificar_login(url, texto, tem_captcha, http_status) -> str | None` (modulo-robo), chamada depois do "Entrar":
  - continua no `/login` com mensagem de erro de credencial → `MAXIMA_SENHA`;
  - captcha → `MAXIMA_CAPTCHA`;
  - continua no `/login`, ou foi para uma página de verificação, com texto de código, confirmação, dispositivo, termo ou troca de senha → `MAXIMA_CONFIRMACAO`;
  - texto de bloqueio ou HTTP 403 → `MAXIMA_BLOQUEIO`;
  - saiu do `/login` → `None` (segue).
- **Nunca** tenta resolver captcha, nunca repete o login, nunca espera um humano. Fecha o navegador, manda o `fim` e sai.
- Se o diagnóstico (§6) der `MAXIMA_CONFIRMACAO`, `MAXIMA_CAPTCHA` ou `MAXIMA_BLOQUEIO`, a agenda **não é ligada** e o caso vai ao Alexandre numa ADR nova: liberar na Máxima os IPs de saída do Render, ou voltar à opção A do po (senha no cofre do notebook do robô).

## 6. Diagnóstico (antes de ligar a agenda)

- **Quando:** na primeira volta do cron com as variáveis presentes e `diagnostico.estado == "pendente"`. O admin pode pedir de novo pela tela.
- **O quê:** login, maxGestão, filtros e **ontem** com **2 vendedores**, até `DIAGNOSTICO_MAX_MIN`. **Não manda lote** (nenhum dado sai do contêiner).
- **`medidas` no `fim`:**

```json
{"tempos_s": {"login": 21.4, "maxgestao": 9.8, "filtros": 30.2, "vendedor": [44.0, 51.3]},
 "pico_mb": 612.0, "fonte_pico": "cgroup", "chromium": "<versão>",
 "pediu_confirmacao": false, "captcha": false,
 "espelho_colunas": {"cnpj": false, "telefone": false, "endereco": true}}
```

  - `pico_mb`: `/sys/fs/cgroup/memory.peak` (cgroup v2); sem ele, `memory.max_usage_in_bytes` (v1); sem os dois, `null` com `fonte_pico: "indisponivel"`.
  - `espelho_colunas`: só **se** o cabeçalho do Espelho tem a coluna (verdadeiro ou falso), lido no próprio contêiner, sem copiar valor.
- **Resultado:** uma linha `DIAGNOSTICO codigo=... pico_mb=... login_s=... vendedor_s=... confirmacao=nao captcha=nao` no log do Render e o mesmo na tela do admin. Com `OK`, o `diagnostico.estado` vira `ok`; a agenda continua `desligada` até o admin ligar, depois do "ok" do Alexandre.
- **Plano do serviço:** com `pico_mb` abaixo de 350, o cron pode descer para o `starter` (PR de governança). Acima de 1.600, sobe para o `pro` [SUPOSIÇÃO: o plano de 4 GB do cron].

## 7. Disco do site (`/var/data/visitas/`)

| Arquivo | Regra |
|---|---|
| `estado.json` | `epoca`, `agenda`, `diagnostico`, `pausado`, `pedido`, `rodada_ativa`, `falhas_seguidas`, `indice`, `seq`. Gravação atômica |
| `pedidos.jsonl` | só acréscimo: `{id, de, ate, refazer, perfil, em}` (perfil, nunca o usuário) |
| `rodadas.jsonl` | só acréscimo: o `fim` de cada rodada, mais `RODADA_INTERROMPIDA` |
| `lotes/<seq>.json.gz` | o corpo do §3.4; sai `LOTE_GUARDA_DIAS` depois. O não confirmado em 30 dias sai com aviso no `/saude` |

Cerca de 15 MB por mês, dentro do disco de 1 GB.

## 8. Ordem de publicação

1. Este contrato e a ADR 0004.
2. **Web antes** (modulo-web): §3, §4.1 a §4.4, §4.6, §7 e o `/saude`, com a versão nova do site. Sobe com o merge (ADR 0001, adendo 4).
3. **Cron depois** (modulo-robo): `nuvem/visitas/`. Ele só passa a existir no Render com o PR de governança do `render.yaml`, que entra depois do item 2 e do código do cron no `main`.
4. **Robô do PC** (modulo-robo): §4.5, pela rotina diária (ADR 0002), só com o `/saude` na versão do `main`.
