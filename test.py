import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler, JobQueue # JobQueue для сповіщень
)
import matplotlib.pyplot as plt
import io # Для роботи з байтовими потоками (збереження графіка в пам'ять)
import datetime # Для роботи з датами та часом

# Ваш токен бота
API_TOKEN = "6240970287:AAGKU4lDb85qG1JN0jLwtDiGgni1q8MuMhw"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Глобальний словник для зберігання підписок (ПРОСТА ДЕМОНСТРАЦІЯ, НЕ ДЛЯ ПРОДАКШНУ)
# Формат: {user_id: {"lat": float, "lon": float, "city_name": str, "notification_time": "HH:MM"}}
# У реальному проекті використовуйте базу даних!
user_subscriptions = {}


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
    return codes.get(code, "невідомо")

def get_coordinates(city_name):
    url = f"https://nominatim.openstreetmap.org/search?q={city_name}&format=json"
    headers = {"User-Agent": "WeatherBot/1.0"} # Завжди додавайте User-Agent
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status() # Перевірка на помилки HTTP
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при запиті до Nominatim: {e}")
    except ValueError:
        logging.error("Не вдалося розпарсити координати.")
    return None, None

def get_weather_current(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current_weather": True,
        "timezone": "auto"
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if "current_weather" in data:
            current = data["current_weather"]
            temperature = current["temperature"]
            windspeed = current["windspeed"]
            weathercode = current["weathercode"]
            
            weather_desc = weather_code_to_text(weathercode)
            
            msg = (
                f"🌡️ Температура: {temperature}°C\n"
                f"💨 Швидкість вітру: {windspeed} м/с\n"
                f"☁️ Опис: {weather_desc}"
            )
            return msg
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при отриманні поточної погоди: {e}")
    return "Не вдалося отримати поточну погоду."

# ОНОВЛЕНА ФУНКЦІЯ: get_weather_forecast тепер повертає деталі для кожного дня
def get_weather_forecast(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "daily": "weathercode,temperature_2m_max,temperature_2m_min",
        "hourly": "temperature_2m,weathercode,precipitation_probability", # Включаємо погодинні дані для всіх днів
        "forecast_days": 3,
        "timezone": "auto"
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        daily_data = data.get("daily", {})
        hourly_data = data.get("hourly", {})

        daily_times = daily_data.get("time", [])
        daily_max_temps = daily_data.get("temperature_2m_max", [])
        daily_min_temps = daily_data.get("temperature_2m_min", [])
        daily_codes = daily_data.get("weathercode", [])

        if not daily_times:
            return "Не вдалося отримати прогноз на 3 дні.", {}

        forecast_details = {} # Словник для зберігання деталей по днях

        # ЦИКЛ ПО DAILY_TIMES, який був відсутній у вашому початковому коді
        for i in range(len(daily_times)):
            date_str = daily_times[i]
            # Форматуємо дату для зручності
            date_obj = datetime.datetime.fromisoformat(date_str)
            day_name = date_obj.strftime("%A, %d.%m")
            # Локалізуємо дні тижня (можна додати більше мов)
            day_name = day_name.replace("Monday", "Понеділок").replace("Tuesday", "Вівторок").replace("Wednesday", "Середа").replace("Thursday", "Четвер").replace("Friday", "П'ятниця").replace("Saturday", "Субота").replace("Sunday", "Неділя")
            
            day_text = weather_code_to_text(daily_codes[i])
            max_temp = daily_max_temps[i]
            min_temp = daily_min_temps[i]

            # Збираємо погодинні дані, що належать до поточного дня
            hourly_forecast_for_day = {
                "times": [],
                "temps": [],
                "codes": [],
                "prec_probs": []
            }
            
            for j in range(len(hourly_data.get("time", []))):
                hourly_time_str = hourly_data["time"][j]
                # Перевіряємо, чи погодинний час належить до поточної дати
                if hourly_time_str.startswith(date_str):
                    hourly_forecast_for_day["times"].append(hourly_time_str)
                    hourly_forecast_for_day["temps"].append(hourly_data["temperature_2m"][j])
                    hourly_forecast_for_day["codes"].append(hourly_data["weathercode"][j])
                    hourly_forecast_for_day["prec_probs"].append(hourly_data["precipitation_probability"][j])
            
            forecast_details[date_str] = { # Ключ - ISO дата, щоб потім легко дістати
                "summary": f"{day_name}: {day_text}, від {min_temp}°C до {max_temp}°C",
                "hourly_data": hourly_forecast_for_day
            }
        
        # Сформуємо загальне повідомлення про прогноз на 3 дні для початкового виведення
        initial_message = "Прогноз погоди на 3 дні:\n"
        for date_str, details in forecast_details.items():
            initial_message += f"- {details['summary']}\n"

        return initial_message, forecast_details # Повертаємо і текст, і детальні дані
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при отриманні прогнозу на 3 дні: {e}")
    return "Не вдалося отримати прогноз на 3 дні.", {}

# АДАПТОВАНА ФУНКЦІЯ: get_weather_hourly тепер приймає вже готові дані
def get_weather_hourly(hourly_data_for_day):
    times_raw = hourly_data_for_day.get("times", [])
    temps = hourly_data_for_day.get("temps", [])
    codes = hourly_data_for_day.get("codes", [])
    prec_probs = hourly_data_for_day.get("prec_probs", [])

    if times_raw and temps and codes and prec_probs:
        msg = "Погодинний прогноз:\n"
        plot_times = []
        plot_temps = []
        plot_prec_probs = []

        for i in range(len(times_raw)):
            hour_str = times_raw[i][11:16] # "YYYY-MM-DDTHH:MM" -> "HH:MM"
            day_desc = weather_code_to_text(codes[i])
            msg += (f"{hour_str}: {day_desc}, {temps[i]}°C, "
                    f"опади: {prec_probs[i]}%\n")

            plot_times.append(datetime.datetime.fromisoformat(times_raw[i]))
            plot_temps.append(temps[i])
            plot_prec_probs.append(prec_probs[i])

        return msg, plot_times, plot_temps, plot_prec_probs
    return "Не вдалося отримати погодинний прогноз для цього дня.", None, None, None

# НОВА ФУНКЦІЯ: Генерація графіка
def generate_hourly_weather_plot(times, temps, prec_probs):
    if not times or not temps or not prec_probs:
        return None

    fig, ax1 = plt.subplots(figsize=(12, 7)) # Збільшено розмір для кращої читабельності

    # Графік температури
    ax1.plot(times, temps, 'r-', marker='o', label='Температура (°C)')
    ax1.set_xlabel('Час')
    ax1.set_ylabel('Температура (°C)', color='red')
    ax1.tick_params(axis='y', labelcolor='red')
    ax1.grid(True, linestyle='--', alpha=0.7) # Додано стиль сітки
    ax1.set_title('Погодинний прогноз температури та ймовірності опадів')

    # Форматування осі X для відображення годин
    ax1.xaxis.set_major_locator(plt.matplotlib.dates.HourLocator(interval=3)) # Мітки кожні 3 години
    ax1.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
    fig.autofmt_xdate() # Автоматичне нахилення міток для уникнення перекриття

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Надішліть мені назву міста або його широту та довготу (наприклад, 'Київ' або '50.45,30.52'), і я надам вам прогноз погоди.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я можу надати вам поточну погоду або прогноз на 3 дні. Просто надішліть мені назву міста (наприклад, 'Львів') або координати (наприклад, '49.83,24.02').")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    github_link = "https://github.com/ameloft/weatherbot/tree/main" 
    
    message_text = (
        "Цей <a href=\"" + github_link + "\">бот</a> створений для надання інформації про погоду "
        "з використанням Open-Meteo API та Nominatim OpenStreetMap."
    )
    
    await update.message.reply_text(message_text, parse_mode='HTML')

async def send_weather_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Поточна погода", callback_data="current")],
        [InlineKeyboardButton("Прогноз на 3 дні", callback_data="forecast")],
        # Кнопка "Погодинний прогноз" зникла, бо тепер вона буде вкладена у прогноз на 3 дні
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Перевіряємо, чи є це call_query, щоб правильно відповісти (для повернення назад)
    if update.callback_query:
        await update.callback_query.edit_message_text("Оберіть, що хочете побачити:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Оберіть, що хочете побачити:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lat, lon = None, None

    # Спроба розпарсити як координати
    if "," in text:
        parts = text.split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                # Додаткова перевірка діапазону координат
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    await update.message.reply_text("❌ Некоректні координати. Широта має бути від -90 до 90, довгота від -180 до 180.")
                    return
            except ValueError:
                await update.message.reply_text("❌ Некоректні координати. Спробуйте ще раз у форматі 'широта,довгота'.")
                return
        else:
            await update.message.reply_text("❌ Некоректні координати. Спробуйте ще раз у форматі 'широта,довгота'.")
            return
    
    # Якщо це назва міста
    if lat is None or lon is None: # Тільки якщо не розпарсили як координати
        lat, lon = get_coordinates(text)
        if lat is None or lon is None:
            await update.message.reply_text("❌ Не вдалося знайти місто. Спробуйте ще раз.")
            return

    context.user_data["lat"] = lat
    context.user_data["lon"] = lon
    # Додаємо збереження назви міста для сповіщень
    context.user_data["city_name"] = text # Зберігаємо назву міста
    await send_weather_menu(update, context)

# ОНОВЛЕНИЙ button_handler для вкладеного вибору днів та графіків
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lat = context.user_data.get("lat")
    lon = context.user_data.get("lon")
    if lat is None or lon is None:
        await query.edit_message_text("❌ Помилка: координати відсутні. Будь ласка, введіть місто або координати знову.")
        return

    query_data = query.data

    if query_data == "current":
        weather_text = get_weather_current(lat, lon)
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=10/{lat}/{lon}"
        keyboard = [[InlineKeyboardButton("Переглянути на карті", url=map_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(weather_text, reply_markup=reply_markup)

    elif query_data == "forecast":
        # Отримуємо загальний текст та детальні дані прогнозу на 3 дні
        forecast_text, forecast_details = get_weather_forecast(lat, lon)
        context.user_data["forecast_details"] = forecast_details # Зберігаємо деталі у user_data

        if not forecast_details:
            await query.edit_message_text(forecast_text) # Якщо немає деталей, просто виводимо текст
            return

        # Створюємо кнопки для кожного дня
        keyboard = []
        for date_str, details in forecast_details.items():
            # Форматуємо дату для кнопки
            date_obj = datetime.datetime.fromisoformat(date_str)
            day_name = date_obj.strftime("%A, %d.%m")
            day_name = day_name.replace("Monday", "Понеділок").replace("Tuesday", "Вівторок").replace("Wednesday", "Середа").replace("Thursday", "Четвер").replace("Friday", "П'ятниця").replace("Saturday", "Субота").replace("Sunday", "Неділя")
            
            keyboard.append([InlineKeyboardButton(f"Погодинний на {day_name}", callback_data=f"hourly_for_day_{date_str}")])
        
        # Додаємо кнопку "Назад" до загального меню погоди
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(forecast_text + "\nОберіть день для детального погодинного прогнозу:", reply_markup=reply_markup)

    elif query_data.startswith("hourly_for_day_"):
        # Користувач обрав конкретний день для погодинного прогнозу
        date_str = query_data.replace("hourly_for_day_", "")
        forecast_details = context.user_data.get("forecast_details")

        if not forecast_details or date_str not in forecast_details:
            await query.edit_message_text("❌ Помилка: дані прогнозу для цього дня не знайдено. Спробуйте запитати прогноз знову.")
            return

        hourly_data_for_selected_day = forecast_details[date_str]["hourly_data"]
        
        # Отримуємо текст та дані для графіка за допомогою адаптованої get_weather_hourly
        hourly_forecast_text, plot_times, plot_temps, plot_prec_probs = get_weather_hourly(hourly_data_for_selected_day)
        
        # Форматуємо дату для заголовка
        date_obj = datetime.datetime.fromisoformat(date_str)
        day_name = date_obj.strftime("%A, %d.%m")
        day_name = day_name.replace("Monday", "Понеділок").replace("Tuesday", "Вівторок").replace("Wednesday", "Середа").replace("Thursday", "Четвер").replace("Friday", "П'ятниця").replace("Saturday", "Субота").replace("Sunday", "Неділя")
        
        # Відправляємо текстовий прогноз (редагуємо початкове повідомлення з кнопками дня)
        await query.edit_message_text(f"Погодинний прогноз на {day_name}:\n{hourly_forecast_text}")

        # Якщо є дані для графіка, генеруємо та відправляємо його
        if plot_times and plot_temps and plot_prec_probs:
            await query.message.reply_text("Генерую графік погодинного прогнозу...")
            plot_buffer = generate_hourly_weather_plot(plot_times, plot_temps, plot_prec_probs)
            if plot_buffer:
                await query.message.reply_photo(photo=InputFile(plot_buffer), caption=f"Графік погодинного прогнозу на {day_name}:")
            else:
                await query.message.reply_text("Не вдалося згенерувати графік погодинного прогнозу.")
        
        # Додаємо кнопку "Переглянути на карті" та "Назад" окремим повідомленням
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=10/{lat}/{lon}"
        keyboard = [
            [InlineKeyboardButton("Переглянути на карті", url=map_url)],
            [InlineKeyboardButton("⬅️ Назад до прогнозу на 3 дні", callback_data="forecast")] # Повернення до списку днів
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Додатково:", reply_markup=reply_markup)

    elif query_data == "back_to_main_menu":
        # Просто повертаємося до основного меню вибору погоди
        await send_weather_menu(update, context)

    else:
        await query.edit_message_text("Невідома команда.")

# НОВІ ФУНКЦІЇ ДЛЯ СПОВІЩЕНЬ (ПУНКТ 2)
async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Будь ласка, вкажіть час для сповіщення (наприклад, /subscribe 08:00). Місто буде взято з останнього запиту.")
        
        lat = context.user_data.get("lat")
        lon = context.user_data.get("lon")
        city_name = context.user_data.get("city_name")

        if lat is None or lon is None:
            await update.message.reply_text("Спочатку введіть місто або координати, а потім спробуйте /subscribe.")
            return

        await update.message.reply_text(f"Поточне місцезнаходження для підписки: {city_name if city_name else f'({lat},{lon})'}")
        return

    time_str = context.args[0]

    # Перевірка формату часу
    try:
        import datetime
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        datetime.time(hour, minute)
    except ValueError:
        await update.message.reply_text("Некоректний формат часу. Використовуйте HH:MM (наприклад, 08:00).")
        return

    user_id = update.effective_user.id
    lat = context.user_data.get("lat")
    lon = context.user_data.get("lon")
    city_name = context.user_data.get("city_name")

    if lat is None or lon is None:
        await update.message.reply_text("❌ Будь ласка, спочатку введіть місто або координати, щоб я знав, для якого місця надсилати сповіщення.")
        return

    # Зберігаємо підписку
    user_subscriptions[user_id] = { # Зверніть увагу: використовується глобальний словник, не context.bot_data напряму
        "lat": lat,
        "lon": lon,
        "city_name": city_name if city_name else f"({lat},{lon})",
        "notification_time": time_str
    }
    await update.message.reply_text(f"Ви підписалися на щоденні сповіщення про погоду для {user_subscriptions[user_id]['city_name']} о {time_str}.")
    logging.info(f"User {user_id} subscribed for {user_subscriptions[user_id]['city_name']} at {time_str}")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_subscriptions:
        del user_subscriptions[user_id]
        await update.message.reply_text("Ви відписалися від сповіщень про погоду.")
        logging.info(f"User {user_id} unsubscribed.")
    else:
        await update.message.reply_text("Ви не підписані на сповіщення.")

async def send_daily_weather_notifications(context: ContextTypes.DEFAULT_TYPE):
    import datetime
    now = datetime.datetime.now().strftime("%H:%M")
    logging.info(f"Running daily notification check at {now}")

    # Перевіряємо всі підписки
    for user_id, data in user_subscriptions.items():
        if data.get("notification_time") == now:
            lat, lon = data["lat"], data["lon"]
            city_name = data["city_name"]
            
            # Отримуємо поточну погоду для сповіщення
            weather = get_weather_current(lat, lon) 
            message = f"🔔 Щоденний прогноз для {city_name}:\n{weather}"
            try:
                await context.bot.send_message(chat_id=user_id, text=message)
                logging.info(f"Sent notification to user {user_id} for {city_name}")
            except Exception as e:
                logging.error(f"Failed to send notification to user {user_id}: {e}")


# НОВА ФУНКЦІЯ: Обробка відправленого місцезнаходження Telegram
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    context.user_data["lat"] = lat
    context.user_data["lon"] = lon
    context.user_data["city_name"] = f"({lat},{lon})" # Зберігаємо координати як назву для сповіщень
    await update.message.reply_text(f"Отримано ваше місцезнаходження: Широта {lat}, Довгота {lon}.")
    await send_weather_menu(update, context)

# Блок запуску бота
if __name__ == "__main__":
    app = ApplicationBuilder().token(API_TOKEN).build()

    # Додаємо обробники команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    
    # Обробник текстових повідомлень (місто/координати)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Обробник для відправленого місцезнаходження (геолокації)
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    # Обробник натискань inline-кнопок
    app.add_handler(CallbackQueryHandler(button_handler))

    # Налаштування JobQueue для регулярної перевірки сповіщень (для пункту 2)
    job_queue = app.job_queue
    # Запускаємо функцію send_daily_weather_notifications кожні 60 секунд.
    # first=0 означає, що перший запуск відбудеться негайно.
    job_queue.run_repeating(send_daily_weather_notifications, interval=60, first=0)

    print("Бот запущений...")
    app.run_polling()
