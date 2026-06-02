import os
import re
import tempfile
import logging
import requests
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

def get_platform(url):
    if 'youtu' in url:      return '🎬 YouTube'
    if 'tiktok' in url:     return '🎵 TikTok'
    if 'instagram' in url:  return '📸 Instagram'
    if 'twitter' in url or 'x.com' in url or 't.co' in url: return '🐦 X (Twitter)'
    return '🌐 Видео'

def upload_to_gofile(filepath):
    server_resp = requests.get('https://api.gofile.io/servers', timeout=10).json()
    server = server_resp['data']['servers'][0]['name']
    with open(filepath, 'rb') as f:
        resp = requests.post(
            f'https://{server}.gofile.io/contents/uploadfile',
            files={'file': f},
            timeout=300
        ).json()
    if resp.get('status') == 'ok':
        return resp['data']['downloadPage']
    raise Exception(f"Gofile error: {resp}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я скачиваю видео из:\n\n"
        "🎬 YouTube + Shorts\n"
        "🎵 TikTok\n"
        "📸 Instagram\n"
        "🐦 X (Twitter)\n\n"
        "Просто отправь ссылку — и готово!\n\n"
        "📌 До 50MB — прямо в чат\n"
        "📎 Больше 50MB — ссылка для скачивания"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = URL_PATTERN.search(text)
    if not match:
        await update.message.reply_text("Отправь мне ссылку на видео 👆")
        return

    url = match.group()
    platform = get_platform(url)
    is_shorts = 'shorts' in url.lower()
    status_msg = await update.message.reply_text(f"{platform}\n⏳ Скачиваю...")
    cookies = 'cookies.txt' if os.path.exists('cookies.txt') else None

    # Для Shorts пробуем разные клиенты по очереди
    client_attempts = [['tv_embedded'], ['android'], ['web']] if is_shorts else [['web'], ['android']]

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            outtmpl = os.path.join(tmpdir, '%(title).60s.%(ext)s')
            info = None
            downloaded = False

            for clients in client_attempts:
                for f in os.listdir(tmpdir):
                    try: os.remove(os.path.join(tmpdir, f))
                    except: pass

                ydl_opts = {
                    'outtmpl': outtmpl,
                    'format': 'best[ext=mp4][height<=720]/best[height<=720]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                    'quiet': True,
                    'no_warnings': True,
                    'nocheckcertificate': True,
                    'socket_timeout': 60,
                    'retries': 3,
                    'no_playlist': True,
                    'extractor_args': {'youtube': {'player_client': clients}},
                }
                if cookies:
                    ydl_opts['cookiefile'] = cookies

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                    downloaded = True
                    logger.info(f"Downloaded with clients {clients}")
                    break
                except Exception as e:
                    logger.warning(f"Clients {clients} failed: {e}")
                    continue

            if not downloaded or not info:
                raise Exception("Не удалось скачать ни одним способом")

            files = [f for f in os.listdir(tmpdir) if not f.endswith('.part')]
            if not files:
                raise Exception("Файл не найден после загрузки")

            filepath = os.path.join(tmpdir, files[0])
            title    = info.get('title', 'Видео')[:60]
            duration = info.get('duration', 0)
            filesize = os.path.getsize(filepath)

            if filesize <= 50 * 1024 * 1024:
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
            else:
                await status_msg.edit_text(f"{platform}\n☁️ Загружаю на хостинг ({filesize/1024/1024:.0f}MB)...")
                download_url = upload_to_gofile(filepath)
                await status_msg.edit_text(
                    f"{platform} · {title}\n\n"
                    f"📥 Ссылка для скачивания:\n{download_url}\n\n"
                    f"⚠️ Ссылка действует ~10 дней"
                )

    except Exception as e:
        err = str(e)
        logger.error(f"Error: {e}", exc_info=True)
        if 'Sign in' in err or 'confirm you' in err:
            await status_msg.edit_text("❌ Видео недоступно — возможно оно приватное или с возрастным ограничением.")
        elif 'format is not available' in err:
            await status_msg.edit_text("❌ Формат недоступен. Попробуй другое видео.")
        elif 'Conflict' in err:
            await status_msg.edit_text("❌ Бот запущен в двух местах одновременно.")
        elif 'Gofile' in err:
            await status_msg.edit_text("❌ Ошибка загрузки на хостинг. Попробуй позже.")
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
