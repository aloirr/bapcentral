# BAP Central (BAP Tools)

A central BAP: relatorios, BAP Tools e, no roadmap, a versao web no Render, alimentada pela
sincronizacao diaria feita no PC. **O catalogo nao fica aqui:** base unificada, catalogo grafico e
digital moram no `aloirr/bapajudacatalogo`.

Programas da area comercial da **BAP AUTOPARTS** (Grupo PMZ, Manaus):

- farois de gestao e Painel do Diretor/Executivo;
- metas e RV;
- roteirizacao (Planner);
- pos-venda;
- o robo que baixa os dados do ERP.

Repositorio **PRIVADO**: tem dados de clientes. Python 3.12. As telas atuais sao Tkinter (Windows); a versao web vai para o Render.

## Origem e situacao

- Copia da pasta `Regionais - Leandro` (OneDrive) em 10/11/2026: **codigo + as ultimas bases**. Os relatorios gerados ficam de fora: eles sao gerados de novo pelo programa.
- **O BAP Tools de producao continua rodando da pasta do OneDrive** ate a versao web estar 100%. Nada foi alterado la.
- **Time de agentes (20/11/2026):** veja `CLAUDE.md` e `.coord/README.md`. O Alexandre conversa com o **po** (ambiente BapCentral-PO do claude.ai/code); o **gerente-projetos** (ambiente BapCentral-GP) comanda os outros agentes. Recados no `aloirr/bapcentral-recados`. Memoria do trabalho ate aqui: `docs/legado/`.

## Estrutura (igual a pasta do BAP)

- **Raiz:** programas (`.py`, `.bat`) e configuracoes (`planner_config.json`, `meta_config.json`...).
- **`RELATORIOS/`:** bases:
  - TABELA_BAP, BASE_CLIENTE, ESTOQUE_BAP, SOLICITACAO_BAP;
  - acompanhamentos e diarios de edicao (`_EDICOES_POS_VENDA`, `_NCC`, `_GARANTIAS`, `_AUTORIZACOES`);
  - Visitas (Espelho da Maxima), Roteirizacao (PLANNER e JSON da rota), `DADOS` (fotografia), coordenadas.
- **`SISTEMA BAP/`:** `PLANNER_MESES`, `recursos`, `Consulta CNAE` e as fotos diarias do BAP Tools que os farois leem (`BACKUP_RELATORIOS/BKP_RELATORIOS_BAPTOOLS`: titulos e NCC inteiros; o resto, so o ultimo).
- **`BAP Ajuda 2.0/`:** so a `BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx` (copia de leitura; a fonte e o `aloirr/bapajudacatalogo`).

## Fora do repositorio, de proposito

- **Chaves e credenciais:** TomTom, Google Maps, `visitas_config.json`, `SISTEMA BAP/auth`.
  - A senha do robo no site BAP Tools **nao esta no codigo**: fica no cofre do Windows (`python bap_automation.py --salvar-senha`) ou na variavel `BAP_SENHA`.
- **Relatorios gerados, caches, backups e logs.** Veja o `.gitignore`.

## Atencao: dados no Git

- Cada versao de base que subir fica no historico para sempre e o repositorio cresce.
- Esta carga e a fotografia da migracao.
- Daqui em diante os dados devem ir para o Render pelo robo (tarefa T-0006), nao por commit.
