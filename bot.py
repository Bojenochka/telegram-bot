import logging
import os
import datetime
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# 🔹 Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔹 Читаем переменные окружения
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_FOLDER_ID = os.getenv("GOOGLE_SHEETS_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "/etc/secrets/google_sheets_creds.json"

if not TOKEN or not GOOGLE_SHEETS_FOLDER_ID or not SERVICE_ACCOUNT_FILE:
    raise ValueError(
        "Переменные окружения TOKEN, GOOGLE_SHEETS_FOLDER_ID и SERVICE_ACCOUNT_FILE должны быть установлены!")

# 🔹 Подключение к Google API
try:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
except Exception as e:
    logger.error(f"Ошибка при подключении к Google API: {e}")
    raise


# 🔹 Функция для создания или получения Google Sheet
def create_or_get_sheet():
    """Создает новый Google Sheet или получает существующий."""
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
        sh.share("telegram-bot-service@telegram-bot-sheets-450709.iam.gserviceaccount.com", perm_type="user",
                 role="writer")

        # 📂 Перемещаем в нужную папку
        file = sh.spreadsheet_id
        gc.request(
            "PATCH",
            f"https://www.googleapis.com/drive/v3/files/{file}",
            json={"parents": [GOOGLE_SHEETS_FOLDER_ID]},
        )

        # ✏ Создаем заголовки в таблице
        worksheet = sh.get_worksheet(0)
        headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст", "Категория",
                   "О чем речь"]
        worksheet.append_row(headers)

        logger.info(f"Создан новый файл: {file_name}")
        return sh
    except Exception as e:
        logger.error(f"Ошибка при создании Google Sheet: {e}")
        return None


# 🔹 Функция для сохранения сообщений в таблицу
async def save_message_to_sheet(update: Update, context: CallbackContext):
    """Сохраняет сообщение в Google Sheets."""
    if not update or not update.message:
        logger.error("Ошибка: update или update.message = None")
        return

    message = update.message
    chat = message.chat

    # 📌 Получаем таблицу на сегодня
    sh = create_or_get_sheet()
    if not sh:
        logger.error("Ошибка: Не удалось получить Google Sheet")
        return

    worksheet = sh.get_worksheet(0)

    # 📌 Данные о сообщении
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Личное сообщение"
    username = message.from_user.username or message.from_user.full_name
    chat_id = chat.id
    message_id = message.message_id
    text = message.text or "Без текста"
    category = ""  # 🔹 Можно добавить определение категории
    summary = ""  # 🔹 Краткое описание

    try:
        worksheet.append_row([now, group_name, username, chat_id, message_id, text, category, summary])
        logger.info(f"Сообщение {message_id} сохранено в {sh.title}")
    except Exception as e:
        logger.error(f"Ошибка при записи в Google Sheets: {e}")


# 🔹 Основная функция запуска бота
def main():
    """Запуск бота."""
    if not TOKEN:
        raise ValueError("Переменная окружения TOKEN не установлена!")

    application = Application.builder().token(TOKEN).build()

    # 🔹 Обработчик всех сообщений из чатов
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message_to_sheet))

    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()