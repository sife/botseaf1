import logging
import pytz
from datetime import datetime
import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

# إعدادات البوت
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
RAILWAY_URL = os.getenv("RAILWAY_URL")
PORT = int(os.getenv("PORT", 5000))

TIMEZONE = pytz.timezone("Asia/Riyadh")

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def fetch_economic_events():
    """جلب الأحداث الاقتصادية الأمريكية"""
    logger.info("بدء جلب الأحداث الاقتصادية...")
    url = "https://sa.investing.com/economic-calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(f"فشل في الاتصال بالموقع. كود الحالة: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        events = []
        rows = soup.find_all("tr", class_="js-event-item")

        for row in rows:
            try:
                country_elem = row.find("td", class_="flagCur")
                if not country_elem or "United_States" not in country_elem.get("class", []):
                    continue

                time_elem = row.find("td", class_="first left time js-time")
                event_time = time_elem.text.strip() if time_elem else "غير محدد"

                name_elem = row.find("td", class_="left event")
                event_name = name_elem.text.strip() if name_elem else "غير محدد"

                impact_elem = row.find("td", class_="left textNum sentiment noWrap")
                impact_text = impact_elem.text.strip() if impact_elem else ""

                if "مرتفع" in impact_text or "high" in impact_text:
                    impact = "قوي 🔴"
                elif "متوسط" in impact_text or "medium" in impact_text:
                    impact = "متوسط 🟡"
                else:
                    continue

                events.append({
                    "time": event_time,
                    "name": event_name,
                    "impact": impact,
                })

            except Exception as e:
                logger.error(f"خطأ في معالجة الحدث: {str(e)}")

        return events

    except Exception as e:
        logger.error(f"خطأ في جلب الأحداث: {str(e)}")
        return []

async def send_daily_summary(context: CallbackContext):
    """إرسال ملخص يومي للأحداث"""
    logger.info("إرسال ملخص الأحداث اليومية...")
    events = fetch_economic_events()
    
    if not events:
        logger.info("لم يتم العثور على أحداث لليوم")
        return

    message = "📅 ملخص الأحداث الاقتصادية الأمريكية لليوم:\n\n"
    for event in events[:5]:
        message += f"⏰ {event['time']}\n📊 {event['name']}\n📈 التأثير: {event['impact']}\n➖➖➖➖➖➖➖➖\n"
    
    await context.bot.send_message(chat_id=CHANNEL_ID, text=message)
    logger.info("تم إرسال الملخص اليومي بنجاح!")

async def check_events(context: CallbackContext):
    """التحقق من الأحداث الجديدة ونشرها"""
    logger.info("🔍 التحقق من الأحداث الاقتصادية...")
    events = fetch_economic_events()

    if not events:
        logger.info("لا توجد أحداث جديدة.")
        return

    for event in events[:3]:  # الحد من عدد الإرساليات
        message = f"⏰ {event['time']}\n📊 {event['name']}\n📈 التأثير: {event['impact']}\n"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=message)

async def start(update: Update, context: CallbackContext):
    """معالجة أمر /start"""
    await update.message.reply_text("✅ بوت الأخبار الاقتصادية جاهز!")

async def main():
    """تشغيل البوت"""
    logger.info("بدء تشغيل البوت...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    job_queue = app.job_queue
    if job_queue is None:
        raise ValueError("❌ خطأ: JobQueue لم يتم تهيئته بشكل صحيح!")

    job_queue.run_daily(send_daily_summary, time=datetime.strptime("00:00", "%H:%M").time())
    job_queue.run_repeating(check_events, interval=60, first=0)

    if RAILWAY_URL:
        webhook_url = f"{RAILWAY_URL}/{TOKEN}"
        logger.info(f"إعداد Webhook على الرابط: {webhook_url}")
        await app.bot.set_webhook(url=webhook_url)

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=webhook_url,
        )
    else:
        logger.info("تشغيل البوت باستخدام polling...")
        await app.run_polling()

# ✅ إصلاح مشكلة event loop
if __name__ == "__main__":
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(main())
    except RuntimeError:
        asyncio.run(main())
