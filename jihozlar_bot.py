"""
Jihozlar katalogi - Telegram bot
=================================
Rasm (foto) + tavsif yuborsangiz, bot saqlab qoladi.
Keyin /qidir buyrug'i bilan nom yoki tavsif bo'yicha qidirishingiz mumkin.
Bu versiyada barcha foydalanuvchilar bitta umumiy ro'yxatni ko'radi va qidiradi.
"""

import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============ SOZLAMALAR ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "BU_YERGA_TOKENINGIZNI_YOZING")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jihozlar.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============ MA'LUMOTLAR BAZASI ============
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jihozlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            caption TEXT,
            user_id INTEGER,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_item(file_id: str, caption: str, user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO jihozlar (file_id, caption, user_id, created_at) VALUES (?, ?, ?, ?)",
        (file_id, caption or "", user_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def search_items(query: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_id, caption, created_at FROM jihozlar "
        "WHERE caption LIKE ? ORDER BY id DESC",
        (f"%{query}%",),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_items(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption, created_at FROM jihozlar ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM jihozlar")
    total = cur.fetchone()[0]
    conn.close()
    return rows, total


def delete_item(item_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM jihozlar WHERE id = ?", (item_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ============ BUYRUQLAR ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Menga jihoz rasmini tavsif bilan yuboring, men saqlab qolaman.\n\n"
        "Keyin /qidir <so'z> orqali qidirishingiz mumkin.\n"
        "Barcha yozuvlarni ko'rish uchun: /royxat"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    caption = update.message.caption or ""
    user_id = update.effective_user.id

    item_id = add_item(photo.file_id, caption, user_id)

    await update.message.reply_text(
        f"✅ Saqlandi (ID: {item_id})\n"
        f"Tavsif: {caption if caption else '(tavsif kiritilmagan)'}"
    )


async def qidir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Qidiruv so'zini yozing. Masalan: /qidir Bosch")
        return

    query = " ".join(context.args)
    rows = search_items(query)

    if not rows:
        await update.message.reply_text(f"'{query}' bo'yicha hech narsa topilmadi.")
        return

    await update.message.reply_text(f"Topildi: {len(rows)} ta natija")
    for item_id, file_id, caption, created_at in rows[:15]:
        text = f"ID: {item_id} | {created_at}\n{caption}"
        await update.message.reply_photo(photo=file_id, caption=text)


async def royxat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows, total = list_items()

    if total == 0:
        await update.message.reply_text("Hali hech qanday jihoz saqlanmagan.")
        return

    lines = [f"Jami: {total} ta jihoz. Oxirgi {len(rows)} tasi:\n"]
    for item_id, caption, created_at in rows:
        short_caption = (caption[:50] + "...") if len(caption) > 50 else caption
        lines.append(f"#{item_id} [{created_at}] {short_caption}")

    await update.message.reply_text("\n".join(lines))


async def ochir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("ID raqamini yozing. Masalan: /ochir 5")
        return

    item_id = int(context.args[0])
    if delete_item(item_id):
        await update.message.reply_text(f"ID {item_id} o'chirildi.")
    else:
        await update.message.reply_text(f"ID {item_id} topilmadi.")


# ============ ISHGA TUSHIRISH ============
def main():
    if BOT_TOKEN == "BU_YERGA_TOKENINGIZNI_YOZING":
        print("XATOLIK: BOT_TOKEN kiritilmagan.")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qidir", qidir))
    app.add_handler(CommandHandler("royxat", royxat))
    app.add_handler(CommandHandler("ochir", ochir))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
