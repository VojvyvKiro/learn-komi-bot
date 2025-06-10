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

API_TOKEN = 'token' #Insert your token here
AUDIO_PATH = "voice_lessons" #Insert your folder location here
SUBSCRIBED_USERS_FILE = "subscribed_users.json"
UNITS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRUS3NpoMDo8CSULPn3cBm12wYX1p-8yAWzZaYizQn3G_F7-_Zpd5EduOiQFe9-1vqMQiA9JHgzsJPC/pub?gid=0&single=true&output=csv"
GROUPS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRUS3NpoMDo8CSULPn3cBm12wYX1p-8yAWzZaYizQn3G_F7-_Zpd5EduOiQFe9-1vqMQiA9JHgzsJPC/pub?gid=1530881854&single=true&output=csv"
SCORES_FILE = "scores.json"

bot = TeleBot(API_TOKEN)
scheduler = BackgroundScheduler()
df_units = pd.read_csv(UNITS)
df_groups = pd.read_csv(GROUPS)
auto_lessons_ids = []
group_id_to_name = {row['group_id']: row['name_ru'] for _, row in df_groups.iterrows()}

# Dictionaries to track user progressсс
current_lesson_index = {}
current_quiz_index = {}
active_quizzes = {}
dictant_state = {}
scramble_state = {}

lessons = []
audio_ids = []

for _, row in df_units.iterrows():
    komi = str(row.get("value", "")).strip()
    ru = str(row.get("translate_ru", "")).strip()
    audio_id = row.get("_id")
    group_id = row.get("group_id")

    # Получаем название раздела (если есть, иначе "Без раздела")
    group_name = group_id_to_name.get(group_id, "Без раздела")

    # Пропускаем пустое/битое
    if komi and ru and pd.notnull(audio_id):
        lesson_number = len(lessons) + 1
        lessons.append(
            f"Урок {lesson_number}: {group_name}\n\nФраза: '{komi}' — означает '{ru}'.\nПопробуйте написать эту фразу!"
        )
        audio_ids.append(int(audio_id))

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
                text += f"\n🔻 Вы на {i} месте с {score} очками."
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

def normalize_text(text):
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘' + "!?.,:;–—()[]{}\"'")
    clean = text.lower().translate(table).replace("ё", "е")
    clean = " ".join(clean.split())
    return clean.strip()

def normalize_phrase(text):
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘!?.,:;–—()[]{}"\'')
    return text.lower().translate(table).replace("ё", "е").replace(" ", "").strip()

# Получаем нормализованные коми-фразы из lessons
existing_phrases_normalized = set()
for lesson in lessons:
    match = re.search(r"[\"'](.+?)[\"']", lesson)
    if match:
        phrase = normalize_text(match.group(1))
        existing_phrases_normalized.add(phrase)
        
auto_lessons = []
auto_lessons_ids = []
lesson_counter = len(lessons) + 1

for _, row in df_units.iterrows():
    komi = str(row.get("value", "")).strip()
    ru = str(row.get("translate_ru", "")).strip()
    audio_id = row.get("_id")
    if komi and ru and normalize_phrase(komi) not in existing_phrases_normalized and pd.notnull(audio_id):
        group_id = row.get("group_id")
        group_name = group_id_to_name.get(group_id, "Без раздела")
        auto_lessons.append(
            f"Урок {lesson_counter}: {group_name}\n\nФраза: '{komi}' — означает '{ru}'.\nПопробуйте написать эту фразу!"
        )
        auto_lessons_ids.append(int(audio_id))
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
            user_id = message.from_user.id
            current_lesson_index[user_id] = number
            save_lesson_progress()
        else:
            bot.send_message(message.chat.id, f"Урока с номером {number} не существует. Всего уроков: {len(lessons)}.")
    except Exception as e:
        bot.send_message(message.chat.id, "Используйте формат: /lesson 5")


# Quiz questions (автоматически генерируемые)
quiz_questions = []

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
    for idx, row in df_units.iterrows():
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
                [str(df_units.iloc[i]['value']) for i in random.sample(range(len(df_units)), 10)
                 if i != idx and isinstance(df_units.iloc[i]['value'], str)], 3)
        else:
            question = random.choice(question_templates_komi_to_ru).format(komi=komi)
            correct = ru
            options = [ru] + random.sample(
                [str(df_units.iloc[i]['translate_ru']) for i in random.sample(range(len(df_units)), 10)
                 if i != idx and isinstance(df_units.iloc[i]['translate_ru'], str)], 3)

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
    for _, row in df_units.iterrows()
    if is_single_word(row['value']) and isinstance(row['translate_ru'], str)
]

def contains_latin_oi(text):
    # Латинская Ö: U+00D6, U+00F6; латинская I: U+0049, U+0069
    # Кириллическая Ӧ: U+04E6, U+04E7; кириллическая І: U+0406, U+0456
    for ch in text:
        code = ord(ch)
        # Латинская Ö/ö
        if code in (0x00D6, 0x00F6):
            return True
        # Латинская I/i
        if code in (0x0049, 0x0069):
            # Но не если это часть латиницы в английском слове, а если в коми слове
            return True
    return False

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
        bot.send_message(chat_id, f"Раунд окончен! Вы собрали правильно {score} слов из {len(state['indices'])}. Вернуться в меню — кнопка ниже.")
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
        f"Собери слово по переводу: «{translation}»\nБуквы вперемешку: {scrambled}\nВведите слово:",
        reply_markup=kb
    )
    state['answer'] = word
    state['waiting_answer'] = True

all_lessons_info = []
for i in range(len(audio_ids)):
    m = re.search(r"['\"](.+?)['\"]", lessons[i])
    komi_text = m.group(1) if m else ""
    all_lessons_info.append({
        "komi": komi_text,
        "audio_id": audio_ids[i]
    })

@bot.message_handler(func=lambda m: m.text == "🎧Диктант")
def start_dictant(message):
    user_id = message.from_user.id
    register_user(message.chat.id)
    indices = list(range(len(all_lessons_info)))
    random.shuffle(indices)
    dictant_state[user_id] = {
        'indices': indices,
        'current': 0,
        'correct': 0,
        'waiting_answer': False
    }
    send_next_dictant(message.chat.id, user_id)

def send_next_dictant(chat_id, user_id):
    state = dictant_state.get(user_id)
    if not state:
        # Новый раунд: случайный порядок фраз
        indices = list(range(len(dictant_phrases)))
        random.shuffle(indices)
        dictant_state[user_id] = {
            'indices': indices,
            'current': 0,
            'correct': 0,
            'waiting_answer': False
        }
        state = dictant_state[user_id]
    while state['current'] < len(state['indices']):
        idx = state['indices'][state['current']]
        komi, translation, audio_id = dictant_phrases[idx]
        voice_path = os.path.join(AUDIO_PATH, f"{audio_id}.ogg")
        if os.path.exists(voice_path):
            kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.add("В меню")
            caption = f"Диктант {state['current']+1}.\nВведи услышанное предложение:"
            with open(voice_path, 'rb') as audio:
                bot.send_voice(chat_id, audio, caption=caption, reply_markup=kb)
            state['answer'] = komi
            state['waiting_answer'] = True
            return
        else:
            # Если аудио нет, просто переходим к следующему слову
            state['current'] += 1

    # Если все фразы закончились или не осталось с аудио
    score = state['correct']
    dictant_state.pop(user_id, None)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("В меню")
    bot.send_message(chat_id, f"Диктант окончен! Вы правильно написали {score} из {len(state['indices'])} фраз.", reply_markup=kb)

# Собираем автоуроки
for i in range(len(auto_lessons)):
    m = re.search(r"['\"](.+?)['\"]", auto_lessons[i])
    komi_text = m.group(1) if m else ""
    audio_id = auto_lessons_ids[i]
    all_lessons_info.append({
        "komi": komi_text,
        "audio_id": audio_id
    })

# --- Поиск перевода по коми-фразе ---
def find_translation(komi_text):
    norm_komi = normalize_text(komi_text)
    # 1. Поиск в filtered_words
    for w, t in filtered_words:
        if normalize_text(w) == norm_komi:
            return t
    # 2. Поиск в all_lessons_info + df_units
    for row in df_units.itertuples():
        if normalize_text(str(row.value)) == norm_komi:
            return str(row.translate_ru)
    return None
# --- конец поиска перевода ---

# Для диктанта используем все фразы, а не только слова

dictant_phrases = [
    (info['komi'], find_translation(info['komi']), info['audio_id'])
    for info in all_lessons_info
    if info['komi'] and info['audio_id']
]

@bot.message_handler(func=lambda m: scramble_state.get(m.from_user.id, {}).get('waiting_answer', False))
def scramble_answer(message):
    user_id = message.from_user.id
    state = scramble_state.get(user_id)
    if not state:
        return
    if message.text.strip().lower() == "в меню":
        scramble_state.pop(user_id, None)
        start(message)
        return
    else:
        user_norm = normalize_text(message.text)
        answer_norm = normalize_text(state['answer'])
        warn = ""
        if contains_latin_oi(message.text):
            warn = "\n⚠️ Похоже, вы используете латинские буквы Ö или i вместо кириллических. Подробнее о коми-раскладке: http://wiki.fu-lab.ru/index.php/Коми_раскладка_клавиатуры"
        idx = state['indices'][state['current']]
        word, _ = filtered_words[idx]
        translation = find_translation(word)
        word_bold = f"<b>{word}</b>"
        if user_norm == answer_norm:
            state['correct'] += 1
            add_score(user_id, 5)
            bot.send_message(
                message.chat.id,
                f"Зэв бур! 🎉 Всё правильно!\n\n{word_bold} — {translation if translation else '-'}{warn}",
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                message.chat.id,
                f"❌ Нет, правильный ответ:\n\n{word_bold} — {translation if translation else '-'}{warn}",
                parse_mode="HTML"
            )
    state['current'] += 1
    state['waiting_answer'] = False
    send_next_scramble(message.chat.id, user_id)

@bot.message_handler(func=lambda m: dictant_state.get(m.from_user.id, {}).get('waiting_answer', False))
def dictant_answer(message):
    user_id = message.from_user.id
    state = dictant_state.get(user_id)
    if not state:
        return

    if message.text.strip().lower() == "в меню":
        dictant_state.pop(user_id, None)
        start(message)
        return
    else:
        user_norm = normalize_text(message.text)
        answer_norm = normalize_text(state['answer'])
        warn = ""
        if contains_latin_oi(message.text):
            warn = "\n⚠️ Похоже, вы используете латинские буквы Ö или I вместо кириллических Ӧ или І. Подробнее о коми-раскладке: http://wiki.fu-lab.ru/index.php/Коми_раскладка_клавиатуры"
        komi_text = state['answer']
        translation = find_translation(komi_text)
        komi_bold = f"<b>{komi_text}</b>"
        if user_norm == answer_norm:
            state['correct'] += 1
            add_score(user_id, 7)
            bot.send_message(
                message.chat.id,
                f"Зэв бур! ✅ Всё верно!\n\n{komi_bold} — {translation if translation else '-'}{warn}\nИдём дальше!",
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                message.chat.id,
                f"❌ Нет, правильный ответ:\n\n{komi_bold} — {translation if translation else '-'}{warn}\nПопробуйте ещё раз!",
                parse_mode="HTML"
            )
    state['current'] += 1
    state['waiting_answer'] = False
    send_next_dictant(message.chat.id, user_id)

def save_lesson_progress():
    with open(LESSON_PROGRESS_FILE, 'w') as f:
        json.dump(current_lesson_index, f)

def save_quiz_progress():
    with open(QUIZ_PROGRESS_FILE, 'w') as f:
        json.dump(quiz_progress, f)

def save_subscribed_users(users: set):
    with open(SUBSCRIBED_USERS_FILE, "w") as f:
        json.dump(list(users), f)

def load_subscribed_users() -> set:
    try:
        with open(SUBSCRIBED_USERS_FILE, "r") as f:
            users = json.load(f)
            return set(users)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def register_user(chat_id):
    if chat_id not in subscribed_users:
        subscribed_users.add(chat_id)
        save_subscribed_users(subscribed_users)

def normalize_text(text):
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘' + "!?.,:;–—()[]{}\"'")
    clean = text.lower().translate(table).replace("ё", "е")
    clean = " ".join(clean.split())
    return clean.strip()

def normalize_phrase(text):
    table = str.maketrans('', '', string.punctuation + '«»—…–‐‑“”’‘!?.,:;–—()[]{}"\'')
    return text.lower().translate(table).replace("ё", "е").replace(" ", "").strip()

# --- NEW: Progress persistence ---
LESSON_PROGRESS_FILE = "lesson_progress.json"
QUIZ_PROGRESS_FILE = "quiz_progress.json"

# user_id: lesson_index
try:
    with open(LESSON_PROGRESS_FILE, 'r') as f:
        current_lesson_index = json.load(f)
        current_lesson_index = {int(k): v for k, v in current_lesson_index.items()}
except:
    current_lesson_index = {}

def save_lesson_progress():
    with open(LESSON_PROGRESS_FILE, 'w') as f:
        json.dump(current_lesson_index, f)

# user_id: {"current": int, "passed": [int]}
try:
    with open(QUIZ_PROGRESS_FILE, 'r') as f:
        quiz_progress = json.load(f)
        quiz_progress = {int(k): v for k, v in quiz_progress.items()}
except:
    quiz_progress = {}

def save_quiz_progress():
    with open(QUIZ_PROGRESS_FILE, 'w') as f:
        json.dump(quiz_progress, f)
# --- END progress persistence ---

# Handler for /start command
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.chat.id)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📘Урок")
    keyboard.add("✅Начать квиз", "🎧Диктант", "🔤 Собери слово")
    keyboard.add("📊 Рейтинг", "⚙️Настройки")
    bot.send_message(message.chat.id, "Чолӧм👋 я бот для изучения коми языка! Выберите действие:", reply_markup=keyboard)

# Кнопка "Собери слово" вызывает scramble-режим
@bot.message_handler(func=lambda message: message.text == "🔤 Собери слово")
def menu_scramble(message):
    scramble_task(message)

@bot.message_handler(func=lambda message: message.text == "📘Урок")
def lesson_button(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    lesson_index = current_lesson_index.get(user_id, 0)
    if lesson_index < len(lessons):
        send_lesson_with_voice(message.chat.id, lesson_index)
        current_lesson_index[user_id] = lesson_index + 1
        save_lesson_progress()
    else:
        bot.send_message(message.chat.id, "Все уроки пройдены! Ждите новых.")

def send_lesson_with_voice(chat_id, lesson_index):
    bot.send_message(chat_id, lessons[lesson_index])
    audio_id = None
    if lesson_index < len(audio_ids):
        audio_id = audio_ids[lesson_index]
    else:
        auto_index = lesson_index - len(audio_ids)
        if 0 <= auto_index < len(auto_lessons_ids):
            audio_id = auto_lessons_ids[auto_index]
    if audio_id:
        voice_file = f"{audio_id}.ogg"
        voice_path = os.path.join(AUDIO_PATH, voice_file)
        if os.path.exists(voice_path):
            try:
                with open(voice_path, 'rb') as audio:
                    bot.send_voice(chat_id, audio, caption="🔊 Прослушайте произношение фразы")
            except Exception as e:
                bot.send_message(chat_id, "Извините, не удалось отправить аудио для этого урока.")
        else:
            bot.send_message(chat_id, "Извините, аудио для этого урока отсутствует.")
    else:
        bot.send_message(chat_id, "Аудиофайл не найден для этого урока.")

# Quiz functions
@bot.message_handler(func=lambda message: message.text == "✅Начать квиз")
def start_quiz(message):
    register_user(message.chat.id)
    user_id = message.from_user.id
    # Загружаем прогресс пользователя
    user_quiz = quiz_progress.get(user_id, {"current": 0, "passed": []})
    quiz_progress[user_id] = user_quiz
    save_quiz_progress()
    question_index = user_quiz["current"]
    if question_index < len(quiz_questions):
        question_data = quiz_questions[question_index]
        send_quiz(message.chat.id, question_data, user_id)
    else:
        bot.send_message(message.chat.id, "Вы уже прошли все квизы!")

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
    active_quizzes[msg.poll.id] = (user_id, chat_id, quiz_progress[user_id]["current"])

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
    user_quiz = quiz_progress.get(user_id, {"current": 0, "passed": []})
    if poll_answer.option_ids and poll_answer.option_ids[0] == question_data["correct_option_id"]:
        # Если вопрос ещё не был решён правильно — начисляем баллы
        if question_index not in user_quiz["passed"]:
            add_score(user_id, 4)
            user_quiz["passed"].append(question_index)
        del active_quizzes[poll_id]
    else:
        explanation = question_data.get("explanation", "Неверный ответ.")
        bot.send_message(chat_id=chat_id, text=explanation)
        del active_quizzes[poll_id]
    user_quiz["current"] = question_index + 1
    quiz_progress[user_id] = user_quiz
    save_quiz_progress()
    if user_quiz["current"] < len(quiz_questions):
        next_question_data = quiz_questions[user_quiz["current"]]
        msg = bot.send_poll(
            chat_id=chat_id,
            question=next_question_data["question"],
            options=next_question_data["options"],
            is_anonymous=False,
            type='quiz',
            correct_option_id=next_question_data["correct_option_id"],
            open_period=60
        )
        active_quizzes[msg.poll.id] = (user_id, chat_id, user_quiz["current"])
    else:
        bot.send_message(chat_id=chat_id, text="Квиз завершён! Отличная работа!")
        if user_id in quiz_progress:
            quiz_progress[user_id]["current"] = len(quiz_questions)
            save_quiz_progress()

@bot.message_handler(func=lambda message: message.text == "⚙️Настройки")
def settings_menu(message):
    user_id = message.from_user.id
    is_on = user_id in auto_subscribed_users
    time_str = user_times.get(user_id, '11:30')
    text = (
        "🤖 Это бот для изучения коми языка. Вот что умеют кнопки в меню:\n\n\n📘Урок - Изучить уроки\n\n✅ Начать квиз - проверить знания в формате теста\n\n🎧 Диктант - прослушать аудио и написать услышанную фразу\n\n🔤 Собери слово - игра на составление слов из перемешанных букв\n\n⚙️ Настройки - показать это сообщение и открыть настройки\n\nТакже в боте есть команды:\n\n/start - открыть главное меню\n/lesson {Номер урока} - открыть урок по номеру\n/resetquiz - начать прохождение квизов с начала\n\n\nКаждый урок содержит фразу на коми языке с переводом и аудио произношением.\nУчитесь, практикуйтесь и наслаждайтесь процессом! 😊\n\nМожете выбрать действие:"
    )
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⏲️Рассылка", "В меню")
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "⏲️Рассылка")
def mailing_settings(message):
    user_id = message.from_user.id
    is_on = user_id in auto_subscribed_users
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_on:
        kb.add("Включить ✔️", "Выключить", "В меню")
        time_str = user_times.get(user_id, '09:00')
        text = (
            "⏲️ <b>Настройка рассылки</b>\n\n"
            f"Статус: <b>Включена</b>\n"
            f"Время: <b>{time_str}</b>\n\n"
            f"Если хотите сменить время, нажмите снова '<b>Включить</b>':"
        )
    else:
        kb.add("Включить", "Выключить ✔️", "В меню")
        text = (
            "⏲️ <b>Настройка рассылки</b>\n\n"
            "Статус: <b>Выключена</b>\n\n"
            "Выберите действие:"
        )
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text in ["Включить", "Включить ✔️"])
def mailing_enable(message):
    user_id = message.from_user.id
    auto_subscribed_users.add(user_id)
    save_auto_subscribers()
    schedule_user_job(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("В меню")
    bot.send_message(message.chat.id, "Рассылка включена!\n\nВведите время в формате ЧЧ:ММ (например, 08:30), когда хотите получать уроки:", reply_markup=kb)
    bot.register_next_step_handler(message, mailing_set_time)

@bot.message_handler(func=lambda message: message.text in ["Выключить", "Выключить ✔️"])
def mailing_disable(message):
    user_id = message.from_user.id
    if user_id in auto_subscribed_users:
        auto_subscribed_users.remove(user_id)
        save_auto_subscribers()
        remove_user_job(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("В меню")
    bot.send_message(message.chat.id, "Рассылка выключена.", reply_markup=kb)

# Ввод времени рассылки

def mailing_set_time(message):
    user_id = message.from_user.id
    time_text = message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", time_text):
        bot.send_message(message.chat.id, "Некорректный формат времени. Введите в формате ЧЧ:ММ (например, 08:30)")
        bot.register_next_step_handler(message, mailing_set_time)
        return
    hour, minute = map(int, time_text.split(":"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        bot.send_message(message.chat.id, "Некорректное время. Часы 0-23, минуты 0-59.")
        bot.register_next_step_handler(message, mailing_set_time)
        return
    user_times[user_id] = f"{hour:02d}:{minute:02d}"
    save_user_times()
    schedule_user_job(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("В меню")
    bot.send_message(message.chat.id, f"Время рассылки установлено на {hour:02d}:{minute:02d}.", reply_markup=kb)

@bot.message_handler(func=lambda message: message.text == "⚙️Настройки")
def help_command(message):
    settings_menu(message)

# --- Авторассылка уроков ---
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger

SUBSCRIBED_USERS_FILE = "subscribed_users.json"
USER_TIMES_FILE = "user_times.json"

# Загружаем подписчиков и их время
try:
    with open(SUBSCRIBED_USERS_FILE, "r") as f:
        auto_subscribed_users = set(json.load(f))
except:
    auto_subscribed_users = set()

try:
    with open(USER_TIMES_FILE, "r") as f:
        user_times = json.load(f)
        user_times = {int(k): v for k, v in user_times.items()}
except:
    user_times = {}

def save_auto_subscribers():
    with open(SUBSCRIBED_USERS_FILE, "w") as f:
        json.dump(list(auto_subscribed_users), f)

def save_user_times():
    with open(USER_TIMES_FILE, "w") as f:
        json.dump(user_times, f)

def schedule_user_job(user_id):
    # Удаляем старую задачу
    remove_user_job(user_id)
    if user_id not in auto_subscribed_users:
        return
    time_str = user_times.get(user_id, "12:00")
    hour, minute = map(int, time_str.split(":"))
    job_id = f"lesson_{user_id}"
    scheduler.add_job(
        send_random_lesson_job,
        CronTrigger(hour=hour, minute=minute),
        args=[user_id],
        id=job_id,
        replace_existing=True
    )

def remove_user_job(user_id):
    job_id = f"lesson_{user_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

def send_random_lesson_job(user_id):
    try:
        chat_id = user_id
        lesson_index = random.randint(0, len(lessons) - 1)
        send_lesson_with_voice(chat_id, lesson_index)
    except Exception as e:
        print(f"Ошибка авторассылки для {user_id}: {e}")

# При запуске пересоздаём все задачи
for user_id in auto_subscribed_users:
    schedule_user_job(user_id)

scheduler.start()
# --- конец авторассылки ---

# Handler for /resetquiz command
@bot.message_handler(commands=['resetquiz'])
def reset_quiz(message):
    user_id = message.from_user.id
    quiz_progress[user_id] = {"current": 0, "passed": quiz_progress.get(user_id, {}).get("passed", [])}
    save_quiz_progress()
    bot.send_message(message.chat.id, "Прогресс по квизу сброшен. Баллы за уже правильно решённые вопросы больше не начисляются, а за те, что были ошибочны — начисляются при повторном прохождении.")

@bot.message_handler(func=lambda message: message.text == "В меню")
def back_to_menu(message):
    start(message)
    
for user_id in subscribed_users:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📘Урок")
    kb.add("✅Начать квиз", "🎧Диктант", "🔤 Собери слово")
    kb.add("📊 Рейтинг", "⚙️Настройки")
    bot.send_message(user_id, "🚀 Выльмӧдӧм! Обновление!\n\n - Обновлено меню\n - Исправлены ошибки\n - Добавлены новые команды\n - Добавлена возможность создавать ежедневную рассылку с регулированием времени в настройках", reply_markup=kb)

if __name__ == "__main__":
    bot.polling(none_stop=True)