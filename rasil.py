import asyncio
import logging
import json
import random
import sqlite3
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BotCommand
from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, UserDeactivated, SessionRevoked

BOT_TOKEN = "8286579469:AAEjC78_pjabE3TxKF89hcAigANVeBw6MrM"
ADMIN_ID = 728960655
DB_FILE = "bot_data.db"
PROJECT_NAME = "Send Pulse"
REQUIRED_CHANNEL = "@send_pulse"
CHANNEL_URL = "https://t.me/send_pulse"

MY_API_ID = 22997803
MY_API_HASH = "15618ba7cd5a5b7e3877ab1d7b235cbe"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

active_tasks = {}
data_total_sent = {}

class Steps(StatesGroup):
    get_post = State()
    get_delay = State()
    get_chat = State()
    get_key = State()
    wait_session = State()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users
                   (user_id INTEGER PRIMARY KEY, expiry TEXT, chats TEXT, post_id TEXT,
                    delay INTEGER DEFAULT 180, session_string TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS keys (key_code TEXT PRIMARY KEY, days INTEGER)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS sent_messages
                   (user_id INTEGER, chat_id TEXT, last_msg_id TEXT, PRIMARY KEY(user_id, chat_id))''')
    conn.commit()
    conn.close()

def db_query(sql, params=(), fetchone=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if not isinstance(params, (list, tuple)): params = (params,)
    cur.execute(sql, params)
    res = None
    if fetchone:
        row = cur.fetchone()
        if row:
            res = row[0] if len(row) == 1 else row
    else:
        conn.commit()
    conn.close()
    return res

def has_active_key(user_id):
    if user_id == ADMIN_ID: return True
    res = db_query("SELECT expiry FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not res or res == "Нет": return False
    try:
        expiry = datetime.strptime(str(res), "%Y-%m-%d %H:%M")
        return expiry > datetime.now()
    except: return False

async def is_subscribed_to_channel(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- ГЛАВНОЕ МЕНЮ ---
async def show_main_menu(uid, target):
    if not await is_subscribed_to_channel(uid):
        txt = (f"🚫 <b>Доступ ограничен!</b>\n\n"
               f"Для использования бота необходимо подписаться на наш канал: {REQUIRED_CHANNEL}\n\n"
               f"Подпишись и нажми кнопку ниже 👇")
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="👉 Подписаться на канал", url=CHANNEL_URL))
        kb.row(types.InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        if isinstance(target, types.Message): await target.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
        else: await target.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
        return

    exists = db_query("SELECT user_id FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not exists:
        db_query("INSERT INTO users (user_id, expiry, chats) VALUES (?, 'Нет', '[]')", (uid,))

    res = db_query("SELECT expiry, chats, post_id, delay, session_string FROM users WHERE user_id = ?", (uid,), fetchone=True)
    expiry, chats_raw, post_id_raw, delay, session = res

    post_exists = False
    if post_id_raw:
        try:
            p_ids = json.loads(str(post_id_raw))
            if p_ids: post_exists = True
        except: post_exists = False

    st_icon = "🟢" if uid in active_tasks else "🔴"
    chats_list = json.loads(str(chats_raw)) if chats_raw else []

    txt = (f"<b>💎 {PROJECT_NAME.upper()} PANEL</b>\n\n"
           f"<b>Статус:</b> {st_icon} {'В РАБОТЕ' if uid in active_tasks else 'ПАУЗА'}\n"
           f"<b>Подписка:</b> <code>{expiry}</code>\n"
           f"<b>Аккаунт:</b> {'✅ Привязан' if session else '❌ Не привязан'}\n"
           f"<b>Пост:</b> {'✅ Загружен' if post_exists else '❌ Не задан'}\n"
           f"<b>Задержка:</b> ⏱ {delay} сек.\n\n"
           f"📊 <b>Чатов в базе:</b> {len(chats_list)}\n"
           f"┗ <b>Всего выслано:</b> {data_total_sent.get(uid, 0)}")

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🖋 Изменить пост", callback_data="set_post"))
    kb.row(types.InlineKeyboardButton(text="📂 Список чатов", callback_data="chats:0"),
           types.InlineKeyboardButton(text="⏱ Таймер", callback_data="delay"))
    acc_btn = "🚫 Отвязать аккаунт" if session else "📱 Привязать аккаунт"
    kb.row(types.InlineKeyboardButton(text=acc_btn, callback_data="confirm_del_acc" if session else "start_binding"))
    kb.row(types.InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key"))
    kb.row(types.InlineKeyboardButton(text="⛔️ ОСТАНОВИТЬ" if uid in active_tasks else "🚀 ЗАПУСТИТЬ", callback_data="toggle"))

    if isinstance(target, types.Message): await target.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
    else: await target.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- ПРИВЯЗКА И ПОСТ ---
@dp.callback_query(F.data == "start_binding")
async def start_binding(call: types.CallbackQuery, state: FSMContext):
    if not has_active_key(call.from_user.id):
        return await call.answer("❌ Сначала активируйте ключ!", show_alert=True)
    await state.set_state(Steps.wait_session)
    txt = ("📋 <b>ИНСТРУКЦИЯ ПО ПРИВЯЗКЕ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
           "1. Напишите администратору: @qqtewp\n"
           "2. Получите строку <b>Session String</b>.\n"
           "3. Введите строку ниже:\n\n"
           "👇 <b>ОЖИДАЮ ВВОДА СТРОКИ СЕССИИ:</b>")
    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="⬅️ ОТМЕНА", callback_data="back")).as_markup())

@dp.message(Steps.wait_session)
async def process_session(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    if len(msg.text) < 50: return await msg.answer("❌ Ошибка: Неверная строка сессии.")
    db_query("UPDATE users SET session_string = ? WHERE user_id = ?", (msg.text.strip(), uid))
    await state.clear(); await msg.answer("✅ <b>Аккаунт привязан!</b>", parse_mode="HTML"); await show_main_menu(uid, msg)

@dp.callback_query(F.data == "set_post")
async def set_post(call: types.CallbackQuery):
    if not has_active_key(call.from_user.id): return await call.answer("❌ Нужен ключ!", show_alert=True)
    txt = ("📝 <b>ИНСТРУКЦИЯ:</b>\n\n"
           "1. Перешли сообщение/альбом в свои <b>Saved Messages</b>.\n"
           "2. Убедись, что это последнее сообщение.\n"
           "3. Нажми ✅ ПЕРЕСЛАЛ.")
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="✅ ПЕРЕСЛАЛ", callback_data="confirm_post"))
    kb.row(types.InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="back"))
    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "confirm_post")
async def confirm_post(call: types.CallbackQuery):
    uid = call.from_user.id
    u_session = db_query("SELECT session_string FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not u_session: return await call.answer("❌ Привяжите аккаунт!", show_alert=True)

    # Фикс ошибки unpack: гарантируем передачу чистой строки сессии
    client = Client(f"gp_{uid}", MY_API_ID, MY_API_HASH, session_string=str(u_session).strip(), in_memory=True)
    try:
        await client.start()
        post_ids = []
        async for m in client.get_chat_history("me", limit=10):
            if not post_ids:
                post_ids.append(m.id); mg_id = m.media_group_id
                if not mg_id: break
            else:
                if m.media_group_id == mg_id: post_ids.append(m.id)
                else: break
        db_query("UPDATE users SET post_id = ? WHERE user_id = ?", (json.dumps(post_ids), uid))
        await call.answer(f"✅ Пост захвачен! ({len(post_ids)} эл.)", show_alert=True)
        await client.stop(); await show_main_menu(uid, call)
    except Exception as e: await call.answer(f"❌ Ошибка сессии: проверьте API_ID/HASH", show_alert=True)

# --- РАССЫЛКА ---
async def mailing_worker(uid):
    u_session = db_query("SELECT session_string FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not u_session: return
    client = Client(f"run_{uid}", MY_API_ID, MY_API_HASH, session_string=str(u_session).strip(), in_memory=True)
    try:
        await client.start()
        while uid in active_tasks:
            if not has_active_key(uid): break
            res = db_query("SELECT chats, post_id, delay FROM users WHERE user_id = ?", (uid,), fetchone=True)
            if not res: break
            chats_raw, post_id_raw, delay = res
            chats = json.loads(str(chats_raw)) if chats_raw else []
            try: p_ids = json.loads(str(post_id_raw)) if post_id_raw else []
            except: p_ids = []

            for chat in chats:
                if uid not in active_tasks: break
                try:
                    old_raw = db_query("SELECT last_msg_id FROM sent_messages WHERE user_id = ? AND chat_id = ?", (uid, str(chat)), fetchone=True)
                    if old_raw:
                        try:
                            old_ids = json.loads(str(old_raw)) if "[" in str(old_raw) else [int(old_raw)]
                            await client.delete_messages(chat, old_ids)
                        except: pass
                    sent = await client.forward_messages(chat, "me", p_ids)
                    new_ids = [m.id for m in sent] if isinstance(sent, list) else [sent.id]
                    db_query("INSERT OR REPLACE INTO sent_messages VALUES (?, ?, ?)", (uid, str(chat), json.dumps(new_ids)))
                    data_total_sent[uid] = data_total_sent.get(uid, 0) + 1
                    await asyncio.sleep(random.randint(5, 10))
                except: pass
            for _ in range(int(delay)):
                if uid not in active_tasks: break
                await asyncio.sleep(1)
    except: pass
    finally:
        try: await client.stop()
        except: pass
        active_tasks.pop(uid, None)

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext = None):
    if state: await state.clear()
    await show_main_menu(msg.from_user.id, msg)

@dp.callback_query(F.data == "activate_key")
async def act_key(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Steps.get_key)
    txt = ("🔑 <b>АКТИВАЦИЯ ДОСТУПА</b>\n\n💳 <b>ПРАЙС-ЛИСТ:</b>\n• 7 дней — 200₽\n• 30 дней — 400₽\n• 90 дней — 600₽\n• Навсегда — 750₽\n\n👨‍💻 Покупка ключа: @qqtewp\n\n<b>Введите лицензионный ключ:</b>")
    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back")).as_markup())

@dp.message(Steps.get_key)
async def process_key(msg: types.Message, state: FSMContext):
    res = db_query("SELECT days FROM keys WHERE key_code = ?", (msg.text.strip(),), fetchone=True)
    if res:
        exp = (datetime.now() + timedelta(days=int(res))).strftime("%Y-%m-%d %H:%M")
        db_query("DELETE FROM keys WHERE key_code = ?", (msg.text.strip(),))
        db_query("UPDATE users SET expiry = ? WHERE user_id = ?", (exp, msg.from_user.id))
        await msg.answer("✅ Доступ активирован!"); await state.clear(); await show_main_menu(msg.from_user.id, msg)
    else: await msg.answer("❌ Неверный ключ.")

@dp.callback_query(F.data == "toggle")
async def toggle_h(call: types.CallbackQuery):
    uid = call.from_user.id
    if not has_active_key(uid): return await call.answer("❌ Нужен ключ!", show_alert=True)
    res = db_query("SELECT session_string, post_id FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not res or not res[0] or not res[1]: return await call.answer("❌ Настройте аккаунт и пост!", show_alert=True)
    if uid in active_tasks:
        active_tasks.pop(uid, None); await call.answer("🛑 Остановил")
    else:
        active_tasks[uid] = True; asyncio.create_task(mailing_worker(uid)); await call.answer("🚀 Запустил")
    await show_main_menu(uid, call)

@dp.callback_query(F.data.startswith("chats:"))
async def chats_menu_pag(call: types.CallbackQuery):
    page = int(call.data.split(":")[1]); uid = call.from_user.id
    res = db_query("SELECT chats FROM users WHERE user_id = ?", (uid,), fetchone=True)
    chats = json.loads(str(res)) if res else []; items = 10; start, end = page * items, (page + 1) * items
    kb = InlineKeyboardBuilder(); txt = f"📂 <b>СПИСОК ЧАТОВ:</b>\n\n"
    for c in chats[start:end]:
        txt += f"• <code>{c}</code>\n"
        kb.row(types.InlineKeyboardButton(text=f"🗑 {c}", callback_data=f"delchat:{c}:{page}"))
    nav = []
    if page > 0: nav.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"chats:{page-1}"))
    if end < len(chats): nav.append(types.InlineKeyboardButton(text="➡️", callback_data=f"chats:{page+1}"))
    if nav: kb.row(*nav)
    kb.row(types.InlineKeyboardButton(text="➕ Добавить", callback_data="add_chats_step"), types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "add_chats_step")
async def ac(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Steps.get_chat); await call.message.edit_text("Юзернеймы через пробел:")

@dp.message(Steps.get_chat)
async def process_chats(msg: types.Message, state: FSMContext):
    new = [c.strip() for c in msg.text.replace('\n', ' ').split(' ') if c.strip()]
    res = db_query("SELECT chats FROM users WHERE user_id = ?", (msg.from_user.id,), fetchone=True)
    chats = json.loads(str(res)) if res else []
    upd = list(set(chats + new))
    db_query("UPDATE users SET chats = ? WHERE user_id = ?", (json.dumps(upd), msg.from_user.id))
    await state.clear(); await show_main_menu(msg.from_user.id, msg)

@dp.callback_query(F.data == "delay")
async def sd(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Steps.get_delay); await call.message.edit_text("⏱ Задержка (в секундах, мин 180):")

@dp.message(Steps.get_delay)
async def pd(msg: types.Message, state: FSMContext):
    if msg.text.isdigit(): db_query("UPDATE users SET delay = ? WHERE user_id = ?", (max(180, int(msg.text)), msg.from_user.id))
    await state.clear(); await show_main_menu(msg.from_user.id, msg)

@dp.callback_query(F.data == "back")
async def back_h(call: types.CallbackQuery, state: FSMContext):
    await state.clear(); await show_main_menu(call.from_user.id, call)

@dp.callback_query(F.data == "check_sub")
async def sub_c(call: types.CallbackQuery):
    if await is_subscribed_to_channel(call.from_user.id): await show_main_menu(call.from_user.id, call)
    else: await call.answer("❌ Не подписан!", show_alert=True)

@dp.callback_query(F.data == "confirm_del_acc")
async def cda(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="✅ Да", callback_data="df"), types.InlineKeyboardButton(text="❌ Нет", callback_data="back"))
    await call.message.edit_text("Отвязать аккаунт?", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "df")
async def daccf(call: types.CallbackQuery):
    db_query("UPDATE users SET session_string = NULL WHERE user_id = ?", (call.from_user.id,))
    await show_main_menu(call.from_user.id, call)

@dp.message(Command("key"), F.from_user.id == ADMIN_ID)
async def mk_key(msg: types.Message, command: CommandObject):
    if not command.args: return
    k = "KEY-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    db_query("INSERT INTO keys VALUES (?, ?)", (k, int(command.args)))
    await msg.answer(f"🎫 Ключ: <code>{k}</code>", parse_mode="HTML")

async def main():
    init_db()
    await bot.set_my_commands([BotCommand(command="/start", description="Запуск"), BotCommand(command="/help", description="Помощь")])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
