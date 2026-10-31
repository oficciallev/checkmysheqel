import json
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import telebot
from telebot import types

# 1. Загрузка конфигурации из .env
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key")
WEB_APP_URL = os.getenv(
    "WEB_APP_URL", "https://oficciallev.github.io/checkmysheqel/"
)
ANALYTICS_FILE = "analytics_data.json"

bot = telebot.TeleBot(TOKEN)
app = FastAPI()
security = HTTPBearer()

# Настройка CORS, чтобы Mini App на GitHub Pages мог присылать запросы
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Логика Telegram-бота
@bot.message_handler(commands=["start"])
def start_cmd(message):
    keyboard = types.InlineKeyboardMarkup()
    web_app_btn = types.InlineKeyboardButton(
        text="📊 Открыть учет трат", web_app=types.WebAppInfo(url=WEB_APP_URL)
    )
    keyboard.add(web_app_btn)

    bot.send_message(
        message.chat.id,
        "👋 Привет! Нажми на кнопку ниже или используй кнопку в меню слева, чтобы открыть веб-приложение трат:",
        reply_markup=keyboard,
    )


# 3. Вспомогательные функции для базы данных аналитики
def load_events():
    if not os.path.exists(ANALYTICS_FILE):
        return []
    try:
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_event_record(event_data):
    events = load_events()
    events.append(event_data)
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# 4. API Эндпоинты (Аналитика и Авторизация)
class EventSchema(BaseModel):
    event: str
    user_id: str = "anonymous"
    details: dict = {}


@app.post("/api/track")
async def track_event(data: EventSchema):
    event_record = {
        "timestamp": datetime.now().isoformat(),
        "event": data.event,
        "user_id": data.user_id,
        "details": data.details,
    }
    save_event_record(event_record)
    return {"status": "ok"}


class LoginSchema(BaseModel):
    password: str


@app.post("/api/admin/login")
async def admin_login(data: LoginSchema):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль"
        )
    return {"token": SECRET_KEY}


@app.get("/api/admin/stats")
async def get_admin_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials.credentials != SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен"
        )

    events = load_events()
    total_opens = sum(1 for e in events if e.get("event") == "app_open")
    total_txs = sum(1 for e in events if e.get("event") == "add_transaction")
    unique_users = len(
        set(e.get("user_id") for e in events if e.get("user_id"))
    )

    categories = {}
    for e in events:
        if e.get("event") == "add_transaction":
            cat = e.get("details", {}).get("category", "Другое")
            categories[cat] = categories.get(cat, 0) + 1

    return {
        "metrics": {
            "total_opens": total_opens,
            "total_transactions": total_txs,
            "unique_users": unique_users,
        },
        "categories": categories,
        "recent_events": events[-15:],
    }


# 5. Параллельный запуск бота и API-сервера
def run_bot():
    print("Бот c Mini App запущен...")
    bot.infinity_polling()


if __name__ == "__main__":
    # Запуск бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Запуск веб-сервера FastAPI
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)