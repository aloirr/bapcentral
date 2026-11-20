# 02 — Módulos

| Módulo | Agente | Arquivos principais | Faróis / telas |
|---|---|---|---|
| Robô | modulo-robo | `bap_automation.py`, `base_cliente.py`, `solicitacao_bap.py`, `visitas_maxima.py` | rodada do robô, BASE_CLIENTE, Atualizar visitas |
| Dados | engenheiro-dados | `bap_dados.py`, `dados_bap.py`, `xlsx_rapido.py`, `catalogo_bap.py` | cache, fotografia, catálogo |
| Faróis | modulo-farois | `relatorios_nucleo.py`, `bap_relatorios.py`, `bap_visual.py`, `painel_*.py`, `bap_central.py` | todos os faróis, Painel do Diretor/Executivo, parciais, Campanhas, DDR |
| Pós-venda | modulo-posvenda | `pos_venda.py`, `garantias.py`, `ncc_controle.py`, `transportadoras.py`, `email_inadimplencia.py` | Entregas, Garantias, NCC, Inadimplência, WhatsApp |
| Rota | modulo-rota | `planner_nucleo.py`, `bap_planner.py`, `rota_lugar.py`, `geocodificar.py` | Planner, Roteirização, JSON da Máxima |
| Metas | modulo-metas | `meta_nucleo.py`, `bap_meta.py`, `bap_analista.py`, `bap_oportunidade.py` | Gerador de Meta, RV, RH, Kits |
| Web | modulo-web | `web/` (a criar) | BAP Central na web |

O mapa completo arquivo → dono está em `.coord/donos.json`.
