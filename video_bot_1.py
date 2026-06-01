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

async def debug_formats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /formats <url> — показывает доступные форматы"""
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /formats <ссылка>")
        return
    url = args[0]
    msg = await update.message.reply_text("🔍 Проверяю доступные форматы...")
    try:
        ydl_opts = {
            'quiet': True,
            'nocheckcertificate': True,
            'skip_download': True,
        }
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = info.get('formats', [])
        lines = []
        for f in fmts[-20:]:  # последние 20
            fid = f.get('format_id','?')
            ext = f.get('ext','?')
            h = f.get('height','?')
            vcodec = f.get('vcodec','none')
            acodec = f.get('acodec','none')
            lines.append(f"{fid}: {ext} {h}p v={vcodec[:8]} a={acodec[:8]}")
        await msg.edit_text("📋 Форматы:\n" + "\n".join(lines[-30:]))
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:300]}")

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

            base_opts = {
                'outtmpl': output_path,
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
            }

            if os.path.exists('cookies.txt'):
                base_opts['cookiefile'] = 'cookies.txt'

            # Сначала смотрим что реально доступно
            with yt_dlp.YoutubeDL({**base_opts, 'skip_download': True}) as ydl:
                info = ydl.extract_info(url, download=False)

            fmts = info.get('formats', [])
            # Берём format_id лучшего доступного формата
            video_fmts = [f for f in fmts if f.get('vcodec','none') != 'none' and f.get('height')]
            audio_fmts = [f for f in fmts if f.get('acodec','none') != 'none' and f.get('vcodec','none') == 'none']
            combined_fmts = [f for f in fmts if f.get('vcodec','none') != 'none' and f.get('acodec','none') != 'none']

            if video_fmts and audio_fmts:
                best_v = sorted(video_fmts, key=lambda x: x.get('height',0), reverse=True)[0]
                best_a = sorted(audio_fmts, key=lambda x: x.get('abr',0) or 0, reverse=True)[0]
                chosen_format = f"{best_v['format_id']}+{best_a['format_id']}"
            elif combined_fmts:
                best = sorted(combined_fmts, key=lambda x: x.get('height',0), reverse=True)[0]
                chosen_format = best['format_id']
            elif fmts:
                chosen_format = fmts[-1]['format_id']
            else:
                raise Exception("Нет доступных форматов")

            logger.info(f"Chosen format: {chosen_format}")

            download_opts = {**base_opts, 'format': chosen_format}
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

            title = info.get('title', 'Видео')[:60]
            duration = info.get('duration', 0)

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

    except Exception as e:
        err = str(e)
        if 'Sign in' in err:
            await status_msg.edit_text("❌ YouTube требует авторизацию — обнови cookies.txt")
        elif '403' in err or 'Forbidden' in err:
            await status_msg.edit_text("❌ Видео заблокировано или приватное")
        elif 'too large' in err.lower():
            await status_msg.edit_text("❌ Файл слишком большой для Telegram (лимит 50MB)")
        else:
            await status_msg.edit_text(f"❌ Ошибка загрузки:\n{err[:300]}")
        logger.error(f"Error: {e}", exc_info=True)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("formats", debug_formats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
