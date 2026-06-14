import logging, os, json, requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import feedparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

BOT_TOKEN = "8936834692:AAHwg_zdI-Jrcz3HI5GOVaIfZGKR_Sajndc"
SUPABASE_URL = "https://arkkvqozdakwaundrwgp.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
PORT = 3000

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا قائد. البوت يعمل الآن مع Supabase REST.")

async def add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args: await update.message.reply_text("استخدم /add <رابط>"); return
    url = context.args[0]; feed = feedparser.parse(url)
    if feed.bozo and not feed.entries: await update.message.reply_text("رابط غير صالح."); return
    title = feed.feed.get("title", "بدون عنوان")
    r = requests.post(f"{SUPABASE_URL}/rest/v1/feeds", json={"user_id": user_id, "feed_url": url, "feed_title": title}, headers=HEADERS)
    if r.status_code == 201: await update.message.reply_text(f"تمت إضافة: {title}")
    else: await update.message.reply_text("هذه الخلاصة مضافة بالفعل." if "duplicate" in r.text else "حدث خطأ أثناء الحفظ.")

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    r = requests.get(f"{SUPABASE_URL}/rest/v1/feeds?select=feed_title,feed_url&user_id=eq.{user_id}", headers=HEADERS)
    rows = r.json()
    if not rows: await update.message.reply_text("لا توجد خلاصات."); return
    await update.message.reply_text("\n".join([f"- {row['feed_title']}: {row['feed_url']}" for row in rows]))

async def check_feeds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("جاري الفحص...")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/feeds?select=feed_url&user_id=eq.{user_id}", headers=HEADERS)
    feeds = r.json(); new_count = 0
    for item in feeds:
        url = item['feed_url']; feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            eid = entry.get("id", entry.get("link", ""))
            if not eid: continue
            check = requests.get(f"{SUPABASE_URL}/rest/v1/sent_entries?select=entry_id&user_id=eq.{user_id}&entry_id=eq.{eid}", headers=HEADERS)
            if not check.json():
                msg = f"{entry.get('title', '')}\n{entry.get('link', '')}"
                await app.bot.send_message(chat_id=user_id, text=msg)
                requests.post(f"{SUPABASE_URL}/rest/v1/sent_entries", json={"user_id": user_id, "entry_id": eid}, headers=HEADERS)
                new_count += 1
    await update.message.reply_text(f"تم إرسال {new_count} مقال جديد." if new_count > 0 else "لا توجد مقالات جديدة.")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
def run_health_server(): HTTPServer(("0.0.0.0", 3000), HealthHandler).serve_forever()

def main():
    global app
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    app.add_handler(CommandHandler("check", check_feeds_command))
    Thread(target=run_health_server, daemon=True).start()
    print("البوت يعمل الآن مع Supabase REST...")
    app.run_polling()

if __name__ == "__main__": main()
