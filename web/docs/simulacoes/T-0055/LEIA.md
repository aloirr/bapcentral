# T-0055 — Porta de leitura da web (leitura v1, RN-GER-020)

Simulação (regra 10): os dois JSON desta pasta foram gerados pela própria rota, com o pacote **fictício** dos testes
(`web/tests/test_T0055_porta_leitura.py`). O lote está marcado como fictício; nenhum token real aparece.

## Como chamar

O token fica só no painel do Render (`BAP_WEB_LEITURA_TOKEN`).

```
curl -H "Authorization: Bearer $BAP_WEB_LEITURA_TOKEN" https://<endereço-da-web>/api/leitura/painel
curl -H "Authorization: Bearer $BAP_WEB_LEITURA_TOKEN" https://<endereço-da-web>/api/leitura/resumo/pv_pedidos
```

Só GET. A visão é a do perfil **diretor** (RN-GER-014). Os números são os textos que o site já mostra (nada é recalculado).

## Respostas

| Situação | Código |
|---|---|
| Porta desligada (sem a variável, token com menos de 32 caracteres ou igual a outro segredo: BAP_WEB_TOKEN, BAP_VISITAS_TOKEN, SESSION_SECRET) | 404 |
| Mais de 30 chamadas por minuto por IP ou 120 no total (proteção técnica, não é RN) | 429 + `Retry-After: 60` |
| POST, PUT, PATCH, DELETE, HEAD, OPTIONS | 405 + `Allow: GET` |
| Token ausente ou errado | 401 |
| `rid` que o diretor não vê (ou o Painel, que tem rota própria) | 404 |
| Ainda sem pacote ou sem o farol | 503 |

Corpo das recusas (JSON): 401 `{"erro": "não autorizado"}` (com `WWW-Authenticate: Bearer`); 404 `{"erro": "não encontrado"}`; 405 `{"erro": "só leitura"}`; 429 `{"erro": "muitas chamadas"}`; 503 `{"erro": "sem pacote"}`.

## O que sai

- `pacote`: `lote`, `gerado_em`, `dados_ate`, `du`.
- `/painel`: `visoes` (abas RRM: Resultado, Produtividade, Por DU; e as abas de painel) com cartões
  (título/rótulo, valor, legenda, anéis, faixa de variação, barras por estado) e `farois` (rid e nome dos faróis que o diretor vê).
- `valor` só com número, R$, mi, mil, %, DU, dia(s), h, min, un, x e —; palavra fora disso corta o cartão.
- `/resumo/{rid}`: `rid`, `nome` e os cartões do Resumo (rótulo, valor, cor, estados).

## O que nunca sai

- Tabela, junta, gráfico, insight, linhas e detalhe dos cartões, recortes, ajuda, anexos, CSV, edição.
- Nome, documento (CPF/CNPJ), telefone ou e-mail de cliente ou vendedor (RN-GER-011).
- Meta RH (RN-GER-001).
- TOTAL A PAGAR das Campanhas (RN-GER-015), mesmo que o diretor o veja na tela.
- O cartão com texto desses tipos é cortado inteiro por um filtro final (`leitura.limpar`).
- Estoque Belém: não há `rid` no pacote, fica fora.

## Registro

Uma linha por acesso 200 em `<dados>/acessos/` (login `porta-leitura`, rid, aba `ok`, ação `api`), só pelo registro de acesso que já existe.
As falhas (401 e 429) não gravam em `acessos/`: viram contadores e, a cada minuto, uma linha agregada no log.
Nunca entram token, cabeçalho `Authorization`, consulta nem IP. O IP só é usado em memória, para o limite por minuto.
