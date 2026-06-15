import logging, os, html, re, urllib.parse
from telegram import Bot
import feedparser
import asyncio
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
import trafilatura

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
YOUR_USER_ID = int(os.environ.get("USER_ID", "0"))
FEEDS_FILE = "feeds.txt"
WEBPAGES_FILE = "webpages.txt"

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
    """فحص موقع comss.ru/club واستخراج أحدث البرامج مع الصور"""
    url = "https://www.comss.ru/list.php?c=club"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        images = soup.select("img.img-icon")[:5]
        
        if not images:
            logger.warning("Comss: لم يتم العثور على صور.")
            return

        for img in images:
            parent_row = img.find_parent("div", class_="row")
            if not parent_row:
                continue

            title_tag = parent_row.select_one("div.list_title.clip a")
            if not title_tag:
                continue
            title = html.escape(title_tag.text.strip())
            link = title_tag.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.comss.ru/" + link

            desc_tag = parent_row.select_one("div.list_desc.clip")
            description = html.escape(desc_tag.text.strip()[:200]) if desc_tag else ""

            image_url = img.get("src", "")

            caption = f"<b>💿 {title}</b>\n"
            if description:
                caption += f"<i>{description}</i>\n"
            caption += f"<a href='{link}'>🔗 رابط البرنامج</a>"

            try:
                if image_url:
                    img_data = requests.get(image_url, headers=headers, timeout=10).content
                    await bot.send_photo(chat_id=YOUR_USER_ID, photo=img_data, caption=caption, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send comss entry: {e}")
                if image_url:
                    await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")

    except requests.exceptions.RequestException as e:
        logger.error(f"Comss request failed: {e}")
    except Exception as e:
        logger.error(f"Error checking comss: {e}")

async def process_webpages(bot):
    """معالجة الصفحات الرئيسية من webpages.txt واستخراج أحدث المقالات"""
    if not os.path.exists(WEBPAGES_FILE):
        logger.info("ملف webpages.txt غير موجود. تخطي.")
        return

    with open(WEBPAGES_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for homepage_url in urls:
        try:
            # 1. تحميل الصفحة الرئيسية
            response = requests.get(homepage_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # 2. البحث عن روابط المقالات المحتملة
            article_candidates = []

            # الأنماط الشائعة لعناوين المقالات في المواقع العربية
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True)

                # تجاهل الروابط غير المفيدة
                if not text or len(text) < 15 or href.startswith("#"):
                    continue

                # تجاهل روابط التنقل والشبكات الاجتماعية
                if any(keyword in text.lower() for keyword in ["رئيسية", "اتصل بنا", "من نحن", "سياسة الخصوصية", "facebook", "twitter", "youtube", "instagram"]):
                    continue

                # بناء الرابط الكامل
                full_url = urllib.parse.urljoin(homepage_url, href)

                # البحث عن عنصر أبوي (parent) قد يحتوي على صورة
                parent = a_tag.find_parent(["article", "div", "li", "section"])
                img_tag = parent.find("img") if parent else None
                img_url = img_tag.get("src") if img_tag else ""
                if img_url and not img_url.startswith("http"):
                    img_url = urllib.parse.urljoin(homepage_url, img_url)

                article_candidates.append({
                    "title": text,
                    "url": full_url,
                    "image_url": img_url
                })

            # 3. إزالة التكرارات (بناءً على الرابط)
            seen_urls = set()
            unique_articles = []
            for article in article_candidates:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)

            # 4. إرسال أول 3 مقالات
            articles_sent = 0
            for article in unique_articles[:3]:
                title = html.escape(article["title"])
                link = article["url"]
                image_url = article["image_url"]

                caption = f"<b>📰 {title}</b>\n<a href='{link}'>🔗 رابط المقال</a>"

                try:
                    if image_url:
                        try:
                            img_data = requests.get(image_url, headers=headers, timeout=10).content
                            await bot.send_photo(chat_id=YOUR_USER_ID, photo=img_data, caption=caption, parse_mode="HTML")
                        except Exception:
                            await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
                    else:
                        await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
                    articles_sent += 1
                except Exception as e:
                    logger.error(f"Error sending article from {homepage_url}: {e}")

            logger.info(f"Sent {articles_sent} articles from {homepage_url}")

        except Exception as e:
            logger.error(f"Error processing homepage {homepage_url}: {e}")
async def main():
    bot = Bot(token=TOKEN)

    # --- رسالة النبض ---
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

    # فحص الصفحات الرئيسية من webpages.txt
    await process_webpages(bot)

    # فحص خلاصات RSS من feeds.txt
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, "r") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    title = html.escape(entry.get("title", "بدون عنوان"))
                    link = entry.get("link", "")
                    if not link:
                        continue
                    
                    caption = f"<b>📰 {title}</b>\n<a href='{link}'>🔗 رابط المقال</a>"
                    image_url = extract_image_url(entry)
                    
                    if image_url:
                        try:
                            await bot.send_photo(chat_id=YOUR_USER_ID, photo=image_url, caption=caption, parse_mode="HTML")
                        except Exception:
                            await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
                    else:
                        await bot.send_message(chat_id=YOUR_USER_ID, text=caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error checking feed {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
