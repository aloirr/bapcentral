# ADR 0002 — Rotina diária que deixa a pasta de produção igual ao `main`

- **Status:** aprovada (R-20261124-214958-alexandre, decisões 1 B, 2 A, 3 B, 4 A e 5 A, sobre as opções do R-20261124-213435-gerente-projetos)
- **Data:** 2026-11-25
- **Tarefa:** T-0018 · **Autor:** engenheiro-software
- **Depende de:** T-0003 (`atualizar_do_github.py`, `ATUALIZAR_DO_GITHUB.bat`), ADR 0001 (web no Render e `/saude`)
- **Consumidores:** gerente-projetos e po (regra 11 do CLAUDE.md), modulo-robo (trava do `bap_automation.py` e a mudança do robô para a pasta pessoal), modulo-web (`web/app/__init__.py` `VERSAO` e `/saude`), testes
- **Recados:** R-20261124-210855-alexandre (deploy automático do Render a cada publicação no `main`), R-20261124-211805-alexandre e R-20261124-213034-alexandre (atualização diária da pasta, sem o .bat no desktop), R-20261124-213435-gerente-projetos (as 5 perguntas), R-20261124-214958-alexandre (as respostas)

## 1. Contexto

- Até aqui a regra 11 exigia o "instale" do Alexandre a cada lote, com o `ATUALIZAR_DO_GITHUB.bat` rodado à mão (T-0003).
- O Alexandre pediu que a pasta de produção fique igual ao `main` todo dia, sem ninguém rodar o .bat (R-20261124-213034).
- O Render já publica a web sozinho a cada publicação no `main` (R-20261124-210855). O código do PC e o da web precisam andar juntos.

## 2. Decisões (texto do Alexandre: "1 b / 2 a / 3 b / 4 a / 5 a")

| # | Decisão | O que vale |
|---|---|---|
| 1 B | Produção = pasta **pessoal** | "Regionais - Leandro" no OneDrive pessoal (não a "- Copia"). A mudança do robô, da TABELA_BAP, do RELATORIOS e dos compartilhamentos para lá é do **modulo-robo**, à parte, com simulação e lista de passos antes. A pasta da empresa vira cópia até a mudança terminar. |
| 2 A | Roda no **notebook do robô, às 06h30** | Tarefa agendada do Windows, contra a pasta pessoal. |
| 3 B | Repositórios **públicos** | Nada de token. O zip sai sem login e a API do GitHub é consultada sem token (cota de 60 requisições por hora, por IP). |
| 4 A | "Instale" **automático**, com os 5 limites | Os `.bat` de instalação, o próprio atualizador, o `tarefa_bap.xml` e os `.json` continuam pedindo "instale". |
| 5 A | Existe o `--primeira-vez` | Manual, com backup total; antes, `--simular` com imagem ao Alexandre. |

## 3. Como funciona — `atualizar_do_github.py --diario`

Ordem, da conferência mais barata à mais cara. Um limite que falha **não troca nada**, sai com o código próprio e grava **uma linha** em `SISTEMA BAP\LOGS\atualizacao_diaria.log`.

| Ordem | Conferência | Função pura | Código |
|---|---|---|---|
| 0 | Pausa: existe `SISTEMA BAP\PAUSAR_ATUALIZACAO` | — | 16 |
| 1 | **Limite 4 (hora):** entre 06h00 e 07h30, America/Manaus | `dentro_da_janela` | 13 |
| 2 | **Limite 4 (robô):** a trava do robô (`SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_BAPTOOLS\_EXECUCAO_EM_ANDAMENTO.txt`) existe e tem menos de 4 h. Só a data do arquivo é lida, nunca o conteúdo. | `robo_rodando` | 14 |
| 3 | Cota da API: `/rate_limit` (não gasta cota) com 4 ou mais restantes | — | 15 |
| 4 | SHA e data do `main` (`/commits/main`). Se for o SHA do `VERSAO_INSTALADA.txt`, sai 0 sem baixar nada. | `sha_do_texto_versao` | 0 / 15 |
| 5 | **Limite 1:** o commit tem 2 h ou mais | `commit_maduro` | 10 |
| 6 | **Limite 2:** o PR de origem (`/commits/{sha}/pulls`, só o PR cujo `merge_commit_sha` é o próprio SHA; commit sem PR próprio sai 11) tem todas as verificações do head concluídas e verdes (`/commits/{head}/check-runs`) | `pr_de_origem`, `ci_verde` | 11 |
| 7 | Baixa o zip **do SHA conferido** (`github.com/.../archive/{sha}.zip`, fora da cota da API) e confere o SHA no comentário do zip; sem o comentário ou com outro SHA, sai 1 sem trocar nada | — | 1 |
| 8 | **Limite 3:** `VERSAO` de `web/app/__init__.py` no zip é igual à `versao` do `/saude`. A URL vem de `BAP_WEB_URL` ou do cofre (`BAP_WEB`/`url`), a mesma do pacote do robô, e não vai para o log. | `versao_do_init`, `versoes_batem` | 12 |
| 9 | Plano sem os arquivos de `so_com_instale`. Os que estiverem diferentes viram "pendente de instale" no log. | `so_com_instale` | — |
| 10 | **Limite 5:** trava "instalado por fora" (arquivo da produção mais novo que o `main`) | `planejar` | 2 |
| 11 | Backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_DIARIO_<MÊS><ANO>[_n]`, troca atômica e conferência byte a byte (T-0003) | — | 3 / 4 |
| 12 | Grava `SISTEMA BAP\VERSAO_INSTALADA.txt`: 1ª linha com o SHA, depois a data (Manaus), o modo e o n.º de arquivos | `texto_versao_instalada` | 0 |

- **`--simular`:** mostra o plano e o código, mas não grava nada, nem a linha de log.
- **Cota:** no máximo 4 requisições por rodada (1 sem custo). Cabem com folga nas 60 por hora.
- **Log sem dado pessoal:** cada linha tem a data, o modo, o código, o SHA curto e só nomes de programa e hashes curtos (`linha_log`). Nada de usuário, máquina, URL ou conteúdo de arquivo.
- **Nunca instalados pelo `--diario`:** `instalar_bap.bat`, `INSTALAR_PDF.bat`, `REPARAR_PYTHON_BAP.bat`, `VERIFICAR_REQUISITOS.bat`, `ATUALIZAR_DO_GITHUB.bat`, `INSTALAR_ROTINA_DIARIA.bat`, `atualizar_do_github.py`, `tarefa_bap.xml`, qualquer `.json`. Também ficam de fora as bases, os dados digitados e os segredos (`eh_excluido`, T-0003).
  - [SUPOSIÇÃO] O próprio atualizador entra na lista: quem muda a régua dos limites não deve se instalar sozinho. A mudança dele segue com "instale" (`ATUALIZAR_DO_GITHUB.bat`).

### 3.1 `--primeira-vez`
- Só manual. Exige `--confirmar`, ou então `--simular` para mostrar antes. Não combina com `--diario`.
- Faz backup **total** dos `.py`/`.bat` da raiz da produção (`ANTES_PRIMEIRA_VEZ_<MÊS><ANO>`) e ignora a trava 5.
- [SUPOSIÇÃO: não está escrito no R-20261124-214958; confirmar com o po] Os limites 1 a 3 não valem aqui: a rodada é manual e o Alexandre está olhando. A trava do robô continua valendo (código 14).

### 3.2 Agendamento
- `ATUALIZAR_DO_GITHUB.bat --agendar` executa `schtasks /Create /TN "BAP - Atualizacao diaria do codigo" /TR "py -3.12 \"<pasta>\atualizar_do_github.py\" --diario" /SC DAILY /ST 06:30 /F`. É criado sem `/RU` e sem senha: fica com o usuário atual e só roda com ele logado. `--remover-agendamento` apaga a tarefa.
- **Pendente (governança):** o `INSTALAR_ROTINA_DIARIA.bat` pedido na T-0018 hoje é **sem-dono**. Ele precisa de uma linha no `.coord/donos.json` (→ engenheiro-software), com a autorização do Alexandre. O conteúdo proposto:

```bat
@echo off
rem T-0018 (ADR 0002): cria a tarefa diaria das 06h30 nesta pasta. Uso: INSTALAR_ROTINA_DIARIA.bat [--remover]
if /I "%~1"=="--remover" (py -3.12 "%~dp0atualizar_do_github.py" --remover-agendamento) else (py -3.12 "%~dp0atualizar_do_github.py" --agendar)
set "BAP_CODIGO=%ERRORLEVEL%"
pause
exit /b %BAP_CODIGO%
```

## 4. Regra 11 — texto novo proposto para o CLAUDE.md

> 11. **Produção no PC:** a rotina diária (`atualizar_do_github.py --diario`, tarefa agendada às 06h30 no notebook do robô) leva os `.py`/`.bat` da raiz do `main` para a pasta de produção (a pessoal, R-20261124-214958). Ela faz backup `SISTEMA BAP\BACKUP_RELATORIOS\ANTES_DIARIO_<MÊS><ANO>` e confere byte a byte. Só instala se: (1) o commit tiver 2 h ou mais no `main`; (2) o PR de origem teve CI verde no head SHA; (3) a versão da web no `main` for igual à do `/saude`; (4) estiver na janela 06h00–07h30 de Manaus, com o robô parado; (5) a trava "instalado por fora" não tiver disparado. Falha = nada trocado + uma linha no log. Pausa: `SISTEMA BAP\PAUSAR_ATUALIZACAO`. Os `.bat` de instalação, o `atualizar_do_github.py`, o `tarefa_bap.xml` e as configs continuam com "instale".

- O CLAUDE.md é governança: a troca do texto vai com "Agente: alexandre", e o po autoriza por delegação (decisão 4 A).

## 5. Consequências e riscos

- **Pasta pessoal sem o robô:** enquanto o modulo-robo não mudar o robô para a pasta pessoal, a trava do limite 4 é procurada na pasta pessoal e não existe lá, então o limite 4 só confere a hora. Risco baixo: às 06h30 o robô (08h/14h) não roda.
- [SUPOSIÇÃO] O notebook sincroniza a pasta pessoal. Sem isso, a rotina atualiza uma pasta que ninguém usa. A mudança do robô (decisão 1 B) resolve.
- [SUPOSIÇÃO] O usuário fica logado no notebook às 06h30. A tarefa sem senha não roda com a sessão fechada; nesse caso não roda nada e não há linha no log.
- **Deploy da web atrasado** (Render dormindo ou com falha): o limite 3 segura o código do PC. Ele tenta de novo no dia seguinte.
- **Cota da API** dividida com outro programa no mesmo IP: código 15 e nova tentativa no dia seguinte.
- **Aviso de falha:** a v1 grava só o log. Na v2, o robô manda `versao_codigo` e `status_atualizacao` no pacote e o `/saude` mostra os dois (modulo-robo, modulo-web e uma versão nova do contrato).

## 6. Testes

- Os testes ficam no rascunho da sessão, `test_T0018_rotina.py`, até o agente testes levar para `tests/`. São 63 casos, sem rede (monkeypatch em `_get_json`, `versao_do_site` e `baixar_main`): cada limite como função pura, o `--diario` ponta a ponta (instala, já instalado, API fora do ar, zip de outro commit ou sem comentário, falha na troca com restauração, cada limite falho sem troca e com 1 linha de log, pausa, simular), o `--primeira-vez` (exige `--confirmar`, backup total, ignora a trava 5) e o `schtasks`.
- O `tests/test_atualizar_do_github.py` (T-0003) continua verde sem alteração.
