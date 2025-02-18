import logging
import os
import datetime
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from telegram.error import TelegramError

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Читаем переменные окружения
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_FOLDER_ID = os.getenv("GOOGLE_SHEETS_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "/etc/secrets/google_sheets_creds.json"

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    logger.error(f"Файл service_account.json не найден по пути: {SERVICE_ACCOUNT_FILE}")
    raise FileNotFoundError(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")

logger.info(f"✅ Путь к файлу сервисного аккаунта: {SERVICE_ACCOUNT_FILE}")

if not TOKEN or not GOOGLE_SHEETS_FOLDER_ID:
    raise ValueError("Переменные окружения TOKEN и GOOGLE_SHEETS_FOLDER_ID должны быть установлены!")

# Подключение к Google API
try:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    logger.info("✅ Успешное подключение к Google API!")
except Exception as e:
    logger.error(f"❌ Ошибка при подключении к Google API: {e}")
    raise

# Функция для создания или получения Google Sheet
def create_or_get_sheet():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_name = f"bot_{today}"
    try:
        sh = gc.open(file_name)
        logger.info(f"📄 Используем существующую таблицу: {file_name}")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        try:
            sh = gc.create(file_name)
            sh.share("grebennikova.ekaterina95@gmail.com", perm_type="user", role="writer")
            file_id = sh.id
            gc.request("PATCH", f"https://www.googleapis.com/drive/v3/files/{file_id}", json={"parents": [GOOGLE_SHEETS_FOLDER_ID]})
            worksheet = sh.get_worksheet(0)
            headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст", "Категория", "Краткое описание"]
            worksheet.append_row(headers)
            logger.info(f"✅ Создан новый файл: {file_name}")
            return sh
        except Exception as e:
            logger.error(f"❌ Ошибка при создании Google Sheet: {e}")
            return None

async def save_message_to_sheet(update: Update, context: CallbackContext):
    if not update or not update.message:
        logger.error("❌ Ошибка: update или update.message = None")
        return
    message = update.message
    chat = message.chat
    sh = create_or_get_sheet()
    if not sh:
        return
    worksheet = sh.get_worksheet(0)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Личное сообщение"
    username = message.from_user.username or message.from_user.full_name
    data = [now, group_name, username, chat.id, message.message_id, message.text or "Без текста", "", ""]
    try:
        worksheet.append_row(data)
        logger.info(f"✅ Сообщение {message.message_id} сохранено в {sh.title}")
    except Exception as e:
        logger.error(f"❌ Ошибка при записи в Google Sheets: {e}")

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(f"⚠️ Ошибка Telegram API: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message_to_sheet))
    logger.info("🚀 Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
