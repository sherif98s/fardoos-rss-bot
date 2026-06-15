import logging, os, html, re, urllib.parse
from telegram import Bot
import feedparser
import asyncio
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
YOUR_USER_ID = int(os.environ.get("USER_ID", "0"))
FEEDS_FILE = "feeds.txt"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

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

async def check_comss(bot):
    """فحص موقع comss.ru/club واستخراج أحدث البرامج"""
    url = "https://www.comss.ru/list.php?c=club"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        # المحدد الصحيح بناءً على هيكل HTML الذي شاركته
        items = soup.select("div.row div.col-xs-8.col-sm-8.col-md-6.col-lg-6")[:5]
        
        if not items:
            logger.warning("Comss: لم يتم العثور على عناصر. قد يكون الموقع غير متاح أو تغير هيكله.")
            return

        for item in items:
            title_tag = item.select_one("div.list_title.clip a")
            if not title_tag:
                continue
            title = html.escape(title_tag.text.strip())
            link = title_tag.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.comss.ru/" + link
            
            # استخراج الوصف من div.list_desc.clip
            desc_tag = item.parent.select_one("div.list_desc.clip") if item.parent else None
            description = html.escape(desc_tag.text.strip()[:200]) if desc_tag else ""
            
            caption = f"<b>💿 {title}</b>\n"
            if description:
                caption += f"<i>{description}</i>\n"
            caption += f"<a href='{link}'>🔗 رابط البرنامج</a>"
            
            try:
                await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send comss entry: {e}")
                
    except requests.exceptions.RequestException as e:
        logger.error(f"Comss request failed: {e}")
    except Exception as e:
        logger.error(f"Error checking comss: {e}")

async def main():
    bot = Bot(token=TOKEN)

    # --- رسالة النبض (الحالة) ---
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    feeds_count = 0
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, "r") as f:
            feeds_count = len([line for line in f if line.strip() and not line.startswith("#")])

    status_msg = f"✅ نبض البوت: {now}\n📡 البوت يعمل تلقائياً كل 6 ساعات.\n📰 عدد الخلاصات النشطة: {feeds_count}"

    try:
        await bot.send_message(chat_id=YOUR_USER_ID, text=status_msg)
        logger.info("Status message sent.")
    except Exception as e:
        logger.error(f"Failed to send status: {e}")

    # فحص comss.ru مباشرة
    await check_comss(bot)

    # فحص خلاصات RSS من feeds.txt
    if not os.path.exists(FEEDS_FILE):
        logger.error("ملف feeds.txt غير موجود.")
        return

    with open(FEEDS_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:  # أحدث 3 مقالات
                title = html.escape(entry.get("title", "بدون عنوان"))
                link = entry.get("link", "")
                if not link:
                    continue
                
                caption = f"<b>📰 {title}</b>\n<a href='{link}'>🔗 رابط المقال</a>"
                image_url = extract_image_url(entry)
                
                # محاولة إرسال الصورة، وإذا فشلت نرسل النص فقط
                if image_url:
                    try:
                        await bot.send_photo(chat_id=YOUR_USER_ID, photo=image_url, caption=caption, parse_mode="HTML")
                    except Exception:
                        # فشل إرسال الصورة (رابط معطوب مثلاً)، نرسل النص بدلاً منها
                        await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error checking feed {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
