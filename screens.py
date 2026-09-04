from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import storage

KIND_LABEL = {
    "hardware": "🔩 Железо",
    "soft": "💾 Софт",
}
KIND_LABEL_SHORT = {
    "hardware": "🔩 железо",
    "soft": "💾 софт",
}


def kind_code(kind: str) -> str:
    return "h" if kind == "hardware" else "s"


def kind_from_code(code: str) -> str:
    return "hardware" if code == "h" else "soft"


TYPE_FIELDS = {
    "name": "название",
    **storage.TEXT_FIELDS,
}


def _has_changes(values: dict, type_values: dict) -> bool:
    for field in storage.TEXT_FIELDS:
        if values.get(field) != type_values.get(field):
            return True
    for field in storage.FLAG_FIELDS:
        if bool(values.get(field)) != bool(type_values.get(field)):
            return True
    return False


def _hw_text_lines(values: dict, type_values: dict | None = None) -> list[str]:
    lines = []
    for field, label in storage.TEXT_FIELDS.items():
        raw = values.get(field) or ""
        shown = escape(raw) if raw else "—"
        changed = type_values is not None and values.get(field) != type_values.get(field)
        mark = " ❗" if changed else ""
        lines.append(f"<b>{label}:</b> <code>{shown}</code>{mark}")
    return lines


def _hw_flag_lines(values: dict, type_values: dict | None = None) -> list[str]:
    lines = []
    for title, flags in storage.FLAG_GROUPS:
        lines.append(f"<b>{title}:</b>")
        for field, label in flags:
            on = bool(values.get(field))
            changed = type_values is not None and bool(values.get(field)) != bool(type_values.get(field))
            mark = "✅" if on else "☐"
            suffix = " ❗" if changed else ""
            lines.append(f"  {mark} {label}{suffix}")
    return lines


def _status_lines(item: dict) -> list[str]:
    location = item.get("location") or ""
    reserved = item.get("reserved") or ""
    loc_shown = escape(location) if location else "—"
    if reserved:
        res_shown = f"❌ {escape(reserved)}"
    else:
        res_shown = "✅ свободно"
    return [
        f"<b>Бронь:</b> {res_shown}",
        f"<b>Место:</b> {loc_shown}",
    ]


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def _short(text: str, limit: int = 36) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# ──────────────────────────────────────────
# Главное меню
# ──────────────────────────────────────────

def home_screen(is_admin: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    stats = storage.counts()
    text = (
        "📡 <b>Мониторинг пеленгаторов</b>\n\n"
        f"Шаблоны: <b>{stats['types']}</b>\n"
        f"Пеленгаторы: <b>{stats['pelengators']}</b>\n"
        f"Ошибки: <b>{stats['errors']}</b>"
        f"  <i>(🔩 {stats['hardware']} · 💾 {stats['soft']})</i>"
    )
    rows = [
        [
            _btn("Шаблоны", "nav:types"),
            _btn("Пеленгаторы", "nav:pels"),
        ],
        [_btn("⚠️ Ошибки", "nav:errs")],
    ]
    if is_admin:
        rows.append([_btn("Пользователи", "nav:users")])
    return text, _markup(rows)


# ──────────────────────────────────────────
# Шаблоны
# ──────────────────────────────────────────

def types_screen() -> tuple[str, InlineKeyboardMarkup]:
    types = storage.list_types()
    if types:
        text = "<b>Шаблоны пеленгаторов</b>"
    else:
        text = "<b>Шаблоны пеленгаторов</b>\nПока пусто — добавьте первый шаблон."

    rows = [
        [_btn(f"{item['id']}. {_short(item['name'])}", f"type:v:{item['id']}")]
        for item in types
    ]
    rows.append([_btn("＋ Новый шаблон", "type:add")])
    rows.append([_btn("← Меню", "nav:home")])
    return text, _markup(rows)


def type_card(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    used = storage.count_pelengators_of_type(type_id)
    lines = [
        f"<b>Шаблон #{item['id']}</b> — {escape(item['name'])}",
        "",
        *_hw_text_lines(item),
        "",
        *_hw_flag_lines(item),
        "",
        f"Пеленгаторов на шаблоне: <b>{used}</b>",
    ]
    keyboard = _markup(
        [
            [
                _btn("✏️ Изменить", f"type:e:{type_id}"),
                _btn("🗑 Удалить", f"type:d:{type_id}"),
            ],
            [_btn("← К шаблонам", "nav:types")],
        ]
    )
    return "\n".join(lines), keyboard


def type_edit_screen(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    text = (
        f"✏️ <b>Шаблон #{type_id}</b> — {escape(item['name'])}\n"
        "<i>Нажмите поле для изменения. Галочки переключаются кнопкой.</i>"
    )
    rows = [
        [_btn("Название", f"type:f:{type_id}:name")],
        [
            _btn("Микрофоны", f"type:f:{type_id}:mic_distance"),
            _btn("Оси", f"type:f:{type_id}:axis_distance"),
        ],
        [
            _btn("Вычислитель", f"type:f:{type_id}:computer"),
            _btn("Агрегатор", f"type:f:{type_id}:aggregator"),
        ],
        [
            _btn("Кол-во микр.", f"type:f:{type_id}:mic_count"),
            _btn("Носитель", f"type:f:{type_id}:mic_carrier"),
        ],
    ]
    for title, flags in storage.FLAG_GROUPS:
        rows.append([_btn(f"── {title} ──", f"type:e:{type_id}")])
        flag_row = []
        for field, label in flags:
            mark = "✅" if item[field] else "☐"
            flag_row.append(_btn(f"{mark} {label}", f"type:tg:{type_id}:{field}"))
        rows.append(flag_row)
    rows.append([_btn("← К шаблону", f"type:v:{type_id}")])
    return text, _markup(rows)


def confirm_delete_type(type_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_type(type_id)
    if item is None:
        return None
    used = storage.count_pelengators_of_type(type_id)
    if used:
        text = (
            f"⛔️ Шаблон <b>{escape(item['name'])}</b> нельзя удалить: "
            f"на нём ещё <b>{used}</b> пеленгатор(ов).\n"
            "Сначала смените им шаблон или удалите их."
        )
        keyboard = _markup([[_btn("← Назад", f"type:v:{type_id}")]])
        return text, keyboard
    text = f"🗑 Удалить шаблон <b>{escape(item['name'])}</b>?"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"type:do:{type_id}"),
                _btn("Отмена", f"type:v:{type_id}"),
            ]
        ]
    )
    return text, keyboard


# ──────────────────────────────────────────
# Пеленгаторы
# ──────────────────────────────────────────

def pelengators_screen() -> tuple[str, InlineKeyboardMarkup]:
    items = storage.list_pelengators()
    if items:
        lines = ["<b>Пеленгаторы</b>", ""]
        for item in items:
            errors = item["error_count"]
            err_part = f"  ⚠️ <b>{errors} ош.</b>" if errors else ""
            # Проверяем наличие изменений относительно шаблона
            full = storage.get_pelengator(item["id"])
            changed_mark = ""
            if full and full.get("type_values"):
                if _has_changes(full["values"], full["type_values"]):
                    changed_mark = "  ❗"
            loc = item.get("location") or "—"
            reserved = item.get("reserved") or ""
            lines.append(
                f"<code>#{item['id']}</code> · {escape(_short(item['type_name'], 22))} · {escape(_short(loc, 20))}{err_part}{changed_mark}"
            )
            if reserved:
                lines.append(f"    ❌ {escape(reserved)}")
            else:
                lines.append("    ✅ свободно")
        lines.append("")
        lines.append("<i>Введите номер пеленгатора, чтобы открыть карточку.</i>")
        text = "\n".join(lines)
    else:
        text = "<b>Пеленгаторы</b>\nПока пусто — добавьте первое устройство."

    keyboard = _markup([
        [_btn("＋ Новый пеленгатор", "pel:add")],
        [_btn("← Меню", "nav:home")],
    ])
    return text, keyboard


def pelengator_card(
    pelengator_id: int,
    viewer_id: int | None = None,
    is_admin: bool = False,
) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    errors = storage.list_errors_for_pelengator(pelengator_id)
    tv = item.get("type_values")
    lines = [
        f"<b>Пеленгатор #{item['id']}</b>",
        f"Шаблон: <b>{escape(item['type_name'])}</b>",
        *_status_lines(item),
        "",
        *_hw_text_lines(item["values"], tv),
        "",
        *_hw_flag_lines(item["values"], tv),
        "",
        f"⚠️ <b>Ошибки</b> · {len(errors)}",
    ]
    for error in errors[-8:]:
        kind = KIND_LABEL_SHORT.get(error["kind"], error["kind"])
        lines.append(
            f"  #{error['id']} {kind} — {escape(_short(error['description'], 48))}"
        )
    if len(errors) > 8:
        lines.append(f"  … и ещё {len(errors) - 8}")

    error_buttons = [
        [
            _btn(
                f"#{error['id']} · {KIND_LABEL_SHORT.get(error['kind'], error['kind'])} · {_short(error['description'], 26)}",
                f"err:v:{error['id']}",
            )
        ]
        for error in errors[-5:]
    ]
    mine = (
        viewer_id is not None
        and item.get("reserved_user_id") is not None
        and int(item["reserved_user_id"]) == viewer_id
    )
    taken = bool(item.get("reserved_user_id"))
    action_row = [_btn("📍 Переместить", f"pel:mv:{pelengator_id}")]
    if is_admin:
        action_row.append(_btn("🔒 Забронировать", f"pel:bk:{pelengator_id}"))
    elif not taken:
        action_row.append(_btn("🔒 Забронировать", f"pel:bk:{pelengator_id}"))
    keyboard_rows = [action_row]
    if mine:
        keyboard_rows.append([_btn("Освободить", f"pel:ub:{pelengator_id}")])
    keyboard_rows.extend(
        [
            [_btn("Свойства", f"pel:pr:{pelengator_id}")],
            [_btn("➕ Добавить ошибку", f"err:at:{pelengator_id}")],
            [
                _btn("Сменить шаблон", f"pel:ct:{pelengator_id}"),
                _btn("🗑 Удалить", f"pel:d:{pelengator_id}"),
            ],
            *error_buttons,
            [_btn("← К пеленгаторам", "nav:pels")],
        ]
    )
    keyboard = _markup(keyboard_rows)
    return "\n".join(lines), keyboard


def pel_props_screen(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    tv = item.get("type_values")
    lines = [
        f"<b>Свойства пеленгатора #{item['id']}</b>",
        f"Шаблон: <b>{escape(item['type_name'])}</b>",
        "",
        *_hw_text_lines(item["values"], tv),
        "",
        *_hw_flag_lines(item["values"], tv),
        "",
        "<i>❗ — отличается от шаблона. ↩ — сбросить к шаблону.</i>",
    ]
    rows = []
    for field, label in storage.TEXT_FIELDS.items():
        row = [_btn(label, f"pel:tx:{pelengator_id}:{field}")]
        if tv is not None and item["values"].get(field) != tv.get(field):
            row.append(_btn("↩", f"pel:rs:{pelengator_id}:{field}"))
        rows.append(row)
    for title, flags in storage.FLAG_GROUPS:
        rows.append([_btn(f"── {title} ──", f"pel:pr:{pelengator_id}")])
        for field, label in flags:
            on = bool(item["values"][field])
            mark = "✅" if on else "☐"
            row = [_btn(f"{mark} {label}", f"pel:fg:{pelengator_id}:{field}")]
            if tv is not None and bool(item["values"].get(field)) != bool(tv.get(field)):
                row.append(_btn("↩", f"pel:rs:{pelengator_id}:{field}"))
            rows.append(row)
    rows.append([_btn("← К пеленгатору", f"pel:v:{pelengator_id}")])
    return "\n".join(lines), _markup(rows)


def pelengator_pick_type_screen(
    callback_prefix: str,
    back: str,
    title: str,
) -> tuple[str, InlineKeyboardMarkup]:
    types = storage.list_types()
    if not types:
        text = "Сначала создайте хотя бы один шаблон."
        return text, _markup([[_btn("К шаблонам", "nav:types"), _btn("← Меню", "nav:home")]])

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
        f" Вместе с ним удалятся <b>{len(errors)}</b> ошибок."
        if errors
        else ""
    )
    text = f"🗑 Удалить пеленгатор <b>#{item['id']}</b>?{extra}"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"pel:do:{pelengator_id}"),
                _btn("Отмена", f"pel:v:{pelengator_id}"),
            ]
        ]
    )
    return text, keyboard


# ──────────────────────────────────────────
# Ошибки
# ──────────────────────────────────────────

def errors_hub_screen() -> tuple[str, InlineKeyboardMarkup]:
    stats = storage.counts()
    text = (
        "⚠️ <b>Ошибки</b>\n\n"
        f"🔩 Железо: <b>{stats['hardware']}</b>\n"
        f"💾 Софт:   <b>{stats['soft']}</b>"
    )
    keyboard = _markup(
        [
            [
                _btn(f"🔩 Железо · {stats['hardware']}", "err:list:h"),
                _btn(f"💾 Софт · {stats['soft']}", "err:list:s"),
            ],
            [_btn("← Меню", "nav:home")],
        ]
    )
    return text, keyboard


def errors_screen(kind: str) -> tuple[str, InlineKeyboardMarkup]:
    label = KIND_LABEL[kind]
    items = storage.list_errors(kind)
    if items:
        text = f"<b>Ошибки · {label}</b>"
    else:
        text = f"<b>Ошибки · {label}</b>\nПока чисто."

    rows = [
        [
            _btn(
                f"#{item['id']} · пел.{item['pelengator_id']} · {_short(item['description'], 24)}",
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
        f"⚠️ <b>Ошибка #{item['id']}</b>\n\n"
        f"Пеленгатор: <code>{item['pelengator_id']}</code>\n"
        f"Тип: <b>{kind}</b>\n\n"
        f"<b>Описание:</b>\n{escape(item['description'])}"
    )
    keyboard = _markup(
        [
            [_btn("✏️ Изменить описание", f"err:e:{error_id}")],
            [_btn(f"Сменить на {other_label}", f"err:sk:{error_id}:{other_kind[0]}")],
            [_btn("🗑 Удалить", f"err:d:{error_id}")],
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
    text = f"🗑 Удалить ошибку <b>#{item['id']}</b>?"
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
                _btn("🔩 Железо", "err:k:h"),
                _btn("💾 Софт", "err:k:s"),
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
        [_btn(f"#{item['id']} · {_short(item['type_name'])}", f"err:go:{item['id']}:{kind_code(kind)}")]
        for item in items
    ]
    rows.append([_btn("← Назад", f"err:list:{kind_code(kind)}")])
    return f"Куда записать ошибку ({label})?", _markup(rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return _markup([[_btn("Отмена", "conv:cancel")]])


def users_screen() -> tuple[str, InlineKeyboardMarkup]:
    users = storage.list_users()
    if users:
        lines = ["<b>Пользователи</b>", ""]
        for item in users:
            nick = f" (@{item['username']})" if item.get("username") else ""
            lines.append(f"{escape(item['name'])}{escape(nick)}")
        text = "\n".join(lines)
    else:
        text = "<b>Пользователи</b>\nПока никого нет."

    rows = []
    for item in users:
        if item.get("role") == "admin":
            continue
        rows.append(
            [
                _btn(
                    f"Сделать админом · {_short(item['name'], 22)}",
                    f"usr:adm:{item['telegram_id']}",
                )
            ]
        )
    rows.append([_btn("← Меню", "nav:home")])
    return text, _markup(rows)


def pick_user_for_booking(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup]:
    users = storage.list_users()
    if not users:
        text = "Нет зарегистрированных пользователей."
        return text, _markup([[_btn("← Назад", f"pel:v:{pelengator_id}")]])
    rows = []
    for item in users:
        nick = f" @{item['username']}" if item.get("username") else ""
        rows.append(
            [
                _btn(
                    f"{_short(item['name'], 22)}{nick}",
                    f"pel:bku:{pelengator_id}:{item['telegram_id']}",
                )
            ]
        )
    rows.append([_btn("← Назад", f"pel:v:{pelengator_id}")])
    return f"На кого забронировать пеленгатор <b>#{pelengator_id}</b>?", _markup(rows)


def register_prompt() -> tuple[str, None]:
    return (
        "Как вас зовут?\n\n"
        "<i>Это имя будут видеть при бронировании.</i>",
        None,
    )


def prompt(text: str) -> tuple[str, InlineKeyboardMarkup]:
    return f"{text}\n\n<i>Напишите ответ сообщением</i>", cancel_keyboard()
