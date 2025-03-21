import os
import json
import random
from datetime import time as dtime
from zoneinfo import ZoneInfo
from telebot import TeleBot, types
from telebot.types import InlineQueryResultArticle, InputTextMessageContent
from apscheduler.schedulers.background import BackgroundScheduler

API_TOKEN = 'token'
SUBSCRIBED_USERS_FILE = "subscribed_users.json"

bot = TeleBot(API_TOKEN)
scheduler = BackgroundScheduler()

# Functions to save/load subscribed users
def load_subscribed_users() -> set:
    try:
        with open(SUBSCRIBED_USERS_FILE, "r") as f:
            users = json.load(f)
            return set(users)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_subscribed_users(users: set):
    with open(SUBSCRIBED_USERS_FILE, "w") as f:
        json.dump(list(users), f)

# Global set of subscribed users (chat_id)
subscribed_users = load_subscribed_users()

# Function to register a user (called on any interaction)
def register_user(chat_id):
    if chat_id not in subscribed_users:
        subscribed_users.add(chat_id)
        save_subscribed_users(subscribed_users)

# Lessons (example)
lessons = [
    "Урок 1: 💡Основы коми языка.\n\nФраза: 'Видза оланныд!!' — означает 'Здравствуйте!'.\nПопробуй написать эту фразу!",
    "Урок 2: 👋Приветствие.\n\nФраза: 'Чолӧм!' — означает 'Привет!'.\nЗапомни эту фразу!",
    "Урок 3: 🏡Гостеприимство.\n\nФраза: 'Радпырысь корам' — означает 'С радостью приглашаем!'.\nПопробуй использовать её в предложении!",
    "Урок 4: ❓Вопрос.\n\nФраза: 'Кыдзи олан?' — означает 'Как поживаешь?'.\nПопробуй написать эту фразу!",
    "Урок 5: 🙏Благодарность.\n\nФраза: 'Аттьӧ, бура' — означают 'Спасибо, хорошо'.\nЗапомни эту фразу!",
    "Урок 6: 🆒Эпитеты.\n\nСлова: 'Шань, бур' — означает 'Добрый, хороший'.\nПопробуй использовать их в предложении!",
    "Урок 7: 🌠Пожелание.\n\nФраза: 'Став бурсӧ!' — означает 'Всего хорошего!!'.\nПопробуй написать эту фразу!",
    "Урок 8: 🗣Обращение.\n\nФраза: 'Пыдди пуктана ёртъяс!' — означает 'Уважаемые друзья!'.\nЗапомни эту фразу!",
    "Урок 9: 🎉Поздравление.\n\nФраза: 'Чолӧмала тэнӧ!' — означает 'Поздравляю тебя!'.\nПопробуй использовать её в предложении!",
    "Урок 10: 📛Имя.\n\nВопрос: 'Кыдзи тэнад нимыд?' — означает 'Как тебя зовут?!'.\nПопробуй написать этот вопрос!",
    "Урок 11: 💁‍♂️Помощь.\n\nВопрос: 'Отсыштны верма ог?!' — означает 'Могу ли я помочь?!'.\nЗапомни этот вопрос!",
    "Урок 12: 📖Учёба.\n\nФраза: 'Коми кыв велӧда' — означает 'Учу коми язык'.\nЗапомни эту фразу!",
    "Урок 13: 👨‍🎓Основы коми языка.\n\nВопрос: 'Кутшӧм лунӧ коми кывйысь экзамен?' — означает 'В какой день по коми языку экзамен?!'.\nПопробуй написать этот вопрос!",
    "Урок 14: 😴Фраза ко сну.\n\nФраза: 'Бур вой!' — означает 'Доброй ночи!'.\nЗапомни эту фразу!",
    "Урок 15: 👋Прощание.\n\nФраза: 'Аддзысьлытӧдз!' — означает 'До встречи! До свидания!'.\nПопробуй использовать её в предложении!",
]

# Quiz questions with added "explanation" field
quiz_questions = [
    {
        "question": "Как переводится 'Чолӧм'?",
        "options": ["Спасибо", "Привет", "До свидания", "Извините"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Привет. 'Чолӧм' означает 'Привет'."
    },
    {
        "question": "Как переводится 'Видза оланныд'?",
        "options": ["Добро пожаловать", "Извините", "Спасибо", "Здравствуйте"],
        "correct_option_id": 3,
        "explanation": "Правильный ответ: Здравствуйте. 'Видза оланныд' означает 'Здравствуйте'."
    },
    {
        "question": "Как переводится 'Радпырысь корам'?",
        "options": ["До свидания", "С радостью приглашаем", "Привет", "Извините"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: С радостью приглашаем. 'Радпырысь корам' означает 'С радостью приглашаем'."
    }
]

# Dictionaries to track user progress
current_lesson_index = {}
current_quiz_index = {}
# active_quizzes stores for each active poll (poll_id) a tuple: (user_id, chat_id, question_index)
active_quizzes = {}

# Handler for /start command
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.chat.id)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Начать урок", "Следующий урок", "Начать квиз")
    keyboard.add("Помощь")
    bot.send_message(message.chat.id, "Чолӧм, я бот для изучения коми языка! Выберите действие:", reply_markup=keyboard)

def send_lesson(chat_id, lesson_index):
    bot.send_message(chat_id, lessons[lesson_index])

@bot.message_handler(func=lambda message: message.text == "Начать урок")
def start_lesson(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    if user_id not in current_lesson_index:
        current_lesson_index[user_id] = 0

    lesson_index = current_lesson_index[user_id]
    if lesson_index < len(lessons):
        send_lesson(message.chat.id, lesson_index)
    else:
        bot.send_message(message.chat.id, "Все уроки пройдены! Ждите новых.")

@bot.message_handler(func=lambda message: message.text == "Следующий урок")
def next_lesson(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    if user_id not in current_lesson_index:
        current_lesson_index[user_id] = 0

    current_lesson_index[user_id] += 1
    lesson_index = current_lesson_index[user_id]

    if lesson_index < len(lessons):
        send_lesson(message.chat.id, lesson_index)
    else:
        bot.send_message(message.chat.id, "Все уроки пройдены! Ждите новых.")

# Quiz functions
@bot.message_handler(func=lambda message: message.text == "Начать квиз")
def start_quiz(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    current_quiz_index[user_id] = 0
    question_data = quiz_questions[0]
    send_quiz(message.chat.id, question_data, user_id)

def send_quiz(chat_id, question_data, user_id):
    # Send poll in QUIZ mode (without inline buttons)
    msg = bot.send_poll(
        chat_id=chat_id,
        question=question_data["question"],
        options=question_data["options"],
        is_anonymous=False,
        type='quiz',
        correct_option_id=question_data["correct_option_id"],
        open_period=60  # Poll open period in seconds
    )
    # Save information about the active quiz (poll_id)
    active_quizzes[msg.poll.id] = (user_id, chat_id, current_quiz_index[user_id])

# Handler for poll answers (PollAnswer)
@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    if poll_id not in active_quizzes:
        return  # This poll is not being tracked

    stored_user_id, chat_id, question_index = active_quizzes[poll_id]
    # If the poll does not belong to this user, ignore
    if stored_user_id != user_id:
        return

    question_data = quiz_questions[question_index]
    # If the correct option is selected:
    if poll_answer.option_ids and poll_answer.option_ids[0] == question_data["correct_option_id"]:
        del active_quizzes[poll_id]  # Delete information about this poll
    else:
        # If incorrect, send explanation
        explanation = question_data.get("explanation", "Неверный ответ.")
        bot.send_message(chat_id=chat_id, text=explanation)
        del active_quizzes[poll_id]

    # Move to the next question (regardless of the correctness of the answer)
    current_quiz_index[user_id] = question_index + 1
    if current_quiz_index[user_id] < len(quiz_questions):
        next_question_data = quiz_questions[current_quiz_index[user_id]]
        msg = bot.send_poll(
            chat_id=chat_id,
            question=next_question_data["question"],
            options=next_question_data["options"],
            is_anonymous=False,
            type='quiz',
            correct_option_id=next_question_data["correct_option_id"],
            open_period=60  # Poll open period in seconds
        )
        active_quizzes[msg.poll.id] = (user_id, chat_id, current_quiz_index[user_id])
    else:
        bot.send_message(chat_id=chat_id, text="Квиз завершён! Отличная работа!")
        del current_quiz_index[user_id]

@bot.message_handler(func=lambda message: message.text == "Помощь")
def help_command(message):
    register_user(message.chat.id)
    bot.send_message(message.chat.id, "Это помощь! Используйте кнопки: 'Начать урок', 'Следующий урок', 'Начать квиз'.")

# Handler for text messages – registers the user and selects an action
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    register_user(message.chat.id)
    text = message.text.strip().lower()
    if text == "начать урок":
        start_lesson(message)
    elif text == "следующий урок":
        next_lesson(message)
    elif text == "начать квиз":
        start_quiz(message)
    elif text == "помощь":
        help_command(message)
    else:
        bot.send_message(message.chat.id, "Извините, я не понимаю. Пожалуйста, используйте кнопки для навигации.")

# Function to send a random lesson to a specific chat (for daily mailing)
def send_random_lesson(chat_id):
    lesson_index = random.randint(0, len(lessons) - 1)
    bot.send_message(chat_id, lessons[lesson_index])

# Function that sends a random lesson to all subscribed users daily at 22:20 (Moscow time)
def send_daily_lesson():
    for chat_id in subscribed_users:
        try:
            send_random_lesson(chat_id)
        except Exception as e:
            print(f"Ошибка при отправке урока пользователю {chat_id}: {e}")

# Schedule the daily lesson sending
msk_time = dtime(hour=22, minute=20, tzinfo=ZoneInfo("Europe/Moscow"))
scheduler.add_job(send_daily_lesson, 'cron', hour=msk_time.hour, minute=msk_time.minute, timezone=msk_time.tzinfo)
scheduler.start()

# Inline query handler
@bot.inline_handler(lambda query: True)
def query_text(inline_query):
    try:
        lesson_index = random.randint(0, len(lessons) - 1)
        lesson_text = lessons[lesson_index]
        r = types.InlineQueryResultArticle(
            id='1', title="Отправить урок",
            input_message_content=types.InputTextMessageContent(message_text=lesson_text)
        )
        bot.answer_inline_query(inline_query.id, [r], cache_time=1)
    except Exception as e:
        print(f"Error handling inline query: {e}")

if __name__ == "__main__":
    bot.polling(none_stop=True)
