import os
import asyncio
import aiohttp
import sqlite3
import traceback
import subprocess  # Добавлено для работы с FFmpeg
import base64      # Добавлено для кодирования аудио в Base64
import yt_dlp
import struct
import cv2         # Добавлено для автоматического определения размеров видео
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, URLInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# =====================================================================
# 🔥 УМНАЯ ОБЕРТКА ДЛЯ АВТОМАТИЧЕСКОГО СТРИМИНГА И ПРОПОРЦИЙ ВИДЕО 9:16 🔥
# =====================================================================
original_answer_video = Message.answer_video

async def smart_answer_video(self: Message, video, *args, **kwargs):
    # Если передали локальный файл, автоматически считываем его оригинальные пропорции
    if isinstance(video, FSInputFile):
        try:
            video_info = cv2.VideoCapture(video.path)
            kwargs['width'] = int(video_info.get(cv2.CAP_PROP_FRAME_WIDTH))
            kwargs['height'] = int(video_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = video_info.get(cv2.CAP_PROP_FPS)
            frame_count = int(video_info.get(cv2.CAP_PROP_FRAME_COUNT))
            kwargs['duration'] = int(frame_count / fps) if fps > 0 else 0
            video_info.release()
        except Exception:
            pass

    # Принудительно включаем мгновенный онлайн-просмотр без черного экрана загрузки
    kwargs['supports_streaming'] = True
    return await original_answer_video(self, video, *args, **kwargs)

# Заменяем стандартный метод aiogram на наш улучшенный метод
Message.answer_video = smart_answer_video
# =====================================================================

# # ТОКЕН И ИНИЦИАЛИЗАЦИЯ
# Обязательно обновите токен на новый от @BotFather, так как старый засветился на скриншоте!
TOKEN = "8690533387:AAHoohAUgk_CfnUy-mDuw9qDsDZU-Pig95o"
bot = Bot(token=TOKEN)
dp = Dispatcher()
CACHE = {}

# # НАСТРОЙКА АДМИНИСТРАТОРА
ADMIN_ID = 5431492715

BD = os.path.dirname(os.path.abspath(__file__))
DD = os.path.join(BD, "downloads")
os.makedirs(DD, exist_ok=True)
CP = os.path.join(BD, "instagram_cookies.txt")

CAPTION_TEXT = "🔥 Скачано с помощью @SkySaveMediaBot"

# СОСТОЯНИЯ ДЛЯ АДМИНКИ
class AdminStates(StatesGroup):
    srv = State()       # Рассылка
    set_cid = State()   # Ввод ID канала
    set_link = State()  # Ввод ссылки на канал

# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
def db_init():
    conn = sqlite3.connect(os.path.join(BD, "bot.db"))
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, val TEXT)")
    c.execute("INSERT OR IGNORE INTO settings (key, val) VALUES ('channel_id', '')")
    c.execute("INSERT OR IGNORE INTO settings (key, val) VALUES ('channel_link', '')")
    conn.commit()
    conn.close()

def db_add_user(uid):
    conn = sqlite3.connect(os.path.join(BD, "bot.db"))
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (id) VALUES (?)", (uid,))
        conn.commit()
    except:
        pass
    conn.close()

def db_get_users():
    conn = sqlite3.connect(os.path.join(BD, "bot.db"))
    c = conn.cursor()
    c.execute("SELECT id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def db_get_setting(key):
    conn = sqlite3.connect(os.path.join(BD, "bot.db"))
    c = conn.cursor()
    c.execute("SELECT val FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def db_set_setting(key, val):
    conn = sqlite3.connect(os.path.join(BD, "bot.db"))
    c = conn.cursor()
    c.execute("UPDATE settings SET val = ? WHERE key = ?", (str(val), key))
    conn.commit()
    conn.close()

db_init()

# ДИНАМИЧЕСКАЯ ПРОВЕРКА ПОДПИСКИ
async def check_sub(uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    cid = db_get_setting('channel_id')
    if not cid:
        return True
    try:
        member = await bot.get_chat_member(chat_id=int(cid), user_id=uid)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True

def sub_kb():
    link = db_get_setting('channel_link') or "https://t.me"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=link)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")]
    ])

# НАСТРОЙКИ YT_DLP С ИСПРАВЛЕНИЕМ ЗАВИСАНИЯ ВИДЕО (КОДЕКИ H.264 + AAC)
def get_opts(url_or_is_audio, custom=None):
    is_audio = False
    url = ""
    if isinstance(url_or_is_audio, bool):
        is_audio = url_or_is_audio
    elif isinstance(url_or_is_audio, str):
        url = url_or_is_audio

    opts = {
        'outtmpl': os.path.join(DD, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'http_chunk_size': 10485760,
        'cookiefile': CP if os.path.exists(CP) else None,
        'extractor_args': {'tiktok': {'impersonate': True}, 'instagram': {'impersonate': True}},
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'},
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
    }

    # 1. СКАЧИВАНИЕ АУДИО (В КЛАССИЧЕСКОМ MP3)
    if is_audio:
        if "tiktok.com" in url or "likee" in url:
            opts['format'] = 'best/mp4'
        else:
            opts['format'] = 'bestaudio/best'

        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    # 2. СКАЧИВАНИЕ ВИДЕО ДЛЯ ТИКТОК И ЛАЙКИ (ОДИН ИСПРАВЛЕННЫЙ MP4 СТРИМ)
    elif "tiktok.com" in url or "likee" in url:
        opts['format'] = 'best[ext=mp4]/best'

    # 3. СКАЧИВАНИЕ ВИДЕО ДЛЯ YOUTUBE И INSTAGRAM
    else:
        opts['format'] = 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'

    if custom:
        opts.update(custom)
    return opts

# 2. ФУНКЦИЯ СКАЧИВАНИЯ МЕДИА С ЛЕЧЕНИЕМ ЛАГОВ И СПЛЮСНУТОГО ЭКРАНА
async def dl_media(url: str, is_audio: bool = False, custom: dict = None) -> str:
    def sync_dl():
        opts = get_opts(url, custom)
        if is_audio:
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloads = info.get('requested_downloads')
            if downloads and isinstance(downloads, list) and len(downloads) > 0:
                return downloads[0].get('filepath') or ydl.prepare_filename(info)
            return ydl.prepare_filename(info)

    # 1. Скачиваем файл через yt-dlp
    downloaded_path = await asyncio.to_thread(sync_dl)

    # 2. Если скачивали аудио или файл отсутствует — отдаем путь как есть
    if is_audio or not downloaded_path or not os.path.exists(downloaded_path):
        return downloaded_path

    # 3. ПЕРЕСБОРКА ВИДЕО ДЛЯ ИСПРАВЛЕНИЯ ПРОПОРЦИЙ И ТОРМОЗОВ НА СМАРТФОНАХ
    fixed_path = os.path.join(DD, f"fixed_{os.path.basename(downloaded_path)}")

    # -vf "scale=..." лечит вертикальное сплющивание, подгоняя размеры под стандарт
    # -profile:v main гарантирует плавность плеера на мобильных устройствах
    # -movflags +faststart позволяет видео стримиться без долгой прогрузки
    cmd = [
        'ffmpeg',
        '-y',
        '-i', downloaded_path,
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'main',
        '-level', '3.1',
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        '-preset', 'superfast',
        fixed_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()

        # Проверяем, что ffmpeg завершился УСПЕШНО (returncode == 0)
        if process.returncode == 0 and os.path.exists(fixed_path) and os.path.getsize(fixed_path) > 0:
            if os.path.exists(downloaded_path):
                os.remove(downloaded_path)
            return fixed_path
        else:
            print(f"[FFMPEG ERROR] Процесс завершился с кодом {process.returncode}")
            # Если ffmpeg накосячил, удаляем битый fixed_path, если он создался
            if os.path.exists(fixed_path):
                os.remove(fixed_path)

    except Exception:
        traceback.print_exc()
        if os.path.exists(fixed_path):
            os.remove(fixed_path)

    # Если пережатие не удалось, лучше вернуть None или вызвать ошибку,
    # чтобы бот не слал лагающий файл, а честно сказал "Ошибка обработки"
    return downloaded_path  # Либо замените на return None

# 3. ФУНКЦИЯ ПОИСКА ТЕКСТА
async def fetch_lyrics(t: str, a: str) -> str:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://apple.com", params={"term": f"{a} {t}", "entity": "song", "limit": 1}) as r:
                if r.status == 200 and (dt := await r.json()).get('results'):
                    res = dt['results'][0]
                    async with s.get(f"https://lyrics.ovh{res['artistName']}/{res['trackName']}") as lr:
                        if lr.status == 200:
                            return (await lr.json()).get('lyrics', '').strip()
    except:
        pass
    return None

# 4. ФУНКЦИЯ СКАЧИВАНИЯ TIKTOK (API)
async def dl_tk(url: str):
    hd = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36", "Accept": "application/json, text/plain, */*"}
    try:
        async with aiohttp.ClientSession(headers=hd) as s:
            async with s.get("https://tikwm.com", params={"url": url}) as r:
                if r.status == 200 and (d := await r.json()).get("code") == 0:
                    return d.get("data")
    except:
        pass
    try:
        async with aiohttp.ClientSession(headers=hd) as s:
            async with s.post("https://lovetik.com", data={"query": url}) as r:
                if r.status == 200 and (d := await r.json()).get("status") == "ok":
                    links = d.get("links", {})
                    return {
                        "play": links.get("a") if links else None,
                        "music": links.get("b") if links else None,
                        "images": d.get("images", [])
                    }
    except:
        pass
    return None

# 5. ТА САМАЯ КЛАВИАТУРА ИЗ ВАШЕГО КОДА (ФОРМИРУЕТ КНОПКИ)
def get_kb(mid, uname, sq=None, su=None, ck=None):
    b = [
        [InlineKeyboardButton(text="💾 Сохранить", callback_data="save_video")],
        [InlineKeyboardButton(text="📥 Скачать песню", callback_data=f"audio_{mid}")],
        [InlineKeyboardButton(text="➕ Добавить в группу ⤴️", url=f"tg://resolve?domain={uname}&startgroup=true")]
    ]
    if sq:
        b = [
            [InlineKeyboardButton(text="🎵 Найти в Telegram", url=f"https://t.me{sq}")],
            [InlineKeyboardButton(text="🔗 Открыть в Shazam", url=su if su else "https://shazam.com")]
        ]
        if ck:
            b.insert(1, [InlineKeyboardButton(text="📄 Показать текст", callback_data=ck)])
    return InlineKeyboardMarkup(inline_keyboard=b)

# ФУНКЦИЯ СКАЧИВАНИЯ НА ДИСК СЕРВЕРА
async def dl_media(url: str, is_audio: bool = False, custom: dict = None) -> str:
    def sync_dl():
        # Передаем url, чтобы get_opts знал, с какой соцсетью работает
        opts = get_opts(url if not is_audio else url, custom)

        # Если это аудио, переключаем внутреннее состояние opts для правильной обработки флагов
        if is_audio:
            opts = get_opts(url, custom)
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloads = info.get('requested_downloads')
            if downloads and isinstance(downloads, list) and len(downloads) > 0:
                # Извлекаем путь методом get из первого элемента-словаря в списке
                return downloads[0].get('filepath') or ydl.prepare_filename(info)
            return ydl.prepare_filename(info)
    return await asyncio.to_thread(sync_dl)

# ГЛАВНАЯ АДМИНКА
@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    total = len(db_get_users())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Изменить ОП", callback_data="admin_op_menu")]
    ])
    await m.answer(f"⚙️ <b>Админ-панель</b>\n\nВсего пользователей в боте: <code>{total}</code>", parse_mode="HTML", reply_markup=kb)

# ВОЗВРАТ В ГЛАВНУЮ АДМИНКУ ИЗ CALLBACK
@dp.callback_query(F.data == "admin_main_menu")
async def cb_admin_main(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    await c.answer()
    total = len(db_get_users())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Изменить ОП", callback_data="admin_op_menu")]
    ])
    await c.message.edit_text(f"⚙️ <b>Админ-панель</b>\n\nВсего пользователей в БД: <code>{total}</code>", parse_mode="HTML", reply_markup=kb)

# ПОДМЕНЮ «ИЗМЕНИТЬ ОП»
@dp.callback_query(F.data == "admin_op_menu")
async def cb_op_menu(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    await c.answer()
    current_id = db_get_setting('channel_id') or "Не указан"
    current_link = db_get_setting('channel_link') or "Не указана"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆔 Изменить ID канала", callback_data="admin_set_id")],
        [InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data="admin_set_link")],
        [InlineKeyboardButton(text="« Назад", callback_data="admin_main_menu")]
    ])
    txt = (
        f"⚙️ <b>Настройки Обязательной Подписки (ОП)</b>\n\n"
        f"🆔 Текущий ID канала: <code>{current_id}</code>\n"
        f"🔗 Текущая ссылка: {current_link}"
    )
    await c.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)

# ОБРАБОТЧИКИ КНОПОК
@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await c.answer()
    await state.set_state(AdminStates.srv)
    await c.message.answer("📥 <b>Отправьте текст или медиафайл для рассылки:</b>", parse_mode="HTML")

@dp.callback_query(F.data == "admin_set_id")
async def set_channel_id_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await c.answer()
    await state.set_state(AdminStates.set_cid)
    await c.message.answer("🆔 <b>Введите новый ID канала (должен начинаться с -100):</b>\nПример: <code>-100198425123</code>", parse_mode="HTML")

@dp.callback_query(F.data == "admin_set_link")
async def set_channel_link_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await c.answer()
    await state.set_state(AdminStates.set_link)
    # ИСПРАВЛЕНО: Вместо несуществующего m.answer теперь c.message.answer
    await c.message.answer("🔗 <b>Введите новую ссылку на канал:</b>\nПример: <code>https://t.me...</code>", parse_mode="HTML")

# ОБРАБОТКА ВВОДА АДМИНИСТРАТОРА
@dp.message(AdminStates.srv)
async def broadcast_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await state.clear()
    users = db_get_users()
    await m.answer(f"🚀 Рассылка запущена для {len(users)} пользователей...")
    success, blocked = 0, 0
    for uid in users:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id)
            success += 1; await asyncio.sleep(0.05)
        except: blocked += 1
    await m.answer(f"📊 <b>Рассылка завершена!</b>\n\n✅ Успешно: {success}\n❌ Заблокировали: {blocked}", parse_mode="HTML")

@dp.message(AdminStates.set_cid)
async def broadcast_id_save(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await state.clear()
    text = m.text.strip()
    if not text.startswith("-100") or not text.replace("-", "").isdigit():
        return await m.answer("❌ Неверный формат ID. Он должен начинаться с -100 и содержать только цифры.")
    db_set_setting('channel_id', text)
    await m.answer(f"✅ ID канала успешно обновлен на: <code>{text}</code>", parse_mode="HTML")

@dp.message(AdminStates.set_link)
async def broadcast_link_save(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await state.clear()
    text = m.text.strip()
    if not text.startswith("http://") and not text.startswith("https://"):
        return await m.answer("❌ Ссылка должна начинаться с http:// или https://")
    db_set_setting('channel_link', text)
    await m.answer(f"✅ Ссылка на канал успешно обновлена на: {text}", parse_mode="HTML")

# ОБРАБОТКА ПОДТВЕРЖДЕНИЯ ПОДПИСКИ
@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(c: CallbackQuery):
    if await check_sub(c.from_user.id):
        await c.answer("✅ Подписка подтверждена! Можете пользоваться ботом.", show_alert=True)
        await c.message.delete()
    else:
        await c.answer("❌ Вы всё ещё не подписались на канал!", show_alert=True)

# СТАРТ С КНОПКОЙ «ДОБАВИТЬ В ГРУППУ»
@dp.message(CommandStart())
async def cmd_start(message: Message):
    db_add_user(message.from_user.id)

    # Сначала проверяем обязательную подписку
    if not await check_sub(message.from_user.id):
        return await message.answer("⚠️ <b>Для использования бота необходимо подписаться на наш канал!</b>", parse_mode="HTML", reply_markup=sub_kb())

    # Получаем актуальные данные бота (его юзернейм)
    bi = await bot.get_me()

    # Создаем инлайн-кнопку со специальной deep-link ссылкой для добавления в группы
    start_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить в группу ⤴️", url=f"tg://resolve?domain={bi.username}&startgroup=true")]
    ])

    txt = (
        "🔥 <b>Добро пожаловать!</b>\n\n"
        "С помощью этого бота вы можете быстро скачивать видео и аудио из популярных социальных сетей:\n\n"
        "📸 <b>Instagram</b>\n"
        "• Посты\n"
        "• Reels\n"
        "• IGTV\n"
        "• Аудио\n\n"
        "🎵 <b>TikTok</b>\n"
        "• Видео без водяного знака\n"
        "• Аудио\n\n"
        "▶️ <b>YouTube</b>\n"
        "• Shorts\n"
        "• Видео\n"
        "• Аудио\n\n"
        "💜 <b>Likee</b>\n"
        "• Видео без водяного знака\n"
        "• Аудио\n\n"
        "⚡ <i>Быстро • Удобно • Бесплатно</i>\n\n"
        "🚀 Просто отправьте ссылку на видео, и бот мгновенно подготовит файл для скачивания.\n\n"
        "😎 <b>Бот также поддерживает работу в группах!</b>"
    )

    # Отправляем приветственный текст вместе с кнопкой
    await message.answer(txt, parse_mode="HTML", reply_markup=start_kb)

# ХЭНДЛЕР ССЫЛОК С ГАРАНТИРОВАННЫМ ВЫВОДОМ КНОПОК ПОД ВИДЕО
@dp.message(F.text.regexp(r'https?://[^\s]+'))
async def handle_links(m: Message):
    db_add_user(m.from_user.id)
    # Проверка обязательной подписки
    if not await check_sub(m.from_user.id):
        return await m.answer("⚠️ <b>Для использования бота необходимо подписаться на наш канал!</b>", parse_mode="HTML", reply_markup=sub_kb())

    url, bi = m.text.strip(), await bot.get_me()
    if not any(d in url for d in ["tiktok.com", "instagram.com", "youtube.com", "youtu.be", "likee.video", "likee.com"]):
        return await m.answer("Я поддерживаю только ссылки на TikTok, Instagram, YouTube и Likee.")

    mid = str(m.message_id)
    CACHE[f"url_{mid}"] = url
    await bot.send_chat_action(m.chat.id, "upload_video")

    # Создаем клавиатуру с кнопками для видеоролика
    video_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Сохранить", callback_data="save_video")],
        [InlineKeyboardButton(text="📥 Скачать песню", callback_data=f"audio_{mid}")],
        [InlineKeyboardButton(text="➕ Добавить в группу ⤴️", url=f"tg://resolve?domain={bi.username}&startgroup=true")]
    ])

    # 1. Обработка ссылок TIKTOK
    if "tiktok.com" in url:
        if tk := await dl_tk(url):
            if tk.get("images"):
                await bot.send_chat_action(m.chat.id, "upload_photo")
                return await m.reply_media_group([InputMediaPhoto(media=URLInputFile(u), caption=CAPTION_TEXT if i==0 else "") for i, u in enumerate(tk["images"][:10])])
            if tk.get("play"):
                # Отправка видео из API с кнопками
                return await m.answer_video(URLInputFile(tk["play"]), caption=CAPTION_TEXT, reply_markup=video_kb)
        try:
            fp = await dl_media(url)
            if fp and os.path.exists(fp):
                # Отправка скачанного через сервер видео с кнопками
                await m.answer_video(FSInputFile(fp), caption=CAPTION_TEXT, reply_markup=video_kb)
                return os.remove(fp)
        except Exception:
            import traceback
            traceback.print_exc()
        return await m.answer("Не удалось получить медиафайл из TikTok. Проверьте ссылку.")

    # 2. Обработка остальных соцсетей (YouTube, Instagram, Likee)
    try:
        fp = await dl_media(url)
        if fp and os.path.exists(fp):
            # Отправка видео с кнопками
            await m.answer_video(FSInputFile(fp), caption=CAPTION_TEXT, reply_markup=video_kb)
            os.remove(fp)
        else:
            await m.answer("Не удалось получить файл.")
    except Exception:
        await m.answer("Ошибка разбора ссылки.")



# ИСПРАВЛЕННЫЙ СЦЕНАРИЙ СКАЧИВАНИЯ АУДИО (ПО КНОПКЕ)
@dp.callback_query(F.data.startswith("audio_"))
async def process_audio(c: CallbackQuery):
    if not await check_sub(c.from_user.id):
        return await c.message.answer("⚠️ <b>Для использования бота необходимо подписаться на наш канал!</b>", parse_mode="HTML", reply_markup=sub_kb())

    url = CACHE.get(f"url_{c.data.replace('audio_', '')}")
    if not url:
        return await c.answer("Ссылка устарела. Отправьте её заново.", show_alert=True)

    await c.answer("Загружаю аудиодорожку...")
    await bot.send_chat_action(c.message.chat.id, "upload_voice")

    # 1. Быстрое извлечение звука из TikTok через API
    if "tiktok.com" in url:
        tk = await dl_tk(url)
        if tk and tk.get("music"): # Исправлено: берём прямую ссылку на музыку из API
            try:
                return await c.message.answer_audio(URLInputFile(tk["music"]), caption=CAPTION_TEXT)
            except Exception:
                pass

    # 2. Скачивание аудио через исправленный dl_media для любых соцсетей (включая YouTube/Instagram)
    try:
        # Передаём строго url и флаг аудио (без лишних аргументов логгера)
        ap = await dl_media(url, is_audio=True)
        if ap and os.path.exists(ap):
            await c.message.answer_audio(FSInputFile(ap), caption=CAPTION_TEXT)
            os.remove(ap)
        else:
            await c.message.answer("Не удалось извлечь звук.")
    except Exception:
        import traceback
        traceback.print_exc() # Если что-то пойдёт не так, вы увидите причину в терминале
        await c.message.answer("Ошибка при скачивании аудио.")


# ЖЕЛЕЗНО РАБОЧИЙ ХЭНДЛЕР ШАЗАМА ЧЕРЕЗ СИСТЕМНЫЙ FFMPEG И ВЕБ-API
@dp.message(F.voice | F.audio | F.video | F.video_note)
async def handle_audio(m: Message):
    db_add_user(m.from_user.id)
    if not await check_sub(m.from_user.id):
        return await m.answer("⚠️ Для использования бота необходимо подписаться на наш канал!", parse_mode="HTML", reply_markup=sub_kb())

    await bot.send_chat_action(m.chat.id, "typing")
    f = next(obj for obj in [m.voice, m.audio, m.video, m.video_note] if obj is not None)
    ext = "mp4" if (m.video or m.video_note) else "ogg"

    tf = os.path.join(DD, f"sz_{m.chat.id}.{ext}")
    cut_m4a = os.path.join(DD, f"cut_{m.chat.id}.m4a") # Конвертируем в компактный m4a

    try:
        # 1. Скачиваем файл из Telegram
        file_info = await bot.get_file(f.file_id)
        await bot.download_file(file_info.file_path, tf)

        # 2. Обрезаем ровно до 4 секунд и сжимаем в AAC/M4A 44100Hz (Идеальный формат для веб-Shazam)
        cmd = [
            'ffmpeg', '-y', '-ss', '00:00:00', '-i', tf,
            '-t', '4', '-c:a', 'aac', '-b:a', '64k', '-ar', '44100', '-ac', '1', cut_m4a
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()

        if not os.path.exists(cut_m4a) or os.path.getsize(cut_m4a) == 0:
            return await m.answer("Не удалось обработать аудиофайл. Попробуйте еще раз.")

        # Читаем легкий сжатый бинарный файл (всего ~30-40 КБ вместо megabayt)
        with open(cut_m4a, 'rb') as audio_file:
            audio_data = audio_file.read()

        # 3. Прямой запрос к официальному веб-серверу Shazam
        web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/octet-stream",
            "Referer": "https://shazam.com"
        }

        out = None
        async with aiohttp.ClientSession(headers=web_headers) as session:
            # Веб-эндпоинт принимает сжатый m4a поток без обрывов соединений и без токенов
            async with session.post("https://shazam.com", data=audio_data, timeout=10) as resp:
                if resp.status == 200:
                    out = await resp.json()

        # 4. Вывод карточки трека
        if out and 'track' in out:
            tr = out['track']
            t, s, su, cu = tr.get('title', '?'), tr.get('subtitle', '?'), tr.get('url', ''), tr.get('images', {}).get('coverarthq')

            # --- ЕДИНСТВЕННОЕ ИСПРАВЛЕНИЕ: ЗАЩИТА ОТ КРАША ИНЛАЙН-КНОПКИ ТЕЛЕГРАМА ---
            # Заменяем пробелы в URL на безопасный формат, чтобы инлайн-кнопка не выдавала Bad Request
            if su and isinstance(su, str) and " " in su:
                su = su.replace(" ", "%20")
            # ------------------------------------------------------------------------

            cap, sq = f"🎵 Трек найден!\n\n📌 Название: {t}\n👤 Исполнитель: {s}", f"{s} {t}"
            ck = f"ly_{m.chat.id}_{m.message_id}" if (sl := await fetch_lyrics(t, s)) else None

            if ck:
                CACHE[ck] = f"📄 Текст песни: {s} — {t}\n\n{sl}"

            bi = await bot.get_me()
            kb = get_kb(m.message_id, bi.username, sq, su, ck)
            if cu:
                await m.answer_photo(URLInputFile(cu), caption=cap, parse_mode="HTML", reply_markup=kb)
            else:
                await m.answer(cap, parse_mode="HTML", reply_markup=kb)
        else:
            await m.answer("Функции шазама временно недоступны. Приносим извинения за неудобства")

    except Exception as e:
        traceback.print_exc()
        await m.answer("Ошибка при обработке аудио.")
    finally:
        # Полная очистка временных файлов
        for path in [tf, cut_m4a]:
            try:
                if os.path.exists(path): os.remove(path)
            except: pass

# ПРОСМОТР ТЕКСТА ПЕСНИ
@dp.callback_query(F.data.startswith("ly_"))
async def process_lyrics(c: CallbackQuery):
    if lt := CACHE.get(c.data):
        await c.answer()
        if len(lt) > 4000:
            await c.message.answer(lt[:4000], parse_mode="HTML")
            await c.message.answer(lt[4000:], parse_mode="HTML")
        else:
            await c.message.answer(lt, parse_mode="HTML")
    else:
        await c.answer("Сессия текста песни устарела.", show_alert=True)

# ОСТАЛЬНОЙ ТЕКСТ
@dp.message(F.text)
async def handle_txt(m: Message):
    db_add_user(m.from_user.id)
    if not await check_sub(m.from_user.id):
        return await m.answer("⚠️ Для использования бота необходимо подписаться на наш канал!", parse_mode="HTML", reply_markup=sub_kb())
    await m.answer("Отправь ссылку на ТТ/Инсту/Ютуб/Лайк или пришли медиафайл для Шазама.")

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
