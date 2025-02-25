from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import logging
import pytz
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import os

# إعدادات البوت
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TIMEZONE = pytz.timezone("Asia/Riyadh")

# إعداد التسجيل بشكل مفصل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def filter_impact(impact_text):
    """تصفية الأحداث حسب مستوى التأثير"""
    logger.debug(f"تحليل مستوى التأثير: {impact_text}")
    impact_text = impact_text.lower()
    if "high" in impact_text or "مرتفع" in impact_text:
        return "قوي 🔴"
    elif "medium" in impact_text or "moderate" in impact_text or "متوسط" in impact_text:
        return "متوسط 🟡"
    return None

def fetch_economic_events():
    """جلب الأحداث الاقتصادية الأمريكية ذات التأثير المتوسط والقوي"""
    logger.info("بدء عملية جلب الأحداث الاقتصادية...")
    url = "https://sa.investing.com/economic-calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        logger.info("إرسال طلب HTTP إلى موقع investing.com...")
        response = requests.get(url, headers=headers)
        logger.info(f"استجابة الخادم: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"فشل في الاتصال بالموقع. كود الحالة: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        events = []
        rows = soup.find_all("tr", class_="js-event-item")
        logger.info(f"تم العثور على {len(rows)} حدث إجمالي")
        us_events_count = 0
        filtered_events_count = 0

        for row in rows:
            try:
                # التحقق من أن الحدث أمريكي
                country_elem = row.find("td", class_="flagCur")
                if not country_elem or "United_States" not in country_elem.get("class", []):
                    continue

                us_events_count += 1
                logger.debug("تم العثور على حدث أمريكي")

                # جلب وقت الحدث
                time_elem = row.find("td", class_="first left time js-time")
                event_time = time_elem.text.strip() if time_elem else "غير محدد"

                # جلب اسم الحدث
                name_elem = row.find("td", class_="left event")
                event_name = name_elem.text.strip() if name_elem else "غير محدد"

                # جلب التأثير
                impact_elem = row.find("td", class_="left textNum sentiment noWrap")
                impact_text = impact_elem.text.strip() if impact_elem else ""

                # تصفية حسب التأثير
                impact = filter_impact(impact_text)
                if not impact:
                    continue

                filtered_events_count += 1
                events.append({
                    'time': event_time,
                    'name': event_name,
                    'impact': impact
                })
                logger.info(f"تمت إضافة حدث: {event_name} | التوقيت: {event_time} | التأثير: {impact}")

            except Exception as e:
                logger.error(f"خطأ في معالجة الحدث: {str(e)}")
                continue

        logger.info(f"إحصائيات الأحداث - إجمالي: {len(rows)}, أمريكية: {us_events_count}, مصفاة: {filtered_events_count}")
        return events
    except Exception as e:
        logger.error(f"خطأ في جلب الأحداث: {str(e)}")
        return []

def send_daily_summary(context: CallbackContext):
    """إرسال ملخص يومي للأحداث (3 رسائل كحد أقصى)"""
    logger.info("بدء إعداد الملخص اليومي...")
    events = fetch_economic_events()
    if not events:
        logger.info("لم يتم العثور على أحداث للملخص اليومي")
        return

    now = datetime.now(TIMEZONE)
    today_events = []

    for event in events:
        try:
            event_time = datetime.strptime(event['time'], "%I:%M %p").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=TIMEZONE
            )
            event['datetime'] = event_time
            today_events.append(event)
            logger.debug(f"تمت معالجة وقت الحدث: {event['name']} - {event_time}")
        except Exception as e:
            logger.error(f"خطأ في معالجة وقت الحدث: {str(e)}")

    if not today_events:
        logger.info("لم يتم العثور على أحداث لليوم")
        return

    # ترتيب الأحداث حسب الوقت
    today_events.sort(key=lambda x: x['datetime'])
    logger.info(f"تجهيز ملخص لـ {len(today_events)} حدث")

    # تقسيم الأحداث إلى 3 رسائل كحد أقصى
    events_per_message = (len(today_events) + 2) // 3
    messages = []

    for i in range(0, len(today_events), events_per_message):
        chunk = today_events[i:i + events_per_message]
        message = "📅 ملخص الأحداث الاقتصادية الأمريكية لليوم:\n\n"
        for event in chunk:
            message += f"⏰ {event['time']}\n"
            message += f"📊 {event['name']}\n"
            message += f"📈 التأثير: {event['impact']}\n"
            message += "➖➖➖➖➖➖➖➖\n"
        messages.append(message)

    # إرسال الرسائل
    for i, message in enumerate(messages[:3], 1):
        try:
            context.bot.send_message(chat_id=CHANNEL_ID, text=message)
            logger.info(f"تم إرسال رسالة الملخص اليومي {i}/{min(3, len(messages))}")
        except Exception as e:
            logger.error(f"خطأ في إرسال الملخص اليومي: {str(e)}")

def send_event_alert(context: CallbackContext):
    """إرسال تنبيه للحدث القادم"""
    event = context.job.context
    logger.info(f"إرسال تنبيه للحدث: {event['name']}")

    message = (
        "🚨 تنبيه: حدث اقتصادي خلال 15 دقيقة 🚨\n\n"
        f"⏰ الموعد: {event['time']}\n"
        f"📊 الحدث: {event['name']}\n"
        f"📈 التأثير: {event['impact']}\n"
    )
    try:
        context.bot.send_message(chat_id=CHANNEL_ID, text=message)
        logger.info(f"تم إرسال تنبيه الحدث بنجاح: {event['name']}")
    except Exception as e:
        logger.error(f"خطأ في إرسال تنبيه الحدث: {str(e)}")

def check_events(context: CallbackContext):
    """التحقق من الأحداث وإرسال التنبيهات"""
    try:
        now = datetime.now(TIMEZONE)
        logger.info("بدء التحقق من الأحداث القادمة...")
        events = fetch_economic_events()

        logger.info(f"التحقق من {len(events)} حدث للتنبيهات")
        for event in events:
            try:
                event_time = datetime.strptime(event['time'], "%I:%M %p").replace(
                    year=now.year, month=now.month, day=now.day, tzinfo=TIMEZONE
                )

                # حساب الوقت المتبقي للحدث
                time_diff = event_time - now
                minutes_until_event = time_diff.total_seconds() / 60

                # إرسال تنبيه قبل الحدث بـ 15 دقيقة
                if 14 <= minutes_until_event <= 16:
                    logger.info(f"جدولة تنبيه للحدث: {event['name']} (بعد {minutes_until_event:.1f} دقيقة)")
                    context.job_queue.run_once(send_event_alert, 1, context=event)

            except Exception as e:
                logger.error(f"خطأ في معالجة جدولة الحدث: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"خطأ في check_events: {str(e)}")

def start(update: Update, context: CallbackContext):
    """معالجة أمر /start"""
    logger.info("تم استلام أمر /start")
    try:
        update.message.reply_text(
            "✅ تم تشغيل بوت التنبيهات الاقتصادية!\n"
            "سيتم إرسال:\n"
            "- ملخص يومي للأحداث\n"
            "- تنبيهات قبل كل حدث بـ 15 دقيقة\n"
        )
        logger.info("تم الرد على أمر /start بنجاح")
        # إرسال الملخص الأولي
        send_daily_summary(context)
    except Exception as e:
        logger.error(f"خطأ في معالجة أمر /start: {str(e)}")

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    try:
        logger.info("بدء تشغيل البوت...")
        application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()

        dp = application.dispatcher

        # إضافة معالج الأمر start/
        dp.add_handler(CommandHandler("start", start))

        # جدولة وظيفة الملخص اليومي (عند منتصف الليل)
        application.job_queue.run_daily(
            send_daily_summary,
            time=datetime.strptime("00:00", "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6)
        )

        # جدولة وظيفة التحقق من الأحداث (كل دقيقة)
        application.job_queue.run_repeating(check_events, interval=60)

        # استخدام Webhook بدلًا من polling على Railway
        logger.info("تم بدء تشغيل البوت بنجاح!")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get('PORT', 5000)),
            url_path=os.getenv("TELEGRAM_TOKEN"),
            webhook_url=f"https://<YOUR_RAIL
