# BAP Central web no Render (Onda 0 e 1)

Texto de apoio do `modulo-web` (T-0013). O deploy é automático a cada commit no `main` (R-20261124-210855-alexandre).

> **Depende do adendo à ADR 0001.** A ADR 0001 (seção 2.1) escolheu M1 (a web roda `montar`). A decisão do gerente para esta onda é outra: **a web não roda o `montar`**. O robô no PC manda pronta a **parte dado** do contrato (`.coord/contratos/relatorio.md`, §10) dos dois relatórios, e a web só guarda e mostra. O adendo que registra essa mudança fica fora de `web/**` (é do dono da ADR) e precisa existir antes do deploy.

## 1. O que roda

- Python 3.12, FastAPI + Jinja2 + uvicorn. HTML do servidor; um único JavaScript (`static/cobranca.js`) só na fila de cobrança.
- Entrada: `uvicorn app.main:criar_app --factory` (a pasta de trabalho é `web/`).
- Sem `SESSION_SECRET` o app **não sobe** e diz o motivo no log.
- Dados no disco: `$BAP_WEB_DADOS/usuarios.json` (senhas com scrypt + sal) e `$BAP_WEB_DADOS/pacotes/<gerado_em>.json` (os últimos 7) e `cobranca/` (diário do site, §10.6.5). Sem Postgres. Dado de cliente e dado digitado nunca vão ao GitHub.

## 2. Texto proposto do `render.yaml` (governança: proposta ao gerente, não entra no PR)

```yaml
services:
  - type: web
    name: bap-central
    runtime: python
    plan: starter            # US$ 7, 512 MB [SUPOSIÇÃO: confirmar no painel]
    region: oregon
    rootDir: web
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:criar_app --factory --host 0.0.0.0 --port $PORT
    healthCheckPath: /saude
    autoDeploy: true         # deploy automático a cada commit no main (R-20261124-210855-alexandre)
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.7
      - key: TZ
        value: America/Manaus
      - key: BAP_WEB_DADOS
        value: /var/data
      - key: BAP_WEB_PACOTE_MAX_MB
        value: "2"
      - key: SESSION_SECRET
        sync: false          # o Alexandre cria no painel
      - key: BAP_WEB_TOKEN
        sync: false
      - key: BAP_ADMIN_USUARIO
        sync: false
      - key: BAP_ADMIN_SENHA_INICIAL
        sync: false
    disk:
      name: bap-dados
      mountPath: /var/data
      sizeGB: 1
```

## 3. Segredos que só o Alexandre cria (painel do Render, "Environment")

| Variável | O que é | Como gerar |
|---|---|---|
| `SESSION_SECRET` | assina o cookie de sessão | texto aleatório longo (mínimo 16; use 48 hex) |
| `BAP_WEB_TOKEN` | o robô usa em `Authorization: Bearer ...` no `POST /api/pacote` | texto aleatório de no mínimo 32 caracteres (o app não sobe com menos); a mesma chave vai no cofre do Windows do PC do robô |
| `BAP_ADMIN_USUARIO` | login do primeiro admin | ex.: `alexandre` (a-z, 0-9, `.`, `_`, `-`) |
| `BAP_ADMIN_SENHA_INICIAL` | senha provisória do primeiro admin | só vale se `usuarios.json` não existir; a troca é obrigatória no primeiro acesso |

Depois do primeiro acesso, `BAP_ADMIN_SENHA_INICIAL` pode ser apagada do painel. Nenhum segredo vai ao GitHub, a log ou a recado.

## 4. Contrato do `POST /api/pacote` (para o modulo-robo)

- Cabeçalho `Authorization: Bearer $BAP_WEB_TOKEN` (401 se ausente ou errado) e `Content-Type: application/json` (outro tipo, multipart ou `.pkl` = 415).
- Limite `BAP_WEB_PACOTE_MAX_MB` (padrão 2): 413 pelo `Content-Length` ou durante a leitura.
- Escopo da T-0013 (R-20261120-120939): só **Painel · resultado** e **Painel · produtividade** do `vc_painel`. Não há mais Inadimplência nem a aba "por dia útil".
- Corpo (as chaves que a tela lê):

```json
{"versao_contrato": 1, "gerado_em": "2026-11-20T08:30:00-04:00", "ano": 2026, "mes": 11,
 "relatorios": {"vc_painel": {"titulo": "Painel Executivo", "abas": {
   "resultado":     {"titulo": "Painel · resultado", "kpis_export": [], "altura_min": 2000,
                     "painel": {"blocos": [{"tipo": "rrm", "visao": "res", "dados": {"res": [CARTÃO, ...], "sub": {"res": "visão absoluta · ..."}, "como_ler": "...", "avisos": []}}]}},
   "produtividade": {"titulo": "Painel · produtividade", "...": "igual, com visao \"prod\" e dados.prod / dados.sub.prod"}}}}}
```

- Como o PC monta: `relatorios_nucleo._abas_do_painel` insere `paineis[0]` e `paineis[1]` a partir de `painel_rrm.VISOES` (`res`, `prod`), cada um com um bloco `rrm` cujo `dados` é a saída de `painel_rrm.calcular`. **Escolha**: o robô manda esses dois itens em `abas.resultado` e `abas.produtividade` (a web identifica a aba pela chave e confere `painel.blocos[0].tipo == "rrm"` e `visao == "res"|"prod"`, não pelo título nem pelo índice). A web só lê `dados[visao]`, `dados.sub[visao]`, `dados.como_ler` e `dados.avisos`; o resto (`du`, `comp`, `dados_ate`, `diretor`) pode ir, mas é descartado na gravação. O robô deve mandar só essas duas visões, para o pacote ficar pequeno.
- `CARTÃO` é o dict de `painel_rrm.card`, em JSON (tupla vira lista): `{"titulo", "valor" (texto pronto), "legenda", "aneis": [[rótulo, % (número), meta (texto)]], "faixa": [[mês, variação (texto), tom, fechamento (texto)]] (até 3), "estados": {"barras": [[UF, número, texto, % ou variação (texto), tom]], "legenda"} | null, "ajuda"}`. `tom` em `ok`, `atencao`, `alerta` ou `""`.
- A web não recalcula: mostra textos e números como vêm. Só a apresentação é dela: o percentual do anel (`11%`), o arco SVG e a cor do anel (verde ≥ 100, amarelo 90-99, vermelho < 90, as mesmas faixas do PC, pois o PC não manda o tom do anel), e a altura relativa da barra (`|número| ÷ maior`).
- Esquema errado (sem `vc_painel`, sem uma das duas abas, cartão malformado) = 422 com a lista de problemas. Chaves que começam com `_` são descartadas. `gerado_em` (ISO 8601) vira o nome do arquivo (só letras e dígitos); gravação atômica; ficam os 15 mais recentes.
- O campo `paineis[0].diretor` (`painel_diretor.calcular`) **não é necessário**: o cartão já traz tudo o que o PC desenha (anéis, faixa, barras). Nada a pedir ao robô.

## 5. Memória medida (Starter tem 512 MB)

Medida local (Python 3.13, uvicorn, 1 processo) por `VmHWM` de `/proc/<pid>/status`:

| Momento | VmHWM |
|---|---|
| App recém-subido, sem pacote | 60,6 MB |
| Pacote de exemplo esperado (2 abas × 10 cartões, 12 KB) recebido e as 2 telas abertas | **62,8 MB** |
| Estresse: 2 abas × 500 cartões (565 KB, 50 vezes o esperado), 2 telas abertas | 69,7 MB |

O pacote do painel é pequeno (cartões e textos prontos, sem tabelas). Folga de mais de 7 vezes sobre os 512 MB. O tamanho real é estimado pelo contrato [SUPOSIÇÃO].

## 6. Como testar em 5 passos (local, sem Render)

1. `pip install -r web/requirements-dev.txt` e, na raiz, `pytest web/tests` (todos com dado de exemplo, agregado por UF).
2. Defina no terminal, só para esta sessão: `SESSION_SECRET`, `BAP_WEB_TOKEN`, `BAP_ADMIN_USUARIO`, `BAP_ADMIN_SENHA_INICIAL`, `BAP_WEB_DADOS=./dados_local`, `TZ=America/Manaus`, `BAP_WEB_COOKIE_SEGURO=0` (só em http local).
3. Em `web/`: `uvicorn app.main:criar_app --factory --port 8099` e abra `http://127.0.0.1:8099/saude` (mostra versão, hora de Manaus, `tz_ok` e `ultimo_pacote`).
4. Envie um pacote: `curl -X POST localhost:8099/api/pacote -H "Authorization: Bearer $BAP_WEB_TOKEN" -H "Content-Type: application/json" --data-binary @pacote.json` (resposta 200).
5. Entre em `/login` com o admin, troque a senha (obrigatório), abra "Painel Executivo" (abas Painel · resultado e Painel · produtividade); em "Usuários" crie um gerente e confira que ele não vê `/usuarios`.

Simulação visual: `web/docs/simulacao_onda1.png` (dados de exemplo, agregados por UF; o rótulo da imagem ainda diz "fictícios").

## 7. Limites desta onda

- Só `vc_painel`, abas resultado e produtividade. Tabelas, gráficos, "por dia útil" e Inadimplência ficam para outra onda.
- Perfis `admin`, `diretor` e `gerente` veem o painel [SUPOSIÇÃO].
- Bloqueio por tentativas vale por usuário existente (5 erros = 15 minutos, ou até o admin trocar a senha); não há limite por IP.
- Uma instância só (disco preso a ela); deploy deixa o serviço fora do ar por alguns segundos.
