import asyncio
import logging
import pandas as pd
import torch
from datetime import datetime
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import nest_asyncio  # Фикс ошибки "This event loop is already running"

# 🔹 Настройки бота
TOKEN = "7820174844:AAEpPab-Wt7iNSO0GkEjEdSKrYpNju3G8Z0"
GROUP_ID = -1002298203209  # Укажи ID группы
EXCEL_FILE = "filtered_messages_context.xlsx"

# 🔹 Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# 🔹 Загрузка обученной модели
model_path = "./trained_model"  # Путь к сохраненной модели
device = torch.device("mps") if torch.backends.mps.is_built() else "cpu"

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path).to(device)

# 🔹 Функция анализа текста через обученную модель
def classify_message_with_context(text):
    """Определяет тип сообщения: Проблема, Предложение, Другое."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding="max_length", max_length=128).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    predicted_label = torch.argmax(outputs.logits, dim=1).item()
    label_map = {0: "Проблема", 1: "Предложение", 2: "Другое"}

    return label_map.get(predicted_label, "Другое")

# 🔹 Команда /start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я анализирую сообщения из группы и сохраняю проблемы и предложения в Excel."
    )

# 🔹 Функция обработки сообщений
async def handle_message(update: Update, context: CallbackContext):
    if update.message and update.message.chat_id == GROUP_ID:
        text = update.message.text
        date = datetime.fromtimestamp(update.message.date.timestamp())

        logging.info(f"📩 Получено сообщение: {text} | Дата: {date}")

        # Классификация сообщения
        message_type = classify_message_with_context(text)

        if message_type != "Другое":
            try:
                df = pd.read_excel(EXCEL_FILE)
            except FileNotFoundError:
                df = pd.DataFrame(columns=["Дата", "Тип сообщения", "Сообщение"])

            # Добавление данных
            new_row = {"Дата": date, "Тип сообщения": message_type, "Сообщение": text}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            # Сохранение в Excel
            df.to_excel(EXCEL_FILE, index=False, engine="openpyxl")
            logging.info(f"✅ Сообщение сохранено в Excel: {new_row}")

# 🔹 Функция для обработки старых сообщений
async def handle_old_messages(context: CallbackContext):
    logging.info("🔄 Проверка старых сообщений...")
    async for update in context.application.bot.get_updates(offset=None, timeout=10):
        if update.message and update.message.chat_id == GROUP_ID:
            await handle_message(update, context)

# 🔹 Основная функция
async def main():
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Chat(GROUP_ID) & filters.TEXT, handle_message))

    # Настроим планировщик задач
    scheduler = AsyncIOScheduler()
    scheduler.add_job(handle_old_messages, "interval", minutes=5, args=[application])
    scheduler.start()

    logging.info("🤖 Бот запущен и анализирует сообщения...")

    await application.run_polling()

# 🔹 Запуск
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())