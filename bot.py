#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from dotenv import load_dotenv  # для локального тестирования
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Загружаем переменные из .env только если файл существует (локально)
if os.path.exists('.env'):
    load_dotenv()

# Получаем токен из переменной окружения
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена!")

# ID консультанта — также лучше вынести в переменную
CONSULTANT_CHAT_ID = int(os.environ.get('CONSULTANT_CHAT_ID', 0))
if not CONSULTANT_CHAT_ID:
    raise ValueError("Переменная окружения CONSULTANT_CHAT_ID не установлена!")

# -------------------- ЛОГИРОВАНИЕ --------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 МБ на файл
LOG_BACKUP_COUNT = 5              # хранить 5 ротированных файлов


def setup_logging() -> logging.Logger:
    """Настраивает логирование: консоль + rotatable файл для всех событий + отдельный файл для ошибок"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Общий файл логов
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "bot.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Отдельный файл только для ошибок
    error_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


logger = setup_logging()

ASKING = range(1)

# -------------------- ВОПРОСЫ --------------------
QUESTIONS = [
    ("А1. Когда клиент (или внутренний заказчик) что-то просит, мы записываем его просьбу в систему или документ, а не держим в голове или переписке.", "A", 1),
    ("А2. У нас есть чёткий процесс согласования изменений: если заказчик передумал, мы понимаем, как это повлияет на сроки и бюджет, и сообщаем ему об этом до начала работ.", "A", 2),
    ("А3. Мы редко переделываем работу из-за того, что «не так поняли» требования.", "A", 3),
    ("Б1. Перед началом любой задачи мы оцениваем, сколько времени она займёт, и записываем эту оценку.", "B", 1),
    ("Б2. Фактическое время выполнения задач мы сравниваем с планом и анализируем расхождения.", "B", 2),
    ("Б3. Если мы отстаём от графика, мы пересматриваем план и сообщаем об этом заинтересованным сторонам (клиенту, руководству) до наступления дедлайна.", "B", 3),
    ("Б4. В компании есть утверждённый порядок приоритизации задач: все знают, что делать в первую очередь, а что можно отложить.", "B", 4),
    ("В1. Готовый результат (отчёт, код, товар, услуга) проверяется другим сотрудником (не автором) до того, как попадает к клиенту.", "C", 1),
    ("В2. У нас есть список обязательных проверок (чек-лист), который мы используем перед сдачей работы.", "C", 2),
    ("В3. Если обнаруживается ошибка, мы разбираем её причину и меняем процесс, чтобы ошибка не повторилась (а не просто исправляем и идём дальше).", "C", 3),
    ("Г1. Мы используем систему контроля версий (или хотя бы чёткое именование файлов), чтобы всегда знать, какая версия документа или продукта последняя.", "D", 1),
    ("Г2. У нас есть единое хранилище (папка, облако, репозиторий), где лежат все рабочие артефакты, и доступ к нему есть у всех членов команды.", "D", 2),
    ("Д1. Перед тем как внедрить новую систему или изменить процесс, мы рассматриваем хотя бы 2-3 альтернативы и сравниваем их по критериям.", "E", 1),
    ("Д2. Мы фиксируем, почему приняли то или иное решение (протокол, запись в чате), чтобы потом можно было вернуться и понять логику.", "E", 2),
    ("Е1. Мы регулярно (раз в месяц или чаще) обсуждаем: «что может пойти не так в ближайшее время?»", "F", 1),
    ("Е2. Для самых страшных рисков у нас есть план Б (как действовать, если событие наступит).", "F", 2),
    ("Е3. Если риск материализовался, мы анализируем, почему не смогли его предотвратить, и корректируем нашу систему.", "F", 3),
    ("Ж1. Мы собираем ключевые метрики нашей работы (время выполнения заказа, доля брака, загрузка сотрудников) не реже раза в месяц.", "G", 1),
    ("Ж2. Мы не просто собираем метрики, но и используем их для принятия решений (например, видим рост брака → ищем причину).", "G", 2),
    ("Ж3. Мы можем предсказать, сколько времени займёт типовой заказ, с погрешностью не более 20%.", "G", 3),
    ("З1. У нас есть регулярный ритуал (например, планерка раз в неделю), где мы ищем, что улучшить в процессах.", "H", 1),
    ("З2. Любой сотрудник может предложить улучшение, и это предложение будет рассмотрено (без страха наказания).", "H", 2),
    ("З3. Мы отслеживаем, сколько улучшений внедрили за последний месяц, и гордимся этим.", "H", 3),
]

LEVEL_BOUNDARIES = {
    1: (0, 1.79),
    2: (1.8, 2.5),
    3: (2.6, 3.2),
    4: (3.3, 3.7),
    5: (3.71, 4.0),
}

RECOMMENDATIONS = {
    1: "🔴 Уровень 1 (Начальный). Процессы хаотичны, успех зависит от героев. Высок риск срыва сроков и качества.\nРекомендация: Начните с внедрения базового планирования и контроля. Проведите бумажную симуляцию одного сквозного процесса, введите чек-лист для регулярных задач.",
    2: "🟠 Уровень 2 (Управляемый). На уровне отдельных проектов есть планирование и контроль, но нет единых стандартов. Рекомендация: Стандартизируйте лучшие практики на всю компанию. Введите ретроспективы раз в неделю.",
    3: "🟡 Уровень 3 (Определённый). Процессы стандартизированы и документированы. Рекомендация: Переходите к сбору метрик и управлению рисками. Заведите дашборд ключевых показателей.",
    4: "🟢 Уровень 4 (Количественно управляемый). Компания управляется цифрами. Рекомендация: Сфокусируйтесь на постоянных улучшениях. Внедрите систему раннего оповещения.",
    5: "✅ Уровень 5 (Оптимизирующий). Непрерывное улучшение встроено в культуру. Рекомендация: Поддерживайте уровень, обучайте другие команды, ищите следующие узкие места.",
}

# -------------------- РЕКОМЕНДАЦИИ ПО БЛОКАМ --------------------
BLOCK_RECOMMENDATIONS = {
    'A': {
        'low': "🔴 Низкий балл (<2.0). Требования не фиксируются, изменения хаотичны.\n➜ Введите правило: любая просьба клиента записывается в тикет-систему или общую папку.\n➜ Проведите встречу с заказчиком, где проговорите, как изменения влияют на сроки.\n➜ Инструмент: 'Поток единицы работы' (глава 6).",
        'medium': "🟡 Средний балл (2.0–3.0). Требования фиксируются, но бывают сбои.\n➜ Введите чек-лист согласования требований перед стартом.\n➜ Добавьте правило: любое изменение — письменно.\n➜ Инструмент: 'Встреча без последствий' (глава 16).",
        'high': "🟢 Высокий балл (>3.0). Процесс управления требованиями отлажен.\n➜ Поддерживайте дисциплину через еженедельный чек-лист.\n➜ Переходите к количественным метрикам: доля возвратов из-за неверных требований.\n➜ Инструмент: 'Кирпичная стена' (глава 27).",
    },
    'B': {
        'low': "🔴 Низкий балл (<2.0). Планирования почти нет, сроки срываются.\n➜ Начните с оценки времени на задачи. Записывайте.\n➜ Введите еженедельное ретро (глава 19).\n➜ Инструмент: 'Бумажная симуляция' (глава 6).",
        'medium': "🟡 Средний балл (2.0–3.0). Планирование есть, но не всегда точно.\n➜ Сравнивайте факт с планом каждую неделю.\n➜ Ограничьте незавершёнку (WIP) — не более 3-х задач на человека.\n➜ Инструмент: 'Чек-лист на пятницу' (глава 28).",
        'high': "🟢 Высокий балл (>3.0). Планирование работает стабильно.\n➜ Используйте метрики для прогнозирования.\n➜ Автоматизируйте сбор оценок.\n➜ Инструмент: 'Спираль улучшений' (глава 30).",
    },
    'C': {
        'low': "🔴 Низкий балл (<2.0). Качество не контролируется, ошибки попадают к клиенту.\n➜ Введите обязательную проверку вторым лицом.\n➜ Создайте чек-лист из 5 пунктов перед сдачей.\n➜ Инструмент: 'Доска благодарности за найденные баги' (глава 19).",
        'medium': "🟡 Средний балл (2.0–3.0). Проверки есть, но не всегда эффективны.\n➜ Анализируйте причины каждого возврата.\n➜ Введите правило: 'ошибка не повторяется дважды'.\n➜ Инструмент: 'Карта страхов и выгод' (глава 17).",
        'high': "🟢 Высокий балл (>3.0). Качество на высоком уровне.\n➜ Переходите к профилактике.\n➜ Обучайте сотрудников техникам тестирования.\n➜ Инструмент: 'Кирпичная стена'.",
    },
    'D': {
        'low': "🔴 Низкий балл (<2.0). Хаос в версиях, путаница в файлах.\n➜ Введите единое облачное хранилище.\n➜ Договоритесь о простом именовании файлов.\n➜ Инструмент: 'Одно автоматическое действие' (глава 26).",
        'medium': "🟡 Средний балл (2.0–3.0). Хранилище есть, но иногда нарушают.\n➜ Запретите отправку файлов по email.\n➜ Введите еженедельную проверку порядка.\n➜ Инструмент: 'Кирпичная стена' (глава 27).",
        'high': "🟢 Высокий балл (>3.0). С версиями порядок.\n➜ Подключите автоматическую систему контроля версий (Git).\n➜ Обучите команду работе с ветками.\n➜ Инструмент: 'Система раннего оповещения' (глава 31).",
    },
    'E': {
        'low': "🔴 Низкий балл (<2.0). Решения принимаются интуитивно, без анализа альтернатив.\n➜ Введите правило: 'прежде чем принять важное решение, рассмотри 2 варианта'.\n➜ Записывайте аргументы.\n➜ Инструмент: 'Красные карточки' (глава 24).",
        'medium': "🟡 Средний балл (2.0–3.0). Альтернативы рассматриваются, но не всегда фиксируются.\n➜ Создайте шаблон протокола решения.\n➜ Вовлекайте сотрудников.\n➜ Инструмент: 'Встреча без последствий'.",
        'high': "🟢 Высокий балл (>3.0). Анализ решений системен.\n➜ Используйте технику 'Стеклянный шар'.\n➜ Автоматизируйте сбор критериев.\n➜ Инструмент: 'Совещание с собой' (глава 24).",
    },
    'F': {
        'low': "🔴 Низкий балл (<2.0). Риски не обсуждаются, кризисы приходят неожиданно.\n➜ Раз в месяц проводите 'мозговой штурм рисков'.\n➜ Для ТОП-3 рисков напишите план Б.\n➜ Инструмент: 'План Б по Таллебу' (глава 13).",
        'medium': "🟡 Средний балл (2.0–3.0). Риски обсуждаются, но планы Б устаревают.\n➜ Пересматривайте риски раз в месяц.\n➜ После каждого сбоя обновляйте список рисков.\n➜ Инструмент: 'Стеклянный шар'.",
        'high': "🟢 Высокий балл (>3.0). Рисками управляют проактивно.\n➜ Используйте количественные оценки.\n➜ Включите управление рисками в ретро.\n➜ Инструмент: 'Система раннего оповещения'.",
    },
    'G': {
        'low': "🔴 Низкий балл (<2.0). Метрики не собираются, управление по ощущениям.\n➜ Начните с одной метрики: время выполнения типового заказа.\n➜ Собирайте её вручную в таблице 2 недели.\n➜ Инструмент: 'Цифры, которые можно собрать за день' (глава 7).",
        'medium': "🟡 Средний балл (2.0–3.0). Метрики собираются, но не используются для решений.\n➜ На еженедельном ретро смотрите динамику метрик.\n➜ Введите правило: 'отклонение более 20% требует анализа'.\n➜ Инструмент: 'Чек-лист на пятницу'.",
        'high': "🟢 Высокий балл (>3.0). Метрики управляют процессами.\n➜ Постройте простой дашборд.\n➜ Прогнозируйте будущие значения.\n➜ Инструмент: 'Система раннего оповещения'.",
    },
    'H': {
        'low': "🔴 Низкий балл (<2.0). Улучшений нет, команда не вовлечена.\n➜ Запустите еженедельное ретро (15 минут).\n➜ Заведите доску благодарности.\n➜ Инструмент: 'Быстрые победы' (глава 18).",
        'medium': "🟡 Средний балл (2.0–3.0). Улучшения есть, но нерегулярные.\n➜ Введите правило 'одно улучшение в неделю от отдела'.\n➜ Фиксируйте внедрённые улучшения.\n➜ Инструмент: 'Культура изменений' (глава 19).",
        'high': "🟢 Высокий балл (>3.0). Постоянные улучшения в крови.\n➜ Передайте эстафету команде.\n➜ Поощряйте инициативы публично.\n➜ Инструмент: 'Обучающаяся организация' (глава 32).",
    }
}

# -------------------- ФУНКЦИИ --------------------
def calculate_level(scores_by_block):
    questions_count = {'A':3,'B':4,'C':3,'D':2,'E':2,'F':3,'G':3,'H':3}
    averages = {}
    total_sum = 0
    total_questions = 0
    for block in scores_by_block:
        cnt = questions_count[block]
        avg = scores_by_block[block] / cnt
        averages[block] = avg
        total_sum += scores_by_block[block]
        total_questions += cnt
    overall_avg = total_sum / total_questions
    level = None
    for lvl, (low, high) in LEVEL_BOUNDARIES.items():
        if low <= overall_avg <= high:
            level = lvl
            break
    return level or 1, averages, overall_avg

def format_detailed_recommendations(averages):
    lines = []
    block_titles = {'A':'Требования','B':'Планирование','C':'Качество','D':'Версии','E':'Решения','F':'Риски','G':'Метрики','H':'Улучшения'}
    for block in sorted(averages.keys()):
        score = averages[block]
        title = block_titles.get(block, block)
        if score < 2.0:
            rec = BLOCK_RECOMMENDATIONS[block]['low']
        elif 2.0 <= score <= 3.0:
            rec = BLOCK_RECOMMENDATIONS[block]['medium']
        else:
            rec = BLOCK_RECOMMENDATIONS[block]['high']
        lines.append(f"📌 Блок {block} — {title} (балл {score:.2f})\n{rec}\n")
    return "\n".join(lines)

def format_result_text(level, averages, overall_avg, recommendations):
    text = f"📊 *Ваш уровень зрелости бизнес-процессов:* **{level}** (средний балл {overall_avg:.2f})\n\n"
    text += "_Средние баллы по блокам:_\n"
    block_names = {'A':'Требования','B':'Планирование','C':'Качество','D':'Версии','E':'Решения','F':'Риски','G':'Метрики','H':'Улучшения'}
    for block, avg in averages.items():
        text += f"• {block_names[block]}: {avg:.2f}\n"
    text += "\n---\n"
    text += f"*Общая рекомендация:*\n{recommendations.get(level, recommendations[1])}\n\n"
    text += "---\n*Детальные рекомендации по блокам:*\n"
    text += format_detailed_recommendations(averages)
    text += "\n---\n"
    text += "Если хотите разобрать результаты детально и получить план первых шагов, записывайтесь на первую консультацию (1,5 часа, 5000 ₽)."
    return text

# -------------------- ОБРАБОТЧИКИ --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info("Пользователь начал опрос | id=%s | username=%s | name=%s",
                user.id, user.username, user.full_name)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Я проведу диагностику зрелости ваших бизнес-процессов.\n"
        "Вам будет предложено 23 утверждения. Оцените каждое по шкале от 1 до 4:\n"
        "1 — почти никогда / не согласен\n"
        "2 — иногда / скорее нет\n"
        "3 — часто / скорее да\n"
        "4 — почти всегда / полностью согласен\n\n"
        "Отвечайте честно — это для вашей пользы. Начнём!"
    )
    context.user_data['answers'] = []
    context.user_data['current_q_index'] = 0
    q_text, _, _ = QUESTIONS[0]
    await update.message.reply_text(f"Вопрос 1/23:\n{q_text}\n\nВведите число от 1 до 4:")
    logger.info("Первый вопрос отправлен | user_id=%s", user.id)
    return ASKING

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_answer = update.message.text.strip()
    if not user_answer.isdigit():
        logger.warning("Некорректный ввод (не число) | user_id=%s | ввод='%s'", user.id, user_answer)
        await update.message.reply_text("❌ Ошибка: введите число от 1 до 4. Попробуйте ещё раз.")
        return ASKING
    value = int(user_answer)
    if value < 1 or value > 4:
        logger.warning("Некорректный ввод (вне диапазона) | user_id=%s | ввод=%d", user.id, value)
        await update.message.reply_text("❌ Ошибка: число должно быть от 1 до 4. Попробуйте ещё раз.")
        return ASKING
    current_idx = context.user_data['current_q_index']
    q_text, block, _ = QUESTIONS[current_idx]
    context.user_data['answers'].append((block, value))
    logger.info("Ответ получен | user_id=%s | вопрос=%d/%d | блок=%s | балл=%d",
                user.id, current_idx + 1, len(QUESTIONS), block, value)
    current_idx += 1
    context.user_data['current_q_index'] = current_idx
    if current_idx < len(QUESTIONS):
        next_q_text, _, _ = QUESTIONS[current_idx]
        await update.message.reply_text(f"Вопрос {current_idx+1}/{len(QUESTIONS)}:\n{next_q_text}\n\nВведите число от 1 до 4:")
        return ASKING
    else:
        answers = context.user_data['answers']
        scores = {'A':0,'B':0,'C':0,'D':0,'E':0,'F':0,'G':0,'H':0}
        for blk, val in answers:
            scores[blk] += val
        level, averages, overall = calculate_level(scores)
        result_text = format_result_text(level, averages, overall, RECOMMENDATIONS)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📅 Записаться на консультацию", callback_data="consult")]])
        await update.message.reply_text(result_text, reply_markup=keyboard, parse_mode='Markdown')
        context.user_data['final_results'] = {'level': level, 'averages': averages, 'overall': overall, 'text': result_text}
        logger.info("Опрос завершён | user_id=%s | уровень=%d | средний_балл=%.2f | ответы=%s",
                    user.id, level, overall, answers)
        return ConversationHandler.END

async def consult_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    logger.info("Заявка на консультацию | user_id=%s | username=%s | name=%s",
                user.id, user.username, user.full_name)
    final = context.user_data.get('final_results', {})
    level = final.get('level', 'не определён')
    overall = final.get('overall', 0)
    text_result = final.get('text', 'нет данных')
    # Экранируем HTML-спецсимволы в тексте результата для корректной отправки
    text_escaped = (text_result
                    .replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))
    msg = (
        f"📨 <b>Новая заявка на консультацию!</b>\n"
        f"👤 Имя: {user.full_name}\n"
        f"🆔 Username: @{user.username if user.username else 'нет'}\n"
        f"🆔 User ID: {user.id}\n"
        f"📊 Результат: уровень {level} (средний балл {overall:.2f})\n\n"
        f"<pre>{text_escaped}</pre>\n\n"
        f"Свяжитесь с клиентом для согласования времени."
    )
    try:
        await context.bot.send_message(chat_id=CONSULTANT_CHAT_ID, text=msg, parse_mode='HTML')
        logger.info("Уведомление отправлено консультанту | chat_id=%s | user_id=%s", CONSULTANT_CHAT_ID, user.id)
    except Exception as e:
        logger.error("Ошибка отправки уведомления консультанту | chat_id=%s | user_id=%s | error=%s",
                     CONSULTANT_CHAT_ID, user.id, e, exc_info=True)
    await query.edit_message_text(
        "✅ Спасибо! Ваша заявка отправлена. Я свяжусь с вами в ближайшее время для согласования консультации.",
        reply_markup=None
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    idx = context.user_data.get('current_q_index', 0)
    logger.info("Опрос отменён | user_id=%s | username=%s | остановился на вопросе %d",
                user.id, user.username, idx)
    await update.message.reply_text("Опрос отменён. Чтобы начать заново, нажмите /start")
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.warning("Неизвестная команда | user_id=%s | username=%s | текст='%s'",
                   user.id, user.username, update.message.text)
    await update.message.reply_text("Я понимаю только команду /start для начала опроса. Если вы в процессе, введите число от 1 до 4.")


async def error_handler(update: object, error: Exception) -> None:
    """Глобальный обработчик ошибок приложения"""
    logger.error("Необработанная ошибка | update=%s | error=%s",
                 update, error, exc_info=True)

def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_error_handler(error_handler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(consult_callback, pattern='^consult$'))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    logger.info("Бот запущен. Логи: %s/", LOG_DIR)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
