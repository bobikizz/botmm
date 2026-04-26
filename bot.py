import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest # Добавление для стабильности

from moviepy import VideoFileClip
import moviepy.video.fx as fx
import os
os.environ["IMAGEIO_FFMPEG_TIMEOUT"] = "300"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = '' # Вставьте свой токен

DEFAULT_SETTINGS = {
    'speed': 1.0,
    'fps': 10,
    'width': 480,
    'start_time': 0,
    'duration': 5.0,
    'awaiting_input': None,
    'last_menu_msg_id': None
}

def get_settings_keyboard(settings):
    keyboard = [
        [
            InlineKeyboardButton(f"🚀 Скорость: {settings['speed']}x", callback_data="edit_speed"),
            InlineKeyboardButton(f"🎞 FPS: {settings['fps']}", callback_data="edit_fps")
        ],
        [
            InlineKeyboardButton(f"📏 Ширина: {settings['width']}px", callback_data="edit_width"),
            InlineKeyboardButton(f"⏱ Старт: {settings['start_time']}с", callback_data="edit_start")
        ],
        [InlineKeyboardButton(f"⌛ Длительность: {settings['duration']}с", callback_data="edit_duration")],
        [InlineKeyboardButton("✅ СОЗДАТЬ GIF", callback_data="start_conversion")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здравствуйте! Пришлите видео — сделаем GIF.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    user_id = update.effective_user.id
    context.user_data['settings'] = DEFAULT_SETTINGS.copy()
    input_path = f"video_{user_id}.mp4"
    
    status_msg = await update.message.reply_text("📥 Скачиваю...")
    file = await video.get_file()
    await file.download_to_drive(input_path)
    await status_msg.delete()
    
    sent_msg = await update.message.reply_text(
        "Настройки:", reply_markup=get_settings_keyboard(context.user_data['settings'])
    )
    context.user_data['settings']['last_menu_msg_id'] = sent_msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    settings = context.user_data.get('settings')
    if not settings: return

    if query.data.startswith("edit_"):
        param = query.data.split("_")[1]
        settings['awaiting_input'] = param
        await query.edit_message_text(f"📝 Введите значение для **{param}**:", parse_mode="Markdown")
    
    elif query.data == "start_conversion":
        settings['awaiting_input'] = None
        await query.edit_message_text("⚙️ Обработка и сжатие...")
        await convert_and_send_gif(update, context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = context.user_data.get('settings')
    if not settings or not settings.get('awaiting_input'): return
    
    param = settings['awaiting_input']
    try:
        val = float(update.message.text.replace(',', '.'))
        settings[param] = val if param in ['speed', 'start_time', 'duration'] else int(val)
        settings['awaiting_input'] = None
        await update.message.delete()
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=settings['last_menu_msg_id'],
            text="Обновлено:",
            reply_markup=get_settings_keyboard(settings)
        )
    except:
        await update.message.reply_text("Введите число.")

async def convert_and_send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    input_path, output_path = f"video_{user_id}.mp4", f"output_{user_id}.gif"
    settings = context.user_data['settings']
    
    current_fps = settings['fps']
    current_width = settings['width']
    
    try:
        for attempt in range(3):
            # Используем with, чтобы основной клип закрывался сам
            with VideoFileClip(input_path) as clip:
                start_t = min(max(0, settings['start_time']), clip.duration - 0.1)
                end_t = min(start_t + settings['duration'], clip.duration)
                
                new_clip = clip.subclipped(start_t, end_t) if hasattr(clip, 'subclipped') else clip.subclip(start_t, end_t)
                
                if settings['speed'] != 1.0:
                    if hasattr(fx, 'MultiplySpeed'):
                        new_clip = new_clip.with_effects([fx.MultiplySpeed(settings['speed'])])
                    else:
                        new_clip = new_clip.speedx(settings['speed'])

                final_clip = new_clip.resized(width=current_width) if hasattr(new_clip, 'resized') else new_clip.resize(width=current_width)
                final_clip.write_gif(output_path, fps=current_fps, logger=None)
                
                # ЯВНО ЗАКРЫВАЕМ ВСЕ ПОДКЛИПЫ (ФИКС PermissionError)
                final_clip.close()
                if new_clip != clip:
                    new_clip.close()

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            if file_size <= 10.0:
                break
            else:
                current_fps = max(5, int(current_fps * 0.8))
                current_width = max(240, int(current_width * 0.9))
                logger.info(f"Слишком большой файл. Пробуем сжать больше...")

        # ИСПОЛЬЗУЕМ with open ДЛЯ ОТПРАВКИ (ФИКС PermissionError)
        with open(output_path, 'rb') as animation_file:
            await context.bot.send_animation(
                chat_id=update.effective_chat.id, 
                animation=animation_file,
                caption=f"🎬 Сжато до {os.path.getsize(output_path)//1024} KB",
                write_timeout=300
            )
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=settings['last_menu_msg_id'])
        
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка: {e}")
    finally:
        # Даем Windows 2 секунды "отпустить" файлы
        await asyncio.sleep(2)
        for p in [input_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    logger.warning(f"Не удалось удалить файл {p}: {e}")
        context.user_data.clear()

def main():
    # Настройка с таймаутами
    request_config = HTTPXRequest(http_version="1.1", read_timeout=60, write_timeout=60)
    app = Application.builder().token(TOKEN).request(request_config).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    print("Бот запущен. Жду видео...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
