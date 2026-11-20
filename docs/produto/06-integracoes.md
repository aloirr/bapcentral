# 06 — Integrações

- **Site BAP Tools** (interno, `172.19.20.76:8501`): o robô entra com usuário e senha (cofre do Windows ou `BAP_SENHA`).
- **Protheus:** pelos relatórios do site (dClientesBap, ftTitulos, ftPedidos, ftNCC...). Inclui A1_LATITU/A1_LONGIT desde 10/11.
- **Máxima:**
  - Espelho e GridRca pelo robô de visitas (`visitas_maxima.py`, login do Alexandre);
  - JSON da rota e da base (`ERP_MXSROTACLI`).
- **BAP Ajuda 2.0** (Render, `aloirr/bapajuda2.0`): respostas (pesquisa, indicação, prospecção) em `RELATORIOS\BAP_AJUDA_RESPOSTAS`.
- **Google Geocoding/Places, OpenStreetMap, BrasilAPI:** coordenadas. As chaves ficam só na pasta de produção.
- **Outlook clássico:** e-mails de parcial, rota e inadimplência.
- **Power BI:** CSV do `exportar_bi.py` (piloto).
