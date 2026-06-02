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

MAX_VIDEO_SIZE  = 50  * 1024 * 1024   # 50MB  — шлём как видео
MAX_DOC_SIZE    = 1500 * 1024 * 1024  # 1.5GB — шлём как документ
MAX_DL_SIZE     = 1500 * 1024 * 1024  # не скачиваем больше 1.5GB

URL_PATTERN = re.compile(
    r'https?://'
    r'(?:www\.)?'
    r'(?:youtube\.com/|youtu\.be/|'
    r'tiktok\.com/|vm\.tiktok\.com/|'
    r'instagram\.com/|'
    r'twitter\.com/|x\.com/|t\.co/)'
    r'\S+'
)

def get_platform(url):
    if 'youtu' in url:      return '🎬 YouTube'
    if 'tiktok' in url:     return '🎵 TikTok'
    if 'instagram' in url:  return '📸 Instagram'
    if 'twitter' in url or 'x.com' in url or 't.co' in url: return '🐦 X (Twitter)'
    return '🌐 Видео'

def make_opts(output_template, fmt, cookies=None):
    opts = {
        'outtmpl': output_template,
        'format': fmt,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 60,
        'retries': 3,
        'fragment_retries': 3,
        'skip_unavailable_fragments': True,
        'no_playlist': True,
        'max_filesize': MAX_DL_SIZE,
        'extractor_args': {'youtube': {'player_client': 'web'}},
    }
    if cookies:
        opts['cookiefile'] = cookies
    return opts

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
    cookies = 'cookies.txt' if os.path.exists('cookies.txt') else None

    # Лесенка качества: пробуем от лучшего к худшему
    format_ladder = [
        'best[ext=mp4][height<=720]/best[height<=720]',
        'best[ext=mp4][height<=480]/best[height<=480]',
        'best[ext=mp4][height<=360]/best[height<=360]',
        'worst[ext=mp4]/worst',
    ]

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, '%(title).60s.%(ext)s')
            info = None
            filepath = None

            for fmt in format_ladder:
                for f in os.listdir(tmpdir):
                    try: os.remove(os.path.join(tmpdir, f))
                    except: pass

                try:
                    with yt_dlp.YoutubeDL(make_opts(output_template, fmt, cookies)) as ydl:
                        info = ydl.extract_info(url, download=True)
                except Exception as e:
                    logger.warning(f"Format {fmt} failed: {e}")
                    continue

                files = [f for f in os.listdir(tmpdir) if not f.endswith('.part')]
                if not files:
                    continue

                fp = os.path.join(tmpdir, files[0])
                size = os.path.getsize(fp)
                logger.info(f"Format '{fmt}': {size/1024/1024:.1f}MB")

                filepath = fp  # сохраняем всегда
                if size <= MAX_VIDEO_SIZE:
                    break  # отлично — влезает как видео

            if not filepath or not info:
                await status_msg.edit_text("❌ Не удалось скачать видео 😔")
                return

            title    = info.get('title', 'Видео')[:60]
            duration = info.get('duration', 0)
            filesize = os.path.getsize(filepath)

            if filesize > MAX_DOC_SIZE:
                await status_msg.edit_text(
                    f"❌ Видео слишком большое ({filesize/1024/1024:.0f}MB)\n"
                    "Попробуй более короткое видео 😔"
                )
                return

            await status_msg.edit_text(f"{platform}\n📤 Отправляю...")

            with open(filepath, 'rb') as f:
                if filesize <= MAX_VIDEO_SIZE:
                    await update.message.reply_video(
                        video=f,
                        caption=f"{platform} · {title}",
                        duration=duration,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                    )
                else:
                    size_mb = filesize / 1024 / 1024
                    await update.message.reply_document(
                        document=f,
                        caption=f"{platform} · {title}\n📎 Файл {size_mb:.0f}MB — скачай и открой",
                        read_timeout=600,
                        write_timeout=600,
                    )

            await status_msg.delete()

    except Exception as e:
        err = str(e)
        logger.error(f"Error: {e}", exc_info=True)
        if 'Sign in' in err or 'confirm you' in err:
            await status_msg.edit_text("❌ YouTube требует авторизацию.\nПопробуй другое видео.")
        elif 'format is not available' in err:
            await status_msg.edit_text("❌ Видео недоступно в этом регионе.")
        elif 'Conflict' in err:
            await status_msg.edit_text("❌ Бот запущен в двух местах одновременно.")
        elif 'Entity Too Large' in err or 'Request Entity' in err:
            await status_msg.edit_text("❌ Файл слишком большой даже для документа.\nПопробуй более короткое видео.")
        else:
            await status_msg.edit_text(f"❌ Ошибка:\n{err[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
