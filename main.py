from # main.py
import os
import time
import requests
import sqlite3
from collections import defaultdict
from flask import Flask, request, g

# --- Config from env ---
TOKEN = os.getenv("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}/"
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
PORT = int(os.getenv("PORT", 8080))
USER_COOLDOWN = int(os.getenv("USER_COOLDOWN_SECONDS", 3))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "evileuro")  # without @

# --- App + DB setup ---
app = Flask(__name__)
DB_PATH = "bot_data.db"

# simple in-memory rate limiting
_last_request = defaultdict(lambda: 0.0)

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER UNIQUE,
        username TEXT,
        first_seen INTEGER
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        number TEXT,
        status TEXT,
        details TEXT,
        timestamp INTEGER
    )""")
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# --- Helper functions ---
def send_message(chat_id, text, parse_mode=None):
    url = URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def is_owner(message_from):
    # message_from is a dict with 'username' key possibly missing
    username = message_from.get("username", "") or ""
    return username.lower().lstrip("@") == OWNER_USERNAME.lower().lstrip("@")

def record_user(chat_id, username):
    db = get_db()
    cur = db.cursor()
    now = int(time.time())
    cur.execute("INSERT OR IGNORE INTO users (chat_id, username, first_seen) VALUES (?, ?, ?)",
                (chat_id, username, now))
    db.commit()

def record_check(chat_id, number, status, details):
    db = get_db()
    cur = db.cursor()
    now = int(time.time())
    cur.execute("INSERT INTO checks (chat_id, number, status, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (chat_id, number, status, details, now))
    db.commit()

def is_valid_number(text):
    if not text:
        return False
    t = text.strip()
    if t.startswith("+") and t[1:].isdigit() and 8 <= len(t[1:]) <= 15:
        return True
    return False

def check_whatsapp_status(number):
    # same placeholder adapter as before
    if not WHATSAPP_API_URL:
        return {"status": "unknown", "details": "No WHATSAPP_API_URL configured."}
    try:
        headers = {}
        params = {"number": number}
        if WHATSAPP_API_KEY:
            headers["Authorization"] = f"Bearer {WHATSAPP_API_KEY}"
            params["key"] = WHATSAPP_API_KEY
        resp = requests.get(WHATSAPP_API_URL, params=params, headers=headers, timeout=12)
        data = {}
        if resp.headers.get("content-type","").lower().startswith("application/json"):
            data = resp.json()
        if resp.status_code == 200:
            if isinstance(data, dict):
                if "banned" in data:
                    return {"status": "BANNED" if data.get("banned") else "ACTIVE",
                            "details": data.get("reason", str(data))}
                if "status" in data:
                    return {"status": str(data.get("status")), "details": str(data)}
            return {"status": "UNKNOWN", "details": resp.text[:1000]}
        else:
            return {"status": "error", "details": f"API returned {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"status": "error", "details": str(e)}

# --- Routes ---
@app.before_first_request
def startup():
    init_db()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return "OK", 200

    message = data.get("message") or data.get("edited_message") or {}
    if not message:
        return "OK", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user = message.get("from", {})
    user_id = user.get("id")
    username = user.get("username") or ""
    text = message.get("text", "").strip()

    # register user in DB
    try:
        record_user(chat_id, username)
    except Exception:
        pass

    # rate limiting
    now = time.time()
    if now - _last_request[user_id] < USER_COOLDOWN:
        send_message(chat_id, "⏳ Slow down a bit — try again in a few seconds.")
        return "OK", 200
    _last_request[user_id] = now

    # Owner/admin commands
    if text.lower().startswith("/owner"):
        owner_line = f"Owner: @{OWNER_USERNAME}"
        send_message(chat_id, owner_line)
        return "OK", 200

    if text.lower().startswith("/stats"):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as c FROM users")
        users_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM checks")
        checks_count = cur.fetchone()["c"]
        send_message(chat_id, f"📊 Users: {users_count}\n📋 Checks: {checks_count}")
        return "OK", 200

    if text.lower().startswith("/history"):
        if not is_owner(user):
            send_message(chat_id, "❌ Only the owner can use /history.")
            return "OK", 200
        parts = text.split(maxsplit=1)
        limit = 10
        if len(parts) == 2 and parts[1].isdigit():
            limit = min(100, int(parts[1]))
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT number, status, details, timestamp FROM checks ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        if not rows:
            send_message(chat_id, "No history yet.")
            return "OK", 200
        msg = "Recent checks:\n"
        for r in rows:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
            msg += f"{r['number']} → {r['status']} ({ts})\n"
        send_message(chat_id, msg)
        return "OK", 200

    if text.lower().startswith("/broadcast"):
        if not is_owner(user):
            send_message(chat_id, "❌ Only the owner can broadcast.")
            return "OK", 200
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, "Usage: /broadcast Your message here")
            return "OK", 200
        bmsg = parts[1]
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT chat_id FROM users")
        rows = cur.fetchall()
        count = 0
        for r in rows:
            try:
                send_message(r["chat_id"], f"📢 Broadcast from owner:\n\n{bmsg}")
                count += 1
            except Exception:
                pass
        send_message(chat_id, f"Broadcast sent to {count} users.")
        return "OK", 200

    # Help and start
    if text.lower() == "/start":
        send_message(chat_id,
            "🔥 *Evil Ban Checker*\n\nSend a phone number in international format (example: `+2348100000000`) and I'll check its WhatsApp ban status.\n\nOwner: @" + OWNER_USERNAME,
            parse_mode="Markdown")
        return "OK", 200

    if text.lower() in ("/help", "/commands"):
        send_message(chat_id,
            "Commands:\n/start - Start bot\n/help - This help\n/send a number like `+1234567890`\nOwner commands: /stats /history /broadcast",
            parse_mode="Markdown")
        return "OK", 200

    # Phone check
    if is_valid_number(text):
        send_message(chat_id, f"🔎 Checking *{text}* — please wait...", parse_mode="Markdown")
        result = check_whatsapp_status(text)
        status = result.get("status", "unknown")
        details = result.get("details", "")
        record_check(chat_id, text, status, details)
        reply = f"📋 Result for *{text}*:\n*Status:* `{status}`\n*Details:* {details}"
        send_message(chat_id, reply, parse_mode="Markdown")
        return "OK", 200

    send_message(chat_id, "❗ I didn't understand that. Send a phone number in international format like `+1234567890`.", parse_mode="Markdown")
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Evil Ban Checker is running.", 200

if __name__ == "__main__":
    # ensure DB initialized when testing locally
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=PORT))
