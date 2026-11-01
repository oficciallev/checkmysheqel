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

# 1. Загрузка конфигурации из .env
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL")

DB_FILE = "analytics.db"

bot = telebot.TeleBot(TOKEN)
app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Инициализация постоянной базы данных SQLite
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    conn.close()

init_db()


# 3. Логика Telegram-бота
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

# Запись событий (заходы, добавление доходов/расходов)
@app.post("/api/track")
async def track_event(data: TrackEvent):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (user_id, username, event, details) VALUES (?, ?, ?, ?)",
        (
            str(data.user_id),
            data.username,
            data.event,
            json.dumps(data.details, ensure_ascii=False)
        )
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


# Получение аналитики для админки (доступ только по твоем user_id)
@app.post("/api/admin/stats")
async def get_admin_stats(auth: AdminAuth):
    if str(auth.user_id) != str(ADMIN_TELEGRAM_ID):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен"
        )

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Общее кол-во записей и уникальных юзеров
    cursor.execute("SELECT COUNT(*) FROM logs")
    total_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM logs WHERE user_id != 'anonymous'")
    unique_users = cursor.fetchone()[0]

    # Подсчет по событиям (app_open, add_income, add_expense)
    cursor.execute("SELECT event, COUNT(*) FROM logs GROUP BY event")
    event_counts = dict(cursor.fetchall())

    # Последние 50 логов
    cursor.execute("SELECT user_id, username, event, details, timestamp FROM logs ORDER BY id DESC LIMIT 50")
    raw_logs = cursor.fetchall()

    recent_logs = []
    for row in raw_logs:
        try:
            parsed_details = json.loads(row[3]) if row[3] else {}
        except Exception:
            parsed_details = {}

        recent_logs.append({
            "user_id": row[0],
            "username": row[1],
            "event": row[2],
            "details": parsed_details,
            "timestamp": row[4]
        })

    conn.close()

    return {
        "total_events": total_events,
        "unique_users": unique_users,
        "event_counts": event_counts,
        "recent_logs": recent_logs
    }


# 6. Запуск бота и веб-сервера
def run_bot():
    print("🤖 Бот запущен...")
    bot.infinity_polling()


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)