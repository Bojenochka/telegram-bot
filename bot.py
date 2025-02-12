import logging
import os
import datetime
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔹 Настройки Google Sheets
GOOGLE_SHEETS_FOLDER_ID = "1B2OErx-Ch_c-BktZ8KyoFPGJqruAi--4"  # 📂 ID папки Google Drive
SERVICE_ACCOUNT_FILE = "/etc/secrets/google_sheets_creds.json"

# Подключение к Google API
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=[
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])
gc = gspread.authorize(creds)

def create_or_get_sheet():
    """Создает новый Google Sheet или получает существующий."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_name = f"bot_{today}"

    # 🔍 Проверяем, есть ли уже созданный файл
    try:
        sh = gc.open(file_name)
        logger.info(f"Используем существующую таблицу: {file_name}")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        pass

    # 📌 Если нет — создаем новую Google Таблицу
    sh = gc.create(file_name)
    sh.share("telegram-bot-service@telegram-bot-sheets-450709.iam.gserviceaccount.com", perm_type="user", role="writer")

    # 📂 Перемещаем в нужную папку
    drive_service = creds.with_scopes(["https://www.googleapis.com/auth/drive"])
    file = sh.spreadsheet_id
    gc.request(
        "PATCH",
        f"https://www.googleapis.com/drive/v3/files/{file}",
        json={"parents": [GOOGLE_SHEETS_FOLDER_ID]},
    )

    # ✏ Создаем заголовки в таблице
    worksheet = sh.get_worksheet(0)
    headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст", "Категория", "О чем речь"]
    worksheet.append_row(headers)

    logger.info(f"Создан новый файл: {file_name}")
    return sh

def save_message_to_sheet(update: Update, context: CallbackContext):
    """Сохраняет сообщение в Google Sheets."""
    message = update.message
    chat = message.chat

    # 📌 Получаем таблицу на сегодня
    sh = create_or_get_sheet()
    worksheet = sh.get_worksheet(0)

    # 📌 Данные о сообщении
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Личное сообщение"
    username = message.from_user.username or message.from_user.full_name
    chat_id = chat.id
    message_id = message.message_id
    text = message.text
    category = ""  # 🔹 Можно добавить определение категории
    summary = ""  # 🔹 Краткое описание

    # 📌 Записываем в таблицу
    worksheet.append_row([now, group_name, username, chat_id, message_id, text, category, summary])
    logger.info(f"Сообщение {message_id} сохранено в {sh.title}")

def main():
    """Запуск бота."""
    TOKEN = "7820174844:AAEpPab-Wt7iNSO0GkEjEdSKrYpNju3G8Z0"  # 🔹 Замените на ваш токен
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # 🔹 Обработчик всех сообщений из чатов
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, save_message_to_sheet))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()