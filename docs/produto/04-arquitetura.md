# 04 — Arquitetura e dados (hoje)

- **Robô** (`bap_automation.py`, PC dentro da rede):
  - site BAP Tools `172.19.20.76:8501` (7 relatórios);
  - saídas: TABELA_BAP (saída; a fotografia fica em `RELATORIOS\DADOS`), ESTOQUE_BAP, BASE_CLIENTE (+ coordenadas), SOLICITACAO_BAP, pós-venda e cache (`_CACHE_RELATORIOS`, `bap_dados` VERSAO 27);
  - ao fim, a sincronização do BAP Ajuda (4e, precisa de Git).
- **Telas:** BAP Central → `bap_relatorios.py <id>` → `relatorios_nucleo.montar(id)` → dicionário (o contrato da T-0002) → `bap_visual` (Tkinter, PDF, Excel).
- **Cadastros:** BAP Analista (Planner, Gerador de Meta, Kits, Entrega, DDR, Saldo). As configurações são `.json` na raiz.
- **Dados digitados:** os diários por máquina em `RELATORIOS\_*` (só acrescentam linha).
- **Alvo:** ver `05-roadmap.md` e a T-0006.
