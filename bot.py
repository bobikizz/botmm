import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = ''

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне видео, и я попробую его обработать.")

# ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ВИДЕО
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Уведомляем пользователя, что начали работу
    status_msg = await update.message.reply_text("Видео получено! Скачиваю и подготавливаю к конвертации...")

    # Получаем объект видео (берем самое последнее/лучшее качество)
    video_file = await update.message.video.get_file()
    
    # Путь, куда сохраняется файл
    input_path = f"video_{update.message.from_user.id}.mp4"
    
    # Скачивание файла на сервер
    await video_file.download_to_drive(input_path)
    
    await status_msg.edit_text("Видео скачано. Здесь будет логика конвертации в GIF...")
    
    # ТУТ БУДЕТ КОНВЕРТАЦИИ ЧЕРЕЗ moviepy
def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    
    
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    # Обработчик текста
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, отправь видео, а не текст.")

if __name__ == '__main__':
    main()
