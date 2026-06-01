import os
import re
import asyncio
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
    status_msg = await update.message.reply_text(f"{platform}\n⏳ Скачиваю...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, '%(title).60s.%(ext)s')

            ydl_opts = {
                'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
                'outtmpl': output_path,
                'merge_output_format': 'mp4',
                'quiet': True,
                'cookiefile': 'cookies.txt',
                'no_warnings': True,
                'max_filesize': 50 * 1024 * 1024,  # 50MB лимит Telegram
            }

            # Для Instagram и X иногда нужен другой подход
            if 'instagram' in url:
                ydl_opts['format'] = 'best[ext=mp4]/best'
            elif 'twitter' in url or 'x.com' in url:
                ydl_opts['format'] = 'best[ext=mp4]/best'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Видео')[:60]
                duration = info.get('duration', 0)

                # Найти скачанный файл
                files = os.listdir(tmpdir)
                if not files:
                    raise Exception("Файл не найден после загрузки")

                filepath = os.path.join(tmpdir, files[0])
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

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if '403' in err or 'Forbidden' in err:
            await status_msg.edit_text("❌ Видео недоступно для скачивания (приватное или заблокировано)")
        elif 'too large' in err.lower() or 'filesize' in err.lower():
            await status_msg.edit_text("❌ Файл слишком большой для Telegram (лимит 50MB)")
        else:
            await status_msg.edit_text(f"❌ Ошибка загрузки:\n{err[:200]}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Что-то пошло не так:\n{str(e)[:200]}")
        logger.error(f"Error: {e}", exc_info=True)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
