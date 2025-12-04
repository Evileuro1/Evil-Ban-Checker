from flask import Flask, request
import requests
import os

TOKEN = os.getenv("BOT_TOKEN")  # <-- CORRECT
URL = f"https://api.telegram.org/bot{TOKEN}/"

app = Flask(__name__)

def send_message(chat_id, text):
    url = URL + "sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send_message(chat_id, "🔥 Evil Ban Checker Online!")
        else:
            send_message(chat_id, "❗ Send /start to test.")

    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Hello from Evil Ban Checker!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
