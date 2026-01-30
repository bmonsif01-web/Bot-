import logging
import sqlite3
import os
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import google.generativeai as genai

# --- المتغيرات (تأكد من إضافتها في Railway Variables) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_TAG = "chop07c-20"
DEVELOPER_USER = "SAID_BEN_01" 

# إعداد Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- قاعدة البيانات ---
DB_PATH = '/app/data/bot_users.db' if os.path.exists('/app/data') else 'bot_users.db'

def setup_db():
    if not os.path.exists(os.path.dirname(DB_PATH)) and '/app/data' in DB_PATH:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)''')
    conn.close()

def get_lang(uid):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT lang FROM users WHERE user_id = ?', (uid,)).fetchone()
    conn.close()
    return res[0] if res else 'ar'

# --- النصوص ---
MSG = {
    'ar': {'wait': "🔍 جاري فحص المنتج...", 'buy': "اشتري الآن من أمازون 🛒", 'err': "❌ لم أتعرف على الصورة، جرب زاوية أخرى."},
    'en': {'wait': "🔍 Analyzing product...", 'buy': "Buy on Amazon 🛒", 'err': "❌ Could not identify. Try again."}
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='set_ar'), 
           InlineKeyboardButton("English 🇺🇸", callback_data='set_en')]]
    await update.message.reply_text("🛍️ أهلاً بك! أرسل صورة أي منتج.", reply_markup=InlineKeyboardMarkup(kb))

async def set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data.split('_')[1]
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, lang) VALUES (?, ?)', (query.from_user.id, lang))
    conn.commit()
    conn.close()
    await query.edit_message_text("✅ Done!")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    lang = get_lang(uid)
    status = await update.message.reply_text(MSG[lang]['wait'])

    try:
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            img_bytes = await file.download_as_bytearray()
            
            # إرسال الصورة لـ Gemini
            response = model.generate_content([
                "Identify this product. Respond with ONLY the commercial name.",
                {"mime_type": "image/jpeg", "data": bytes(img_bytes)}
            ])
            query_text = response.text.strip()
        else:
            query_text = update.message.text

        # تصحيح الرابط (حل مشكلة تكرار amazon)
        link = f"https://www.amazon.com/s?k={query_text.replace(' ', '+')}&tag={AMAZON_TAG}"
        
        kb = [[InlineKeyboardButton(MSG[lang]['buy'], url=link)],
              [InlineKeyboardButton("تواصل مع المطور 👨‍💻", url=f"https://t.me/{DEVELOPER_USER}")]]
        
        await update.message.reply_text(f"📦 **{query_text}**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        await status.delete()
    except:
        await status.edit_text(MSG[lang]['err'])

if __name__ == '__main__':
    setup_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_lang, pattern='^set_'))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_msg))
    app.run_polling(drop_pending_updates=True)
