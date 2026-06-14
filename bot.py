import logging, os, sqlite3, traceback
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import feedparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
DB_PATH = "/data/rss_bot.db"
PORT = 3000

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    try:
        os.makedirs("/data", exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS feeds (user_id INTEGER, feed_url TEXT UNIQUE, feed_title TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS sent_entries (user_id INTEGER, entry_id TEXT, PRIMARY KEY (user_id, entry_id))")
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully at /data/rss_bot.db")
    except Exception as e:
        logger.error(f"Init DB Error: {traceback.format_exc()}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا قائد. جاهز للتشخيص.")

async def add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args: await update.message.reply_text("استخدم /add <رابط>"); return
    url = context.args[0]
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries: await update.message.reply_text("رابط غير صالح."); return
    title = feed.feed.get("title", "بدون عنوان")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO feeds (user_id, feed_url, feed_title) VALUES (?, ?, ?)", (user_id, url, title))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"تمت إضافة: {title}")
    except Exception as e:
        error_msg = f"حفظ الخطأ: {str(e)}"
        logger.error(error_msg)
        await update.message.reply_text(f"❌ {error_msg}")

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT feed_title, feed_url FROM feeds WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows: await update.message.reply_text("لا توجد خلاصات."); return
        msg = "\n".join([f"- {r[0]}: {r[1]}" for r in rows])
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في القراءة: {str(e)}")

# ... (باقي الدوال مشابهة مع try/except)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
def run_health_server(): HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

def main():
    init_db()
    global app
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    # باقي الهاندلرز...
    Thread(target=run_health_server, daemon=True).start()
    logger.info("Bot started with diagnostics mode...")
    app.run_polling()

if __name__ == "__main__": main()
