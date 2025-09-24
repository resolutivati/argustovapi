from flask import Flask, request, jsonify
import re, requests, os, traceback

app = Flask(__name__)

# ===== VARIÁVEIS DE AMBIENTE =====
VAPI_API_URL   = os.environ.get("VAPI_API_URL", "https://api.vapi.ai")
VAPI_API_KEY   = os.environ.get("VAPI_API_KEY")  # OBRIGATÓRIA
VAPI_AGENT_ID  = os.environ.get("VAPI_AGENT_ID") # OBRIGATÓRIA (assistantId)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "170808")
DRY_RUN        = os.environ.get("DRY_RUN", "0")  # "1" = não chama Vapi, só loga

def normalize_phone(raw):
    digits = re.sub(r"\D+", "", raw or "")
    if not digits:
        return None
    return digits if digits.startswith("55") else "55" + digits

def call_vapi(phone, name="", meta=None):
    if DRY_RUN == "1":
        print("[DRY_RUN] Chamaria VAPI com:", phone, name, meta)
        return {"dry_run": True, "to": phone, "assistantId": VAPI_AGENT_ID}

    if not VAPI_API_KEY:
        raise RuntimeError("VAPI_API_KEY ausente nas variáveis de ambiente")
    if not VAPI_AGENT_ID:
        raise RuntimeError("VAPI_AGENT_ID ausente nas variáveis de ambiente")

    payload = {
        "to": phone,
        "assistantId": VAPI_AGENT_ID,  # conforme docs Vapi
        "language": "pt-BR",
        "metadata": meta or {}
    }
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{VAPI_API_URL}/call"  # se sua doc exigir, troque para /v1/calls
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

@app.post("/argus/webhook")
def argus_webhook():
    try:
        # Validação simples de segredo
        secret = request.headers.get("X-Argus-Secret", "")
        if secret != WEBHOOK_SECRET:
            print("[AUTH] Segredo inválido:", secret)
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        # Ler JSON com tolerância
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        print("[WEBHOOK] payload recebido:", data)

        # Checar tipo de evento e derivação
        tipo = data.get("idTipoWebhook")
        deriv = data.get("acionouDerivacao", False)
        if tipo != 4 or not deriv:
            print("[WEBHOOK] Evento ignorado. idTipoWebhook=", tipo, "acionouDerivacao=", deriv)
            return jsonify({"ok": True, "ignored": True}), 200

        raw_phone = data.get("telefone")
        phone = normalize_phone(raw_phone)
        if not phone:
            print("[ERRO] Telefone ausente/inválido:", raw_phone)
            return jsonify({"ok": False, "error": "telefone invalido"}), 400

        name = data.get("nomeCliente") or ""
        meta = {"argus": {
            "idDominio": data.get("idDominio"),
            "idCampanha": data.get("idCampanha"),
            "idSkill": data.get("idSkill"),
            "idLote": data.get("idLote"),
            "nrLead": data.get("nrLead"),
            "codCliente": data.get("codCliente"),
            "idLigacao": data.get("idLigacao")
        }}

        resp = call_vapi(phone, name=name, meta=meta)
        return jsonify({"ok": True, "vapi": resp}), 200

    except requests.HTTPError as http_err:
        print("[HTTPERROR]", http_err, "body=", getattr(http_err.response, "text", "")[:500])
        return jsonify({"ok": False, "error": "vapi_http_error", "detail": str(http_err),
                        "body": getattr(http_err.response, "text", "")[:500]}), 502
    except Exception as e:
        print("[EXCEPTION]", e)
        traceback.print_exc()
        return jsonify({"ok": False, "error": "server_error", "detail": str(e)}), 500
