"""
Jihozlar katalogi - Telegram bot
=================================
Admin bir nechta rasm, tsex, uchastka, jihoz nomi va zakaz linki bilan
jihoz qo'shadi. Boshqalar qidiradi, ro'yxat va hisobotlarni ko'radi.

Admin uchun qo'shish jarayoni:
1. Rasm(lar) yuboring (bir nechtasini ketma-ket yuborishingiz mumkin)
2. "Tayyor" deb yozing
3. Bot tsex, uchastka, jihoz nomi va linkni birma-bir so'raydi

Buyruqlar:
- /start            -> tugmali menyu
- /qidir <so'z>      -> tavsif/tsex/uchastka bo'yicha qidirish
- /royxat            -> oxirgi 10 ta yozuv
- /export            -> Excel fayl
- /pdf               -> PDF hisobot
- /statistika        -> uchastkalar/tsexlar bo'yicha son
- /tahrir <id>       -> (admin) yozuvni tahrirlash
- /rasm_qosh <id>    -> (admin) mavjud yozuvga qo'shimcha rasm qo'shish
- /ochir <id>        -> (admin) yozuvni o'chirish
"""

import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, InputMediaPhoto
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

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
except ImportError:
    SimpleDocTemplate = None

# ============ SOZLAMALAR ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "BU_YERGA_TOKENINGIZNI_YOZING")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jihozlar.db")

ADMIN_IDS = [7726996138]

BTN_QIDIR = "🔍 Qidirish"
BTN_ROYXAT = "📋 Ro'yxat"
BTN_EXCEL = "📊 Excel"
BTN_PDF = "📄 PDF hisobot"
BTN_STAT = "📈 Statistika"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_QIDIR, BTN_ROYXAT], [BTN_EXCEL, BTN_PDF], [BTN_STAT]],
    resize_keyboard=True,
)

DONE_WORDS = {"tayyor", "tugadi", "done", "tayyor."}
SKIP_WORDS = {"yoq", "yo'q", "yoq.", "yo'q.", "-"}

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
            caption TEXT,
            location TEXT,
            user_id INTEGER,
            created_at TEXT
        )
        """
    )
    for col in ("tsexi TEXT", "link TEXT", "file_id TEXT"):
        try:
            cur.execute(f"ALTER TABLE jihozlar ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            file_id TEXT NOT NULL
        )
        """
    )
    conn.commit()

    cur.execute(
        "SELECT id, file_id FROM jihozlar WHERE file_id IS NOT NULL AND file_id != ''"
    )
    old_rows = cur.fetchall()
    for item_id, file_id in old_rows:
        cur.execute("SELECT COUNT(*) FROM photos WHERE item_id = ?", (item_id,))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO photos (item_id, file_id) VALUES (?, ?)", (item_id, file_id)
            )
    conn.commit()
    conn.close()


def add_item(caption: str, tsexi: str, location: str, link: str, user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO jihozlar (caption, tsexi, location, link, user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (caption or "", tsexi or "", location or "", link or "", user_id,
         datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def add_photo(item_id: int, file_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO photos (item_id, file_id) VALUES (?, ?)", (item_id, file_id))
    conn.commit()
    conn.close()


def get_photos(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id FROM photos WHERE item_id = ? ORDER BY id", (item_id,))
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def search_items(query: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    like = f"%{query}%"
    cur.execute(
        "SELECT id, caption, tsexi, location, link, created_at FROM jihozlar "
        "WHERE caption LIKE ? OR location LIKE ? OR tsexi LIKE ? ORDER BY id DESC",
        (like, like, like),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_items(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption, tsexi, location, created_at FROM jihozlar "
        "ORDER BY id DESC LIMIT ?",
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
        "SELECT id, tsexi, location, caption, link, created_at FROM jihozlar ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_item(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption, tsexi, location, link FROM jihozlar WHERE id = ?", (item_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_item(item_id: int, caption=None, tsexi=None, location=None, link=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if caption is not None:
        cur.execute("UPDATE jihozlar SET caption = ? WHERE id = ?", (caption, item_id))
    if tsexi is not None:
        cur.execute("UPDATE jihozlar SET tsexi = ? WHERE id = ?", (tsexi, item_id))
    if location is not None:
        cur.execute("UPDATE jihozlar SET location = ? WHERE id = ?", (location, item_id))
    if link is not None:
        cur.execute("UPDATE jihozlar SET link = ? WHERE id = ?", (link, item_id))
    conn.commit()
    conn.close()


def delete_item(item_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM jihozlar WHERE id = ?", (item_id,))
    deleted = cur.rowcount > 0
    cur.execute("DELETE FROM photos WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    return deleted


def uchastka_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(NULLIF(location,''),'(belgilanmagan)'), COUNT(*) "
        "FROM jihozlar GROUP BY location ORDER BY COUNT(*) DESC"
    )
    uch = cur.fetchall()
    cur.execute(
        "SELECT COALESCE(NULLIF(tsexi,''),'(belgilanmagan)'), COUNT(*) "
        "FROM jihozlar GROUP BY tsexi ORDER BY COUNT(*) DESC"
    )
    tsex = cur.fetchall()
    conn.close()
    return uch, tsex


# ============ YORDAMCHI ============
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def reset_add_flow(user_data: dict):
    for key in ("step", "photos", "tsexi", "uchastka", "name", "target_id"):
        user_data.pop(key, None)


def format_result_text(item_id, caption, tsexi, location, link, created_at) -> str:
    parts = [f"ID: {item_id} | {created_at}"]
    if tsexi:
        parts.append(f"🏭 Tsex: {tsexi}")
    if location:
        parts.append(f"📍 Uchastka: {location}")
    parts.append(f"🔧 {caption}")
    if link:
        parts.append(f"🔗 Zakaz: {link}")
    return "\n".join(parts)


async def send_item_photos(update: Update, item_id, caption, tsexi, location, link, created_at):
    photos = get_photos(item_id)
    text = format_result_text(item_id, caption, tsexi, location, link, created_at)
    if not photos:
        await update.message.reply_text(text)
        return
    if len(photos) == 1:
        await update.message.reply_photo(photo=photos[0], caption=text)
        return
    media = [InputMediaPhoto(photos[0], caption=text)]
    for p in photos[1:]:
        media.append(InputMediaPhoto(p))
    await update.message.reply_media_group(media=media)


# ============ BUYRUQLAR ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_add_flow(context.user_data)
    await update.message.reply_text(
        "Salom! Admin rasm(lar) yuborib jihoz qo'shadi.\n\n"
        "Pastdagi tugmalar orqali qidirishingiz, ro'yxat, statistika yoki "
        "hisobot faylini olishingiz mumkin.",
        reply_markup=MAIN_KEYBOARD,
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Kechirasiz, faqat admin yangi jihoz qo'sha oladi. Siz qidirishingiz mumkin.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    photo = update.message.photo[-1]
    step = context.user_data.get("step")

    if step == "adding_photos_existing":
        target_id = context.user_data.get("target_id")
        add_photo(target_id, photo.file_id)
        await update.message.reply_text(
            "📸 Rasm qo'shildi. Yana yuborishingiz mumkin, tugagach 'Tayyor' deb yozing."
        )
        return

    if step == "collecting_photos":
        context.user_data["photos"].append(photo.file_id)
    else:
        reset_add_flow(context.user_data)
        context.user_data["step"] = "collecting_photos"
        context.user_data["photos"] = [photo.file_id]

    count = len(context.user_data["photos"])
    await update.message.reply_text(
        f"📸 Rasm qo'shildi ({count} ta). Yana rasm yuborishingiz mumkin.\n"
        f"Tugagan bo'lsa 'Tayyor' deb yozing."
    )


async def qidir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        context.user_data["step"] = "search"
        await update.message.reply_text("Qidiruv so'zini yozing:")
        return
    await do_search(update, " ".join(context.args))


async def do_search(update: Update, query: str):
    rows = search_items(query)
    if not rows:
        await update.message.reply_text(
            f"'{query}' bo'yicha hech narsa topilmadi.", reply_markup=MAIN_KEYBOARD
        )
        return
    await update.message.reply_text(f"Topildi: {len(rows)} ta natija")
    for item_id, caption, tsexi, location, link, created_at in rows[:15]:
        await send_item_photos(update, item_id, caption, tsexi, location, link, created_at)


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
    for item_id, caption, tsexi, location, created_at in rows:
        short_caption = (caption[:40] + "...") if len(caption) > 40 else caption
        loc_parts = []
        if tsexi:
            loc_parts.append(tsexi)
        if location:
            loc_parts.append(location)
        loc = f" [{' / '.join(loc_parts)}]" if loc_parts else ""
        lines.append(f"#{item_id}{loc} [{created_at}] {short_caption}")
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_export(update)


async def send_export(update: Update):
    if Workbook is None:
        await update.message.reply_text("Excel eksport uchun 'openpyxl' kutubxonasi kerak.")
        return
    rows = all_items()
    if not rows:
        await update.message.reply_text("Hali hech qanday jihoz saqlanmagan.")
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Jihozlar"
    ws.append(["ID", "Tsex", "Uchastka", "Jihoz nomi", "Link", "Sana"])
    for item_id, tsexi, location, caption, link, created_at in rows:
        ws.append([item_id, tsexi, location, caption, link, created_at])
    file_path = "/tmp/jihozlar_royxati.xlsx"
    wb.save(file_path)
    with open(file_path, "rb") as f:
        await update.message.reply_document(
            document=f, filename="jihozlar_royxati.xlsx",
            caption=f"Jami {len(rows)} ta jihoz.",
        )


async def pdf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_pdf(update)


async def send_pdf(update: Update):
    if SimpleDocTemplate is None:
        await update.message.reply_text("PDF eksport uchun 'reportlab' kutubxonasi kerak.")
        return
    rows = all_items()
    if not rows:
        await update.message.reply_text("Hali hech qanday jihoz saqlanmagan.")
        return

    file_path = "/tmp/jihozlar_hisobot.pdf"
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"]
    cell_style.fontSize = 8
    cell_style.leading = 10

    data = [["ID", "Tsex", "Uchastka", "Jihoz nomi", "Link"]]
    for item_id, tsexi, location, caption, link, created_at in rows:
        data.append([
            Paragraph(str(item_id), cell_style),
            Paragraph(tsexi or "-", cell_style),
            Paragraph(location or "-", cell_style),
            Paragraph(caption or "-", cell_style),
            Paragraph(link or "-", cell_style),
        ])

    doc = SimpleDocTemplate(
        file_path, pagesize=landscape(A4),
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm, bottomMargin=1 * cm,
    )
    col_widths = [1.5 * cm, 4 * cm, 4 * cm, 9 * cm, 8 * cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    doc.build([table])

    with open(file_path, "rb") as f:
        await update.message.reply_document(
            document=f, filename="jihozlar_hisobot.pdf",
            caption=f"Jami {len(rows)} ta jihoz.",
        )


async def statistika_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_statistika(update)


async def send_statistika(update: Update):
    uch, tsex = uchastka_stats()
    if not uch:
        await update.message.reply_text("Hali hech qanday jihoz saqlanmagan.")
        return

    lines = ["📈 Uchastkalar bo'yicha:"]
    for location, count in uch:
        lines.append(f"  • {location}: {count} ta")

    lines.append("\n🏭 Tsexlar bo'yicha:")
    for tsexi, count in tsex:
        lines.append(f"  • {tsexi}: {count} ta")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)


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

    context.user_data["step"] = "edit"
    context.user_data["target_id"] = item_id
    await update.message.reply_text(
        "O'zgartirmoqchi bo'lgan qatorlarni yuboring (kerakli qatorlarni yozing, "
        "qolganini o'zgarishsiz qoldirish uchun yozmang):\n\n"
        "Tavsif: yangi jihoz nomi\n"
        "Tsex: yangi tsex nomi\n"
        "Uchastka: yangi uchastka nomi\n"
        "Link: yangi zakaz linki"
    )


async def rasm_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Kechirasiz, faqat admin rasm qo'sha oladi.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("ID raqamini yozing. Masalan: /rasm_qosh 5")
        return
    item_id = int(context.args[0])
    item = get_item(item_id)
    if not item:
        await update.message.reply_text(f"ID {item_id} topilmadi.")
        return

    reset_add_flow(context.user_data)
    context.user_data["step"] = "adding_photos_existing"
    context.user_data["target_id"] = item_id
    await update.message.reply_text(
        f"ID {item_id} uchun yangi rasm(lar)ni yuboring. Tugagach 'Tayyor' deb yozing."
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
    low = text.lower()
    step = context.user_data.get("step")

    if step == "collecting_photos":
        if low in DONE_WORDS:
            if not context.user_data.get("photos"):
                await update.message.reply_text("Hali birorta rasm yubormadingiz.")
                return
            context.user_data["step"] = "ask_tsexi"
            await update.message.reply_text("🏭 Qaysi tsexda joylashgan?")
        else:
            await update.message.reply_text(
                "Rasm yuboring yoki tugagan bo'lsa 'Tayyor' deb yozing."
            )
        return

    if step == "ask_tsexi":
        context.user_data["tsexi"] = text
        context.user_data["step"] = "ask_uchastka"
        await update.message.reply_text("📍 Qaysi uchastkada joylashgan?")
        return

    if step == "ask_uchastka":
        context.user_data["uchastka"] = text
        context.user_data["step"] = "ask_name"
        await update.message.reply_text("🔧 Jihoz nomini/tavsifini yozing:")
        return

    if step == "ask_name":
        context.user_data["name"] = text
        context.user_data["step"] = "ask_link"
        await update.message.reply_text(
            "🔗 Zakaz qilish uchun sayt linkini yuboring (bo'lmasa '-' deb yozing):"
        )
        return

    if step == "ask_link":
        link = "" if low in SKIP_WORDS else text
        photos = context.user_data.get("photos", [])
        tsexi = context.user_data.get("tsexi", "")
        uchastka = context.user_data.get("uchastka", "")
        name = context.user_data.get("name", "")

        item_id = add_item(name, tsexi, uchastka, link, update.effective_user.id)
        for file_id in photos:
            add_photo(item_id, file_id)

        reset_add_flow(context.user_data)
        summary = format_result_text(
            item_id, name, tsexi, uchastka, link, datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        await update.message.reply_text(
            f"✅ Saqlandi!\n\n{summary}\n\n📸 Rasmlar soni: {len(photos)}",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    if step == "adding_photos_existing":
        if
