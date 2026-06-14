import logging
import os
import asyncio
import asyncpg
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import feedparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

TOKEN = os.environ.get("BOT_TOKEN", "")
DB_URL = os.environ.get("DB_URL", "")
PORT = 3000

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            user_id BIGINT,
            feed_url TEXT,
            feed_title TEXT,
            PRIMARY KEY (user_id, feed_url)
        )
    """)
    await conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا قائد. البوت يعمل الآن بقاعدة دائمة.")

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
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("INSERT INTO feeds (user_id, feed_url, feed_title) VALUES ($1, $2, $3)",
                           user_id, url, title)
        await update.message.reply_text(f"تمت إضافة: {title}")
    except asyncpg.UniqueViolationError:
        await update.message.reply_text("هذه الخلاصة مضافة بالفعل.")
    finally:
        await conn.close()

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT feed_title, feed_url FROM feeds WHERE user_id=$1", user_id)
    await conn.close()
    if not rows:
        await update.message.reply_text("لا توجد خلاصات.")
        return
    msg = "\n".join([f"- {r['feed_title']}: {r['feed_url']}" for r in rows])
    await update.message.reply_text(msg)

async def check_feeds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = await check_feeds_for_user(user_id)
    if count > 0:
        await update.message.reply_text(f"تم إرسال {count} مقال جديد.")
    else:
        await update.message.reply_text("لا توجد مقالات جديدة.")

async def check_feeds_for_user(user_id):
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT feed_url FROM feeds WHERE user_id=$1", user_id)
    new_count = 0
    for row in rows:
        url = row['feed_url']
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            entry_id = entry.get("id", entry.get("link", ""))
            if not entry_id:
                continue
            exists = await conn.fetchval("SELECT 1 FROM sent_entries WHERE user_id=$1 AND entry_id=$2", user_id, entry_id)
            if not exists:
                msg = f"{entry.get('title', '')}\n{entry.get('link', '')}"
                await app.bot.send_message(chat_id=user_id, text=msg)
                try:
                    await conn.execute("INSERT INTO sent_entries (user_id, entry_id) VALUES ($1, $2)", user_id, entry_id)
                except:
                    pass
                new_count += 1
    await conn.close()
    return new_count

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

async def main():
    await init_db()
    global app
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    app.add_handler(CommandHandler("check", check_feeds_command))
    Thread(target=run_health_server, daemon=True).start()
    print(f"البوت يعمل الآن بقاعدة دائمة على المنفذ {PORT}...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
