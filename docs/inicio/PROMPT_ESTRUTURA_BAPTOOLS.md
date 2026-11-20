# Prompt — time de agentes, coordenação e migração do BAP Tools para o GitHub e o Render

> Cole tudo abaixo na conversa do Claude Code ligada ao repositório **baptools** (ambiente **Baptools-default**), ou diga: "leia `docs/inicio/PROMPT_ESTRUTURA_BAPTOOLS.md` e execute".
> A sessão de montagem roda **sem guardião** (é uma sessão manual). Responda sempre em português do Brasil.
> Adaptado do prompt do meu outro projeto (o padrão de time, recados, guardião e definição de pronto é o mesmo). O que muda está no **Contexto do BAP Tools** e nos passos 1, 8 e 12.

---

Você vai montar no BAP Tools um **time de agentes do Claude Code**, comandado por um gerente de projetos. O time tem:

- **donos de pastas**;
- um **guardião** que bloqueia edição fora do dono;
- **recados** entre agentes;
- um **quadro de tarefas**;
- **skills**;
- uma **definição de pronto**.

Depois o time conduz a **migração do BAP Central para a web, no Render**.

Eu sou o **dono do produto**: decido escopo, prioridade, aprovações e tudo o que é governança.

## Contexto do BAP Tools (leia antes do Passo 1)

### O que é

O BAP Tools são os programas da área comercial da **BAP AUTOPARTS** (Grupo PMZ, Manaus): faróis de gestão, painéis do Diretor, metas e RV, roteirização dos vendedores, pós-venda e o robô que baixa os dados do ERP.

- **Hoje:** roda em Windows, em Python 3.12 com Tkinter, numa pasta do OneDrive compartilhada por 3 máquinas.
- **Dados:** são arquivos (xlsx, csv, json) nessa pasta. Não há banco de dados.
- **Até agora:** o trabalho foi feito por um assistente (Claude Cowork) ligado ao computador. Daqui em diante o **GitHub é a fonte da verdade** e o trabalho é feito aqui.

### Objetivo

1. Código no GitHub, mantido por este time. Eu não preciso mais do Cowork para mexer no BAP Tools.
2. **O BAP Central inteiro na web, no Render.** São todos os faróis, painéis, cadastros e edições hoje acessados pelo `bap_central.py`, acessíveis por login, do computador e do celular.
3. O **robô** continua numa máquina Windows, porque depende do Excel, do Outlook e do navegador logado. Ele passa a **enviar os dados** para o Render.

### Programas

O código fica na raiz do repositório, como na pasta.

| Programa | Arquivos |
|---|---|
| Lançador | `bap_central.py` (4 quadrados: Pré-venda, Vendas e CRM, Pós-venda e Logística, Analista Comercial; mais Trade) e `bap_janela.py` |
| Faróis | `bap_relatorios.py` (tela Tkinter) + `relatorios_nucleo.py` (regras, ~920 KB). Cada farol é um `id` (`pv_pedidos`, `vc_meta`, `vc_visitas`, `pl_inadimplencia`, `vc_painel`…) e `rn.montar(id, raiz, params=…)` devolve um dicionário com cartões, tabelas, gráficos e avisos |
| Painéis do Diretor | `painel_diretor.py`, `painel_rrm.py` (3 abas no modelo RRM), `painel_cartoes.py`, `visao_executiva.py`, `painel_farol.py` |
| Visual e exportação | `bap_visual.py` (cores, cartões RRM, tabelas, exportação PDF reportlab / Excel openpyxl), `parcial_imagem.py` (PNG/PDF das parciais para o WhatsApp) |
| Metas e RV | `meta_nucleo.py`, `bap_meta.py` (Gerador de Meta), `saldo_meta.py`, `bap_champions.py` (campanhas) |
| Rota | `planner_nucleo.py`, `bap_planner.py` (Planner, tela pesada com mapa/calendário), `rota_lugar.py`, `geocodificar.py`, `geografia.py`, `zonas_padrao.py`, `agenda_cidades.py`, `email_rota.py` |
| Visitas | `visitas_nucleo.py`, `visitas_maxima.py` (robô Playwright da Máxima), `prospeccao_forms.py`, `respostas_bap_ajuda.py` |
| Pós-venda e crédito | `pos_venda.py`, `garantias.py`, `ncc_controle.py`, `transportadoras.py`, `autorizacoes.py`, `expositores.py`, `email_inadimplencia.py`, `cobranca_whatsapp.py`, `email_parcial.py` |
| Produto | `catalogo_bap.py`, `familia_nucleo.py`, `cnae_bap.py`, `oportunidade_nucleo.py`, `bap_oportunidade.py` |
| Analista | `bap_analista.py` (abriga Planner, Gerador de Meta e cadastros) |
| Robô e dados | `bap_automation.py` (robô: Playwright no site BAP Tools, Excel COM para recalcular, keyring, Outlook), `dados_bap.py`, `bap_dados.py` (cache dos faróis; **VERSAO 27 nunca sobe**, regra nova = marca de cache nova), `xlsx_rapido.py`, `base_cliente.py`, `solicitacao_bap.py`, `conferir_solicitacao.py`, `aviso_arquivo.py`, `pastas_bap.py` |
| Testes | `smoke_relatorios.py` e `smoke_processos.py`. Precisam da pasta de dados real; sem ela, muitos checks são pulados ou falham. Falhas conhecidas: Farol DDR ×3, Entregas, Resumo gerencial `tm_expositores`, recorte 000040, Farol de Visita, NCC e `contatos_vcf` ausente |
| Scripts Windows | `*.bat` (abrir, instalar, reparar Python, rodar testes) e `tarefa_bap.xml` (tarefa agendada do robô) |
| Recursos | `SISTEMA BAP/recursos/` (logo, cabeçalho e fonte Poppins) |
| Referências | `CATEGORIAS_PRODUTO.csv`, `COORDENADAS_CIDADES_BAIRRO_BAP.xlsx`, `SEGMENTACAO_BAP.xlsx` |

- **Dependências:** pillow, openpyxl, pandas, reportlab, requests, playwright, keyring, msal (sem uso: o TI proíbe Graph) e pywin32 (só no Windows). Veja o `requirements.txt`.
- **Fora do repositório**, na pasta do OneDrive:
  - os dados: `RELATORIOS/` (TABELA_BAP, BASE_CLIENTE, PLANNER, Espelho da Máxima, acompanhamentos) e `SISTEMA BAP/` (backups, logs, `PLANNER_MESES/`, `auth/`);
  - as configurações com dado digitado ou pessoal: `planner_config.json`, `meta_config.json`, `champions_config.json`, `transportadoras_config.json`, `painel_diretor_config.json` etc.;
  - os arquivos com chave: `tomtom_config.json`, `google_maps_config.json`, `visitas_config.json` e `BAP Ajuda 2.0/config.json`. **Nunca abrir.**
- **App irmão:** o **BAP Ajuda 2.0** é outro repositório (`bapajuda2.0`), em Streamlit no Render, com disco `/var/data`. As respostas dele vão para o ramo `respostas`. Ele não é deste time; integração só por contrato.

### Documentos legados (`docs/legado/`)

Leia antes do Passo 1.

- `diario_maestro_sistemas.md`: o diário do Cowork. A **seção 3** tem as regras; a 5, o estado e as instalações; a 6, as pendências.
- `processo_bap_out2026.md`: as regras de cálculo de cada farol.
- `INSTALACAO_ROTA_1710.md`: o item 0 tem as **regras da rota em vigor**.

São a base das RN do Passo 10. Em conflito entre eles, vale o mais recente e a seção 3 do diário.

### Máquinas

| Máquina | Uso |
|---|---|
| NT-AMADMVD13 (notebook do Alexandre) | O BAP Central é usado aqui |
| DESKTOP-PRUKJF6 (desktop do Alexandre) | Tem Git; o BAP Central também é usado aqui |
| DT-AMADMBAP-03 (Juliana) | Roda o robô na tarefa agendada e é a única que grava o acompanhamento de pós-venda. **Não tem Git** |

## Passo 1 — Levantamento (não crie nada ainda)

1. Leia o repositório e os documentos legados. Confirme:
   - a linguagem e as dependências;
   - o que é tela (Tkinter), o que é regra pura (núcleos) e o que é integração (robô, Excel COM, Outlook, Playwright).
2. Liste os **módulos de negócio**. Pelo código, proponho [SUPOSIÇÃO; ajuste se o código mostrar outra divisão]:

   | Módulo | Abrange |
   |---|---|
   | comercial | faróis de vendas, Painel Executivo e do Diretor, Visão executiva |
   | metas | metas, RV, saldo, campanhas |
   | rota | Planner, roteirização, geocodificação, JSON para a Máxima |
   | visitas | Espelho da Máxima, Farol de Visita, prospecção, BAP Ajuda |
   | posvenda | entregas, garantias, NCC, devoluções, transportadoras, expositores |
   | credito | inadimplência, cobrança, autorização de venda |
   | produto | catálogo, família, giro, markup, preço, oportunidades e kits |
   | integracao | robô, TABELA_BAP, BASE_CLIENTE, solicitação, fotografia de dados |

3. **Problema central:** o `relatorios_nucleo.py` é um monólito com os faróis de todos os módulos. Proponha:
   - **fase 0:** ele tem dono único (`modulo-farois`);
   - **ADR-0001:** dividir em `farois/<modulo>/`, mantendo `rn.montar` e os ids;
   - a ordem da divisão.
   Até a divisão, mudanças de outros módulos nele vão por recado ao dono.
4. Proponha o time numa tabela `agente | papel | caminhos que altera | modelo`:
   - **Fixos:** `gerente-projetos`, `engenheiro-software`, `designer-ux`, `testes`, `corretor-redundancias`.
   - **`engenheiro-apps`:** dono do shell web (Render: login, navegação, menu do BAP Central, renderização genérica de "relatório") e do shell Tkinter enquanto ele existir (`bap_central.py`, `bap_janela.py`, `bap_relatorios.py` como casca).
   - **`engenheiro-dados`** (no lugar de `banco-dados`, porque hoje não há banco). É dono:
     - da fotografia de dados (`dados_bap.py`, `bap_dados.py`, `xlsx_rapido.py`);
     - do envio do robô para o Render;
     - da persistência no Render (disco e, se houver ADR, Postgres);
     - da migração dos dados digitados para a web.
   - **Um `modulo-<nome>`** por módulo do item 2.
5. Proponha os **comandos de qualidade**:
   - `python -m compileall -q .`;
   - `ruff check` (a adicionar, ADR);
   - `pytest tests/` (a criar);
   - os smokes atuais só com a pasta de dados (`BAP_DADOS=<pasta>`).
   Diga também:
   - onde fica cada tipo de arquivo;
   - como os testes vão rodar sem dados reais: **fixtures anonimizadas** em `tests/dados_exemplo/`, sem CNPJ, nome, telefone ou e-mail reais.
6. **Pare e me mostre** a tabela, os comandos e as premissas. Só siga com o meu "ok".

## Passo 2 — Estrutura a criar

```
CLAUDE.md                        guia do repositório (dono: gerente-projetos)
.claude/settings.json            sessão principal = gerente-projetos, permissões e hooks (dono: dono do produto)
.claude/agents/<agente>.md       um arquivo por agente (dono: dono do produto)
.claude/skills/<skill>/SKILL.md  protocolo-recados, status, feature, entrega (dono: dono do produto)
.claude/hooks/guarda-donos.mjs   guardião de donos (dono: dono do produto)
.claude/hooks/guarda-bash.mjs    guardião do shell (dono: dono do produto)
scripts/coord.mjs + scripts/coord-lib.mjs  CLI de coordenação (dono: dono do produto; Node ≥ 18, só para coordenação)
.coord/donos.json                mapa caminho → dono (só o dono do produto altera)
.coord/quadro.md                 quadro da sprint (gerente)
.coord/tarefas/T-nnnn.md         uma tarefa por arquivo (gerente)
.coord/modelos/tarefa.md, recado.md
.coord/contratos/                contratos entre módulos: funções públicas dos núcleos, formato do dicionário de relatório, API web, eventos (engenheiro-software)
.coord/diario/<agente>.md        diário de cada agente (só acrescentar linha)
docs/produto/01..07              visão, requisitos (RF), regras (RN), arquitetura, roadmap, integrações, agentes (gerente)
docs/decisoes/NNNN-*.md          ADRs (engenheiro-software)
docs/desenho/T-nnnn.md           desenho técnico por tarefa (engenheiro-software)
docs/design/                     especificações e referências visuais (designer-ux)
docs/testes/T-nnnn.md            matriz de cenários (testes)
docs/qualidade/redundancias/     relatórios e catálogo RD-nnnn (corretor-redundancias)
docs/status/AAAA-MM-DD.md, docs/backlog.md  (gerente)
docs/legado/                     congelado (só leitura; é a memória do Cowork)
docs/inicio/                     congelado (este prompt)
```

**Governança** = `.claude/**`, `.coord/donos.json`, `scripts/coord*.mjs`, `.github/**` e `render.yaml`. Nenhum agente altera. A mudança vai como proposta (patch) por recado para mim e só entra com a minha autorização escrita.

## Passo 3 — Recados (repositório próprio desde o primeiro dia)

- Crie um **repositório privado separado**, `<dono>/baptools-recados`, com:
  - `recados/<destino>/R-AAAAMMDD-HHMMSS-<remetente>.md`;
  - `recados/anexos/`;
  - `lidos/<agente>.txt`.

  Destinos: cada agente, `dono` (eu) e `todos`.
- O `coord.mjs` grava e lê **direto no GitHub**: commit pela API com `expectedHeadOid` e, em conflito, relê e tenta de novo.
  - Sem rede, não grava e avisa.
  - Nada de clone local sincronizado por agendador nem junções de pasta.
  - O token fica só em variável de ambiente (`RECADOS_TOKEN`, no ambiente Baptools-default), nunca em arquivo ou log.
- Recados e lidos **não entram** nos commits do repositório de código.
- **Convivência com o Cowork na transição:** os "Maestros" do projeto BAP no Claude (Comercial e Sistemas) trocam recados em `claude/recados/` do Projeto do Claude. Este time não lê esse lugar. O que chegar de lá eu colo no chat, e o gerente grava como recado `aviso` (regra 3 do Passo 7).
- Formato do recado (gerado só pela CLI):

```markdown
---
id: R-20261111-140512-modulo-comercial
de: modulo-comercial
para: [modulo-metas]
cc: [gerente-projetos]
tipo: pedido          # pedido | pergunta | resposta | aviso | bloqueio | entrega | revisao
prioridade: alta      # alta | normal | baixa
tarefa: T-0012
responde_a: null
encerra: false        # true numa resposta = assunto resolvido
criado_em: 2026-11-11T14:05:12-04:00
---
# Assunto
## Contexto
## O que preciso / o que mudou
## Pronto quando
```

- **Regras do recado:**
  - a CLI recusa recado com seção vazia (Contexto e O que preciso são obrigatórios);
  - recado é imutável: nunca editar nem apagar;
  - `bloqueio` vai com cópia automática ao gerente;
  - nenhum agente grava `de: dono`.
- Comandos do `coord.mjs`:

  | Comando | Faz |
  |---|---|
  | `caixa <agente>` | recados abertos e não lidos do agente |
  | `enviar --de --para [--cc] --tipo --tarefa --prioridade --assunto --corpo "Contexto \| O que preciso \| Pronto quando" [--arquivo] [--responde-a] [--encerra]` | grava recado novo |
  | `lido <agente> <id>` | marca como lido |
  | `ler <id>` · `fio <id>` | lê um recado / a conversa inteira |
  | `pendencias` | pedidos sem resposta, bloqueios e não lidos por agente, com idade |
  | `dono <caminho>` | dono do caminho pelo `donos.json` |
  | `verificar [<agente>] [--base origin/main] [--por-commit <faixa>] [--por-dono]` | confere no git se cada agente só alterou o que é dele (saída 0 ok, 1 violação, 2 erro de uso) |

- Escreva testes da CLI: envio, recusa de seção vazia, imutabilidade e `verificar`.

## Passo 4 — Donos e guardião

- **`.coord/donos.json`:** lista de `regras` `{padrao, dono}` em glob; **a primeira que casa vence**.
  - Valores especiais: `congelado` (ninguém altera; vale para `docs/legado/**` e `docs/inicio/**`) e `sem-dono` (caminho não mapeado = bloqueado).
  - Campo `somente_leitura` para pastas fora do repositório que ninguém altera.
  - Como o código hoje está **todo na raiz**, mapeie **arquivo a arquivo** (ex.: `planner_nucleo.py` → `modulo-rota`) até a reorganização em pastas (ADR).
- **`guarda-donos.mjs`** (hook `PreToolUse` em `Edit|Write|MultiEdit|NotebookEdit`):
  1. lê o JSON do hook no stdin;
  2. identifica o agente pelo argumento do frontmatter do agente ou pelo `agent_type` (a variável `BAP_AGENTE` só vale na sessão principal);
  3. **bloqueia com exit 2** quando o caminho não é do agente.
  - Sessão manual sem agente = liberada.
  - `BAP_GUARDA=off` desliga.
- **`guarda-bash.mjs`** (hook `Bash`) bloqueia:
  - `git push --force`, `-f`, `--delete`;
  - `reset --hard` em branch compartilhado;
  - `rm -rf` fora do repositório;
  - leitura de `.env` e dos arquivos de chave (`*tomtom_config*`, `*google_maps_config*`, `visitas_config.json`, `config.json` do BAP Ajuda);
  - commit/push por quem não é o gerente.
- **Teste do guardião:** um agente tentando editar fora do seu caminho → bloqueado; dentro → liberado.

## Passo 5 — `.claude/settings.json`

- `"agent": "gerente-projetos"` (o gerente é a sessão principal).
- `permissions.allow`:
  - comandos do `coord.mjs`;
  - `python -m compileall`, `ruff`, `pytest`;
  - `git status|diff|log|branch`;
  - `git push origin main` e branches de nuvem (`nuvem/*`).
- `permissions.deny`:
  - `Read(./.env*)`, `Read(./**/.env*)`, `Read(./**/*tomtom_config*)`, `Read(./**/*google_maps_config*)`;
  - push com force ou delete;
  - merge com `--admin` ou `--auto`.
- `hooks`: `guarda-donos` (Edit/Write), `guarda-bash` (Bash, pré e pós).

## Passo 6 — `CLAUDE.md` (curto, é lido em toda sessão)

O `CLAUDE.md` contém:

- **O projeto em 2 linhas**; idioma pt-BR; estrutura de pastas; comandos.
- **O time e a regra de ouro**; frentes local × nuvem; git só pelo gerente; a definição de pronto do Passo 7.
- **Regras inegociáveis** (as do Passo 1 e estas, que já valem no BAP):
  1. **Regra de negócio em função pura, com teste citando a RN** (`def test_RN_META_003_...`).
  2. **Números:** os cálculos atuais (float em R$, arredondamento só na exibição) não mudam sem RN e ADR. Código novo de dinheiro usa `Decimal`.
  3. **Datas e dias úteis:**
     - fuso **America/Manaus**;
     - dia útil = seg a sex, menos os feriados do Planner do mês;
     - **o dia de hoje fica fora da conta do DU e da projeção** (o mês corrente vai até ontem);
     - projeção = real ÷ DU fechados × DU do mês.
  4. **Segredos só em variável de ambiente ou `.env`.** Nunca no código, em log, em recado ou em commit. Ler os arquivos de chave da pasta é proibido.
  5. **Dados pessoais:** sem dado pessoal de cliente ou vendedor em log, fixture ou print de recado (CNPJ, nome, telefone, e-mail).
  6. **Dado digitado é intocável:** diários de edição (`_EDICOES_POS_VENDA`, `_NCC`, `_GARANTIAS`, `_AUTORIZACOES`), `champions_config.json`, `transportadoras_config.json`, `painel_diretor_config.json`. Planilhas de acompanhamento: só acrescentar linha.
  7. **`bap_dados.VERSAO` fica em 27.** Regra nova de cache = marca nova na assinatura do bloco.
  8. **Regras de negócio fixadas pelo Alexandre** (detalhe e histórico no diário legado, seção 3):
     - **desafio comercial em todo lugar**; meta RH só no Exportar para o RH, no e-mail e na parcial de RV;
     - faturado = líquido de devolução, pela data da NF;
     - positivação = cliente com líquido > 0 no mês;
     - CNPJs internos do grupo fora (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA);
     - conta 000040 = testes, fora de tudo;
     - **estado do faturamento = filial da nota** (0101002 AM, 0101004 RR, 0101005 + 0101007 PA, 0101006 MA, 0101003 AP, 0101001 MT);
     - vendedor inativo sem movimento fica oculto;
     - nome nos materiais: "BAP AUTOPARTS";
     - BAP Ajuda não mostra preço.
  9. **TI da empresa:** nada que dependa de registro de aplicativo no Microsoft 365/Graph (sem SSO Microsoft).
  10. **Rota:** as regras do item 0 do `INSTALACAO_ROTA_1710.md` mandam. Regra nova de rota atualiza o doc de RN e a tela "Mecânica da rota".
  11. **"Simule" = mostrar antes.** Tela ou documento novo vai primeiro como **PNG** para eu aprovar (regra 6 do Passo 7).
  12. **Instalação no PC Windows** (enquanto o desktop existir): sempre com **backup** em `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_<ASSUNTO>_<MÊS><ANO>` e conferência byte a byte, pelo script de atualização do Passo 12.

## Passo 7 — Regras de trabalho (vão no CLAUDE.md e no doc 07)

1. **Regra de ouro:** cada agente altera só o que é seu; para o resto, recado ao dono. Nunca contornar o guardião com shell, cópia ou pedindo a outro agente "por você".
2. **Esteira permanente:** tudo o que o dono do produto pede, e o que é preciso para entregar, entra em execução. **Backlog só com a minha autorização escrita** (recado ou chat com a palavra "backlog").
3. **Chat vira recado:** o que eu disser ao gerente no chat ele grava como recado `aviso` para `todos`, com o texto literal, data e hora e o que foi feito.
4. **Toda entrega passa por 3 crivos antes de fechar:**
   - `testes`: critérios e defeito funcional, inclusive **valor exibido × fórmula da RN** e **rótulo × valor**;
   - `corretor-redundancias`: excessos e repetições;
   - `engenheiro-software`: revisão final; 🔴 bloqueia.

   Tela passa também pelo `designer-ux`. **Número que vai para o Diretor** (Painel do Diretor, faróis) é conferido contra o farol de origem.
5. **Telas e documentos:**
   - uma informação, um lugar;
   - avisos só na área de **Alertas**;
   - eventos (aprovado, enviado, recusado) só no **Histórico**;
   - "o usuário precisa disso para decidir ou agir agora? Se não, sai".
6. **Imagens para aprovação:** tela nova ou refeita e documento gerado (PDF, parcial, relatório) vão primeiro como imagem PNG em `recados/anexos/` para eu aprovar. Só depois vão para o código.
7. **Git só pelo gerente:**
   - início da rodada: `git pull --no-rebase origin main`;
   - fim da rodada, com compileall/ruff/pytest verdes: um commit por dono (`T-nnnn: resumo` + trailer `Agente: <dono>`) → pull → checks de novo → push só se verde;
   - proibido: force push, rebase do main, push vermelho, apagar histórico.
8. **Frentes local × nuvem:**
   - cada tarefa roda num lugar só (coluna **Onde** no quadro);
   - a nuvem trabalha em `nuvem/T-nnnn-<assunto>`, só nos caminhos travados para ela, com PR em rascunho até ficar pronto;
   - "local" = uma máquina Windows com a pasta de dados (para smoke real e Tkinter).
9. **CI econômico desde o início:**
   - nos PRs, rodar só o que mudou;
   - ignorar commits só de docs/coordenação;
   - não repetir o CI para o mesmo código;
   - poucos jobs, com cache;
   - matriz completa só à noite (dias úteis) e na véspera de entrega oficial;
   - só o gerente dispara workflow manual.
10. **Governança** (`.claude/**`, `.coord/donos.json`, `scripts/coord*.mjs`, `.github/**`, `render.yaml`): mudança só com recado meu "autorizo o merge do PR #N no commit <sha>".
11. **Definição de pronto:**
    - compileall + ruff + pytest verdes;
    - critérios demonstrados por teste;
    - corretor sem achado alto aberto;
    - engenheiro sem 🔴;
    - `coord.mjs verificar` sem violação;
    - quadro, backlog e docs atualizados;
    - se mexe em número, conferência contra o farol de origem anexada.

## Passo 8 — Agentes

Todo agente tem frontmatter com:

- `name`, `description` (quando usar), `tools`, `color`;
- `model`: `opus` para gerente, engenheiros, testes, designer e corretor; `sonnet` para os módulos;
- `skills: [protocolo-recados]`;
- o hook do guardião com o próprio nome:

```yaml
hooks:
  PreToolUse:
    - matcher: "Edit|Write|MultiEdit|NotebookEdit"
      hooks:
        - type: command
          command: "node .claude/hooks/guarda-donos.mjs <agente>"
```

E todos terminam com o **Protocolo comum** (troque `<agente>`):

```markdown
## Protocolo comum do time (idêntico em todos os agentes)
1. Comece sempre com `node scripts/coord.mjs caixa <agente>` e trate os recados abertos antes da tarefa nova.
2. Leia a tarefa em `.coord/tarefas/T-nnnn.md`, o `CLAUDE.md` e os docs de `docs/produto/` que ela citar (e o legado, se a tarefa mexe em regra antiga).
3. Altere só os seus caminhos (`.coord/donos.json`). O guardião bloqueia o resto; nunca o contorne.
4. Precisa de algo fora deles? Recado ao dono (`node scripts/coord.mjs dono <caminho>`): `enviar --de <agente> --para <dono> --tipo pedido --tarefa T-nnnn --assunto "..." --corpo "Contexto | O que preciso | Pronto quando"`.
5. Responda com `--responde-a <id>`; quem resolve encerra com `--encerra`. Informativo lido: `lido <agente> <id>`.
6. Bloqueado? `--tipo bloqueio` e avance no que não depende do bloqueio.
7. Recados objetivos, autocontidos, em português, citando arquivos, contratos e regras (`RN-...`). Recado é imutável.
8. Ao terminar: compileall, ruff e pytest do que tocou; `node scripts/coord.mjs verificar <agente>`; recado `entrega` ao gerente (o que fez, arquivos, testes, pendências) e linha em `.coord/diario/<agente>.md` (`AAAA-MM-DD — T-nnnn — resumo`).
9. Resposta final a quem te chamou: resumo da entrega em até 10 linhas, com as premissas.
```

### gerente-projetos

- **Frontmatter:**
  - `tools: Agent, Read, Grep, Glob, Write, Edit, Bash`;
  - `initialPrompt: "Abra a sessão: rode node scripts/coord.mjs pendencias e caixa gerente-projetos, leia .coord/quadro.md e me dê o status em até 10 linhas, com bloqueios e o próximo passo."`
- Comanda o time e responde ao dono do produto. **Não escreve código.**
- Como comanda:
  1. **Entender** o pedido pelos docs (inclusive o legado) e pelo quadro. Se faltar dado, assume o padrão e registra a premissa.
  2. **Planejar** a tarefa `T-nnnn` pelo modelo, com critérios verificáveis, e atualizar o quadro.
  3. **Desenho primeiro** quando mexe em contrato, dado persistido ou mais de um módulo: engenheiro-software e engenheiro-dados.
  4. **Delegar** pela ferramenta Agent com prompt autocontido: no máximo 3 em paralelo, e só sem dependência entre eles.
  5. **Acompanhar** `pendencias` após cada retorno e conferir as caixas a cada 5 min. Decisão vira recado `aviso` para `todos`; decisão estrutural vira pedido de ADR.
  6. **Validar** com testes, corretor e revisão final.
  7. **Fechar:** quadro, backlog e status, mais recado `entrega` ao dono com como testar em 5 passos.
- Faz o git da rodada.
- Manda ao dono, às 18h (Manaus), o status do dia com o percentual do cronograma e os riscos.
- Ordem padrão de uma funcionalidade: engenheiro-software (desenho) → engenheiro-dados (dados) → modulo-* → testes + corretor-redundancias (+ designer-ux nas telas) → engenheiro-software (revisão) → gerente (fechamento).
- Caminhos: `.coord/` (menos `donos.json` e `contratos/`), `CLAUDE.md`, `docs/produto/`, `docs/status/`, `docs/backlog.md` e o resto de `docs/` sem dono.

### engenheiro-software

- Guardião da arquitetura e da qualidade técnica.
- Faz:
  - desenho técnico em `docs/desenho/T-nnnn.md`;
  - contratos em `.coord/contratos/`, em especial o **contrato do relatório** (o dicionário que `rn.montar` devolve: `kpis`, `tabelas`, `graficos`, `paineis`, `avisos`). Ele é a ponte entre os núcleos e qualquer tela, Tkinter ou web. Mudança incompatível = nova versão + ADR + recado aos consumidores;
  - regras de fronteira no CI: módulo só importa pacotes comuns e o `contracts` dos outros, depois da reorganização;
  - ADRs, CI, `pyproject.toml`/ruff, scripts, raiz e `requirements*.txt`.
- **Revisão final** de toda tarefa, com saída 🔴 bloqueia / 🟡 corrigir / 🟢 sugestão e arquivo:linha. Confere:
  - regra no domínio com teste citando a RN;
  - tipos vindos de contratos;
  - perfil de acesso na web (quem vê o quê);
  - idempotência, segurança, simplicidade e `verificar`.
- Problemas vão por recado ao dono; não corrige código alheio.
- Impõe: type hints nas funções públicas novas, validação de entrada na web, erros de negócio com código da RN, logs sem dado pessoal, nenhuma dependência pesada sem ADR.
- Caminhos: `.coord/contratos/`, `docs/decisoes/`, `docs/desenho/`, `.github/` (por proposta, porque é governança), `scripts/` (menos `coord*`), arquivos de raiz de projeto (`pyproject.toml`, `requirements*.txt`, `README.md`) e, até a divisão, nenhum `.py` de negócio.

### engenheiro-apps

- **Shell web (Render):**
  - login próprio, com usuários e perfis (diretor, gerente, supervisor, analista, assistente), senha com hash e sessão segura. Sem SSO Microsoft (regra do TI);
  - menu igual ao BAP Central (quadrados por área);
  - **renderizador genérico do contrato de relatório**: cartões no modelo RRM, tabelas com filtro e ordenação, gráficos, exportar PDF/Excel reusando os exportadores do `bap_visual`, filtros na URL;
  - layout responsivo para o celular.
- **Shell Tkinter** enquanto existir: `bap_central.py`, `bap_janela.py`, a casca do `bap_relatorios.py`.
- Revisão técnica das telas dos módulos (desempenho, sem regra de negócio na tela), com saída 🔴/🟡/🟢 por recado.
- Liga as transições que o designer especifica.
- Antes de cada deploy: build verde e health check respondendo.
- Caminhos: `web/` (ou o nome do ADR) e os arquivos de shell Tkinter.

### engenheiro-dados

- Dono de todos os dados persistidos e do caminho **robô → Render**.
- Faz:
  - a fotografia de dados (`dados_bap.py`, `bap_dados.py`, `xlsx_rapido.py`; a fotografia `RELATORIOS\DADOS\*.csv.gz` + `_estado.json` já existe e é a candidata natural para o envio);
  - o **upload autenticado** do robô para o Render: token em variável de ambiente dos dois lados, idempotente, com checagem de CRC, avisando no log da rodada;
  - a persistência no Render: disco persistente (padrão do BAP Ajuda: `/var/data`) e, se houver ADR, Postgres;
  - a **migração dos dados digitados** (pós-venda, NCC, garantias, autorizações, campanhas, transportadoras, Planner, metas) para a web, **sem perder nem duplicar**, com período de convivência em que o PC lê da web;
  - as fixtures anonimizadas de `tests/dados_exemplo/`;
  - o dicionário de dados em `docs/dados/`.
- Nenhum módulo lê o arquivo de outro módulo direto: o pedido é recusado, com sugestão de função pública ou API.
- Caminhos: `dados_bap.py`, `bap_dados.py`, `xlsx_rapido.py`, `tests/dados_exemplo/`, `docs/dados/` e a pasta de persistência da web.

### designer-ux

- Use o arquivo `designer-ux.md` que já está pronto no outro projeto. Copie para `.claude/agents/` e acrescente o hook do guardião e o Protocolo comum.
- **Identidade BAP:**
  - verde #62BB47 e grafite;
  - fonte Poppins na marca e Calibri/Carlito nas tabelas do PDF;
  - **cartão RRM** como padrão de todo indicador (faixa no alto, círculos MTD/MÊS, faixa mês anterior/anterior/julho, barras por estado; paleta C clara escolhida em 10/11);
  - cores do atingimento: verde ≥ 100%, amarelo 90–99%, vermelho < 90%;
  - nada de linha inteira pintada (alerta vai para a coluna, em selo).
- Referência visual: os slides 3 a 5 do RRM do Diretor e as telas atuais. Peça os PNGs ao dono quando precisar.
- Faz:
  - tokens (cor, tipografia, espaçamento, raio, sombra, estados);
  - componentes base (botão principal 52 px, secundário 44 px, **um principal por tela**; cartões; chips de estado com texto; listas; folhas; aviso com Desfazer; abas);
  - movimento (240 ms lateral, 280 ms folha, toque 0,97 em 120 ms, respeitar "reduzir movimento");
  - **documentos gerados** (parciais, PDF dos faróis, RH) com cara de documento comercial profissional.
- Especificação de telas em `docs/design/`.
- Propostas sempre em imagem PNG lado a lado, com o mesmo dado de exemplo, para o dono escolher.
- **Revisão de UX** antes do merge, com saída 🔴/🟡/🟢 por recado. Confere:
  - hierarquia;
  - legibilidade;
  - toque ≥ 44 px e contraste ≥ 4,5:1;
  - "3 toques";
  - textos claros;
  - Alertas e Histórico no lugar certo.
- Identidade (paleta, fontes, logo) só muda com pedido do dono.
- Caminhos: pasta de componentes visuais da web, `SISTEMA BAP/recursos/` e `docs/design/`. O `bap_visual.py` fica com o modulo-farois até a divisão; o designer pede por recado.

### testes

- Prova que os critérios são verdade ou mostra onde não são.
- **Matriz de cenários** em `docs/testes/T-nnnn.md`:
  - caminho feliz;
  - limites;
  - perfil errado (quem não deve ver);
  - mês fechado × mês corrente;
  - dia útil × sábado/feriado × "hoje fora";
  - virada de mês;
  - vendedor inativo;
  - CNPJ interno e conta 000040;
  - reenvio duplicado do robô;
  - dado faltando (sem Espelho, sem TABELA do dia).
- Testa integração entre módulos, a API web, e2e (Playwright na web) e carga.
- **Valor × regra obrigatório** em toda tela com número:
  - o valor exibido bate com a fórmula da RN;
  - o rótulo diz exatamente o que o número é;
  - **o mesmo número bate em todos os faróis e no Painel do Diretor** (ex.: faturamento do cartão = soma dos estados pela filial da nota).
- Mantém os smokes atuais funcionando e migra os checks para `pytest` aos poucos.
- Relatório critério → teste → ✅/❌. Defeito vira recado `pedido` ao dono, com passos para reproduzir; nunca corrige código de produção.
- Caminhos: `tests/` (menos `dados_exemplo/`), `docs/testes/`, a configuração dos testes, `smoke_relatorios.py` e `smoke_processos.py`.

### corretor-redundancias

- Use o arquivo `corretor-redundancias.md` que já está pronto: copie para `.claude/agents/` e acrescente o hook do guardião e o Protocolo comum.
- Escopo: só excessos, duplicidades e redundâncias (no BAP há muitas: a mesma regra de DU, de projeção e de positivação em vários lugares). Defeito funcional ele só encaminha ao `testes`.
- Toda entrega passa por ele.
- Caminhos: `docs/qualidade/redundancias/**` e o próprio diário.

### modulo-<nome> (um por módulo)

- Dono da fatia vertical do módulo:
  - domínio: regras puras, com teste escrito antes, `def test_RN_<MOD>_nnn_...`;
  - contratos: funções públicas, ids de relatório, campos do dicionário;
  - telas Tkinter do módulo enquanto existirem;
  - a parte do módulo na web: parâmetros, edições e as telas próprias que o renderizador genérico não cobre.
- Manifesto do módulo sempre atualizado: ids de farol, arquivos e RN.
- Importa só pacotes comuns e o contrato dos outros módulos.
- Dado novo persistido é pedido ao engenheiro-dados. Contrato de outro módulo é pedido ao dono dele, com cc ao engenheiro-software.
- Telas web:
  - até 3 toques nas tarefas frequentes;
  - erro em português com a próxima ação;
  - tabelas densas, com filtro na URL e exportação Excel/PDF;
  - no celular, cartões primeiro.
- A `description` diz o escopo do módulo e os RF/RN.
- Caminhos: os arquivos do módulo na raiz (mapa no `donos.json`) e, depois da reorganização, `modulos/<nome>/` e `docs/modulos/<nome>/`. O `modulo-farois` é dono do `relatorios_nucleo.py`, do `bap_visual.py` e do `bap_relatorios.py` (regras) até a divisão.

## Passo 9 — Skills

- **protocolo-recados** (carregada por todos os agentes):
  - tabela "quero... → comando" do `coord.mjs`: caixa, dono, pedido, pergunta, resposta, encerrar, aviso a todos, bloqueio, entrega, lido, ler/fio, verificar;
  - boas práticas: um assunto por recado, citar arquivos e regras, dizer o critério de pronto, responder rápido.
- **status** (`disable-model-invocation: true`): roda `pendencias` e `caixa dono`, lê o quadro e responde em até 12 linhas com:
  - sprint e progresso;
  - bloqueios com recomendação;
  - o que o time precisa do dono;
  - próximo passo.
- **feature** (`argument-hint: <RF ou descrição>`, `disable-model-invocation: true`): conduz uma funcionalidade de ponta a ponta.
  1. Cria a tarefa e **aguarda meu ok**.
  2. Desenho com o engenheiro-software.
  3. Dados com o engenheiro-dados.
  4. Implementação nos módulos (máx. 3 em paralelo).
  5. Testes e corretor (+ designer nas telas, com PNG para eu aprovar).
  6. Revisão final; havendo 🔴, volta ao dono.
  7. `pendencias` e `verificar` limpos.
  8. Fechamento com como testar em 5 passos e a mensagem de commit sugerida.
- **entrega** (`disable-model-invocation: true`): fecha a sprint.
  1. compileall, ruff e pytest; se falhar, para e mostra o dono.
  2. `pendencias` sem nada aberto da sprint.
  3. `verificar --por-dono` sem violação.
  4. Revisão do engenheiro e relatório do testes e do corretor.
  5. Critérios do roadmap.
  6. Quadro, backlog e `docs/status/AAAA-MM-DD.md`.
  7. Recado `entrega` ao dono com roteiro de demonstração de 5 a 8 passos.

## Passo 10 — Docs iniciais

- **`docs/produto`:**
  - preencher do que o código e o legado já mostram:
    - 01 visão;
    - 02 módulos e RF (um RF por farol/tela do BAP Central);
    - 03 regras **RN numeradas por módulo**, tiradas do `processo_bap_out2026.md`, do `INSTALACAO_ROTA_1710.md` item 0 e da seção 3 do diário;
    - 04 arquitetura e dados (o caminho robô → fotografia → Render);
    - 05 roadmap com sprints e datas (Passo 12);
    - 06 integrações: Protheus via site BAP Tools, Máxima (Espelho e JSON de rota), BAP Ajuda, Google Geocoding/Places, Outlook, WhatsApp;
  - 07 agentes e coordenação, com o organograma, a tabela de papéis "faz / não faz", o protocolo de recados, as regras do Passo 7 e quem revisa o quê.
- **`.coord/modelos/tarefa.md`:**
  - frontmatter: `id, titulo, sprint, status (aberta|em_andamento|em_teste|em_revisao|concluida|bloqueada), responsavel, agentes, requisitos, regras, onde (local|nuvem)`;
  - seções: Objetivo · Critérios de aceite · Ordem e agentes · Premissas · Histórico.
- **`.coord/quadro.md`:** tabela das tarefas com status, dono, **Onde** (local|nuvem) e a seção "Travado pela nuvem".

## Passo 11 — Conferência final da montagem

1. Rode os testes da CLI e do guardião.
2. Simule um subagente editando fora do seu caminho e mostre o bloqueio.
3. Envie e leia um recado de teste para `todos`.
4. Rode `verificar --por-dono`.
5. Commit único com trailer `Agente: dono` (é governança) e push.
6. Me entregue em até 15 linhas:
   - o que foi criado;
   - a tabela do time;
   - os comandos;
   - o que preciso fazer: criar o repositório de recados, o token `RECADOS_TOKEN`, os segredos do CI e, no Render, o serviço e as variáveis;
   - as premissas.

## Passo 12 — Roadmap da migração (vira o doc 05 e as primeiras tarefas)

Cada item é uma tarefa `T-nnnn`, com aprovação por PNG quando tem tela. Ordem proposta [SUPOSIÇÃO; o gerente ajusta com as dependências]:

1. **T-0001 · Base do repositório:**
   - `pyproject.toml` com ruff;
   - `requirements.txt` separando o que é Windows (pywin32, keyring) e o que roda no Render;
   - CI mínimo (compileall + ruff + pytest);
   - `.gitignore` conferido;
   - nenhuma chave no histórico (varredura).
2. **T-0002 · Fixtures anonimizadas e pytest:**
   - um mês pequeno de TABELA_BAP, BASE_CLIENTE, Planner e Espelho, sem dado pessoal;
   - os checks mais importantes do smoke viram pytest: DU sem hoje, projeção, filial da nota, positivação, CNPJ interno, 000040, inativo oculto, cartões RRM somando os estados.
3. **T-0003 · Atualizar o PC a partir do GitHub (`ATUALIZAR_DO_GITHUB.bat`):**
   - clone fora do OneDrive (ex.: `%USERPROFILE%\baptools_git`) e `git pull`;
   - **backup** do que vai mudar em `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_GITHUB_<data>`;
   - cópia só dos arquivos de código para a pasta do BAP;
   - conferência byte a byte e log.
   - Roda no desktop (tem Git). Na DT-AMADMBAP-03, a instalação do Git ou um pacote zip é decisão do dono.
   - A partir daqui, **ninguém edita código direto na pasta do OneDrive**.
4. **T-0004 · ADR-0001, divisão do `relatorios_nucleo.py`** por módulo, sem mudar ids nem números (teste de equivalência: o mesmo `rn.montar` antes × depois em todos os ids, com as fixtures).
5. **T-0005 · ADR-0002, stack web.** Proposta inicial [SUPOSIÇÃO]:
   - FastAPI + Jinja2 + HTMX (renderiza o contrato de relatório no servidor, reaproveitando os núcleos sem reescrever regra);
   - gráficos com uma biblioteca JS leve;
   - PDF/Excel pelos exportadores atuais;
   - alternativa avaliada: Streamlit, como o BAP Ajuda.
   - Critérios: os faróis têm tabelas grandes com filtros, edição e exportação; vários usuários ao mesmo tempo; celular.
6. **T-0006 · Dados no Render (engenheiro-dados):**
   - endpoint de upload autenticado;
   - o robô envia a fotografia no fim de cada rodada;
   - disco persistente e retenção;
   - tela "Dados de: dd/mm hh:mm" com alerta quando estiver velho.
7. **T-0007 · Shell web (engenheiro-apps + designer-ux):**
   - login e perfis;
   - BAP Central (quadrados por área);
   - renderizador genérico com cartões RRM, tabelas, gráficos e exportação;
   - deploy no Render com `render.yaml` (governança: proposta para o dono).
   - Instância com memória suficiente para o Painel Executivo (hoje ~7 GB num smoke completo; medir) [SUPOSIÇÃO: começar com 2–4 GB e medir].
8. **T-0008 · Faróis só de leitura na web**, um módulo por vez: comercial (Metas, Visita, Clientes, Saldo, Markup, Preço, Giro), Painel Executivo e Painel do Diretor (resultado, produtividade, por DU), pós-venda e crédito.
   - Critério: **o número da web = o número do Tkinter** com a mesma fotografia.
9. **T-0009 · Edições na web:** pós-venda, NCC, garantias, autorização de venda, Farol DDR, expositores, transportadoras, campanhas.
   - A fonte da verdade passa a ser a web, com migração dos diários e período de convivência.
   - **Dado digitado nunca se perde.**
10. **T-0010 · Cadastros e Planner na web** (Gerador de Meta, Planner, zonas, rota por cidade, JSON para a Máxima). É o mais pesado; desenho primeiro.
11. **T-0011 · E-mails, parciais e WhatsApp:**
    - o envio pelo Outlook clássico fica no Windows;
    - na web, gerar PNG/PDF e "copiar/compartilhar".
    - SMTP corporativo só com aprovação do TI (dono decide).
12. **T-0012 · Desligar o Tkinter** quando tudo estiver na web e o dono aprovar.

**Fica no Windows (não vai para o Render):**

- o robô do site BAP Tools (Playwright) e o recálculo do Excel (COM);
- o robô da Máxima (login da usuária, sem guardar senha);
- o Outlook clássico e o WhatsApp Desktop.

A web recebe só os dados.
