import logging
import secrets
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Logging
logging.basicConfig(level=logging.INFO)

# Config
BOT_TOKEN = "8893475094:AAEXkB_ucaVBFngeTjxhSQbkefVQLrdRbow"
TOTAL_SLOTS = 18
ENTRY_FEE = 18
WINNER_PERCENTAGE = 0.70

# Database Initialization
def init_db():
    conn = sqlite3.connect("contest.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            round_id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'ACTIVE',
            winner_user_id INTEGER,
            winner_name TEXT,
            winner_upi TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER,
            user_id INTEGER,
            username TEXT,
            upi_id TEXT,
            paid BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_current_round():
    conn = sqlite3.connect("contest.db")
    cursor = conn.cursor()
    cursor.execute("SELECT round_id FROM rounds WHERE status = 'ACTIVE' ORDER BY round_id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO rounds (status) VALUES ('ACTIVE')")
        conn.commit()
        round_id = cursor.lastrowid
    else:
        round_id = row[0]
    conn.close()
    return round_id

def get_slot_count(round_id):
    conn = sqlite3.connect("contest.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants WHERE round_id = ? AND paid = 1", (round_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def generate_progress_bar(filled, total=18):
    filled_blocks = int((filled / total) * 10)
    empty_blocks = 10 - filled_blocks
    bar = "🟩" * filled_blocks + "⬜" * empty_blocks
    return f"{bar} ({filled}/{total})"

# /start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    round_id = get_current_round()
    filled = get_slot_count(round_id)
    progress_bar = generate_progress_bar(filled, TOTAL_SLOTS)
    prize_amount = round(TOTAL_SLOTS * ENTRY_FEE * WINNER_PERCENTAGE, 2)

    text = (
        f"🎯 *Lucky Draw Contest - Round #{round_id}*\n\n"
        f"💰 *Entry Fee:* ₹{ENTRY_FEE}\n"
        f"👥 *Total Slots:* {TOTAL_SLOTS}\n"
        f"🏆 *Winner Prize:* ₹{prize_amount} (70% Direct UPI Payout)\n\n"
        f"📊 *Live Slot Progress:*\n{progress_bar}\n"
        f"Slots Left: *{TOTAL_SLOTS - filled}*"
    )
    keyboard = [
        [InlineKeyboardButton("🎟️ Join Contest (₹18)", callback_data="join_contest")],
        [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# Button Click Handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "refresh_status":
        await start(update, context)
    elif query.data == "join_contest":
        round_id = get_current_round()
        filled = get_slot_count(round_id)

        if filled >= TOTAL_SLOTS:
            await query.edit_message_text("⚠️ Ye round full ho chuka hai! Winner calculate ho raha hai...")
            return

        instruction_text = (
            "💳 *Enter Your Payout UPI ID*\n\n"
            "⚠️ *Dhyan dein:* Yahan wahi UPI ID enter karein jisme aap winning amount lena chahte hain. "
            "Agar aap winner bante hain, to direct *₹226.80* isi UPI ID par credit honge.\n\n"
            "✍️ *Apni UPI ID bhejiye niche diye format me:*\n"
            "`/pay aapki_upi_id`\n\n"
            "*Example:* `/pay 9876543210@paytm` ya `/pay name@oksbi`"
        )
        await query.message.reply_text(instruction_text, parse_mode="Markdown")

# /pay Command (Slot Booking & Winner Trigger)
async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Kripya UPI ID format me bhejein:\n`/pay username@upi`",
            parse_mode="Markdown"
        )
        return

    upi_id = context.args[0]
    user = update.effective_user
    round_id = get_current_round()

    conn = sqlite3.connect("contest.db")
    cursor = conn.cursor()

    # Add participant (Auto marked as paid for testing)
    cursor.execute("""
        INSERT INTO participants (round_id, user_id, username, upi_id, paid)
        VALUES (?, ?, ?, ?, 1)
    """, (round_id, user.id, user.first_name, upi_id))
    conn.commit()

    # Count updated slots
    cursor.execute("SELECT user_id, username, upi_id FROM participants WHERE round_id = ? AND paid = 1", (round_id,))
    participants = cursor.fetchall()
    filled_count = len(participants)

    if filled_count < TOTAL_SLOTS:
        conn.close()
        progress_bar = generate_progress_bar(filled_count, TOTAL_SLOTS)
        await update.message.reply_text(
            f"✅ *Slot Booked Successfully!*\n\n"
            f"👤 Name: *{user.first_name}*\n"
            f"🏦 Registered UPI: `{upi_id}`\n"
            f"📊 Progress: {progress_bar}\n"
            f"Round #{round_id} me *{TOTAL_SLOTS - filled_count}* slots baki hain.",
            parse_mode="Markdown"
        )
    else:
        # 18 Slots Complete -> Select Winner
        winner = secrets.choice(participants)
        winner_id, winner_name, winner_upi = winner
        prize = round(TOTAL_SLOTS * ENTRY_FEE * WINNER_PERCENTAGE, 2)

        # Complete current round
        cursor.execute(
            "UPDATE rounds SET status = 'COMPLETED', winner_user_id = ?, winner_name = ?, winner_upi = ? WHERE round_id = ?",
            (winner_id, winner_name, winner_upi, round_id)
        )
        
        # Create Next Round
        cursor.execute("INSERT INTO rounds (status) VALUES ('ACTIVE')")
        conn.commit()
        next_round_id = cursor.lastrowid
        conn.close()

        # Announcement Message
        winner_msg = (
            f"🎉🎉 *CONTEST COMPLETED (Round #{round_id})* 🎉🎉\n\n"
            f"👑 *LUCKY WINNER:* [{winner_name}](tg://user?id={winner_id})\n"
            f"💰 *Prize Won:* ₹{prize}\n"
            f"🏦 *Payout UPI ID:* `{winner_upi}`\n\n"
            f"------------------------------------\n"
            f"🚀 *New Round #{next_round_id} has started!*\n"
            f"Type /start to join the new round."
        )
        await update.message.reply_text(winner_msg, parse_mode="Markdown")

# /rules Command
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 *Contest Rules:*\n\n"
        "1. Ek round me total 18 slots hote hain.\n"
        "2. Har participant ki entry fee ₹18 hai.\n"
        "3. Jaise hi 18th slot fill hota hai, system automatic 1 random winner chunta hai.\n"
        "4. Total collection ka 70% (₹226.80) winner ke UPI par direct credit hota hai.\n"
        "5. Round complete hote hi turant naya round start ho jata hai."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pay", handle_pay))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
