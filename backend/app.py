import json
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from config import load_config
from chat_service import ChatService
from db.database import init_db
from db.seed import seed_pois
from tools.amap import reverse_geocode
from tools.xhs_ugc import search_xhs_public_notes, read_public_webpage

app = Flask(__name__)
CORS(app)

# 初始化数据库
init_db()
seed_pois()

config = load_config()
chat_service = ChatService(config)


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    result = chat_service.chat(message, session_id)
    return jsonify({
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
        "alternatives": result.get("alternatives", []),
        "intent": result.get("intent"),
    })


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    def generate():
        for chunk in chat_service.chat_stream(message, session_id):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/reorder", methods=["POST"])
def reorder():
    data = request.get_json(silent=True) or {}
    blocks = data.get("blocks", [])
    session_id = data.get("session_id", "default")

    if not blocks:
        return jsonify({"error": "blocks is required"}), 400

    result = chat_service.reorder(blocks, session_id)
    return jsonify({
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
    })


@app.route("/api/itinerary/adjust", methods=["POST"])
def adjust_itinerary():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    session_id = data.get("session_id", "default")
    payload = data.get("payload", {})

    if not action:
        return jsonify({"error": "action is required"}), 400

    result = chat_service.adjust(action, session_id, payload)
    return jsonify({
        "message": result.get("message", ""),
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
        "alternatives": result.get("alternatives", []),
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/location/reverse", methods=["POST"])
def reverse_location():
    data = request.get_json(silent=True) or {}
    location = data.get("location", "").strip()

    if not location:
        return jsonify({"error": "location is required"}), 400

    result = reverse_geocode.invoke({"location": location})
    payload = json.loads(result)
    status = 400 if payload.get("error") else 200
    return jsonify(payload), status


@app.route("/api/ugc/xhs/search", methods=["POST"])
def search_xhs_ugc():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    limit = data.get("limit", 5)

    if not query:
        return jsonify({"error": "query is required"}), 400

    result = search_xhs_public_notes.invoke({"query": query, "limit": limit})
    return jsonify({"items": json.loads(result)})


@app.route("/api/ugc/read-page", methods=["POST"])
def read_ugc_page():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    max_chars = data.get("max_chars", 4000)

    if not url:
        return jsonify({"error": "url is required"}), 400

    result = read_public_webpage.invoke({"url": url, "max_chars": max_chars})
    payload = json.loads(result)
    status = 400 if payload.get("error") else 200
    return jsonify(payload), status


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
