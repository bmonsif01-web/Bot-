""" Telegram bot (python-telegram-bot) that converts images or text to Amazon affiliate links Requirements:

python-telegram-bot (v20+)

requests


Environment variables used (ONLY these two):

TELEGRAM_TOKEN

GEMINI_API_KEY


Behavior summary:

/start shows language selection (Arabic 🇸🇦 / English 🇺🇸)

language is persisted in a simple SQLite DB (users.db)

when user sends a photo, the bot sends the image to Gemini (gemini-1.5-flash) using the Generative Language REST endpoint and asks: "Identify this product and give me ONLY the short commercial name"

when user sends text, it is directly converted to an Amazon link: https://www.amazon.com/s?k=NAME&tag=chop07c-20

messages use Markdown formatting and the reply contains a button "اشتري الآن 🛒" / "Buy Now 🛒"

robust logging and exception handling included """


import os import logging import sqlite3 import base64 import json import io import urllib.parse from typing import Optional

import requests from telegram import ( Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ) from telegram.constants import ParseMode from telegram.ext import ( ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters, )

--------------------------- Configuration & Logging ---------------------------

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if TELEGRAM_TOKEN is None: raise RuntimeError("TELEGRAM_TOKEN environment variable is required")

Only GEMINI_API_KEY may be empty — we will handle it gracefully at runtime.

logging.basicConfig( format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO, ) logger = logging.getLogger(name)

--------------------------- SQLite (language persistence) ---------------------------

DB_PATH = "users.db"

def init_db(): conn = sqlite3.connect(DB_PATH) cur = conn.cursor() cur.execute( """ CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY, lang TEXT NOT NULL ) """ ) conn.commit() conn.close()

def set_user_lang(user_id: int, lang: str): conn = sqlite3.connect(DB_PATH) cur = conn.cursor() cur.execute("REPLACE INTO users (user_id, lang) VALUES (?, ?)", (user_id, lang)) conn.commit() conn.close()

def get_user_lang(user_id: int) -> str: conn = sqlite3.connect(DB_PATH) cur = conn.cursor() cur.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) row = cur.fetchone() conn.close() return row[0] if row else "en"

--------------------------- Utilities ---------------------------

def escape_markdown_v2(text: str) -> str: """Escape text for Telegram MarkdownV2. We'll use MarkdownV2 so we can safely bold without breaking.""" if not text: return text escape_chars = r"_*~`>#+-=|{}.!" return "".join(("\" + ch) if ch in escape_chars else ch for ch in text)

def make_amazon_link(name: str) -> str: q = urllib.parse.quote_plus(name) return f"https://www.amazon.com/s?k={q}&tag=chop07c-20"

--------------------------- Gemini (REST) ---------------------------

GEMINI_ENDPOINT_TEMPLATE = ( "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent" ) GEMINI_MODEL = "gemini-1.5-flash"  # per requirement; may return 404 on some accounts — handled gracefully

def call_gemini_with_image(image_bytes: bytes, prompt_text: str) -> Optional[str]: """Send image + prompt to Gemini generateContent endpoint. Returns the model text or None on failure.""" if not GEMINI_API_KEY: logger.warning("GEMINI_API_KEY not set; skipping Gemini call") return None

url = GEMINI_ENDPOINT_TEMPLATE.format(model=GEMINI_MODEL)
b64 = base64.b64encode(image_bytes).decode("utf-8")

payload = {
    "contents": [
        {
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": prompt_text},
            ]
        }
    ]
}

headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

try:
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    logger.info("Gemini response status: %s", resp.status_code)
    if resp.status_code != 200:
        logger.error("Gemini API error: %s -- %s", resp.status_code, resp.text)
        return None
    data = resp.json()
    # Robust extraction: try a few common fields seen in Gemini responses
    text = extract_text_from_gemini_response(data)
    return text
except Exception as e:
    logger.exception("Exception while calling Gemini: %s", e)
    return None

def extract_text_from_gemini_response(data: dict) -> Optional[str]: """Try to extract generated text from known response structures.""" # Common patterns: data['candidates'][0]['content'][0]['text'] or data['candidates'][0]['text'] try: if isinstance(data, dict): # Check 'candidates' cands = data.get("candidates") or data.get("outputs") or data.get("outputs_candidates") if cands and isinstance(cands, list) and len(cands) > 0: # try several nesting options first = cands[0] # common: first.get('content') -> list with dicts that have 'text' if isinstance(first, dict): cont = first.get("content") if cont and isinstance(cont, list): # search for a text field for part in cont: if isinstance(part, dict) and "text" in part: return part["text"].strip() if isinstance(part, str): return part.strip() # sometimes candidate has 'text' if "text" in first and isinstance(first["text"], str): return first["text"].strip() # Check 'output' -> 'text' if "output" in data and isinstance(data["output"], dict): out = data["output"] if "text" in out: return out["text"].strip() # Maybe 'response' or 'result' for k in ("response", "result", "text"): if k in data and isinstance(data[k], str): return data[k].strip() # fallback: try to find any string value deeply def find_first_str(obj): if isinstance(obj, str): return obj if isinstance(obj, dict): for v in obj.values(): res = find_first_str(v) if res: return res if isinstance(obj, list): for item in obj: res = find_first_str(item) if res: return res return None found = find_first_str(data) return found.strip() if isinstance(found, str) else None except Exception as e: logger.exception("Error extracting text from Gemini response: %s", e) return None

--------------------------- Telegram Handlers ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user lang = get_user_lang(user.id)

keyboard = [
    [
        InlineKeyboardButton("العربية 🇸🇦", callback_data="lang:ar"),
        InlineKeyboardButton("English 🇺🇸", callback_data="lang:en"),
    ]
]

if lang == "ar":
    text = "مرحباً! أرسل صورة منتج أو اكتب اسمه وسأعيد لك رابط أمازون مع زر "
else:
    text = "Hello! Send a product photo or type a product name and I'll return an Amazon link with a button"

await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() data = query.data or "" user = query.from_user if data.startswith("lang:"): chosen = data.split(":", 1)[1] set_user_lang(user.id, chosen) if chosen == "ar": await query.edit_message_text("تم اختيار العربية 🇸🇦. الآن أرسل صورة أو اسم المنتج.") else: await query.edit_message_text("English 🇺🇸 selected. Now send a product photo or the product name.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user text = (update.message.text or "").strip() if not text: return try: # Use the text directly to build Amazon link link = make_amazon_link(text) lang = get_user_lang(user.id) bold_name = escape_markdown_v2(text) if lang == "ar": caption = f"{bold_name}\nإليك الرابط على أمازون:" button_text = "اشتري الآن 🛒" else: caption = f"{bold_name}\nHere's the Amazon link:" button_text = "Buy Now 🛒"

keyboard = InlineKeyboardMarkup.from_button(InlineKeyboardButton(button_text, url=link))
    await update.message.reply_text(caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
except Exception as e:
    logger.exception("Error in text_handler: %s", e)
    await update.message.reply_text("Sorry, an error occurred. Please try again later.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user photos = update.message.photo if not photos: await update.message.reply_text("No photo found in the message.") return

# take the highest resolution
photo = photos[-1]
try:
    file = await context.bot.get_file(photo.file_id)
    # download to memory
    image_bytes = await file.download_as_bytearray()
    # call Gemini
    prompt = "Identify this product and give me ONLY the short commercial name"
    product_name = call_gemini_with_image(bytes(image_bytes), prompt)

    lang = get_user_lang(user.id)

    if product_name:
        product_name = product_name.strip().splitlines()[0]  # only first line
        link = make_amazon_link(product_name)
        bold_name = escape_markdown_v2(product_name)

        if lang == "ar":
            caption = f"*{bold_name}*\nإليك الرابط على أمازون:"
            button_text = "اشتري الآن 🛒"
        else:
            caption = f"*{bold_name}*\nHere's the Amazon link:"
            button_text = "Buy Now 🛒"

        keyboard = InlineKeyboardMarkup.from_button(InlineKeyboardButton(button_text, url=link))
        await update.message.reply_text(caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Fallback: ask user to type name or use "unknown"
        if lang == "ar":
            await update.message.reply_text("عذراً لم أستطع التعرف على المنتج. أرسل اسم المنتج نصياً لأقوم بإنشاء الرابط.")
        else:
            await update.message.reply_text("Sorry, I couldn't identify the product. Send the product name as text and I'll create the link.")
except Exception as e:
    logger.exception("Error in photo_handler: %s", e)
    if lang := get_user_lang(user.id):
        if lang == "ar":
            await update.message.reply_text("حدث خطأ أثناء معالجة الصورة. تأكد من وضوح الصورة أو توافر مفتاح Gemini.")
        else:
            await update.message.reply_text("An error occurred while processing the image. Make sure the image is clear or check your Gemini API key.")

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): lang = get_user_lang(update.effective_user.id) if lang == "ar": await update.message.reply_text("أرسل صورة أو اكتب اسم المنتج وسيتم إنشاء رابط أمازون تلقائياً.") else: await update.message.reply_text("Send a photo or type a product name and I'll return an Amazon search link.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None: logger.exception("Unhandled exception: %s", context.error)

--------------------------- App Start ---------------------------

def main(): init_db()

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_handler))
app.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang:"))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

app.add_error_handler(error_handler)

logger.info("Starting bot with drop_pending_updates=True")
# drop_pending_updates prevents processing old queued messages after a restart (Railway friendliness)
app.run_polling(drop_pending_updates=True)

if name == "main": main()
