"""
Jihozlar katalogi - Telegram bot
=================================
Rasm (foto) yuborsangiz, bot tavsif va uchastkani so'raydi, keyin saqlaydi.
Faqat admin yangi jihoz qo'sha oladi va tahrirlay oladi, boshqalar qidiradi.

Buyruqlar:
- /start        -> tugmali menyu bilan xush kelibsiz xabari
- /qidir <so'z> -> tavsif yoki uchastka bo'yicha qidirish
- /royxat       -> barcha saqlangan jihozlar (oxirgi 10 tasi)
- /export       -> barcha jihozlar ro'yxatini Excel faylga tushirib beradi
- /tahrir <id>  -> (faqat admin) berilgan ID'dagi yozuvni tahrirlash
- /ochir <id>   -> (faqat admin) berilgan ID'dagi yozuvni o'chirish
"""

import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

# ============ SOZLAMALAR ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "BU_YERGA_TOKENINGIZNI_YOZING")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jihozlar.db")

# Faqat shu ID'dagi foydalanuvchi(lar) jihoz qo'sha oladi/tahrirlaydi/o'chiradi
ADMIN_IDS = [7726996138]

BTN_QIDIR = "🔍 Qidirish"
BTN_ROYXAT = "📋 Ro'yxat"
BTN_EXPORT = "📊 Excel'ga yuklash"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_QIDIR, BTN_ROYXAT], [BTN_EXPORT]],
    resize_keyboard=True,
)

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
            location TEXT,
            user_id INTEGER,
            created_at TEXT
        )
        """
    )
    # Eski bazalarda "location" ustuni bo'lmasligi mumkin - qo'shib qo'yamiz
    try:
        cur.execute("ALTER TABLE jihozlar ADD COLUMN location TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def add_item(file_id: str, caption: str, location: str, user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO jihozlar (file_id, caption, location, user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (file_id, caption or "", location or "", user_id,
         datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def search_items(query: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_id, caption, location, created_at FROM jihozlar "
        "WHERE caption LIKE ? OR location LIKE ? ORDER BY id DESC",
        (f"%{query}%", f"%{query}%"),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_items(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption, location, created_at FROM jihozlar ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM jihozlar")
    total = cur.fetchone()[0]
    conn.close()
    return rows, total


def all_items():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption, location, created_at FROM jihozlar ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_item(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_id, caption, location FROM jihozlar WHERE id = ?", (item_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_item(item_id: int, caption: str = None, location: str = None) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if caption is not None:
        cur.execute("UPDATE jihozlar SET caption = ? WHERE id = ?", (caption, item_id))
    if location is not None:
        cur.execute("UPDATE jihozlar SET location = ? WHERE id = ?", (location, item_id))
    conn.commit()
    updated = cur.rowcount > 0 or caption is not None or location is not None
    conn.close()
    return updated


def delete_item(item_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM jihozlar WHERE id = ?", (item_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ============ YORDAMCHI ============
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def format_result_text(item_id, caption, location, created_at) -> str:
    loc_line = f"\n📍 Uchastka: {location}" if location else ""
    return f"ID: {item_id} | {created_at}{loc_line}\n{caption}"


# ============ BUYRUQLAR ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Salom! Menga jihoz rasmini yuboring, men tavsif va uchastkani so'rayman.\n\n"
        "Pastdagi tugmalar orqali qidirishingiz yoki ro'yxatni ko'rishingiz mumkin.",
        reply_markup=MAIN_KEYBOARD,
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Kechirasiz, faqat admin yangi jihoz qo'sha oladi. "
            "Siz qidirishingiz mumkin.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    context.user_data["pending_photo"] = {"file_id": photo.file_id, "caption": caption}
    context.user_data["awaiting"] = "location"

    await update.message.reply_text(
        "📍 Bu jihoz qaysi uchastkada joylashgan? (masalan: Unloading, Ombor-2, Sex-1)"
    )


async def qidir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        context.user_data["awaiting"] = "search"
        await update.message.reply_text("Qidiruv so'zini yozing:")
        return
    query = " ".join(context.args)
    await do_search(update, query)


async def do_search(update: Update, query: str):
    rows = search_items(query)
    if not rows:
        await update.message.reply_text(
            f"'{query}' bo'yicha hech narsa topilmadi.", reply_markup=MAIN_KEYBOARD
        )
        return

    await update.message.reply_text(f"Topildi: {len(rows)} ta natija")
    for item_id, file_id, caption, location, created_at in rows[:15]:
        text = format_result_text(item_id, caption, location, created_at)
        await update.message.reply_photo(photo=file_id, caption=text)


async def royxat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_royxat(update)


async def send_royxat(update: Update):
    rows, total = list_items()
    if total == 0:
        await update.message.reply_text(
            "Hali hech qanday jihoz saqlanmagan.", reply_markup=MAIN_KEYBOARD
        )
        return

    lines = [f"Jami: {total} ta jihoz. Oxirgi {len(rows)} tasi:\n"]
    for item_id, caption, location, created_at in rows:
        short_caption = (caption[:40] + "...") if len(caption) > 40 else caption
        loc = f" [{location}]" if location else ""
        lines.append(f"#{item_id}{loc} [{created_at}] {short_caption}")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_export(update)


async def send_export(update: Update):
    if Workbook is None:
        await update.message.reply_text(
            "Excel eksport funksiyasi ishlashi uchun 'openpyxl' kutubxonasi kerak."
        )
        return

    rows = all_items()
    if not rows:
        await update.message.reply_text("Hali hech qanday jihoz saqlanmagan.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Jihozlar"
    ws.append(["ID", "Tavsif", "Uchastka", "Sana"])
    for item_id, caption, location, created_at in rows:
        ws.append([item_id, caption, location, created_at])

    file_path = "/tmp/jihozlar_royxati.xlsx"
    wb.save(file_path)

    with open(file_path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="jihozlar_royxati.xlsx",
            caption=f"Jami {len(rows)} ta jihoz.",
        )


async def tahrir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Kechirasiz, faqat admin tahrirlay oladi.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("ID raqamini yozing. Masalan: /tahrir 5")
        return

    item_id = int(context.args[0])
    item = get_item(item_id)
    if not item:
        await update.message.reply_text(f"ID {item_id} topilmadi.")
        return

    context.user_data["awaiting"] = "edit"
    context.user_data["edit_id"] = item_id

    await update.message.reply_text(
        "Yangi ma'lumotni shu ko'rinishda yuboring (ikkala qatorni ham yozing):\n\n"
        "Tavsif: yangi tavsif matni\n"
        "Uchastka: yangi uchastka nomi"
    )


async def ochir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Kechirasiz, faqat admin yozuvlarni o'chira oladi.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("ID raqamini yozing. Masalan: /ochir 5")
        return

    item_id = int(context.args[0])
    if delete_item(item_id):
        await update.message.reply_text(f"ID {item_id} o'chirildi.")
    else:
        await update.message.reply_text(f"ID {item_id} topilmadi.")


# ============ MATNLI XABARLARNI QAYTA ISHLASH ============
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    awaiting = context.user_data.get("awaiting")

    # 1) Yangi rasm uchun uchastka kutilmoqda
    if awaiting == "location":
        pending = context.user_data.pop("pending_photo", None)
        context.user_data.pop("awaiting", None)
        if not pending:
            await update.message.reply_text("Xatolik yuz berdi, rasmni qayta yuboring.")
            return
        item_id = add_item(pending["file_id"], pending["caption"], text, update.effective_user.id)
        await update.message.reply_text(
            f"✅ Saqlandi (ID: {item_id})\n"
            f"Tavsif: {pending['caption'] if pending['caption'] else '(kiritilmagan)'}\n"
            f"Uchastka: {text}",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # 2) Qidiruv so'zi kutilmoqda (tugma orqali)
    if awaiting == "search":
        context.user_data.pop("awaiting", None)
        await do_search(update, text)
        return

    # 3) Tahrirlash uchun yangi ma'lumot kutilmoqda
    if awaiting == "edit":
        item_id = context.user_data.pop("edit_id", None)
        context.user_data.pop("awaiting", None)
        new_caption = None
        new_location = None
        for line in text.split("\n"):
            low = line.strip().lower()
            if low.startswith("tavsif:"):
                new_caption = line.split(":", 1)[1].strip()
            elif low.startswith("uchastka:"):
                new_location = line.split(":", 1)[1].strip()

        if new_caption is None and new_location is None:
            await update.message.reply_text(
                "Format noto'g'ri. 'Tavsif:' va/yoki 'Uchastka:' bilan boshlang."
            )
            return

        update_item(item_id, caption=new_caption, location=new_location)
        await update.message.reply_text(f"✅ ID {item_id} yangilandi.", reply_markup=MAIN_KEYBOARD)
        return

    # 4) Tugmalar bosilganda
    if text == BTN_QIDIR:
        context.user_data["awaiting"] = "search"
        await update.message.reply_text("Qidiruv so'zini yozing:")
        return

    if text == BTN_ROYXAT:
        await send_royxat(update)
        return

    if text == BTN_EXPORT:
        await send_export(update)
        return

    # Boshqa har qanday matn
    await update.message.reply_text(
        "Buyruqni tanlang yoki tugmalardan foydalaning.", reply_markup=MAIN_KEYBOARD
    )


# ============ ISHGA TUSHIRISH ============
def main():
    if BOT_TOKEN == "BU_YERGA_TOKENINGIZNI_YOZING":
        print("XATOLIK: BOT_TOKEN kiritilmagan.")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qidir", qidir))
    app.add_handler(CommandHandler("royxat", royxat_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("tahrir", tahrir))
    app.add_handler(CommandHandler("ochir", ochir))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
