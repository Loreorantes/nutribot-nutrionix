"""
NutriBot – Asistente de IA de Producción y Costos de Nutrionix (Fase 2)
Aplicación web (Flask) hospedada en Azure App Service que conversa con un
AGENTE de Microsoft Foundry (modelo + instrucciones + conocimiento).

Autenticación: Microsoft Entra ID mediante la IDENTIDAD ADMINISTRADA del App Service
(DefaultAzureCredential). No hay llaves ni contraseñas en el código.

Variables de entorno (App Service > Configuración):
  PROJECT_ENDPOINT  https://<recurso>.services.ai.azure.com/api/projects/<proyecto>
  AGENT_NAME        nombre del agente en Foundry (ej. nutribot)
  FLASK_SECRET      cualquier texto largo (firma la cookie de sesión)
"""
import base64
import logging
import os
import re

from flask import Flask, jsonify, render_template, request, session

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nutribot")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "nutrionix-fase2-demo")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB por petición

PROJECT_ENDPOINT = os.environ.get("PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "nutribot")
ALLOWED_IMAGES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

_openai_client = None


def get_openai_client():
    """Cliente OpenAI (Responses API) obtenido desde el proyecto de Foundry."""
    global _openai_client
    if _openai_client is None:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        _openai_client = project_client.get_openai_client()
    return _openai_client


def get_conversation_id(client, reset=False):
    """El historial vive en el objeto 'conversation' del servidor de Foundry."""
    if reset or not session.get("conv_id"):
        conv = client.conversations.create()
        session["conv_id"] = conv.id
    return session["conv_id"]


CITATION_MARK = re.compile(r"【[^】]*】|\ue200[^\ue201]*\ue201|[\ue200-\ue2ff]")


def extract_answer(response):
    """Texto de la respuesta + documentos citados (transparencia)."""
    text = CITATION_MARK.sub("", response.output_text or "").strip()
    sources, tools_used = [], []
    for item in response.output or []:
        itype = getattr(item, "type", "")
        if itype.endswith("_call"):
            tools_used.append(itype)
        if itype == "message":
            for part in getattr(item, "content", []) or []:
                for ann in getattr(part, "annotations", []) or []:
                    name = getattr(ann, "filename", None) or getattr(ann, "title", None)
                    if name and name not in sources:
                        sources.append(name)
    return text, sources, sorted(set(tools_used))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"ok": True, "agent": AGENT_NAME, "endpoint_configurado": bool(PROJECT_ENDPOINT)}


@app.route("/api/reset", methods=["POST"])
def reset():
    session.pop("conv_id", None)
    return {"ok": True}


@app.route("/api/chat", methods=["POST"])
def chat():
    message = (request.form.get("message") or "").strip()
    image = request.files.get("image")

    if not message and not image:
        return jsonify(error="Escribe una pregunta o adjunta una foto."), 400
    if not PROJECT_ENDPOINT:
        return jsonify(error="Falta configurar PROJECT_ENDPOINT en el App Service."), 500

    content = []
    if image and image.filename:
        if image.mimetype not in ALLOWED_IMAGES:
            return jsonify(error="Formato no soportado. Usa JPG, PNG o WEBP."), 400
        b64 = base64.b64encode(image.read()).decode("ascii")
        if not message:
            message = ("Extrae los datos de esta orden de producción en papel y "
                       "conviértelos a la plantilla oficial de Nutrionix.")
        content.append({"type": "input_text", "text": message})
        content.append({"type": "input_image",
                        "image_url": f"data:{image.mimetype};base64,{b64}"})
    else:
        content.append({"type": "input_text", "text": message})

    client = get_openai_client()
    for attempt in (1, 2):
        try:
            conv_id = get_conversation_id(client, reset=(attempt == 2))
            response = client.responses.create(
                conversation=conv_id,
                input=[{"role": "user", "content": content}],
                extra_body={"agent_reference": {"name": AGENT_NAME, "type": "agent_reference"}},
            )
            text, sources, tools_used = extract_answer(response)
            return jsonify(answer=text, sources=sources, tools=tools_used)
        except Exception as exc:  # noqa: BLE001
            log.exception("Error al llamar al agente (intento %s)", attempt)
            if attempt == 2:
                return jsonify(error=f"No pude obtener respuesta del agente: {exc}"), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
