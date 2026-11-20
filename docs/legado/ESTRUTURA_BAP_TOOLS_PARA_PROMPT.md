# BAP TOOLS: estrutura, dados e funcionamento (13/11/2026)

> Texto para colar no chat do outro projeto e gerar um **prompt de estruturação** do BAP Tools no mesmo modelo dele.
> Escrito pelo Maestro Sistemas a partir do código instalado (pasta `Regionais - Leandro`, versão de 13/11/2026), do diário de bordo e das regras oficiais.
> Não contém senha, chave nem token. Os arquivos de chave aparecem só pelo nome.

---

## 1. O que é

O **BAP Tools** é o conjunto de programas Python da área comercial da **BAP AUTOPARTS** (Grupo PMZ, Manaus). A empresa distribui autopeças, baterias, lubrificantes e pneus em AM, RR, PA, MA, AP e MT. O dono é o Alexandre Guerreiro, Gerente Comercial.

Ele faz quatro coisas:

1. **Robô de dados (`bap_automation.py`)**
   - Entra no site interno "BAP Tools" do ERP: Streamlit em IP privado, `http://172.19.20.76:8501`, só na rede da empresa ou na VPN.
   - Baixa 7 relatórios do Protheus e monta a planilha-mãe `TABELA_BAP.xlsx` e as bases derivadas.
   - Roda por tarefa agendada do Windows, várias vezes ao dia.
2. **BAP Central (`bap_central.py`)**
   - É a porta de entrada do time: 4 quadrados, um por área.
   - Cada botão abre um **farol**, que é um relatório só de leitura com cartões, abas e tabelas, exportável para Excel e PDF.
3. **Programas de gestão**
   - **Planner** (roteirização de visitas e JSON para a Máxima).
   - **Gerador de Meta** (desafio comercial, meta RH e RV).
   - **Oportunidades** (potencial por cliente).
   - **BAP Analista** (cadastros e parâmetros).
   - **Campanhas BAP** (jogo de pontos).
4. **Saídas para pessoas**
   - E-mails: parcial de resultado, inadimplência, rota da semana.
   - Imagens para WhatsApp: parcial de pedidos e de visitas.
   - Exportação para o RH (RV).
   - JSON da rota e da base para a **Máxima**, o app de força de vendas.
   - CSVs de importação para o Protheus.

**Projeto irmão: BAP Ajuda 2.0.** App web em Streamlit no Render, repositório `aloirr/bapajuda2.0`, com as telas:
- Estoque, Cliente, Pesquisa de mercado, Indicação, Prospecção.
- Não mostra preço.
- As respostas voltam para `RELATORIOS\BAP_AJUDA_RESPOSTAS\RESPOSTAS_BAP_AJUDA.xlsx`, que os faróis leem.
- Hoje ele é publicado por `3_SINCRONIZAR_GITHUB.bat` numa máquina com Git.

**Hoje tudo é desktop.** São telas Tkinter no Windows, lendo e gravando numa pasta compartilhada do OneDrive/SharePoint. Não há banco de dados: os dados são arquivos Excel, CSV e JSON.

---

## 2. Pessoas e máquinas

| Quem | Papel no sistema |
|---|---|
| Alexandre Guerreiro | Gerente Comercial; aprova toda mudança ("simule" = simular antes; "instale" = gravar) |
| Leandro (Analista Comercial) | quadrado do Analista: BAP Analista, Planner, Meta, cadastros |
| Juliana Almeida (Pré-venda e Faturamento) | Farol de Pedidos, solicitação de coleta; a máquina dela roda o robô |
| Mayara (Vendas e CRM) | Metas, Planner, base, oportunidades |
| Estefanie (Pós-venda e Logística) | entregas, garantias, devoluções, fretes, NCC, inadimplência (só ela grava no `ACOMPANHAMENTO_POS_VENDA.xlsx`) |
| Allaiza (Trade Marketing) | Farol de Expositores |
| Supervisores | Denylson (MA), Laís (PA), Francisco (AM/RR) |
| Vendedores | ~11, com código Protheus de 6 dígitos (ex.: 000015 Thiago); 000040 = conta de TESTE do Alexandre, fora de tudo |

| Máquina | Uso |
|---|---|
| **DT-AMADMBAP-03** (juliana.almeida) | robô agendado (rodadas ~8h–18h); **sem Git** |
| **NT-AMADMVD13** (notebook do Alexandre) | "servidor" das conversas Claude; às vezes roda o robô |
| **DESKTOP-PRUKJF6** (pessoal) | tem Git e Power BI Desktop |
| NT-AMADMBAP-07 | outra máquina que já rodou o robô |

A mesma pasta é sincronizada em todas as máquinas pelo OneDrive: `...\OneDrive - PMZ DISTRIBUIDORA SA\1 - PMZ\2025\IM PMZ\Regionais - Leandro`. Na máquina do robô ela se chama "Atualizações BAP".

---

## 3. Estrutura da pasta (reorganizada em 29/10/2026)

```
Regionais - Leandro\
  *.py, *.bat, *.json           ← os programas e as configurações (raiz)
  RELATORIOS\                   ← dados do dia a dia (as BASES)
    TABELA_BAP.xlsx             ← planilha-mãe (19 abas, ~15 MB)
    DADOS\*.csv.gz + _estado.json ← "fotografia" das abas (rodada rápida)
    BASE_CLIENTE.xlsx           ← carteira (abas BASE_CLIENTE, EXCLUIDOS, HIST_POR_NF, HIST_DETALHADO, REGRAS)
    ESTOQUE_BAP.xlsx            ← estoque por filial com preço e catálogo
    SOLICITACAO_BAP.xlsx        ← coletas (acumulativa)
    ACOMPANHAMENTO_*.xlsx       ← pós-venda, meta…
    ALTERACOES_PRECO.xlsx
    COORDENADAS_CLIENTES.json   ← lat/long de cada cliente (OSM/Google/Protheus/manual)
    painel_diretor_hist.json    ← fechamento mensal dos indicadores
    _EDICOES_POS_VENDA\ _NCC\ _GARANTIAS\ _AUTORIZACOES\ _COBRANCA_WHATSAPP\  ← diários do que as assistentes DIGITAM (nunca sobrescrever)
    Visitas\                    ← Espelho da Máxima (diário, AAAAMM.csv, ANALITICO, maxima_equipe.json)
    Roteirizacao\               ← PLANNER_BAP_<mês>.xlsx, JSON da rota/base, PDFs de rota, AGENDA_CIDADES
    BAP_AJUDA_RESPOSTAS\        ← respostas do app + fotos
    EXPORTADOS\                 ← tudo que os programas exportam (PDF, PNG, Excel, e-mails)
    POWERBI\                    ← CSVs do piloto Power BI
  SISTEMA BAP\                  ← tudo que é do programa
    BACKUP_RELATORIOS\
      BKP_RELATORIOS_BAPTOOLS\  ← cada relatório baixado, com a data (histórico completo)
      BKP_RELATORIOS_PRECO\ BKP_RELATORIOS_AUXILIARES\ BKP_RELATORIOS_PLANNER\
      ANTES_<ASSUNTO>_<MÊS><ANO>\  ← backup de código antes de cada instalação
    PLANNER_MESES\              ← planner_config_AAAA-MM.json de cada mês
    recursos\ (logo, cabeçalho)  Consulta CNAE\  logs\  evidencias\  cards\  auth\  Arquivos para Importar\
  DOCUMENTOS BAP\               ← documentos, simulações (CLAUDE OUTPUTS), Power BI, pacote GitHub
  BAP Ajuda 2.0\                ← o app web (repositório próprio) + BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx
  ARQUIVO MORTO\  Treinamentos e materiais de trade\
```

O desenho da pasta está num lugar só: `pastas_bap.py`. Os programas se arrumam sozinhos, e arquivo solto vai para a gaveta certa.

---

## 4. Módulos (56 `.py`, ~5 MB e ~108 mil linhas de código)

### Robô e dados
| Arquivo | Linhas | Função |
|---|---|---|
| `bap_automation.py` | 8.180 | O ROBÔ: Playwright (Chromium invisível) → login no site BAP Tools → baixa 7 relatórios → grava na TABELA_BAP só as colunas de mesmo nome (fórmulas preservadas) → arquiva os relatórios → monta SOLICITACAO, ESTOQUE_BAP, BASE_CLIENTE, pós-venda, dados dos faróis → sincroniza o BAP Ajuda. Trava `_EXECUCAO_EM_ANDAMENTO.txt` (4 h). Senha no cofre do Windows (keyring) |
| `bap_janela.py` | 1.112 | janela de acompanhamento do robô |
| `dados_bap.py` | 1.884 | "fotografia" das abas da TABELA_BAP em CSV.gz: rodada RÁPIDA (Python calcula as fórmulas, não abre o xlsx) × COMPLETA (1ª do dia, abre o Excel) |
| `xlsx_rapido.py` | 891 | leitor rápido de xlsx só de valores; usa a fotografia quando válida (CRC) |
| `bap_dados.py` | 1.492 | cache dos dados dos relatórios (lidos uma vez, marcas de versão `VERSAO 27`) |
| `aviso_arquivo.py` | 676 | pop-up "arquivo em aberto: Continuar / Cancelar / Salvar e fechar" |
| `base_cliente.py` | 1.216 | gera a BASE_CLIENTE (carteira, histórico, curva, status, CNAE/segmento, vendedor Protheus × Planner, coordenadas, STATUS_PROTHEUS) |
| `cnae_bap.py` | 706 | CNAE na Receita (BrasilAPI) e os 8 segmentos de cliente |
| `catalogo_bap.py` / `familia_nucleo.py` | 294 / 405 | categoria/família/linha de cada produto (base unificada) |
| `geocodificar.py` / `geografia.py` / `rota_lugar.py` / `zonas_padrao.py` | 2.277 / 1.400 / 220 / 327 | lat/long (Protheus › manual › Google › OpenStreetMap), centros de cidade/bairro, distâncias, zonas |
| `visitas_maxima.py` / `visitas_nucleo.py` | 1.362 / 1.406 | baixa o Espelho de Rotas da Máxima (maxGestão › Painel Auditoria) e monta as visitas |
| `prospeccao_forms.py` / `respostas_bap_ajuda.py` | 695 / 364 | prospecção (Forms e app) e respostas do BAP Ajuda nos faróis |
| `solicitacao_bap.py` / `conferir_solicitacao.py` | 363 / 157 | coletas |
| `verificar_requisitos.py` | 463 | checagem do ambiente (Python, pacotes, Excel) |

### Telas (Tkinter)
| Arquivo | Linhas | Função |
|---|---|---|
| `bap_central.py` | 289 | porta de entrada (4 quadrados; `bap_acesso.json` controla quem vê o do Analista) |
| `bap_relatorios.py` | 4.761 | a janela de cada farol: filtros, abas, cartões, tabelas, exportar, enviar e-mail |
| `bap_visual.py` | 4.220 | a "cara" de tudo: cores, cartões no modelo RRM, tabelas, PDF/Excel estilo BAP |
| `bap_analista.py` | 1.543 | BAP Analista: cadastros e parâmetros (transportadoras, meta de saldo, campanhas, CNAE…) |
| `bap_planner.py` | 7.101 | Planner (rota) |
| `bap_meta.py` | 4.232 | Gerador de Meta |
| `bap_oportunidade.py` | 3.410 | Oportunidades |

### Motores (sem tela)
| Arquivo | Linhas | Função |
|---|---|---|
| `relatorios_nucleo.py` | 19.173 | a conta de TODOS os faróis (`CATALOGO`, `montar(id)`), Contexto de dados, regras de negócio |
| `planner_nucleo.py` | 7.229 | motor da roteirização |
| `meta_nucleo.py` | 7.463 | motor da meta e da RV |
| `oportunidade_nucleo.py` | 3.445 | motor de oportunidades |
| `painel_diretor.py` / `painel_cartoes.py` / `painel_rrm.py` / `visao_executiva.py` / `painel_farol.py` | 1.240 / 737 / 923 / 721 / 406 | Painel do Diretor (modelo RRM), painel em cartões, placar dos faróis, resumo gerencial |
| `farol_ddr.py` | 1.106 | rotina diária do time com pontuação |
| `bap_champions.py` | 262 | Campanhas BAP (pontos) |
| `pos_venda.py`, `garantias.py`, `ncc_controle.py`, `autorizacoes.py`, `transportadoras.py`, `expositores.py`, `saldo_meta.py`, `agenda_cidades.py` | — | pós-venda, garantias, NCC, autorizações, fretes, trade, meta de saldo, agenda dos supervisores |

### Saídas
| Arquivo | Função |
|---|---|
| `email_parcial.py` | parcial de resultado por e-mail (Outlook clássico › MAPI › web › `.eml`) |
| `email_inadimplencia.py` | inadimplência + a vencer em 7 dias, por pessoa (vendedor/supervisor/gerente) |
| `email_rota.py` | rota da semana por e-mail |
| `parcial_imagem.py` | PNG das parciais para WhatsApp |
| `cobranca_whatsapp.py` | fila de cobrança no WhatsApp (`whatsapp://send`) |
| `conta_email.py` | conta de e-mail (sem registro de app no M365) |

### Testes
| Arquivo | Função |
|---|---|
| `smoke_relatorios.py` (5.389 linhas, ~290 checks) | bateria de todos os faróis, BAP Central e Analista |
| `smoke_processos.py` (~140 checks) | robô, base, fotografia, pop-up, Planner |
| Falhas conhecidas (não bloqueiam) | ftPedidos × Excel; recorte 000040; Farol de Visita/NCC dependem do dado do dia; falta `contatos_vcf.py` |

### `.bat` (16)
- **Abertura:** `executar_bap.bat` (o robô), `abrir_bap_central.bat`, `abrir_planner.bat`, `abrir_gerador_de_meta.bat`, `abrir_oportunidade.bat`, `abrir_bap_analista.bat`.
- **Coordenadas:** `atualizar_coordenadas*.bat`.
- **Instalação e reparo:** `instalar_bap.bat`, `REPARAR_PYTHON_BAP.bat`, `VERIFICAR_REQUISITOS.bat`, `RODAR_TESTE_BAP.bat`.
- **Outros:** `gerar_farol_ddr.bat`, `INSTALAR_PDF.bat`, e `tarefa_bap.xml` (a tarefa agendada).

### Configurações (JSON na raiz; dado digitado = não sobrescrever)
- `planner_config.json`: equipe (pessoas, cargos, chefes, e-mails, admissão), zonas, áreas, rota fixa, feriados, parâmetros de rota.
- `meta_config.json`: competência, desafio comercial do mês, metas travadas, tabelas de RV.
- `oportunidade_config.json`, `farol_ddr_config.json`, `expositores_config.json`, `meta_saldo_config.json`.
- `painel_diretor_config.json`, `champions_config.json`, `transportadoras_config.json`.
- **Chaves (nunca abrir nem versionar):** `tomtom_config.json`, `google_maps_config.json`, `visitas_config.json`, `SISTEMA BAP\auth\`.

---

## 5. Dados

### 5.1 Os 7 relatórios do robô → abas da TABELA_BAP
| Relatório no site | Aba | Conteúdo |
|---|---|---|
| Clientes | `dClientesBap` | cadastro Protheus (A1_*), STATUS ativo/inativo, desde 10/11 A1_LATITU/A1_LONGIT; colunas calculadas: limite, saldo, em aberto, em atraso, dias e média de atraso |
| Títulos em Abertos Protheus | `ftTitulos` | contas a receber por título |
| Estoque BAP Protheus | `ftEstoqueBap` | estoque por filial |
| Movimentos BAP Protheus | `ftPedidos` | pedidos e notas (VND, VEA, DEV, TRF, EXC), item a item, com custo, desconto, vendedor (C5_VEND1), data da NF |
| Estoques PMZ WEB-LEGADO | `ftEstoquePMZ` | estoque/custo das lojas PMZ (o custo do markup) |
| NCC Pendentes | `ftNCC` | notas de crédito a compensar |
| Tabela preços | `ftTabelaPreco` | preço por filial |

Também ficam na TABELA_BAP: ProdutosBAP, ProdutosExcluir, Filiais, FiliaisExcluir, ftCondicaoPagamentos, ftAutorizacaoVenda e Contatos Gerentes. A aba Fato_devolução tem fórmulas quebradas (#REF!).

**Filiais:**

| Filial | UF |
|---|---|
| 0101001 | MT |
| 0101002 | AM (Manaus) |
| 0101003 | AP |
| 0101004 | RR |
| 0101005 e 0101007 | PA (Belém, Santarém) |
| 0101006 | MA (São Luís) |

### 5.2 Fontes externas
- **Máxima** (app dos vendedores):
  - O robô baixa o Espelho de Rotas (visitas, horários, fora de rota).
  - O Planner exporta para ela o JSON da rota (layout `ERP_MXSROTACLI`) e o da base de clientes.
- **Receita (BrasilAPI):** CNAE.
- **OpenStreetMap, Google Geocoding/Places e Protheus:** coordenadas.
- **Microsoft Forms:** prospecção antiga.
- **BAP Ajuda (app):** pesquisa de mercado, indicação e prospecção.
- **Base unificada de produtos:** `BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx`, com categoria, sistema, família, linha, aplicação e referência cruzada; é mantida pelo agente de catálogo.

### 5.3 Volumes (nov/2026)
- **Clientes:** ~4.450 no Protheus; BASE_CLIENTE com ~3.690 na carteira e ~760 excluídos (fora dos 8 segmentos).
- **Movimento:** ~12.500 linhas de ftPedidos (12 meses).
- **Estoque:** ~18.000 linhas (2.930 produtos, 7 filiais). Base de produtos com ~4.700 itens.
- **Rota e visitas:** ~4.200 visitas programadas por mês; ~1.600 de meta de visita.
- **Faturamento:** meta (desafio) de NOV/26 R$ 1,5 mi.

---

## 6. Funcionamento

### 6.1 Rodada do robô
1. **Trava.** Se a SOLICITACAO estiver aberta no Excel, aparece o pop-up.
2. **Login no site BAP Tools** pelo Playwright e download dos 7 relatórios. Cada um é arquivado com a data.
3. **Gravação nas abas.**
   - Só as colunas de mesmo nome são gravadas; as calculadas ficam protegidas.
   - Coluna nova do relatório só entra se estiver em `criar_colunas`.
   - **Rodada rápida:** em memória, a partir da fotografia, com o Python calculando as 28 fórmulas diferentes (~78 mil células, conferidas contra o Excel).
   - **Rodada completa:** 1ª do dia; abre o Excel e recalcula.
4. **Bases derivadas:** SOLICITACAO_BAP (coletas + CSVs de importação), ALTERACOES_PRECO, ESTOQUE_BAP (com catálogo e preço), BASE_CLIENTE (CNAE com até 150 consultas por rodada, coordenadas com 60 s), pós-venda (Excel recalcula).
5. **Dados prontos dos faróis** (cache) e **sincronização do BAP Ajuda**, que precisa de Git: falha na máquina do robô.
6. **Resumo** em `ultimo_resumo.json` e log em `SISTEMA BAP\logs\execucao_AAAAMM_<MÁQUINA>.log`.
   - Rodada rápida leva ~500 s; antes das otimizações eram ~1.000 s.

### 6.2 Faróis (BAP Central)
Catálogo (`relatorios_nucleo.CATALOGO`), por quadrado:

| Quadrado | Faróis |
|---|---|
| **Pré-venda e Faturamento** | Farol de Pedidos; Painel de indicadores; Farol DDR |
| **Vendas e CRM** | Farol de Metas Equipe (abas Equipe e Acomp. RH; parcial por e-mail; Exportar para o RH); Farol Roteirização; Painel Executivo (Painel do Diretor · resultado / produtividade / por dia útil, no modelo RRM; Resumo gerencial; Faturamento; Volume; Produtividade; Positivação; Itens por pedido; Markup; Preço; Inadimplência); Farol de Clientes; Farol de Visita; Campanhas BAP; Farol de Giro de Produtos; Farol DDR |
| **Pós-venda e Logística** | Farol de Entregas; Farol de Garantias; Farol de Devolução e Reembolsos; Farol de Estoque FRW; Farol de Inadimplência (e-mail, cobrança no WhatsApp); Farol de NCC; Farol DDR |
| **Trade Marketing** | Farol de Expositores |
| **Analista Comercial** | Farol de Saldo; Farol de Markup; Farol de Preço; Divergências clientes Planner × Protheus; BAP Analista; Planner; Gerador de Meta; Oportunidades |

**Padrão de cada farol:**
- **Topo:** filtros (mês, ano, UF, cidade, supervisor, vendedor, segmento, categoria, sistema, família, linha, produto).
- **Cartões no modelo RRM:**
  - faixa preta com o número;
  - círculos MTD e MÊS (atingimento);
  - faixa com mês anterior, o anterior a ele e julho (benchmark);
  - barras por estado (PA, MA, AM, RR, MT, AP).
- **Abas:** tabelas (Por supervisor, Por vendedor, Por UF, Por cliente, Dia a dia…).
- **Exportação:** Excel, PDF e PNG.

### 6.3 Planner e meta
- **Planner:**
  - Carteira por zona + segmento → rota do mês por lugar: cidade › bairro › rua › número, 1 cidade por dia, dia compacto de 5 km.
  - Teto de 12 visitas/dia, sexta 12, dia foco (segunda bateria, terça moto) e ordem do mês por prioridade (S, A e com limite primeiro).
  - Saídas: PLANNER_BAP, JSON para a Máxima, PDF da rota e e-mail da rota.
- **Gerador de Meta:**
  - Desafio comercial do mês distribuído pelo potencial, com piso e tabela de mês de casa.
  - Meta RH com teto; metas de visita (90% de 12/DU), positivação, cadastro e categoria.
  - RV por faixas, com Excel auditável (fórmulas e aba MECÂNICA).

### 6.4 Regras de negócio fixadas (não mudar sem o Alexandre)
- **Faturado** = venda − devolução, pela data da NF. **Positivação** = cliente com líquido > 0 no mês. CNPJs internos (BAP AUTO PARTS, FRW, PMZ) ficam fora.
- **Desafio comercial em tudo.** A meta RH só aparece no Exportar para o RH, no e-mail e na parcial de RV.
- **DU (dia útil):** hoje fica fora da conta; a projeção = realizado até ontem ÷ DU fechados × DU do mês.
- **Estado (UF):**
  - pela **filial da nota/título**: faturamento, markup, saldo, inadimplência;
  - pela UF do cliente: carteira, frete, rota.
- **Vendedor INATIVO no Planner:**
  - sem meta e sem RV;
  - fica oculto nas parciais se não teve movimento;
  - a carteira dele fica sem meta de visita e de positivação.
- **Cliente INATIVO no Protheus:** sai da rota.
- **000040 (teste):** fora de prospecção, indicação, pesquisa, e-mails e metas.
- **Inadimplente:** tem título vencido (vencimento real antes de hoje).
- **Nome nos materiais:** "BAP AUTOPARTS". O BAP Ajuda não mostra preço.
- **TI da empresa:**
  - nada que dependa de registro de app no Microsoft 365/Graph;
  - e-mail pelo Outlook clássico, MAPI, web ou `.eml`.

---

## 7. Como o trabalho é feito hoje (o que o novo modelo deve substituir)

- **Organização:** o trabalho é feito no **Claude Cowork** por dois "maestros" com subagentes, em conversas no notebook.
  - **Maestro Sistemas:** BAP Tools, faróis, Planner, robô e BAP Ajuda. Subagentes @bap-tools, @bap-ajuda e @revisor-codigo.
  - **Maestro Comercial:** análises, apresentações, RRM e RPS do Diretor, catálogo.
- **Memória e comunicação:**
  - Cada maestro tem um **diário** (`claude/maestro_*.md`) com estado, pendências e registro.
  - Os maestros trocam **recados** entre si em `claude/recados/AAAAMMDD-HHMM_de-X_para-Y.md`.
- **Ciclo de cada mudança:**
  1. O Alexandre pede (muitas vezes com print).
  2. Copia-se da pasta para a nuvem.
  3. Simula e testa (smoke, telas com xvfb).
  4. Manda os prints e espera o ok ("instale").
  5. Grava o backup `ANTES_<ASSUNTO>_<MÊS><ANO>`, grava os novos com trava de data e confere byte a byte.
  6. Registra no diário. Para valer, é preciso fechar e abrir o programa.
- **Problemas desse modelo:**
  - não há controle de versão (só backups em pasta);
  - duas máquinas instalam na mesma pasta pelo OneDrive (risco de versão velha voltar);
  - o diário fica enorme;
  - o código vive na pasta de produção;
  - nada roda na nuvem; a máquina do robô não tem Git;
  - os testes rodam numa cópia na nuvem.

---

## 8. Aonde se quer chegar

1. **Repositório GitHub `baptools`** (privado) como fonte da verdade do código.
   - Já existe um pacote pronto: `CRIAR_REPO_BAPTOOLS.bat` cria `C:\baptools` com o código e as últimas bases, sem relatórios gerados e sem chaves.
   - O BAP Tools atual continua rodando do OneDrive até a nuvem estar 100%.
2. **Claude Code** no repositório (ambiente "Baptools-default"), com time de agentes, quadro de tarefas, recados, guardião de regras e testes automáticos. Já existe um prompt-base adaptado: `docs/inicio/PROMPT_ESTRUTURA_BAPTOOLS.md`.
3. **BAP Central web no Render:**
   - faróis em web (Streamlit ou similar) com login por pessoa;
   - dados enviados pelo robô (que continua na rede interna, porque o site BAP Tools é IP privado) para um armazenamento na nuvem, em vez de Excel no OneDrive.
4. **Distribuição:** `ATUALIZAR_DO_GITHUB.bat` leva o código do GitHub para as máquinas Windows (robô e telas desktop enquanto existirem).
5. **Restrições que o novo projeto precisa respeitar:**
   - **Credenciais fora do repositório:** senha do robô no cofre do Windows ou em variável de ambiente; chaves Google/TomTom; token do GitHub.
   - **Dados digitados pelas assistentes** (`_EDICOES_*`, `_NCC`, `_GARANTIAS`, `_AUTORIZACOES`, configs de campanha, transportadoras e painel) **nunca** são sobrescritos.
   - **Clientes no histórico:** dados de clientes (CNPJ, telefone) ficam em repositório privado; evitar versionar base todo dia.
   - **Validação de mudança:** toda mudança de número que vai para o Diretor passa por revisão e por teste.

---

## 9. O que pedir ao outro projeto

> "Com base neste retrato do BAP Tools, gere um **prompt de estruturação** no mesmo modelo do meu projeto [nome]. Ele deve conter:
> - o time de agentes;
> - os papéis e o que cada um pode mexer;
> - o quadro de tarefas;
> - as regras de commit, branch e PR;
> - os testes obrigatórios (`smoke_relatorios`, `smoke_processos`, mais testes novos por farol);
> - o guardião das regras de negócio da seção 6.4;
> - o fluxo simular → aprovar → instalar adaptado ao Git;
> - o plano de migração para o Render em fases;
> - a convivência com a pasta do OneDrive enquanto a migração não termina."
