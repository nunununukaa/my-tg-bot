import asyncio
import logging
import sqlite3
import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 6511829371  # Ваш Telegram ID
KINOPOISK_API_KEY = "ВАШ_API_KEY_КИНОПОИСКА"

DB_NAME = "kinokomnata.db"

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            year INTEGER,
            genre TEXT,
            rating TEXT,
            description TEXT,
            file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def fetch_kp_data(kp_id):
    headers = {"X-API-KEY": KINOPOISK_API_KEY, "Content-Type": "application/json"}
    url = f"https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        genres = ", ".join([g["genre"].capitalize() for g in data.get("genres", [])])
        return {
            "title": data.get("nameRu") or data.get("nameOriginal") or "Без названия",
            "year": data.get("year"),
            "genre": genres or "Не указан",
            "rating": str(data.get("ratingKinopoisk") or data.get("ratingImdb") or "—"),
            "description": data.get("description") or "Описание отсутствует."
        }
    return None

def add_movie_to_db(title, year, genre, rating, description, file_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO movies (title, year, genre, rating, description, file_id) VALUES (?, ?, ?, ?, ?, ?)",
        (title, year, genre, rating, description, file_id)
    )
    conn.commit()
    conn.close()

def search_movies_db(query):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, year FROM movies WHERE title LIKE ?", (f"%{query}%",))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_movie_by_id(m_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, year, genre, rating, description, file_id FROM movies WHERE id = ?", (m_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ==================== СОСТОЯНИЯ ====================
class AddMovieState(StatesGroup):
    waiting_for_video = State()
    waiting_for_kp_id = State()

class SearchState(StatesGroup):
    waiting_for_query = State()

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

def get_main_kb(user_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔎 Поиск", "🎬 Все фильмы")
    if user_id == ADMIN_ID:
        kb.add("➕ Добавить фильм")
    return kb

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer("Добро пожаловать в Kinoкомната!", reply_markup=get_main_kb(message.from_user.id))

@dp.message_handler(text="🔎 Поиск")
async def search_start(message: types.Message):
    await SearchState.waiting_for_query.set()
    await message.answer("Введите название фильма:")

@dp.message_handler(state=SearchState.waiting_for_query)
async def search_process(message: types.Message, state: FSMContext):
    q = message.text.strip()
    await state.finish()
    results = search_movies_db(q)
    if not results:
        await message.answer("❌ Ничего не найдено.")
        return
    kb = types.InlineKeyboardMarkup()
    for m in results:
        kb.add(types.InlineKeyboardButton(f"🎬 {m[1]} ({m[2]})", callback_data=f"show_{m[0]}"))
    await message.answer(f"Результаты по запросу «{q}»:", reply_markup=kb)

@dp.message_handler(text="🎬 Все фильмы")
async def list_all(message: types.Message):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, year FROM movies ORDER BY id DESC")
    movies = cursor.fetchall()
    conn.close()
    if not movies:
        await message.answer("Фильмов пока нет.")
        return
    kb = types.InlineKeyboardMarkup()
    for m in movies:
        kb.add(types.InlineKeyboardButton(f"🎬 {m[1]} ({m[2]})", callback_data=f"show_{m[0]}"))
    await message.answer("Список фильмов:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("show_"))
async def show_card(cb: types.CallbackQuery):
    m_id = int(cb.data.split("_")[1])
    m = get_movie_by_id(m_id)
    if not m:
        return
    text = (
        f"🎬 **{m[1]}**\n"
        f"📅 **Год:** {m[2]}\n"
        f"🎭 **Жанр:** {m[3]}\n"
        f"⭐ **Рейтинг KP:** {m[4]}\n\n"
        f"📝 **Описание:**\n{m[5]}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("▶️ Смотреть", callback_data=f"watch_{m[0]}"))
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("watch_"))
async def watch_movie(cb: types.CallbackQuery):
    m_id = int(cb.data.split("_")[1])
    m = get_movie_by_id(m_id)
    if m and m[6]:
        await cb.message.answer_video(video=m[6], caption=f"🎬 {m[1]}")
    await cb.answer()

# --- Админка ---
@dp.message_handler(text="➕ Добавить фильм")
async def add_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await AddMovieState.waiting_for_video.set()
    await message.answer("Отправьте видеофайл фильма:")

@dp.message_handler(content_types=['video', 'document'], state=AddMovieState.waiting_for_video)
async def add_video(message: types.Message, state: FSMContext):
    fid = message.video.file_id if message.video else message.document.file_id
    await state.update_data(file_id=fid)
    await AddMovieState.waiting_for_kp_id.set()
    await message.answer("Введите ID фильма на Кинопоиске (число):")

@dp.message_handler(state=AddMovieState.waiting_for_kp_id)
async def add_kp_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите числовой ID:")
        return
    data = await state.get_data()
    kp = fetch_kp_data(int(message.text))
    if not kp:
        await message.answer("Фильм не найден на Кинопоиске.")
        return
    add_movie_to_db(kp['title'], kp['year'], kp['genre'], kp['rating'], kp['description'], data['file_id'])
    await state.finish()
    await message.answer(f"✅ Фильм «{kp['title']}» успешно добавлен!")

if __name__ == "__main__":
    init_db()
    logging.basicConfig(level=logging.INFO)
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)

