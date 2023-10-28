import time
import requests
import logging
import telegram
import os
import sys
import exceptions

# from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from http import HTTPStatus
from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
RETRY_PERIOD_IN_SECONDS = RETRY_PERIOD
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s - %(filename)s',)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))


def check_tokens():
    """Проверяет доступность переменных окружения.

    Если отсутствуют переменные окружения,
    сообщаем их имена, при этом бот завершает работу.
    """
    tokens = {'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
              'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
              'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID}
    empty_tokens = [name for name, value in tokens.items() if not value]
    if empty_tokens:
        error = f'Не все токены указаны корректно: {", ".join(empty_tokens)}'
        logger.critical(error)
        raise ValueError(error)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.

    Чат определяется переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра: экземпляр класса Bot
    и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as error:
        raise f'Ошибка при отправке сообщения: {error}'
    logger.debug(f'Сообщение {message} отправлено')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса домашек.

    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params=params
                                )
        if response.status_code != HTTPStatus.OK:
            raise requests.HTTPError(
                f'Ошибка API-сервиса. - '
                f'Адрес запроса {ENDPOINT} - '
                f'Параметры запроса {params} - '
                f'Код ответа: {response.status_code} - '
                f'Тело ответа: {response.content}'
            )
    except Exception:
        raise exceptions.ServiceUnavailable(
            'Ошибка при запросе к основному API'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации.

    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    # Проверим корректность формата данных
    if not isinstance(response, dict):
        raise TypeError('Данные не соответствуют формату JSON')
    # Проверим наличие необходимых ключей в ответе
    if 'homeworks' not in response or 'current_date' not in response:
        raise TypeError('Некорректный формат ответа сервиса')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Данные не являются списком')
    homework = response.get('homeworks')
    return homework


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе ее статус.

    В качестве параметра функция получает только один элемент
    из списка домашних работ. Функция возвращает
    подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_VERDICTS
    """
    homework_status = homework.get('status')
    homework_name = homework.get('homework_name')
    if not homework_name:
        raise exceptions.DataError('В данных не указано название домашки')
    if not homework_status or homework_status not in HOMEWORK_VERDICTS:
        raise exceptions.DataError('Что-то не так со статусом домашки')
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.debug('Поехали!')
    if check_tokens():
        error_message = 'Указаны не все переменные окружения'
        logger.critical(error_message)
        sys.exit(error_message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0  # int(time.time())
    previous_message = ''
    while True:
        try:
            response_json = get_api_answer(timestamp)
            timestamp = response_json.get('current_date')
            if not timestamp:
                raise exceptions.DataError('В данных не указана текущая дата')
            homeworks = check_response(response_json)
            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    if message != previous_message:
                        send_message(bot, message)
                        previous_message = message
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(message)
            send_message(bot, message)
        finally:
            # Подождать 10 минут и снова сделать запрос к API
            time.sleep(RETRY_PERIOD_IN_SECONDS)


if __name__ == '__main__':
    main()
