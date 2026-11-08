import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import telebot
from telebot import types

# Проверяем наличие драйвера PostgreSQL
try:
    import psycopg2
except ImportError:
    psycopg2 = None

# 1. Загрузка конфигурации из .env / Environment Variables
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

DB_FILE = "analytics.db"

bot = telebot.TeleBot(TOKEN) if TOKEN else None
app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Динамическое подключение к БД (Supabase PostgreSQL или локальный SQLite)
def get_db_connection():
    if DATABASE_URL and psycopg2:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(DB_FILE)


# 2. Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL and psycopg2:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                username TEXT,
                event TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                event TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()


# 3. Логика Telegram-бота
if bot:
    @bot.message_handler(commands=["start"])
    def start_cmd(message):
        keyboard = types.InlineKeyboardMarkup()
        web_app_btn = types.InlineKeyboardButton(
            text="📊 Открыть учет трат", web_app=types.WebAppInfo(url=WEB_APP_URL)
        )
        keyboard.add(web_app_btn)

        bot.send_message(
            message.chat.id,
            "👋 Привет! Нажми на кнопку ниже, чтобы открыть приложение трат:",
            reply_markup=keyboard,
        )


# 4. Pydantic-модели для API
class TrackEvent(BaseModel):
    user_id: str = "anonymous"
    username: Optional[str] = "Guest"
    event: str
    details: Optional[dict] = {}

class AdminAuth(BaseModel):
    user_id: str


# 5. API Эндпоинты

@app.post("/api/track")
async def track_event(data: TrackEvent):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholder = "%s" if (DATABASE_URL and psycopg2) else "?"
    query = f"INSERT INTO logs (user_id, username, event, details) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})"
    
    cursor.execute(
        query,
        (
            str(data.user_id),
            data.username,
            data.event,
            json.dumps(data.details, ensure_ascii=False)
        )
    )
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.post("/api/admin/stats")
async def get_admin_stats(auth: AdminAuth):
    if str(auth.user_id) != str(ADMIN_TELEGRAM_ID):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен"
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM logs")
    total_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM logs WHERE user_id != 'anonymous'")
    unique_users = cursor.fetchone()[0]

    cursor.execute("SELECT event, COUNT(*) FROM logs GROUP BY event")
    event_rows = cursor.fetchall()
    event_counts = {row[0]: row[1] for row in event_rows}

    cursor.execute("SELECT user_id, username, event, details, timestamp FROM logs ORDER BY id DESC LIMIT 50")
    raw_logs = cursor.fetchall()

    recent_logs = []
    for row in raw_logs:
        try:
            parsed_details = json.loads(row[3]) if isinstance(row[3], str) else row[3]
        except Exception:
            parsed_details = {}

        recent_logs.append({
            "user_id": row[0],
            "username": row[1],
            "event": row[2],
            "details": parsed_details,
            "timestamp": str(row[4])
        })

    cursor.close()
    conn.close()

    return {
        "total_events": total_events,
        "unique_users": unique_users,
        "event_counts": event_counts,
        "recent_logs": recent_logs
    }


# 6. Запуск бота и веб-сервера
def run_bot():
    if bot:
        print("🤖 Бот запущен...")
        bot.infinity_polling()


if __name__ == "__main__":
    if bot:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)