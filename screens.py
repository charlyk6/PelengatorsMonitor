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


def error_category_label(item: dict, *, short: bool = False) -> str:
    kind = item.get("kind") or "soft"
    class_key = item.get("hw_class") or ""
    part_key = item.get("hw_part") or ""
    if kind == "hardware":
        class_label = storage.HW_CLASS_LABELS.get(class_key)
        part_label = storage.HW_PART_LABELS.get(part_key)
        kind_label = KIND_LABEL["hardware"]
        kind_short = KIND_LABEL_SHORT["hardware"]
    else:
        class_label = storage.SW_CLASS_LABELS.get(class_key)
        part_label = storage.SW_PART_LABELS.get(part_key)
        kind_label = KIND_LABEL["soft"]
        kind_short = KIND_LABEL_SHORT["soft"]
    if short:
        if part_label:
            return part_label
        if class_label:
            return class_label
        return kind_short
    parts = [kind_label]
    if class_label:
        parts.append(class_label)
    if part_label:
        parts.append(part_label)
    return " · ".join(parts)


def error_priority_emoji(item: dict) -> str:
    key = item.get("priority") or storage.DEFAULT_PRIORITY
    return storage.PRIORITY_EMOJI.get(key, storage.PRIORITY_EMOJI[storage.DEFAULT_PRIORITY])


def error_priority_text(item: dict) -> str:
    key = item.get("priority") or storage.DEFAULT_PRIORITY
    emoji = error_priority_emoji(item)
    label = storage.PRIORITY_LABELS.get(key, key)
    return f"{emoji} {label}"


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


def _break_autolink(text: str) -> str:
    """Telegram иначе делает из config/settings.py кликабельную ссылку."""
    return text.replace("config/settings.py", "config/\u200bsettings.py")


def check_status_label(status: str) -> str:
    emoji = storage.CHECK_RESULT_EMOJI.get(status, "⚪")
    label = storage.CHECK_RESULT_LABELS.get(status, status)
    return f"{emoji} {label}"


def _check_status_lines(pelengator_id: int) -> list[str]:
    insp = storage.get_latest_inspection(pelengator_id)
    if insp is None:
        return ["<b>Последняя проверка:</b> —"]
    when = storage.format_check_time(insp.get("finished_at") or insp.get("started_at"))
    return [f"<b>Последняя проверка:</b> {when} · {check_status_label(insp['status'])}"]


def pel_id_link(bot_username: str | None, pelengator_id: int) -> str:
    label = f"#{pelengator_id}"
    if not bot_username:
        return f"<code>{label}</code>"
    return (
        f'<a href="https://t.me/{bot_username}?start=p{pelengator_id}">'
        f"{label}</a>"
    )


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
        [
            _btn("⚠️ Ошибки", "nav:errs"),
            _btn("Профиль", "nav:profile"),
        ],
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
        [_btn("ОС", f"type:f:{type_id}:os")],
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

def pelengators_screen(bot_username: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
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
                f"{pel_id_link(bot_username, item['id'])} · {escape(_short(item['type_name'], 22))} · {escape(_short(loc, 20))}{err_part}{changed_mark}"
            )
            if reserved:
                lines.append(f"    ❌ {escape(reserved)}")
            else:
                lines.append("    ✅ свободно")
        lines.append("")
        lines.append("<i>Нажмите номер или введите его, чтобы открыть карточку.</i>")
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
        *_check_status_lines(pelengator_id),
        "",
        *_hw_text_lines(item["values"], tv),
        "",
        *_hw_flag_lines(item["values"], tv),
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
    keyboard_rows = [[_btn("🔎 Проверить", f"chk:go:{pelengator_id}")], action_row]
    if mine:
        keyboard_rows.append([_btn("Освободить", f"pel:ub:{pelengator_id}")])
    keyboard_rows.extend(
        [
            [_btn("Свойства", f"pel:pr:{pelengator_id}")],
            [
                _btn(f"⚠️ Ошибки · {len(errors)}", f"pel:er:{pelengator_id}"),
                _btn("➕ Добавить", f"err:at:{pelengator_id}"),
            ],
            [
                _btn("Сменить шаблон", f"pel:ct:{pelengator_id}"),
                _btn("🗑 Удалить", f"pel:d:{pelengator_id}"),
            ],
            [_btn("← К пеленгаторам", "nav:pels")],
        ]
    )
    keyboard = _markup(keyboard_rows)
    return "\n".join(lines), keyboard


def pel_errors_screen(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    errors = storage.list_errors_for_pelengator(pelengator_id)
    if errors:
        text = (
            f"⚠️ <b>Ошибки пеленгатора #{item['id']}</b>\n"
            f"Всего: <b>{len(errors)}</b>"
        )
    else:
        text = (
            f"⚠️ <b>Ошибки пеленгатора #{item['id']}</b>\n"
            "Пока чисто."
        )
    rows = [
        [
            _btn(
                f"{error_priority_emoji(error)} {error_category_label(error, short=True)} · {_short(error['description'], 26)}",
                f"err:v:{error['id']}",
            )
        ]
        for error in errors
    ]
    rows.append([_btn("➕ Добавить ошибку", f"err:at:{pelengator_id}")])
    rows.append([_btn("← К пеленгатору", f"pel:v:{pelengator_id}")])
    return text, _markup(rows)


def check_resume_screen(inspection: dict) -> tuple[str, InlineKeyboardMarkup]:
    pelengator_id = inspection["pelengator_id"]
    answered = len(inspection.get("answers") or {})
    total = len(storage.CHECK_QUESTIONS)
    text = (
        f"🔎 <b>Проверка пеленгатора #{pelengator_id}</b>\n"
        f"Статус: {check_status_label(inspection['status'])}\n"
        f"Отвечено: <b>{answered}/{total}</b>\n"
        f"Начало: {storage.format_check_time(inspection.get('started_at'))}"
    )
    keyboard = _markup(
        [
            [_btn("▶ Продолжить", f"chk:cont:{inspection['id']}")],
            [_btn("↻ Начать заново", f"chk:new:{pelengator_id}")],
            [_btn("← К пеленгатору", f"pel:v:{pelengator_id}")],
        ]
    )
    return text, keyboard


def check_question_screen(inspection: dict, question_index: int) -> tuple[str, InlineKeyboardMarkup] | None:
    if question_index < 0 or question_index >= len(storage.CHECK_QUESTIONS):
        return None
    key, title, hint = storage.CHECK_QUESTIONS[question_index]
    pelengator_id = inspection["pelengator_id"]
    total = len(storage.CHECK_QUESTIONS)
    lines = [
        f"🔎 <b>Проверка #{pelengator_id}</b> · шаг {question_index + 1}/{total}",
        "",
        f"<b>{escape(_break_autolink(title))}</b>",
    ]
    if hint:
        lines.append("")
        for hint_line in hint.split("\n"):
            lines.append(f"<code>{escape(hint_line)}</code>")
    current = (inspection.get("answers") or {}).get(key)
    if current:
        lines.append("")
        lines.append(f"Сейчас: {check_status_label(current)}")
    insp_id = inspection["id"]
    keyboard = _markup(
        [
            [_btn("🟢 Окей", f"chk:a:{insp_id}:{question_index}:o")],
            [_btn("🟡 Незначительные повреждения", f"chk:a:{insp_id}:{question_index}:m")],
            [_btn("🔴 Критические повреждения", f"chk:a:{insp_id}:{question_index}:c")],
            [
                _btn("Отменить проверку", f"chk:cx:{insp_id}"),
                _btn("Закончить", f"chk:end:{insp_id}"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


def check_result_screen(inspection: dict) -> tuple[str, InlineKeyboardMarkup]:
    pelengator_id = inspection["pelengator_id"]
    answered = len(inspection.get("answers") or {})
    total = len(storage.CHECK_QUESTIONS)
    lines = [
        f"🔎 <b>Проверка пеленгатора #{pelengator_id}</b>",
        f"Статус: {check_status_label(inspection['status'])}",
        f"Отвечено: <b>{answered}/{total}</b>",
        f"Время: {storage.format_check_time(inspection.get('finished_at') or inspection.get('started_at'))}",
        "",
    ]
    answers = inspection.get("answers") or {}
    for key, title, _hint in storage.CHECK_QUESTIONS:
        result = answers.get(key)
        if result:
            mark = storage.CHECK_RESULT_EMOJI.get(result, "⚪")
            lines.append(f"{mark} {escape(_break_autolink(title))}")
        else:
            lines.append(f"⚪ {escape(_break_autolink(title))}")
    keyboard = _markup(
        [
            [_btn("↻ Начать заново", f"chk:new:{pelengator_id}")],
            [_btn("← К пеленгатору", f"pel:v:{pelengator_id}")],
        ]
    )
    return "\n".join(lines), keyboard


def pel_props_screen(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        return None
    tv = item.get("type_values") or {}
    values = item["values"]
    text = (
        f"✏️ <b>Пеленгатор #{item['id']}</b> — {escape(item['type_name'])}\n"
        "<i>Нажмите поле для изменения. Галочки переключаются кнопкой.\n"
        "❗ — отличается от шаблона.</i>"
    )

    text_pairs = [
        ("mic_distance", "Микрофоны", "axis_distance", "Оси"),
        ("computer", "Вычислитель", "aggregator", "Агрегатор"),
        ("mic_count", "Кол-во микр.", "mic_carrier", "Носитель"),
    ]

    def _changed_text(field: str) -> bool:
        return values.get(field) != tv.get(field)

    def _changed_flag(field: str) -> bool:
        return bool(values.get(field)) != bool(tv.get(field))

    def _text_btn(field: str, label: str):
        mark = " ❗" if _changed_text(field) else ""
        return _btn(f"{label}{mark}", f"pel:tx:{pelengator_id}:{field}")

    rows = [
        [_text_btn("os", "ОС")],
        *[
            [_text_btn(left, left_label), _text_btn(right, right_label)]
            for left, left_label, right, right_label in text_pairs
        ],
    ]
    for title, flags in storage.FLAG_GROUPS:
        rows.append([_btn(f"── {title} ──", f"pel:pr:{pelengator_id}")])
        flag_row = []
        for field, label in flags:
            mark = "✅" if values.get(field) else "☐"
            suffix = " ❗" if _changed_flag(field) else ""
            flag_row.append(
                _btn(f"{mark} {label}{suffix}", f"pel:fg:{pelengator_id}:{field}")
            )
        rows.append(flag_row)

    rows.append([_btn("← К пеленгатору", f"pel:v:{pelengator_id}")])
    return text, _markup(rows)


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
            [_btn("Все ошибки", "err:all")],
            [_btn("← Меню", "nav:home")],
        ]
    )
    return text, keyboard


def errors_all_screen() -> tuple[str, InlineKeyboardMarkup]:
    items = storage.list_errors()
    if items:
        text = f"<b>Все ошибки</b>\nВсего: <b>{len(items)}</b>"
    else:
        text = "<b>Все ошибки</b>\nПока чисто."
    rows = [
        [
            _btn(
                f"{error_priority_emoji(item)} #{item['pelengator_id']} · {error_category_label(item, short=True)} · {_short(item['description'], 20)}",
                f"err:v:{item['id']}",
            )
        ]
        for item in items
    ]
    rows.append(
        [
            _btn("＋ Железо", "err:add:h"),
            _btn("＋ Софт", "err:add:s"),
        ]
    )
    rows.append([_btn("← К ошибкам", "nav:errs")])
    return text, _markup(rows)


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
                f"{error_priority_emoji(item)} пел.{item['pelengator_id']} · {error_category_label(item, short=True)} · {_short(item['description'], 20)}",
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
    category = error_category_label(item)
    current = item.get("priority") or storage.DEFAULT_PRIORITY
    text = (
        f"⚠️ <b>Ошибка</b>\n\n"
        f"Пеленгатор: <code>{item['pelengator_id']}</code>\n"
        f"Тип: <b>{category}</b>\n"
        f"Приоритет: <b>{error_priority_text(item)}</b>\n\n"
        f"<b>Описание:</b>\n<b>{escape(item['description'])}</b>"
    )
    prio_row = []
    for key in storage.ERROR_PRIORITIES:
        emoji = storage.PRIORITY_EMOJI[key]
        mark = " ·" if key == current else ""
        prio_row.append(_btn(f"{emoji}{mark}", f"err:sp:{error_id}:{key}"))
    keyboard = _markup(
        [
            prio_row,
            [_btn("✏️ Изменить описание", f"err:e:{error_id}")],
            [_btn("🗑 Удалить", f"err:d:{error_id}")],
            [
                _btn("К пеленгатору", f"pel:v:{item['pelengator_id']}"),
                _btn("← Все ошибки", "err:all"),
            ],
        ]
    )
    return text, keyboard


def confirm_delete_error(error_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    item = storage.get_error(error_id)
    if item is None:
        return None
    text = "🗑 Удалить эту ошибку?"
    keyboard = _markup(
        [
            [
                _btn("Да, удалить", f"err:do:{error_id}"),
                _btn("Отмена", f"err:v:{error_id}"),
            ]
        ]
    )
    return text, keyboard


def error_priority_screen(
    pelengator_id: int,
    category: str,
    back: str,
) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"Пеленгатор <b>#{pelengator_id}</b>\n"
        f"{escape(category)}\n\n"
        "Какой приоритет?"
    )
    keyboard = _markup(
        [
            [
                _btn("🟢 низкий", "err:np:low"),
                _btn("🟡 средний", "err:np:medium"),
                _btn("🔴 критический", "err:np:critical"),
            ],
            [_btn("← Назад", back)],
        ]
    )
    return text, keyboard


def error_class_screen(
    pelengator_id: int, kind: str, back: str
) -> tuple[str, InlineKeyboardMarkup]:
    if kind == "hardware":
        title = "🔩 Ошибка железа"
        classes = storage.HW_CLASSES
        parts_map = storage.HW_PARTS
        part_prefix = "err:hw:"
        code = "h"
    else:
        title = "💾 Ошибка софта"
        classes = storage.SW_CLASSES
        parts_map = storage.SW_PARTS
        part_prefix = "err:sw:"
        code = "s"
    text = (
        f"{title} · пеленгатор <b>#{pelengator_id}</b>\n"
        "Что сломалось?"
    )
    rows = []
    row = []
    for key, label in classes:
        if key in parts_map:
            callback = f"{part_prefix}{key}"
        else:
            callback = f"err:ds:{code}:{key}"
        row.append(_btn(label, callback))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("← Назад", back)])
    return text, _markup(rows)


def error_part_screen(
    pelengator_id: int,
    kind: str,
    class_key: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    if kind == "hardware":
        parts = storage.HW_PARTS.get(class_key)
        class_label = storage.HW_CLASS_LABELS.get(class_key, class_key)
        code = "h"
        back = "err:k:h"
        icon = "🔩"
    else:
        parts = storage.SW_PARTS.get(class_key)
        class_label = storage.SW_CLASS_LABELS.get(class_key, class_key)
        code = "s"
        back = "err:k:s"
        icon = "💾"
    if not parts:
        return None
    text = (
        f"{icon} {escape(class_label)} · пеленгатор <b>#{pelengator_id}</b>\n"
        "Уточните:"
    )
    rows = []
    row = []
    for key, label in parts:
        row.append(_btn(label, f"err:ds:{code}:{class_key}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("← Назад", back)])
    return text, _markup(rows)


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
    lines = [f"<b>Куда записать ошибку ({label})?</b>", ""]
    for item in items:
        loc = item.get("location") or "—"
        lines.append(
            f"<code>#{item['id']}</code> · {escape(_short(item['type_name'], 22))} · {escape(_short(loc, 20))}"
        )
    lines.append("")
    lines.append("<i>Введите номер пеленгатора сообщением.</i>")
    keyboard = _markup([[_btn("← Назад", f"err:list:{kind_code(kind)}")]])
    return "\n".join(lines), keyboard


def cancel_keyboard(
    reset_callback: str | None = None,
    back_callback: str = "conv:cancel",
) -> InlineKeyboardMarkup:
    row = []
    if reset_callback:
        row.append(_btn("Сбросить", reset_callback))
    row.append(_btn("Отмена", back_callback or "conv:cancel"))
    return _markup([row])


def users_screen(viewer_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    users = storage.list_users()
    if users:
        lines = ["<b>Пользователи</b>", ""]
        for item in users:
            nick = f" (@{item['username']})" if item.get("username") else ""
            status = item.get("status") or "active"
            extra = ""
            if status == "pending":
                extra = " — ожидает"
            elif status == "blocked":
                extra = " — заблокирован"
            lines.append(f"{escape(item['name'])}{escape(nick)}{extra}")
        text = "\n".join(lines)
    else:
        text = "<b>Пользователи</b>\nПока никого нет."

    rows = []
    for item in users:
        uid = item["telegram_id"]
        name = _short(item["name"], 18)
        status = item.get("status") or "active"
        is_self = viewer_id is not None and uid == viewer_id
        row = []
        if status == "pending":
            row.append(_btn(f"Подтвердить · {name}", f"usr:ok:{uid}"))
            if not is_self:
                row.append(_btn("Заблок.", f"usr:bl:{uid}"))
        elif status == "blocked":
            row.append(_btn(f"Разблок. · {name}", f"usr:un:{uid}"))
        else:
            if item.get("role") != "admin":
                row.append(_btn(f"В админы · {name}", f"usr:adm:{uid}"))
            if not is_self:
                row.append(_btn("Заблок.", f"usr:bl:{uid}"))
        if row:
            rows.append(row)
    rows.append([_btn("← Меню", "nav:home")])
    return text, _markup(rows)


def pick_user_for_booking(pelengator_id: int) -> tuple[str, InlineKeyboardMarkup]:
    users = storage.list_users()
    if not users:
        text = "Нет зарегистрированных пользователей."
        return text, _markup([[_btn("← Назад", f"pel:v:{pelengator_id}")]])
    rows = []
    for item in users:
        if item.get("status") and item["status"] != "active":
            continue
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


ROLE_LABEL = {
    "admin": "Администратор",
    "worker": "Работник",
}


def profile_screen(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    role = ROLE_LABEL.get(user.get("role") or "worker", "Работник")
    text = (
        "<b>Профиль</b>\n\n"
        f"<b>Имя:</b> {escape(user.get('name') or '—')}\n"
        f"<b>Роль:</b> {escape(role)}"
    )
    keyboard = _markup(
        [
            [_btn("Сменить имя", "me:name")],
            [_btn("← Меню", "nav:home")],
        ]
    )
    return text, keyboard


def register_prompt() -> tuple[str, None]:
    return (
        "Как вас зовут?\n\n"
        "<i>Это имя будут видеть при бронировании.\n"
        "После регистрации дождитесь подтверждения от администратора.</i>",
        None,
    )


def registration_review_markup(telegram_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                _btn("Подтвердить", f"usr:ok:{telegram_id}"),
                _btn("Заблокировать", f"usr:bl:{telegram_id}"),
            ]
        ]
    )


def pending_screen() -> tuple[str, None]:
    return (
        "Заявка отправлена.\n"
        "Дождитесь подтверждения от администратора.",
        None,
    )


def blocked_screen() -> tuple[str, None]:
    return (
        "Доступ заблокирован.\n"
        "Если это ошибка — напишите администратору.",
        None,
    )


def prompt(
    text: str,
    reset_callback: str | None = None,
    back_callback: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    return (
        f"{text}\n\n<i>Напишите ответ сообщением</i>",
        cancel_keyboard(reset_callback, back_callback or "conv:cancel"),
    )
