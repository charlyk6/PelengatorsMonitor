from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import storage

KIND_LABEL = {
    "hardware": "железо",
    "soft": "софт",
}


def kind_code(kind: str) -> str:
    return "h" if kind == "hardware" else "s"


def kind_from_code(code: str) -> str:
    return "hardware" if code == "h" else "soft"

TYPE_FIELDS = {
    "name": "название",
    "board": "плата",
    "mic_distance": "расстояние между микрофонами",
    "axis_distance": "расстояние между осями",
}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def _short(text: str, limit: int = 36) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def home_screen() -> tuple[str, InlineKeyboardMarkup]:
    stats = storage.counts()
    text = (
        "<b>Мониторинг пеленгаторов</b>\n\n"
        f"Типы: <code>{stats['types']}</code>\n"
        f"Пеленгаторы: <code>{stats['pelengators']}</code>\n"
        f"Ошибки: <code>{stats['errors']}</code>"
        f"  ·  железо <code>{stats['hardware']}</code>"
        f"  ·  софт <code>{stats['soft']}</code>\n\n"
        "Откройте раздел — дальше всё кнопками."
    )
    keyboard = _markup(
        [
            [
                _btn("Типы", "nav:types"),
                _btn("Пеленгаторы", "nav:pels"),
            ],
            [_btn("Ошибки", "nav:errs")],
        ]
    )
    return text, keyboard


def types_screen() -> tuple[str, InlineKeyboardMarkup]:
    types = storage.list_types()
    if types:
        text = "<b>Типы пеленгаторов</b>\nНажмите тип, чтобы открыть карточку."
    else:
        text = "<b>Типы пеленгаторов</b>\nПока пусто. Добавьте первый тип."

    rows = [
        [
            _btn(
                f"{item['id']}. {_short(item['name'])}",
                f"type:v:{item['id']}",
            )
        ]
        for item in types
    ]
    rows.append([_btn("＋ Новый тип", "type:add")])
    rows.append([_btn("← Меню", "nav:home")])
    return text, _markup(rows)


def type_card(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    used = storage.count_pelengators_of_type(type_id)
    text = (
        f"<b>Тип #{item['id']}</b> — {escape(item['name'])}\n\n"
        f"Плата: <code>{escape(item['board'])}</code>\n"
        f"Микрофоны: <code>{escape(item['mic_distance'])}</code>\n"
        f"Оси: <code>{escape(item['axis_distance'])}</code>\n"
        f"Пеленгаторов этого типа: <code>{used}</code>"
    )
    keyboard = _markup(
        [
            [
                _btn("Изменить", f"type:e:{type_id}"),
                _btn("Удалить", f"type:d:{type_id}"),
            ],
            [_btn("← К типам", "nav:types")],
        ]
    )
    return text, keyboard


def type_edit_screen(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    text = (
        f"<b>Что изменить в типе #{type_id}?</b>\n"
        f"Сейчас: {escape(item['name'])}"
    )
    keyboard = _markup(
        [
            [
                _btn("Название", f"type:f:{type_id}:name"),
                _btn("Плата", f"type:f:{type_id}:board"),
            ],
            [
                _btn("Микрофоны", f"type:f:{type_id}:mic_distance"),
                _btn("Оси", f"type:f:{type_id}:axis_distance"),
            ],
            [_btn("← Назад", f"type:v:{type_id}")],
        ]
    )
    return text, keyboard


def confirm_delete_type(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    used = storage.count_pelengators_of_type(type_id)
    if used:
        text = (
            f"Тип <b>{escape(item['name'])}</b> нельзя удалить: "
            f"на нём ещё {used} пеленгатор(ов).\n"
            "Сначала смените им тип или удалите их."
        )
        keyboard = _markup([[_btn("← Назад", f"type:v:{type_id}")]])
        return text, keyboard
    text = f"Удалить тип <b>{escape(item['name'])}</b>?"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"type:do:{type_id}"),
                _btn("Отмена", f"type:v:{type_id}"),
            ]
        ]
    )
    return text, keyboard


def pelengators_screen() -> tuple[str, InlineKeyboardMarkup]:
    items = storage.list_pelengators()
    if items:
        text = "<b>Пеленгаторы</b>\nНажмите устройство, чтобы открыть карточку."
    else:
        text = "<b>Пеленгаторы</b>\nПока пусто. Добавьте первое устройство."

    rows = []
    for item in items:
        errors = item["error_count"]
        suffix = f" · {errors} ош." if errors else ""
        rows.append(
            [
                _btn(
                    f"{item['id']} · {_short(item['type_name'], 22)}{suffix}",
                    f"pel:v:{item['id']}",
                )
            ]
        )
    rows.append([_btn("＋ Новый пеленгатор", "pel:add")])
    rows.append([_btn("← Меню", "nav:home")])
    return text, _markup(rows)


def pelengator_card(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    errors = storage.list_errors_for_pelengator(pelengator_id)
    lines = [
        f"<b>Пеленгатор #{item['id']}</b>",
        f"Тип: {escape(item['type_name'])} <code>#{item['type_id']}</code>",
        f"Плата: <code>{escape(item['board'])}</code>",
        f"Микрофоны: <code>{escape(item['mic_distance'])}</code>",
        f"Оси: <code>{escape(item['axis_distance'])}</code>",
        "",
        f"<b>Ошибки</b> · {len(errors)}",
    ]
    if errors:
        for error in errors[-8:]:
            kind = KIND_LABEL.get(error["kind"], error["kind"])
            lines.append(
                f"#{error['id']} {kind} — {escape(_short(error['description'], 48))}"
            )
        if len(errors) > 8:
            lines.append(f"… и ещё {len(errors) - 8}")
    else:
        lines.append("Пока чисто.")

    error_buttons = [
        [
            _btn(
                f"#{error['id']} · {KIND_LABEL.get(error['kind'], error['kind'])} · {_short(error['description'], 28)}",
                f"err:v:{error['id']}",
            )
        ]
        for error in errors[-5:]
    ]
    keyboard = _markup(
        [
            [_btn("＋ Ошибка", f"err:at:{pelengator_id}")],
            [
                _btn("Сменить тип", f"pel:ct:{pelengator_id}"),
                _btn("Удалить", f"pel:d:{pelengator_id}"),
            ],
            *error_buttons,
            [_btn("← К пеленгаторам", "nav:pels")],
        ]
    )
    return "\n".join(lines), keyboard


def pelengator_pick_type_screen(
    callback_prefix: str,
    back: str,
    title: str,
) -> tuple[str, InlineKeyboardMarkup]:
    types = storage.list_types()
    if not types:
        text = "Сначала создайте хотя бы один тип."
        return text, _markup([[_btn("К типам", "nav:types"), _btn("← Меню", "nav:home")]])

    rows = [
        [_btn(f"{item['id']}. {_short(item['name'])}", f"{callback_prefix}{item['id']}")]
        for item in types
    ]
    rows.append([_btn("← Назад", back)])
    return title, _markup(rows)


def confirm_delete_pelengator(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    errors = storage.list_errors_for_pelengator(pelengator_id)
    extra = (
        f" Вместе с ним удалятся ошибки: {len(errors)}."
        if errors
        else ""
    )
    text = f"Удалить пеленгатор <b>#{item['id']}</b>?{extra}"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"pel:do:{pelengator_id}"),
                _btn("Отмена", f"pel:v:{pelengator_id}"),
            ]
        ]
    )
    return text, keyboard


def errors_hub_screen() -> tuple[str, InlineKeyboardMarkup]:
    stats = storage.counts()
    text = (
        "<b>Ошибки</b>\n"
        "Сначала выберите, какие смотреть."
    )
    keyboard = _markup(
        [
            [
                _btn(f"Железо · {stats['hardware']}", "err:list:h"),
                _btn(f"Софт · {stats['soft']}", "err:list:s"),
            ],
            [_btn("← Меню", "nav:home")],
        ]
    )
    return text, keyboard


def errors_screen(kind: str) -> tuple[str, InlineKeyboardMarkup]:
    label = KIND_LABEL[kind]
    items = storage.list_errors(kind)
    if items:
        text = f"<b>Ошибки · {label}</b>\nНажмите запись, чтобы открыть."
    else:
        text = f"<b>Ошибки · {label}</b>\nПока пусто."

    rows = [
        [
            _btn(
                f"#{item['id']} · {item['pelengator_id']} · {_short(item['description'], 22)}",
                f"err:v:{item['id']}",
            )
        ]
        for item in items
    ]
    rows.append([_btn(f"＋ Добавить ({label})", f"err:add:{kind_code(kind)}")])
    rows.append([_btn("← К ошибкам", "nav:errs")])
    return text, _markup(rows)


def error_card(error_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_error(error_id)
    if item is None:
        return None
    kind = KIND_LABEL.get(item["kind"], item["kind"])
    other_kind = "soft" if item["kind"] == "hardware" else "hardware"
    other_label = KIND_LABEL[other_kind]
    text = (
        f"<b>Ошибка #{item['id']}</b>\n\n"
        f"Пеленгатор: <code>{item['pelengator_id']}</code>\n"
        f"Тип: <b>{kind}</b>\n"
        f"Описание: {escape(item['description'])}"
    )
    keyboard = _markup(
        [
            [_btn("Изменить описание", f"err:e:{error_id}")],
            [_btn(f"Сменить на {other_label}", f"err:sk:{error_id}:{other_kind[0]}")],
            [_btn("Удалить", f"err:d:{error_id}")],
            [
                _btn("К пеленгатору", f"pel:v:{item['pelengator_id']}"),
                _btn("← К списку", f"err:list:{kind_code(item['kind'])}"),
            ],
        ]
    )
    return text, keyboard


def confirm_delete_error(error_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_error(error_id)
    if item is None:
        return None
    text = f"Удалить ошибку <b>#{item['id']}</b>?"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"err:do:{error_id}"),
                _btn("Отмена", f"err:v:{error_id}"),
            ]
        ]
    )
    return text, keyboard


def kind_screen(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"Ошибка для пеленгатора <b>#{pelengator_id}</b>\n"
        "Это железо или софт?"
    )
    keyboard = _markup(
        [
            [
                _btn("Железо", "err:k:h"),
                _btn("Софт", "err:k:s"),
            ],
            [_btn("← Назад", f"pel:v:{pelengator_id}")],
        ]
    )
    return text, keyboard


def pick_pelengator_for_error(kind: str) -> tuple[str, InlineKeyboardMarkup]:
    items = storage.list_pelengators()
    label = KIND_LABEL[kind]
    if not items:
        text = "Сначала добавьте пеленгатор."
        return text, _markup([[_btn("К пеленгаторам", "nav:pels")]])
    rows = [
        [_btn(f"{item['id']} · {_short(item['type_name'])}", f"err:go:{item['id']}:{kind_code(kind)}")]
        for item in items
    ]
    rows.append([_btn("← Назад", f"err:list:{kind_code(kind)}")])
    return f"Куда записать ошибку ({label})?", _markup(rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return _markup([[_btn("Отмена", "conv:cancel")]])


def prompt(text: str) -> tuple[str, InlineKeyboardMarkup]:
    return f"{text}\n\n<i>Напишите ответ сообщением</i>", cancel_keyboard()
