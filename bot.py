import os
import logging
import signal
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Poll
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, PollHandler

try:
    from dotenv import load_dotenv
    load_dotenv()  # Загружаем переменные из файла .env
except ImportError:
    print("python-dotenv не установлен. Переменные окружения должны быть заданы в системе.")

# Импортируем класс базы данных
from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Замените на свой токен бота
TOKEN = os.getenv('BOT_TOKEN')

# Замените на @username вашего канала (без символа @)
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
if CHANNEL_USERNAME:
    CHANNEL_ID = "@" + CHANNEL_USERNAME if not CHANNEL_USERNAME.startswith('@') else CHANNEL_USERNAME
else:
    print("ВНИМАНИЕ: CHANNEL_USERNAME не задан.")
    CHANNEL_USERNAME = "young_astra"
    CHANNEL_ID = "@" + CHANNEL_USERNAME

# Состояния для ConversationHandler
CHECKING_SUBSCRIPTION, MUNICIPALITY, CATEGORY, EDUCATION_ORG, KNOWS_MOVEMENT, IS_PARTICIPANT, KNOWS_CURATOR, DIRECTIONS, REGION_RATING, ORGANIZATION_RATING, KNOWS_KOSA = range(11)

# Список администраторов (ID пользователей Telegram)
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")
try:
    ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS if admin_id.strip()]
except ValueError:
    print("ВНИМАНИЕ: Некорректный формат ADMIN_IDS. Используйте числовые ID через запятую.")
    ADMIN_IDS = []

print(f"ID администраторов: {ADMIN_IDS}")

# Данные для опроса
municipalities = [
    "Ахтубинский район", "Володарский район", "Город Астрахань", "Енотаевский район",
    "ЗАТО Знаменск", "Икрянинский район", "Камызякский район", "Красноярский округ",
    "Лиманский район", "Наримановский район", "Приволжский район", "Харабалинский район",
    "Черноярский округ"
]

categories = ["Ученик", "Студент ССУЗа", "Студент ВУЗа"]

directions = [
    "Волонтерство и добровольчество", "Труд, профессия и свое дело", "Спорт",
    "Образование и знания", "Культура и искусство", "Наука и технологии",
    "Патриотизм и историческая память", "Медиа и коммуникации", "Здоровый образ жизни",
    "Экология и охрана природы", "Дипломатия и международные отношения", "Туризм и путешествия"
]

# Инициализация базы данных
db = Database()

# Временное хранение ответов пользователей (будет синхронизироваться с БД)
user_responses = {}

# Функция для загрузки данных из БД в память
def load_data_from_db():
    global user_responses
    try:
        results = db.get_all_results()
        for result in results:
            user_id = result['user_id']
            del result['user_id']  # Удаляем, так как это ключ
            del result['timestamp']  # Удаляем, так как это не нужно в памяти
            user_responses[user_id] = result
        logger.info(f"Загружено {len(results)} записей из базы данных")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из базы данных: {e}")

# Загружаем данные при запуске
load_data_from_db()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start, проверяет подписку на канал"""
    user = update.effective_user
    user_id = user.id
    
    # Создаем словарь для хранения ответов пользователя если его еще нет
    user_responses[user_id] = {
            'selected_directions': []
        }
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! Мы рады приветствовать тебя в главном молодежном чат-боте региона. "
        f"Не стесняйся! Пройди опрос! Внеси свой вклад в развитие!\n\n"
        f"Для начала нужно проверить, подписаны ли вы на канал."
    )
    
    # Проверяем подписку на канал
    return await check_subscription(update, context)


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверка подписки пользователя на канал"""
    user_id = update.effective_user.id
    
    try:
        # Проверяем статус пользователя в канале
        chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        status = chat_member.status
        
        # Проверяем, является ли пользователь участником канала
        if status in ['member', 'administrator', 'creator']:
            await update.message.reply_text(
                f"Спасибо, что подписаны на наш канал {CHANNEL_ID}!"
            )
            # Пользователь подписан, переходим к опросу
            return await ask_municipality(update, context)
        else:
            # Если пользователь не подписан, отправляем сообщение с кнопкой для подписки
            keyboard = [
                [InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton("Я подписан", callback_data="check_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"❌ Для участия в опросе необходимо подписаться на канал {CHANNEL_ID}.\n"
                f"Пожалуйста, подпишитесь и нажмите кнопку 'Я подписан'.",
                reply_markup=reply_markup
            )
            return CHECKING_SUBSCRIPTION
    except Exception as e:
        logging.error(f"Ошибка при проверке подписки: {e}")
        
        # В случае ошибки тоже требуем подписаться и Я подписан
        keyboard = [
            [InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
            [InlineKeyboardButton("Я подписан", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при проверке подписки на канал {CHANNEL_ID}.\n"
            f"Пожалуйста, подпишитесь на канал и нажмите кнопку 'Я подписан'.",
            reply_markup=reply_markup
        )
        return CHECKING_SUBSCRIPTION

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик нажатия на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_subscription":
        user_id = update.effective_user.id
        
        try:
            # Проверяем статус пользователя в канале
            chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            status = chat_member.status
            
            if status in ['member', 'administrator', 'creator']:
                await query.edit_message_text(
                    f"✅ Отлично! Вы подписаны на канал {CHANNEL_ID}. Теперь можно перейти к опросу."
                )

                # Переходим к первому вопросу опроса
                return await ask_municipality_after_callback(update, context)
            else:
                # Пользователь ещё не подписан
                keyboard = [
                    [InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                    [InlineKeyboardButton("Я подписан", callback_data="check_subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"❌ Вы всё ещё не подписаны на канал {CHANNEL_ID}.\n"
                    f"Пожалуйста, подпишитесь на канал и проверьте подписку снова.",
                    reply_markup=reply_markup
                )
                return CHECKING_SUBSCRIPTION
        except Exception as e:
            logging.error(f"Ошибка при проверке подписки: {e}")
            
            # В случае ошибки тоже требуем подписаться и проверить
            keyboard = [
                [InlineKeyboardButton("Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton("Я подписан", callback_data="check_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ Произошла ошибка при проверке подписки на канал {CHANNEL_ID}.\n"
                f"Пожалуйста, убедитесь что вы подписаны и нажмите кнопку 'Я подписан' снова.",
                reply_markup=reply_markup
            )
            return CHECKING_SUBSCRIPTION
            
    # Обработка выбора направлений
    elif query.data.startswith("direction_"):
        return await handle_direction_selection(update, context)

async def ask_municipality_after_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Специальная функция для перехода к вопросу о муниципалитете после callback query"""
    # Создаем и отправляем новое сообщение с вопросом о муниципалитете
    user_id = update.effective_user.id
    await context.bot.send_message(
        chat_id=user_id,
        text="Опрос для обучающихся и студентов Астраханской области\n\nУкажите Ваше муниципальное образование:",
        reply_markup=ReplyKeyboardMarkup(
            [[municipality] for municipality in municipalities],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return MUNICIPALITY

async def ask_municipality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает муниципальное образование пользователя"""
    await update.message.reply_text(
        "Опрос для обучающихся и студентов Астраханской области\n\nУкажите Ваше муниципальное образование:",
        reply_markup=ReplyKeyboardMarkup(
            [[municipality] for municipality in municipalities],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return MUNICIPALITY

async def handle_municipality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор муниципального образования"""
    user_id = update.effective_user.id
    municipality = update.message.text
    
    if municipality in municipalities:
        user_responses[user_id]['municipality'] = municipality
        
        # Задаем следующий вопрос - категория
        await update.message.reply_text(
            "Выберите категорию, к которой вы относитесь:",
            reply_markup=ReplyKeyboardMarkup(
                [[category] for category in categories],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return CATEGORY
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите один из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup(
                [[municipality] for municipality in municipalities],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return MUNICIPALITY

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор категории"""
    user_id = update.effective_user.id
    category = update.message.text
    
    if category in categories:
        user_responses[user_id]['category'] = category
        
        # Для студентов ВУЗа задаем вопрос о Молодежном центре "Коса"
        if category == "Студент ВУЗа":
            await update.message.reply_text(
                "Знаете ли вы о работе Молодежного центра «Коса» @dmpp30",
                reply_markup=ReplyKeyboardMarkup(
                    [["Да"], ["Нет"]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return KNOWS_KOSA
        
        # Для остальных категорий запрашиваем название образовательной организации
        await update.message.reply_text(
            "Введите название Вашей образовательной организации:",
            reply_markup=ReplyKeyboardRemove()
        )
        return EDUCATION_ORG
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите один из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup(
                [[category] for category in categories],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return CATEGORY

async def handle_education_org(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод названия образовательной организации"""
    user_id = update.effective_user.id
    education_org = update.message.text
    
    # Сохраняем название образовательной организации
    user_responses[user_id]['education_org'] = education_org
    
    category = user_responses[user_id]['category']
    
    # Для студентов ВУЗа завершаем опрос
    if category == "Студент ВУЗа":
        # Сохраняем результаты в базу данных
        db.save_survey_result(user_id, user_responses[user_id])
        
        # Благодарим за прохождение опроса
        await update.message.reply_text(
            "Спасибо за участие в опросе! Ваши ответы успешно записаны.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем напоминание о боте "ТРЕВОГА АСТРАХАНЬ"
        await update.message.reply_text(
            "Также напоминаем о боте «ТРЕВОГА АСТРАХАНЬ» @trevoga30_bot в который приходит вся проверенная информация о БПЛА и других ЧП региона. "
            "Думайте. Подпишись, чтобы быть в курсе."
        )
        
        return ConversationHandler.END
    
    # Для остальных категорий задаем вопрос о знании Движения Первых
    await update.message.reply_text(
        "Знаете ли Вы о проектах Общероссийского общественно-государственного движения детей и молодежи \"Движение первых\"?",
        reply_markup=ReplyKeyboardMarkup(
            [["Да"], ["Нет"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return KNOWS_MOVEMENT

async def handle_knows_movement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ на вопрос о знании Движения Первых"""
    user_id = update.effective_user.id
    knows_movement = update.message.text
    
    user_responses[user_id]['knows_movement'] = knows_movement
    
    if knows_movement == "Да":
        # Если знает, продолжаем опрос
        await update.message.reply_text(
            "Являетесь ли Вы участником Движения Первых?",
            reply_markup=ReplyKeyboardMarkup(
                [["Да"], ["Нет"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return IS_PARTICIPANT
    else:
        # Если не знает, завершаем опрос
        # Сохраняем результаты в базу данных
        db.save_survey_result(user_id, user_responses[user_id])
        
        # Благодарим за прохождение опроса
        await update.message.reply_text(
            "Спасибо за участие в опросе! Ваши ответы записаны.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем напоминание о боте "ТРЕВОГА АСТРАХАНЬ"
        await update.message.reply_text(
            "Также напоминаем о боте «ТРЕВОГА АСТРАХАНЬ» @trevoga30_bot в который приходит вся проверенная информация о БПЛА и других ЧП региона. "
            "Думайте. Подпишись, чтобы быть в курсе."
        )
        
        return ConversationHandler.END

async def handle_is_participant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ на вопрос об участии в Движении Первых"""
    user_id = update.effective_user.id
    is_participant = update.message.text
    
    user_responses[user_id]['is_participant'] = is_participant
    
    # Задаем вопрос о знании куратора
    await update.message.reply_text(
        "Знаете ли Вы куратора первичного отделения Движения Первых в Вашей образовательной организации?",
        reply_markup=ReplyKeyboardMarkup(
            [["Да"], ["Нет"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return KNOWS_CURATOR

async def handle_knows_curator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ на вопрос о знании куратора"""
    user_id = update.effective_user.id
    knows_curator = update.message.text
    
    user_responses[user_id]['knows_curator'] = knows_curator
    
    # Если не знает куратора, завершаем опрос
    if knows_curator == "Нет":
        # Сохраняем результаты в базу данных
        db.save_survey_result(user_id, user_responses[user_id])
        
        # Благодарим за прохождение опроса
        await update.message.reply_text(
            "Спасибо за участие в опросе! Ваши ответы успешно записаны.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем напоминание о боте "ТРЕВОГА АСТРАХАНЬ"
        await update.message.reply_text(
            "Будь с нами!\n\n"
            "Также напоминаем о боте «ТРЕВОГА АСТРАХАНЬ» @trevoga30_bot в который приходит вся проверенная информация о БПЛА и других ЧП региона. "
            "Думайте. Подпишись, чтобы быть в курсе."
        )
        
        return ConversationHandler.END
    
    # Если знает куратора, продолжаем опрос с выбором направлений
    # Получаем список направлений и создаем клавиатуру
    keyboard = []
    for i, direction in enumerate(directions):
        keyboard.append([InlineKeyboardButton(
            f"{direction}", callback_data=f"direction_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton("Завершить выбор", callback_data="direction_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Укажите 3 направления Движения Первых, в проектах которых Вы принимаете активное участие:\n"
        "(Выберите до 3 направлений, затем нажмите 'Завершить выбор')",
        reply_markup=reply_markup
    )
    return DIRECTIONS

async def handle_direction_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор направлений"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if query.data == "direction_done":
        # Пользователь завершил выбор, переходим к следующему вопросу
        selected = user_responses[user_id]['selected_directions']
        
        if len(selected) > 0:
            selected_texts = [directions[idx] for idx in selected]
            selected_text = "\n• ".join(selected_texts)
            
            await query.edit_message_text(
                f"Вы выбрали следующие направления:\n• {selected_text}"
            )
            
            # Задаем вопрос об оценке уровня развития
            await context.bot.send_message(
                chat_id=user_id,
                text="Оцените уровень развития Движения Первых на территории Вашего муниципального образования\n"
                     "Оцените по шкале от 1 до 5, где 5 - \"отлично\", а 1 - \"плохо\"",
                reply_markup=ReplyKeyboardMarkup(
                    [["5", "4", "3", "2", "1"][::-1]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return REGION_RATING
        else:
            await query.answer("Пожалуйста, выберите хотя бы одно направление")
            return DIRECTIONS
            
    else:
        # Пользователь выбирает направление
        direction_idx = int(query.data.split("_")[1])
        
        if 'selected_directions' not in user_responses[user_id]:
            user_responses[user_id]['selected_directions'] = []
            
        selected = user_responses[user_id]['selected_directions']
        
        if direction_idx in selected:
            # Если направление уже выбрано, удаляем его
            selected.remove(direction_idx)
            await query.answer(f"Вы отменили выбор: {directions[direction_idx]}")
        else:
            # Если направление не выбрано и выбрано меньше 3, добавляем
            if len(selected) < 3:
                selected.append(direction_idx)
                await query.answer(f"Вы выбрали: {directions[direction_idx]}")
            else:
                await query.answer("Вы уже выбрали 3 направления. Отмените одно из них или завершите выбор.")
        
        # Обновляем клавиатуру
        keyboard = []
        for i, direction in enumerate(directions):
            text = direction
            if i in selected:
                text = f"✅ {direction}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"direction_{i}")])
        
        keyboard.append([InlineKeyboardButton("Завершить выбор", callback_data="direction_done")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Укажите 3 направления Движения Первых, в проектах которых Вы принимаете активное участие:\n"
            f"(Выбрано: {len(selected)}/3)",
            reply_markup=reply_markup
        )
        return DIRECTIONS

async def handle_region_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает оценку уровня развития в регионе"""
    user_id = update.effective_user.id
    rating = update.message.text
    
    if rating in ["1", "2", "3", "4", "5"]:
        user_responses[user_id]['region_rating'] = rating
        
        # Задаем последний вопрос об оценке уровня организации
        await update.message.reply_text(
            "Оцените уровень организации и проведения мероприятий Движения Первых в Вашей образовательной организации\n"
            "Оцените по шкале от 1 до 5, где 5 - \"отлично\", а 1 - \"плохо\"",
            reply_markup=ReplyKeyboardMarkup(
                [["5", "4", "3", "2", "1"][::-1]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ORGANIZATION_RATING
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите оценку от 1 до 5:",
            reply_markup=ReplyKeyboardMarkup(
                [["5", "4", "3", "2", "1"][::-1]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return REGION_RATING

async def handle_organization_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает оценку уровня организации мероприятий"""
    user_id = update.effective_user.id
    rating = update.message.text
    
    if rating in ["1", "2", "3", "4", "5"]:
        user_responses[user_id]['organization_rating'] = rating
        
        # Сохраняем результаты в базу данных
        db.save_survey_result(user_id, user_responses[user_id])
        
        # Благодарим за прохождение опроса
        await update.message.reply_text(
            "Спасибо за участие в опросе! Ваши ответы успешно записаны.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Выводим результаты опроса
        response = user_responses[user_id]
        selected_directions = [directions[idx] for idx in response.get('selected_directions', [])]
        
        summary = (
            f"📋 Ваши ответы:\n\n"
            f"🏙️ Муниципальное образование: {response.get('municipality', 'Не указано')}\n"
            f"👤 Категория: {response.get('category', 'Не указано')}\n"
            f"🏫 Образовательная организация: {response.get('education_org', 'Не указано')}\n"
            f"🚩 Знание о Движении Первых: {response.get('knows_movement', 'Не указано')}\n"
        )
        
        if response.get('knows_movement') == "Да":
            summary += (
                f"🧑‍🤝‍🧑 Участие в Движении: {response.get('is_participant', 'Не указано')}\n"
                f"👨‍🏫 Знание куратора: {response.get('knows_curator', 'Не указано')}\n"
                f"🧭 Выбранные направления: {', '.join(selected_directions)}\n"
                f"⭐ Оценка в муниципалитете: {response.get('region_rating', 'Не указано')}/5\n"
                f"🏫 Оценка в организации: {response.get('organization_rating', 'Не указано')}/5\n\n\n"
            )
            
        await update.message.reply_text(summary + 
            f"Будь с нами!\n\n" 
            f"Также напоминаем о боте «ТРЕВОГА АСТРАХАНЬ» @trevoga30_bot в который приходит вся проверенная информация о БПЛА и других ЧП региона. "
            f"Думайте. Подпишись, чтобы быть в курсе."
        )
        
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите оценку от 1 до 5:",
            reply_markup=ReplyKeyboardMarkup(
                [["5", "4", "3", "2", "1"][::-1]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ORGANIZATION_RATING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет опрос по команде /cancel"""
    user = update.effective_user
    await update.message.reply_text(
        f"Опрос отменен. Вы можете начать заново, отправив команду /start.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /admin - проверяет права администратора"""
    user_id = update.effective_user.id
    
    if str(user_id) in ADMIN_IDS or user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("Список всех участников", callback_data="admin_users")],
            [InlineKeyboardButton("Экспорт результатов (CSV)", callback_data="admin_export")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👑 Панель администратора\nВыберите действие:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "⛔ У вас нет прав администратора для доступа к этой команде."
        )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок админской панели"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем права администратора
    if str(user_id) not in ADMIN_IDS and user_id not in ADMIN_IDS:
        await query.answer("У вас нет прав администратора", show_alert=True)
        return
    
    await query.answer()
    
    if query.data == "admin_stats":
        await show_stats(query, context)
    elif query.data == "admin_users":
        await show_users(query, context)
    elif query.data == "admin_export":
        await export_results(query, context)
    elif query.data.startswith("user_details_"):
        user_id_to_show = query.data.split("_")[2]
        await show_user_details(query, context, user_id_to_show)
    elif query.data == "admin_back":
        # Возврат к основной панели администратора
        keyboard = [
            [InlineKeyboardButton("Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("Список всех участников", callback_data="admin_users")],
            [InlineKeyboardButton("Экспорт результатов (CSV)", callback_data="admin_export")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👑 Панель администратора\nВыберите действие:",
            reply_markup=reply_markup
        )

async def show_stats(query, context):
    """Показывает общую статистику по опросу"""
    # Получаем статистику из базы данных
    stats = db.get_statistics()
    total_users = stats['total_users']
    
    # Формируем сообщение со статистикой
    stats_message = f"📊 Общая статистика опроса\n\n"
    stats_message += f"Всего участников: {total_users}\n\n"
    
    stats_message += "По муниципалитетам:\n"
    for municipality, count in sorted(stats['municipalities'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_users) * 100 if total_users else 0
        stats_message += f"• {municipality}: {count} ({percentage:.1f}%)\n"
    
    stats_message += "\nПо категориям:\n"
    for category, count in sorted(stats['categories'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_users) * 100 if total_users else 0
        stats_message += f"• {category}: {count} ({percentage:.1f}%)\n"
    
    stats_message += "\nЗнание о Движении Первых:\n"
    for knows, count in stats['knows_movement'].items():
        percentage = (count / total_users) * 100 if total_users else 0
        stats_message += f"• {knows}: {count} ({percentage:.1f}%)\n"
    
    # Кнопка возврата к панели администратора
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(stats_message) > 4096:
        # Если сообщение слишком длинное, разделяем его
        for i in range(0, len(stats_message), 4096):
            part = stats_message[i:i+4096]
            if i == 0:
                await query.edit_message_text(part, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=query.from_user.id, text=part)
    else:
        await query.edit_message_text(stats_message, reply_markup=reply_markup)

async def show_users(query, context):
    """Показывает список пользователей, прошедших опрос"""
    # Получаем всех пользователей из базы данных
    results = db.get_all_results()
    
    if not results:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 Пока никто не прошел опрос.",
            reply_markup=reply_markup
        )
        return
    
    # Создаем список пользователей для пагинации
    users_list = []
    for result in results:
        user_id = result['user_id']
        municipality = result.get('municipality', 'Не указано')
        category = result.get('category', 'Не указано')
        users_list.append((user_id, municipality, category))
    
    # Сортируем по муниципалитету
    users_list.sort(key=lambda x: x[1])
    
    # Создаем клавиатуру для просмотра деталей каждого пользователя
    keyboard = []
    for user_id, municipality, category in users_list[:10]:  # Показываем первые 10
        keyboard.append([InlineKeyboardButton(
            f"{municipality} - {category} (ID: {user_id})",
            callback_data=f"user_details_{user_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👥 Список участников опроса ({len(users_list)}):\nВыберите участника для просмотра подробной информации",
        reply_markup=reply_markup
    )

async def show_user_details(query, context, user_id_to_show):
    """Показывает подробную информацию о конкретном пользователе"""
    user_id_to_show = int(user_id_to_show)
    
    # Получаем данные пользователя из базы данных
    result = db.get_result_by_user_id(user_id_to_show)
    
    if not result:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚠️ Пользователь с ID {user_id_to_show} не найден в базе данных.",
            reply_markup=reply_markup
        )
        return
    
    # Получаем ответы пользователя
    selected_directions = [directions[idx] for idx in result.get('selected_directions', [])]
    
    # Формируем детальную информацию
    details = f"👤 Детальная информация о пользователе {user_id_to_show}:\n\n"
    details += f"🏙️ Муниципальное образование: {result.get('municipality', 'Не указано')}\n"
    details += f"👤 Категория: {result.get('category', 'Не указано')}\n"
    details += f"🏫 Образовательная организация: {result.get('education_org', 'Не указано')}\n"
    details += f"🚩 Знание о Движении Первых: {result.get('knows_movement', 'Не указано')}\n"
    
    if result.get('knows_movement') == "Да":
        details += f"🧑‍🤝‍🧑 Участие в Движении: {result.get('is_participant', 'Не указано')}\n"
        details += f"👨‍🏫 Знание куратора: {result.get('knows_curator', 'Не указано')}\n"
        
        if selected_directions:
            details += f"🧭 Выбранные направления:\n"
            for direction in selected_directions:
                details += f"  • {direction}\n"
        else:
            details += f"🧭 Выбранные направления: Не указаны\n"
        
        details += f"⭐ Оценка в муниципалитете: {result.get('region_rating', 'Не указано')}/5\n"
        details += f"🏫 Оценка в организации: {result.get('organization_rating', 'Не указано')}/5\n"
    
    # Кнопки навигации
    keyboard = [
        [InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("◀️ К панели администратора", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(details, reply_markup=reply_markup)

async def export_results(query, context):
    """Экспортирует результаты опроса в CSV файл"""
    # Получаем всех пользователей из базы данных
    results = db.get_all_results()
    
    if not results:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 Пока никто не прошел опрос. Нет данных для экспорта.",
            reply_markup=reply_markup
        )
        return
    
    try:
        import csv
        import io
        from datetime import datetime
        
        # Создаем файл CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовки CSV
        headers = [
            "ID пользователя", "Муниципалитет", "Категория", "Знает о Движении", 
            "Участник Движения", "Знает куратора", "Направления", 
            "Оценка региона", "Оценка организации", "Дата и время"
        ]
        writer.writerow(headers)
        
        # Данные пользователей
        for result in results:
            selected_directions = [directions[idx] for idx in result.get('selected_directions', [])]
            directions_str = "; ".join(selected_directions)
            
            row = [
                result['user_id'],
                result.get('municipality', ''),
                result.get('category', ''),
                result.get('knows_movement', ''),
                result.get('is_participant', ''),
                result.get('knows_curator', ''),
                directions_str,
                result.get('region_rating', ''),
                result.get('organization_rating', ''),
                result.get('timestamp', '')
            ]
            writer.writerow(row)
        
        # Возвращаем указатель в начало файла
        output.seek(0)
        
        # Имя файла с датой и временем
        filename = f"opros_results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        
        # Отправляем файл пользователю
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=io.BytesIO(output.getvalue().encode('utf-8-sig')),  # Используем UTF-8 с BOM для корректного отображения в Excel
            filename=filename,
            caption="📊 Результаты опроса в формате CSV"
        )
        
        # Информируем пользователя
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ Файл с результатами опроса успешно сформирован и отправлен!\n"
            f"Имя файла: {filename}\n"
            f"Количество записей: {len(results)}",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logging.error(f"Ошибка при экспорте данных: {e}")
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ Произошла ошибка при экспорте данных: {e}",
            reply_markup=reply_markup
        )

# Добавляем новый обработчик для ответа о Молодежном центре "Коса"
async def handle_knows_kosa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ на вопрос о знании Молодежного центра "Коса" и запрашивает название образовательной организации"""
    user_id = update.effective_user.id
    knows_kosa = update.message.text
    
    # Сохраняем ответ пользователя
    user_responses[user_id]['knows_kosa'] = knows_kosa
    
    # Запрашиваем название образовательной организации
    await update.message.reply_text(
        "Введите название Вашей образовательной организации:",
        reply_markup=ReplyKeyboardRemove()
    )
    return EDUCATION_ORG

# Функция для корректного завершения работы бота
def shutdown_handler(signal_number, frame):
    """Обработчик сигналов завершения для корректного закрытия соединения с БД"""
    print("Получен сигнал завершения, закрываем соединение с базой данных...")
    db.close()
    print("Соединение с базой данных закрыто. Завершение работы.")
    sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, shutdown_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, shutdown_handler)  # kill

def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Настраиваем обработчик разговоров
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHECKING_SUBSCRIPTION: [
                CallbackQueryHandler(button_callback),
            ],
            MUNICIPALITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_municipality)
            ],
            CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)
            ],
            EDUCATION_ORG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_education_org)
            ],
            KNOWS_MOVEMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_knows_movement)
            ],
            IS_PARTICIPANT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_is_participant)
            ],
            KNOWS_CURATOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_knows_curator)
            ],
            DIRECTIONS: [
                CallbackQueryHandler(handle_direction_selection)
            ],
            REGION_RATING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_region_rating)
            ],
            ORGANIZATION_RATING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_organization_rating)
            ],
            KNOWS_KOSA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_knows_kosa)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^user_details_"))
    
    # Запускаем бота
    print(f"Бот запущен. Канал: {CHANNEL_ID}, Админы: {ADMIN_IDS}")
    print("Для остановки нажмите Ctrl+C.")
    application.run_polling()

if __name__ == "__main__":
    main()
