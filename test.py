import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler
)

API_TOKEN = "6240970287:AAGKU4lDb85qG1JN0jLwtDiGgni1q8MuMhw"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def weather_code_to_text(code):
    codes = {
        0: "ясно",
        1: "переважно ясно",
        2: "переважно хмарно",
        3: "хмарно",
        45: "туман",
        48: "морозна імла",
        51: "дрібний дощ",
        53: "помірний дощ",
        55: "сильний дрібний дощ",
        61: "невеликий дощ",
        63: "помірний дощ",
        65: "сильний дощ",
        71: "невеликий сніг",
        73: "помірний сніг",
        75: "сильний сніг",
        80: "дощові зливи",
        81: "сильні дощі",
        82: "інтенсивні зливи",
        95: "гроза",
        99: "сильна гроза"
    }
    return codes.get(code, "невідома погода")

def get_coordinates(city_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    headers = {"User-Agent": "telegram-weather-bot"}
    resp = requests.get(url, params=params, headers=headers)
    if resp.status_code == 200 and resp.json():
        data = resp.json()[0]
        return float(data["lat"]), float(data["lon"])
    else:
        return None, None

def get_weather_current(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current_weather": "true",
        "temperature_unit": "celsius",
        "timezone": "auto"
    }
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        data = resp.json()
        if "current_weather" in data:
            temp = data["current_weather"]["temperature"]
            code = data["current_weather"]["weathercode"]
            desc = weather_code_to_text(code)
            return f"Поточна погода: {desc}, {temp}°C"
    return "Не вдалося отримати поточну погоду."

def get_weather_forecast(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "timezone": "auto"
    }
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        max_temps = daily.get("temperature_2m_max", [])
        min_temps = daily.get("temperature_2m_min", [])
        codes = daily.get("weathercode", [])
        if dates and max_temps and min_temps and codes:
            msg = "Прогноз на 3 дні:\n"
            for i in range(min(3, len(dates))):
                day_desc = weather_code_to_text(codes[i])
                msg += (f"{dates[i]}: {day_desc}, "
                        f"макс: {max_temps[i]}°C, мін: {min_temps[i]}°C\n")
            return msg
    return "Не вдалося отримати прогноз."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("Привіт! Надішли мені назву міста або координати (lat,lon), "
            "і я скажу погоду.\n\n"
            "Доступні команди:\n"
            "/help - допомога\n"
            "/about - про бота")
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("Введи назву міста (наприклад, Kyiv) або координати (наприклад, 50.45,30.52).\n"
            "Я надішлю поточну погоду та прогноз на 3 дні.\n"
            "Команди:\n"
            "/start - привітання\n"
            "/help - ця допомога\n"
            "/about - інформація про бота")
    await update.message.reply_text(text)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("WeatherBot v1.0\n"
            "Показує погоду через Open-Meteo API.\n"
            "Автор: @ameloft\n"
            "Безкоштовний та відкритий.")
    await update.message.reply_text(text)

async def send_weather_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Поточна погода", callback_data="current")],
        [InlineKeyboardButton("Прогноз на 3 дні", callback_data="forecast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Оберіть, що хочете побачити:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Визначаємо, чи це координати
    if "," in text:
        parts = text.split(",")
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            context.user_data["lat"] = lat
            context.user_data["lon"] = lon
            await send_weather_menu(update, context)
            return
        except ValueError:
            await update.message.reply_text("❌ Некоректні координати. Спробуйте ще раз.")
            return
    # Якщо це назва міста
    lat, lon = get_coordinates(text)
    if lat is None or lon is None:
        await update.message.reply_text("❌ Не вдалося знайти місто. Спробуйте ще раз.")
        return
    context.user_data["lat"] = lat
    context.user_data["lon"] = lon
    await send_weather_menu(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lat = context.user_data.get("lat")
    lon = context.user_data.get("lon")
    if lat is None or lon is None:
        await query.edit_message_text("❌ Помилка: координати відсутні.")
        return

    if query.data == "current":
        weather = get_weather_current(lat, lon)
        await query.edit_message_text(weather)
    elif query.data == "forecast":
        forecast = get_weather_forecast(lat, lon)
        await query.edit_message_text(forecast)
    else:
        await query.edit_message_text("Невідома команда.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущений...")
    app.run_polling()
