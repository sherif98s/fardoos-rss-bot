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
            downloaded = trafilatura.fetch_url(homepage_url)
            if not downloaded:
                logger.warning(f"Trafilatura failed to download {homepage_url}")
                continue

            # 2. استخراج الروابط من الصفحة الرئيسية
            soup = BeautifulSoup(downloaded, "html.parser")
            article_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # تجاهل الروابط غير المقالية (مثل روابط التواصل الاجتماعي، التنقل، إلخ)
                if not href.startswith("#") and len(href) > 10:
                    full_url = urllib.parse.urljoin(homepage_url, href)
                    article_links.append(full_url)

            # 3. تصفية الروابط وإزالة التكرار
            unique_links = list(dict.fromkeys(article_links))[:10]  # نحلل أول 10 روابط فريدة
            articles_sent = 0

            for article_url in unique_links:
                if articles_sent >= 3:  # نكتفي بـ 3 مقالات لكل موقع
                    break

                try:
                    # 4. استخراج المحتوى الرئيسي من المقال
                    article_html = trafilatura.fetch_url(article_url)
                    if not article_html:
                        continue
                    extracted = trafilatura.extract(article_html, output_format="xml")
                    if not extracted:
                        continue

                    # تحليل الـ XML المستخرج للحصول على العنوان والنص والصورة
                    article_soup = BeautifulSoup(extracted, "xml")
                    title_tag = article_soup.find("title")
                    title = title_tag.text if title_tag else "بدون عنوان"
                    text_tag = article_soup.find("text")
                    description = text_tag.text[:200] if text_tag else ""
                    image_tag = article_soup.find("image")
                    image_url = image_tag.text if image_tag else ""

                    title = html.escape(title)
                    description = html.escape(description)

                    caption = f"<b>📰 {title}</b>\n"
                    if description:
                        caption += f"<i>{description}</i>\n"
                    caption += f"<a href='{article_url}'>🔗 رابط المقال</a>"

                    # إرسال المقال
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
                    logger.error(f"Error processing article {article_url}: {e}")
                    continue

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
