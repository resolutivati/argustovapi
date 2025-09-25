from flask import Flask, request, jsonify
import re, requests, os, traceback

app = Flask(__name__)

# ===== VARIÁVEIS DE AMBIENTE =====
VAPI_API_URL   = os.environ.get("VAPI_API_URL", "https://api.vapi.ai")
VAPI_API_KEY   = os.environ.get("VAPI_API_KEY")  # coloque sua PRIVATE key no Render
VAPI_AGENT_ID  = os.environ.get("VAPI_AGENT_ID") # assistantId do agente IA
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "170808")
DRY_RUN        = os.environ.get("DRY_RUN", "0")  # "1" = não liga, só loga

def normalize_phone(raw):
    digits = re.sub(r"\D+", "", raw or "")
    if not digits:
        return None
    return digits if digits.startswith("55") else "55" + digits

def call_vapi(phone, name="", meta=None):
    if DRY_RUN == "1":
        print("[DRY_RUN] Chamaria VAPI com:", phone, name, meta)
        return {"dry_run": True, "customer": {"number": f"+{phone}"}, "assistantId": VAPI_AGENT_ID}

    if not VAPI_API_KEY:
        raise RuntimeError("VAPI_API_KEY ausente")
    if not VAPI_AGENT_ID:
        raise RuntimeError("VAPI_AGENT_ID ausente")
    phone_number_id = os.environ.get("VAPI_PHONE_NUMBER_ID")  # << NOVO: id do número na Vapi
    if not phone_number_id:
        raise RuntimeError("VAPI_PHONE_NUMBER_ID ausente (id do número emissor da Vapi)")

    payload = {
        "assistantId": VAPI_AGENT_ID,
        "phoneNumberId": phone_number_id,
        "customer": { "number": f"+{phone}" },  # phone já vem sem +, então prefixamos
        # opcional: overrides por chamada
        # "assistantOverrides": { "variableValues": {"nome": name} },
        "metadata": meta or {}
    }
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{VAPI_API_URL}/call"  # conforme docs de Outbound Calls
    print("[VAPI] POST", url, "payload=", payload)
    r = requests.post(url, json=payload, headers=headers, timeout=25)
    print("[VAPI] status", r.status_code, "resp:", r.text[:500])
    r.raise_for_status()
    return r.json()

@app.get("/")
def home():
    return "OK", 200

@app.get("/health")
def health():
    return {"status": "up"}, 200
@app.post("/vapi/inbound")

def vapi_inbound():
    """
    Endpoint chamado pela Vapi quando alguém liga para o seu número (+55 43 94040 4567).
    Use para logar, enriquecer contexto e (se quiser) escolher dinamicamente o assistant.
    """
    try:
        # (Opcional) validar um segredo se você configurar credencial na Vapi:
        expected = os.environ.get("VAPI_INBOUND_SECRET")  # ex: "170808"
        got = request.headers.get("X-Vapi-Secret")
        if expected and got != expected:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        print("[VAPI INBOUND] recebido:", data)

        # Monte contexto opcional (ex.: quem ligou, id da ligação, etc)
        caller = data.get("from") or data.get("customer", {}).get("number") or ""
        metadata = {
            "source": "inbound-number",
            "caller": caller,
            # você pode repassar dados do Argus/CRM aqui também
        }

        # Resposta mínima: informe o assistant que deve atender e metadados
        return jsonify({
            "assistantId": VAPI_AGENT_ID,  # usa o mesmo assistant do outbound
            "metadata": metadata
            # Se quiser overrides por chamada:
            # "assistantOverrides": { "variableValues": {"nomeCliente": "..." } }
        }), 200

    except Exception as e:
        print("[VAPI INBOUND][EXCEPTION]", e)
        return jsonify({"ok": False, "error": "server_error", "detail": str(e)}), 500
        
@app.post("/argus/webhook")
def argus_webhook():
    try:
        # valida segredo
        secret = request.headers.get("X-Argus-Secret", "")
        if secret != WEBHOOK_SECRET:
            print("[AUTH] Segredo inválido:", secret)
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        print("[WEBHOOK] recebido:", data)

        # Só processa derivação (id=4 e acionouDerivacao true)
        if data.get("idTipoWebhook") != 4 or not data.get("acionouDerivacao", False):
            return jsonify({"ok": True, "ignored": True}), 200

        phone = normalize_phone(data.get("telefone"))
        if not phone:
            return jsonify({"ok": False, "error": "telefone invalido"}), 400

        name = data.get("nomeCliente") or ""
        meta = {"argus": data}

        resp = call_vapi(phone, name=name, meta=meta)
        return jsonify({"ok": True, "vapi": resp}), 200

    except requests.HTTPError as http_err:
        return jsonify({
            "ok": False,
            "error": "vapi_http_error",
            "detail": str(http_err),
            "body": getattr(http_err.response, "text", "")[:200]
        }), 502
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": "server_error", "detail": str(e)}), 500

# ⚠️ Não precisa app.run() aqui se usar Gunicorn no Render


