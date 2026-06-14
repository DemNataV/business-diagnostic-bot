#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram-бот для диагностики зрелости бизнес-процессов (на основе CMMI)
Автор: Наталия Демина (бизнес-терапия)

Функции:
- Последовательный опрос с валидацией ввода (1-4)
- Подсчет баллов по блокам и определение уровня зрелости (1-5)
- Вывод рекомендаций и кнопка записи на консультацию
- Отправка результатов консультанту в Telegram при нажатии кнопки

Требования: python-telegram-bot >= 20.7
Установка: pip install python-telegram-bot
"""

import logging
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

# -------------------- НАСТРОЙКИ --------------------
# Токен бота, полученный от @BotFather
BOT_TOKEN = "8104874567:AAGUcnZxyo3EmGQDU6aku2HfDMMR1qW5wEg" # <-- Замените на реальный токен

# ID вашего Telegram-аккаунта (куда отправлять уведомления о записи)
CONSULTANT_CHAT_ID = 307488211 # <-- Замените на ваш ID (можно узнать у @userinfobot)

# Состояния разговора
ASKING = range(1)

# -------------------- ВОПРОСЫ ОПРОСНИКА --------------------
# Каждый вопрос: текст, блок (буква), номер в блоке
QUESTIONS = [
    # Блок А. Управление требованиями (3 вопроса)
    ("А1. Когда клиент (или внутренний заказчик) что-то просит, мы записываем его просьбу в систему или документ, а не держим в голове или переписке.", "A", 1),
    ("А2. У нас есть чёткий процесс согласования изменений: если заказчик передумал, мы понимаем, как это повлияет на сроки и бюджет, и сообщаем ему об этом до начала работ.", "A", 2),
    ("А3. Мы редко переделываем работу из-за того, что «не так поняли» требования.", "A", 3),
    # Блок Б. Планирование и контроль (4 вопроса)
    ("Б1. Перед началом любой задачи мы оцениваем, сколько времени она займёт, и записываем эту оценку.", "B", 1),
    ("Б2. Фактическое время выполнения задач мы сравниваем с планом и анализируем расхождения.", "B", 2),
    ("Б3. Если мы отстаём от графика, мы пересматриваем план и сообщаем об этом заинтересованным сторонам (клиенту, руководству) до наступления дедлайна.", "B", 3),
    ("Б4. В компании есть утверждённый порядок приоритизации задач: все знают, что делать в первую очередь, а что можно отложить.", "B", 4),
    # Блок В. Обеспечение качества (3 вопроса)
    ("В1. Готовый результат (отчёт, код, товар, услуга) проверяется другим сотрудником (не автором) до того, как попадает к клиенту.", "C", 1),
    ("В2. У нас есть список обязательных проверок (чек-лист), который мы используем перед сдачей работы.", "C", 2),
    ("В3. Если обнаруживается ошибка, мы разбираем её причину и меняем процесс, чтобы ошибка не повторилась (а не просто исправляем и идём дальше).", "C", 3),
    # Блок Г. Управление конфигурацией (2 вопроса)
    ("Г1. Мы используем систему контроля версий (или хотя бы чёткое именование файлов), чтобы всегда знать, какая версия документа или продукта последняя.", "D", 1),
    ("Г2. У нас есть единое хранилище (папка, облако, репозиторий), где лежат все рабочие артефакты, и доступ к нему есть у всех членов команды.", "D", 2),
    # Блок Д. Анализ решений (2 вопроса)
    ("Д1. Перед тем как внедрить новую систему или изменить процесс, мы рассматриваем хотя бы 2-3 альтернативы и сравниваем их по критериям.", "E", 1),
    ("Д2. Мы фиксируем, почему приняли то или иное решение (протокол, запись в чате), чтобы потом можно было вернуться и понять логику.", "E", 2),
    # Блок Е. Управление рисками (3 вопроса)
    ("Е1. Мы регулярно (раз в месяц или чаще) обсуждаем: «что может пойти не так в ближайшее время?»", "F", 1),
    ("Е2. Для самых страшных рисков у нас есть план Б (как действовать, если событие наступит).", "F", 2),
    ("Е3. Если риск материализовался, мы анализируем, почему не смогли его предотвратить, и корректируем нашу систему.", "F", 3),
    # Блок Ж. Количественное управление (3 вопроса)
    ("Ж1. Мы собираем ключевые метрики нашей работы (время выполнения заказа, доля брака, загрузка сотрудников) не реже раза в месяц.", "G", 1),
    ("Ж2. Мы не просто собираем метрики, но и используем их для принятия решений (например, видим рост брака → ищем причину).", "G", 2),
    ("Ж3. Мы можем предсказать, сколько времени займёт типовой заказ, с погрешностью не более 20%.", "G", 3),
    # Блок З. Оптимизация и улучшение (3 вопроса)
    ("З1. У нас есть регулярный ритуал (например, планерка раз в неделю), где мы ищем, что улучшить в процессах.", "H", 1),
    ("З2. Любой сотрудник может предложить улучшение, и это предложение будет рассмотрено (без страха наказания).", "H", 2),
    ("З3. Мы отслеживаем, сколько улучшений внедрили за последний месяц, и гордимся этим.", "H", 3),
]

# Определение границ уровней по среднему баллу (по опроснику)
LEVEL_BOUNDARIES = {
    1: (0, 1.79),
    2: (1.8, 2.5),
    3: (2.6, 3.2),
    4: (3.3, 3.7),
    5: (3.71, 4.0),
}

# Тексты рекомендаций для каждого уровня
RECOMMENDATIONS = {
    1: """🔴 Уровень 1 (Начальный). Процессы хаотичны, успех зависит от героев. Высок риск срыва сроков и качества.
Рекомендация: Начните с внедрения базового планирования и контроля. Проведите бумажную симуляцию одного сквозного процесса, введите чек-лист для регулярных задач. Обратите внимание на блоки А (требования) и Б (планирование) — они самые критичные для старта.""",
    2: """🟠 Уровень 2 (Управляемый). На уровне отдельных проектов есть планирование и контроль, но нет единых стандартов. Уже можно доверять некритичные заказы.
Рекомендация: Стандартизируйте лучшие практики на всю компанию. Опишите основные процессы (приём заказа, передача в работу, сдача результата). Введите ретроспективы раз в неделю для выявления узких мест.""",
    3: """🟡 Уровень 3 (Определённый). Процессы стандартизированы и документированы. Компания предсказуема.
Рекомендация: Переходите к сбору метрик и управлению рисками. Заведите дашборд ключевых показателей (время цикла, брак). Начните регулярно обсуждать «что может пойти не так» и готовить планы Б.""",
    4: """🟢 Уровень 4 (Количественно управляемый). Компания управляется цифрами и может прогнозировать.
Рекомендация: Сфокусируйтесь на постоянных улучшениях. Внедрите систему раннего оповещения по ключевым метрикам. Поощряйте команду предлагать улучшения и внедряйте лучшее каждую неделю.""",
    5: """✅ Уровень 5 (Оптимизирующий). Непрерывное улучшение встроено в культуру. Ваш бизнес антихрупок.
Рекомендация: Поддерживайте текущий уровень, обучайте другие команды, выступайте как эталон. Продолжайте спираль улучшений: ищите следующие узкие места и работайте над ними.""",
}

# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------------------
def calculate_level(scores_by_block):
    """
    scores_by_block: dict {'A': сумма баллов, 'B': сумма, ...}
    Возвращает (уровень_общий, dict_средних_по_блокам)
    """
    # Количество вопросов в каждом блоке
    questions_count = {
        'A': 3, 'B': 4, 'C': 3, 'D': 2, 'E': 2, 'F': 3, 'G': 3, 'H': 3
    }
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
    # Определяем уровень по overall_avg
    level = None
    for lvl, (low, high) in LEVEL_BOUNDARIES.items():
        if low <= overall_avg <= high:
            level = lvl
            break
    if level is None:
        level = 1 # fallback
    return level, averages, overall_avg

def format_result_text(level, averages, overall_avg, recommendations):
    """Форматирует текст результата для отправки пользователю"""
    text = f"📊 *Ваш уровень зрелости бизнес-процессов:* **{level}** (средний балл {overall_avg:.2f})\n\n"
    text += "_Средние баллы по блокам:_\n"
    for block, avg in averages.items():
        block_names = {
            'A': 'Требования', 'B': 'Планирование', 'C': 'Качество',
            'D': 'Версии', 'E': 'Решения', 'F': 'Риски',
            'G': 'Метрики', 'H': 'Улучшения'
        }
        text += f"• {block_names[block]}: {avg:.2f}\n"
    text += "\n---\n"
    text += recommendations.get(level, recommendations[1])
    text += "\n\n---\n"
    text += "Если хотите разобрать результаты детально и получить план первых шагов, записывайтесь на первую консультацию (1,5 часа, 5000 ₽)."
    return text

# -------------------- ОБРАБОТЧИКИ --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: приветствие и первый вопрос"""
    user = update.effective_user
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
    # Инициализируем хранилище ответов
    context.user_data['answers'] = [] # список кортежей (блок, значение)
    context.user_data['current_q_index'] = 0
    # Задаем первый вопрос
    q_text, _, _ = QUESTIONS[0]
    await update.message.reply_text(f"Вопрос 1/23:\n{q_text}\n\nВведите число от 1 до 4:")
    return ASKING

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа пользователя"""
    user_answer = update.message.text.strip()
    # Проверяем, что введено целое число от 1 до 4
    if not user_answer.isdigit():
        await update.message.reply_text("❌ Ошибка: введите число от 1 до 4. Попробуйте ещё раз.")
        return ASKING
    value = int(user_answer)
    if value < 1 or value > 4:
        await update.message.reply_text("❌ Ошибка: число должно быть от 1 до 4. Попробуйте ещё раз.")
        return ASKING

    # Сохраняем ответ
    current_idx = context.user_data['current_q_index']
    q_text, block, _ = QUESTIONS[current_idx]
    context.user_data['answers'].append((block, value))
    current_idx += 1
    context.user_data['current_q_index'] = current_idx

    # Если есть следующий вопрос
    if current_idx < len(QUESTIONS):
        next_q_text, _, _ = QUESTIONS[current_idx]
        await update.message.reply_text(f"Вопрос {current_idx+1}/{len(QUESTIONS)}:\n{next_q_text}\n\nВведите число от 1 до 4:")
        return ASKING
    else:
        # Опрос завершён, подводим итоги
        answers = context.user_data['answers']
        # Группируем по блокам
        scores = { 'A':0, 'B':0, 'C':0, 'D':0, 'E':0, 'F':0, 'G':0, 'H':0 }
        for blk, val in answers:
            scores[blk] += val
        level, averages, overall = calculate_level(scores)
        result_text = format_result_text(level, averages, overall, RECOMMENDATIONS)

        # Кнопка "Записаться на консультацию"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Записаться на консультацию", callback_data="consult")]
        ])
        await update.message.reply_text(result_text, reply_markup=keyboard, parse_mode='Markdown')
        # Сохраняем результаты в user_data для возможной отправки
        context.user_data['final_results'] = {
            'level': level,
            'averages': averages,
            'overall': overall,
            'text': result_text
        }
        return ConversationHandler.END

async def consult_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на кнопку записи"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    # Получаем сохранённые результаты (если есть)
    final = context.user_data.get('final_results', {})
    level = final.get('level', 'не определён')
    overall = final.get('overall', 0)
    text_result = final.get('text', 'нет данных')
    # Формируем сообщение для консультанта
    msg = (
        f"📨 *Новая заявка на консультацию!*\n"
        f"👤 Имя: {user.full_name}\n"
        f"🆔 Username: @{user.username if user.username else 'нет'}\n"
        f"🆔 User ID: {user.id}\n"
        f"📊 Результат опроса: уровень {level} (средний балл {overall:.2f})\n\n"
        f"<pre>{text_result}</pre>\n\n"
        f"Свяжитесь с клиентом для согласования времени."
    )
    # Отправляем консультанту
    await context.bot.send_message(chat_id=CONSULTANT_CHAT_ID, text=msg, parse_mode='HTML')
    # Подтверждаем пользователю
    await query.edit_message_text(
        "✅ Спасибо! Ваша заявка отправлена. Я свяжусь с вами в ближайшее время для согласования консультации.",
        reply_markup=None
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена опроса"""
    await update.message.reply_text("Опрос отменён. Чтобы начать заново, нажмите /start")
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на неизвестную команду вне диалога"""
    await update.message.reply_text("Я понимаю только команду /start для начала опроса. Если вы в процессе, введите число от 1 до 4.")

# -------------------- MAIN --------------------
def main():
    # Настройка логирования
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler для опроса
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(consult_callback, pattern='^consult$'))
    application.add_handler(MessageHandler(filters.COMMAND, unknown)) # обработка других команд

    # Запуск бота (polling)
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()