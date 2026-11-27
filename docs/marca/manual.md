# Manual da marca BAP AUTOPARTS (BAP Central)

> **APROVADO pelo Alexandre em 26/11/2026, por volta das 18:22 (Manaus): R-20261126-182227-alexandre.**
> As 9 lacunas ficaram na opção A (itens 4 a 12 do recado) e a decisão do verde do BapAjuda (R-20261120-115646-alexandre) vale também aqui (item 3 A).
> Este manual é a fonte única da marca da BAP Central. Mudança só com novo "aprovo" do Alexandre, registrado em [`decisoes.md`](decisoes.md).
> Prancha aprovada: [`prancha-manual-marca-v2.png`](prancha-manual-marca-v2.png). A v1, a do rascunho que o Alexandre viu, fica em `aloirr/bapcentral-recados`, `recados/anexos/T-0033/prancha-manual-marca-v1.png`.

## Como ler este manual
- **Base:** o manual da marca do BapAjuda, `aloirr/bapajudacatalogo`, `docs/marca/manual.md` e `docs/marca/decisoes.md`, commit `0969a78`. A ordem é do Alexandre: "Pegue o manual da marca do bapajuda" (R-20261126-180414-alexandre).
  - O que vem de lá está copiado aqui, com a origem citada.
  - Mudança no manual do BapAjuda é do time do catálogo. Aqui ele só é lido como referência.
- **Selo [VALE]**: aprovado pelo Alexandre, com o recado citado. Tudo neste manual vale. O que era lacuna do manual do BapAjuda foi aprovado no R-20261126-182227-alexandre.
- Registro das decisões: [`decisoes.md`](decisoes.md).

## 1. Essência [VALE]
- **Para quem:** o time comercial, os gerentes e o Diretor da BAP AUTOPARTS (Grupo PMZ, Manaus), e o cliente, quando a mensagem sai para ele.
- **O que a marca passa:** número certo, na hora, sem enfeite. É uma ferramenta de trabalho: o número aparece primeiro e a marca assina.
- **Personalidade:** direta, confiável, próxima e organizada.
- **O que a marca nunca é:** enfeitada, técnica demais com o cliente, informal demais com o Diretor, nem "parecida" (cor quase igual, nome escrito de outro jeito).

## 2. Nome [VALE]
- A grafia oficial é **"BAP AUTOPARTS"**: tudo em maiúsculas e sem espaço entre AUTO e PARTS.
  - Origem: BapAjuda, decisão 10 a, R-20261122-032433-alexandre.
  - BAP Central: regra 8 do `CLAUDE.md` e R-20261126-180414-alexandre ("vale de imediato na T-0033").
- Vale na tela (site e PC), no PDF, no Excel, no e-mail, na imagem da parcial e na mensagem do WhatsApp.
- Errado: "BAP AUTO PARTS", "BAP Auto Parts" e "BAP Autoparts".
- Nomes de produto (o nome do produto acompanha a marca; não a substitui):
  - **BAP Central**: o sistema (site e PC).
  - **BAP Tools**: os programas do PC.
  - **Painel Executivo**: o painel do Diretor no site, nome único [VALE, 12 A, R-20261126-182227-alexandre]. A tela ainda mostra "Painel do Diretor · resultado" (MC-0009, a trocar).
- Onde o texto serve para achar o CNPJ interno pelo nome (regra de negócio, `meta_nucleo.py`, `bap_dados.py`), ele não é marca e não muda.

## 3. Logo

### 3.1 O que já vale [VALE]
- **Logo inteiro da BAP, pequeno.** O símbolo "b" não se corta do PNG nem se usa solto no lugar do logo.
  - Origem: BapAjuda, decisão 7 a, R-20261122-032433-alexandre.
  - BAP Central: R-20261126-180414-alexandre ("logo inteiro, não o quadrado verde") e R-20261125-174000-alexandre ("visual C com as cores e o logo da BAP AUTOPARTS").
- Logo nunca esticado, girado, recolorido, com sombra ou com contorno.

### 3.2 O arquivo
- `SISTEMA BAP/recursos/logo_bap.png`, 290 × 399 px, com fundo transparente.
  - Em cima, o círculo verde #59BA61 com o "b" branco (diâmetro de 202 px).
  - Embaixo, a palavra "bap" e "componentes de qualidade", **em branco**.
- Consequência: este arquivo **só serve em fundo escuro**. Em fundo claro a palavra some e sobra só o símbolo, o que fere o 3.1.
- Existe também uma versão deitada (símbolo + "bap" lado a lado), mas só embutida no `SISTEMA BAP/recursos/cabecalho_bap.png`, o cabeçalho do PDF. Está em baixa resolução, com um fio cruzando o símbolo, e não serve como ativo.

### 3.3 Uso [VALE, 10 A e 11 A, R-20261126-182227-alexandre]
| Item | Regra |
|---|---|
| Fundos | Preto BAP `#231F20` (o do cabeçalho do PDF) ou a faixa escura `#1B4D1F`. Em fundo claro, o logo vai numa **placa preto BAP** com canto de 9 a 10 px |
| Área de respiro | ¼ do diâmetro do círculo nos 4 lados (no arquivo, 50 px). Nada entra nessa área |
| Tamanho mínimo | 48 px de altura na tela; 15 mm impresso (PDF). Abaixo disso a palavra "bap" não se lê |
| Site, barra lateral (BC3, PC) | Placa preto BAP no topo da barra, com o logo inteiro de 56 px de altura e, ao lado, "BAP Central" (15 px, 700) e "BAP AUTOPARTS" (10,5 px, 600), em branco. O quadrado verde de hoje sai (MC-0001) |
| Site, topo do celular (M3) | A mesma placa, com o logo de 48 px |
| Login | Logo inteiro de 96 px na placa preto BAP, centralizado, com "BAP AUTOPARTS" embaixo |
| Favicon e ícone de atalho do celular | **Única exceção** ao logo inteiro: o símbolo "b" no círculo, porque o logo inteiro não cabe em 16 px. Arquivos de 32 px (favicon) e 180 px (ícone do celular), recortados do `logo_bap.png` sem recolorir. Fica reconhecível em 16 px (ver a prancha) |
| PDF | O logo inteiro na faixa preto BAP do cabeçalho, como o PDF do PC já faz (`bap_visual.py`, cabeçalho do PDF) |

- **Pedido em aberto (10 A):** a versão do logo com a palavra "bap" escura, para fundo claro, vem do time do catálogo, pedida por recado ao Alexandre. Quando ela chegar e for registrada em `decisoes.md`, a placa preta deixa de ser obrigatória no fundo branco. Até lá, a placa vale. Recolorir o PNG por conta própria é proibido.
- **Revisão do meu parecer anterior:** a correção do MC-0001 (revisao-marca-geral.md) pedia o símbolo de 56 × 55 px na barra lateral. Com a decisão 7 a do BapAjuda, a correção passa a ser o logo inteiro na placa preto BAP. O símbolo recortado que hoje aparece no topo do visual C (`estilo.css`, `.marca::before`) também precisa trocar.

## 4. Paleta em tokens
Os nomes valem igual no CSS do site (`--nome`) e nas constantes do PC (`bap_visual.py`), que passam a usar o mesmo hex. Hex solto no código ou no PDF é proibido: só a constante.

Contraste pela fórmula WCAG 2.1 (luminância relativa). Mínimo de **4,5:1** no texto; **3:1** no texto grande (≥ 24 px, ou ≥ 18,7 px em negrito) e em ícone.

### 4.1 Já vale [VALE]
| Token | Hex | Papel | Origem |
|---|---|---|---|
| `--erro` | `#B42318` | Mensagem de erro, campo com erro, botão de desativar | BapAjuda, decisão 8 a, R-20261122-032433-alexandre; BAP Central, R-20261126-180414-alexandre |
| `--erro-claro` | `#FDECEA` | Fundo da caixa de erro | idem |

### 4.2 O resto da paleta [VALE, 3 A a 8 A, R-20261126-182227-alexandre]
O manual do BapAjuda deixava a paleta completa "a aprovar" e citava a decisão do verde de lá (R-20261120-115646-alexandre). O Alexandre decidiu que essa decisão vale também na BAP Central (3 A) e aprovou os valores abaixo (4 A a 8 A): verde da marca `#59BA61` com o verde escuro `#2F7D32` para texto e botão; faixa do BC3 de `#2F7D32` a `#1B4D1F` com texto branco; o vermelho do farol igual ao do erro; o amarelo de texto `#8A5A00`; e os cinzas e fundos da prancha.

**Marca e faixa**
| Token | Hex | Papel | De onde vem | Muda o quê |
|---|---|---|---|---|
| `--verde-marca` | `#59BA61` | O verde do logo. Logo, selo e destaque grande. **Nunca texto em fundo claro** | Medido no `logo_bap.png`; é o `VERDE_BAP` do PDF (`bap_visual.py`) | `VERDE #62BB47` (telas do PC) passa a `#59BA61`: os dois são "quase iguais" e o certo é o do logo |
| `--verde-escuro` | `#2F7D32` | Texto verde, botão, aba ativa, número "bom" | `VERDE_ESCURO` (`bap_visual.py`), já usado no BC3 | Os outros 6 verdes do `estilo.css` (#2b8a3e, #1e8e3e, #4FA236, #3C9440, #2F5D3A, #2E5C3B) saem |
| `--preto-bap` | `#231F20` | Fundo do logo e faixa do cabeçalho do PDF | `PRETO_BAP` (`bap_visual.py`), a cor do catálogo | Nenhuma no PC; no site, a placa do logo |
| `--verde-claro` | `#E5F3DF` | Fundo de destaque (grupo do Excel, total), **só com `--texto`** | `VERDE_CLARO` (`bap_visual.py`) | Nenhuma |
| `--faixa-inicio` | `#2F7D32` | Início do degradê da faixa BC3 | O BC3 aprovado (R-20261126-171559-alexandre) | Antes era `#3C9440`: texto branco a 3,82:1 e o esverdeado `#D2E7D3` a 2,93:1. Muda o tom do canto da faixa, que fica um pouco mais escuro (ver o antes e depois da prancha) |
| `--faixa-fim` | `#1B4D1F` | Fim do degradê da faixa BC3 | O BC3 aprovado | Nenhuma |
| `--faixa-texto` | `#FFFFFF` | Todo o texto da faixa, inclusive o pequeno | — | Antes, o texto pequeno era `#D2E7D3`: 2,93:1 sobre o `#3C9440` de antes e 3,93:1 mesmo sobre o novo `#2F7D32`, abaixo de 4,5:1 nos dois. A hierarquia fica pelo peso e pelo tamanho |
| `--faixa-alerta` | `#FFB4A9` | Número em alerta na faixa | O BC3 aprovado | Só em número ≥ 19 px negrito |
| `--faixa-atencao` | `#FFE08A` | Número em atenção na faixa | O BC3 aprovado | idem |
| `--faixa-ok` | `#A6E3A9` | Número bom na faixa | O BC3 aprovado | idem |

**Estados (farol)**: verde, amarelo e vermelho só para estado (linha, ponto, número e SLA). Nunca para decorar.
| Token | Hex | Papel | Muda o quê |
|---|---|---|---|
| `--alerta` | `#B42318` (= `--erro`) | Número e ponto vermelhos do farol | `VERMELHO #B3261E` sai: é "quase igual" ao vermelho aprovado |
| `--alerta-claro` | `#FDECEA` (= `--erro-claro`) | Fundo da linha em alerta | `VERMELHO_CLARO #FBE3E1` sai. O site já usa `#fdecea` na linha |
| `--atencao` | `#B7791F` | **Só** ponto, ícone e barra amarelos | `AMARELO` continua, mas sai do texto: como texto tem 3,64:1 |
| `--atencao-texto` | `#8A5A00` | Número e texto em atenção | Novo token, mas é um tom já usado no PDF da parcial (`ATING_CORES`) |
| `--atencao-claro` | `#FFF4D6` | Fundo da linha em atenção | `AMARELO_CLARO`. Saem `#fff3bf`, `#fff8e1` e `#FFF8E6` |
| `--ok` | `#2F7D32` (= `--verde-escuro`) | Número e ponto verdes do farol | Nenhuma |
| `--ok-claro` | `#F0F7EC` | Fundo da linha boa | `FUNDOS["ok"]` do PC. No `#E5F3DF`, o verde-escuro dá 4,44:1 e não passa |
| `--grafico-1` · `--grafico-2` · `--grafico-3` | `#7DB46A` · `#D8B56E` · `#8FA79A` | Barras dos gráficos, sempre com o número escrito ao lado | Vistos e aprovados nas simulações do BC3; ganham constante, sem trocar o tom |

**Neutros**
| Token | Hex | Papel | Muda o quê |
|---|---|---|---|
| `--texto` | `#1E2722` | Texto principal | Nenhuma no PC. No e-mail, `#1F2937` sai |
| `--suave` | `#5E6B63` | Texto de apoio, rótulo, data | `SUAVE #69736D` dá 4,45:1 no fundo e não passa. O BC3 já usa `#5E6B63`. No e-mail, `#6B7280` sai |
| `--fundo` | `#F3F4F2` | O gelo do fundo | `FUNDO` do PC. No site, `#F6F7F5` e `#F5F6F4` (quase iguais) saem |
| `--cartao` | `#FFFFFF` | Cartões e tabelas | Nenhuma |
| `--borda` | `#E3E8E4` | Contorno de cartão e de campo | O BC3. No PC, `CINZA_LINHA #D5DAD4` passa a `--borda` |
| `--grade` | `#ECEEEB` | Linhas internas da tabela | `GRADE` do PC |
| `--cinza-cab` | `#E4E7E3` | Cabeçalho das telas do PC (Tkinter) | Fica só no PC, até a tela migrar para o site |

- **Fora da paleta da BAP Central:** o azul `#1F4FD1` / `#E3EAFB` é o selo "NOVO" do card de preço do catálogo. Fica só nele. As sobras do visual antigo do site (`--azul #0b3a6b`, `--lar #e8590c`, `#d0ebff`, `#a5d8ff`, `#e7edf5`) saem.

### 4.3 Contraste de cada par texto/fundo
| Texto | Fundo | Contraste | Uso |
|---|---|---|---|
| `--texto` #1E2722 | `--cartao` #FFFFFF | 15,35:1 | texto |
| `--texto` | `--fundo` #F3F4F2 | 13,91:1 | texto |
| `--texto` | `--verde-claro` #E5F3DF | 13,31:1 | texto |
| `--texto` | `--erro-claro` #FDECEA | 13,42:1 | texto na linha em alerta |
| `--texto` | `--atencao-claro` #FFF4D6 | 14,00:1 | texto na linha em atenção |
| `--suave` #5E6B63 | `--cartao` | 5,59:1 | texto |
| `--suave` | `--fundo` | 5,06:1 | texto |
| `--verde-escuro` #2F7D32 | `--cartao` | 5,12:1 | texto, aba ativa |
| `--verde-escuro` | `--fundo` | 4,64:1 | texto |
| `--ok` #2F7D32 | `--ok-claro` #F0F7EC | 4,69:1 | número bom na linha |
| #FFFFFF | `--verde-escuro` / `--faixa-inicio` | 5,12:1 | botão, texto da faixa (pior ponto) |
| #FFFFFF | `--faixa-fim` #1B4D1F | 9,87:1 | texto da faixa |
| `--faixa-atencao` #FFE08A | `--faixa-inicio` | 3,97:1 | só número grande |
| `--faixa-ok` #A6E3A9 | `--faixa-inicio` | 3,46:1 | só número grande |
| `--faixa-alerta` #FFB4A9 | `--faixa-inicio` | 3,01:1 | só número grande (no `--faixa-fim`, 5,81:1) |
| `--erro` #B42318 | `--cartao` | 6,57:1 | texto [VALE] |
| `--erro` | `--erro-claro` | 5,75:1 | texto [VALE] |
| #FFFFFF | `--erro` | 6,57:1 | botão de desativar [VALE] |
| `--atencao-texto` #8A5A00 | `--cartao` | 5,93:1 | texto |
| `--atencao-texto` | `--atencao-claro` | 5,41:1 | texto |
| `--atencao` #B7791F | `--cartao` | 3,64:1 | **só ícone, ponto e barra** |
| #FFFFFF | `--preto-bap` #231F20 | 16,30:1 | texto na placa do logo e na faixa do PDF |
| `--verde-marca` #59BA61 | `--preto-bap` | 6,69:1 | destaque no escuro |

### 4.4 Combinações proibidas
- `--verde-marca` como texto ou ícone em fundo claro (2,44:1 no branco).
- `--verde-escuro` sobre `--verde-claro` em texto pequeno (4,44:1).
- `--atencao` #B7791F como texto (3,64:1): use `--atencao-texto`.
- Texto esverdeado (#D2E7D3) na faixa (2,93:1 no #3C9440; 3,93:1 no #2F7D32): use branco.
- Cor de farol (verde, amarelo, vermelho) como enfeite, título ou fundo de cabeçalho.
- Logo inteiro direto em fundo claro (a palavra "bap" some).

## 5. Tipografia [VALE, 9 A, R-20261126-182227-alexandre]
O manual do BapAjuda deixava a tipografia do site "a aprovar". Antes da decisão, a BAP Central tinha quatro letras:
- Segoe UI: telas do PC e imagem da parcial.
- Inter, Segoe UI ou system-ui: três pilhas diferentes no `estilo.css`.
- Poppins e Calibri: o PDF do PC.
- Arial: o .pptx [VALE], pela decisão 7 a do BapAjuda (R-20261123-112006-alexandre).

**Decisão (9 A): uma família, a Inter.**
- **Por quê:**
  - É a letra das simulações do BC3 e do M3 que o Alexandre aprovou. O `estilo.css` já pede a Inter primeiro.
  - É livre (licença OFL), então pode ser hospedada no site: fica igual no PC e no celular. Também pode ser embutida no PDF e na imagem da parcial.
  - Tem algarismos de mesma largura, o que deixa as colunas de números alinhadas.
- **Onde não dá para levar a Inter**, entra a Segoe UI e, sem ela, Arial (pilha: `Inter, "Segoe UI", Arial, sans-serif`):
  - telas do PC (Tkinter), que só têm as fontes do Windows;
  - Excel;
  - e-mail no Outlook.
  - A Segoe UI tem o mesmo desenho limpo e não muda a leitura.
- **Ficou a A (Inter), não a B (Segoe UI em tudo).** A Segoe UI não pode ser hospedada no site (licença): o celular abriria em outra letra, e o PDF do site não teria como embuti-la.
- **O .pptx fica em Arial** [VALE].

| Tamanho (px na tela) | PDF (pt) | Peso | Uso |
|---|---|---|---|
| 24 | 18 | 700 | Título da tela (faixa) |
| 22 | 16 | 700 | Número de destaque (faixa, cartão) |
| 16 | 12 | 600 | Título de bloco ou de cartão |
| 14 | 10 | 400 (600 no botão) | Texto, menu, botão |
| 13 | 9 | 400 | Tabela; número com algarismos de mesma largura |
| 12 | 8,5 | 400 | Apoio, data, rodapé |
| 11 | 8 | 600, maiúsculas, +4% de espaço | Rótulo de coluna e de número. **Menor tamanho permitido** |

- Pesos: só 400, 600 e 700. O 800 do `.bc3-marca` passa a 700.
- O mesmo papel usa sempre o mesmo tamanho e o mesmo peso em todas as telas.

## 6. Tom de voz [VALE, 12 A, R-20261126-182227-alexandre]
- Direto, confiante e próximo de quem usa. Frase curta, verbo na frente, número com unidade.
- Com a equipe e o Diretor: o número primeiro, depois o porquê. Ex.: "Faltam R$ 42 mil para a meta. Restam 6 dias úteis."
- Com o cliente (WhatsApp, e-mail): cordial, sem jargão do sistema (nada de "Protheus", "ftTitulos", "DU").
- Sem "Prezado colaborador", sem caixa alta para gritar (a exceção é o nome "BAP AUTOPARTS") e sem emoji em material formal.
- Assinatura: "BAP AUTOPARTS · {programa}". Ex.: "BAP AUTOPARTS · Farol de Metas (gerado automaticamente)".
- O texto de interface é do designer-ux e do corretor-redundancias. Aqui vale só a voz da marca: nomes, assinatura, assunto e boas-vindas.

## 7. Aplicações [VALE]
| Onde | Como fica | O que ainda falta trocar (achados do parecer T-0033) |
|---|---|---|
| **Site, PC (BC3)** | Barra lateral com a placa do logo (3.3). Faixa com `--faixa-inicio` → `--faixa-fim` e texto branco. Cartões `--cartao` com `--borda` sobre `--fundo`. Aba ativa `--verde-escuro`. Aba do navegador: "{tela} · BAP AUTOPARTS". Favicon (3.3). BC3 em todas as telas logadas (R-20261126-171559-alexandre) | Quadrado verde (MC-0001); duas cascas (MC-0004); contraste da faixa (MC-0005); cores soltas (MC-0006); sem favicon (MC-0010) |
| **Site, celular (M3)** | A mesma marca da barra no topo (logo de 48 px); lista que abre; tabelas de baixo recolhíveis (R-20261126-171559-alexandre) | Igual ao PC |
| **PDF** (PC e site) | Faixa `--preto-bap` com o logo inteiro e "BAP AUTOPARTS · {título}" em branco. Corpo na pilha da Inter. Cabeçalho da tabela em `--verde-escuro` com texto branco. Rodapé: "BAP AUTOPARTS · {farol} · página n de N · gerado em dd/mm/aaaa hh:mm (Manaus)". Autor do arquivo: "BAP AUTOPARTS" | O PDF do site sai sem a marca, com o verde #2E5C3B fora da paleta (MC-0003); o PC grava o autor "BAP Auto Parts" (MC-0011) |
| **Excel** | A1: "BAP AUTOPARTS · {ÁREA}" em negrito. Cabeçalho de coluna em `--verde-escuro` com texto branco; total em `--verde-claro`; letra Segoe UI ou a do Excel | PC "BAP AUTO PARTS" (MC-0011); site #2F5D3A (MC-0003) |
| **E-mail** (parcial, inadimplência, rota) | Assunto: "{programa} · {período}". Topo com "BAP AUTOPARTS" em `--verde-escuro`. Texto em `--texto` e `--suave`. Pilha `"Segoe UI", Arial, sans-serif` (o Outlook não carrega a Inter). Assinatura "BAP AUTOPARTS · {programa} (gerado automaticamente)" | "BAP Auto Parts" na assinatura (MC-0011); cinzas #1F2937 e #6B7280 fora da paleta |
| **Imagem da parcial** (WhatsApp) | "BAP AUTOPARTS" no topo em `--verde-escuro`, como já sai. Letra Inter embutida (hoje Segoe UI) | Conforme no nome |
| **Mensagem do WhatsApp** | Texto puro: "BAP AUTOPARTS" em maiúsculas. Abertura e assinatura do setor: "Aqui é do financeiro da BAP AUTOPARTS." Sem link encurtado e sem emoji [VALE no nome] | "BAP Auto Parts" na cobrança (MC-0002, `cobranca_whatsapp.py`) |
| **Telas do PC (BAP Tools)** | Cabeçalho "BAP AUTOPARTS · {ÁREA}" sobre `--cinza-cab`. As constantes do `bap_visual.py` com os mesmos hex dos tokens | "BAP AUTO PARTS" (MC-0011) |
| **Apresentação (.pptx)** | Arial [VALE]; o logo inteiro em fundo escuro | — |

## 8. Grafismos
- A faixa de ícones de peças do `cabecalho_bap.png` (cabeçalho do PDF) vem do catálogo da BAP. São ícones técnicos, sem origem cultural. Fica só no cabeçalho do PDF.
- Nenhum grafismo cultural em uso. Qualquer grafismo novo só entra com a origem registrada e com o "aprovo" do Alexandre.

## 9. Lacunas decididas (26/11/2026, R-20261126-182227-alexandre)
Todas ficaram na opção A. O número entre parênteses é o item da resposta do Alexandre.

| # | Lacuna | Decisão (A) | Opção não escolhida (B) |
|---|---|---|---|
| L1 (4) | O verde da marca | `--verde-marca #59BA61` (o do logo) e `--verde-escuro #2F7D32` para texto e ação. Sai o `#62BB47` | Manter `#62BB47` no PC |
| L2 (5) | A faixa do BC3 | Degradê `#2F7D32` → `#1B4D1F`, texto branco (5,1:1 ou mais) | Manter `#3C9440` (3,82:1) |
| L3 (6) | O vermelho do farol | O mesmo do erro, `#B42318` / `#FDECEA` | Dois vermelhos (`#B3261E` no farol) |
| L4 (7) | O amarelo | Texto `#8A5A00`; o `#B7791F` só em ponto, ícone e barra | `#B7791F` no texto (3,64:1) |
| L5 (8) | Cinzas e fundos | `--suave #5E6B63`, `--fundo #F3F4F2`, `--borda #E3E8E4`, `--grade #ECEEEB` | Manter os de hoje |
| L6 (9) | Tipografia | Inter no site; Segoe UI ou Arial onde a Inter não chega (PC, Excel, e-mail); .pptx em Arial | Segoe UI em tudo |
| L7 (10) | O logo no site | Logo inteiro de 56 px numa placa preto BAP `#231F20`, com "BAP AUTOPARTS" ao lado; mínimo de 48 px na tela e 15 mm no PDF; pedir ao catálogo a versão com o "bap" escuro | Outra solução |
| L8 (11) | Favicon e ícone do celular | O símbolo "b" no círculo, só nesse caso | O logo inteiro (não cabe em 16 px) |
| L9 (12) | Tom de voz e nomes | Seção 6; "Painel Executivo" como nome único | Ajustar |
