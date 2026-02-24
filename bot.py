import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from moviepy import VideoFileClip
import moviepy.video.fx as fx

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = ''

MAX_SIZE_BYTES = 20 * 1024 * 1024

DEFAULT_SETTINGS = {
    'speed': 1.0,
    'fps': 10,
    'width': 480,
    'start_time': 0.0,
    'end_time': None, # None означает до конца видео
    'awaiting_input': None,
    'last_msg_id': None # Для предотвращения лагов клавиатуры
}

def get_settings_keyboard(settings):
    end_text = f"{settings['end_time']}с" if settings['end_time'] is not None else "До конца"
    keyboard = [
        [
            InlineKeyboardButton(f"Скорость: {settings['speed']}x", callback_data="edit_speed"),
            InlineKeyboardButton(f"FPS: {settings['fps']}", callback_data="edit_fps")
        ],
        [
            InlineKeyboardButton(f"Ширина: {settings['width']}px", callback_data="edit_width"),
            InlineKeyboardButton(f"Старт: {settings['start_time']}с", callback_data="edit_start")
        ],
        [
            InlineKeyboardButton(f"Конец: {end_text}", callback_data="edit_end"),
            InlineKeyboardButton("🚀 СОЗДАТЬ GIF", callback_data="start_conversion")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здравствуйте. Отправьте мне видео, и я отправлю вам GIF!")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    user_id = update.effective_user.id
    
    context.user_data['settings'] = DEFAULT_SETTINGS.copy()
    input_path = f"video_{user_id}.mp4"
    
    status_msg = await update.message.reply_text("📥 Скачиваю...")
    file = await video.get_file()
    await file.download_to_drive(input_path)
    
    # Узнаем длительность видео
    with VideoFileClip(input_path) as clip:
        duration = clip.duration
        context.user_data['settings']['video_duration'] = duration

    await status_msg.delete()
    msg = await update.message.reply_text(
        f"Видео получено (длительность: {duration:.1f}с).\nНастройте параметры:",
        reply_markup=get_settings_keyboard(context.user_data['settings'])
    )
    context.user_data['settings']['last_msg_id'] = msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    settings = context.user_data.get('settings')

    if not settings:
        await query.answer("Сессия истекла, отправьте видео снова.")
        return

    if data.startswith("edit_"):
        param = data.split("_")[1]
        settings['awaiting_input'] = param
        await query.message.reply_text(f"Введите значение для {param} (число):")
        await query.answer()
    
    elif data == "start_conversion":
        await query.edit_message_text("⏳ Обработка... Если файл большой, я попробую его сжать.")
        await convert_and_send_gif(update, context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = context.user_data.get('settings')
    if not settings or not settings.get('awaiting_input'):
        return

    param = settings['awaiting_input']
    text = update.message.text
    
    try:
        val = float(text)
        if param in ['fps', 'width']: val = int(val)
        
        settings[param] = val
        settings['awaiting_input'] = None
        
        # Чтобы клавиатура "не лагала", удаляем старое текстовое сообщение и обновляем главное
        try: await update.message.delete()
        except: pass

        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=settings['last_msg_id'],
            reply_markup=get_settings_keyboard(settings)
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка ввода. Введите только число.")

async def convert_and_send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    input_path = f"video_{user_id}.mp4"
    output_path = f"output_{user_id}.gif"
    settings = context.user_data.get('settings')
    
    curr_width = settings['width']
    curr_fps = settings['fps']
    
    try:
        for attempt in range(3):
            with VideoFileClip(input_path) as clip:
                # Настройка начала и конца
                start_t = max(0, settings['start_time'])
                end_t = settings['end_time'] if settings['end_time'] else clip.duration
                if end_t <= start_t: end_t = clip.duration
                
                new_clip = clip.subclip(start_t, end_t)
                
                # Скорость
                if settings['speed'] != 1.0:
                    new_clip = new_clip.speedx(settings['speed'])

                # Размер
                final_clip = new_clip.resize(width=curr_width)
                final_clip.write_gif(output_path, fps=curr_fps, logger=None)
                final_clip.close()

            if os.path.getsize(output_path) <= MAX_SIZE_BYTES:
                break
            
            # Сжатие если > 20МБ
            curr_width = int(curr_width * 0.7)
            curr_fps = max(5, curr_fps - 2)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Сжимаю сильнее (попытка {attempt+2})...")

        with open(output_path, 'rb') as f:
            await context.bot.send_animation(chat_id=update.effective_chat.id, animation=f)
            
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка: {e}")
    finally:
        await asyncio.sleep(1)
        for p in [input_path, output_path]:
            if os.path.exists(p): os.remove(p)
        context.user_data.clear()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.run_polling()

if __name__ == '__main__':
    main()
