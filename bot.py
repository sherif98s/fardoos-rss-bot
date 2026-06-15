import logging, os, sqlite3, asyncio, html, re, urllib.parse
from datetime import datetime
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
    os.makedirs("/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS feeds (user_id INTEGER, feed_url TEXT UNIQUE, feed_title TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS sent_entries (user_id INTEGER, entry_id TEXT, PRIMARY KEY (user_id, entry_id))")
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_msg = (
        f"أهلاً بك، {user_name}! 🖐️\n\n"
        "أنا <b>قارئ RSS الذكي</b>، مهمتي أن أبقيك على اطلاع دائم بآخر الأخبار من مصادرك المفضلة.\n\n"
        "📌 <b>لتبدأ الآن:</b>\n"
        "• استخدم /add <رابط> لإضافة مصدر جديد\n"
        "• استخدم /test <رابط> لمعاينة المصدر قبل إضافته\n"
        "• استخدم /list لعرض مصادرك الحالية\n\n"
        "أرسل /help في أي وقت لعرض جميع الأوامر."
    )
    await update.message.reply_text(welcome_msg, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر:\n"
        "/start - تشغيل البوت\n"
        "/add <رابط> - إضافة خلاصة RSS\n"
        "/test <رابط> - معاينة الخلاصة قبل إضافتها\n"
        "/list - عرض الخلاصات المضافة (بالأرقام)\n"
        "/remove <رقم> - حذف خلاصة من القائمة\n"
        "/check - فحص فوري للخلاصات\n"
        "/help - هذه المساعدة"
    )

async def test_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /test <رابط الخلاصة>")
        return
    url = context.args[0]
    await update.message.reply_text("🔍 جاري فحص الخلاصة...")
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            await update.message.reply_text("❌ رابط الخلاصة غير صالح أو لا يحتوي على مقالات.")
            return
        title = html.escape(feed.feed.get("title", "بدون عنوان"))
        entries = feed.entries[:3]
        if not entries:
            await update.message.reply_text(f"⚠️ الخلاصة '{title}' ليس بها مقالات حالياً.")
            return
        
        msg = f"<b>📋 معاينة الخلاصة: {title}</b>\n\n"
        for i, entry in enumerate(entries, 1):
            entry_title = html.escape(entry.get("title", "بدون عنوان"))
            entry_link = urllib.parse.quote(entry.get("link", ""), safe=':/?&=')
            published = entry.get("published", "")
            date_str = ""
            if published:
                try:
                    dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %z")
                    date_str = html.escape(dt.strftime("%Y-%m-%d %H:%M"))
                except:
                    date_str = html.escape(published)
            
            msg += f"<b>{i}. {entry_title}</b>\n"
            msg += f"<a href='{entry_link}'>🔗 رابط المقال</a>\n"
            if date_str:
                msg += f"<i>📅 {date_str}</i>\n\n"
        msg += "لإضافة هذه الخلاصة، استخدم الأمر: /add <الرابط>"
        try:
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            plain_msg = msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<a href='", "").replace("'>", " ")
            await update.message.reply_text(plain_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء فحص الرابط: {str(e)}")

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
    except sqlite3.IntegrityError:
        await update.message.reply_text("هذه الخلاصة مضافة بالفعل.")
    except Exception as e:
        await update.message.reply_text(f"خطأ في الحفظ: {str(e)}")

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT feed_title, feed_url FROM feeds WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows: await update.message.reply_text("لا توجد خلاصات."); return
    # ترقيم الخلاصات لتسهيل الحذف
    msg = "\n".join([f"{i+1}. {r[0]}\n   {r[1]}" for i, r in enumerate(rows)])
    await update.message.reply_text(msg)

async def remove_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /remove <رقم الخلاصة>\nلمعرفة الأرقام، استخدم /list")
        return
    try:
        index = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT feed_url, feed_title FROM feeds WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    
    if index < 0 or index >= len(rows):
        await update.message.reply_text("رقم الخلاصة غير موجود.")
        conn.close()
        return
    
    url, title = rows[index]
    # حذف الخلاصة
    c.execute("DELETE FROM feeds WHERE user_id=? AND feed_url=?", (user_id, url))
    # تنظيف المقالات المرتبطة (اختياري، للحفاظ على نظافة القاعدة)
    c.execute("DELETE FROM sent_entries WHERE user_id=? AND entry_id LIKE ?", (user_id, f"%{url}%"))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"تم حذف: {title}")

async def check_feeds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = await check_feeds_for_user(user_id)
    await update.message.reply_text(f"تم إرسال {count} مقال جديد." if count > 0 else "لا توجد مقالات جديدة.")

def extract_image_url(entry):
    if 'media_content' in entry:
        for media in entry.media_content:
            if 'image' in media.get('type', '') or media.get('medium') == 'image':
                return media['url']
    if 'enclosures' in entry:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc['href']
    summary = entry.get('summary', '')
    if summary:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
        if match:
            return match.group(1)
    return None

async def check_feeds_for_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT feed_url, feed_title FROM feeds WHERE user_id=?", (user_id,))
    feeds = [(row[0], row[1]) for row in c.fetchall()]
    new_count = 0
    for url, feed_title in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                entry_id = entry.get("id", entry.get("link", ""))
                if not entry_id: continue
                c.execute("SELECT 1 FROM sent_entries WHERE user_id=? AND entry_id=?", (user_id, entry_id))
                if c.fetchone() is None:
                    title = html.escape(entry.get("title", "بدون عنوان"))
                    link = urllib.parse.quote(entry.get("link", ""), safe=':/?&=')
                    published = entry.get("published", "")
                    date_str = ""
                    if published:
                        try:
                            dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %z")
                            date_str = html.escape(dt.strftime("%Y-%m-%d %H:%M"))
                        except:
                            date_str = html.escape(published)
                    
                    caption = (
                        f"<b>📰 {title}</b>\n"
                        f"<a href='{link}'>🔗 رابط المقال</a>\n"
                    )
                    if date_str:
                        caption += f"<i>📅 {date_str}</i>\n"
                    caption += f"<b>🏷 {html.escape(feed_title)}</b>"
                    
                    image_url = extract_image_url(entry)
                    try:
                        if image_url:
                            await app.bot.send_photo(chat_id=user_id, photo=image_url, caption=caption, parse_mode="HTML")
                        else:
                            await app.bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
                    except Exception:
                        plain_caption = caption.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<a href='", "").replace("'>", " ")
                        if image_url:
                            await app.bot.send_photo(chat_id=user_id, photo=image_url, caption=plain_caption)
                        else:
                            await app.bot.send_message(chat_id=user_id, text=plain_caption)
                    
                    c.execute("INSERT INTO sent_entries (user_id, entry_id) VALUES (?, ?)", (user_id, entry_id))
                    new_count += 1
        except Exception as e:
            logger.error(f"Error checking feed {url}: {e}")
    conn.commit()
    conn.close()
    return new_count

async def check_all_feeds():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM feeds")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    for user_id in users:
        await check_feeds_for_user(user_id)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/check":
            asyncio.run(check_all_feeds())
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

def main():
    init_db()
    global app
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("test", test_feed))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    app.add_handler(CommandHandler("remove", remove_feed))
    app.add_handler(CommandHandler("check", check_feeds_command))
    Thread(target=run_health_server, daemon=True).start()
    logger.info("Bot started with auto-check, HTML formatting, image support, and fallback to plain text...")
    app.run_polling()

if __name__ == "__main__":
    main()
