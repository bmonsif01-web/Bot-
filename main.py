import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import google.generativeai as genai

# --- جلب البيانات من Variables (الأمان أولاً) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_TAG = "chop07c-20"
DEVELOPER_USER = "SAID_BEN_01" 

# إعداد Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("⚠️ Error: GEMINI_API_KEY is missing!")

# --- قاعدة البيانات ---
DB_PATH = '/app/data/bot_users.db' if os.path.exists('/app/data') else 'bot_users.db'

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)''')
    conn.commit()
    conn.close()

def get_user_lang(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT lang FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'ar'

def set_user_lang(user_id, lang):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, lang) VALUES (?, ?)', (user_id, lang))
    conn.commit()
    conn.close()

# --- النصوص ---
STRINGS = {
    'ar': {
        'welcome': "🛍️ **مرحباً بك يا سعيد!** أرسل صورة منتج وسأحولها لرابط عمولة فوراً.",
        'analyzing': "🔍 جاري تحليل الصورة...",
        'searching': "🚀 تم تجهيز الرابط لـ: ",
        'buy_btn': "اشتري الآن من أمازون 🛒",
        'dev_btn': "تواصل مع المطور 👨‍💻",
        'error': "❌ لم أستطع تحديد المنتج، جرب صورة أوضح.",
        'lang_set': "✅ تم اختيار العربية."
    },
    'en': {
        'welcome': "🛍️ **Welcome!** Send a product photo for an affiliate link.",
        'analyzing': "🔍 Analyzing image...",
        'searching': "🚀 Link ready for: ",
        'buy_btn': "Buy on Amazon 🛒",
        'dev_btn': "Contact Developer 👨‍💻",
        'error': "❌ Identification failed.",
        'lang_set': "✅ English selected."
    }
}

# --- الدوال ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='setlang_ar')],
                [InlineKeyboardButton("English 🇺🇸", callback_data='setlang_en')]]
    await update.message.reply_text(STRINGS['ar']['welcome'], parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split('_')[1]
    set_user_lang(query.from_user.id, lang)
    await query.edit_message_text(STRINGS[lang]['lang_set'])

async def process_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    lang = get_user_lang(user_id)
    status_msg = await update.message.reply_text(STRINGS[lang]['analyzing'])

    try:
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            prompt = "Identify this product precisely. Return ONLY the short commercial name."
            contents = [prompt, {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
            response = model.generate_content(contents)
            search_query = response.text.strip()
        else:
            search_query = update.message.text

        # تصحيح الرابط (حل مشكلة التكرار)
        domain = "amazon.com"
        amazon_url = f"https://www.{domain}/s?k={search_query.replace(' ', '+')}&tag={AMAZON_TAG}"

        keyboard = [[InlineKeyboardButton(STRINGS[lang]['buy_btn'], url=amazon_url)],
                    [InlineKeyboardButton(STRINGS[lang]['dev_btn'], url=f"https://t.me/{DEVELOPER_USER}")]]
        
        await update.message.reply_text(f"📦 **{search_query}**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await status_msg.delete()
    except Exception:
        await status_msg.edit_text(STRINGS[lang]['error'])

if __name__ == '__main__':
    setup_db()
    if TELEGRAM_TOKEN:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(language_handler, pattern='^setlang_'))
        app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, process_content))
        # حل مشكلة الـ Conflict بتجاهل التحديثات القديمة
        app.run_polling(drop_pending_updates=True)
