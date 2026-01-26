import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Импорты MoviePy 2.x
from moviepy import VideoFileClip
import moviepy.video.fx as fx

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = ''

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'speed': 1.0,
    'fps': 10,
    'width': 480,
    'start_time': 0,
    'awaiting_input': None  # Флаг: какой параметр ждем от пользователя
}

def get_settings_keyboard(settings):
    keyboard = [
        [
            InlineKeyboardButton(f"Скорость: {settings['speed']}x", callback_data="edit_speed"),
            InlineKeyboardButton(f"FPS: {settings['fps']}", callback_data="edit_fps")
        ],
        [
            InlineKeyboardButton(f"Ширина: {settings['width']}px", callback_data="edit_width"),
            InlineKeyboardButton(f"Старт: {settings['start_time']}с", callback_data="edit_start")
        ],
        [InlineKeyboardButton("🚀 СОЗДАТЬ GIF", callback_data="start_conversion")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь видео, а затем укажи настройки кнопками или текстом.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    user_id = update.effective_user.id
    
    context.user_data['settings'] = DEFAULT_SETTINGS.copy()
    input_path = f"video_{user_id}.mp4"
    
    status_msg = await update.message.reply_text("Скачиваю видео...")
    file = await video.get_file()
    await file.download_to_drive(input_path)
    
    await status_msg.delete()
    await update.message.reply_text(
        "Нажми на кнопку, чтобы изменить параметр текстом:",
        reply_markup=get_settings_keyboard(context.user_data['settings'])
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    settings = context.user_data.get('settings')

    if not settings:
        await query.answer("Сессия истекла.")
        return

    if data.startswith("edit_"):
        param = data.split("_")[1]
        settings['awaiting_input'] = param
        await query.message.reply_text(f"Введите новое значение для: {param}")
        await query.answer()
    
    elif data == "start_conversion":
        settings['awaiting_input'] = None
        await query.edit_message_text("⏳ Начинаю конвертацию...")
        await convert_and_send_gif(update, context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода параметров"""
    settings = context.user_data.get('settings')
    
    if not settings or not settings.get('awaiting_input'):
        return # Если мы ничего не ждем, игнорируем текст

    param = settings['awaiting_input']
    text = update.message.text
    
    try:
        # Простая валидация чисел
        value = float(text) if param in ['speed', 'start_time'] else int(text)
        settings[param] = value
        settings['awaiting_input'] = None # Сбрасываем ожидание
        
        await update.message.reply_text(
            f"✅ Параметр {param} изменен на {value}",
            reply_markup=get_settings_keyboard(settings)
        )
    except ValueError:
        await update.message.reply_text("Ошибка! Введите число (например: 1.5 или 15).")

async def convert_and_send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    input_path = f"video_{user_id}.mp4"
    output_path = f"output_{user_id}.gif"
    settings = context.user_data.get('settings', DEFAULT_SETTINGS)
    
    try:
        with VideoFileClip(input_path) as clip:
            # Обрезка
            start_t = min(max(0, settings['start_time']), clip.duration - 0.5)
            new_clip = clip.subclipped(start_t, clip.duration) if hasattr(clip, 'subclipped') else clip.subclip(start_t, clip.duration)
            
            # Скорость
            if settings['speed'] != 1.0:
                new_clip = new_clip.with_effects([fx.MultiplySpeed(settings['speed'])]) if hasattr(fx, 'MultiplySpeed') else new_clip.speedx(settings['speed'])

            # Размер
            final_clip = new_clip.resized(width=settings['width']) if hasattr(new_clip, 'resized') else new_clip.resize(width=settings['width'])
            
            final_clip.write_gif(output_path, fps=settings['fps'], logger=None)
            final_clip.close()

        with open(output_path, 'rb') as gif_file:
            await context.bot.send_animation(chat_id=update.effective_chat.id, animation=gif_file, write_timeout=300)
        
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка: {e}")
    finally:
        await asyncio.sleep(1.5)
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
        context.user_data.clear()

def main():
    application = Application.builder().token(TOKEN).read_timeout(600).write_timeout(600).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(CallbackQueryHandler(button_handler))
    # Хендлер для текстовых сообщений (настроек)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
