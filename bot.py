import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import feedparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from supabase import create_client, Client

TOKEN = os.environ.get("BOT_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
PORT = 3000

supabase: Client = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def init_supabase():
    global supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # إنشاء الجداول عبر واجهة SQL أو ننشئها يدويًا أول مرة
    try:
        supabase.table("feeds").select("user_id").limit(1).execute()
    except:
        pass  # الجدول غير موجود، سيتم إنشاؤه من اللوحة

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا قائد. البوت الآن متصل بـ Supabase.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("الأوامر: /start, /add <رابط>, /list, /check, /help")

async def add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /add <رابط الخلاصة>")
        return
    url = context.args[0]
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        await update.message.reply_text("رابط الخلاصة غير صالح.")
        return
    title = feed.feed.get("title", "بدون عنوان")

    # حفظ في Supabase
    try:
        supabase.table("feeds").insert({
            "user_id": user_id,
            "feed_url": url,
            "feed_title": title
        }).execute()
        await update.message.reply_text(f"تمت إضافة: {title}")
    except Exception as e:
        if "duplicate key" in str(e).lower():
            await update.message.reply_text("هذه الخلاصة مضافة بالفعل.")
        else:
            await update.message.reply_text("حدث خطأ أثناء الحفظ.")

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        res = supabase.table("feeds").select("feed_title", "feed_url").eq("user_id", user_id).execute()
        rows = res.data
        if not rows:
            await update.message.reply_text("لا توجد خلاصات.")
            return
        msg = "\n".join([f"- {r['feed_title']}: {r['feed_url']}" for r in rows])
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text("حدث خطأ.")

async def check_feeds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = await check_feeds_for_user(user_id)
    if count > 0:
        await update.message.reply_text(f"تم إرسال {count} مقال جديد.")
    else:
        await update.message.reply_text("لا توجد مقالات جديدة.")

async def check_feeds_for_user(user_id):
    try:
        res = supabase.table("feeds").select("feed_url").eq("user_id", user_id).execute()
        feeds = res.data
        new_count = 0
        for row in feeds:
            url = row['feed_url']
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                entry_id = entry.get("id", entry.get("link", ""))
                if not entry_id:
                    continue
                # التحقق من المقالات المرسلة
                check_res = supabase.table("sent_entries").select("entry_id").eq("user_id", user_id).eq("entry_id", entry_id).execute()
                if not check_res.data:
                    msg = f"{entry.get('title', '')}\n{entry.get('link', '')}"
                    await app.bot.send_message(chat_id=user_id, text=msg)
                    supabase.table("sent_entries").insert({
                        "user_id": user_id,
                        "entry_id": entry_id
                    }).execute()
                    new_count += 1
        return new_count
    except Exception as e:
        logger.error(f"Error checking feeds: {e}")
        return 0

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

def main():
    init_supabase()
    global app
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    app.add_handler(CommandHandler("check", check_feeds_command))
    Thread(target=run_health_server, daemon=True).start()
    print("البوت يعمل الآن مع Supabase عبر HTTP...")
    app.run_polling()

if __name__ == "__main__":
    main()
