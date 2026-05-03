import json
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from config import load_config
from chat_service import ChatService

app = Flask(__name__)
CORS(app)

config = load_config()
chat_service = ChatService(config)


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    result = chat_service.chat(message, session_id)
    return jsonify({
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
        "intent": result.get("intent"),
    })


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    def generate():
        for chunk in chat_service.chat_stream(message, session_id):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
