import logging
from telegram import Update, ChatMember, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz
import csv
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Group-wise data store
group_data = {}
transaction_ids = {}

# Timezone for IST
IST = pytz.timezone('Asia/Kolkata')

def get_time():
    return datetime.now(IST).strftime("%H:%M")

def get_date():
    return datetime.now(IST).strftime("%Y-%m-%d")

def is_admin(member: ChatMember):
    return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]

async def check_admin(update: Update, context: CallbackContext) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return is_admin(member)

def init_group_data(chat_id):
    if chat_id not in group_data:
        group_data[chat_id] = {
            'rate': None,
            'total_inr': 0,
            'used_inr': 0,
            'total_usdt': 0,
            'sent_usdt': 0,
            'transactions': []
        }
        transaction_ids[chat_id] = 1

async def set_rate(update: Update, context: CallbackContext):
    if not await check_admin(update, context):
        return

    try:
        rate = float(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /set <rate>")
        return

    chat_id = update.effective_chat.id
    init_group_data(chat_id)
    group_data[chat_id]['rate'] = rate

    await update.message.reply_text(f"✅ Exchange rate set to {rate} INR per USDT.")

async def add_inr(update: Update, context: CallbackContext):
    if not await check_admin(update, context):
        return

    text = update.message.text.strip()
    if not text.startswith("+") and not text.startswith("-"):
        return

    try:
        amount = float(text[1:])
        if text.startswith("-"):
            amount *= -1
    except ValueError:
        return

    chat_id = update.effective_chat.id
    init_group_data(chat_id)
    data = group_data[chat_id]
    data['total_inr'] += amount
    if amount > 0:
        data['used_inr'] += amount

    record_transaction(chat_id, amount, update.message.date)
    await send_summary(update, context)

async def add_usdt(update: Update, context: CallbackContext):
    if not await check_admin(update, context):
        return

    try:
        usdt = float(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <usdt>")
        return

    chat_id = update.effective_chat.id
    init_group_data(chat_id)
    group_data[chat_id]['sent_usdt'] += usdt

    record_transaction(chat_id, 0, update.message.date, usdt=usdt)
    await send_summary(update, context)

async def reset_data(update: Update, context: CallbackContext):
    if not await check_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if chat_id in group_data:
        rate = group_data[chat_id]['rate']
        group_data[chat_id] = {
            'rate': rate,
            'total_inr': 0,
            'used_inr': 0,
            'total_usdt': 0,
            'sent_usdt': 0,
            'transactions': []
        }
        transaction_ids[chat_id] = 1

    await update.message.reply_text("✅ All data except exchange rate has been reset.")

async def download_csv(update: Update, context: CallbackContext):
    if not await check_admin(update, context):
        return

    chat_id = update.effective_chat.id
    date_str = get_date()
    file_path = f"data/{chat_id}_{date_str}.csv"

    if not os.path.exists(file_path):
        await update.message.reply_text("⚠️ No transactions to download today.")
        return

    await update.message.reply_document(document=open(file_path, "rb"))

def record_transaction(chat_id, inr=0, time=None, usdt=0):
    init_group_data(chat_id)
    data = group_data[chat_id]
    rate = data['rate'] or 1
    now = datetime.now(IST)
    time_str = now.strftime("%H:%M")
    tid = f"WX{datetime.now(IST).strftime('%Y%m%d%H%M%S')}"
    transaction_ids[chat_id] += 1

    usdt_calc = inr / rate if inr else usdt
    record = {
        'id': tid,
        'time': time_str,
        'inr': inr,
        'rate': rate,
        'usdt': usdt_calc if inr else usdt
    }
    data['transactions'].append(record)

    # Write to CSV
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{chat_id}_{get_date()}.csv"
    write_header = not os.path.exists(file_path)
    with open(file_path, "a", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'time', 'inr', 'rate', 'usdt'])
        if write_header:
            writer.writeheader()
        writer.writerow(record)

async def send_summary(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    data = group_data[chat_id]
    rate = data['rate'] or 1
    total_usdt = data['total_inr'] / rate
    remaining = total_usdt - data['sent_usdt']
    time_now = get_time()
    count = len(data['transactions'])

    last = data['transactions'][-1]
    summary = (
        f"ID: {last['id']}\n"
        f"Today Received ({count}):\n"
        f"{last['time']} ₹{int(last['inr'])} / {int(rate)} * (1) = {last['usdt']:.2f} USDT\n"
        f"Current Rate: {int(rate)}\n"
        f"Total INR Today: ₹{int(data['total_inr'])}\n"
        f"Total INR Used: ₹{int(data['used_inr'])}\n"
        f"Total USDT Required: {total_usdt:.2f}U\n"
        f"Total USDT Sent: {data['sent_usdt']:.2f}U\n"
        f"Remaining USDT: {remaining:.2f}U"
    )
    await update.message.reply_text(summary)

def daily_reset():
    for chat_id in group_data:
        rate = group_data[chat_id]['rate']
        group_data[chat_id] = {
            'rate': rate,
            'total_inr': 0,
            'used_inr': 0,
            'total_usdt': 0,
            'sent_usdt': 0,
            'transactions': []
        }
        transaction_ids[chat_id] = 1
    logger.info("Daily reset completed.")

def main():
    from config import BOT_TOKEN

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("set", set_rate))
    app.add_handler(CommandHandler("add", add_usdt))
    app.add_handler(CommandHandler("reset", reset_data))
    app.add_handler(CommandHandler("download", download_csv))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[+-][0-9]+"), add_inr))

    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(daily_reset, 'cron', hour=0, minute=0)
    scheduler.start()

    app.run_polling()

if __name__ == '__main__':
    main()
