# ADR 0003 — Pacote por farol: um arquivo por farol (gzip) e um índice, lido do disco sob demanda

- **Status:** proposta (T-0035). Não muda o `render.yaml`, então não pede "autorizo". A única decisão visível ao Alexandre é a §4.4 (o farol que falhou numa rodada fica com os dados da rodada anterior), com recomendação.
- **Data:** 2026-11-26
- **Tarefa:** T-0035 · **Autor:** engenheiro-software
- **Depende de:** ADR 0001 (web no Render, modelo M2, adendos 2 a 5), ADR 0002 (rotina diária: o limite 3 compara a `VERSAO` da web com o `/saude`), contrato do relatório §10 (a nova §10.8 é desta ADR)
- **Consumidores:**
  - modulo-web: `web/app/pacotes.py`, `main.py`, `config.py`, `edicoes.py` (só a chamada), `cobranca.py` (só a chamada), `exportar.py` (só a origem da tabela);
  - modulo-robo: `bap_automation.py` (4f: `enviar_pacote_web`, `_cortar_pacote_web`, `passo_pacote_web`);
  - testes;
  - modulo-posvenda e modulo-farois: só informativo (nada muda no que eles montam).
- **Recados:**
  - R-20261126-174334-alexandre: "migrar tudo";
  - R-20261126-175814-gerente-projetos: o plano, a T-0035 e o risco 1 do inventário;
  - `recados/anexos/T-0033/inventario-pc-site.md`, §4, risco 1.

## 1. Contexto

- **O pacote cresce com a migração.** Ele tem 13,7 MiB de JSON compacto com o lote 2 (T-0024).
  - Só as linhas das tabelas dos 23 faróis do catálogo somam 17 MB nas bases congeladas: Roteirização 3,9 MB, Giro 3,7, Markup 2,5, Garantias 1,4, Clientes 1,2, Painel 0,9, Pedidos 0,9.
  - Somam-se as parciais em PNG (até 3 MB cada, em base64, 3 por farol, em 3 faróis), os CSVs do Protheus (até 1,5 MB) e os recortes por estado.
  - Os tetos de hoje são `BAP_WEB_PACOTE_MAX_MB = 25` na web e `WEB_PACOTE_TETO_MB = 20` no robô. Eles estouram com a T-0024 e a T-0036. O `_cortar_pacote_web` só sabe cortar os faróis antigos e tira abas que o Alexandre pediu ("tudo").
- **A web guarda tudo na memória.** O Render starter tem 512 MB e um processo só.
  - O `pacotes.Ultimo.get()` faz `json.loads` do pacote inteiro e o mantém na memória.
  - O `pacotes.por_sha` (cobrança) carrega um segundo pacote inteiro.
  - O dicionário Python ocupa de 5 a 10 vezes o JSON: 13,7 MiB viram de 70 a 140 MB, e o dobro com o `por_sha`.
  - No recebimento (`POST /api/pacote`), o corpo inteiro (até 25 MB), o dicionário dele e o pacote anterior ficam juntos na memória. É o pico, e ele chega perto dos 512 MB.
  - Cada página lê um farol só, mas paga por todos.
- **Sem dependência nova:** o `gzip`, o `zlib` e o `hashlib` são da biblioteca padrão, nos dois lados. O PC do robô (DT-AMADMBAP-03) não ganha nada para instalar.

## 2. Opções

| | Opção | A favor | Contra |
|---|---|---|---|
| A | Manter o pacote único e cortar mais | nada a mudar | contraria o "tudo"; o pico de memória continua |
| B | Plano maior no Render (Standard, 2 GB, cerca de US$ 25/mês) | nenhum código | custo (o Alexandre escolheu o plano de US$ 7, ADR 0001, adendo 1); muda o `render.yaml` (governança); só adia o problema |
| C | Pacote único, que a web divide por farol ao receber | só a web muda | o pico do recebimento e o teto de 25 MB continuam |
| **D** | **Um arquivo por farol (gzip) e um índice, enviados farol a farol; a web guarda só o índice e lê o farol do disco quando a página pede** | a memória fica proporcional ao maior farol, não à soma; o envio fica cerca de 85% menor; o farol que falha não derruba os outros | robô e web mudam juntos; o transporte ganha 2 rotas |
| E | Banco (SQLite no disco, ou Postgres) com as linhas | filtro e busca no servidor sem carregar a tabela | a maior mudança; Postgres tem custo e pede ADR própria |

## 3. Decisão

- **D**, com **C** como caminho de compatibilidade: a web nova continua aceitando o pacote único do robô antigo e o divide ao receber.
- **B** fica como alavanca de reserva, se a medição do `/saude` (§4.6) mostrar que não basta. Ela pede "autorizo" do Alexandre por causa do custo e do `render.yaml`.
- **E** fica para quando precisarmos de filtro pesado no servidor. Hoje a tela filtra linhas de um farol só, que cabem na memória.
- **O conteúdo de cada farol não muda.** `relatorios[rid]` continua com as mesmas chaves (§10.1 a §10.7). Muda o **transporte e a guarda**: o "formato do pacote" passa de 1 (um JSON) a 2 (um arquivo por farol e um índice). O `versao_contrato` continua 1. Os detalhes de rota, campo e código de erro estão no contrato do relatório, §10.8.

## 4. Desenho

### 4.1 Disco (`/var/data/pacotes/`)

```
pacotes/
  20261126T083000/              # um lote = uma rodada do robô (nome = gerado_em em Manaus, pacotes.nome_arquivo)
    indice.json                 # o topo do pacote + uma entrada por farol (§10.8.2)
    vc_painel.json.gz
    pv_pedidos.json.gz          # o farol sem os anexos
    pv_pedidos.parcial-acum.png # anexos: as parciais em PNG (decodificadas)
    pv_pedidos.csvs.json.gz     # anexos: os CSVs do Protheus
    ...
  _recebendo/20261126T083000/   # o lote em recebimento; só vira pasta de lote depois do "fechar"
  20261125T140000.json          # pacote no formato 1 (web antiga); só sai pela retenção
```

- **O lote vigente é a maior pasta `pacotes/<lote>/` que tem `indice.json`.** O lote em recebimento fica em `_recebendo/` e passa para `pacotes/` com um `os.replace` só, depois do `indice.json` gravado. Por isso uma pasta de lote está sempre completa, e não existe ponteiro `atual` para manter.
- **Retenção:** os 7 lotes mais novos (`GUARDAR = 7`, RN-POS-003), contando junto os `*.json` do formato 1, pelo nome.
- **Limpeza:** um `_recebendo/<lote>` com mais de 2 h sai na partida do app e em todo `fechar`.
- **A web antiga ignora tudo isso:** ela só lista `pacotes/*.json`. No rollback do Render, o site fica sem dado até a próxima rodada do robô, que vê o `/saude` antigo e volta a mandar o formato 1 (§4.7).
- **Partida da web nova sobre um disco no formato 1:** se não há lote e há `pacotes/*.json`, ela converte **só o mais novo** num lote (`origem: "convertido"`). É o mesmo pico de memória de hoje, uma vez só.
- **Tamanho:** um lote com gzip leva cerca de 2 a 4 MB [SUPOSIÇÃO: o JSON das tabelas comprime de 85% a 90%; o PNG não comprime]. 7 lotes ficam em cerca de 30 MB, dentro do disco de 1 GB.

### 4.2 Envio pelo robô (4f)

1. `GET /saude`. Se `pacote.formatos` não traz `2` (web antiga) ou o GET falha, o robô manda o formato 1, como hoje: `enviar_pacote_web(_cortar_pacote_web(pacote))`.
2. Para cada farol de `relatorios`:
   - o corpo é `json.dumps(farol, ensure_ascii=False, allow_nan=False, separators=(",", ":"))` em UTF-8, com o sha256 desses bytes e o `gzip.compress(corpo, 6)`;
   - vai em `POST /api/pacote/<lote>/farol/<rid>` (§10.8.3), com 3 tentativas e timeout de 60 s.
   - Quando a web recusa o farol (413 ou 422), o robô registra no log o `rid`, o código e os `detalhes` (sem dado pessoal). O farol vai para a lista `manter` do passo 3, e o lote segue.
   - O 404 (um `rid` que a web publicada ainda não conhece) também fica só no farol: ele sai, e o resto do lote segue. Acaba o risco do §10.7.10 do contrato ("o robô novo antes da web derruba o pacote inteiro").
3. `POST /api/pacote/<lote>/fechar` com o topo (`versao_contrato`, `gerado_em`, `ano`, `mes`), o `{rid: sha256}` dos faróis aceitos e a lista `manter` dos que falharam (§4.4).
4. Se o `fechar` falhar 3 vezes, nada troca no site, e o lote em `_recebendo/` sai pela limpeza. A rodada do robô segue (o 4f nunca derruba a rodada).

- **Teto por farol no robô:** `WEB_FAROL_TETO_MB = 8`, medido no JSON do farol **sem os anexos** (`parciais`, `csvs_protheus`).
  - Os anexos têm os tetos que já existem: `MAX_PNG_B64` e `MAX_CSVS_TOTAL` (`web/app/pacotes.py`).
  - Acima do teto, uma função pura nova corta **o farol**: `_cortar_farol_web(rid, farol, teto_mb) -> dict`, com a ordem de corte por `rid` numa constante (`_CORTES_FAROL_WEB`).
  - Os passos 1 a 3 do `_cortar_pacote_web` viram os cortes do `pv_pedidos` e do `vc_visitas`. O último corte de qualquer farol é tirar todas as `tabelas`, e o farol cai no §10.1. Cada corte deixa um aviso no farol (`AVISO_ABAS_FORA`).
  - O `_cortar_pacote_web` e o `WEB_PACOTE_TETO_MB` ficam só para o formato 1 (web antiga).
- **`montar_pacote_web`** continua pura e devolve o mesmo dicionário. Ela ganha `cortar: bool = True`. O envio por farol chama com `cortar=False` e corta farol a farol.
- **Simulação:** o `--simular-pacote` grava também a pasta do lote (o `indice.json` e os `.json.gz`) ao lado do JSON de hoje, para o testes medir o tamanho e a memória.

### 4.3 Recebimento na web

- **`POST /api/pacote/<lote>/farol/<rid>`:**
  - autenticação: o mesmo Bearer `BAP_WEB_TOKEN`;
  - `<lote>` = `^\d{8}T\d{6}$` e `<rid>` em `pacotes.ACEITOS`;
  - o corpo é lido em partes, até `FAROL_GZ_MAX`, e descomprimido aos poucos (`zlib.decompressobj(16 + zlib.MAX_WBITS)` com `max_length`), até `FAROL_CORPO_MAX`. Passou = 413 (defesa contra bomba de gzip);
  - o sha256 dos bytes descomprimidos é conferido com `X-BAP-SHA256`; diferente = 422;
  - `json.loads`, depois `pacotes.validar_relatorio(rid, farol)` (§4.8) e `tabelas.tirar_abas_com_documento` só naquele farol;
  - os anexos saem do farol (`parciais` para PNG decodificado; `csvs_protheus` para `<rid>.csvs.json.gz`);
  - o farol sem anexos vai para `_recebendo/<lote>/<rid>.json.gz` (gravação atômica). Se o JSON dele passar de `FAROL_JSON_MAX` = 10 MB, a resposta é 413;
  - o mesmo farol de novo no mesmo lote substitui o anterior (idempotente para a nova tentativa do robô).
- **`POST /api/pacote/<lote>/fechar`:**
  - confere o topo (`pacotes.validar_topo`) e que `nome_arquivo(gerado_em) == lote`;
  - confere que cada `rid` de `farois` está em `_recebendo/<lote>/` com o mesmo sha256;
  - aplica o `manter` (§4.4), grava o `indice.json` e move a pasta. Depois roda a retenção e a limpeza;
  - repetir o `fechar` de um lote já fechado responde 200 com o mesmo resultado;
  - um lote mais velho que o vigente é guardado, mas não vira o vigente (é a regra de hoje: vale o maior nome).
- **`POST /api/pacote` (formato 1):** continua.
  - Antes do `json.loads`, ele esvazia o cache de faróis (§4.5), para baixar o pico.
  - Valida como hoje (`pacotes.validar`), divide o pacote num lote (`origem: "inteiro"`) com as mesmas funções do envio por farol e troca o vigente.
  - O teto dele continua o `BAP_WEB_PACOTE_MAX_MB` (25). Ele sai numa ADR futura, depois de 2 semanas sem uso no log.

### 4.4 Farol que falhou na rodada (decisão a levar, recomendação A)

- **Hoje:** o farol que não montou no PC some do pacote ("Sem dados hoje"), mas os outros também param se o envio inteiro falhar.
- **Com o envio por farol,** pode faltar um farol só numa rodada (rede, 413). Duas opções:
  - **(A) recomendada:** o farol da lista `manter` é copiado do lote vigente para o novo (hard link, com fallback para cópia), com `herdado_de` e o `gerado_em`/`recebido_em` dele. A faixa mostra a data **do farol** e o selo "Desatualizado" quando ela passa de 26 h (contrato tela-bc3 §4.1). Farol herdado com mais de 26 h não é copiado de novo e sai.
  - **(B):** o farol some até a próxima rodada boa, como hoje com o farol que não montou.
- **O farol que não montou no PC** (`erro_montagem`) **não** entra no `manter`: ele some, como hoje. Isso evita mostrar como atual um número que o PC não conseguiu fazer.
- **Número do Diretor:** com (A), o `vc_painel` e um farol herdado podem ter datas diferentes. A data de cada um aparece na tela, e a conferência PC × web (ADR 0001, §5) compara farol com farol do mesmo `gerado_em`.

### 4.5 Leitura (o que fica na memória)

- **`pacotes.Indice(dados)`** substitui o `Ultimo`. Na memória, ele guarda só o `indice.json` do lote vigente: alguns KB, recarregado quando o nome do lote ou o `mtime` mudam.
  - `indice()`: o topo e os faróis, para o menu, a faixa e o `/saude`.
  - `farol(rid) -> dict | None`: lê `<rid>.json.gz` do disco e guarda num **cache LRU com orçamento**:
    - o custo de cada farol é estimado em `bytes_json × 6`;
    - os faróis mais antigos saem até a soma caber em `CACHE_FAROIS_MB` (96 MB);
    - um farol maior que o orçamento sozinho é lido e não guardado;
    - a chave é `(lote, rid, sha256)`.
  - `sha(rid)`, `recebido_em(rid)` e `gerado_em(rid)`: vêm do índice, sem abrir o farol.
  - `anexo(rid, nome) -> Path | None`: o caminho do PNG ou dos CSVs, servido do disco (`FileResponse`), sem passar pela memória do farol.
- **Por rota:**

  | Rota | Lê |
  |---|---|
  | menu lateral e `/` | só o índice |
  | `/painel` | `farol("vc_painel")` |
  | `/farol/<rid>` e `/farol/<rid>/exportar` | `farol(rid)` |
  | parcial e CSV | o anexo do disco |
  | cobrança | `farol("pl_inadimplencia")`; `por_sha` lê só esse farol do lote antigo |

- **Uma leitura por vez:** os handlers são `async def` com leitura síncrona num processo só, então só um farol é lido de cada vez. Se algum virar `def` (pool de threads), o `Indice.farol` passa a usar uma trava (`threading.Lock`) na leitura.

### 4.6 Memória medida no `/saude`

- **O `/saude` ganha:**
  - `"pacote": {"formatos": [1, 2], "lote": "<lote vigente>", "farois": <n>, "origem": "por_farol" | "inteiro" | "convertido"}`;
  - `"memoria": {"rss_mb", "pico_mb", "limite_mb", "cache_mb", "cache_farois"}`.
- **Origem dos números:**
  - `rss_mb`: o `VmRSS` de `/proc/self/status`;
  - `pico_mb`: `resource.getrusage(RUSAGE_SELF).ru_maxrss / 1024`;
  - `limite_mb`: `/sys/fs/cgroup/memory.max` quando dá para ler, senão `null`;
  - `cache_mb`: a estimativa do LRU.
  - Todos da biblioteca padrão. Fora do Linux, `null`.
- **Log:** uma linha por recebimento: `rid`, bytes gzip, bytes JSON, ms e `rss_mb` depois. Sem conteúdo nem dado pessoal.
- **Alerta:** com `pico_mb` acima de 400, o `/saude` acrescenta `"memoria_alerta": true`. O gerente leva ao Alexandre a opção B (§2), com o número medido.
- **Nada de segredo nem de dado pessoal** no `/saude`, que é público (o health check do Render).

### 4.7 Compatibilidade na virada e ordem de merge

| Robô | Web | O que acontece |
|---|---|---|
| antigo | antiga | como hoje |
| antigo | **nova** | o `POST /api/pacote` continua. A web divide o pacote num lote; o site funciona, com o pico de recebimento de hoje |
| **novo** | antiga | o `/saude` não traz `pacote.formatos`, e o robô manda o formato 1 com o `_cortar_pacote_web` (teto de 20 MB), como hoje |
| **novo** | **nova** | por farol |
| novo | nova, depois de um rollback para a antiga | o site fica sem dado até a próxima rodada. O robô vê o `/saude` antigo e volta ao formato 1. Nenhum dado digitado se perde: os diários de cobrança e de edições não mudam de formato |

- **Ordem de merge:**
  1. este PR (ADR e contrato §10.8, engenheiro-software);
  2. **web** (modulo-web), com a `VERSAO` em `0.4.0`. Sobe sozinho com o merge (ADR 0001, adendo 4);
  3. **robô** (modulo-robo), merge depois do deploy da web. A rotina diária só instala o `bap_automation.py` novo quando a `VERSAO` do `main` bate com o `/saude` (ADR 0002, limite 3), então a web chega antes por construção. Mesmo fora de ordem, o passo 1 da §4.2 protege;
  4. **T-0024** (lote 2) e os seguintes, já sem o corte global.
- **A T-0024 não precisa esperar** se cortar "Todos os produtos" (Giro) e "Por cliente" (Roteirização) no formato 1 até o passo 3 entrar (inventário, item 4).

### 4.8 Impacto no código que existe

- **`pacotes.validar(c)`** é dividida, sem mudar regra nenhuma:
  - `validar_topo(c)`: `versao_contrato`, `gerado_em`, `ano`, `mes`;
  - `validar_relatorio(rid, r)`: o corpo do laço de hoje (`rid` em `ACEITOS`, a forma "farol" via `validar_farol`, a forma "abas" do `vc_painel`);
  - `validar(c)` = `validar_topo` + `validar_relatorio` de cada `rid`, com o mesmo corte de 10 erros. Continua para o formato 1 e para os testes de hoje.
  - Não existe regra que cruze faróis.
- **`pacotes.gravar` e `listar`** passam a gravar e listar lotes (§4.1). O `_enxuto` do `vc_painel` vale nos dois formatos.
- **Diário de edições (`edicoes.py`):** o formato não muda (`EDICOES_WEB_<AAAA-MM>.jsonl`, `/api/edicoes`).
  - Muda o `recebido_em` que a `edicoes.marca` recebe: passa a ser **o do farol** (`Indice.recebido_em(rid)`), não o do pacote. No farol herdado (§4.4), é o da rodada de origem, então a edição aplicada segue "Aguardando o PC" até chegar um farol montado depois da confirmação. É o certo.
  - O robô já sincroniza as edições antes do `montar` (`passo_pacote_web`), e a ordem continua.
  - A especificação `edicao` dentro das tabelas (`edicoes.LUGARES`) é validada no farol, como hoje.
- **Cobrança (`cobranca.py`, §10.6.4 e §10.6.5):** o formato do diário não muda.
  - O campo `pacote_sha` passa a ser o **sha256 do farol `pl_inadimplencia`** do índice, não o do pacote inteiro. O PC não lê esse campo (`cobranca_whatsapp.importar_web`).
  - `pacotes.por_sha(dados, sha)` vira `por_sha(dados, rid, sha)` e procura nos 7 lotes pelo índice, abrindo só aquele farol.
  - Um `pacote_sha` antigo (do pacote inteiro) não é achado e cai no farol vigente. É o caminho que o §10.6.4 já prevê.
- **`exportar.py`:** a tabela vem de `Indice.farol(rid)`. O rodapé usa o `gerado_em` do farol.
- **Parciais e CSVs:** as rotas `/farol/<rid>/parcial*` e `/farol/pv_pedidos/csv/<nome>` leem o anexo do disco. O robô manda os anexos dentro do farol, como hoje.
- **Testes de hoje:** os de `pacotes.validar` continuam. Os que leem `Ultimo` passam a ler `Indice`, com um auxiliar que grava um lote de teste.

### 4.9 Tetos

| Teto | Onde | Valor | O que acontece acima |
|---|---|---|---|
| `WEB_FAROL_TETO_MB` | robô, JSON do farol sem anexos | 8 MB | `_cortar_farol_web`, com aviso no farol |
| `FAROL_JSON_MAX` | web, JSON do farol sem anexos | 10 MB | 413 no farol; o robô põe o farol no `manter` |
| `FAROL_CORPO_MAX` | web, corpo descomprimido (farol + anexos) | 24 MB | 413 |
| `FAROL_GZ_MAX` | web, corpo comprimido | 24 MB | 413 |
| `LOTE_FAROIS_MAX` | web, faróis por lote | 60 | 422 no `fechar` |
| `CACHE_FAROIS_MB` | web, orçamento estimado do LRU | 96 MB | o farol mais antigo sai do cache |
| `BAP_WEB_PACOTE_MAX_MB` | web, formato 1 | 25 MB (`render.yaml`, não muda) | 413, como hoje |
| `WEB_PACOTE_TETO_MB` | robô, formato 1 | 20 MB | `_cortar_pacote_web`, como hoje |

- **Onde ficam:** os tetos novos da web são constantes em `web/app/config.py`, cada uma com uma variável de ambiente opcional (`BAP_WEB_FAROL_MAX_MB`, `BAP_WEB_CACHE_MB`) para ajuste no painel sem deploy. Elas **não** entram no `render.yaml`.
- **Conta do pior caso:** o app vazio tem cerca de 100 MB. Somam-se o cache (96 MB) e a leitura de um farol de 10 MB (cerca de 80 MB). Dá cerca de 280 MB, contra os 300 a 450 MB de hoje com 13,7 MiB.

### 4.10 `render.yaml`

- **Não muda.** Nenhuma variável nova é obrigatória, e o disco (1 GB) e o plano (starter, 512 MB) continuam. Por isso esta ADR não pede "autorizo".
- Se a medição da §4.6 pedir o plano maior (opção B), vira um PR de governança à parte, com o número medido e o "autorizo" do Alexandre.

### 4.11 Segurança

- **Mesmas regras do `POST /api/pacote`:** Bearer conferido em tempo constante, só `application/json` (com `Content-Encoding: gzip` ou sem), nenhum `.pkl`, nenhuma chave proibida (§10.1).
- **Bomba de gzip:** barrada pelo `max_length` da descompressão (§4.3).
- **Caminho:** `<lote>` e `<rid>` passam por regex e lista fechada, e o nome do arquivo é montado pela web, nunca vem do robô. O nome do CSV já passa pela `pacotes.RE_CSV`.
- **Log** sem conteúdo do farol nem dado pessoal (regra 6).

## 5. Consequências

- **(+)** A memória fica no tamanho do maior farol mais o cache, e não da soma. A migração inteira (T-0023 a T-0043) cabe no plano de US$ 7 [SUPOSIÇÃO: a medição do `/saude` confirma].
- **(+)** Cada farol tem o próprio teto. Um farol grande não tira as abas dos outros, e um farol com erro não derruba o lote.
- **(+)** O envio pela rede da empresa fica cerca de 85% menor.
- **(+)** O `/saude` mostra a memória: a decisão sobre o plano maior passa a ter número.
- **(−)** Duas rotas novas e um formato de disco novo. O formato 1 convive até ser retirado (ADR futura).
- **(−)** Com a §4.4 (A), dois faróis podem ter datas diferentes na mesma hora. A data e o selo ficam na faixa de cada um.
- **(−)** O rollback da web para antes da 0.4.0 deixa o site sem dado até a próxima rodada.

## 6. Plano por dono

| Dono | O quê | Tamanho |
|---|---|---|
| engenheiro-software | esta ADR e o contrato §10.8; revisão dos 2 PRs contra o contrato | P (2 h; o desenho está feito) |
| modulo-web | `pacotes.py` (`validar_topo`, `validar_relatorio`, lote, `Indice` com LRU, `por_sha` por farol, anexos, conversão na partida, retenção e limpeza); `main.py` (2 rotas, formato 1 dividido, `/saude` com `pacote` e `memoria`, trocar `ultimo.get()`); `config.py` (tetos); `VERSAO = "0.4.0"`; testes da web | M (8 h) |
| modulo-robo | `enviar_pacote_web` por farol, com o `/saude` e a volta ao formato 1; `_cortar_farol_web` e `_CORTES_FAROL_WEB`; `montar_pacote_web(cortar=)`; o `--simular-pacote` grava o lote; testes com `test_RN_GER_011_...` nos cortes | M (5 h) |
| testes | matriz da §4.7 (4 casos, com fixture sintética); bomba de gzip; sha errado; `fechar` repetido; `manter`; o `por_sha` antigo cai no vigente; a memória medida com o lote simulado do lote 2 (`tracemalloc` fora do CI, número no PR) | M (4 h) |
| modulo-posvenda, modulo-farois | nada no código; recado informativo (o `pacote_sha` muda de sentido, §4.8) | — |

**Total: G (cerca de 19 h de agente).** A web e o robô correm em paralelo, e o merge segue a ordem da §4.7.

## 7. Riscos

- **A estimativa de 6× para o custo do farol na memória** pode errar. Por isso o orçamento do cache é estimado e o `/saude` mede: ajusta-se o `BAP_WEB_CACHE_MB` no painel, sem deploy.
- **Proxy da empresa e `Content-Encoding` no POST:** se o proxy recusar, o robô manda o mesmo corpo sem gzip (a rota aceita os dois), com os mesmos tetos.
- **Dois faróis com datas diferentes** (§4.4 A): mitigado pela data por farol na faixa e pelo selo.
- **O pico do formato 1 continua até o robô novo ser instalado.** Ele é igual ao de hoje e sai com a instalação.
