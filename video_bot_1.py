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
        "Просто отправь ссылку — и готово!\n"
        "Команда /debug <ссылка> — покажет, что видит бот"
    )

async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /debug <url> — показывает, что доступно для видео"""
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /debug <ссылка>")
        return
    
    url = args[0]
    msg = await update.message.reply_text("🔍 Проверяю...")
    
    try:
        ydl_opts = {
            'quiet': True,
            'nocheckcertificate': True,
            'skip_download': True,
            'extractor_args': {'youtube': {'player_client': ['tv', 'android']}}
        }
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        formats = info.get('formats', [])
        # Показываем только комбинированные (видео+аудио) форматы
        combined = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
        
        if combined:
            best = sorted(combined, key=lambda x: x.get('height', 0), reverse=True)[0]
            response = (
                f"✅ Найдено форматов: {len(combined)}\n"
                f"🎯 Лучший: {best.get('format_id')} · "
                f"{best.get('height', '?')}p · "
                f"{best.get('ext', '?')} · "
                f"{best.get('filesize', 0) // 1024 // 1024}MB"
            )
        else:
            response = "⚠️ Нет комбинированных форматов. Бот попробует склеить видео+аудио через ffmpeg."
        
        await msg.edit_text(f"📋 {info.get('title', 'Видео')[:50]}\n{response}")
        
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
    status_msg = await update.message.reply_text(f"{platform}\n⏳ Обрабатываю...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, '%(title).60s.%(ext)s')

            # 🎯 Максимально простой и надёжный формат
            ydl_opts = {
                'outtmpl': output_template,
                'format': 'bestvideo+bestaudio/best',  # сначала пробуем раздельные, потом готовые
                'merge_output_format': 'mp4',  # результат всегда в MP4
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
                'skip_unavailable_fragments': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv', 'android', 'web']  # пробуем разные клиенты
                    }
                }
            }

            # 🔑 Подключаем куки
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
                logger.info("Using cookies.txt")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            # Ищем скачанный файл
            files = [f for f in os.listdir(tmpdir) if not f.endswith('.part')]
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
        logger.error(f"Download error: {e}", exc_info=True)
        
        if 'Sign in' in err or 'confirm you' in err:
            await status_msg.edit_text("❌ YouTube требует авторизацию.\n✅ Обнови cookies.txt")
        elif 'ffmpeg' in err.lower() or 'merge' in err.lower():
            await status_msg.edit_text("❌ Не установлен ffmpeg на сервере.\n✅ Добавь Aptfile с содержимым 'ffmpeg'")
        elif 'format is not available' in err:
            await status_msg.edit_text("❌ Не удалось подобрать формат.\n💡 Попробуй команду /debug <ссылка>")
        elif '403' in err or 'Forbidden' in err:
            await status_msg.edit_text("❌ Видео заблокировано или приватное")
        elif 'too large' in err.lower():
            await status_msg.edit_text("❌ Файл >50MB — Telegram не пропустит")
        else:
            await status_msg.edit_text(f"❌ Ошибка:\n{err[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_info))  # новая команда
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
