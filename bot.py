import logging
import os
import datetime
import json
import threading
import requests
import gspread
from flask import Flask
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# --- Конфигурация логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Чтение переменных окружения ---
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEETS_FOLDER_ID = os.getenv("GOOGLE_SHEETS_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "/etc/secrets/google_sheets_creds.json"
LAST_MESSAGE_FILE = "last_message_id.json"

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    logger.error(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")
    raise FileNotFoundError(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")

if not TOKEN or not GOOGLE_SHEETS_FOLDER_ID:
    raise ValueError("Переменные окружения TOKEN и GOOGLE_SHEETS_FOLDER_ID должны быть установлены!")

# --- Подключение к Google API ---
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

# --- Функции для работы с последним сообщением ---
def load_last_message_id():
    try:
        with open(LAST_MESSAGE_FILE, "r") as f:
            return json.load(f).get("last_id", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

def save_last_message_id(message_id):
    with open(LAST_MESSAGE_FILE, "w") as f:
        json.dump({"last_id": message_id}, f)

# --- Функция для перемещения Google Sheet в нужную папку ---
def move_sheet_to_folder(file_id):
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    response = requests.patch(url, headers=headers, json={"parents": [GOOGLE_SHEETS_FOLDER_ID]})

    if response.status_code == 200:
        logger.info("📂 Файл успешно перемещен в нужную папку Google Drive")
    else:
        logger.error(f"❌ Ошибка при перемещении файла: {response.text}")

# --- Функция для создания или получения Google Sheet ---
def create_or_get_sheet():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_name = f"bot_{today}"

    try:
        sh = gc.open(file_name)
        worksheet = sh.get_worksheet(0)
    except gspread.exceptions.SpreadsheetNotFound:
        try:
            sh = gc.create(file_name)
            sh.share("grebennikova.ekaterina95@gmail.com", perm_type="user", role="writer")

            move_sheet_to_folder(sh.id)

            if not sh.worksheets():
                worksheet = sh.add_worksheet(title="Sheet1", rows="100", cols="10")
            else:
                worksheet = sh.get_worksheet(0)

            headers = ["Дата и время", "Название группы", "Имя/Ник", "ID чата", "ID сообщения", "Текст", "Категория", "Краткое описание"]
            worksheet.append_row(headers)
        except Exception as e:
            logger.error(f"❌ Ошибка при создании Google Sheet: {e}")
            return None

    return worksheet

# --- Функция для сохранения сообщений в таблицу ---
async def save_message_to_sheet(update: Update, context: CallbackContext):
    if not update or not update.message:
        return

    message = update.message
    chat = message.chat
    message_id = message.message_id

    last_message_id = load_last_message_id()
    if message_id <= last_message_id:
        return

    worksheet = create_or_get_sheet()
    if not worksheet:
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Личное сообщение"
    username = message.from_user.username or message.from_user.full_name
    chat_id = chat.id
    text = message.text or "Без текста"

    worksheet.append_row([now, group_name, username, chat_id, message_id, text, "", ""])
    save_last_message_id(message_id)

# --- Минимальный HTTP-сервер на Flask ---
app = Flask(__name__)

@app.route('/')
def index():
    return "OK", 200

@app.route('/status')
def status():
    return {"status": "running", "bot": "active"}, 200

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)

# --- Основная функция запуска бота ---
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message_to_sheet))
    application.run_polling()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    main()