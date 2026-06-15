import logging, os, html, re, urllib.parse
from telegram import Bot
import feedparser
import asyncio

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

async def main():
    bot = Bot(token=TOKEN)
    
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
                
                try:
                    if image_url:
                        await bot.send_photo(chat_id=YOUR_USER_ID, photo=image_url, caption=caption, parse_mode="HTML")
                    else:
                        await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send entry: {e}")
        except Exception as e:
            logger.error(f"Error checking feed {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
