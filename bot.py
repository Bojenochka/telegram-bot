import logging
import os
import datetime
import gspread
import requests
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Читаем переменные окружения
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_FOLDER_ID = os.getenv("GOOGLE_SHEETS_FOLDER_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "/etc/secrets/google_sheets_creds.json")

# Логируем путь к файлу сервисного аккаунта
logger.info(f"Путь к файлу сервисного аккаунта: {SERVICE_ACCOUNT_FILE}")

# Проверяем, существует ли файл
if not os.path.exists(SERVICE_ACCOUNT_FILE):
    logger.error(f"Файл {SERVICE_ACCOUNT_FILE} не найден. Проверь путь!")
    raise FileNotFoundError(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")

if not TOKEN or not GOOGLE_SHEETS_FOLDER_ID:
    raise ValueError("Переменные окружения TOKEN и GOOGLE_SHEETS_FOLDER_ID должны быть установлены!")

# Подключение к Google API
try:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    logger.info("Успешное подключение к Google API!")
except Exception as e:
    logger.error(f"Ошибка при подключении к Google API: {e}")
    raise

# Функция перемещения файла в папку Google Drive
def move_file_to_folder(file_id, folder_id, creds):
    headers = {"Authorization": f"Bearer {creds.token}"}
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?addParents={folder_id}&removeParents=root"
    response = requests.patch(url, headers=headers)

    if response.status_code == 200:
        logger.info(f"Файл {file_id} перемещен в папку {folder_id}")
    else:
        logger.error(f"Ошибка перемещения файла: {response.text}")

# Функция для создания или получения Google Sheet
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

    # Если таблицы нет — создаем новую
    try:
        sh = gc.create(file_name)
        sh.share("telegram-bot-service@telegram-bot-sheets-450709.iam.gserviceaccount.com", perm_type="user", role="writer")

        # Перемещаем в нужную папку Google Drive
        move_file_to_folder(sh.spreadsheet_id, GOOGLE_SHEETS_FOLDER_ID, creds)

        # Создаем заголовки
        worksheet = sh.get_worksheet(0)
        headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст", "Категория", "Краткое описание"]
        worksheet.append_row(headers)

        logger.info(f"Создан новый файл: {file_name}")
        return sh
    except Exception as e:
        logger.error(f"Ошибка при создании Google Sheet: {e}")
        return None

# Функция для сохранения сообщений в таблицу
async def save_message_to_sheet(update: Update, context: CallbackContext):
    """Сохраняет сообщение в Google Sheets."""
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
    category = ""  # Можно добавить логику категорий
    summary = ""   # Можно добавить логику краткого описания

    try:
        worksheet.append_row([now, group_name, username, chat_id, message_id, text, category, summary])
        logger.info(f"Сообщение {message_id} сохранено в {sh.title}")
    except Exception as e:
        logger.error(f"Ошибка при записи в Google Sheets: {e}")

# Основная функция запуска бота
def main():
    """Запуск бота."""
    if not TOKEN:
        raise ValueError("Переменная окружения TOKEN не установлена!")

    application = Application.builder().token(TOKEN).build()

    # Обработка всех сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message_to_sheet))

    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()