import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import google.generativeai as genai

# --- إعدادات البوت والبيانات الخاصة ---
# تم وضع البيانات التي أرسلتها
TELEGRAM_TOKEN = "8129202725:AAFksWTy7PXyn_tO_K9ycxzveOEam0iYXRA"
GEMINI_API_KEY = "AIzaSyCiHXJkuMyqOSKendVkaC-kARjUA6UcYKU"
AMAZON_TAG = "chop07c-20"
DEVELOPER_USER = "SAID_BEN_01"  # معرفك للتواصل

# إعداد مكتبة الذكاء الاصطناعي
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- إعداد قاعدة البيانات (متوافق مع Railway) ---
# يقوم الكود بفحص ما إذا كان مجلد البيانات الخاص بـ Railway موجوداً
DB_FOLDER = '/app/data'
if os.path.exists(DB_FOLDER):
    DB_PATH = os.path.join(DB_FOLDER, 'bot_users.db')
else:
    DB_PATH = 'bot_users.db'

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)''')
    conn.commit()
    conn.close()

def set_user_lang(user_id, lang):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, lang) VALUES (?, ?)', (user_id, lang))
    conn.commit()
    conn.close()

def get_user_lang(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT lang FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'ar'

# --- نصوص اللغات (عربي - إنجليزي - فرنسي) ---
STRINGS = {
    'ar': {
        'welcome': "👋 **أهلاً بك!**\n\nأرسل صورة أي منتج أو اسمه، وسأجلب لك رابط شرائه من أمازون فوراً.",
        'analyzing': "🤖 **جاري التحليل:** الذكاء الاصطناعي يفحص الصورة...",
        'searching': "🔎 **جاري البحث:** ",
        'buy_btn': "🛒 اشتري الآن من أمازون",
        'dev_btn': "👨‍💻 تواصل مع المطور",
        'error': "⚠️ عذراً، الصورة غير واضحة. حاول مرة أخرى.",
        'lang_set': "✅ تم حفظ اللغة العربية."
    },
    'en': {
        'welcome': "👋 **Welcome!**\n\nSend a product image or name, and I'll get you the Amazon link instantly.",
        'analyzing': "🤖 **Analyzing:** AI is checking the image...",
        'searching': "🔎 **Searching:** ",
        'buy_btn': "🛒 Buy Now on Amazon",
        'dev_btn': "👨‍💻 Contact Developer",
        'error': "⚠️ Sorry, image is unclear. Try again.",
        'lang_set': "✅ English language saved."
    },
    'fr': {
        'welcome': "👋 **Bienvenue !**\n\nEnvoyez une image ou le nom d'un produit pour avoir le lien Amazon.",
        'analyzing': "🤖 **Analyse :** L'IA examine l'image...",
        'searching': "🔎 **Recherche :** ",
        'buy_btn': "🛒 Acheter sur Amazon",
        'dev_btn': "👨‍💻 Contacter le développeur",
        'error': "⚠️ Désolé, image floue. Réessayez.",
        'lang_set': "✅ Langue française enregistrée."
    }
}

# --- دوال المعالجة ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # لوحة اختيار اللغة عند البدء
    keyboard = [
        [InlineKeyboardButton("العربية 🇸🇦", callback_data='setlang_ar')],
        [InlineKeyboardButton("English 🇺🇸", callback_data='setlang_en')],
        [InlineKeyboardButton("Français 🇫🇷", callback_data='setlang_fr')]
    ]
    await update.message.reply_text(
        STRINGS['ar']['welcome'], 
        parse_mode='Markdown', 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang = query.data.split('_')[1]
    set_user_lang(query.from_user.id, lang)
    
    # تحديث الرسالة لتأكيد اللغة
    await query.edit_message_text(STRINGS[lang]['lang_set'])

async def process_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    lang = get_user_lang(user_id)
    
    # إرسال رسالة انتظار
    status_msg = await update.message.reply_text(STRINGS[lang]['analyzing'])

    try:
        search_query = ""
        
        # 1. إذا كانت رسالة صورة
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            # نطلب من Gemini الاسم التجاري فقط
            prompt = "Identify this product. Respond ONLY with the short commercial name for Amazon search."
            contents = [prompt, {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
            
            response = model.generate_content(contents)
            search_query = response.text.strip()
            
        # 2. إذا كانت رسالة نصية
        elif update.message.text:
            search_query = update.message.text
            
        # إذا لم يتم العثور على نص للبحث
        if not search_query:
            await status_msg.edit_text(STRINGS[lang]['error'])
            return

        # تحديد الدومين حسب اللغة (فرنسي لفرنسا، وكوم للبقية)
        domain = "amazon.fr" if lang == 'fr' else "amazon.com"
        
        # تكوين رابط البحث مع كود العمولة (Tag)
        amazon_url = f"https://www.amazon.{domain}/s?k={search_query.replace(' ', '+')}&tag={AMAZON_TAG}"

        # أزرار الرد (الشراء + المطور)
        keyboard = [
            [InlineKeyboardButton(STRINGS[lang]['buy_btn'], url=amazon_url)],
            [InlineKeyboardButton(STRINGS[lang]['dev_btn'], url=f"https://t.me/{DEVELOPER_USER}")]
        ]
        
        # الرد النهائي
        await update.message.reply_text(
            f"📦 **{search_query}**\n\n{STRINGS[lang]['searching']} Amazon.{domain.split('.')[-1]}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # حذف رسالة "جاري التحليل"
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error processing message: {e}")
        await status_msg.edit_text(STRINGS[lang]['error'])

# --- تشغيل البوت ---
if __name__ == '__main__':
    # إعداد قاعدة البيانات
    setup_db()
    
    # بناء التطبيق
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة المعالجات (Handlers)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_handler, pattern='^setlang_'))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, process_content))
    
    print("🚀 Bot is running on Railway...")
    app.run_polling()
