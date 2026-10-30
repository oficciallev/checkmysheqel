import telebot
from telebot import types

TOKEN = "9197805537:AAHaJew1atD3r0KGWlo0yoLgZ52WNcIA3HE"
bot = telebot.TeleBot(TOKEN)

# Ссылка на ваше веб-приложение с GitHub Pages
WEB_APP_URL = "https://oficciallev.github.io/checkmysheqel/"

@bot.message_handler(commands=['start'])
def start_cmd(message):
    keyboard = types.InlineKeyboardMarkup()
    
    # Кнопка прямо в сообщении
    web_app_btn = types.InlineKeyboardButton(
        text="📊 Открыть учет трат", 
        web_app=types.WebAppInfo(url=WEB_APP_URL)
    )
    keyboard.add(web_app_btn)

    bot.send_message(
        message.chat.id,
        "👋 Привет! Нажми на кнопку ниже или используй кнопку в меню слева, чтобы открыть веб-приложение трат:",
        reply_markup=keyboard
    )

if __name__ == "__main__":
    print("Бот с Mini App запущен...")
    bot.infinity_polling()