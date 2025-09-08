import os
import imaplib
import email
from bs4 import BeautifulSoup as BS
from datetime import datetime
import time
import logging
from dotenv import load_dotenv
from FunPayAPI import Account
from FunPayAPI.updater.runner import Runner
from FunPayAPI.updater.events import NewMessageEvent
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SteamGuardBot")

load_dotenv()
FUNPAY_TOKEN = os.getenv("FUNPAY_AUTH_TOKEN")

USAGE_FILE = "usage.json"
if not os.path.exists(USAGE_FILE):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)


def load_usage():
    with open(USAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_usage(data):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def format_time_left(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м"
    return f"{s}с"


accounts = []
index = 1
while True:
    email_addr = os.getenv(f"EMAIL_{index}")
    password = os.getenv(f"PASSWORD_{index}")
    command = os.getenv(f"COMMAND_{index}")
    daily_limit = os.getenv(f"DAILY_LIMIT_{index}")
    period_hours = os.getenv(f"PERIOD_HOURS_{index}")

    if not email_addr or not password or not command:
        break

    limit = None if daily_limit == "-" else int(daily_limit)
    if limit is not None and limit <= 0:
        logger.error(f"❌ DAILY_LIMIT_{index} должно быть больше 0 или '-'")
        exit(1)

    period = None if not period_hours or period_hours in ["-", "0"] else int(period_hours)

    accounts.append({
        "email": email_addr,
        "password": password,
        "command": command.lower().strip(),
        "limit": limit,
        "period_hours": period,
        "last_uid": None
    })
    index += 1

if not accounts:
    logger.critical("❌ В .env не найдено ни одной почты.")
    exit(1)


def get_imap_server(email_address: str) -> str:
    domain = email_address.split('@')[-1].lower()
    if 'mail.ru' in domain: return 'imap.mail.ru'
    if 'gmail' in domain: return 'imap.gmail.com'
    if 'yandex' in domain: return 'imap.yandex.ru'
    if 'rambler' in domain: return 'imap.rambler.ru'
    if 'firstmail' in domain: return 'imap.firstmail.ru'
    if 'notletters' in domain: return 'imap.notletters.com'
    if 'outlook' in domain or 'hotmail' in domain: return 'outlook.office365.com'
    raise ValueError("Неизвестный почтовый провайдер")


def fetch_latest_steam_code(email_address: str, password: str, last_uid=None):
    try:
        server = get_imap_server(email_address)
        with imaplib.IMAP4_SSL(server) as mail:
            mail.login(email_address, password)
            mail.select("inbox")
            result, data = mail.uid('search', None, 'FROM "noreply@steampowered.com"')
            if not data or not data[0]:
                return None, None, last_uid
            uids = data[0].split()
            latest_uid = uids[-1]
            if latest_uid == last_uid:
                return None, None, last_uid
            result, data = mail.uid('fetch', latest_uid, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            date_str = msg['Date']
            date_val = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z').astimezone().strftime('%d.%m.%Y %H:%M:%S')
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_payload(decode=True).decode(errors="ignore")
                    soup = BS(html, 'html.parser')
                    text = soup.get_text(" ", strip=True).lower()
                    if "вам понадобится код steam guard" not in text and "you'll need to enter the steam guard code" not in text:
                        return None, None, last_uid
                    code_tag = soup.find('td', class_='title-48 c-blue1 fw-b a-center')
                    if code_tag:
                        return code_tag.get_text(strip=True), date_val, latest_uid
        return None, None, last_uid
    except Exception as e:
        logger.error(f"Ошибка при получении кода: {e}")
        return None, None, last_uid


def wait_for_steam_code(acc, last_uid=None, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        code, date_val, new_uid = fetch_latest_steam_code(acc["email"], acc["password"], last_uid)
        if code:
            return code, date_val, new_uid
        time.sleep(5)
    return None, None, last_uid


def handle_message(account: Account, event: NewMessageEvent):
    text = (getattr(event.message, "text", "") or "").strip().lower()
    if not text:
        return

    usage = load_usage()
    buyer_id = str(event.message.author_id)
    now = int(time.time())

    for acc in accounts:
        if text != acc["command"]:
            continue

        limit, period_hours = acc["limit"], acc["period_hours"]

        if limit is None:
            account.send_message(event.message.chat_id, "🔍 Ищу код Steam Guard...")
            code, date_val, new_uid = wait_for_steam_code(acc, acc["last_uid"])
            if code:
                acc["last_uid"] = new_uid
                account.send_message(event.message.chat_id, f"✅ Ваш код: {code}\n🕒 Время: {date_val}")
                logger.info(f"✅ Код {code} отправлен пользователю {buyer_id} (безлимит).")
            else:
                account.send_message(event.message.chat_id, "❌ Код не найден за 60 секунд.")
                logger.warning(f"❌ Код для {buyer_id} не найден.")
            return

        usage.setdefault(buyer_id, {}).setdefault(acc["command"], {"count": 0})
        record = usage[buyer_id][acc["command"]]

        if period_hours is None:
            if record["count"] >= limit:
                msg = f"❌ Лимит {limit} навсегда исчерпан."
                account.send_message(event.message.chat_id, msg)
                logger.warning(f"🔒 Пользователь {buyer_id} исчерпал лимит {limit} навсегда.")
                save_usage(usage)
                return
        else:
            period_seconds = int(period_hours) * 3600
            record.setdefault("reset_time", now + period_seconds)

            if now > record["reset_time"]:
                record["count"] = 0
                record["reset_time"] = now + period_seconds

            if record["count"] >= limit:
                seconds_left = int(record["reset_time"] - now)
                reset_in = format_time_left(seconds_left)
                msg = f"❌ Лимит {limit}/{period_hours}ч исчерпан.\n⏳ Новый запрос будет доступен через {reset_in}."
                account.send_message(event.message.chat_id, msg)
                logger.warning(
                    f"🔒 Пользователь {buyer_id} исчерпал лимит {limit} ({acc['command']}). "
                    f"Сброс через {reset_in}."
                )
                save_usage(usage)
                return

        account.send_message(event.message.chat_id, "🔍 Ищу код Steam Guard...")
        code, date_val, new_uid = wait_for_steam_code(acc, acc["last_uid"])
        if not code:
            account.send_message(event.message.chat_id, "❌ Код не найден за 60 секунд.")
            logger.warning(f"❌ Пользователь {buyer_id} запросил код, но он не найден.")
            return

        acc["last_uid"] = new_uid
        record["count"] += 1
        save_usage(usage)

        left = max(0, limit - record["count"])
        total_txt = str(limit) if period_hours else "∞"

        account.send_message(
            event.message.chat_id,
            f"✅ Ваш код: {code}\n🕒 Время: {date_val}\n📊 Осталось: {left}/{total_txt}"
        )

        logger.info(
            f"📤 Код {code} отправлен пользователю {buyer_id} "
            f"(осталось {left}/{total_txt}, команда {acc['command']})"
        )
        return



def main():
    if not FUNPAY_TOKEN:
        logger.critical("❌ Проверь .env файл: отсутствует токен FunPay.")
        return

    account = Account(FUNPAY_TOKEN)
    account.get()
    if not account.username:
        logger.critical("❌ Неверный FunPay токен.")
        return

    logger.info(f"✅ Авторизован в FunPay как {account.username}")
    runner = Runner(account)

    logger.info("🕵️ Ожидание команд...")

    for event in runner.listen(requests_delay=5):
        try:
            if isinstance(event, NewMessageEvent):
                if event.message.author_id == 0:
                    continue
                handle_message(account, event)
        except Exception as e:
            logger.error(f"Ошибка в обработке события: {str(e)}")


if __name__ == "__main__":
    main()
