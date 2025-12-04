import os
from telegram.ext import Updater, CommandHandler

BOT_TOKEN = os.getenv("7982718796:AAFQ7uUpG_b-apWRlmVt7YwDRfU7YQKHXxc")

def start(update, context):
    update.message.reply_text("👁‍🔥 Evil Ban Checker Activated!\nSend a number to check WhatsApp status.")

def check(update, context):
    number = update.message.text.strip()

    # Fake checker logic — replace later with real API
    if number.startswith("+"):
        update.message.reply_text(f"🔍 Checking {number}...\n\n⚠️ Result: Looks Safe (Not Banned)")
    else:
        update.message.reply_text("❌ Invalid number format! Use +234...")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("check", check))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
