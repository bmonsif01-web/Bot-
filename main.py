import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import google.generativeai as genai

# --- إعدادات الأمان (القراءة من Variables) ---
# سيقوم البوت بالبحث عن هذه القيم في إعدادات Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_TAG = "chop07c-20"
DEVELOPER_USER = "SAID_BEN_01" 

# إعداد الذكاء الاصطناعي (Gemini)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("⚠️ Error: GEMINI_API_KEY not found in environment variables!")

# --- إعداد قاعدة البيانات ---
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

# --- النصوص (عربي، إنجليزي، فرنسي) ---
STRINGS = {
    'ar': {
        'welcome': "🛍️ **مرحباً بك في مساعد التسوق الذكي!**\n\nأرسل صورة منتج أو اسمه، وسأعطيك رابط أمازون فوراً.",
        'analyzing': "🔍 جاري تحليل الصورة...",
        'searching': "🚀 جاري البحث عن عرض لـ: ",
        'buy_btn': "اشتري الآن من أمازون 🛒",
        'dev_btn': "تواصل مع المطور @SAID_BEN_01 👨‍💻",
        'error': "❌ عذراً، لم أستطع تحديد المنتج. جرب صورة أوضح.",
        'lang_set': "✅ تم ضبط اللغة للعربية."
    },
    'en': {
        'welcome': "🛍️ **Welcome to Smart Shopping Assistant!**\n\nSend a product photo or name for an Amazon link.",
        'analyzing': "🔍 AI is analyzing image...",
        'searching': "🚀 Searching Amazon for: ",
        'buy_btn': "Buy on Amazon 🛒",
        'dev_btn': "Contact Developer @SAID_BEN_01 👨‍💻",
        'error': "❌ Identification failed. Try a clearer photo.",
        'lang_set': "✅ English language selected."
    },
    'fr': {
        'welcome': "🛍️ **Bienvenue sur l'Assistant Shopping !**\n\nEnvoyez une photo ou le nom d'un produit.",
        'analyzing': "🔍 L'IA analyse l'image...",
        'searching': "🚀 Recherche sur Amazon pour : ",
        'buy_btn': "Voir sur Amazon 🛒",
        'dev_btn': "Contacter @SAID_BEN_01 👨‍💻",
        'error': "❌ Échec. Essayez une photo plus claire.",
        'lang_set': "✅ Langue réglée sur le Français."
    }
}

# --- الدوال الأساسية ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("العربية 🇸🇦", callback_data='setlang_ar')],
        [InlineKeyboardButton("English 🇺🇸", callback_data='setlang_en')],
        [InlineKeyboardButton("Français 🇫🇷", callback_data='setlang_fr')]
    ]
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
            # إرسال الصورة لـ Gemini
            prompt = "Identify this product precisely. Respond with the shortest commercial name only."
            contents = [prompt, {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
            response = model.generate_content(contents)
            search_query = response.text.strip()
        else:
            search_query = update.message.text

        domain = "amazon.fr" if lang == 'fr' else "amazon.com"
        amazon_url = f"https://www.amazon.{domain}/s?k={search_query.replace(' ', '+')}&tag={AMAZON_TAG}"

        keyboard = [
            [InlineKeyboardButton(STRINGS[lang]['buy_btn'], url=amazon_url)],
            [InlineKeyboardButton(STRINGS[lang]['dev_btn'], url=f"https://t.me/{DEVELOPER_USER}")]
        ]
        
        await update.message.reply_text(
            f"✅ **تم العثور على المنتج!**\n📦 **{search_query}**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        await status_msg.delete()

    except Exception:
        await status_msg.edit_text(STRINGS[lang]['error'])

if __name__ == '__main__':
    setup_db()
    if not TELEGRAM_TOKEN:
        print("❌ CRITICAL ERROR: TELEGRAM_TOKEN is missing!")
    else:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(language_handler, pattern='^setlang_'))
        app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, process_content))
        print("🚀 البوت يعمل الآن...")
        app.run_polling()
