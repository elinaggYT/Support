import os
import sys
import asyncio
import logging
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STAFF_CHAT_ID = os.getenv("STAFF_CHAT_ID")
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN:
    logging.error("BOT_TOKEN environment variable not set. Exiting.")
    sys.exit(1)

try:
    STAFF_CHAT_ID = int(STAFF_CHAT_ID)
except (TypeError, ValueError):
    logging.error("STAFF_CHAT_ID must be a valid integer. Exiting.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Database setup
conn = sqlite3.connect("support_system.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        category TEXT NOT NULL,
        order_id TEXT,
        priority TEXT DEFAULT 'Normal',
        status TEXT DEFAULT 'Open',
        assigned_staff_id INTEGER DEFAULT NULL,
        created_at TEXT NOT NULL
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        sender_role TEXT NOT NULL,
        sender_id INTEGER NOT NULL,
        text TEXT,
        timestamp TEXT NOT NULL
    )
""")
conn.commit()

class TicketCreation(StatesGroup):
    category = State()
    order_id = State()
    description = State()

class StaffReply(StatesGroup):
    ticket_id = State()

def get_customer_main_kb():
    buttons = [
        [InlineKeyboardButton(text="📦 Order Problem", callback_data="cat_Order Problem")],
        [InlineKeyboardButton(text="💳 Payment Problem", callback_data="cat_Payment Problem")],
        [InlineKeyboardButton(text="🛠 Product Support", callback_data="cat_Product Support")],
        [InlineKeyboardButton(text="🔄 Replacement Request", callback_data="cat_Replacement Request")],
        [InlineKeyboardButton(text="❓ General Question", callback_data="cat_General Question")],
        [InlineKeyboardButton(text="👨💻 Talk to Admin", callback_data="cat_Talk to Admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_staff_ticket_kb(ticket_id: int):
    buttons = [
        [
            InlineKeyboardButton(text="💬 Reply", callback_data=f"staff_reply_{ticket_id}"),
            InlineKeyboardButton(text="👤 Claim Ticket", callback_data=f"staff_claim_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="✅ Resolve", callback_data=f"staff_resolve_{ticket_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎧 *KALUZZ SUPPORT CENTER*\n\n"
        "Welcome! How can we assist you today?\n"
        "Select an option below to create a support ticket:",
        parse_mode="Markdown",
        reply_markup=get_customer_main_kb()
    )

@dp.callback_query(F.data.startswith("cat_"))
async def process_category(call: CallbackQuery, state: FSMContext):
    category = call.data.split("cat_")[1]
    await state.update_data(category=category)
    await state.set_state(TicketCreation.order_id)
    await call.message.edit_text(
        f"Selected: *{category}*\n\n"
        "Please enter your *Order ID* (or send 'None' if not applicable):",
        parse_mode="Markdown"
    )

@dp.message(TicketCreation.order_id, F.chat.type == "private")
async def process_order_id(message: Message, state: FSMContext):
    order_id = message.text.strip()
    await state.update_data(order_id=order_id)
    await state.set_state(TicketCreation.description)
    await message.answer("Please describe your problem or inquiry in detail:")

@dp.message(TicketCreation.description, F.chat.type == "private")
async def process_ticket_creation(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("category", "General")
    order_id = data.get("order_id", "None")
    description = message.text.strip()
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO tickets (user_id, username, category, order_id, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (message.from_user.id, message.from_user.username or "Anonymous", category, order_id, now_str))
    conn.commit()

    ticket_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO messages (ticket_id, sender_role, sender_id, text, timestamp)
        VALUES (?, 'customer', ?, ?, ?)
    """, (ticket_id, message.from_user.id, description, now_str))
    conn.commit()

    await state.clear()

    await message.answer(
        f"✅ *Ticket Created Successfully!*\n\n"
        f"🎫 *SUPPORT TICKET #{ticket_id}*\n"
        f"Category: {category}\n"
        f"Order ID: {order_id}\n"
        f"Status: Open\n\n"
        f"Our support team has been notified.",
        parse_mode="Markdown"
    )

    staff_notification = (
        f"🎫 *NEW SUPPORT TICKET #{ticket_id}*\n\n"
        f"Customer: @{message.from_user.username or 'NoUsername'} (`{message.from_user.id}`)\n"
        f"Category: {category}\n"
        f"Order ID: {order_id}\n"
        f"Priority: Normal\n"
        f"Status: Open\n\n"
        f"Initial Message:\n\"{description}\""
    )
    await bot.send_message(
        chat_id=STAFF_CHAT_ID,
        text=staff_notification,
        parse_mode="Markdown",
        reply_markup=get_staff_ticket_kb(ticket_id)
    )

@dp.callback_query(F.data.startswith("staff_claim_"))
async def handle_claim(call: CallbackQuery):
    ticket_id = int(call.data.split("_")[2])
    staff_user = call.from_user

    cursor.execute("SELECT status, assigned_staff_id FROM tickets WHERE ticket_id = ?", (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket:
        await call.answer("Ticket not found.", show_alert=True)
        return

    cursor.execute(
        "UPDATE tickets SET assigned_staff_id = ?, status = 'In Progress' WHERE ticket_id = ?",
        (staff_user.id, ticket_id)
    )
    conn.commit()

    await call.message.edit_text(
        f"{call.message.text}\n\n👤 *Claimed by:* @{staff_user.username or staff_user.first_name}",
        parse_mode="Markdown",
        reply_markup=get_staff_ticket_kb(ticket_id)
    )
    await call.answer("Ticket assigned to you.")

@dp.callback_query(F.data.startswith("staff_reply_"))
async def handle_staff_reply_prompt(call: CallbackQuery, state: FSMContext):
    ticket_id = int(call.data.split("_")[2])
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(StaffReply.ticket_id)
    await call.message.reply(f"Replying to *Ticket #{ticket_id}*. Send your message below:", parse_mode="Markdown")
    await call.answer()

@dp.message(StaffReply.ticket_id)
async def process_staff_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    reply_text = message.text.strip()
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT user_id, status FROM tickets WHERE ticket_id = ?", (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket:
        await message.reply("Ticket not found.")
        await state.clear()
        return

    customer_id = ticket[0]

    cursor.execute("""
        INSERT INTO messages (ticket_id, sender_role, sender_id, text, timestamp)
        VALUES (?, 'staff', ?, ?, ?)
    """, (ticket_id, message.from_user.id, reply_text, now_str))
    conn.commit()

    try:
        await bot.send_message(
            chat_id=customer_id,
            text=f"💬 *Support Update on Ticket #{ticket_id}:*\n\n{reply_text}",
            parse_mode="Markdown"
        )
        await message.reply(f"Delivered to customer for Ticket #{ticket_id}.")
    except Exception as e:
        await message.reply(f"Failed to deliver: {e}")

    await state.clear()

@dp.callback_query(F.data.startswith("staff_resolve_"))
async def handle_resolve(call: CallbackQuery):
    ticket_id = int(call.data.split("_")[2])

    cursor.execute("SELECT user_id FROM tickets WHERE ticket_id = ?", (ticket_id,))
    ticket = cursor.fetchone()

    cursor.execute("UPDATE tickets SET status = 'Resolved' WHERE ticket_id = ?", (ticket_id,))
    conn.commit()

    await call.message.edit_text(
        f"{call.message.text}\n\n✅ *STATUS: RESOLVED*",
        parse_mode="Markdown"
    )
    await call.answer("Marked as resolved.")

    if ticket:
        try:
            await bot.send_message(
                chat_id=ticket[0],
                text=f"✅ *Ticket #{ticket_id} has been marked as Resolved.*\nThank you for choosing Kaluzz Support!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def handle_health_check(request):
    return web.Response(text="Kaluzz Support Bot is running.")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/healthz", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Health server running on port {PORT}")

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
