import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import feedparser

# --- الإعدادات ---
TOKEN = "8936834692:AAG-ORYDpaUxl6U2qOZENor4RevdaNU-D_c"
DB_NAME = "rss_bot.db"

# --- إعداد التسجيل ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS feeds
                 (user_id INTEGER, feed_url TEXT UNIQUE, feed_title TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sent_entries
                 (user_id INTEGER, entry_id TEXT, PRIMARY KEY (user_id, entry_id))""")
    conn.commit()
    conn.close()

# --- أوامر البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك يا قائد. أنا بوت RSS الخاص بك.\n\n"
        "الأوامر المتاحة:\n"
        "/add <رابط> - إضافة خلاصة RSS جديدة\n"
        "/list - عرض الخلاصات المضافة\n"
        "/check - فحص الخلاصات يدوياً الآن\n"
        "/help - عرض هذه المساعدة"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر:\n"
        "/start - تشغيل البوت\n"
        "/add <رابط> - إضافة خلاصة RSS\n"
        "/list - عرض خلاصاتك\n"
        "/check - فحص فوري للخلاصات\n"
        "/help - هذه المساعدة"
    )

async def add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /add <رابط الخلاصة>")
        return

    url = context.args[0]

    # فحص الرابط
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            await update.message.reply_text("❌ رابط الخلاصة غير صالح أو لا يحتوي على مقالات.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في قراءة الرابط: {e}")
        return

    title = feed.feed.get("title", "بدون عنوان")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO feeds (user_id, feed_url, feed_title) VALUES (?, ?, ?)",
                  (user_id, url, title))
        conn.commit()
        await update.message.reply_text(f"✅ تمت إضافة الخلاصة: **{title}**")
    except sqlite3.IntegrityError:
        await update.message.reply_text("⚠️ هذه الخلاصة مضافة بالفعل.")
    finally:
        conn.close()

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT feed_title, feed_url FROM feeds WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 لا توجد خلاصات مضافة. استخدم /add <رابط> لإضافة واحدة.")
        return

    msg = "📋 **خلاصاتك:**\n"
    for i, (title, url) in enumerate(rows, 1):
        msg += f"{i}. {title}\n   {url}\n\n"
    await update.message.reply_text(msg)

async def check_feeds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 جاري فحص الخلاصات...")

    count = await check_feeds_for_user(user_id)

    if count > 0:
        await update.message.reply_text(f"✅ تم إرسال {count} مقال جديد.")
    else:
        await update.message.reply_text("📭 لا توجد مقالات جديدة.")

async def check_feeds_for_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT feed_url FROM feeds WHERE user_id=?", (user_id,))
    feeds = [row[0] for row in c.fetchall()]

    new_count = 0
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:  # آخر 5 مقالات فقط
                entry_id = entry.get("id", entry.get("link", ""))
                if not entry_id:
                    continue

                c.execute("SELECT 1 FROM sent_entries WHERE user_id=? AND entry_id=?",
                          (user_id, entry_id))
                if c.fetchone() is None:
                    title = entry.get("title", "بدون عنوان")
                    link = entry.get("link", "")
                    msg = f"📰 **{title}**\n🔗 {link}"
                    await app.bot.send_message(chat_id=user_id, text=msg)
                    c.execute("INSERT INTO sent_entries (user_id, entry_id) VALUES (?, ?)",
                              (user_id, entry_id))
                    new_count += 1
        except Exception as e:
            logger.error(f"خطأ في فحص الخلاصة {url}: {e}")

    conn.commit()
    conn.close()
    return new_count

# --- الوظيفة الرئيسية ---
def main():
    init_db()
    global app
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_feed))
    app.add_handler(CommandHandler("list", list_feeds))
    app.add_handler(CommandHandler("check", check_feeds_command))
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()