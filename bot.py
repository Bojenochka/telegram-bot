import os
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Читаем переменные окружения
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_FOLDER_ID = os.getenv("GOOGLE_SHEETS_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "/etc/secrets/google_sheets_creds.json"

if not TOKEN or not GOOGLE_SHEETS_FOLDER_ID or not SERVICE_ACCOUNT_FILE:
    raise ValueError("Переменные окружения не установлены!")

# Настроим Google API
creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
)
gc = gspread.authorize(creds)


# Функция создания или открытия таблицы
def create_or_get_sheet():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_name = f"bot_{today}"

    try:
        sh = gc.open(file_name)
        logger.info(f"Используем существующую таблицу: {file_name}")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        pass

    try:
        sh = gc.create(file_name)
        sh.share("telegram-bot@your-project.iam.gserviceaccount.com", perm_type="user", role="writer")

        # Перемещение в нужную папку
        file_id = sh.id
        gc.request(
            "PATCH",
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            json={"parents": [GOOGLE_SHEETS_FOLDER_ID]},
        )

        # Создаем заголовки в таблице
        worksheet = sh.get_worksheet(0)
        headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст"]
        worksheet.append_row(headers)

        logger.info(f"Создан новый файл: {file_name}")
        return sh
    except Exception as e:
        logger.error(f"Ошибка при создании Google Sheet: {e}")
        return None


# Функция сохранения сообщений в таблицу
async def save_message_to_sheet(update: Update, context):
    if not update or not update.message:
        logger.error("Ошибка: update или update.message = None")
        return

    message = update.message
    chat = message.chat

    # Получаем таблицу
    sh = create_or_get_sheet()
    if not sh:
        logger.error("Ошибка: Не удалось получить Google Sheet")
        return

    worksheet = sh.get_worksheet(0)

    # Данные о сообщении
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Личное сообщение"
    username = message.from_user.username or message.from_user.full_name
    chat_id = chat.id
    message_id = message.message_id
    text = message.text or "Без текста"

    try:
        worksheet.append_row([now, group_name, username, chat_id, message_id, text])
        logger.info(f"Сообщение {message_id} сохранено в {sh.title}")
    except Exception as e:
        logger.error(f"Ошибка при записи в Google Sheets: {e}")


# Настраиваем Telegram бота
app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message_to_sheet))


@app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), bot_app.bot)
    bot_app.process_update(update)
    return "OK"


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8443))
    WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}"

    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )