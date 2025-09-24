from flask import Flask, request, jsonify
import re, requests, os

app = Flask(__name__)

VAPI_API_URL = os.environ.get("VAPI_API_URL", "https://api.vapi.ai/v1/calls")
VAPI_API_KEY = os.environ.get("VAPI_API_KEY", "COLOQUE_SUA_CHAVE_DA_VAPI")
VAPI_AGENT_ID = os.environ.get("VAPI_AGENT_ID", "agente_resolutiva")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "segredo123")

def normalize_phone(raw):
    digits = re.sub(r"\D+", "", raw or "")
    if digits.startswith("55"):
        return digits
    return "55" + digits

def call_vapi(phone, name="", meta=None):
    payload = {
        "to": phone,
        "assistantId": VAPI_AGENT_ID,  # na Vapi é "assistantId"
        "language": "pt-BR",
        "metadata": meta or {}
    }
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    r = requests.post(f"{VAPI_API_URL}/call", json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

@app.route("/argus/webhook", methods=["POST"])
def argus_webhook():
    if request.headers.get("X-Argus-Secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(force=True)
    if data.get("idTipoWebhook") == 4 and data.get("acionouDerivacao", False):
        phone = normalize_phone(data.get("telefone"))
        name  = data.get("nomeCliente") or ""
        meta  = {"argus": data}
        try:
            resp = call_vapi(phone, name=name, meta=meta)
            return jsonify({"ok": True, "vapi": resp}), 200
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "ignored": True}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

