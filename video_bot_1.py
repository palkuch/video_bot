import os
import re
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = "8766144410:AAG6_hzXnL1BFomrrG4DNA5KRwtb0c8a9Vg"

URL_PATTERN = re.compile(
    r'https?://'
    r'(?:www\.)?'
    r'(?:youtube\.com/|youtu\.be/|'
    r'tiktok\.com/|vm\.tiktok\.com/|'
    r'instagram\.com/|'
    r'twitter\.com/|x\.com/|t\.co/)'
    r'\S+'
)

def get_platform(url: str) -> str:
    if 'youtu' in url:
        return '🎬 YouTube'
    elif 'tiktok' in url:
        return '🎵 TikTok'
    elif 'instagram' in url:
        return '📸 Instagram'
    elif 'twitter' in url or 'x.com' in url or 't.co' in url:
        return '🐦 X (Twitter)'
    return '🌐 Видео'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я скачиваю видео из:\n\n"
        "🎬 YouTube\n"
        "🎵 TikTok\n"
        "📸 Instagram\n"
        "🐦 X (Twitter)\n\n"
        "Просто отправь ссылку — и готово!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text("Отправь мне ссылку на видео 👆")
        return

    url = match.group()
    platform = get_platform(url)
    status_msg = await update.message.reply_text(f"{platform}\n⏳ Обрабатываю...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, '%(title).60s.%(ext)s')

            # 🎯 Максимально совместимые настройки для YouTube
            ydl_opts = {
                'outtmpl': output_template,
                'format': 'best[ext=mp4][height<=720]/best[height<=480]/best',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'socket_timeout': 40,
                'retries': 5,
                'fragment_retries': 5,
                'skip_unavailable_fragments': True,
                'no_playlist': True,  # не качать плейлисты целиком
                'extractor_args': {
                    'youtube': {
                        'player_client': 'web',  # только web-клиент (работает с куками)
                        'player_skip': ['webpage']  # ускоряет получение данных
                    }
                }
            }

            # 🔑 Куки — только если файл есть
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
                logger.info("Using cookies.txt")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            # Ищем скачанный файл
            files = [f for f in os.listdir(tmpdir) 
                    if not f.endswith('.part') and f.endswith(('.mp4', '.mkv', '.webm', '.m4a'))]
            if not files:
                raise Exception("Файл не найден после загрузки")

            filepath = os.path.join(tmpdir, files[0])
            title = info.get('title', 'Видео')[:60]
            duration = info.get('duration', 0)
            filesize = os.path.getsize(filepath)

            if filesize > 50 * 1024 * 1024:
                await status_msg.edit_text(
                    f"❌ Файл слишком большой ({filesize/1024/1024:.0f}MB)\n"
                    f"Telegram принимает до 50MB"
                )
                return

            await status_msg.edit_text(f"{platform}\n📤 Отправляю...")

            with open(filepath, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"{platform} · {title}",
                    duration=duration,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )

            await status_msg.delete()

    except Exception as e:
        err = str(e)
        logger.error(f"Error: {e}", exc_info=True)
        
        if 'n challenge' in err or 'JavaScript runtime' in err:
            await status_msg.edit_text("❌ YouTube требует Node.js для расшифровки.\n✅ Добавь 'nodejs' в файл Aptfile на GitHub")
        elif 'Sign in' in err or 'confirm you' in err:
            await status_msg.edit_text("❌ YouTube требует авторизацию.\n✅ Обнови cookies.txt (куки живут ~7 дней)")
        elif 'ffmpeg' in err.lower() or 'merge' in err.lower():
            await status_msg.edit_text("❌ Не установлен ffmpeg.\n✅ Добавь 'ffmpeg' в Aptfile")
        elif 'format is not available' in err or 'Only images' in err:
            await status_msg.edit_text("❌ Видео защищено или недоступно в твоём регионе.\n💡 Попробуй другую ссылку.")
        elif 'Conflict' in err:
            await status_msg.edit_text("❌ Бот запущен в двух местах.\n✅ Останови локальную копию, оставь только Railway")
        elif '403' in err or 'Forbidden' in err:
            await status_msg.edit_text("❌ Видео заблокировано автором")
        else:
            await status_msg.edit_text(f"❌ Ошибка:\n{err[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
