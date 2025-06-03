import os
import json
import random
from datetime import time as dtime
from zoneinfo import ZoneInfo
from random import shuffle
from telebot import TeleBot, types
from telebot.types import InlineQueryResultArticle, InputTextMessageContent, InputInvoiceMessageContent, ReplyKeyboardMarkup
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import re
import string

API_TOKEN = 'token' #Insert your folder location here
VOICE_LESSONS_PATH = 'voice_lessons' #Insert your folder location here
SUBSCRIBED_USERS_FILE = "subscribed_users.json"
WORDS_BASE_PATH = "Word_base.Komi.xlsx" #Insert your file location here
SCORES_FILE = "scores.json"

bot = TeleBot(API_TOKEN)
scheduler = BackgroundScheduler()
df_words = pd.read_excel(WORDS_BASE_PATH)

current_lesson_index = {}
current_quiz_index = {}
active_quizzes = {}
dictant_state = {}
scramble_state = {}

try:
    with open(SCORES_FILE, 'r') as f:
        user_scores = json.load(f)
except:
    user_scores = {}

def save_scores():
    with open(SCORES_FILE, 'w') as f:
        json.dump(user_scores, f)

def add_score(user_id, amount):
    user_id_str = str(user_id)
    user_scores[user_id_str] = user_scores.get(user_id_str, 0) + amount
    save_scores()

def get_username(user):
    if user.username:
        return f"@{user.username}"
    else:
        return f"{user.first_name}" if user.first_name else f"ID:{user.id}"

def pluralize_points(n):
    n = abs(int(n))
    if 10 < n % 100 < 20:
        return "очков"
    elif n % 10 == 1:
        return "очко"
    elif 2 <= n % 10 <= 4:
        return "очка"
    else:
        return "очков"

@bot.message_handler(commands=['rating'])
@bot.message_handler(func=lambda m: m.text == "📊 Рейтинг")
def handle_rating_button(message):
    show_rating(message)
def show_rating(message):
    if not user_scores:
        bot.send_message(message.chat.id, "Рейтинг пока пуст. Будь первым!")
        return

    sorted_scores = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)
    user_id_str = str(message.from_user.id)

    text = "🏆 Топ 20 пользователей по очкам:\n"
    found = False

    for i, (uid, score) in enumerate(sorted_scores[:20], 1):
        try:
            user = bot.get_chat(uid)
            name = get_username(user)
        except:
            name = f"Пользователь {uid}"
        if uid == user_id_str:
            found = True
            text += f"{i}. {name}: {score} {pluralize_points(score)} 👈 (это вы)\n"
        else:
            text += f"{i}. {name}: {score} {pluralize_points(score)}\n"

    # Если текущего пользователя нет в топ-20, покажи его позицию отдельно
    if not found and user_id_str in user_scores:
        for i, (uid, score) in enumerate(sorted_scores, 1):
            if uid == user_id_str:
                name = get_username(message.from_user)
                text += f"\n🔻 Вы на {i} месте с {score} {pluralize_points(score)}."
                break

    bot.send_message(message.chat.id, text)


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
    "Урок 1: 💡Вежливое приветствие.\n\nФраза: 'Видза оланныд!!' — означает 'Здравствуйте!'.\nПопробуй написать эту фразу!",
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
    "Урок 16: 👋 Простое приветствие.\n\nФраза: 'Видза олан!' — означает 'Здравствуй!'.\nЗапомни эту фразу!",
    "Урок 17: 🚪 Гостеприимство.\n\nФраза: 'Видза корам!' — означает 'Добро пожаловать!'.\nПопробуй написать эту фразу!",
    "Урок 18: 🧑 Жизнь.\n\nСлово: 'Олан' — означает 'Живёшь'.\nЗапомни это слово!",
    "Урок 19: 🙏 Простое спасибо.\n\nСлово: 'Аттьӧ' — означает 'Спасибо'.\nПопробуй написать это слово!",
    "Урок 20: 👍 Одобрение.\n\nСлово: 'Лӧсьыда' — означает 'Хорошо'.\nЗапомни это слово!",
    "Урок 21: 🙏 Нейтральная благодарность.\n\nФраза: 'Аттьӧ, шогмана' — означает 'Спасибо, нормально'.\nЗапомни эту фразу!",
    "Урок 22: 😊 Нейтральный ответ.\n\nСлово: 'Шогмана' — означает 'Нормально'.\nПопробуй написать это слово!",
    "Урок 23: 😁 Настроение.\n\nСлово: 'Шуда' — означает 'Счастливый'.\nЗапомни это слово!",
    "Урок 24: 🛣 Дорога.\n\nСлово: 'Туй' — означает 'Дорога'.\nЗапомни это слово!",
    "Урок 25: 🙏 Быть.\n\nСлово: 'Лоны' — означает 'Быть'.\nЗапомни это слово!",
    "Урок 26: 🌅 До завтра.\n\nФраза: 'Аскиӧдз!' — означает 'До завтра!'.\nПопробуй написать эту фразу!",
    "Урок 27: 😴 Пожелание на сон.\n\nФраза: 'Бура узьны! Чӧскыд ун!' — означает 'Хорошего сна! Приятных снов!'.\nЗапомни эту фразу!",
    "Урок 28: 📆 Время.\n\nСлово: 'Лун' — означает 'День'.\nЗапомни это слово!",
    "Урок 29: 🚗 Пожелание на дорогу.\n\nФраза: 'Шуда туй!' — означает 'Счастливого пути!'.\nПопробуй написать эту фразу!",
    "Урок 30: 😢 Скучание.\n\nФраза: 'Гажтӧмтча!' — означает 'Скучаю!'.\nПопробуй написать эту фразу!",
    "Урок 31: ✍️ Обращение.\n\nСлово: 'Гиж!' — означает 'Пиши!'.\nПопробуй написать это слово!",
    "Урок 32: 📞 Связь.\n\nСлово: 'Триньӧбты!' — означает 'Звони!'.\nПопробуй написать это слово!",
    "Урок 33: 💌 Ласковое обращение.\n\nСлово: 'Дона' — означает 'Дорогой'.\nЗапомни это слово!",
    "Урок 34: 💌 Ласковое обращение (мой).\n\nФраза: 'Донаӧй!' — означает 'Дорогой мой!'.\nПопробуй использовать её в предложении!",
    "Урок 35: 💖 Милый.\n\nФраза: 'Мусаӧй!' — означает 'Милый мой!'.\nЗапомни эту фразу!",
    "Урок 36: 👬 Дружба.\n\nФраза: 'Ёртӧй!' — означает 'Друг мой!'.\nПопробуй написать эту фразу!",
    "Урок 37: 👨 Человек.\n\nФраза: 'Бур морт!' — означает 'Хороший(-ая)!'.\nЗапомни эту фразу!",
]

def normalize_phrase(text):
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘!?.,:;–—()[]{}"\'')
    return text.lower().translate(table).replace("ё", "е").replace(" ", "").strip()

# Получаем нормализованные коми-фразы из lessons
existing_phrases_normalized = set()
for lesson in lessons:
    match = re.search(r"[\"'](.+?)[\"']", lesson)
    if match:
        phrase = normalize_phrase(match.group(1))
        existing_phrases_normalized.add(phrase)

# Автоуроки на основе таблицы, исключая уже встречавшиеся фразы
auto_lessons = []
lesson_counter = len(lessons) + 1

for _, row in df_words.iterrows():
    komi = str(row.get("value", "")).strip()
    ru = str(row.get("translate_ru", "")).strip()

    if komi and ru and normalize_phrase(komi) not in existing_phrases_normalized:
        auto_lessons.append(
            f"Урок {lesson_counter}:\n\nФраза: '{komi}' — означает '{ru}'.\nПопробуй написать эту фразу!"
        )
        lesson_counter += 1

lessons += auto_lessons

@bot.message_handler(commands=['lesson'])
def send_specific_lesson(message):
    register_user(message.chat.id)
    try:
        command_parts = message.text.strip().split()
        if len(command_parts) != 2:
            raise ValueError("Формат: /lesson номер")
        number = int(command_parts[1])
        if 1 <= number <= len(lessons):
            send_lesson_with_voice(message.chat.id, number - 1)
        else:
            bot.send_message(message.chat.id, f"Урока с номером {number} не существует. Всего уроков: {len(lessons)}.")
    except Exception as e:
        bot.send_message(message.chat.id, "Используйте формат: /lesson 5")


# Quiz questions with added "explanation" field
quiz_questions = [
    {
        "question": "Как переводится 'Чолӧм!'?",
        "options": ["Спасибо", "До свидания", "Привет", "Год"],
        "correct_option_id": 2,
        "explanation": "Правильный ответ: Привет. 'Чолӧм!' — это приветствие."
    },
    {
        "question": "Как по-коми будет 'Спасибо'?",
        "options": ["Бура", "Аттьӧ", "Став", "Шогмана"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Аттьӧ."
    },
    {
        "question": "Что значит 'Видза корам!'?",
        "options": ["С днём рождения!", "Спасибо!", "Добро пожаловать!", "До завтра!"],
        "correct_option_id": 2,
        "explanation": "Правильный ответ: Добро пожаловать!."
    },
    {
        "question": "Как переводится 'Радпырысь корам!'?",
        "options": ["Поздравляю!", "Добрый путь!", "С радостью приглашаем!", "Живёшь!"],
        "correct_option_id": 2,
        "explanation": "Правильный ответ: С радостью приглашаем!"
    },
    {
        "question": "Что значит 'Бур вой!'?",
        "options": ["Добрый день!", "Доброй ночи!", "Пиши!", "До встречи!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Доброй ночи!"
    },
    {
        "question": "Что по-коми означает 'Кыдзи олан?'",
        "options": ["Как дела?", "Где живёшь?", "Что делаешь?", "Как тебя зовут?"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Как дела? (Как поживаешь?)"
    },
    {
        "question": "Как сказать по-коми 'До встречи!'?",
        "options": ["Аддзысьлытӧдз!", "Триньӧбты!", "Шуда туй!", "Гиж!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Аддзысьлытӧдз!"
    },
    {
        "question": "Что по-коми 'Звони!'?",
        "options": ["Гиж!", "Триньӧбты!", "Шуда туй!", "Видза ло!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Триньӧбты!"
    },
    {
        "question": "Как переводится 'Шуда'?",
        "options": ["Добрый", "Счастливый", "Год", "Друг"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Счастливый."
    },
    {
        "question": "Что значит 'Донаӧй!'?",
        "options": ["Мужчина!", "Дорогой мой!", "Сынок!", "Спасибо!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Дорогой мой!"
    },
    {
        "question": "Как переводится 'Гажтӧмтча!'?",
        "options": ["Скучаю!", "Поздравляю!", "Девушка!", "До завтра!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Скучаю!"
    },
    {
        "question": "Что по-коми 'Дети!'?",
        "options": ["Челядь!", "Пиукӧй!", "Нылукӧй!", "Ёртъяс!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Челядь!"
    },
    {
        "question": "Как будет по-коми 'Год'?",
        "options": ["Выль", "Во", "Воас", "Ло"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Во."
    },
    {
        "question": "Что по-коми 'Пиши!'?",
        "options": ["Гиж!", "Триньӧбты!", "Ныланӧй!", "Во!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Гиж!"
    },
    {
        "question": "Как сказать 'Спасибо, хорошо' по-коми?",
        "options": ["Аттьӧ, бура", "Видза оланныд", "Бур вой", "Став бурсӧ"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Аттьӧ, бура"
    },
    {
        "question": "Что значит по-коми 'Шогмана'?",
        "options": ["Нормально", "Добрый", "Пиши!", "Спасибо"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Нормально."
    },
    {
        "question": "Как будет 'Счастливого пути!' на коми?",
        "options": ["Шуда туй!", "Видза оланныд!", "Гажтӧмтча!", "Аддзысьлытӧдз!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Шуда туй!"
    },
    {
        "question": "Что по-коми означает 'Бура узьны! Чӧскыд ун!'?",
        "options": ["До встречи!", "Хорошего сна! Приятных снов!", "Пиши!", "До завтра!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Хорошего сна! Приятных снов!"
    },
    {
        "question": "Как по-коми сказать 'Девушка!'?",
        "options": ["Пиукӧй!", "Ныланӧй!", "Донаӧй!", "Ёртӧй!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Ныланӧй!"
    },
    {
        "question": "Что значит 'Пыдди пуктана ёртъяс!'?",
        "options": ["Пиши друзьям!", "Уважаемые друзья!", "Друг мой!", "Дети!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Уважаемые друзья!"
    },
    {
        "question": "Как переводится 'Мусаӧй!'?",
        "options": ["Милый мой!", "Дорогой!", "Год!", "Дорога!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Милый мой!"
    },
    {
        "question": "Что значит по-коми 'Бур морт!'?",
        "options": ["Дорогой мой!", "Мужчина!", "Друг мой!", "Пиши!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Мужчина!"
    },
    {
        "question": "Как будет по-коми 'Друг мой!'?",
        "options": ["Ёртӧй!", "Пиукӧй!", "Донаӧй!", "Аддзысьлытӧдз!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Ёртӧй!"
    },
    {
        "question": "Что по-коми 'Дети!'?",
        "options": ["Ёртъяс!", "Челядь!", "Аслыд аттьӧ!", "Тайӧ вывті этша"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Челядь!"
    },
    {
        "question": "Что значит 'Аскиӧдз!'?",
        "options": ["До встречи!", "До завтра!", "Скучаю!", "Пожалуйста!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: До завтра!"
    },
    {
        "question": "Как переводится 'Гиж!'?",
        "options": ["Звони!", "Пиши!", "Живёшь!", "Спасибо!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Пиши!"
    },
    {
        "question": "Что по-коми 'Год'?",
        "options": ["во", "ло", "туй", "шогмана"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: во."
    },
    {
        "question": "Как будет по-коми 'Дорога'?",
        "options": ["туй", "во", "ло", "Гиж!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: туй."
    },
    {
        "question": "Что значит 'Шань, бур'?",
        "options": ["Счастливый", "Милый мой", "До встречи", "Хороший, добрый"],
        "correct_option_id": 3,
        "explanation": "Правильный ответ: Хороший, добрый."
    },
    {
        "question": "Как переводится 'Видза ло!'?",
        "options": ["Счастливого пути!", "Будь здоров!", "Спасибо, хорошо", "До завтра!"],
        "correct_option_id": 1,
        "explanation": "Правильный ответ: Будь здоров!"
    },
    {
        "question": "Что означает 'Кутшӧм лунӧ коми кывйысь экзамен?'?",
        "options": ["Когда экзамен по коми языку?", "Как дела?", "До свидания!", "Спасибо!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Когда экзамен по коми языку?"
    },
    {
        "question": "Как будет 'До завтра!' на коми?",
        "options": ["Аскиӧдз!", "Аддзысьлытӧдз!", "Шуда туй!", "Бур вой!"],
        "correct_option_id": 0,
        "explanation": "Правильный ответ: Аскиӧдз!"
    },
]

# Автоматически сгенерированные квизы из таблицы
used_word_indices = set()
question_templates_ru_to_komi = [
    "Как по-коми сказать: '{ru}'?",
    "Как будет на коми: '{ru}'?",
    "Переведи на коми: '{ru}'",
    "Что на коми означает фраза: '{ru}'?",
    "Как звучит по-коми: '{ru}'?"
]

question_templates_komi_to_ru = [
    "Как переводится с коми: '{komi}'?",
    "Что значит слово '{komi}'?",
    "Как понять: '{komi}'?",
    "Что означает '{komi}'?",
    "Как перевести: '{komi}'?"
]

def generate_auto_quiz():
    for idx, row in df_words.iterrows():
        if idx in used_word_indices:
            continue
        komi = str(row.get("value", "")).strip()
        ru = str(row.get("translate_ru", "")).strip()
        if not komi or not ru or ' ' in komi or ' ' in ru:
            continue

        used_word_indices.add(idx)
        if random.random() < 0.5:
            question = random.choice(question_templates_ru_to_komi).format(ru=ru)
            correct = komi
            options = [komi] + random.sample(
                [str(df_words.iloc[i]['value']) for i in random.sample(range(len(df_words)), 10)
                 if i != idx and isinstance(df_words.iloc[i]['value'], str)], 3)
        else:
            question = random.choice(question_templates_komi_to_ru).format(komi=komi)
            correct = ru
            options = [ru] + random.sample(
                [str(df_words.iloc[i]['translate_ru']) for i in random.sample(range(len(df_words)), 10)
                 if i != idx and isinstance(df_words.iloc[i]['translate_ru'], str)], 3)

        random.shuffle(options)
        correct_option_id = options.index(correct)

        quiz_questions.append({
            "question": question,
            "options": options,
            "correct_option_id": correct_option_id,
            "explanation": f"Правильный ответ: {correct}"
        })

random.seed(42)
generate_auto_quiz()

from random import shuffle

def is_single_word(word):
    word = str(word)
    word_clean = re.sub(r"[^\wӧӱӓӭёäöüʼ'-]", '', word, flags=re.IGNORECASE)
    return ' ' not in word_clean and len(word_clean) > 0 and word_clean == word

filtered_words = [
    (re.sub(r"[^\wӧӱӓӭёäöüʼ'-]", '', str(row['value'])), row['translate_ru'])
    for _, row in df_words.iterrows()
    if is_single_word(row['value']) and isinstance(row['translate_ru'], str)
]

@bot.message_handler(commands=['scramble'])
def scramble_task(message):
    user_id = message.from_user.id
    if not filtered_words:
        bot.send_message(message.chat.id, "Нет подходящих слов в базе.")
        return
    # Проходим по всем словам в случайном порядке до выхода или конца базы
    words_order = list(range(len(filtered_words)))
    random.shuffle(words_order)
    scramble_state[user_id] = {
        'indices': words_order,
        'current': 0,
        'correct': 0,
        'waiting_answer': False
    }
    send_next_scramble(message.chat.id, user_id)

def send_next_scramble(chat_id, user_id):
    state = scramble_state.get(user_id)
    if not state or state['current'] >= len(state['indices']):
        score = state['correct']
        bot.send_message(chat_id, f"Раунд окончен! Ты собрал правильно {score} слов из {len(state['indices'])}. Вернуться в меню — кнопка ниже.")
        scramble_state.pop(user_id, None)
        return

    idx = state['indices'][state['current']]
    word, translation = filtered_words[idx]
    letters = list(word)
    random.shuffle(letters)
    scrambled = " ".join(f"[{l}]" for l in letters)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("В меню")
    bot.send_message(
        chat_id,
        f"Собери слово по переводу: «{translation}»\nБуквы вперемешку: {scrambled}\nВведи слово:",
        reply_markup=kb
    )
    state['answer'] = word
    state['waiting_answer'] = True

@bot.message_handler(func=lambda m: scramble_state.get(m.from_user.id, {}).get('waiting_answer', False))
def scramble_answer(message):
    user_id = message.from_user.id
    state = scramble_state.get(user_id)
    if not state:
        return
    if message.text.strip().lower() == "в меню":
        bot.send_message(message.chat.id, "Вы вышли в главное меню. Раунд отменён.")
        scramble_state.pop(user_id, None)
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("🧠Начать урок", "📘Следующий урок")
        keyboard.add("✅Начать квиз", "🎧Диктант")
        keyboard.add("🔤 Собери слово", "📊 Рейтинг", "⚙️Помощь")
        bot.send_message(message.chat.id, "Чолӧм, я бот для изучения коми языка! Выберите действие:", reply_markup=keyboard)
        return
    else:
        user_norm = normalize_text(message.text)
        answer_norm = normalize_text(state['answer'])
        if user_norm == answer_norm:
            state['correct'] += 1
            add_score(user_id, 5)  # +5 очков за правильное слово в scramble

            bot.send_message(message.chat.id, "Бур! Всё правильно, ты собрал слово верно")
        else:
            bot.send_message(message.chat.id, f"Нет, правильный ответ: {state['answer']}. Возможно вы используете Ӧ или і из латинской расскладки, а не из кириллической.")

    state['current'] += 1
    state['waiting_answer'] = False
    send_next_scramble(message.chat.id, user_id)

DICTANT_QUESTIONS = 37

def normalize_text(text):
    # Вырезаем все знаки препинания и переводим в нижний регистр
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘' + "!?.,:;–—()[]{}\"'")  # на все случаи жизни
    # Удаляем лишние пробелы, убираем точки, запятые, кавычки, приведение к lower
    clean = text.lower().translate(table).replace("ё", "е")
    clean = " ".join(clean.split())  # заменяем множественные пробелы на один
    return clean.strip()

@bot.message_handler(func=lambda m: m.text == "🎧Диктант")
def start_dictant(message):
    user_id = message.from_user.id
    register_user(message.chat.id)
    indices = random.sample(range(37), DICTANT_QUESTIONS)
    dictant_state[user_id] = {
        'indices': indices,
        'current': 0,
        'correct': 0,
        'waiting_answer': False
    }
    send_next_dictant(message.chat.id, user_id)

# Кнопка теперь "В меню":
def send_next_dictant(chat_id, user_id):
    state = dictant_state.get(user_id)
    if not state or state['current'] >= DICTANT_QUESTIONS:
        score = state['correct']
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("В меню")
        bot.send_message(chat_id, f"Диктант окончен! Ты угадал {score} из {DICTANT_QUESTIONS}. Вернуться в меню - кнопка ниже", reply_markup=kb)
        state['waiting_answer'] = True
        return

    idx = state['indices'][state['current']]
    m = re.search(r"['\"](.+?)['\"]", lessons[idx])
    correct_text = m.group(1) if m else ""
    state['answer'] = correct_text

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("В меню")
    bot.send_voice(chat_id, open(os.path.join(VOICE_LESSONS_PATH, f'lesson{idx+1}.ogg'), 'rb'),
                   caption=f"Диктант {state['current']+1} из {DICTANT_QUESTIONS}.\nВведи услышанное предложение.",
                   reply_markup=kb)
    state['waiting_answer'] = True

@bot.message_handler(func=lambda m: dictant_state.get(m.from_user.id, {}).get('waiting_answer', False))
def dictant_answer(message):
    user_id = message.from_user.id
    state = dictant_state.get(user_id)
    if not state:
        return

    if message.text.strip().lower() == "в меню":
        bot.send_message(message.chat.id, "Вы вышли в главное меню. Диктант отменён.")
        dictant_state.pop(user_id, None)
        # Отправляем меню (то же, что /start)
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("🧠Начать урок", "📘Следующий урок")
        keyboard.add("✅Начать квиз", "🎧Диктант")
        keyboard.add("🔤 Собери слово", "📊 Рейтинг", "⚙️Помощь")
        bot.send_message(message.chat.id, "Чолӧм, я бот для изучения коми языка! Выберите действие:", reply_markup=keyboard)
        return
    else:
        user_norm = normalize_text(message.text)
        answer_norm = normalize_text(state['answer'])
        if user_norm == answer_norm:
            state['correct'] += 1
            add_score(user_id, 7)  # +7 очков за правильный ответ в диктанте
            bot.send_message(message.chat.id, "Зэв бур! Ты верно услышал и записал!")
        else:
            bot.send_message(message.chat.id, f"Нет, правильный ответ: {state['answer']}\nВозможно вы используете Ӧ или і из латинской расскладки, а не из кириллической.\n Попробуй ещё раз!")

    state['current'] += 1
    state['waiting_answer'] = False
    send_next_dictant(message.chat.id, user_id)

# Handler for /start command
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.chat.id)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🧠Начать урок", "📘Следующий урок")
    keyboard.add("✅Начать квиз", "🎧Диктант")
    keyboard.add("🔤 Собери слово", "📊 Рейтинг", "⚙️Помощь")

    bot.send_message(message.chat.id, "Чолӧм, я бот для изучения коми языка! Выберите действие:", reply_markup=keyboard)

# Кнопка "Собери слово" вызывает scramble-режим
@bot.message_handler(func=lambda message: message.text == "🔤 Собери слово")
def menu_scramble(message):
    scramble_task(message)


def send_lesson_with_voice(chat_id, lesson_index):
    bot.send_message(chat_id, lessons[lesson_index])
    voice_file = f"lesson{lesson_index + 1}.ogg"
    voice_path = os.path.join(VOICE_LESSONS_PATH, voice_file)
    if os.path.exists(voice_path):
        try:
            with open(voice_path, 'rb') as audio:
                bot.send_voice(chat_id, audio, caption="🔊 Прослушайте произношение фразы")
        except Exception as e:
            bot.send_message(chat_id, "Извините, не удалось отправить аудио для этого урока.")
    else:
        bot.send_message(chat_id, "Извините, аудио для этого урока отсутствует.")

@bot.message_handler(func=lambda message: message.text == "🧠Начать урок")
def start_lesson(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    # Reset the lesson index to 0 when starting lessons
    current_lesson_index[user_id] = 0
    lesson_index = current_lesson_index[user_id]
    if lesson_index < len(lessons):
        send_lesson_with_voice(message.chat.id, lesson_index)
    else:
        bot.send_message(message.chat.id, "Все уроки пройдены! Ждите новых.")

@bot.message_handler(func=lambda message: message.text == "📘Следующий урок")
def next_lesson(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    if user_id not in current_lesson_index:
        current_lesson_index[user_id] = 0
    current_lesson_index[user_id] += 1
    lesson_index = current_lesson_index[user_id]
    if lesson_index < len(lessons):
        send_lesson_with_voice(message.chat.id, lesson_index)
    else:
        bot.send_message(message.chat.id, "Все уроки пройдены! Ждите новых. ")

# Quiz functions
@bot.message_handler(func=lambda message: message.text == "✅Начать квиз")
def start_quiz(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    current_quiz_index[user_id] = 0
    question_data = quiz_questions[0]
    send_quiz(message.chat.id, question_data, user_id)

def send_quiz(chat_id, question_data, user_id):
    msg = bot.send_poll(
        chat_id=chat_id,
        question=question_data["question"],
        options=question_data["options"],
        is_anonymous=False,
        type='quiz',
        correct_option_id=question_data["correct_option_id"],
        open_period=60
    )
    active_quizzes[msg.poll.id] = (user_id, chat_id, current_quiz_index[user_id])

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    if poll_id not in active_quizzes:
        return
    stored_user_id, chat_id, question_index = active_quizzes[poll_id]
    if stored_user_id != user_id:
        return
    question_data = quiz_questions[question_index]
    if poll_answer.option_ids and poll_answer.option_ids[0] == question_data["correct_option_id"]:
        add_score(user_id, 4)  # +4 очка за правильный ответ в квизе
        del active_quizzes[poll_id]
    else:
        explanation = question_data.get("explanation", "Неверный ответ.")
        bot.send_message(chat_id=chat_id, text=explanation)
        del active_quizzes[poll_id]
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
            open_period=60
        )
        active_quizzes[msg.poll.id] = (user_id, chat_id, current_quiz_index[user_id])
    else:
        bot.send_message(chat_id=chat_id, text="Квиз завершён! Отличная работа!")
        del current_quiz_index[user_id]

@bot.message_handler(func=lambda message: message.text == "⚙️Помощь")
def help_command(message):
    register_user(message.chat.id)
    help_text = """
🤖 Это бот для изучения коми языка. Вот что умеют кнопки в меню:\n\n\n🧠 Начать урок - начать изучение с первого урока\n\n📘 Следующий урок - перейти к следующему уроку\n\n✅ Начать квиз - проверить знания в формате теста\n\n🎧 Диктант - прослушать аудио и написать услышанную фразу\n\n🔤 Собери слово - игра на составление слов из перемешанных букв\n\n⚙️ Помощь - показать это сообщение\n\n\nКаждый урок содержит фразу на коми языке с переводом и аудио произношением.\nУчитесь, практикуйтесь и наслаждайтесь процессом! 😊
    """
    bot.send_message(message.chat.id, help_text)

def send_random_lesson(chat_id):
    lesson_index = random.randint(0, len(lessons) - 1)
    bot.send_message(chat_id, lessons[lesson_index])
    voice_file = f"lesson{lesson_index + 1}.ogg"
    voice_path = os.path.join(VOICE_LESSONS_PATH, voice_file)
    if os.path.exists(voice_path):
        try:
            with open(voice_path, 'rb') as audio:
                bot.send_voice(chat_id, audio, caption="🔊 Прослушайте произношение фразы")
        except Exception as e:
            bot.send_message(chat_id, "Извините, не удалось отправить аудио для этого урока.")
    else:
        bot.send_message(chat_id, "Извините, аудио для этого урока отсутствует.")

def send_daily_lesson():
    for chat_id in subscribed_users:
        try:
            send_random_lesson(chat_id)
        except Exception as e:
            print(f"Ошибка при отправке урока пользователю {chat_id}: {e}")

msk_time = dtime(hour=22, minute=20, tzinfo=ZoneInfo("Europe/Moscow"))
scheduler.add_job(send_daily_lesson, 'cron', hour=msk_time.hour, minute=msk_time.minute, timezone=msk_time.tzinfo)
scheduler.start()

@bot.inline_handler(lambda query: True)
def query_text(inline_query):
    try:
        lesson_index = random.randint(0, len(lessons) - 1)
        lesson_text = lessons[lesson_index]
        voice_file = f"lesson{lesson_index + 1}.ogg"
        voice_path = os.path.join(VOICE_LESSONS_PATH, voice_file)
        if os.path.exists(voice_path):
            with open(voice_path, 'rb') as audio:
                voice_content = InputTextMessageContent(message_text=lesson_text)
                r = types.InlineQueryResultArticle(
                    id='1',
                    title="Отправить урок с голосовым сообщением",
                    input_message_content=voice_content
                )
                bot.answer_inline_query(inline_query.id, [r], cache_time=1)
        else:
            r = types.InlineQueryResultArticle(
                id='1', title="Отправить урок",
                input_message_content=types.InputTextMessageContent(message_text=lesson_text)
            )
            bot.answer_inline_query(inline_query.id, [r], cache_time=1)
    except Exception as e:
        print(f"Error handling inline query: {e}")

if __name__ == "__main__":
    bot.polling(none_stop=True)
