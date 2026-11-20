# BAP Central web no Render (Onda 0 e 1)

Texto de apoio do `modulo-web` (T-0013). **Nada daqui foi publicado.** Deploy só com a frase do Alexandre "aprovo deploy vX.Y.Z".

> **Depende do adendo à ADR 0001.** A ADR 0001 (seção 2.1) escolheu M1 (a web roda `montar`). A decisão do gerente para esta onda é outra: **a web não roda o `montar`**. O robô no PC manda pronta a **parte dado** do contrato (`.coord/contratos/relatorio.md`, §10) dos dois relatórios, e a web só guarda e mostra. O adendo que registra essa mudança fica fora de `web/**` (é do dono da ADR) e precisa existir antes do deploy.

## 1. O que roda

- Python 3.12, FastAPI + Jinja2 + uvicorn. HTML do servidor, sem JavaScript.
- Entrada: `uvicorn app.main:criar_app --factory` (a pasta de trabalho é `web/`).
- Sem `SESSION_SECRET` o app **não sobe** e diz o motivo no log.
- Dados no disco: `$BAP_WEB_DADOS/usuarios.json` (senhas com scrypt + sal) e `$BAP_WEB_DADOS/pacotes/<gerado_em>.json` (os últimos 15). Sem Postgres. Dado de cliente e dado digitado nunca vão ao GitHub.

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
    autoDeploy: false        # deploy só com "aprovo deploy vX.Y.Z"
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.7
      - key: TZ
        value: America/Manaus
      - key: BAP_WEB_DADOS
        value: /var/data
      - key: BAP_WEB_PACOTE_MAX_MB
        value: "25"
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
| `BAP_WEB_TOKEN` | o robô usa em `Authorization: Bearer ...` no `POST /api/pacote` | texto aleatório longo; a mesma chave vai no cofre do Windows do PC do robô |
| `BAP_ADMIN_USUARIO` | login do primeiro admin | ex.: `alexandre` (a-z, 0-9, `.`, `_`, `-`) |
| `BAP_ADMIN_SENHA_INICIAL` | senha provisória do primeiro admin | só vale se `usuarios.json` não existir; a troca é obrigatória no primeiro acesso |

Depois do primeiro acesso, `BAP_ADMIN_SENHA_INICIAL` pode ser apagada do painel. Nenhum segredo vai ao GitHub, a log ou a recado.

## 4. Contrato do `POST /api/pacote` (para o modulo-robo)

- Cabeçalho `Authorization: Bearer $BAP_WEB_TOKEN` (401 se ausente ou errado) e `Content-Type: application/json` (outro tipo, multipart ou `.pkl` = 415).
- Limite `BAP_WEB_PACOTE_MAX_MB` (padrão 25): 413 pelo `Content-Length` ou durante a leitura.
- Corpo: `{"versao_contrato": 1, "gerado_em": "2026-11-20T08:30:00-04:00", "ano": 2026, "mes": 11, "relatorios": {"vc_painel_diretor": <parte dado>, "pl_inadimplencia": <parte dado>}}`.
- Cada relatório: `titulo`, `kpis`, `tabelas`, e no Diretor `paineis[]` com `titulo` e `kpis_export`. Esquema errado = 422 com a lista de problemas. Chaves que começam com `_` são descartadas na gravação.
- `gerado_em` vira o nome do arquivo (só letras e dígitos). Gravação atômica; ficam os 15 mais recentes.
- A web mostra o pacote mais recente. Não calcula nada: formata, filtra e ordena.

## 5. Memória medida (Starter tem 512 MB)

Medida local (Python 3.13, uvicorn, 1 processo) por `VmHWM` de `/proc/<pid>/status`:

| Momento | VmHWM |
|---|---|
| App recém-subido, sem pacote | 60,6 MB |
| Depois de receber um pacote fictício de **3,6 MB** (17 tabelas no Diretor, 5 na Inadimplência com 2 de 4.000 linhas, 3 abas RRM) e abrir as duas telas, as 3 abas, busca e ordem | **81,4 MB** |

O tamanho real do pacote **não é conhecido**: 3,6 MB é estimativa pelo contrato (vc_painel: 17 tabelas, 7 kpis; pl_inadimplencia: 7 tabelas) [SUPOSIÇÃO]. Cada tabela desenha no máximo 300 linhas (o resto vem pela busca e pelo filtro), então a página fica em torno de 0,2 a 0,6 MB. Com folga de mais de 5 vezes sobre os 512 MB, mesmo que o pacote real seja bem maior.

## 6. Como testar em 5 passos (local, sem Render)

1. `pip install -r web/requirements-dev.txt` e, na raiz, `pytest web/tests` (23 testes, todos com dado fictício).
2. Defina no terminal, só para esta sessão: `SESSION_SECRET`, `BAP_WEB_TOKEN`, `BAP_ADMIN_USUARIO`, `BAP_ADMIN_SENHA_INICIAL`, `BAP_WEB_DADOS=./dados_local`, `TZ=America/Manaus`, `BAP_WEB_COOKIE_SEGURO=0` (só em http local).
3. Em `web/`: `uvicorn app.main:criar_app --factory --port 8099` e abra `http://127.0.0.1:8099/saude` (mostra versão, hora de Manaus, `tz_ok` e `ultimo_pacote`).
4. Envie um pacote: `curl -X POST localhost:8099/api/pacote -H "Authorization: Bearer $BAP_WEB_TOKEN" -H "Content-Type: application/json" --data-binary @pacote.json` (resposta 200).
5. Entre em `/login` com o admin, troque a senha (obrigatório), abra "Painel do Diretor" (3 abas) e "Farol de Inadimplência"; em "Usuários" crie um gerente e confira que ele não vê `/usuarios`.

Simulação visual: `web/docs/simulacao_onda1.png` (dados fictícios).

## 7. Limites desta onda

- Gráficos, `insights_painel` e o `painel` (blocos `rrm`) do contrato não são desenhados ainda; o Diretor mostra os cartões de `kpis_export` e as tabelas.
- Perfis `admin`, `diretor` e `gerente` veem os dois relatórios [SUPOSIÇÃO].
- Bloqueio por tentativas vale por usuário existente (5 erros = 15 minutos, ou até o admin trocar a senha); não há limite por IP.
- Uma instância só (disco preso a ela); deploy deixa o serviço fora do ar por alguns segundos.
