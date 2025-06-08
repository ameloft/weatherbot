import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile # Додайте InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler
)
import matplotlib.pyplot as plt # Для побудови графіків
import io # Для роботи з байтовими потоками (збереження графіка в пам'ять)
import datetime # Для роботи з датами та часом

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

def get_weather_hourly(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,weathercode,precipitation_probability",
        "forecast_days": 1, # Прогноз на 1 день (24 години)
        "timezone": "auto"
    }
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        data = resp.json()
        hourly_data = data.get("hourly", {})
        times_raw = hourly_data.get("time", []) # Необроблені часові мітки
        temps = hourly_data.get("temperature_2m", [])
        codes = hourly_data.get("weathercode", [])
        prec_probs = hourly_data.get("precipitation_probability", [])

        if times_raw and temps and codes and prec_probs:
            msg = "Погодинний прогноз (наступні 24 години):\n"
            # Обробка даних для графіка
            plot_times = []
            plot_temps = []
            plot_prec_probs = []

            for i in range(min(24, len(times_raw))): # Обмежимо 24 годинами
                # Для текстового виводу
                hour_str = times_raw[i][11:16] # "YYYY-MM-DDTHH:MM" -> "HH:MM"
                day_desc = weather_code_to_text(codes[i])
                msg += (f"{hour_str}: {day_desc}, {temps[i]}°C, "
                        f"опади: {prec_probs[i]}%\n")

                # Для графіка
                plot_times.append(datetime.datetime.fromisoformat(times_raw[i]))
                plot_temps.append(temps[i])
                plot_prec_probs.append(prec_probs[i])

            return msg, plot_times, plot_temps, plot_prec_probs # Повертаємо дані для графіка
    return "Не вдалося отримати погодинний прогноз.", None, None, None

def generate_hourly_weather_plot(times, temps, prec_probs):
    if not times or not temps or not prec_probs:
        return None

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Графік температури
    ax1.plot(times, temps, 'r-', marker='o', label='Температура (°C)')
    ax1.set_xlabel('Час')
    ax1.set_ylabel('Температура (°C)', color='red')
    ax1.tick_params(axis='y', labelcolor='red')
    ax1.grid(True)
    ax1.set_title('Погодинний прогноз температури та ймовірності опадів')

    # Форматування осі X для відображення годин
    # Встановлюємо локатор для кожних 3 годин
    ax1.xaxis.set_major_locator(plt.matplotlib.dates.HourLocator(interval=3))
    # Форматуємо мітки як "HH:MM"
    ax1.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
    fig.autofmt_xdate() # Автоматичне нахилення міток

    # Графік ймовірності опадів (на другій осі Y)
    ax2 = ax1.twinx()
    ax2.bar(times, prec_probs, color='blue', alpha=0.3, width=0.04, label='Ймовірність опадів (%)')
    ax2.set_ylabel('Ймовірність опадів (%)', color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    ax2.set_ylim(0, 100) # Ймовірність від 0 до 100%

    # Додавання легенд
    lines, labels = ax1.get_legend_handles_labels()
    bars, bar_labels = ax2.get_legend_handles_labels()
    ax2.legend(lines + bars, labels + bar_labels, loc='upper left')

    # Зберігаємо графік у байтовий потік
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig) # Закриваємо фігуру, щоб уникнути витоків пам'яті
    return buf

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
        [InlineKeyboardButton("Прогноз на 3 дні", callback_data="forecast")],
        [InlineKeyboardButton("Погодинний прогноз", callback_data="hourly")] # Нова кнопка
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Перевіряємо, чи є це call_query, щоб правильно відповісти
    if update.callback_query:
        await update.callback_query.edit_message_text("Оберіть, що хочете побачити:", reply_markup=reply_markup)
    else:
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
        await query.edit_message_text("❌ Помилка: координати відсутні. Будь ласка, введіть місто або координати знову.")
        return

    weather_text = "Невідома команда."
    if query.data == "current":
        weather_text = get_weather_current(lat, lon)
        # Для поточної погоди графік не будуємо
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=10/{lat}/{lon}"
        keyboard = [[InlineKeyboardButton("Переглянути на карті", url=map_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(weather_text, reply_markup=reply_markup)

    elif query.data == "forecast":
        weather_text = get_weather_forecast(lat, lon)
        # Для прогнозу на 3 дні графік також не будуємо тут, можна розширити пізніше
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=10/{lat}/{lon}"
        keyboard = [[InlineKeyboardButton("Переглянути на карті", url=map_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(weather_text, reply_markup=reply_markup)

    elif query.data == "hourly": # Обробка нової кнопки
        # Отримуємо текст та дані для графіка
        hourly_forecast_text, plot_times, plot_temps, plot_prec_probs = get_weather_hourly(lat, lon)
        await query.edit_message_text(hourly_forecast_text) # Відправляємо текстовий прогноз

        # Якщо є дані для графіка, генеруємо та відправляємо його
        if plot_times and plot_temps and plot_prec_probs:
            await query.message.reply_text("Генерую графік погодинного прогнозу...")
            plot_buffer = generate_hourly_weather_plot(plot_times, plot_temps, plot_prec_probs)
            if plot_buffer:
                await query.message.reply_photo(photo=InputFile(plot_buffer), caption="Графік погодинного прогнозу:")
            else:
                await query.message.reply_text("Не вдалося згенерувати графік погодинного прогнозу.")

        # Додаємо кнопку "Переглянути на карті" також і для погодинного прогнозу
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=10/{lat}/{lon}"
        keyboard = [[InlineKeyboardButton("Переглянути на карті", url=map_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Оскільки ми вже відредагували повідомлення з текстом, відправляємо нове з картою
        await query.message.reply_text("Ви можете переглянути місцезнаходження на карті:", reply_markup=reply_markup)

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
