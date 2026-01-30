import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import google.generativeai as genai

# --- الإعدادات (تأكد من وضعها في Variables بـ Railway) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AMAZON_TAG = "chop07c-20"
DEVELOPER_USER = "SAID_BEN_01" 

# إعداد Gemini 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # نستخدم فلاش لأنه الأسرع والأفضل في تحليل الصور
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- المنطق الأساسي لإرسال الصورة لـ Gemini واستخراج الاسم ---
async def analyze_image_with_gemini(photo_bytes):
    prompt = "What is the exact commercial name of this product? Provide only the name, no extra text."
    # تحويل الصورة لصيغة يفهمها Gemini
    image_parts = [{"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
    response = model.generate_content([prompt, image_parts[0]])
    return response.text.strip()

# --- معالجة الرسائل ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # التأكد من أن المستخدم أرسل صورة
    if update.message.photo:
        status_msg = await update.message.reply_text("🔍 جاري تحليل الصورة وإرسالها للذكاء الاصطناعي...")
        
        try:
            # 1. تحميل الصورة من تليجرام
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            # 2. إرسال الصورة لـ Gemini (المنطق الذي ذكرته)
            product_name = await analyze_image_with_gemini(photo_bytes)
            
            # 3. إنشاء رابط العمولة باستخدام الاسم المستخرج
            amazon_url = f"https://www.amazon.com/s?k={product_name.replace(' ', '+')}&tag={AMAZON_TAG}"
            
            # 4. إرسال النتيجة للمستخدم
            keyboard = [[InlineKeyboardButton("اشتري الآن 🛒", url=amazon_url)]]
            await update.message.reply_text(
                f"✅ تم التعرف على المنتج: **{product_name}**\nرابط البحث بعمولتك جاهز!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            await status_msg.delete()

        except Exception as e:
            print(f"Error: {e}")
            await status_msg.edit_text("❌ عذراً، حدث خطأ أثناء تحليل الصورة. تأكد من صلاحية مفتاح Gemini.")
    else:
        await update.message.reply_text("من فضلك أرسل صورة للمنتج ليقوم الذكاء الاصطناعي بتحليلها.")

# --- تشغيل البوت ---
if __name__ == '__main__':
    # تأكد من إنشاء قاعدة البيانات إذا كنت تستخدمها
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("أهلاً بك! أرسل صورة المنتج الآن.")))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.run_polling(drop_pending_updates=True) # لمنع التداخل (Conflict)
