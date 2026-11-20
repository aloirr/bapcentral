# ADR 0001 — BAP Central na web (Render)

- **Status:** proposta (aguarda o aceite do Alexandre pelo po)
- **Data:** 2026-11-20
- **Tarefa:** T-0006 · **Autor:** engenheiro-software
- **Depende de:** T-0002 (contrato do relatório), T-0003 (`ATUALIZAR_DO_GITHUB.bat`), T-0007 (recados por git)
- **Consumidores:** modulo-web (`web/**`), modulo-robo (`bap_automation.py`), engenheiro-dados (`bap_dados.py`), modulo-farois (`relatorios_nucleo.py`, `painel_diretor.py`), testes, revisor-codigo
- **Fontes:** `docs/produto/04-arquitetura.md`, `05-roadmap.md`, `06-integracoes.md`; `relatorios_nucleo.montar`; `bap_dados.BLOCOS`/`_fontes`; `docs/legado/ESTRUTURA_BAP_TOOLS_PARA_PROMPT.md` (seção 8) e o diário do Maestro Sistemas (o BAP Ajuda 2.0 no Render)

## 1. Contexto

- Hoje o BAP Tools roda no Windows (Tkinter), a partir da pasta de produção no OneDrive. O robô (`bap_automation.py`, PC DT-AMADMBAP-03) baixa os 7 relatórios do site BAP Tools (`172.19.20.76:8501`, **IP privado**) e grava as bases em `RELATORIOS\`.
- As telas fazem `bap_relatorios.py <id>` → `relatorios_nucleo.montar(id, raiz, hoje, params)` → dicionário do relatório → `bap_visual` (Tkinter, PDF, Excel).
- O alvo (roadmap, fases 3 a 6) é a **BAP Central na web**, acessível do celular, com login por pessoa, **sem** depender de Microsoft 365/Graph (CLAUDE.md, regra 9).
- O robô **continua no PC**, dentro da rede da empresa, porque o site BAP Tools é interno. A web não alcança a rede da empresa, e a rede da empresa **não será aberta para entrada**.
- Já existe um precedente que funciona: o BAP Ajuda 2.0 (Streamlit no Render, instância paga "1c-2g", disco persistente em `/var/data`, `BAP_DADOS_DIR`).
- Volumes (nov/2026, legado): TABELA_BAP ~15 MB (19 abas), ~12.500 linhas de ftPedidos (12 meses), ~18.000 linhas de estoque. É pequeno: cabe com folga num disco de 1 a 5 GB, com histórico de vários dias.

### Decisões do Alexandre que esta ADR respeita
Texto literal:
- CLAUDE.md, regra 9: "TI da empresa: nada que dependa de registro de aplicativo no Microsoft 365/Graph."
- R-20261120-092924-alexandre (trechos literais): "Nunca leia nem grave segredos (.env, chaves, tokens, senhas). Secret do GitHub só eu crio." · "Deploy só com a minha frase 'aprovo deploy vX.Y.Z', uma vez por versão."
- CLAUDE.md, regra 4: fuso America/Manaus, e "hoje fica fora do DU e da projeção".

Redação do recado (não é texto literal do Alexandre):
- R-20261120-080000-alexandre, item 3 de "O que preciso": "A produção continua no PC (pasta do OneDrive). Nada vai para lá sem o meu 'instale'." A mesma regra está no CLAUDE.md, regra 11.

## 2. As perguntas e as opções

### 2.1 Onde o relatório é montado

| Opção | Como | A favor | Contra |
|---|---|---|---|
| **M1. Na web** | O robô manda as **bases brutas** do dia; a web roda o mesmo `relatorios_nucleo.montar` do `main` | Um código só; filtros e parâmetros (`mes`, supervisor, vendedor) funcionam como no PC; prepara a onda das edições | Precisa de pandas/openpyxl no Render e de memória para montar; a versão do código da web e a do PC podem divergir (ver 4.4) |
| M2. No PC | O robô roda `montar` e manda o **dicionário pronto** (JSON) | A web é "burra": número igual por construção | Cada combinação de filtro tem de ser pré-calculada (explode); o dicionário tem função dentro (`rel["detalhe_pedido"]` é uma função) e não vira JSON sem a T-0002 cortar; edição na web fica impossível; rodada do robô mais longa |

**Escolha: M1**, com uma **conferência** vinda do PC: junto das bases, o robô manda os números dos relatórios da onda calculados no PC (JSON pequeno). Do Painel do Diretor, são os `kpis_export` das 3 abas RRM; da Inadimplência, os `kpis` do relatório (detalhe em 4.3). A web compara os dela com os do PC todo dia (seção 5).

### 2.2 Onde os dados ficam no Render

| Opção | Como | A favor | Contra |
|---|---|---|---|
| **A. Disco persistente** (`/var/data`) | Os arquivos do pacote do dia ficam como no PC (`RELATORIOS/`, `SISTEMA BAP/`, configs), e `montar(rid, raiz=/var/data/atual)` roda sem mudança | Zero reescrita do `bap_dados`; o mesmo modelo do BAP Ajuda (já conhecido); barato; o cache do `bap_dados` (pickle, VERSAO 27) funciona como está, gerado na web (4.1) | Disco preso a **uma instância** só (sem escalar na horizontal) e deploy com alguns segundos fora do ar [SUPOSIÇÃO: limitação documentada do Render para serviço com disco]; backup por snapshot do Render [SUPOSIÇÃO: diário, retenção curta]; concorrência de escrita fraca para as edições |
| B. Postgres gerenciado | As bases viram tabelas; a web consulta | Backup e restauração gerenciados; transação e auditoria para as edições; escala com mais instâncias | Reescrever a camada de dados (`bap_dados` lê Excel); o número do Diretor passa a sair de outro caminho e perde a garantia de "mesmo código"; custo a mais; migração longa |
| C. Disco agora, Postgres para as edições | Onda 1 e 2 em A; na onda 3 (edições), os diários digitados vão para o Postgres | Entrega rápida da leitura sem reescrever nada; o Postgres entra só onde ele ganha (escrita concorrente, auditoria, "só acrescentar linha") | Duas peças para manter a partir da onda 3 |

**Escolha: C.** Ondas 1 e 2 com **disco persistente**. O Postgres fica **proposto** para a onda 3 e será decidido numa ADR própria (0002), com o desenho de quem é a fonte da verdade do dado digitado enquanto o PC ainda grava os diários.

### 2.3 Como o dado sai do PC e chega na web

| Opção | Como | A favor | Contra |
|---|---|---|---|
| **P1. Push HTTPS do robô** | Ao fim da rodada (novo passo "4f", depois do 4e do BAP Ajuda), o robô faz um `POST` HTTPS do **pacote do dia** para a web | Só **saída** da rede da empresa (porta 443), como qualquer navegador; usa `requests`, que já está no `requirements.txt`; sem Git no PC; sem dado pessoal no GitHub | A web precisa de um endpoint de recebimento bem protegido |
| P2. Via GitHub (ramo de dados, como o BAP Ajuda) | O robô grava as bases num ramo e a web puxa | Padrão conhecido | O PC do robô **não tem Git**; base com CNPJ e nome de cliente no histórico do GitHub, todo dia (o legado pede para evitar) |
| P3. Armazenamento de objetos (S3 ou similar) | O robô sobe o pacote; a web lê | Desacopla | Mais um fornecedor, mais um segredo, mais custo |
| P4. A web puxa do PC | A web chama o PC | — | Exige **abrir a rede da empresa para entrada**: **descartada** |

**Escolha: P1.** Detalhe na seção 4.

### 2.4 Login

| Opção | Contra | Situação |
|---|---|---|
| Microsoft 365 / Entra ID / Graph | Exige registro de aplicativo (o TI não aprova; `msal` está no requirements só como legado) | **Descartada** (regra 9) |
| Google / outro provedor social | Conta pessoal de terceiro; nem todos têm | Descartada |
| Senha única compartilhada (como o `BAP_ADMIN_SENHA` do BAP Ajuda) | Sem perfil, sem saber quem viu o quê | Descartada |
| **Login próprio com perfis** | Precisamos cuidar de hash, sessão e troca de senha | **Escolhida** |

## 3. Decisão (resumo)

1. **Um serviço web Python 3.12 no Render** (plano pago), com **disco persistente** em `/var/data`, rodando o **mesmo** `relatorios_nucleo.montar` do `main`.
2. **Push HTTPS do robô** (PC → web), só de saída; a web nunca chama o PC.
3. **Login próprio com perfis**, sem Microsoft 365/Graph.
4. **Renderizador genérico** do contrato do relatório (T-0002): uma tela que desenha **qualquer** relatório que siga o contrato, sem código por farol.
5. **Postgres só na onda 3 (edições)**, em ADR própria.
6. **Produção do PC inalterada**: o PC continua sendo a produção até o Alexandre desligar farol a farol (fase 6 do roadmap).

## 4. Desenho

### 4.1 O serviço web

- **Pilha proposta:** FastAPI + Jinja2 (HTML montado no servidor, responsivo para o celular) + uvicorn. Gráfico em SVG gerado no servidor, sem biblioteca JavaScript pesada. [SUPOSIÇÃO: o modulo-web pode preferir Streamlit, como o BAP Ajuda; o critério é o login com perfil e o renderizador genérico. Streamlit atende mal o controle de sessão por perfil, por isso a preferência pela FastAPI. A troca de pilha pede um adendo a esta ADR.]
- **Dependências novas** (só na web, em `web/requirements.txt`, nunca no PC do robô): `fastapi`, `uvicorn`, `jinja2`, `python-multipart`. Pandas, openpyxl e pillow já estão no projeto. **Sem pyarrow.** Hash de senha com `hashlib.scrypt` (biblioteca padrão), sem dependência nova.
- **Caminhos:** `BAP_DADOS_DIR=/var/data` (variável de ambiente, como no BAP Ajuda). Todo caminho com `pathlib`; nada de `C:\` nem de `/tmp` fixo no código compartilhado. O `relatorios_nucleo` já recebe `raiz` como parâmetro.
- **Somente leitura nas ondas 1 e 2:** a web **não grava** nada nas bases nem nas configs. Ponto a corrigir antes da onda 1: `painel_diretor.calcular(ctx, ano, mes, gravar_hist=True)` grava `RELATORIOS/painel_diretor_hist.json`, e `relatorios_nucleo` o chama com o padrão. A web precisa chamar sem gravar (parâmetro ou variável de modo leitura): é um **pedido ao modulo-farois** (`relatorios_nucleo.py`, `painel_diretor.py`), sem mudar o número.
- **Cache:** o cache do `bap_dados` (`_CACHE_RELATORIOS`, pickle) é **gerado na própria web**, a partir das bases recebidas. **A web nunca aceita pickle vindo de fora** (abrir pickle recebido = executar código de terceiro): o recebimento recusa o pacote inteiro (4.3). `bap_dados.VERSAO` continua em 27.
  - **Onde o cache grava hoje:** em `<raiz>/RELATORIOS/_CACHE_RELATORIOS` (`bap_dados.carregar` grava e `bap_dados.do_cache` lê, pela `pasta_relatorios(raiz) / PASTA_CACHE`; o `custos_legado.pkl` dos custos do estoque legado, no bloco `comercial`; e o `meta_nucleo`, pela `caminho.parent / "_CACHE_RELATORIOS"`). Com `raiz=/var/data/atual`, ele cai **dentro do pacote**.
  - **Exceção aberta por esta ADR, até a pasta configurável chegar:** a web pode gravar **só** em `atual/RELATORIOS/_CACHE_RELATORIOS/`. Esse cache é de cada pacote: nasce vazio, é refeito na web e é apagado com o pacote (retenção, 4.2). Fora dessa pasta, nada dentro de `pacotes/` é gravado depois do pacote validado.
  - **Alvo, antes da onda 1:** pasta de cache configurável por variável de ambiente (`BAP_CACHE_DIR`, nome proposto), com o padrão de hoje quando a variável não existir, para o PC não mudar nada. Na web, `BAP_CACHE_DIR=/var/data/cache/<pacote>`. É **pedido ao engenheiro-dados** (`bap_dados.py`) e **ao modulo-metas** (`meta_nucleo.py`), sem mudar número nem a assinatura dos blocos. Quando entrar, a exceção acima fecha e o teste de "nada gravado em `pacotes/`" (seção 7) fica sem exceção.
  - O cache do `planner_nucleo` vai para `tempfile.gettempdir()` (fora do pacote; no Render, disco efêmero): pode ficar como está.
- **Fuso do serviço: `TZ=America/Manaus`, obrigatório.** Os núcleos chamam `date.today()` e `datetime.now()` por dentro, além do `hoje` que a web passa ao `montar` (4.6): `bap_dados._fontes` (o `hoje` da assinatura do cache), `meta_nucleo`, `planner_nucleo`, `visitas_nucleo` e `painel_diretor` (como reserva). Num servidor em UTC, depois das 20h de Manaus, eles já dariam o dia seguinte, e o DU e a projeção mudariam (regra 4, RN-GER-007).
  - `TZ` é uma variável de ambiente comum do serviço (**não é segredo**), declarada no `render.yaml` (governança, 4.7).
  - **Teste obrigatório** (modulo-web, roda no CI): com o relógio fixado em 00:30 UTC de um dia D (20:30 de D−1 em Manaus) e `TZ=America/Manaus`, `date.today()` dá D−1, igual a `datetime.now(ZoneInfo("America/Manaus")).date()`.
  - **Trava na partida:** se `date.today()` for diferente da data de Manaus (`zoneinfo`), o serviço não sobe e o `/saude` diz o motivo. Assim, um `TZ` esquecido não vira número errado em silêncio.

### 4.2 Disco `/var/data`

```
/var/data/
  pacotes/AAAAMMDD-HHMM/     # um pacote por rodada do robô, completo (manifesto + arquivos)
  atual -> pacotes/...       # ponteiro trocado só depois do pacote validado
  acumulado/por_sha/         # os arquivos de BKP_RELATORIOS_BAPTOOLS já recebidos, um por SHA-256 (fora de pacotes/)
  cache/                     # o cache do bap_dados, quando a pasta configurável existir (4.1)
  usuarios/                  # cadastro de login (hash, perfil); nunca no GitHub
  conferencia/               # os números PC × web por dia (seção 5)
  logs/                      # sem dado pessoal
```

- Retenção: os últimos 15 pacotes [SUPOSIÇÃO: ~60 a 100 MB por pacote, pelos tamanhos de hoje da `RELATORIOS/` (~106 MB, dos quais `Visitas/` ~45 MB e `BAP_AJUDA_RESPOSTAS/` ~12 MB); 15 × 100 MB ≈ 1,5 GB]; os mais velhos são apagados pela própria web. A `acumulado/` não entra na retenção: cada pacote aponta para ela por *hard link* (4.3), e o arquivo só some do disco quando nenhum pacote nem a `acumulado/` o usa.
- Tamanho do disco: **5 GB** para começar (folga para o histórico, a `acumulado/` e o cache).

### 4.3 O pacote do dia (push do robô)

- **Quem manda:** `bap_automation.py`, passo novo "4f", depois do 4e. Como o 4e, **falha aqui nunca derruba a rodada**, e o modo `--simular` não envia. É pedido ao modulo-robo.
- **O que vai:** exatamente os arquivos que `bap_dados._fontes` lista para **todos** os blocos que os relatórios da onda carregam, mais as configs que eles leem. O Painel do Diretor não é um farol só: `painel_diretor.calcular` chama o `montar` de `vc_meta`, `vc_markup`, `vc_saldo`, `vc_visitas`, `pl_inadimplencia` e `pl_giro` (`painel_diretor.py`, o laço dos "farois de origem"), e cada um deles carrega os seus blocos (`tabela`, `base`, `meta@AAAA-MM`, `executivo`, `inadimplencia` e o que mais usar). Onda 1, no mínimo:
  - `RELATORIOS/`: TABELA_BAP e a fotografia dela em `RELATORIOS/DADOS/` (entra na assinatura do cache), BASE_CLIENTE, `COORDENADAS_CLIENTES.json`, ESTOQUE_BAP, o PLANNER_BAP do mês da meta (`_planner_da_meta`), `Visitas/` (o arquivo de visita do mês, `meta_nucleo.achar_visitas_do_mes`, os Espelhos e `Visitas/PROSPECCAO/PROSPECCAO_AAAAMM.xlsx`), `BAP_AJUDA_RESPOSTAS/RESPOSTAS_BAP_AJUDA.xlsx` e `painel_diretor_hist.json`;
  - raiz: `meta_config.json`, `CATEGORIAS_PRODUTO.csv`, `planner_config.json` e a config do Planner do mês (`pastas_bap.config_do_planner`), com os feriados do mês (o DU depende deles, RN-GER-007), e `painel_diretor_config.json`. **Todas só para leitura** na web;
  - `BAP Ajuda 2.0/BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx` (bloco `tabela`, `catalogo_bap.achar_base`);
  - `SISTEMA BAP/BACKUP_RELATORIOS/BKP_RELATORIOS_BAPTOOLS/`: **todas** as fotos diárias dos títulos que o PC tem (`_fotos_de_titulos` lê a pasta inteira) e os relatórios de estoque legado que `_relatorios_de_estoque` lê (os 15 mais novos, `OLHAR_PARA_TRAS`). Como chegam, ver "Fotos e estoques" abaixo.
  - A lista exata sai do desenho da onda 1 (engenheiro-dados + modulo-robo), **gerada por código a partir de `_fontes`** para cada bloco que os 7 relatórios carregam (`vc_painel` e os 6 de origem), e não à mão. Teste: o pacote montado no PC e aberto numa pasta limpa dá os mesmos números do PC.
  - **Tamanho e memória:** isso leva o pacote a ~60 a 100 MB [SUPOSIÇÃO, pelos tamanhos de hoje], e uma tela do Painel do Diretor monta 7 relatórios. A memória é medida na onda 0 com uma base de teste sem dado pessoal (seção 7).
- **Fotos e estoques (`BKP_RELATORIOS_BAPTOOLS`):** o pacote é sempre **completo** para o `bap_dados`, mas os arquivos dessa pasta não são reenviados todo dia.
  1. O manifesto lista o conjunto **inteiro** de arquivos da pasta que o `_fontes` leria no PC naquele dia (nome, SHA-256 e tamanho).
  2. O zip leva só os arquivos cujo SHA-256 a web ainda não confirmou. O robô guarda no PC a lista dos SHA-256 confirmados.
  3. A web guarda cada arquivo uma vez só, em `/var/data/acumulado/por_sha/<sha256>`, fora de `pacotes/` e fora da retenção.
  4. Ao montar o pacote, a web cria `SISTEMA BAP/BACKUP_RELATORIOS/BKP_RELATORIOS_BAPTOOLS/` dentro dele, com *hard links* para a `acumulado/`, **exatamente** com os nomes e os SHA-256 do manifesto. Nem um a mais, nem um a menos: a web lê o mesmo conjunto que o PC. A foto do dia regravada no PC tem outro SHA-256 e entra como arquivo novo.
  5. Faltou algum SHA-256 na `acumulado/`: o pacote é recusado com a lista dos nomes que faltam (são datas, sem dado pessoal), e o robô reenvia na mesma rodada com esses arquivos. O modo `--completo` do 4f manda a pasta inteira (~21 MB hoje), para o primeiro envio e para a recuperação.
- **O que nunca entra no pacote** (nem na montagem pelo robô, nem no recebimento pela web): `tomtom_config*`, `google_maps_config*`, `visitas_config.json`, qualquer caminho com `auth/` (`**/auth/**`), `.env`, o `config.json` do BAP Ajuda, qualquer `.pkl` e qualquer coisa dentro de `_CACHE_RELATORIOS/`. O robô monta o pacote por **lista de permissão** (a lista gerada do `_fontes`), nunca copiando pasta inteira, e confere essa lista de proibidos antes de zipar. A lista vira uma constante com teste, usada nos dois lados.
- **Formato:** um `.zip` com `manifesto.json`:
  - data e hora da rodada (Manaus), o nome do PC;
  - a versão do código do PC (o commit que o `ATUALIZAR_DO_GITHUB.bat` instalou, T-0003);
  - o SHA-256 e o tamanho de cada arquivo, inclusive o conjunto inteiro da `BKP_RELATORIOS_BAPTOOLS`;
  - a **conferência**, calculada no PC:
    - Painel do Diretor: o `mes` usado e, para cada uma das 3 abas RRM, o título e os `kpis_export` (`paineis[i]["kpis_export"]` do `montar("vc_painel", ..., params={"MÊS": mes, "ANO": ano})`, que vêm de `painel_rrm.kpis(dr, visao)`). Os `rel["kpis"]` do `vc_painel` são os do Painel Executivo e **não** são o número do Diretor;
    - Inadimplência: os `rel["kpis"]` de `pl_inadimplencia`.
- **Envio:** `POST https://<serviço>.onrender.com/api/pacote`, com o token do robô no cabeçalho `Authorization`. O `requests` respeita o proxy da empresa (`HTTPS_PROXY`), se houver.
- **Recebimento na web:**
  1. token conferido em tempo constante;
  2. limite de tamanho (ex.: 200 MB) e só `.zip`;
  3. extração numa pasta nova, recusando caminho absoluto ou com `..`, e **recusando o pacote inteiro** se vier algum item da lista "nunca entra" acima (inclusive `.pkl` e `_CACHE_RELATORIOS/`) ou arquivo fora do manifesto. O log registra a regra que recusou, não o conteúdo;
  4. SHA-256 de cada arquivo conferido com o manifesto;
  5. a `BKP_RELATORIOS_BAPTOOLS` montada a partir da `acumulado/` (passo 4 de "Fotos e estoques");
  6. só então o ponteiro `atual` é trocado (troca atômica). Pacote ruim não derruba o pacote de ontem.
- **Segredos:** o token do robô é **criado pelo Alexandre**. No PC fica no cofre do Windows (`keyring`, como a senha do robô) ou em variável de ambiente. No Render fica numa variável de ambiente do serviço. Nunca no código, em log, em recado ou em commit.
- **Rede:** só **saída** HTTPS (443) do PC. Nada de porta aberta, VPN ou túnel para dentro da rede da empresa.
- **Opcional:** o envio manual pelo botão "Enviar para a web" no BAP Central, para quando a rodada falhar. Ele usa o mesmo código. [SUPOSIÇÃO: útil; decidir na onda 1.]

### 4.4 Versão do código: web × PC

- A web só recebe código novo com **"aprovo deploy vX.Y.Z"**. O PC só recebe com **"instale"**. As duas versões podem ficar diferentes por alguns dias.
- O manifesto traz a versão do PC. A web mostra a versão dela e a do pacote no rodapé de toda tela.
- Na **conferência**, dia com versões diferentes em código que muda número **não conta** para os 5 dias úteis (seção 5).
- Recomendação: a mesma tag `vX.Y.Z` para o "instale" e para o deploy, sempre que a mudança tocar número.

### 4.5 Login e perfis

- **Cadastro:** feito pelo **Alexandre**, perfil `admin`, numa tela da própria web. Guarda o usuário, o nome de exibição, o perfil, o hash scrypt com sal e a data da última troca. Fica em `/var/data/usuarios/`, nunca no GitHub. O primeiro admin entra por uma senha inicial que o Alexandre define numa variável de ambiente do Render e troca no primeiro acesso.
- **Sessão:** cookie `HttpOnly`, `Secure`, `SameSite=Lax`, assinado com uma chave que o Alexandre cria no Render. Expira em 12 h. Logout apaga a sessão.
- **Proteção:**
  - bloqueio de 15 min depois de 5 erros seguidos;
  - mensagem de erro igual para usuário e senha;
  - troca de senha obrigatória no primeiro acesso;
  - senha mínima de 10 caracteres.
  - [SUPOSIÇÃO: segundo fator (TOTP) fica para depois da onda 1.]
- **Perfis** (o que cada um vê, pela lista de `rid` do `relatorios_nucleo.CATALOGO`; a consulta por `rid` usa o `relatorios_nucleo.POR_ID`):

| Perfil | Onda 1 | Depois |
|---|---|---|
| `admin` (Alexandre) | tudo + usuários + conferência | — |
| `diretor` | Painel do Diretor (leitura) | Painel Executivo inteiro |
| `gerente` | Painel do Diretor + Inadimplência | todos os faróis |
| `pos_venda` (assistentes) | Inadimplência | faróis de pós-venda; edições na onda 3 |
| `supervisor` | — | faróis da equipe dele (filtro pelo supervisor) |
| `analista` | — | faróis do analista |
| `vendedor` | — | só a carteira dele [SUPOSIÇÃO: onda 2 ou depois] |

- Perfil é **lista de permissão**: o `rid` fora da lista dá 403. O filtro por pessoa (supervisor, vendedor) é aplicado **no servidor**, pelo `params` do `montar`, nunca escondido só na tela.
- **Logs:** usuário (o login, não o nome), `rid`, hora e resultado. **Sem dado de cliente** (CNPJ, nome, telefone, e-mail), sem senha e sem token.

### 4.6 Renderizador genérico do contrato (T-0002)

- **Depende da T-0002.** O contrato do relatório (as chaves que `montar` devolve: `kpis`, `tabelas`, `graficos`, `paineis`, `avisos`...) está sendo escrito em `.coord/contratos/` em paralelo. Esta ADR não repete o contrato: ela exige que ele seja **serializável em JSON** na parte que a web desenha.
- Achado para a T-0002: hoje `montar` põe uma **função** no dicionário (`rel["detalhe_pedido"]`) e as tabelas levam `edicao`, `detalhe` e `recortes`. O contrato precisa separar a parte "dado" (serializável) da parte "ação" (função do servidor, chamada por uma rota como `/r/<rid>/detalhe`).
- **Como funciona:** uma rota `/r/<rid>?params` chama `montar(rid, raiz=/var/data/atual, hoje=<hoje em Manaus>, params=...)` e entrega o dicionário a um conjunto de **componentes** (cartão de KPI, tabela com tom e chip, gráfico, painel em grade, aviso). Cada componente corresponde a uma chave do contrato.
- **Painel do Diretor = `vc_painel` com mês.** O `montar("vc_painel")` só monta o Painel do Diretor (as 3 abas RRM) quando há um mês escolhido (`relatorios_nucleo._abas_do_painel`, o `if mes:`; o mês vem de `periodo(ctx)`, e "TODOS OS MESES" dá `mes = 0`). A rota do Painel do Diretor manda **sempre** `params={"MÊS": <mês>, "ANO": <ano>}` explícitos (padrão: o mês de `hoje` em Manaus), nunca "TODOS OS MESES", e mostra só as 3 abas RRM (`paineis` com bloco `tipo: "rrm"`), não o resto do Painel Executivo. A conferência (4.3, seção 5) usa os mesmos `MÊS` e `ANO`.
- Bloco que o renderizador ainda não conhece (ex.: `tipo: "rrm"` do Painel do Diretor): aparece um aviso "bloco ainda não disponível na web", e a tela não quebra. A onda 1 precisa do bloco `rrm` (as 3 abas do Painel do Diretor) e dos blocos do `_painel_inadimplencia`.
- **Versão do contrato:** a web lê a versão que o contrato declarar e recusa versão maior que a que conhece, com aviso. Mudança incompatível = versão nova + ADR + recado (regra do contrato).
- **Hoje** = data de Manaus (America/Manaus), nunca a do servidor (UTC). Hoje fica fora do DU e da projeção (RN-GER-007): a web passa `hoje` explícito para o `montar`. Isso **não basta**: os núcleos também chamam `date.today()` por dentro, e por isso o serviço roda com `TZ=America/Manaus`, com teste e trava na partida (4.1).

### 4.7 Deploy e governança

- `render.yaml` é **governança**: o modulo-web propõe, e só entra com o recado do Alexandre "autorizo o merge do PR #N no commit <sha>".
- **Deploy automático desligado** (`autoDeploy: false`). O deploy de uma versão só acontece depois da frase do Alexandre **"aprovo deploy vX.Y.Z"**, uma vez por versão, sobre a tag `vX.Y.Z` do `main`. Quem aperta o botão (ou o deploy hook) é definido no desenho da onda 0; o deploy hook, se existir, é segredo e **só o Alexandre cria**.
- **Secrets do Render e do GitHub são criados só pelo Alexandre:** o token do robô, a chave da sessão, a senha inicial do admin e o deploy hook. Os agentes só citam o **nome** da variável, nunca o valor.
- **Produção do PC inalterada:** nada desta ADR muda a pasta de produção no OneDrive. O passo 4f do robô só chega ao PC pelo "instale" do Alexandre, com o backup `ANTES_<ASSUNTO>_<MÊS><ANO>` e a conferência byte a byte (T-0003).

## 5. Plano em ondas

| Onda | O quê | Pronto quando |
|---|---|---|
| **0. Fundação** | Serviço vazio no Render: login, perfis, tela de usuários, `/saude`, disco montado, deploy manual. Sem dado de cliente. | Login e bloqueio testados; "aprovo deploy v0.1.0" |
| **1. Primeira entrega (leitura)** | Passo 4f do robô + `/api/pacote` + renderizador genérico com os blocos da onda. **Painel do Diretor** (as 3 abas RRM do `vc_painel`, leitura) e **Farol de Inadimplência** (`pl_inadimplencia`). | Ver critério abaixo |
| **2. Faróis de leitura** | Os outros faróis, **em lotes por área** (Vendas e CRM; Pós-venda em leitura; Analista; Trade), sem código por farol, só blocos novos no renderizador quando faltarem. Filtros por supervisor e por vendedor. | Cada lote com 5 dias úteis batendo com o PC |
| **3. Edições** | Pós-venda (`_EDICOES_POS_VENDA`), NCC, garantias, autorizações, os textos do `painel_diretor_config.json`. **ADR 0002** antes: Postgres, quem é a fonte da verdade, como a edição volta para o PC, regra "só acrescentar linha", auditoria por usuário. | ADR 0002 aceita; simulação aprovada pelo Alexandre (regra 10) |
| **4. Desligar o Tkinter** | Farol a farol, depois de **2 semanas iguais** (roadmap, fase 6), só com a decisão do Alexandre. | Decisão registrada por farol |

### Critério da primeira entrega (onda 1)

1. A web mostra o Painel do Diretor (leitura) e o Farol de Inadimplência a partir do pacote do dia, no celular e no computador, só para os perfis permitidos.
2. **Os números batem com o PC por 5 dias úteis seguidos** (DU conforme RN-GER-007). Todo dia, a web compara os números dela com os da conferência que o PC mandou no manifesto (4.3), valor a valor e com os mesmos `MÊS` e `ANO`: do Painel do Diretor, os `kpis_export` de cada uma das **3 abas RRM** (`paineis[i]["kpis_export"]`), e não os `rel["kpis"]` do `vc_painel` (que são os do Painel Executivo); da Inadimplência, os `rel["kpis"]` de `pl_inadimplencia`. Moeda bate ao centavo; contagem e percentual, na casa decimal mostrada na tela.
3. Qualquer divergência **zera a contagem**, vira recado ao dono do número e só volta a contar depois de explicada. Dia sem pacote ou com versões de código diferentes (4.4) não conta, mas também não zera.
4. A conferência dos 5 dias fica em `/var/data/conferencia/` e é demonstrada pelo agente `testes` com valor × regra. O número do Diretor bate com o farol de origem.
5. Antes do deploy, a simulação (PNG das duas telas) vai ao Alexandre (regra 10). Depois, "aprovo deploy vX.Y.Z".

## 6. Custos

Valores mensais em dólar, **todos [SUPOSIÇÃO]**: são a tabela pública do Render como eu a conheço, e não foram conferidos nesta tarefa. Antes da onda 0, o Alexandre ou o po confirma em render.com/pricing e no painel da conta (onde o BAP Ajuda já roda).

| Item | Escolha | Custo/mês [SUPOSIÇÃO] |
|---|---|---|
| Web service | **Standard** (1 CPU, 2 GB), o mesmo "1c-2g" do BAP Ajuda. O `montar` com pandas sobre a TABELA_BAP precisa de memória; o Starter (512 MB) não deve bastar. | ~US$ 25 |
| Disco persistente | 5 GB | ~US$ 1,25 (~US$ 0,25/GB) |
| Postgres (só onda 3) | Plano básico com 1 GB de RAM | ~US$ 19 (a confirmar na ADR 0002) |
| Workspace / assentos | O mesmo da conta do BAP Ajuda | US$ 0 a mais, se o plano atual cobrir mais um serviço [SUPOSIÇÃO] |
| Tráfego | Pacote de ~60 a 100 MB/dia (as fotos e os estoques só quando novos, 4.3) e as telas | dentro da franquia [SUPOSIÇÃO] |
| **Total ondas 0 a 2** | | **~US$ 26/mês** |
| **Total a partir da onda 3** | | **~US$ 45/mês** |

Alternativas descartadas, para comparação [SUPOSIÇÃO]: Postgres desde já (~US$ 45/mês já na onda 1, mais a reescrita do `bap_dados`); armazenamento de objetos (P3) = mais um fornecedor e mais um segredo.

## 7. Consequências

**Boas**
- A leitura chega à web **sem reescrever** núcleo nenhum: o mesmo `montar`, o mesmo cache, o mesmo número.
- Nenhuma porta da empresa é aberta; nada de Microsoft 365/Graph; nada de dado de cliente no GitHub.
- O renderizador genérico faz cada farol novo custar "zero tela": só bloco novo, quando faltar.

**Custos e riscos**

| Risco | Mitigação |
|---|---|
| Disco = uma instância só; deploy com alguns segundos fora do ar | Aceitável para o uso interno; deploy fora do horário comercial de Manaus |
| `montar` lento ou sem memória no Render (uma tela do Painel do Diretor monta 7 relatórios: o `vc_painel` e os 6 de origem) | Cache do `bap_dados` na própria web; medir na onda 0, com o Painel do Diretor numa base de teste sem dado pessoal, o pico de memória e o tempo; se o Standard (2 GB) não bastar, subir de plano só com recado e o custo novo ao Alexandre |
| Versão do código web ≠ PC | Versão no manifesto e no rodapé; o dia não conta na conferência (4.4) |
| Vazamento de dado de cliente (LGPD) | Login obrigatório em toda rota (menos `/saude`); filtro por perfil no servidor; HTTPS; logs sem dado pessoal; pacotes antigos apagados |
| Token do robô vazado | Token só de envio (não lê nada); o Alexandre troca no Render e no cofre do PC |
| Rodada do robô mais longa ou falhando no envio | O 4f nunca derruba a rodada; o envio manual pelo BAP Central |
| A web gravar sem querer (`painel_diretor_hist.json`, cache dentro do pacote) | Modo leitura pedido ao modulo-farois antes da onda 1; teste que falha se a web gravar em `pacotes/` (e em `atual/`), **com uma exceção só**, `atual/RELATORIOS/_CACHE_RELATORIOS/`, enquanto a pasta de cache configurável não chegar (4.1). Depois dela, o teste fica sem exceção |
| Código Windows-only no caminho da web (`pywin32`, Outlook, Excel COM) | A web importa só os núcleos; `pywin32` já é condicional no requirements; teste de import no Linux no CI |

## 8. Próximos passos (cada um vira tarefa no quadro, pelo gerente-projetos)

1. **T-0002** fecha o contrato serializável, com a parte "ação" separada (`detalhe_pedido`).
2. **modulo-farois:** modo leitura do `painel_diretor.calcular` e do `relatorios_nucleo.montar` na web (sem mudar o número).
3. **engenheiro-dados:** a lista de arquivos do pacote, gerada por código a partir de `bap_dados._fontes`, para todos os blocos que o `vc_painel` e os 6 faróis de origem carregam (4.3); e a pasta de cache configurável (`BAP_CACHE_DIR`, nome proposto) no `bap_dados`, sem mudar número nem assinatura (4.1). O mesmo pedido da pasta de cache vai ao **modulo-metas** (`meta_nucleo.py`).
4. **modulo-robo:** passo 4f (envio do pacote + kpis da conferência), com `--simular` sem envio.
5. **modulo-web:** desenho da onda 0 (`docs/desenho/`), proposta do `render.yaml` (governança, com `TZ=America/Manaus`) e o serviço com login, a trava do fuso e o teste do fuso (4.1).
6. **Alexandre:** confirmar os custos (seção 6), criar os secrets no Render, aceitar esta ADR. **Aceitar esta ADR põe CNPJ e nome de cliente no Render** (as bases do pacote, no disco `/var/data`, atrás do login), como o BAP Ajuda 2.0 já faz hoje. Nada disso vai para o GitHub.
