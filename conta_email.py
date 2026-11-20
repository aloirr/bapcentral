"""
A CONTA DE E-MAIL CORPORATIVA (Microsoft 365), CONECTADA UMA VEZ

Usa a biblioteca oficial da Microsoft (msal) e a API Microsoft Graph:
    - conecta uma vez com a conta @bapautoparts.com.br (codigo no navegador,
      com a verificacao em duas etapas normal da empresa);
    - fica conectado: o login renova sozinho a cada uso (~90 dias sem usar
      e pede de novo);
    - envia pela SUA caixa (o e-mail aparece nos Itens Enviados), em HTML e
      com o PDF anexado. Nao precisa de Outlook nenhum aberto nem instalado.

O app e o MESMO registro "Automacao BAP Tools" do bap_automation.py. O
locatario da empresa exige que o TI aprove o app uma vez (tela "Aprovacao
necessaria"): na primeira conexao, peca a aprovacao ali mesmo, com o texto
de TEXTO_PARA_O_TI. Aprovado, vale para todo mundo.

O login fica em auth/email_token.bin, criptografado com a conta do Windows
(so o seu usuario, neste computador, consegue abrir).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARQ_TOKEN = AQUI / "SISTEMA BAP" / "auth" / "email_token.bin"

# o mesmo registro do bap_automation.py (Automacao BAP Tools)
CLIENT_ID = "3d5e39c3-5230-4e2b-a7ae-cb2b71fad1c7"
TENANT_ID = "743d9744-08b4-4b52-b358-56ae77c79473"
ESCOPOS = ["Mail.Send", "User.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"

TEXTO_PARA_O_TI = (
    "Aplicativo interno 'Automacao BAP Tools' (cliente publico, sem segredo). "
    "Permissoes delegadas Mail.Send e User.Read: envia, pela caixa do "
    "proprio usuario que fez login, a parcial de metas de cada vendedor, "
    "supervisor e gerente da BAP Auto Parts (Farol de Metas). Nao le e-mails "
    "nem acessa a caixa de ninguem.")


class PrecisaAprovacao(RuntimeError):
    """O locatario exige aprovacao do administrador para o app."""


# --------------------------------------------------------------- o cofre
def _proteger(dados: bytes) -> bytes:
    try:
        import win32crypt                               # noqa: PLC0415
        return b"DPAPI" + win32crypt.CryptProtectData(dados, "BAP", None,
                                                      None, None, 0)
    except Exception:                                   # noqa: BLE001
        return dados


def _abrir(dados: bytes) -> bytes:
    if dados.startswith(b"DPAPI"):
        import win32crypt                               # noqa: PLC0415
        return win32crypt.CryptUnprotectData(dados[5:], None, None, None,
                                             0)[1]
    return dados


def _app():
    import msal                                         # noqa: PLC0415
    cache = msal.SerializableTokenCache()
    if ARQ_TOKEN.exists():
        try:
            cache.deserialize(_abrir(ARQ_TOKEN.read_bytes()).decode("utf-8"))
        except Exception:                               # noqa: BLE001
            pass                        # ilegivel (outro usuario): refaz
    app = msal.PublicClientApplication(
        CLIENT_ID, authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache)
    return app, cache


def _guardar(cache) -> None:
    if cache.has_state_changed:
        ARQ_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        ARQ_TOKEN.write_bytes(_proteger(cache.serialize().encode("utf-8")))


def disponivel() -> bool:
    try:
        import msal                                     # noqa: F401,PLC0415
        import requests                                 # noqa: F401,PLC0415
        return True
    except ImportError:
        return False


# --------------------------------------------------------------- o login
def conta_conectada() -> str:
    """O e-mail da conta conectada (login guardado e valido), ou ""."""
    if not disponivel():
        return ""
    try:
        app, cache = _app()
        contas = app.get_accounts()
        if not contas:
            return ""
        r = app.acquire_token_silent(ESCOPOS, account=contas[0])
        _guardar(cache)
        return contas[0].get("username", "") if r and "access_token" in r \
            else ""
    except Exception:                                   # noqa: BLE001
        return ""


def _token() -> str:
    app, cache = _app()
    contas = app.get_accounts()
    r = app.acquire_token_silent(ESCOPOS, account=contas[0]) if contas \
        else None
    _guardar(cache)
    if not r or "access_token" not in r:
        raise RuntimeError("A conta de e-mail não está conectada.")
    return r["access_token"]


def iniciar_conexao() -> dict:
    """Comeca o login: devolve {codigo, endereco, fluxo}. A pessoa abre o
    endereco, digita o codigo e entra com a conta da empresa."""
    app, _cache = _app()
    fluxo = app.initiate_device_flow(scopes=ESCOPOS)
    if "user_code" not in fluxo:
        raise RuntimeError(fluxo.get("error_description")
                           or "A Microsoft não deu o código de login.")
    return {"codigo": fluxo["user_code"],
            "endereco": fluxo["verification_uri"], "fluxo": fluxo}


def concluir_conexao(inicio: dict) -> str:
    """Espera a pessoa terminar no navegador (ate ~15 min). Devolve o
    e-mail conectado."""
    app, cache = _app()
    r = app.acquire_token_by_device_flow(inicio["fluxo"])
    if "access_token" not in r:
        texto = r.get("error_description") or str(r)
        if any(x in texto for x in ("AADSTS65001", "AADSTS90094",
                                    "consent", "admin")):
            raise PrecisaAprovacao(texto)
        raise RuntimeError(texto)
    _guardar(cache)
    return (r.get("id_token_claims") or {}).get("preferred_username", "")


def desconectar() -> None:
    try:
        ARQ_TOKEN.unlink()
    except OSError:
        pass


# --------------------------------------------------------------- o envio
def enviar_email(para, assunto, html_corpo, anexos=(), token=None) -> None:
    """Envia pela caixa da conta conectada (fica nos Itens Enviados)."""
    import requests                                     # noqa: PLC0415
    token = token or _token()
    msg = {"subject": assunto,
           "body": {"contentType": "HTML", "content": html_corpo},
           "toRecipients": [{"emailAddress": {"address": e}}
                            for e in ([para] if isinstance(para, str)
                                      else para)]}
    if anexos:
        msg["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": Path(a).name,
            "contentType": "application/pdf" if str(a).lower().endswith(
                ".pdf") else "text/html",
            "contentBytes": base64.b64encode(Path(a).read_bytes()).decode()}
            for a in anexos]
    r = requests.post(f"{GRAPH}/me/sendMail",
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"},
                      data=json.dumps({"message": msg,
                                       "saveToSentItems": True}), timeout=60)
    if r.status_code != 202:
        try:
            erro = r.json().get("error", {}).get("message", r.text)
        except ValueError:
            erro = r.text
        raise RuntimeError(f"Microsoft 365 recusou ({r.status_code}): "
                           f"{erro[:200]}")
