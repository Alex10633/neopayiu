import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import shelve
import os
from dotenv import load_dotenv

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Define the database
DB_FILE = "exchange_data.db"

def get_group_data(group_id):
    with shelve.open(DB_FILE) as db:
        return db.get(str(group_id), {"rate": 0.0, "inr_paid": 0.0, "usdt_sent": 0.0})

def save_group_data(group_id, data):
    with shelve.open(DB_FILE) as db:
        db[str(group_id)] = data

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    if context.args:
        try:
            rate = float(context.args[0])
            data = get_group_data(group_id)
            data['rate'] = rate
            save_group_data(group_id, data)
            await update.message.reply_text(f"✅ USDT rate set to {rate}")
        except ValueError:
            await update.message.reply_text("❌ Invalid rate format. Use: /set 91.5")
    else:
        await update.message.reply_text("❌ Please provide a rate. Use: /set 91.5")

async def handle_inr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    text = update.message.text.strip()
    data = get_group_data(group_id)

    if text.startswith('+') or text.startswith('-'):
        try:
            amount = float(text)
            data['inr_paid'] += amount
            usdt_to_pay = data['inr_paid'] / data['rate'] if data['rate'] else 0.0
            remaining = usdt_to_pay - data['usdt_sent']
            save_group_data(group_id, data)

            await update.message.reply_text(
                f"INR Paid: {data['inr_paid']:.2f}\n"
                f"Rate: {data['rate']}\n"
                f"USDT To Pay: {usdt_to_pay:.2f}\n"
                f"USDT Sent: {data['usdt_sent']:.2f}\n"
                f"Remaining: {remaining:.2f}"
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid amount format.")

async def add_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    data = get_group_data(group_id)

    try:
        amount = float(context.args[0].replace('u', ''))
        data['usdt_sent'] += amount
        usdt_to_pay = data['inr_paid'] / data['rate'] if data['rate'] else 0.0
        remaining = usdt_to_pay - data['usdt_sent']
        save_group_data(group_id, data)

        await update.message.reply_text(
            f"INR Paid: {data['inr_paid']:.2f}\n"
            f"Rate: {data['rate']}\n"
            f"USDT To Pay: {usdt_to_pay:.2f}\n"
            f"USDT Sent: {data['usdt_sent']:.2f}\n"
            f"Remaining: {remaining:.2f}"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use format: /add 1000 or /add 1000u")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to INR ↔ USDT Exchange Bot! Use /set <rate> to begin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set", set_rate))
    app.add_handler(CommandHandler("add", add_usdt))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_inr))

    print("Bot is running...")
    app.run_polling()
