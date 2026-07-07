# -*- coding: utf-8 -*-
"""
Бот автопостинга для мессенджера MAX.

Две кнопки:
  • "Оповещение" — публикует в канал сообщение о ракетной опасности.
  • "Отмена"     — публикует в канал сообщение об отбое.

После публикации бот отвечает нажавшему: "Сообщение опубликовано".
"""

import os
import json
import sys
import time
import requests

# Печатаем логи сразу, без буферизации (чтобы было видно в консоли/файле)
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ─────────────────────────── НАСТРОЙКИ ───────────────────────────

# Токен бота и пароль берутся из config.py (он НЕ попадает в git — см. .gitignore).
# Скопируйте config.example.py в config.py и впишите свои значения.
try:
    from config import TOKEN, PASSWORD
except ImportError:
    raise SystemExit(
        "Не найден config.py с токеном и паролем.\n"
        "Скопируйте config.example.py в config.py "
        "и впишите TOKEN и PASSWORD."
    )

# Ссылка на канал, в который публикуем. chat_id определяется автоматически по ней.
# ВАЖНО: бот должен быть добавлен АДМИНИСТРАТОРОМ в этот канал.
CHANNEL_LINK = "https://max.ru/Shapsha_VV"

# Если авто-определение канала не сработает — можно вписать chat_id вручную.
CHANNEL_CHAT_ID = None

# Базовый адрес MAX Bot API
API_URL = "https://botapi.max.ru"

# Тексты сообщений, публикуемых в канале
TEXT_ALERT = (
    "❗️Внимание, в "
    "Калужской области "
    "объявлена ракетная "
    "опасность! \n\n"
    "Укройтесь в помещении "
    "без окон и со сплошными "
    "стенами. Если вы находитесь "
    "на улице или в автотранспорте - "
    "направляйтесь в ближайшее "
    "безопасное место со "
    "сплошными стенами и "
    "не подходите к окнам."
)

TEXT_CANCEL = (
    "✅ Отбой ракетной "
    "опасности в Калужской "
    "области!"
)

# Пароль PASSWORD импортируется из config.py (см. верх файла)

# Файл, где хранятся ID уже авторизованных пользователей
# (лежит рядом с bot.py; авторизация сохраняется после перезапуска)
AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "authorized.json")

# Подписи и служебные тексты бота
BTN_ALERT = "Оповещение"          # Оповещение
BTN_CANCEL = "Отмена"                                # Отмена
MSG_CHOOSE = "Выберите действие:"  # Выберите действие:
MSG_PUBLISHED = "✅ Сообщение опубликовано"  # ✅ Сообщение опубликовано
MSG_ENTER_PASSWORD = "Введите пароль"  # Введите пароль
MSG_WRONG_PASSWORD = "Неверный пароль. Введите пароль:"  # Неверный пароль

# ─────────────────────────── HTTP-СЛОЙ ───────────────────────────

session = requests.Session()
session.headers.update({"Authorization": TOKEN})


def api_get(path, **params):
    r = session.get(f"{API_URL}{path}", params=params, timeout=95)
    r.raise_for_status()
    return r.json()


def api_post(path, json=None, **params):
    r = session.post(f"{API_URL}{path}", params=params, json=json or {}, timeout=30)
    r.raise_for_status()
    return r.json()


# ─────────────────────────── ЛОГИКА ───────────────────────────

def build_keyboard():
    """Клавиатура с двумя кнопками."""
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [{"type": "callback", "text": BTN_ALERT, "payload": "alert"}],
                [{"type": "callback", "text": BTN_CANCEL, "payload": "cancel"}],
            ]
        },
    }


def send_message(text, chat_id=None, user_id=None, with_keyboard=False):
    """Отправляет сообщение в чат ЛИБО пользователю.

    MAX API требует ровно один адресат: если задан chat_id — используем его,
    иначе user_id. Передавать оба сразу нельзя (API вернёт ошибку).
    """
    body = {"text": text}
    if with_keyboard:
        body["attachments"] = [build_keyboard()]
    params = {}
    if chat_id is not None:
        params["chat_id"] = chat_id
    elif user_id is not None:
        params["user_id"] = user_id
    return api_post("/messages", json=body, **params)


def answer_callback(callback_id, notification=None):
    """Убирает «часики» на нажатой кнопке. Не критично: ошибки тут не мешают."""
    if not callback_id:
        return
    body = {"notification": notification} if notification else {"notification": " "}
    try:
        api_post("/answers", json=body, callback_id=callback_id)
    except Exception as e:
        print("answer_callback не удался (не критично):", e)


def _link_key(link):
    """Последний сегмент ссылки в нижнем регистре (для устойчивого сравнения)."""
    return (link or "").rstrip("/").split("/")[-1].lower()


def resolve_channel_id():
    """Ищет chat_id канала по ссылке среди чатов бота.

    Возвращает chat_id или None, если бот ещё не добавлен в канал.
    Не выбрасывает исключение — чтобы бот не падал до добавления в канал.
    """
    if CHANNEL_CHAT_ID is not None:
        return CHANNEL_CHAT_ID
    try:
        data = api_get("/chats", count=100)
    except Exception as e:
        print("Не удалось получить список чатов:", e)
        return None
    target = _link_key(CHANNEL_LINK)
    for chat in data.get("chats", []):
        if _link_key(chat.get("link")) == target:
            return chat["chat_id"]
    return None


# ─────────────────────────── АВТОРИЗАЦИЯ ───────────────────────────

def load_authorized():
    """Читает список авторизованных пользователей из файла."""
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_authorized(users):
    """Сохраняет список авторизованных пользователей в файл."""
    try:
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(users), f)
    except Exception as e:
        print("Не удалось сохранить авторизацию:", e)


# Множество ID пользователей, уже прошедших авторизацию по паролю
authorized_users = load_authorized()


def show_menu(chat_id=None, user_id=None):
    """Показывает сообщение «Выберите действие:» с кнопками."""
    send_message(MSG_CHOOSE, chat_id=chat_id, user_id=user_id, with_keyboard=True)


def handle_button(payload, channel_id, reply_user_id, callback_id):
    """Публикует сообщение в канал по нажатой кнопке и подтверждает публикацию.

    Все ответы оператору идут строго в личку по user_id — в канал уходит
    ТОЛЬКО сам текст оповещения (chat_id канала), больше ничего.
    """
    # Если канал ещё не определён — пробуем найти его сейчас
    if not channel_id:
        channel_id = resolve_channel_id()
    if not channel_id:
        answer_callback(callback_id)
        send_message(
            "Бот не добавлен администратором в канал " + CHANNEL_LINK +
            ". Публикация невозможна. Добавьте бота админом в канал.",
            user_id=reply_user_id, with_keyboard=True,
        )
        return

    text = TEXT_ALERT if payload == "alert" else TEXT_CANCEL
    print(f"Кнопка '{payload}': публикую в канал {channel_id}, ответ user={reply_user_id}")
    try:
        send_message(text, chat_id=channel_id)
    except Exception as e:  # публикация не удалась — сообщаем об ошибке в личку
        answer_callback(callback_id)
        send_message("Ошибка публикации: " + str(e),
                     user_id=reply_user_id, with_keyboard=True)
        return

    # Успех: подтверждение БЕЗ кнопок, затем новое «Выберите действие» С кнопками — в личку
    send_message(MSG_PUBLISHED, user_id=reply_user_id, with_keyboard=False)
    send_message(MSG_CHOOSE, user_id=reply_user_id, with_keyboard=True)
    answer_callback(callback_id)


def _is_private_dialog(recipient):
    """True только для личного диалога 1-на-1.

    Каналы и группы отсекаются: у диалогов chat_id положительный,
    у каналов/групп — отрицательный; также явно исключаем тип channel/chat.
    Это защищает от ответа «Введите пароль» прямо в канал на чужой пост.
    """
    ct = recipient.get("chat_type")
    if ct in ("channel", "chat"):
        return False
    cid = recipient.get("chat_id")
    return isinstance(cid, int) and cid > 0


def handle_update(update, channel_id):
    utype = update.get("update_type")

    # Пользователь открыл бота (нажал /start) — всегда личный диалог
    if utype == "bot_started":
        uid = update.get("user_id") or update.get("user", {}).get("user_id")
        if not uid:
            return
        if uid in authorized_users:
            show_menu(user_id=uid)
        else:
            send_message(MSG_ENTER_PASSWORD, user_id=uid)

    # Пользователь написал боту
    elif utype == "message_created":
        msg = update.get("message", {})
        recipient = msg.get("recipient", {})
        sender_id = msg.get("sender", {}).get("user_id")

        # ВАЖНО: реагируем ТОЛЬКО на личные сообщения боту.
        # Посты в каналах и сообщения в группах игнорируем полностью,
        # иначе бот ответит «Введите пароль» прямо в канал.
        if not sender_id or not _is_private_dialog(recipient):
            return

        text = (msg.get("body", {}).get("text") or "").strip()

        if sender_id in authorized_users:
            show_menu(user_id=sender_id)
        elif text == PASSWORD:
            authorized_users.add(sender_id)
            save_authorized(authorized_users)
            print(f"Пользователь {sender_id} авторизован")
            show_menu(user_id=sender_id)
        elif text in ("/start", ""):
            send_message(MSG_ENTER_PASSWORD, user_id=sender_id)
        else:
            send_message(MSG_WRONG_PASSWORD, user_id=sender_id)

    # Нажата кнопка
    elif utype == "message_callback":
        cb = update.get("callback", {})
        reply_user_id = cb.get("user", {}).get("user_id")
        if not reply_user_id:
            return

        # Кнопки доступны только авторизованным; ответ — строго в личку
        if reply_user_id not in authorized_users:
            answer_callback(cb.get("callback_id"))
            send_message(MSG_ENTER_PASSWORD, user_id=reply_user_id)
            return

        handle_button(
            payload=cb.get("payload"),
            channel_id=channel_id,
            reply_user_id=reply_user_id,
            callback_id=cb.get("callback_id"),
        )


def main():
    me = api_get("/me")
    print("Бот запущен:", me.get("name"), "@" + me.get("username", ""))
    channel_id = resolve_channel_id()
    if channel_id:
        print("Канал:", channel_id)
    else:
        print("ВНИМАНИЕ: канал", CHANNEL_LINK,
              "не найден. Добавьте бота АДМИНИСТРАТОРОМ в канал —",
              "он определится автоматически, деплой не нужен.")

    marker = None
    while True:
        try:
            # Пока канал не определён — пробуем найти его перед каждым опросом
            if channel_id is None:
                channel_id = resolve_channel_id()
                if channel_id:
                    print("Канал определён:", channel_id)
            params = {"timeout": 90}
            if marker is not None:
                params["marker"] = marker
            data = api_get("/updates", **params)
            for update in data.get("updates", []):
                try:
                    handle_update(update, channel_id)
                except Exception as e:
                    print("Ошибка обработки:", e)
            marker = data.get("marker", marker)
        except requests.exceptions.RequestException as e:
            print("Сетевая ошибка, повтор через 5с:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
