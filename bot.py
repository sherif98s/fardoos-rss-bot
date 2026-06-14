import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- الإعدادات ---
TOKEN = "8936834692:AAG-ORYDpaUxl6U2qOZENor4RevdaNU-D_c"  # سنغيره بعد قليل

# --- إعداد التسجيل ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- أوامر البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا قائد. البوت يعمل الآن. أرسل /help للمساعدة.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("الأوامر المتاحة:\n/start - تشغيل البوت\n/help - عرض هذه المساعدة")

# --- الوظيفة الرئيسية ---
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()