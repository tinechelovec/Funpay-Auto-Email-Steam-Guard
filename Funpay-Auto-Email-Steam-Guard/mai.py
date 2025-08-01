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

# ─── Логгирование ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── Загрузка переменных из .env ───────────────────────────────────────
load_dotenv()
EMAIL = os.getenv("EMAIL_ADDRESS")
PASSWORD = os.getenv("EMAIL_PASSWORD")
FUNPAY_TOKEN = os.getenv("FUNPAY_AUTH_TOKEN")

# ─── IMAP сервер по домену ─────────────────────────────────────────────
def get_imap_server(email_address: str) -> str:
    domain = email_address.split('@')[-1]
    if 'mail.ru' in domain:
        return 'imap.mail.ru'
    elif 'gmail' in domain:
        return 'imap.gmail.com'
    elif 'yandex' in domain:
        return 'imap.yandex.ru'
    elif 'outlook' in domain or 'hotmail' in domain:
        return 'outlook.office365.com'
    raise ValueError("Unknown email provider")

# ─── Получение кода с почты ────────────────────────────────────────────
def fetch_latest_steam_code(last_uid=None):
    try:
        server = get_imap_server(EMAIL)
        with imaplib.IMAP4_SSL(server) as mail:
            mail.login(EMAIL, PASSWORD)
            mail.select("inbox")
            result, data = mail.uid('search', None, 'FROM "noreply@steampowered.com"')
            if not data[0]:
                return None, None, last_uid

            uids = data[0].split()
            latest_uid = uids[-1]

            if latest_uid == last_uid:
                return None, None, last_uid

            result, data = mail.uid('fetch', latest_uid, '(RFC822)')
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            date = datetime.strptime(msg['Date'], '%a, %d %b %Y %H:%M:%S %z').astimezone().strftime('%d.%m.%Y %H:%M:%S')

            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_payload(decode=True)
                    soup = BS(html, 'html.parser')
                    code_tag = soup.find('td', class_='title-48 c-blue1 fw-b a-center')
                    if code_tag:
                        return code_tag.get_text(strip=True), date, latest_uid
        return None, None, last_uid
    except Exception as e:
        logger.error(f"Ошибка при получении кода: {e}")
        return None, None, last_uid

# ─── Ожидание нового кода в течение N секунд ───────────────────────────
def wait_for_steam_code(timeout_seconds=60, last_uid=None):
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        code, date, new_uid = fetch_latest_steam_code(last_uid)
        if code:
            return code, date, new_uid
        time.sleep(5)
    return None, None, last_uid

# ─── Основная логика ────────────────────────────────────────────────────
def main():
    if not FUNPAY_TOKEN or not EMAIL or not PASSWORD:
        logger.critical("❌ Проверь .env файл: отсутствуют токены или данные почты.")
        return

    account = Account(FUNPAY_TOKEN)
    account.get()

    if not account.username:
        logger.critical("❌ Неверный FunPay токен.")
        return

    logger.info(f"✅ Авторизован в FunPay как {account.username}")
    runner = Runner(account)
    last_seen_uid = None

    logger.info("🕵️ Ожидание команды `!код`...")

    for event in runner.listen(requests_delay=5):
        try:
            if isinstance(event, NewMessageEvent):
                msg = event.message
                if msg.author_id == 0:
                    continue

                if msg.text.strip().lower() == "!код":
                    logger.info(f"Получен запрос на код от {msg.chat_id}")
                    account.send_message(msg.chat_id, "🔍 Ищу код Steam Guard...")

                    code, date, new_uid = wait_for_steam_code(last_uid=last_seen_uid)
                    if code:
                        account.send_message(msg.chat_id, f"✅ Ваш код: `{code}`\n🕒 Время: {date}")
                        logger.info(f"Отправлен код: {code} (чат {msg.chat_id})")
                        last_seen_uid = new_uid
                    else:
                        account.send_message(msg.chat_id, "❌ Код не найден за 60 секунд.")
                        logger.info(f"Код не найден для чата {msg.chat_id}")
        except Exception as e:
            logger.error(f"Ошибка в обработке события: {str(e)}")

# ─── Запуск ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
