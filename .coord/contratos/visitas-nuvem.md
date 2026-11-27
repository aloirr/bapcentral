# Contrato das visitas na nuvem — v1 (T-0045, ADR 0004)

- **Dono:** engenheiro-software. **Escrito em:** 27/11/2026; revisado no PR #137, antes do merge e de qualquer consumidor.
- **Papel:** este contrato diz **como** (rotas, corpos, constantes, códigos, textos). O **porquê** e as decisões D1 a D5 estão na ADR 0004 (§0). A ordem de publicação está na ADR 0004, §9.
- **Quem usa:**
  - o cron job `bap-visitas-maxima` (modulo-robo, `nuvem/visitas/`);
  - o site `bap-central` (modulo-web, `web/app/`);
  - o robô do PC (modulo-robo, `bap_automation.sincronizar_visitas_web`);
  - o `visitas_nucleo` (modulo-rota: as funções puras citadas aqui);
  - os testes (agente testes).
- **Versão:** renomear ou tirar chave, rota, código de erro, coluna permitida ou variável deste contrato = v2, com ADR e recado aos consumidores. Acrescentar chave opcional ou código novo = v1 (aviso aos consumidores). **Acrescentar coluna à lista de permitidas (§3.6) = v2**, porque é decisão de dado pessoal do Alexandre.

## 1. Variáveis de ambiente (só os nomes; nenhum valor aqui)

| Serviço | Nome | Origem | Para quê |
|---|---|---|---|
| `bap-visitas-maxima` (cron) | `TZ` | `render.yaml`: `America/Manaus` | o "hoje", o `baixado_em` e o `HH-MM` do nome do Excel em Manaus |
| | `PYTHONUNBUFFERED` | `render.yaml`: `1` | o log aparece na hora no painel do Render |
| | `BAP_WEB_HOSTPORT` | `render.yaml`: `fromService` do `bap-central`, `property: hostport` | o endereço do site na rede privada (`http://<hostport>`) |
| | `BAP_VISITAS_TOKEN` | `render.yaml`: `fromService` do `bap-central`, `envVarKey: BAP_VISITAS_TOKEN` | o Bearer das rotas do cron (§3) |
| | `BAP_MAXIMA_USUARIO` | **segredo** (`sync: false`), criado pelo Alexandre no painel | o usuário próprio do robô na Máxima (D4) |
| | `BAP_MAXIMA_SENHA` | **segredo** (`sync: false`), criado pelo Alexandre no painel | a senha desse usuário. **Só neste serviço** |
| `bap-central` (site) | `BAP_VISITAS_TOKEN` | `render.yaml`: `generateValue: true` (o Render sorteia) | confere o Bearer das rotas do cron |

- **Proibido no cron** (a única lista; os testes conferem as duas partes):
  - no ambiente: `DEBUG` que contenha `pw`, `PWDEBUG` e `PLAYWRIGHT_*` de trace ou vídeo. Com qualquer um, o `rodar.py` sai com `CONFIG_INSEGURA` antes de abrir o navegador;
  - no código: trace, vídeo, HAR, `page.on("console")` e print de tela (D5).
- **Leitura dos segredos:** o `rodar.py` lê `BAP_MAXIMA_USUARIO` e `BAP_MAXIMA_SENHA` com `os.environ.pop(...)` **antes** de abrir o Playwright (o driver, processo filho, não herda). A senha vai só no `fill` do login e em seguida vira `None`.
- **O robô do PC não ganha variável nova:** ele usa o `BAP_WEB_TOKEN` e a URL do site de hoje.

## 2. Constantes (no código, com teste; não são variáveis de ambiente)

| Nome | Valor | Onde | Regra |
|---|---|---|---|
| `AGENDA_HORA` | `06:00` (Manaus) | `nuvem/visitas/agenda.py` | D2: a rodada automática baixa **ontem** |
| `RETENTATIVAS_AGENDA` | 06h30, 07h00, 07h30 | idem | a 2ª, a 3ª e a 4ª tentativa da agenda, só depois de um código de `NOVA_TENTATIVA` |
| `NOVA_TENTATIVA` | `MAXIMA_FORA`, `TELA_MUDOU`, `NAVEGADOR_FALHOU`, `SITE_RECUSOU`, `RODADA_INTERROMPIDA`, `PARCIAL_TEMPO`, `ERRO_INTERNO` | idem | os códigos que deixam tentar de novo, dentro do teto do dia |
| `TENTATIVAS_DIA` | `agenda` 4, `pedido` 3, `retentativa` 1, `diagnostico` 2 | `web/app/visitas.py` e `agenda.py` | teto por motivo no dia de Manaus (RN-VIS-008) |
| `LOGINS_DIA_MAX` | 8 | idem | teto da soma dos motivos no dia: o que vier primeiro trava (RN-VIS-008) |
| `JANELA` | 06h00 a 21h59 (Manaus) | `agenda.py` | fora dela o cron sai sem falar com a Máxima. O pedido do botão feito fora da janela espera as 06h00 |
| `CONCESSAO_MIN` | 10 | `web/app/visitas.py` | a concessão vence sem `progresso` em 10 min (RN-VIS-004) |
| `RODADA_MAX_MIN` | 45 | `nuvem/visitas/rodar.py` | conferido **no fim de cada dia**: passou, a rodada fecha com `PARCIAL_TEMPO` |
| `RODADA_TETO_MIN` | 55 | idem | vigia (thread): liga o `parar` do `Robo` |
| `RODADA_MATA_MIN` | 58 | idem | vigia: `os._exit(1)` (saída de erro, §5). O site marca `RODADA_INTERROMPIDA` quando a concessão vence |
| `DIAGNOSTICO_MAX_MIN` | 15 | idem | o diagnóstico (§6) para aqui, com o que mediu |
| `PEDIDO_MAX_DIAS` | 7 | web e cron | período maior que 7 dias continua no PC (até 93) |
| `PEDIDO_MAX_RODADAS` | 3 | web e cron | um pedido que não cabe em 45 min continua nas voltas seguintes, até 3 rodadas |
| `FECHADOS_PC_DIAS` | 40 | robô do PC e web | a janela do `fechados_pc` (§4.3) e do `indice` (§3.1) |
| `HTTP_TEMPO_S` | 30 (15 no `GET /api/visitas/trabalho`) | cron | por requisição ao site |
| `HTTP_TENTATIVAS` | 3, com 30 s entre elas | cron | depois disso, `SITE_FORA` |
| `LOTE_GZ_MAX` | 8 MB | web | teto do corpo gzip do lote do dia |
| `ARQUIVO_MAX` | 2 MB | web | teto de cada Excel decodificado |
| `ARQUIVOS_MAX` | 60 | web | Excel por lote |
| `LOTE_BRUTO_MAX` | 24 MB | web | teto do JSON do lote já descomprimido (trava da "bomba" de gzip) |
| `DESCOMPRESSAO_MAX` | 50 MB | web | teto total do que a conferência do site lê dos Excel (§3.4), por lote e por arquivo |
| `ZIP_MEMBROS_MAX` | 64 | web | membros do zip de cada Excel na conferência |
| `LOTE_GUARDA_DIAS` | 7 depois de confirmado; 30 sem confirmação | web | retenção em `/var/data/visitas/lotes/` |

Os tempos internos do `Robo` (login 45 s, `goto` 60 s, seletores de 40 s) continuam os do PC.

**Processo e navegador na nuvem:**
- o `tini` é o PID 1 do contêiner (`ENTRYPOINT` do `Dockerfile`): recolhe os processos do Chromium que sobrarem e repassa os sinais ao Python;
- o `rodar.py` trata o `SIGTERM` do Render (deploy ou parada manual) ligando o `parar` do `Robo`, como o vigia aos `RODADA_TETO_MIN`. O que não fechar antes do fim do processo vira `RODADA_INTERROMPIDA` no site;
- o Chromium abre com `--disable-dev-shm-usage` (o `/dev/shm` do contêiner é pequeno; sem isso, a aba cai e aparece `NAVEGADOR_FALHOU`).

## 3. API do cron (Bearer `BAP_VISITAS_TOKEN`)

Regras comuns:
- `Authorization: Bearer <BAP_VISITAS_TOKEN>`, comparação em tempo constante (`hmac.compare_digest`). Token errado = 401 em toda rota desta seção. Este token **só** abre as rotas desta seção: não envia pacote, não lê edições, não lê lotes.
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
 "indice": {"20261126": {"baixado_em": "2026-11-27T06:07:41-04:00", "origem": "nuvem",
                         "erros_vendedor": 0, "refeito": false}},
 "tentativas_hoje": {"dia": "20261127", "total": 1,
                     "por_motivo": {"agenda": {"n": 1, "ultima_em": "2026-11-27T06:00:12-04:00",
                                               "codigo": "MAXIMA_FORA"}}},
 "falhas_seguidas": {"fase": null, "n": 0},
 "fechados_pc_em": "2026-11-27T05:31:00-04:00",
 "rodada_ativa": null}
```

| Chave | Tipo | Regra |
|---|---|---|
| `agenda` | `"desligada"` ou `"ligada"` | começa `desligada`. Só o admin liga, e só com diagnóstico `ok` (§6) **e** `fechados_pc_em` nas últimas 24 h (o robô do PC novo no ar, §4.3) |
| `diagnostico.estado` | `"pendente"`, `"ok"` ou `"falhou"` | começa `pendente`. O admin pode pedir de novo (volta a `pendente`) |
| `pausado` | `null` ou `{"codigo": str, "desde": iso}` | RN-VIS-005 e RN-VIS-007. Com pausa, o cron só sai |
| `pedido` | `null` ou objeto | no máximo **1** pendente (o botão). `perfil` é só o perfil, nunca o usuário |
| `indice` | `{AAAAMMDD: {...}}` | **o índice único** dos dias baixados nos últimos `FECHADOS_PC_DIAS` dias, pela nuvem (lote importado) ou pelo PC (`fechados_pc`, §4.3). `baixado_em` = o maior dos dois (`visitas_nucleo.juntar_baixado`, RN-VIS-002); `origem` = de quem é esse maior. **No empate de hora, vale a nuvem** (`origem: "nuvem"`). A web tem um espelho mínimo dessa função (`web/app/visitas.juntar_baixado`), porque o Render publica só `web/`; um teste de paridade na raiz (`tests/`) confere que as duas dão o mesmo resultado, com empate incluído. `erros_vendedor` e `refeito` só valem para `origem: "nuvem"` |
| `tentativas_hoje` | objeto | as concessões dadas hoje (Manaus), por motivo: `n`, `ultima_em` e o `codigo` do `fim` (ou `RODADA_INTERROMPIDA`). O site zera quando o `dia` muda (RN-VIS-008) |
| `falhas_seguidas` | objeto | as rodadas seguidas que terminaram em `TELA_MUDOU` na mesma fase |
| `fechados_pc_em` | `null` ou iso | o último `fechados_pc` recebido do robô do PC |
| `rodada_ativa` | `null` ou `{"id", "vence_em"}` | a concessão em vigor |

O cron decide com a função pura `deve_rodar(agora, trabalho) -> Motivo | None` (`nuvem/visitas/agenda.py`), nesta ordem:
1. `pausado` → `None`;
2. fora da `JANELA` → `None`;
3. `tentativas_hoje.total >= LOGINS_DIA_MAX` → `None` (a tela mostra `TETO_DIA`);
4. `diagnostico.estado == "pendente"` e `diagnostico` abaixo do teto → `"diagnostico"`;
5. `agenda == "desligada"` ou `diagnostico.estado != "ok"` → `None` (o pedido do botão também espera; a agenda ligada só volta a rodar com o diagnóstico limpo);
6. `pedido`, com `pedido.rodadas < PEDIDO_MAX_RODADAS` e `pedido` abaixo do teto → `"pedido"`;
7. ontem não fechado no `indice` e `agenda` abaixo do teto:
   - `n == 0` e `agora >= AGENDA_HORA` → `"agenda"`;
   - `n` de 1 a 3, `codigo` em `NOVA_TENTATIVA` e `agora >= RETENTATIVAS_AGENDA[n - 1]` → `"agenda"`;
8. dia com `erros_vendedor > 0` e `refeito == false` nos últimos 7 dias, e `retentativa` abaixo do teto → `"retentativa"` (RN-VIS-006);
9. senão → `None`.

"Abaixo do teto" = `tentativas_hoje.por_motivo[motivo].n < TENTATIVAS_DIA[motivo]`. Os dias da rodada saem de `visitas_nucleo.dias_a_baixar(indice, de, ate, hoje, refazer)` (função pura, modulo-rota). **Hoje** entra só pelo botão, e o dia fica aberto (RN-VIS-002).

### 3.2 `POST /api/visitas/rodada`

```json
{"motivo": "agenda", "pedido": null, "dias": ["20261126"], "versao_robo": "2026.11.27"}
```

- O cron só pede concessão com `dias` não vazio.
- **Na concessão (201), o site conta a tentativa** em `tentativas_hoje` (cada concessão é um login na Máxima, mesmo que a rodada caia depois). Com `motivo: "retentativa"`, o site marca `refeito: true` nos dias da rodada **já na concessão**: a retentativa é uma só, com sucesso ou falha (RN-VIS-006).

| Resposta | Quando |
|---|---|
| 201 `{"id": "R20261127T060012", "vence_em": iso}` | concessão dada (RN-VIS-004) |
| 409 `{"erro": "rodada ativa", "id": str}` | já há concessão em vigor. O cron sai sem erro |
| 423 `{"erro": "pausado", "codigo": str}` | pausa gravada depois do `trabalho` |
| 429 `{"erro": "teto do dia", "motivo": str}` | o motivo ou a soma chegou ao teto (RN-VIS-008). O cron sai sem erro |
| 400 | corpo fora do formato, `motivo` fora da lista, `dias` vazio, mais de `PEDIDO_MAX_DIAS` dias (o diagnóstico leva 1) |

### 3.3 `POST /api/visitas/rodada/<id>/progresso`

```json
{"fase": "grade", "dia": "20261126", "feitos": 7, "total": 15}
```

- Renova a concessão por `CONCESSAO_MIN`. O cron manda a cada vendedor e a cada troca de fase.
- 200 `{"vence_em": iso}` · 404 `{"erro": "rodada desconhecida"}` · 409 `{"erro": "concessão vencida"}`. Com 404 ou 409, o cron para no fim do vendedor e sai sem `fim`.
- `fase` ∈ `login`, `inicio`, `maxgestao`, `menu`, `filtros`, `grade`, `espelho`, `filtro`, `salvar`, `envio`.

### 3.4 `POST /api/visitas/rodada/<id>/dia/<AAAAMMDD>` (o lote do dia)

- **Cabeçalhos:** `Content-Type: application/json`; `Content-Encoding: gzip`; `X-BAP-SHA256: <sha256 hex dos bytes JSON descomprimidos>`.
- **Quando:** o cron manda cada dia **assim que ele termina** (`Robo.ao_fechar_dia`) e **só depois do filtro do §3.6 limpo**, não no fim da rodada. Dia sem nenhum Excel não é mandado.
- **Corpo:**

```json
{"versao": 1, "rodada": "R20261127T060012", "dia": "20261126",
 "baixado_em": "2026-11-27T06:07:41-04:00",
 "vendedores": 15, "erros_vendedor": 0,
 "equipe": {"filiais": {}, "supervisores": {}, "representantes": {}},
 "extras": {"<nome_chave>": {"gps": true, "versao": "<versão do app>"}},
 "arquivos": [{"pasta": "<nome_limpo>", "nome": "VISITA-<nome_limpo>-26-11-2026-06-07.xlsx",
               "sha256": "<hex do Excel filtrado>", "bytes": 21877, "b64": "<base64 do Excel filtrado>"}]}
```

| Chave | Regra |
|---|---|
| `baixado_em` | a hora em que o **último Excel do dia** foi salvo na nuvem. É ela que fecha o dia (RN-VIS-002), não a hora da importação |
| `vendedores`, `erros_vendedor` | quantos a grade mostrou e quantos falharam. Só números |
| `equipe` | os 3 dicionários que o `Robo._ler_equipe` lê nos filtros, no formato dos argumentos de `visitas_nucleo.gravar_equipe_maxima` |
| `extras` | o que `Robo` devolve em `extras` (chave = `visitas_nucleo.nome_chave`), para `visitas_nucleo.montar_dia` |
| `arquivos[].b64` | **o Excel filtrado do §3.6**, nunca o que a Máxima entregou |
| `arquivos[].pasta` | `visitas_maxima.nome_limpo(nome)`; sem `/`, `\`, `..` nem caractere de controle |
| `arquivos[].nome` | casa com `visitas_nucleo._RX_ARQ_ANALITICO`, começa com `VISITA-<pasta>-` e a data `DD-MM-AAAA` é o `<AAAAMMDD>` da URL |

- **O site confere** (função pura `validar_lote(dia_url, corpo) -> list[str]`, modulo-web): as regras da tabela; `dia` igual ao da URL; dia válido e não futuro; até `ARQUIVOS_MAX` arquivos; cada Excel até `ARQUIVO_MAX` e com o `sha256` certo. O site **nunca abre o Excel no Excel** (nem em biblioteca de planilha) e **nunca** o serve ao navegador.
- **Conferência no site** (defesa extra contra dado pessoal, depois da do cron no §3.6): o site lê **só o texto e os números das células** de cada Excel, direto do zip/XML (`sharedStrings.xml` e as planilhas, biblioteca padrão), e aplica neles a mesma varredura do §3.6.
  - O que ele lê vai até `DESCOMPRESSAO_MAX` no lote e em cada arquivo, com até `ZIP_MEMBROS_MAX` membros por Excel. Passou, ele para na hora e responde 413 `{"erro": "lote grande demais", "codigo": "DESCOMPRESSAO_TETO"}`.
  - Achou dado pessoal ou coluna fora da lista: 422 `{"erro": "dado pessoal", "detalhes": [...]}` (até 10, só o índice do arquivo e o tipo ou a coluna, **nunca o valor**). O lote do dia não é gravado, e o site grava a pausa `DADO_PESSOAL` (RN-VIS-007).
- **Idempotência:** o mesmo `<id>` + dia + `X-BAP-SHA256` devolve o mesmo `seq`, sem gravar de novo.

| Resposta | Quando |
|---|---|
| 200 `{"ok": true, "seq": int, "arquivos": int}` | gravado em `/var/data/visitas/lotes/<seq>.json.gz` (por `.tmp` + `os.replace`) |
| 400 | dia mal formado, corpo que não é JSON |
| 404 | rodada desconhecida |
| 409 | concessão vencida |
| 413 `{"erro": "lote grande demais"}` | acima de `LOTE_GZ_MAX`, de `LOTE_BRUTO_MAX`, de `ARQUIVO_MAX` ou de `ARQUIVOS_MAX` |
| 413 `{"erro": "lote grande demais", "codigo": "DESCOMPRESSAO_TETO"}` | a conferência passou de `DESCOMPRESSAO_MAX` ou de `ZIP_MEMBROS_MAX` |
| 415 | `Content-Type` ou `Content-Encoding` errado |
| 422 `{"erro": "sha256"}`, `{"erro": "esquema inválido", "detalhes": [...]}` ou `{"erro": "dado pessoal", "detalhes": [...]}` | até 10 detalhes, **sem nome**: só a chave e o índice (`arquivos[3].nome`) |

### 3.5 `POST /api/visitas/rodada/<id>/fim`

```json
{"codigo": "PARCIAL_VENDEDOR", "fase": null,
 "dias_ok": ["20261126"], "dias_faltando": [], "erros_vendedor": 1,
 "duracao_s": 412, "pico_mb": 618.0, "achados": null, "medidas": null}
```

- `codigo` da tabela do §5; o site deriva o `status` dela (constante `STATUS_DO_CODIGO`, com teste). `fase` quando o código pede.
- `pico_mb`: `/sys/fs/cgroup/memory.peak` (cgroup v2); sem ele, `memory.max_usage_in_bytes` (v1); sem os dois, `null`.
- `achados`: só com `DADO_PESSOAL` (§3.6): `[{"coluna": "<rótulo>", "tipo": "cnpj|cpf|telefone|email|formato", "n": int}]`, **nunca o valor**. `null` nos outros códigos.
- `medidas`: só no diagnóstico (§6); `null` nas outras.
- 200 `{"ok": true, "pausado": bool}`. O site grava em `rodadas.jsonl` (só acréscimo), solta a concessão, grava o `codigo` em `tentativas_hoje` e aplica a pausa do §5. O `fim` repetido responde igual.

### 3.6 O Espelho que sai do contêiner: lista de permitidas e varredura (RN-VIS-007)

O Excel que a Máxima entrega **nunca sai do contêiner**. Para cada Excel, o cron chama a função `visitas_nucleo.filtrar_espelho(origem, destino) -> dict` (modulo-rota; usa as mesmas tabelas `_ROTULOS_ESPELHO` e `_COLUNAS_ESPELHO` do `ler_espelho`, sem cópia) e manda **só o `destino`**.

**Lista de permitidas** (a constante `ESPELHO_PERMITIDAS`, com teste que a compara com esta tabela):

| Parte do Espelho | Permitido | Formato conferido |
|---|---|---|
| Cabeçalho (rótulo + valores) | `PERIODO`, `FILIAL`, `SUPERVISOR`, `RCA`, `PRIMEIRO CLIENTE`, `ULTIMO CLIENTE`, `ULTIMA POSICAO`, `TEMPO DESLOCAMENTO`, `TEMPO MEDIO ATENDIMENTO`, `VALOR VENDIDO`, `EM ANDAMENTO`, `KM TRABALHADO`, `KM TOTAL`, `CLIENTES AGENDADOS`, `QTDE VISITADOS AGENDA`, `QTDE VISITADOS FORA AGENDA`, `QTDE POSITIVADOS AGENDA`, `QTDE POSITIVADOS FORA AGENDA`, `% VISITAS REALIZADAS NA SEQUENCIA PREVISTA` | texto (código + nome do vendedor, do supervisor e da filial, que o `vc_visitas` já leva), hora, número ou "n / p%" |
| Lista de clientes (colunas) | `DATA`, `ORD PREV`, `ORD REA`, `INICIO`, `FIM`, `ATEND`, `PER`, `CODIGO`, `CLIENTE`, `ENDERECO`, `N PEDIDO`, `PEDIDO`, `JUSTIFICATIVA`, `AGEN`, `PDV` | `DATA` data; `ORD *` até 3 dígitos; `INICIO`, `FIM`, `ATEND`, `PER` hora; `CODIGO` 6 a 8 dígitos; `N PEDIDO` até 10 dígitos; `PEDIDO` número; `AGEN` S ou N; `CLIENTE`, `ENDERECO`, `JUSTIFICATIVA`, `PDV` texto |

- **Tudo o que não está na lista sai**: as colunas `KM DIST`, `BONIF` e `OBSERVACAO`, qualquer coluna ou rótulo novo da Máxima, títulos de página, rodapés e linhas sem rótulo conhecido. A célula fica vazia no `destino`, com a mesma posição, para o `ler_espelho` ler igual.
- **Limpeza do que fica (RN-GER-011), antes da varredura**, com as funções que o pacote do site já usa (`relatorios_nucleo`, sem copiar o regex):
  - `CLIENTE` → `relatorios_nucleo.cliente_sem_documento` (tira CPF/CNPJ do começo, do meio e do fim do nome; o cadastro traz documento no nome com frequência);
  - `JUSTIFICATIVA` (texto livre) → `relatorios_nucleo.texto_sem_contato` (telefone, e-mail e documento viram `[removido]`).
- **Varredura do que sobrou:** a função pura `visitas_nucleo.achar_dado_pessoal(valor, formato) -> str | None` em cada célula mantida, já limpa. É a rede para o que a limpeza não pegou:
  - `email`: `[\w.+-]+@[\w-]+(\.[\w-]+)+`;
  - `cnpj`: `\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}` ou 14 dígitos seguidos;
  - `cpf`: `\d{3}\.\d{3}\.\d{3}-\d{2}` ou 11 dígitos seguidos;
  - `telefone`: `\(?\d{2}\)?\s?9?\d{4}-\d{4}` ou `\(\d{2}\)\s?\d{8,9}`;
  - `formato`: o valor não casa com o formato da coluna (tabela acima).
- **Devolve** `{"colunas_fora": [rótulos], "limpos": {"CLIENTE": int, "JUSTIFICATIVA": int}, "achados": [{"coluna", "tipo", "n"}]}` (`limpos` = células que a limpeza mudou). Rótulo = `_rotulo` (A–Z, 0–9, `%` e espaço), até 40 caracteres e até 20 rótulos. **Nenhum valor** de célula na saída nem no log.
- **Achado em qualquer Excel do dia:** o lote desse dia **não sobe**. O cron para a rodada, fecha o navegador e manda o `fim` com `DADO_PESSOAL`, `fase: "filtro"` e os `achados`. Os dias já mandados ficam.
- **Teste de igualdade:** para todo Excel da fixture, `ler_espelho(destino)` = `ler_espelho(origem)`, fora o campo `arquivo` e com `cliente` e `justificativa` passados pelas 2 funções da limpeza. O efeito no `VISITAS_POR_CLIENTE.xlsx` e no acompanhamento é conferido pelo código do cliente (o mesmo conjunto de códigos e de contagens). Se um dia o `ler_espelho` passar a ler outra coluna, ela tem de entrar na lista (v2), senão o teste falha.

## 4. API do robô do PC (Bearer `BAP_WEB_TOKEN`) e tela

### 4.1 `GET /api/visitas/lotes?desde=<seq>`

```json
{"epoca": "e7c1…", "ate_seq": 42, "mais": false,
 "linhas": [{"seq": 41, "dia": "20261126", "rodada": "R20261127T060012",
             "baixado_em": "2026-11-27T06:07:41-04:00", "arquivos": 15, "bytes_gz": 402311,
             "sha256": "<hex>", "status": "pendente"}]}
```

- **O mesmo formato da `GET /api/edicoes`** (`epoca`, `linhas`, `ate_seq`, `mais`), porque o armazém é a mesma `web/app/edicoes.Fila`, parametrizada pela pasta (`visitas/lotes`) e pelo prefixo do arquivo, não uma cópia (modulo-web).
- No máximo 20 linhas por resposta, em ordem de `seq`. `epoca` muda quando o disco do site recomeça.
- O robô novo trata o **404 da web antiga** como "sem visitas da nuvem" e segue.

### 4.2 `GET /api/visitas/lote/<seq>`

- Devolve o corpo do §3.4 como foi gravado (`Content-Encoding: gzip`, `X-BAP-SHA256`). 404 quando saiu pela retenção.

### 4.3 `POST /api/visitas/lotes/confirmar`

```json
{"epoca": "e7c1…",
 "resultados": [{"seq": 41, "status": "aplicada", "motivo": ""},
                {"seq": 40, "status": "erro", "motivo": "sha256"}],
 "fechados_pc": {"20261126": "2026-11-27T07:12:03-04:00"}}
```

- `resultados`: o formato do `/api/edicoes/confirmar` (`Fila.confirmar`). `motivo` do `erro` ∈ `sha256`, `nome`, `pasta`, `dia`. Com `erro`, o site tira a parte da **nuvem** do dia no `indice` (a nuvem baixa de novo); a parte do PC fica.
- `fechados_pc` (**obrigatório** no robô novo, mesmo com `resultados` vazio): os dias dos últimos `FECHADOS_PC_DIAS` no `_baixados.json` do PC (`visitas_nucleo.indice`), com a hora da baixa em Manaus. O site junta no `indice` com `juntar_baixado` e grava `fechados_pc_em`.
- **O robô manda este `POST` em toda volta de 30 min**, mesmo sem lote novo: é assim que a nuvem sabe o que o PC fechou.
- 200 `{"ok": true}`. 409 `{"erro": "epoca"}`: o robô volta a `desde=0`.

### 4.4 Importação no PC: `bap_automation.sincronizar_visitas_web(raiz, base, token, log) -> dict`

- Chamada na volta de 30 min, **antes de montar o pacote**, no ponto do `sincronizar_edicoes_web`. Nunca levanta exceção e nunca derruba a rodada.
- **O laço `desde`/`epoca`/confirmar é o do `sincronizar_edicoes_web`** (o das edições, porque confirma item a item, como aqui; o da cobrança confirma só o `ate_seq`). Ele sai para uma função só em `bap_automation`, `puxar_fila_web(raiz, rota, arq_estado, aplicar, ja_feitos, registrar, base, token, sessao, log, extra_confirmar=None)`, usada pelas edições e pelas visitas. O `sincronizar_visitas_web` só traz a parte própria (o `aplicar` e o `extra_confirmar` com o `fechados_pc`). Os testes do laço são os das edições, rodados nos dois.
- **Passos do `aplicar` (um lote):**
  1. `GET /api/visitas/lote/<seq>`; confere o sha256 do corpo e de cada arquivo (não confere = `erro: sha256`);
  2. grava cada Excel no `ANALITICO` (RN-VIS-003): `.tmp` + `os.replace`; nome que casa com `visitas_nucleo._RX_ARQ_ANALITICO`, sem `/`, `\` nem `..`; pasta = `nome_limpo`; mesmo sha256 = pula; outro conteúdo = sufixo `-2`, `-3`… (`visitas_maxima.arquivo_analitico`). **Nunca sobrescreve nem apaga;**
  3. `gravar_equipe_maxima`; `anotar_baixado` com o `baixado_em` da nuvem (RN-VIS-002); `montar_dia` e `montar_mes`.
- **Fim comum:** `visitas_maxima.depois_de_baixar(raiz, log)`, uma vez por importação, a mesma função do botão do PC.
- **Registro:** `RELATORIOS/_VISITAS_WEB/IMPORTADOS_VISITAS_WEB.jsonl`, só acréscimo, uma linha por lote: `{"seq", "epoca", "dia", "arquivos", "status", "em"}`. Sem nome. É o `ja_feitos` do laço.
- Devolve `{"lotes": int, "arquivos": int, "dias": [AAAAMMDD], "erro": str | None}`.

### 4.5 Tela (sessão e perfil; corte no servidor, ADR 0001, §4.5)

| Rota | Perfis | O quê |
|---|---|---|
| `GET /visitas/atualizar` | todos os que veem o Farol de Visita | estado (agenda, pausa, rodada em andamento, `TETO_DIA`), lotes à espera do PC ("Baixado às HHhMM · esperando o PC importar") e as 10 últimas rodadas (código e texto do §5; a mais recente em destaque, no topo) |
| `POST /visitas/atualizar` `{de, ate}` | `admin`, `gerente` (D3) | grava o pedido. Padrão: os dias abertos no `indice` até hoje; no máximo 7 |
| `POST /visitas/refazer` `{de, ate}` | `admin` | o mesmo, com `refazer: true` (baixa de novo dia fechado) |
| `POST /visitas/retomar` `{recado?}` | `admin` | tira a pausa (RN-VIS-005). Com `pausado.codigo == "DADO_PESSOAL"` (RN-VIS-007): pede `recado` (`^R-\d{8}-\d{6}-alexandre$`; sem ele, 400), grava no `pedidos.jsonl` e volta o `diagnostico` a `pendente`. O site não confere o recado (ADR 0004, §6) |
| `POST /visitas/diagnostico` | `admin` | volta o diagnóstico a `pendente` |
| `POST /visitas/agenda` `{ligar}` | `admin` | liga ou desliga a agenda. Ligar só nas condições do §3.1 |

- Os outros perfis recebem 403, com teste por perfil.
- `/saude` ganha `visitas: {"agenda", "diagnostico", "ultima_rodada", "codigo", "pausado", "rodada_ativa", "fase", "lotes_a_importar", "tentativas_hoje"}` (`tentativas_hoje` = só o `total`), sem dado pessoal. É a única rota de estado: o PC também lê aqui.
- **Aviso do botão do PC**, quando `/saude.visitas.rodada_ativa`: "O site está baixando agora; baixar aqui também pode derrubar a sessão da Máxima. Continuar?"

## 5. Códigos de erro (D5: sem print de tela, só o código)

A nuvem **não tira print** em nenhum caso. O código e a fase bastam; a investigação com imagem é feita no PC, com "Mostrar o navegador". A mensagem crua da Máxima **nunca** é copiada para o código, o log ou o site.

| Código | `status` | Quando | Depois (quem decide: o site, no `fim`) |
|---|---|---|---|
| `OK` | ok | todos os dias e vendedores vieram | — |
| `NADA_A_FAZER` | ok | a concessão veio, mas os dias ficaram fechados no meio-tempo | — |
| `PARCIAL_VENDEDOR` | parcial | algum vendedor falhou; os outros vieram | `retentativa` uma vez (RN-VIS-006). O nome do vendedor só aparece na tela, para admin e gerente, a partir do lote |
| `PARCIAL_TEMPO` | parcial | passou de `RODADA_MAX_MIN` no fim de um dia | nova tentativa (§3.1); o pedido continua até `PEDIDO_MAX_RODADAS` |
| `MAXIMA_SENHA` | erro | a Máxima recusou usuário ou senha | **pausa** (RN-VIS-005), sem segunda tentativa |
| `MAXIMA_CONFIRMACAO` | erro | a Máxima pediu código por SMS ou e-mail, confirmação de novo dispositivo, aceite de termo ou troca de senha | **pausa** |
| `MAXIMA_CAPTCHA` | erro | apareceu captcha (iframe ou elemento conhecido) | **pausa** |
| `MAXIMA_BLOQUEIO` | erro | conta bloqueada, acesso negado ou HTTP 403 na página de login | **pausa** |
| `DADO_PESSOAL` | erro | o filtro do §3.6 achou CNPJ, CPF, telefone, e-mail ou valor fora do formato; ou o site recusou o lote com 422 de dado pessoal ou coluna fora da lista (§3.4) | **pausa** (RN-VIS-007); o lote do dia não sobe; "Retomar" no §4.5 |
| `MAXIMA_FORA` | erro | tempo esgotado no `goto` do login, ou HTTP 5xx | agenda: nova tentativa (§3.1); botão: o pedido sai da fila |
| `TELA_MUDOU` | erro | `ErroRobo` numa fase (`fase` obrigatória) | nova tentativa (§3.1); 2 rodadas seguidas na mesma fase **pausam a agenda** |
| `NAVEGADOR_FALHOU` | erro | o Chromium não abriu ou caiu (`Target closed`, falta de memória) | nova tentativa (§3.1); 2 seguidas aparecem no `/saude` |
| `SITE_RECUSOU` | parcial | o site respondeu 413 ou 422 a um lote, fora o 413 com `codigo` `DESCOMPRESSAO_TETO` (que é `DESCOMPRESSAO_TETO`) e o 422 de dado pessoal (que é `DADO_PESSOAL`) | nova tentativa (§3.1) do dia recusado |
| `DESCOMPRESSAO_TETO` | parcial | o site respondeu 413 com esse `codigo`: a conferência passou de `DESCOMPRESSAO_MAX` ou de `ZIP_MEMBROS_MAX` (§3.4) | **sem** nova tentativa no dia: o mesmo Excel daria o mesmo erro e gastaria logins da Máxima. Fica fora de `NOVA_TENTATIVA`. O cron fecha o dia com este código |
| `SITE_FORA` | erro | o cron não fala com o site depois de `HTTP_TENTATIVAS` | só no log do Render; o site vê `RODADA_INTERROMPIDA` |
| `RODADA_INTERROMPIDA` | erro | **gravado pelo site**: a concessão venceu sem `fim` | nova tentativa (§3.1) do que falta |
| `TETO_DIA` | — | **estado do site, não rodada**: `tentativas_hoje` chegou ao teto (RN-VIS-008) | nada até o dia seguinte |
| `CONFIG_FALTANDO` | erro | falta `BAP_MAXIMA_USUARIO`, `BAP_MAXIMA_SENHA`, `BAP_VISITAS_TOKEN` ou `BAP_WEB_HOSTPORT` | sai sem abrir o navegador; cada volta repete (custa segundos). O nome da variável só no log do Render |
| `CONFIG_INSEGURA` | erro | `DEBUG` com `pw`, `PWDEBUG` ou trace ligado | sai sem abrir o navegador |
| `ERRO_INTERNO` | erro | exceção não prevista (`fase` obrigatória) | nova tentativa (§3.1). No log, só o nome da classe da exceção, nunca a mensagem |

**`DESCOMPRESSAO_TETO`** (`web/app/visitas.CODIGO_TETO`) é, ao mesmo tempo, o `codigo` da resposta 413 do site (§3.4) e o código com que o cron fecha o dia. Ele entra no `CODIGOS` da web, fora da lista de códigos com nova tentativa.

**Texto no site: a fonte única é a web** (`web/app/visitas.py`, T-0045). Este contrato só aponta para as constantes, e o `testes` compara os códigos daqui com os de lá:
- **`CODIGOS[código]`** = `(status, texto)`. O texto diz o que aconteceu e o que fazer, sem jargão. Os marcadores são:
  - `{h}`: a hora do fim;
  - `{d}`: o dia;
  - `{n}`: os vendedores sem visita;
  - `{c}`: a coluna;
  - `{t}`: "Tentamos de novo às HHhMM." ou "Tente mais tarde.".
- **`STATUS_DO_CODIGO`** sai do `CODIGOS`. O `status` de cada código tem de ser o da tabela acima (teste).
- **"Situação"**, a palavra que a tela mostra no lugar do código: `SITUACAO` (`ok` → "Em dia", `parcial` → "Parcial", `erro` → "Erro"), com a cor de `SITUACAO_COR`. Com `pausado`, a situação é "Pausado"; durante a rodada, "Baixando".
- **O código** (e a `fase`, quando houver) aparece pequeno, "para o suporte". É a decisão 6 B: o código no lugar do print.
- **`TETO_DIA`:** `TETO_DIA_TEXTO`.
- O `NADA_A_FAZER` não aparece na lista de rodadas.

- **Pausa** = `pausado` gravado; o cron sai sem tocar na Máxima até o "Retomar" do admin. O botão do PC continua funcionando.
- **Nova tentativa (§3.1)** = o próximo horário do motivo, dentro do teto do dia: na agenda, os `RETENTATIVAS_AGENDA`; no pedido, a volta seguinte, até `PEDIDO_MAX_RODADAS`; na retentativa e no diagnóstico, nenhuma.
- **Saída do processo:** 0 para `ok`, `parcial`, sem trabalho, pausado, 409 e 429; 1 para `erro` e para o vigia (`RODADA_MATA_MIN`). Não há outra saída. Assim o painel do Render marca a execução falhada.
- **Log do cron** (o único lugar visível no Render): uma linha por evento, `evento=<nome> fase=<fase> dia=<AAAAMMDD> n=<int> codigo=<CÓDIGO>`. Sem nome de vendedor ou cliente, sem valor de célula, sem usuário, sem senha, sem URL com `PWE=`. Um filtro final troca o usuário e a senha por `***` se aparecerem.

### 5.1 A Máxima pede confirmação ou captcha: a regra

- A detecção é a função pura `classificar_login(url, texto, tem_captcha, http_status) -> str | None` (modulo-robo), chamada depois do "Entrar":
  - continua no `/login` com mensagem de erro de credencial → `MAXIMA_SENHA`;
  - captcha → `MAXIMA_CAPTCHA`;
  - continua no `/login`, ou foi para uma página de verificação, com texto de código, confirmação, dispositivo, termo ou troca de senha → `MAXIMA_CONFIRMACAO`;
  - texto de bloqueio ou HTTP 403 → `MAXIMA_BLOQUEIO`;
  - saiu do `/login` → `None` (segue).
- **Nunca** tenta resolver captcha, nunca repete o login, nunca espera um humano. Fecha o navegador, manda o `fim` e sai.
- Se o diagnóstico (§6) der `MAXIMA_CONFIRMACAO`, `MAXIMA_CAPTCHA`, `MAXIMA_BLOQUEIO` ou `DADO_PESSOAL`, a agenda não é ligada (as saídas estão na ADR 0004, §6).

## 6. Diagnóstico (antes de ligar a agenda)

- **Quando:** na primeira volta do cron com as variáveis presentes e `diagnostico.estado == "pendente"`. O admin pode pedir de novo pela tela (teto de `TENTATIVAS_DIA`).
- **O quê:** login, maxGestão, filtros e **ontem** com **2 vendedores**, até `DIAGNOSTICO_MAX_MIN`, e o filtro do §3.6 nos 2 Excel. **Não manda lote** (nenhum dado sai do contêiner).
- **`medidas` no `fim`:**

```json
{"tempos_s": {"login": 21.4, "maxgestao": 9.8, "filtros": 30.2, "vendedor": [44.0, 51.3]},
 "fonte_pico": "cgroup", "chromium": "<versão>",
 "espelho": {"colunas_fora": ["KM DIST", "BONIF", "OBSERVACAO"], "limpos": {"CLIENTE": 3, "JUSTIFICATIVA": 0}}}
```

  - `fonte_pico`: de onde veio o `pico_mb` do `fim` (`cgroup`, `cgroup_v1` ou `indisponivel`).
  - `espelho`: as `colunas_fora` e os `limpos` do `filtrar_espelho` (§3.6) nos 2 Excel, somados. Os achados vão só no `achados` do `fim` (§3.5), e com eles o `codigo` é `DADO_PESSOAL`.
- **Resultado:** uma linha `DIAGNOSTICO codigo=... pico_mb=... login_s=... vendedor_s=... colunas_fora=<n> limpos=<n> achados=<n>` no log do Render e o mesmo na tela do admin. Com `OK`, o `diagnostico.estado` vira `ok`; a agenda continua `desligada` até o admin ligar, depois do "ok" do Alexandre.
- **Antes do "ok":** o Alexandre confere no painel do Render a duração de 3 voltas **sem trabalho** (a conta de custo da ADR 0004, §3.3, supõe 30 s cada).

## 7. Disco do site (`/var/data/visitas/`)

| Arquivo | Regra |
|---|---|
| `estado.json` | `agenda`, `diagnostico`, `pausado`, `pedido`, `rodada_ativa`, `falhas_seguidas`, `indice`, `tentativas_hoje`, `fechados_pc_em`. Gravação atômica |
| `lotes/` | o armazém da `edicoes.Fila` (`epoca`, `seq`, linhas só de acréscimo) e os corpos `<seq>.json.gz` do §3.4. Os corpos saem pela `LOTE_GUARDA_DIAS`; o não confirmado sai com aviso no `/saude` |
| `pedidos.jsonl` | só acréscimo: `{id, de, ate, refazer, perfil, em}` e os "Retomar" (`{retomar, codigo, recado, perfil, em}`); perfil, nunca o usuário |
| `rodadas.jsonl` | só acréscimo: o `fim` de cada rodada, mais `RODADA_INTERROMPIDA` |

Cerca de 15 MB por mês, dentro do disco de 1 GB.
