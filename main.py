import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# إعدادات البيئة
TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")
TAG = os.getenv("AMAZON_TAG", "chop07c-20")

# إعداد Gemini
if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛍️ أهلاً بك! أرسل صورة منتج أو اسمه للحصول على رابط أمازون.")

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 جاري التحليل...")
    try:
        product_name = ""
        # إذا كانت صورة: حل مشكلة عدم وضوح الصورة بإرسالها لـ Gemini
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            response = model.generate_content([
                "Identify this product. Respond with ONLY the commercial name.",
                {"mime_type": "image/jpeg", "data": bytes(img_bytes)}
            ])
            product_name = response.text.strip()
        # إذا كان نصاً
        elif update.message.text:
            product_name = update.message.text

        if product_name:
            # الرابط الصحيح (بدون تكرار amazon)
            link = f"https://www.amazon.com/s?k={product_name.replace(' ', '+')}&tag={TAG}"
            kb = [[InlineKeyboardButton("🛒 اشتري الآن من أمازون", url=link)]]
            await update.message.reply_text(f"📦 المنتج: **{product_name}**", 
                                           reply_markup=InlineKeyboardMarkup(kb), 
                                           parse_mode='Markdown')
        await status_msg.delete()
    except Exception as e:
        print(f"Error: {e}")
        await status_msg.edit_text("❌ حدث خطأ. تأكد من تحديث مفتاح Gemini في Railway.")

if __name__ == '__main__':
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_all))
    app.run_polling(drop_pending_updates=True)
