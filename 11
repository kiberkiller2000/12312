import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus

# ==========================================
# ⚠️ НАСТРОЙКА ТОКЕНОВ, ID И ИЛЛЮСТРАЦИЙ
# ==========================================
TOKEN = "8686860767:AAF4q_u-OC4YBzcPH-PXP1aqrBY2TzBt8c4"
CHANNEL_ID = "@ScamShieldBase"               # Публичный канал со скамерами (с @)
CHANNEL_URL = "t.me/ScamShieldBase"  # Ссылка для проверки подписки
NOTIFICATIONS_CHAT_ID = -1003896320657       # ID группы уведомлений (для логов и жалоб)
ADMIN_IDS = [728960655, 6565153065]           # ID администраторов через запятую

# 🆔 Полностью настроенные медиа-ресурсы проекта
IMAGE_GUARANTOR = "AgACAgIAAxkBAAMyagYxNFRej4Vj6-LjLhzQe-dsjE4AAvMaaxt3CDBI5VdT2xwXTNEBAAMCAAN4AAM7BA"
IMAGE_SCAM = "AgACAgIAAxkBAAM0agYxOnc4xmApaSfIU_rjhUBXSqcAAvQaaxt3CDBI4qPSu3IldQcBAAMCAAN4AAM7BA"
IMAGE_NOT_FOUND = "AgACAgIAAxkBAAM2agYxPs3sMdC13oakxPOAtGZHtH4AAvUaaxt3CDBIxEYQcNLavAYBAAMCAAN4AAM7BA"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Временное хранилище кулдаунов против спама (User_ID -> Timestamp)
user_cooldowns = {}

# ==========================================
# 💾 БАЗА ДАННЫХ SQLite
# ==========================================
def init_db():
    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scammers (
            clean_target TEXT PRIMARY KEY,
            original_target TEXT,
            proofs TEXT,
            post_url TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guarantors (
            clean_target TEXT PRIMARY KEY,
            original_target TEXT,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

def clean_username(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r'(https?://)?(t\.me/|@)', '', text)
    return text

class FormStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_report_target = State()
    waiting_for_proofs = State()

class AdminStates(StatesGroup):
    waiting_for_guarantor = State()
    waiting_for_broadcast_content = State()
    waiting_for_broadcast_btn = State()

# ==========================================
# 🛑 ПРОВЕРКА ОБЯЗАТЕЛЬНОЙ ПОДПИСКИ
# ==========================================
async def check_subscription(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub_again")]
    ])

# ==========================================
# 🎛️ КНОПКИ И МЕНЮ
# ==========================================
def get_main_menu(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🔍 Проверить человека", callback_data="btn_check")],
        [InlineKeyboardButton(text="✍️ Подать жалобу", callback_data="btn_report")],
        [
            InlineKeyboardButton(text="🛡️ Наши гаранты", callback_data="guarantors_list"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="🛠️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_menu")]
    ])

def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="➕ Добавить гаранта", callback_data="adm_add_guarantor")],
        [InlineKeyboardButton(text="⬅️ Выйти в главное меню", callback_data="back_to_menu")]
    ])

# ==========================================
# 🏛️ ЛОГИКА ПОЛЬЗОВАТЕЛЕЙ
# ==========================================
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    conn.close()

    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}! Добро пожаловать в ScamShield!</b>\n"
        f"----------------------------------------\n\n"
        f"Я помогу тебе не попасться на уловки мошенников в Telegram.\n\n"
        f"🤖 <b>Что я умею делать:</b>\n"
        f"• Быстро проверять людей по их Юзернейму или ID\n"
        f"• Показывать список наших проверенных гарантов\n"
        f"• Принимать жалобы на обманщиков со скриншотами\n\n"
        f"Жми кнопку ниже, чтобы начать проверку перед сделкой! 👇"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu(message.from_user.id))

@dp.callback_query(F.data == "check_sub_again")
async def check_sub_again_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        welcome_text = (
            f"👋 <b>Привет, {callback.from_user.first_name}! Добро пожаловать в ScamShield!</b>\n"
            f"----------------------------------------\n\n"
            f"Я помогу тебе не попасться на уловки мошенников в Telegram.\n\n"
            f"🤖 <b>Что я умею делать:</b>\n"
            f"• Быстро проверять людей по их Юзернейму или ID\n"
            f"• Показывать список наших проверенных гарантов\n"
            f"• Принимать жалобы на обманщиков со скриншотами\n\n"
            f"Жми кнопку ниже, чтобы начать проверку перед сделкой! 👇"
        )
        await callback.message.answer(welcome_text, reply_markup=get_main_menu(callback.from_user.id))
    else:
        await callback.answer("❌ Вы все еще не подписались на канал!", show_alert=True)

# --- КНОПКА №1: ПРОВЕРКА ЧЕЛОВЕКА ---
@dp.callback_query(F.data == "btn_check")
async def btn_check_callback(callback: CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "⚠️ <b>Доступ ограничен!</b>\n\nДля использования проверки подпишитесь на наш официальный канал:",
            reply_markup=get_sub_keyboard()
        )
        return

    await state.set_state(FormStates.waiting_for_search)
    await callback.message.edit_text(
        "🔍 <b>Проверка пользователя</b>\n"
        "----------------------------------------\n\n"
        "Отправь мне <b>Юзернейм</b> (например: @username) или <b>Telegram ID</b> человека:\n\n"
        f"<i>⌛ Жду твоего сообщения...</i>",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@dp.message(FormStates.waiting_for_search)
async def process_search(message: Message, state: FSMContext):
    # Защита от спама (Throttling) — не чаще 1 запроса в 3 секунды для обычных юзеров
    now = asyncio.get_event_loop().time()
    last_time = user_cooldowns.get(message.from_user.id, 0)
    if now - last_time < 3 and message.from_user.id not in ADMIN_IDS:
        await message.answer("⏱ <b>Пожалуйста, подождите немного между запросами.</b>")
        return
    user_cooldowns[message.from_user.id] = now

    raw_target = message.text.strip()
    clean_target = clean_username(raw_target)

    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()

    # 1. Ищем среди гарантов
    cursor.execute("SELECT original_target, description FROM guarantors WHERE clean_target=?", (clean_target,))
    guarantor_result = cursor.fetchone()

    if guarantor_result:
        orig_name, desc = guarantor_result
        conn.close()
        await state.clear()

        guarantor_text = (
            f"✨ 🟢 <b>НАШ ОФИЦИАЛЬНЫЙ ГАРАНТ</b> 🟢 ✨\n"
            f"----------------------------------------\n\n"
            f"👤 <b>Контакты:</b> <code>{orig_name}</code>\n"
            f"ℹ️ <b>О гаранте:</b> {desc}\n\n"
            f"----------------------------------------\n"
            f"✅ <b>Это наш доверенный человек!</b> Ему можно спокойно доверять свои деньги и проводить любые сделки.\n\n"
            f"⚠️ <i>Обязательно сверяй каждую букву в нике!</i>"
        )
        await message.answer_photo(photo=IMAGE_GUARANTOR, caption=guarantor_text, reply_markup=get_back_menu())
        return

    # 2. Ищем среди мошенников
    cursor.execute("SELECT original_target, proofs, post_url FROM scammers WHERE clean_target=?", (clean_target,))
    scam_result = cursor.fetchone()
    conn.close()

    if scam_result:
        original_target, proofs, post_url = scam_result
        scam_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 Посмотреть пруфы в канале", url=post_url)] if post_url else [],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
        ])

        scam_alert = (
            f"🚨 ❌ <b>ОСТОРОЖНО! ЭТО МОШЕННИК!</b> ❌ 🚨\n"
            f"----------------------------------------\n\n"
            f"🚫 <b>Кто это:</b>{original_target}\n"
            f"⚠️ <b>Статус:</b> Мошенник.\n"
            f"📝 <b>Что натворил:</b>\n<i>{proofs}</i>\n\n"
            f"----------------------------------------\n"
            f"🛑 <b>НЕ ИМЕЙТЕ С НИМ ДЕЛ!</b> Ничего ему не отправняйте и сразу кидайте в ЧС."
        )
        await message.answer_photo(photo=IMAGE_SCAM, caption=scam_alert, reply_markup=scam_keyboard)
        await state.clear()
        return

    # 3. Если не найден в базе
    not_found_text = (
        f"⚠️ <b>Этого человека нет в нашей базе</b>\n"
        f"----------------------------------------\n\n"
        f"Пользователь <code>{raw_target}</code> пока не занесен в черные списки.\n\n"
        f"💡 Рекомендуем не доверять человеку на слово и провести сделку через проверенных гарантов."
    )
    await message.answer_photo(photo=IMAGE_NOT_FOUND, caption=not_found_text, reply_markup=get_back_menu())
    await state.clear()

# --- КНОПКА №2: ПОДАТЬ ЖАЛОБУ ---

# Глобальный буфер для сборки альбомов (Media Group) в оперативной памяти
report_media_buffer = {}

@dp.callback_query(F.data == "btn_report")
async def btn_report_callback(callback: CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "⚠️ <b>Доступ ограничен!</b>\n\nДля подачи жалобы подпишитесь на наш официальный канал:",
            reply_markup=get_sub_keyboard()
        )
        return

    await state.set_state(FormStates.waiting_for_report_target)
    await callback.message.edit_text(
        "✍ <b>Подача жалобы (Шаг 1 из 2)</b>\n----------------------------------------\n\n"
        "Отправь мне <b>@username</b> или <b>ID мошенника</b>, на которого хочешь заявить:",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@dp.message(FormStates.waiting_for_report_target)
async def process_report_target(message: Message, state: FSMContext):
    raw_target = message.text.strip()
    clean_target = clean_username(raw_target)

    await state.update_data(scam_target=raw_target, clean_target=clean_target)
    await state.set_state(FormStates.waiting_for_proofs)

    await message.answer(
        "📋 <b>Подача жалобы (Шаг 2 из 2)</b>\n----------------------------------------\n\n"
        "ℹ️ <b>Как правильно отправить доказательства:</b>\n\n"
        "1️⃣ Напишите подробную историю обмана (за что перевели деньги, как забанил и т.д.).\n"
        "2️⃣ Прикрепите скриншоты переписки или чеков оплаты.\n\n"
        "⚠️ <b>ВАЖНО:</b> Текст и все скриншоты нужно отправить <u>одним сообщением</u> (альбомом). Пожалуйста, не присылайте доказательства по одной картинке отдельно.",
        reply_markup=get_back_menu()
    )

async def send_aggregated_report(clean_target: str, scam_target: str):
    """Вспомогательная функция сборки альбома и отправки в чат администрации"""
    await asyncio.sleep(1.5) # Кулдаун накопления пакетов альбома

    data = report_media_buffer.get(clean_target)
    if not data:
        return

    photos = data["photos"]
    proofs_text = data["proofs"]
    user_username = data["username"]
    sender_id = data["sender_id"]

    # Берем первую картинку для отправки в канал при одобрении (если есть)
    main_photo = photos[0] if photos else "no_photo"

    # Зашиваем clean_target и ID главной картинки в callback_data кнопки одобрения
    # Внимание: лимит callback_data в Telegram — 64 байта, поэтому если ID картинки длинный,
    # мы будем использовать укороченную ссылку-маркер, но для надежности передаем clean_target.
    admin_action_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Забанить (В базу)", callback_data=f"approve_claim|{clean_target}"),
            InlineKeyboardButton(text="🗑 Отклонить", callback_data="claim_reject")
        ]
    ])

    notification_text = (
        f"📢 <b>Поступила жалоба на рассмотрение</b>\n"
        f"👤 <b>Отправитель:</b> {user_username} (ID: <code>{sender_id}</code>)\n"
        f"🎯 <b>Подозреваемый:</b> <code>{scam_target}</code>\n\n"
        f"📝 <b>Текст жалобы:</b>\n<i>{proofs_text}</i>"
    )

    try:
        if len(photos) > 1:
            from aiogram.types import InputMediaPhoto
            media_group = [InputMediaPhoto(media=p) for p in photos]
            # Сначала шлем сам медиа-альбом
            await bot.send_media_group(chat_id=NOTIFICATIONS_CHAT_ID, media=media_group)
            # Следом шлем текст разбора ИМЕННО с кнопками управления
            await bot.send_message(chat_id=NOTIFICATIONS_CHAT_ID, text=notification_text, reply_markup=admin_action_keyboard)
        elif len(photos) == 1:
            await bot.send_photo(chat_id=NOTIFICATIONS_CHAT_ID, photo=photos[0], caption=notification_text, reply_markup=admin_action_keyboard)
        else:
            await bot.send_message(chat_id=NOTIFICATIONS_CHAT_ID, text=notification_text, reply_markup=admin_action_keyboard)
    except Exception as e:
        print(f"Ошибка отправки объединенного лога: {e}")

    # Важно: МЫ НЕ УДАЛЯЕМ БУФЕР СРАЗУ, чтобы админ успел нажать кнопку и бот взял оттуда фото!
    # Мы просто помечаем его как отправленный администраторам
    report_media_buffer[clean_target]["ready_to_clear"] = True

@dp.message(FormStates.waiting_for_proofs)
async def process_proofs(message: Message, state: FSMContext):
    user_data = await state.get_data()
    scam_target = user_data.get('scam_target')
    clean_target = user_data.get('clean_target')

    current_text = message.caption if message.caption else message.text
    photo_id = message.photo[-1].file_id if message.photo else None
    user_username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"

    if clean_target not in report_media_buffer:
        report_media_buffer[clean_target] = {
            "photos": [],
            "proofs": "Без текстового описания",
            "username": user_username,
            "sender_id": message.from_user.id,
            "task_started": False,
            "ready_to_clear": False
        }

    if photo_id:
        report_media_buffer[clean_target]["photos"].append(photo_id)
    if current_text and current_text != "Без текстового описания":
        report_media_buffer[clean_target]["proofs"] = current_text

    if not report_media_buffer[clean_target]["task_started"]:
        report_media_buffer[clean_target]["task_started"] = True

        asyncio.create_task(send_aggregated_report(clean_target, scam_target))

        await message.answer(
            "📥 <b>Ваши доказательства успешно приняты и отправлены модераторам!</b>\n\n"
            "Администрация проекта проверит информацию в ближайшее время. Спасибо за помощь сообществу!",
            reply_markup=get_main_menu(message.from_user.id)
        )
        await state.clear()

# --- КНОПКА №3: СПИСОК ГАРАНТОВ ---
@dp.callback_query(F.data == "guarantors_list")
async def guarantors_list_callback(callback: CallbackQuery):
    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("SELECT original_target, description FROM guarantors")
    rows = cursor.fetchall()
    conn.close()

    if rows:
        text = "🛡️ <b>Наши проверенные гаранты:</b>\n\nПроводи свои сделки безопасно только через этих людей:\n\n"
        for row in rows:
            text += f"• <b>{row[0]}</b> — {row[1]}\n"
    else:
        text = "🛡️ <b>Наши проверенные гаранты:</b>\n\nСписок временно пуст. Скоро добавятся контакты гарантов."

    await callback.message.edit_text(text, reply_markup=get_back_menu())
    await callback.answer()

# --- КНОПКА №4: СТАТИСТИКА БОТА ---
@dp.callback_query(F.data == "stats")
async def stats_callback(callback: CallbackQuery):
    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammers_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM guarantors")
    guarantors_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    conn.close()

    stat_text = (
        f"📊 <b>Статистика нашего проекта:</b>\n"
        f"----------------------------------------\n\n"
        f"🚫 Всего поймано мошенников: <b>{scammers_count}</b> шт.\n"
        f"🛡️ Доверенных гарантов в списке: <b>{guarantors_count}</b> чел.\n"
        f"👥 Пользователей в системе: <b>{users_count}</b> чел.\n\n"
        f"База обновляется админами каждый день!"
    )
    await callback.message.edit_text(stat_text, reply_markup=get_back_menu())
    await callback.answer()

# --- ОБЩИЙ НАВИГАЦИОННЫЙ ХЭНДЛЕР НАЗАД ---
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    welcome_text = (
        f"👋 <b>Привет, {callback.from_user.first_name}! Добро пожаловать в ScamShield!</b>\n"
        f"----------------------------------------\n\n"
        f"Я помогу тебе не попасться на уловки мошенников в Telegram.\n\n"
        f"🤖 <b>Выберите нужное действие на панели ниже:</b>"
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(text=welcome_text, reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()

# ==========================================
# 🛠️ ИНТЕРФЕЙС АДМИНИСТРАТОРА И КНОПКИ ЖАЛОБ
# ==========================================
@dp.callback_query(F.data.startswith("approve_claim"))
async def admin_inline_approve(callback: CallbackQuery):
    """Автоматическое одобрение жалобы админом из чата уведомлений с публикацией всего альбома"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав.", show_alert=True)
        return

    # Извлекаем clean_target из callback_data кнопки
    clean_target = callback.data.split("|")[1]
    proofs = callback.message.text if callback.message.text else callback.message.caption

    # Извлекаем все фотографии из нашего оперативного буфера
    cached_photos = []
    if clean_target in report_media_buffer:
        cached_photos = report_media_buffer[clean_target].get("photos", [])

    # Если бота перезагружали и буфер пуст, пробуем взять фото из текущего сообщения модерации
    if not cached_photos and callback.message.photo:
        cached_photos = [callback.message.photo[-1].file_id]

    lines = proofs.split("\n")
    orig_target = f"@{clean_target}"
    sender_id = None
    extracted_proofs = "Суть обмана не указана."

    capture_proofs = False
    proofs_lines = []

    for line in lines:
        if "Подозреваемый:" in line:
            orig_target = line.replace("Подозреваемый:", "").strip()
        if "Отправитель:" in line and "ID:" in line:
            try:
                sender_id = int(re.search(r"ID:\s*(\d+)", line).group(1))
            except Exception:
                pass

        if capture_proofs:
            proofs_lines.append(line)
        if "Текст жалобы:" in line:
            capture_proofs = True

    if proofs_lines:
        extracted_proofs = "\n".join(proofs_lines).strip()
    else:
        extracted_proofs = proofs

    channel_post = (
        f"🚨 🛑 <b>ВНИМАНИЕ! ЗАФИКСИРОВАН МОШЕННИК!</b> 🛑 🚨\n"
        f"----------------------------------------\n\n"
        f"🚫 <b>Контакты скамера:</b>{orig_target}\n"
        f"📝 <b>Суть обмана и пруфы:</b>\n<i>{extracted_proofs}</i>\n\n"
        f"----------------------------------------\n"
        f"🛡️ <i>Проверяйте людей перед сделками в боте: @{(await bot.get_me()).username}</i>"
    )

    try:
        # Если в жалобе было несколько фотографий, формируем и отправляем альбом (Media Group)
        if len(cached_photos) > 1:
            from aiogram.types import InputMediaPhoto
            # Создаем структуру медиа-группы. Текст-подпись (caption) прикрепляем строго к ПЕРВОМУ файлу группы
            media_group = []
            for i, photo_id in enumerate(cached_photos):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_id, caption=channel_post))
                else:
                    media_group.append(InputMediaPhoto(media=photo_id))

            await bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)

            # Для сохранения ссылки на пост берем условный переход в канал (точные ID альбомов через API не возвращаются)
            post_url = f"t.me/{CHANNEL_ID.replace('@', '')}"

        elif len(cached_photos) == 1:
            # Если картинка всего одна — шлем её стандартным одиночным методом
            sent_msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=cached_photos[0], caption=channel_post)
            post_url = f"t.me/{CHANNEL_ID.replace('@', '')}/{sent_msg.message_id}"
        else:
            # Если картинок вообще не было (только текст)
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=channel_post)
            post_url = f"t.me/{CHANNEL_ID.replace('@', '')}/{sent_msg.message_id}"

        # Запись в локальную базу данных
        conn = sqlite3.connect("scamshield.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO scammers (clean_target, original_target, proofs, post_url) VALUES (?, ?, ?, ?)",
                       (clean_target, orig_target, extracted_proofs, post_url))
        conn.commit()
        conn.close()

        # Личное уведомление пользователя
        if sender_id:
            try:
                await bot.send_message(
                    chat_id=sender_id,
                    text=f"✅ <b>Ваша жалоба на пользователя {orig_target} была успешно принята!</b>\n\n"
                         f"Нарушитель занесен в черные списки, а все присланные скриншоты опубликованы в канале."
                )
            except Exception:
                pass

        success_msg = f"✅ <b>Жалоба одобрена! Все доказательства успешно опубликован в канале, пользователь уведомлен.</b>"
        if callback.message.photo:
            await callback.message.edit_caption(caption=success_msg)
        else:
            await callback.message.edit_text(text=success_msg)


        # Полностью очищаем оперативную ячейку из буфера
        if clean_target in report_media_buffer:
            del report_media_buffer[clean_target]

    except Exception as e:
        await callback.answer(f"Ошибка публикации альбома: {e}", show_alert=True)

# --- АДМИНКА: ДОБАВИТЬ ГАРАНТА ---
@dp.callback_query(F.data == "adm_add_guarantor")
async def adm_add_guarantor_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_guarantor)
    await callback.message.edit_text(
        "🛠 <b>Добавление гаранта</b>\n\n"
        "Отправь данные в формате (через пробел после юзернейма):\n"
        "<code>@username Описание гаранта</code>",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_guarantor)
async def process_add_guarantor(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text.strip()
    try:
        target, desc = text.split(maxsplit=1)
        clean_target = clean_username(target)

        conn = sqlite3.connect("scamshield.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO guarantors (clean_target, original_target, description) VALUES (?, ?, ?)",
                       (clean_target, target, desc))
        conn.commit()
        conn.close()

        await message.answer(f"✅ Гарант <b>{target}</b> добавлен!", reply_markup=get_admin_menu())
    except ValueError:
        await message.answer("❌ Формат неверный.")
    await state.clear()

# --- АДМИНКА: МАССОВАЯ УМНАЯ РАССЫЛКА ---
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_broadcast_content)
    await callback.message.edit_text("📢 <b>Режим рассылки</b>\n\nОтправь сообщение для всех юзеров бота (можно текст или фото с описанием):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_broadcast_content)
async def process_broadcast_content(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return

    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    await state.update_data(b_text=text, b_photo=photo_id)
    await state.set_state(AdminStates.waiting_for_broadcast_btn)

    await message.answer(
        "🔗 <b>Добавление кнопки-ссылки (Необязательно)</b>\n\n"
        "Если кнопка нужна, отправь её в формате:\n<code>Текст кнопки | https://ссылка</code>\n\n"
        "Если кнопка не нужна, отправь цифру <code>0</code>"
    )

@dp.message(AdminStates.waiting_for_broadcast_btn)
async def process_broadcast_btn(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    btn_text = message.text.strip()

    data = await state.get_data()
    b_text = data.get("b_text")
    b_photo = data.get("b_photo")
    await state.clear()

    reply_markup = None
    if btn_text != "0" and "|" in btn_text:
        try:
            b_name, b_url = btn_text.split("|")
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_name.strip(), url=b_url.strip())]])
        except Exception:
            pass

    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    users = cursor.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    await message.answer(f"⏳ Рассылаю...")
    success = 0
    for user in users:
        try:
            if b_photo:
                await bot.send_photo(chat_id=user[0], photo=b_photo, caption=b_text, reply_markup=reply_markup)
            else:
                await bot.send_message(chat_id=user[0], text=b_text, reply_markup=reply_markup)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"📢 Завершено! Доставлено: {success} / {len(users)}", reply_markup=get_admin_menu())

# ==========================================
# 🛠️ ИНТЕРФЕЙС АДМИНИСТРАТОРА И КНОПКИ ЖАЛОБ
# ==========================================
@dp.callback_query(F.data.style("claim_approve"))
async def admin_inline_approve(callback: CallbackQuery):
    """Автоматическое одобрение жалобы админом из чата уведомлений"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав.", show_alert=True)
        return

    clean_target = callback.data.split("|")[1]
    proofs = callback.message.caption if callback.message.photo else callback.message.text

    # Извлекаем оригинальный юзернейм/ID из текста жалобы
    lines = proofs.split("\n")
    orig_target = f"@{clean_target}"
    for line in lines:
        if "Подозреваемый:" in line:
            orig_target = line.replace("Подозреваемый:", "").strip()

    channel_post = (
        f"🚨 🛑 <b>ВНИМАНИЕ! ЗАФИКСИРОВАН МОШЕННИК!</b> 🛑 🚨\n"
        f"----------------------------------------\n\n"
        f"🚫 <b>Контакты скамера:</b> <code>{orig_target}</code>\n\n"
        f"📝 <b>Суть обмана и пруфы:</b>\n<i>Жалоба подтверждена администрацией.</i>\n\n"
        f"----------------------------------------\n"
        f"🛡️ <i>Проверяйте людей перед сделками в боте: @{(await bot.get_me()).username}</i>"
    )

    try:
        if callback.message.photo:
            sent_msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=callback.message.photo[-1].file_id, caption=channel_post)
        else:
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=channel_post)

        channel_username = CHANNEL_ID.replace("@", "")
        post_url = f"t.me/{channel_username}/{sent_msg.message_id}"

        conn = sqlite3.connect("scamshield.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO scammers (clean_target, original_target, proofs, post_url) VALUES (?, ?, ?, ?)",
                       (clean_target, orig_target, "Подтвержденный скам (проверено администрацией)", post_url))
        conn.commit()
        conn.close()

        success_msg = f"✅ <b>Жалоба №{callback.message.message_id} одобрена! Данные внесены в базу и канал.</b>"
        if callback.message.photo:
            await callback.message.edit_caption(caption=success_msg)
        else:
            await callback.message.edit_text(text=success_msg)

    except Exception as e:
        await callback.answer(f"Ошибка публикации: {e}", show_alert=True)

@dp.callback_query(F.data == "claim_reject")
async def admin_inline_reject(callback: CallbackQuery):
    """Отклонение жалобы из чата уведомлений"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Жалоба отклонена и удалена.", show_alert=True)

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    admin_text = (
        "🛠️ <b>Панель администратора ScamShield</b>\n"
        "----------------------------------------\n\n"
        "⚙️ <b>Команды быстрого добавления в ЛС/чатах:</b>\n"
        "• <code>/add_scam @юзернейм Текст пруфов</code> — Добавить мошенника\n"
        "• <code>/del @юзернейм</code> — Удалить из базы\n\n"
        "Используйте кнопки меню для управления функциями:"
    )

    try:
        await callback.message.edit_text(text=admin_text, reply_markup=get_admin_menu())
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text=admin_text, reply_markup=get_admin_menu())
    await callback.answer()

# --- АДМИНКА: ДОБАВИТЬ ГАРАНТА ---
@dp.callback_query(F.data == "adm_add_guarantor")
async def adm_add_guarantor_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_guarantor)
    await callback.message.edit_text(
        "🛠 <b>Добавление гаранта</b>\n\n"
        "Отправь данные в формате (через пробел после юзернейма):\n"
        "<code>@username Описание гаранта</code>",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_guarantor)
async def process_add_guarantor(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text.strip()
    try:
        target, desc = text.split(maxsplit=1)
        clean_target = clean_username(target)

        conn = sqlite3.connect("scamshield.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO guarantors (clean_target, original_target, description) VALUES (?, ?, ?)",
                       (clean_target, target, desc))
        conn.commit()
        conn.close()

        await message.answer(f"✅ Гарант <b>{target}</b> добавлен!", reply_markup=get_admin_menu())
    except ValueError:
        await message.answer("❌ Формат неверный.")
    await state.clear()

# --- АДМИНКА: УМНАЯ РАССЫЛКА (МЕДИА + КНОПКИ) ---
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_broadcast_content)
    await callback.message.edit_text("📢 <b>Режим рассылки</b>\n\nОтправь сообщение (можно текст, картинку с текстом или ссылки):")
    await callback.answer()

@dp.message(AdminStates.waiting_for_broadcast_content)
async def process_broadcast_content(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return

    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    await state.update_data(b_text=text, b_photo=photo_id)
    await state.set_state(AdminStates.waiting_for_broadcast_btn)

    await message.answer(
        "🔗 <b>Добавление кнопки-ссылки</b>\n\n"
        "Отправь данные в формате:\n<code>Текст кнопки | https://ссылка</code>\n\n"
        "Если кнопка не нужна, отправь цифру <code>0</code>"
    )

@dp.message(AdminStates.waiting_for_broadcast_btn)
async def process_broadcast_btn(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    btn_text = message.text.strip()

    data = await state.get_data()
    b_text = data.get("b_text")
    b_photo = data.get("b_photo")
    await state.clear()

    reply_markup = None
    if btn_text != "0" and "|" in btn_text:
        try:
            b_name, b_url = btn_text.split("|", 1)
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_name.strip(), url=b_url.strip())]])
        except Exception:
            pass

    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    status_msg = await message.answer(f"⏳ Рассылаю...")
    success = 0

    for user in users:
        try:
            if b_photo:
                await bot.send_photo(chat_id=user[0], photo=b_photo, caption=b_text, reply_markup=reply_markup)
            else:
                await bot.send_message(chat_id=user[0], text=b_text, reply_markup=reply_markup)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await status_msg.delete()
    await message.answer(f"📢 Завершено! Доставлено: {success} / {len(users)}", reply_markup=get_admin_menu())

# --- ТЕКСТОВЫЕ АДМИН-КОМАНДЫ ---
@dp.message(Command("add_scam"))
async def add_scam_manually_cmd(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    command_text = message.caption if message.photo else message.text

    try:
        command_body = command_text.replace("/add_scam", "").strip()
        target, proofs = command_body.split(maxsplit=1)
        clean_target = clean_username(target)
        photo_id = message.photo[-1].file_id if message.photo else None

        channel_post = (
            f"🚨 🛑 <b>ВНИМАНИЕ! ЗАФИКСИРОВАН МОШЕННИК!</b> 🛑 🚨\n"
            f"----------------------------------------\n\n"
            f"🚫 <b>Контакты скамера:</b> <code>{target}</code>\n\n"
            f"📝 <b>Суть обмана и пруфы:</b>\n<i>{proofs}</i>\n\n"
            f"----------------------------------------\n"
            f"🛡️ <i>Проверяйте людей перед сделками в боте: @{(await bot.get_me()).username}</i>"
        )

        if photo_id:
            sent_msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=channel_post)
        else:
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=channel_post)

        channel_username = CHANNEL_ID.replace("@", "")
        post_url = f"t.me/{channel_username}/{sent_msg.message_id}"

        conn = sqlite3.connect("scamshield.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO scammers (clean_target, original_target, proofs, post_url) VALUES (?, ?, ?, ?)",
                       (clean_target, target, proofs, post_url))
        conn.commit()
        conn.close()

        await message.answer(f"✅ <b>Успешно!</b> Мошенник {target} внесен в базу, пост опубликован.")
    except (ValueError, IndexError):
        await message.answer("❌ <b>Неверный формат!</b> Шаблон:\n<code>/add_scam @username Текст пруфов</code>")

@dp.message(Command("del"))
async def delete_target_cmd(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Напишите: <code>/del @username</code>")
        return

    target_raw = args[1].strip()
    clean_target = clean_username(target_raw)

    conn = sqlite3.connect("scamshield.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scammers WHERE clean_target=?", (clean_target,))
    s_del = cursor.rowcount
    cursor.execute("DELETE FROM guarantors WHERE clean_target=?", (clean_target,))
    g_del = cursor.rowcount
    conn.commit()
    conn.close()

    if s_del > 0 or g_del > 0:
        await message.answer("✅ Контакт успешно удален из всех баз.")
    else:
        await message.answer("❓ Данный contact не найден.")

# ==========================================
# 🚀 ЗАПУСК БОТА
# ==========================================
async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот ScamShield полностью настроен и готов!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
