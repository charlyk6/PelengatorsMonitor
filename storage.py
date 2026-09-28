import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Lock

DB_PATH = Path(__file__).resolve().parent / "pelengators.db"

_lock = Lock()

TEXT_FIELDS = {
    "mic_distance": "Расстояние между микрофонами",
    "axis_distance": "Расстояние между осями",
    "computer": "Вычислитель",
    "aggregator": "Агрегатор",
    "mic_count": "Количество микрофонов",
    "mic_carrier": "Носитель микрофонов",
    "os": "Операционная система",
}

FLAG_GROUPS = [
    (
        "Связь",
        [
            ("comm_lora", "LORA"),
            ("comm_ethernet", "Ethernet"),
            ("comm_lte", "LTE"),
        ],
    ),
    (
        "Внешние модули",
        [
            ("module_camera", "Камера"),
            ("module_accelerometer", "Акселерометр"),
        ],
    ),
    (
        "Питание",
        [
            ("power_5v", "5V"),
            ("power_220v", "220V"),
            ("power_fiber", "Оптоволокно"),
        ],
    ),
]

FLAG_FIELDS = tuple(
    key for _title, flags in FLAG_GROUPS for key, _label in flags
)

HW_CLASSES = [
    ("computer", "Вычислитель"),
    ("aggregator", "Агрегатор"),
    ("harness", "Шлейфы"),
    ("mics", "Микрофоны"),
    ("enclosure", "Гермобокс"),
    ("comm", "Связь"),
    ("modules", "Внешние модули"),
    ("power", "Питание"),
    ("construction", "Конструкция"),
    ("other", "Другое"),
]

HW_CLASS_LABELS = {key: label for key, label in HW_CLASSES}

HW_PARTS = {
    "comm": list(FLAG_GROUPS[0][1]),
    "modules": list(FLAG_GROUPS[1][1]),
    "power": [
        *FLAG_GROUPS[2][1],
        ("power_transformer", "Трансформатор"),
    ],
    "construction": [
        ("construction_legs", "Ножки"),
        ("construction_mount", "Поворотное крепление"),
        ("construction_pipes", "Трубы"),
    ],
}

HW_PART_LABELS = {
    key: label
    for parts in HW_PARTS.values()
    for key, label in parts
}

SW_CLASSES = [
    ("os", "ОС"),
    ("firmware", "Прошивка"),
    ("loconst", "loconst"),
    ("settings", "Настройки"),
    ("allaproc", "allaproc"),
    ("conn", "Соединения"),
    ("gla", "Определение ГЛА"),
    ("agent", "Агент"),
    ("other", "Другое"),
]

SW_CLASS_LABELS = {key: label for key, label in SW_CLASSES}

SW_PARTS = {
    "conn": [
        ("conn_vpn", "VPN"),
        ("conn_ethernet", "Ethernet"),
    ],
}

SW_PART_LABELS = {
    key: label
    for parts in SW_PARTS.values()
    for key, label in parts
}

_HW_CLASS_RANK = {key: i for i, (key, _) in enumerate(HW_CLASSES)}
_HW_PART_RANK = {
    key: i
    for parts in HW_PARTS.values()
    for i, (key, _) in enumerate(parts)
}
_SW_CLASS_RANK = {key: i for i, (key, _) in enumerate(SW_CLASSES)}
_SW_PART_RANK = {
    key: i
    for parts in SW_PARTS.values()
    for i, (key, _) in enumerate(parts)
}
_KIND_RANK = {"hardware": 0, "soft": 1}

ERROR_PRIORITIES = ("low", "medium", "critical")
DEFAULT_PRIORITY = "medium"
PRIORITY_EMOJI = {
    "low": "🟢",
    "medium": "🟡",
    "critical": "🔴",
}
PRIORITY_LABELS = {
    "low": "низкий",
    "medium": "средний",
    "critical": "критический",
}

# Поля устройства, не связанные с шаблоном
DEVICE_FIELDS = {
    "location": "Местоположение",
    "reserved": "Бронь",
}
DEFAULT_LOCATION = "лаба"
MAX_PELENGATOR_ID = 999_999_999

CHECK_QUESTIONS = [
    (
        "host",
        "Имя хоста совпадает с номером устройства?",
        "hostname утилиты nmtui",
    ),
    (
        "net",
        "Совпадают ли интерфейсы сети?",
        "FPGA addresses: 192.168.0.212/24\nUSBEth addresses: 192.168.2.xx/24 (xx — номер устройства)",
    ),
    ("vpn", "Есть подключение по vpn?", ""),
    (
        "alla",
        "Правильная ли версия (ветка и коммит) у allaproc?",
        "",
    ),
    (
        "loco",
        "Правильно настроены параметры postid, device_patch и disabled_mics в loconst?",
        "",
    ),
    ("sjson", "Правильные настройки в settings.json?", ""),
    ("spy", "Правильные настройки в config/settings.py?", ""),
    (
        "agent",
        "Включен ли агент на устройстве?",
        "sudo systemctl status device-agent.service",
    ),
    (
        "mics",
        "Правильно ли работают микрофоны?",
        "При малом количестве плохих отключите их в loconst и запишите ошибку.",
    ),
    (
        "gla",
        "Правильно определяются ГЛА с помощью шумелки?",
        "",
    ),
    ("data", "Данные приходят на сервер?", ""),
    ("tele", "Телеметрия приходит на сервер?", ""),
    ("cross", "Крест корректно отображается в агенте?", ""),
]
CHECK_QUESTION_KEYS = tuple(key for key, _title, _hint in CHECK_QUESTIONS)
CHECK_RESULTS = ("ok", "minor", "critical")
CHECK_RESULT_RANK = {"ok": 0, "minor": 1, "critical": 2}
CHECK_RESULT_LABELS = {
    "ok": "ок",
    "minor": "незначительные повреждения",
    "critical": "критические повреждения",
    "incomplete": "проверка не завершена",
    "in_progress": "идёт проверка",
}
CHECK_RESULT_EMOJI = {
    "ok": "🟢",
    "minor": "🟡",
    "critical": "🔴",
    "incomplete": "⚪",
    "in_progress": "🔵",
}
CHECK_ANSWER_FROM_CODE = {"o": "ok", "m": "minor", "c": "critical"}
CHECK_ANSWER_TO_CODE = {value: key for key, value in CHECK_ANSWER_FROM_CODE.items()}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    name: str,
    definition: str,
) -> None:
    if name not in _columns(connection, table):
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
        )


def init_db() -> None:
    with _lock:
        connection = _connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pelengator_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pelengators (
                id INTEGER PRIMARY KEY,
                type_id INTEGER NOT NULL,
                FOREIGN KEY (type_id) REFERENCES pelengator_types(id)
            );

            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pelengator_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('hardware', 'soft')),
                description TEXT NOT NULL,
                FOREIGN KEY (pelengator_id) REFERENCES pelengators(id)
            );

            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL CHECK (role IN ('admin', 'worker'))
            );

            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pelengator_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY (pelengator_id) REFERENCES pelengators(id)
            );

            CREATE TABLE IF NOT EXISTS inspection_answers (
                inspection_id INTEGER NOT NULL,
                question_key TEXT NOT NULL,
                result TEXT NOT NULL,
                PRIMARY KEY (inspection_id, question_key),
                FOREIGN KEY (inspection_id) REFERENCES inspections(id)
            );

            CREATE TABLE IF NOT EXISTS stock_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_lots (
                item_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                PRIMARY KEY (item_id, location),
                FOREIGN KEY (item_id) REFERENCES stock_items(id)
            );
            """
        )
        error_columns = _columns(connection, "errors")
        if "kind" not in error_columns:
            connection.execute(
                "ALTER TABLE errors ADD COLUMN kind TEXT NOT NULL DEFAULT 'soft'"
            )
        _ensure_column(connection, "errors", "hw_class", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "errors", "hw_part", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(
            connection,
            "errors",
            "priority",
            "TEXT NOT NULL DEFAULT 'medium'",
        )
        _ensure_column(
            connection,
            "errors",
            "is_deleted",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "users",
            "status",
            "TEXT NOT NULL DEFAULT 'active'",
        )

        for name in TEXT_FIELDS:
            _ensure_column(
                connection,
                "pelengator_types",
                name,
                "TEXT NOT NULL DEFAULT ''",
            )
            _ensure_column(connection, "pelengators", name, "TEXT")
        for name in FLAG_FIELDS:
            _ensure_column(
                connection,
                "pelengator_types",
                name,
                "INTEGER NOT NULL DEFAULT 0",
            )
            _ensure_column(connection, "pelengators", name, "INTEGER")
        for name in DEVICE_FIELDS:
            default = f"'{DEFAULT_LOCATION}'" if name == "location" else "''"
            _ensure_column(
                connection,
                "pelengators",
                name,
                f"TEXT NOT NULL DEFAULT {default}",
            )
        _ensure_column(
            connection,
            "pelengators",
            "reserved_user_id",
            "INTEGER",
        )
        _ensure_column(
            connection,
            "pelengator_types",
            "is_archive",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "pelengators",
            "is_archived",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "stock_items",
            "photo_file_id",
            "TEXT NOT NULL DEFAULT ''",
        )
        connection.execute(
            """
            UPDATE pelengators
            SET location = ?
            WHERE location IS NULL OR location = ''
            """,
            (DEFAULT_LOCATION,),
        )

        type_columns = _columns(connection, "pelengator_types")
        if "board" in type_columns and "computer" in type_columns:
            connection.execute(
                """
                UPDATE pelengator_types
                SET computer = board
                WHERE (computer IS NULL OR computer = '')
                  AND board IS NOT NULL
                  AND board != ''
                """
            )
        connection.commit()
        connection.close()


def _type_from_row(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    item = {
        "id": row["id"],
        "name": row["name"],
        "is_archive": int(row["is_archive"] or 0) if "is_archive" in keys else 0,
    }
    for field in TEXT_FIELDS:
        item[field] = "" if field not in keys or row[field] is None else str(row[field])
    for field in FLAG_FIELDS:
        item[field] = 0 if field not in keys or row[field] is None else int(row[field])
    return item


def list_types() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            "SELECT * FROM pelengator_types ORDER BY id"
        ).fetchall()
        connection.close()
    return [_type_from_row(row) for row in rows]


def get_type(type_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _type_from_row(row)


def add_type(name: str, is_archive: bool = False) -> int:
    with _lock:
        connection = _connect()
        columns = _columns(connection, "pelengator_types")
        fields = ["name"]
        values: list[object] = [name]
        if "board" in columns:
            fields.append("board")
            values.append("")
        for field in TEXT_FIELDS:
            if field in columns:
                fields.append(field)
                values.append("")
        if "is_archive" in columns:
            fields.append("is_archive")
            values.append(1 if is_archive else 0)
        placeholders = ", ".join("?" for _ in fields)
        field_sql = ", ".join(fields)
        cursor = connection.execute(
            f"INSERT INTO pelengator_types ({field_sql}) VALUES ({placeholders})",
            values,
        )
        connection.commit()
        type_id = cursor.lastrowid
        connection.close()
    return type_id


def set_type_archive(type_id: int, is_archive: bool) -> bool:
    with _lock:
        connection = _connect()
        columns = _columns(connection, "pelengator_types")
        if "is_archive" not in columns:
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE pelengator_types SET is_archive = ? WHERE id = ?",
            (1 if is_archive else 0, type_id),
        )
        connection.commit()
        ok = cursor.rowcount > 0
        connection.close()
    return ok


def set_pelengator_archived(pelengator_id: int, archived: bool) -> bool:
    with _lock:
        connection = _connect()
        columns = _columns(connection, "pelengators")
        if "is_archived" not in columns:
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE pelengators SET is_archived = ? WHERE id = ?",
            (1 if archived else 0, pelengator_id),
        )
        connection.commit()
        ok = cursor.rowcount > 0
        connection.close()
    return ok


def list_pelengators(*, archived: bool = False) -> list[dict]:
    archive_flag = 1 if archived else 0
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT
                pelengators.id AS id,
                pelengators.type_id AS type_id,
                pelengator_types.name AS type_name,
                pelengators.location AS location,
                pelengators.reserved AS reserved,
                COALESCE(pelengators.is_archived, 0) AS is_archived,
                (
                    SELECT COUNT(*) FROM errors
                    WHERE errors.pelengator_id = pelengators.id
                      AND COALESCE(errors.is_deleted, 0) = 0
                ) AS error_count
            FROM pelengators
            JOIN pelengator_types ON pelengator_types.id = pelengators.type_id
            WHERE COALESCE(pelengators.is_archived, 0) = ?
            ORDER BY pelengator_types.id, pelengators.id
            """,
            (archive_flag,),
        ).fetchall()
        connection.close()
    return [
        {
            "id": row["id"],
            "type_id": row["type_id"],
            "type_name": row["type_name"],
            "location": "" if row["location"] is None else str(row["location"]),
            "reserved": "" if row["reserved"] is None else str(row["reserved"]),
            "is_archived": int(row["is_archived"] or 0),
            "error_count": row["error_count"],
        }
        for row in rows
    ]


def parse_pelengator_id(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    if value < 1 or value > MAX_PELENGATOR_ID:
        return None
    return value


def add_pelengator(pelengator_id: int, type_id: int) -> str | None:
    """Returns an error code or None on success."""
    if pelengator_id < 1 or pelengator_id > MAX_PELENGATOR_ID:
        return "invalid_id"
    with _lock:
        connection = _connect()
        tpl = connection.execute(
            "SELECT * FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone()
        if tpl is None:
            connection.close()
            return "type_not_found"

        existing = connection.execute(
            "SELECT id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if existing is not None:
            connection.close()
            return "duplicate_id"

        fields = ["id", "type_id"]
        values: list = [pelengator_id, type_id]
        tpl_keys = set(tpl.keys())
        pel_columns = _columns(connection, "pelengators")
        for field in TEXT_FIELDS:
            if field in tpl_keys:
                fields.append(field)
                values.append(tpl[field] if tpl[field] is not None else "")
        for field in FLAG_FIELDS:
            if field in tpl_keys:
                fields.append(field)
                values.append(int(tpl[field]) if tpl[field] is not None else 0)
        if "location" in pel_columns:
            fields.append("location")
            values.append(DEFAULT_LOCATION)
        if "is_archived" in pel_columns:
            archived = 0
            if "is_archive" in tpl_keys and int(tpl["is_archive"] or 0):
                archived = 1
            fields.append("is_archived")
            values.append(archived)

        placeholders = ", ".join("?" for _ in fields)
        connection.execute(
            f"INSERT INTO pelengators ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        connection.commit()
        connection.close()
    return None


def get_pelengator(pelengator_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            """
            SELECT
                pelengators.*,
                pelengator_types.name AS type_name
            FROM pelengators
            JOIN pelengator_types ON pelengator_types.id = pelengators.type_id
            WHERE pelengators.id = ?
            """,
            (pelengator_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        tpl = connection.execute(
            "SELECT * FROM pelengator_types WHERE id = ?",
            (row["type_id"],),
        ).fetchone()
        connection.close()
    keys = set(row.keys())
    tpl_keys = set(tpl.keys()) if tpl else set()
    item: dict = {
        "id": row["id"],
        "type_id": row["type_id"],
        "type_name": row["type_name"],
        "location": "" if "location" not in keys or row["location"] is None else str(row["location"]),
        "reserved": "" if "reserved" not in keys or row["reserved"] is None else str(row["reserved"]),
        "reserved_user_id": (
            None
            if "reserved_user_id" not in keys or row["reserved_user_id"] is None
            else int(row["reserved_user_id"])
        ),
        "is_archived": (
            int(row["is_archived"] or 0) if "is_archived" in keys else 0
        ),
        "values": {},
        "type_values": {},
    }
    for field in TEXT_FIELDS:
        item["values"][field] = "" if field not in keys or row[field] is None else str(row[field])
        item["type_values"][field] = "" if field not in tpl_keys or tpl[field] is None else str(tpl[field])
    for field in FLAG_FIELDS:
        item["values"][field] = 0 if field not in keys or row[field] is None else int(row[field])
        item["type_values"][field] = 0 if field not in tpl_keys or tpl[field] is None else int(tpl[field])
    return item


def _error_sort_key(item: dict) -> tuple:
    kind = item.get("kind") or ""
    kind_rank = _KIND_RANK.get(kind, 9)
    class_key = item.get("hw_class") or ""
    part_key = item.get("hw_part") or ""
    if kind == "hardware":
        class_rank = _HW_CLASS_RANK.get(class_key, len(_HW_CLASS_RANK))
        part_rank = _HW_PART_RANK.get(part_key, len(_HW_PART_RANK))
    else:
        class_rank = _SW_CLASS_RANK.get(class_key, len(_SW_CLASS_RANK))
        part_rank = _SW_PART_RANK.get(part_key, len(_SW_PART_RANK))
    return (
        kind_rank,
        class_rank,
        part_rank,
        int(item["pelengator_id"]),
        int(item["id"]),
    )


def _error_from_row(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    priority = "medium"
    if "priority" in keys and row["priority"] in ERROR_PRIORITIES:
        priority = str(row["priority"])
    is_deleted = 0
    if "is_deleted" in keys and row["is_deleted"] is not None:
        is_deleted = int(row["is_deleted"])
    return {
        "id": row["id"],
        "pelengator_id": row["pelengator_id"],
        "kind": row["kind"],
        "description": row["description"],
        "hw_class": "" if "hw_class" not in keys or row["hw_class"] is None else str(row["hw_class"]),
        "hw_part": "" if "hw_part" not in keys or row["hw_part"] is None else str(row["hw_part"]),
        "priority": priority,
        "is_deleted": is_deleted,
    }


def list_errors(kind: str | None = None) -> list[dict]:
    with _lock:
        connection = _connect()
        if kind is None:
            rows = connection.execute(
                """
                SELECT * FROM errors
                WHERE COALESCE(is_deleted, 0) = 0
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM errors
                WHERE kind = ? AND COALESCE(is_deleted, 0) = 0
                ORDER BY id
                """,
                (kind,),
            ).fetchall()
        connection.close()
    items = [_error_from_row(row) for row in rows]
    items.sort(key=_error_sort_key)
    return items


def add_error(
    pelengator_id: int,
    kind: str,
    description: str,
    hw_class: str = "",
    hw_part: str = "",
    priority: str = DEFAULT_PRIORITY,
) -> int | None:
    if kind not in ("hardware", "soft"):
        return None
    if priority not in ERROR_PRIORITIES:
        priority = DEFAULT_PRIORITY
    with _lock:
        connection = _connect()
        pelengator = connection.execute(
            "SELECT id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if pelengator is None:
            connection.close()
            return None
        columns = _columns(connection, "errors")
        fields = ["pelengator_id", "kind", "description"]
        values: list[object] = [pelengator_id, kind, description]
        if "hw_class" in columns:
            fields.append("hw_class")
            values.append(hw_class or "")
        if "hw_part" in columns:
            fields.append("hw_part")
            values.append(hw_part or "")
        if "priority" in columns:
            fields.append("priority")
            values.append(priority)
        if "is_deleted" in columns:
            fields.append("is_deleted")
            values.append(0)
        placeholders = ", ".join("?" for _ in fields)
        cursor = connection.execute(
            f"INSERT INTO errors ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        connection.commit()
        error_id = cursor.lastrowid
        connection.close()
    return error_id


def counts() -> dict:
    with _lock:
        connection = _connect()
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM pelengator_types) AS types,
                (SELECT COUNT(*) FROM pelengators WHERE COALESCE(is_archived, 0) = 0) AS pelengators,
                (SELECT COUNT(*) FROM pelengators WHERE COALESCE(is_archived, 0) = 1) AS archived,
                (SELECT COUNT(*) FROM errors WHERE COALESCE(is_deleted, 0) = 0) AS errors,
                (SELECT COUNT(*) FROM errors WHERE kind = 'hardware' AND COALESCE(is_deleted, 0) = 0) AS hardware,
                (SELECT COUNT(*) FROM errors WHERE kind = 'soft' AND COALESCE(is_deleted, 0) = 0) AS soft,
                (SELECT COUNT(*) FROM stock_items) AS stock_items,
                (SELECT COALESCE(SUM(qty), 0) FROM stock_lots) AS stock_qty
            """
        ).fetchone()
        connection.close()
    return {
        "types": row["types"],
        "pelengators": row["pelengators"],
        "archived": row["archived"],
        "errors": row["errors"],
        "hardware": row["hardware"],
        "soft": row["soft"],
        "stock_items": row["stock_items"],
        "stock_qty": row["stock_qty"],
    }


def count_pelengators_of_type(type_id: int) -> int:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM pelengators WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        connection.close()
    return row["n"]


def update_type_field(type_id: int, field: str, value: str) -> bool:
    """Update a text field on the template; cascade to devices that still match old value."""
    allowed = {"name", *TEXT_FIELDS}
    if field not in allowed:
        return False
    with _lock:
        connection = _connect()
        old_row = connection.execute(
            f"SELECT {field} FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone()
        if old_row is None:
            connection.close()
            return False
        old_value = old_row[field] if old_row[field] is not None else ""
        connection.execute(
            f"UPDATE pelengator_types SET {field} = ? WHERE id = ?",
            (value, type_id),
        )
        if field in TEXT_FIELDS:
            connection.execute(
                f"UPDATE pelengators SET {field} = ? WHERE type_id = ? AND ({field} = ? OR {field} IS NULL)",
                (value, type_id, old_value),
            )
        connection.commit()
        connection.close()
    return True


def toggle_type_flag(type_id: int, field: str) -> bool:
    """Toggle flag on the template; cascade to devices that still match old value."""
    if field not in FLAG_FIELDS:
        return False
    with _lock:
        connection = _connect()
        row = connection.execute(
            f"SELECT {field} AS value FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        old_value = int(row["value"] or 0)
        new_value = 0 if old_value else 1
        connection.execute(
            f"UPDATE pelengator_types SET {field} = ? WHERE id = ?",
            (new_value, type_id),
        )
        connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE type_id = ? AND ({field} = ? OR {field} IS NULL)",
            (new_value, type_id, old_value),
        )
        connection.commit()
        connection.close()
    return True


def set_pelengator_text(pelengator_id: int, field: str, value: str) -> bool:
    if field not in TEXT_FIELDS:
        return False
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE id = ?",
            (value, pelengator_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def set_pelengator_device_field(pelengator_id: int, field: str, value: str) -> bool:
    if field not in DEVICE_FIELDS:
        return False
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE id = ?",
            (value, pelengator_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def reserve_pelengator(pelengator_id: int, user_id: int, display_name: str) -> bool:
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            """
            UPDATE pelengators
            SET reserved = ?, reserved_user_id = ?
            WHERE id = ?
            """,
            (display_name, user_id, pelengator_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def release_pelengator(pelengator_id: int, user_id: int) -> str | None:
    """Снять бронь. None — успех, иначе код ошибки."""
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT reserved_user_id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return "not_found"
        owner = row["reserved_user_id"]
        if owner is None:
            connection.close()
            return "not_reserved"
        if int(owner) != user_id:
            connection.close()
            return "not_owner"
        connection.execute(
            """
            UPDATE pelengators
            SET reserved = '', reserved_user_id = NULL
            WHERE id = ?
            """,
            (pelengator_id,),
        )
        connection.commit()
        connection.close()
    return None


def reset_pelengator_field(pelengator_id: int, field: str) -> bool:
    """Вернуть поле устройства к текущему значению шаблона."""
    if field not in TEXT_FIELDS and field not in FLAG_FIELDS:
        return False
    with _lock:
        connection = _connect()
        device = connection.execute(
            "SELECT type_id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if device is None:
            connection.close()
            return False
        tpl = connection.execute(
            f"SELECT {field} FROM pelengator_types WHERE id = ?",
            (device["type_id"],),
        ).fetchone()
        if tpl is None:
            connection.close()
            return False
        if field in TEXT_FIELDS:
            value: object = "" if tpl[field] is None else str(tpl[field])
        else:
            value = 0 if tpl[field] is None else int(tpl[field])
        connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE id = ?",
            (value, pelengator_id),
        )
        connection.commit()
        connection.close()
    return True


def toggle_pelengator_flag(pelengator_id: int, field: str) -> bool:
    if field not in FLAG_FIELDS:
        return False
    with _lock:
        connection = _connect()
        row = connection.execute(
            f"SELECT {field} AS value FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        new_value = 0 if int(row["value"] or 0) else 1
        connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE id = ?",
            (new_value, pelengator_id),
        )
        connection.commit()
        connection.close()
    return True


def delete_type(type_id: int) -> str | None:
    with _lock:
        connection = _connect()
        used = connection.execute(
            "SELECT COUNT(*) AS n FROM pelengators WHERE type_id = ?",
            (type_id,),
        ).fetchone()["n"]
        if used:
            connection.close()
            return "in_use"
        cursor = connection.execute(
            "DELETE FROM pelengator_types WHERE id = ?",
            (type_id,),
        )
        connection.commit()
        deleted = cursor.rowcount > 0
        connection.close()
    return None if deleted else "not_found"


def update_pelengator_type(pelengator_id: int, new_type_id: int) -> str | None:
    """Switch template. For each field, if device value still matches old template, overwrite with new template value."""
    with _lock:
        connection = _connect()
        new_tpl = connection.execute(
            "SELECT * FROM pelengator_types WHERE id = ?",
            (new_type_id,),
        ).fetchone()
        if new_tpl is None:
            connection.close()
            return "type_not_found"

        device_row = connection.execute(
            "SELECT * FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if device_row is None:
            connection.close()
            return "not_found"

        old_tpl = connection.execute(
            "SELECT * FROM pelengator_types WHERE id = ?",
            (device_row["type_id"],),
        ).fetchone()

        updates: dict[str, object] = {"type_id": new_type_id}
        tpl_keys = set(new_tpl.keys())

        for field in TEXT_FIELDS:
            if field not in tpl_keys:
                continue
            dev_val = device_row[field] if device_row[field] is not None else ""
            old_val = (old_tpl[field] if old_tpl and old_tpl[field] is not None else "") if old_tpl else ""
            new_val = new_tpl[field] if new_tpl[field] is not None else ""
            if dev_val == old_val:
                updates[field] = new_val

        for field in FLAG_FIELDS:
            if field not in tpl_keys:
                continue
            dev_val = int(device_row[field] or 0) if device_row[field] is not None else 0
            old_val = int(old_tpl[field] or 0) if old_tpl and old_tpl[field] is not None else 0
            new_val = int(new_tpl[field] or 0) if new_tpl[field] is not None else 0
            if dev_val == old_val:
                updates[field] = new_val

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        connection.execute(
            f"UPDATE pelengators SET {set_clause} WHERE id = ?",
            list(updates.values()) + [pelengator_id],
        )
        connection.commit()
        connection.close()
    return None


def delete_pelengator(pelengator_id: int) -> bool:
    with _lock:
        connection = _connect()
        try:
            insp_ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM inspections WHERE pelengator_id = ?",
                    (pelengator_id,),
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            insp_ids = []
        if insp_ids:
            placeholders = ", ".join("?" for _ in insp_ids)
            connection.execute(
                f"DELETE FROM inspection_answers WHERE inspection_id IN ({placeholders})",
                insp_ids,
            )
            connection.execute(
                "DELETE FROM inspections WHERE pelengator_id = ?",
                (pelengator_id,),
            )
        connection.execute(
            "DELETE FROM errors WHERE pelengator_id = ?",
            (pelengator_id,),
        )
        cursor = connection.execute(
            "DELETE FROM pelengators WHERE id = ?",
            (pelengator_id,),
        )
        connection.commit()
        deleted = cursor.rowcount > 0
        connection.close()
    return deleted


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_check_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso


def worst_check_result(results: list[str]) -> str:
    worst = "ok"
    worst_rank = -1
    for result in results:
        rank = CHECK_RESULT_RANK.get(result, -1)
        if rank > worst_rank:
            worst = result
            worst_rank = rank
    return worst if worst_rank >= 0 else "incomplete"


def _inspection_from_row(row: sqlite3.Row, answers: dict[str, str] | None = None) -> dict:
    return {
        "id": int(row["id"]),
        "pelengator_id": int(row["pelengator_id"]),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or "") if row["finished_at"] else "",
        "status": str(row["status"] or "in_progress"),
        "answers": answers if answers is not None else {},
    }


def _load_answers(connection: sqlite3.Connection, inspection_id: int) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT question_key, result
        FROM inspection_answers
        WHERE inspection_id = ?
        """,
        (inspection_id,),
    ).fetchall()
    return {str(row["question_key"]): str(row["result"]) for row in rows}


def _first_unanswered_index(answers: dict[str, str]) -> int | None:
    for index, key in enumerate(CHECK_QUESTION_KEYS):
        if key not in answers:
            return index
    return None


def get_inspection(inspection_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        answers = _load_answers(connection, inspection_id)
        connection.close()
    item = _inspection_from_row(row, answers)
    item["next_index"] = _first_unanswered_index(answers)
    return item


def get_latest_inspection(pelengator_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            """
            SELECT * FROM inspections
            WHERE pelengator_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (pelengator_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        answers = _load_answers(connection, int(row["id"]))
        connection.close()
    item = _inspection_from_row(row, answers)
    item["next_index"] = _first_unanswered_index(answers)
    return item


def get_continuable_inspection(pelengator_id: int) -> dict | None:
    latest = get_latest_inspection(pelengator_id)
    if latest is None:
        return None
    if latest["status"] == "in_progress":
        return latest
    if latest["status"] == "incomplete" and latest.get("next_index") is not None:
        return latest
    return None


def start_inspection(pelengator_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        exists = connection.execute(
            "SELECT id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if exists is None:
            connection.close()
            return None
        active = connection.execute(
            """
            SELECT id FROM inspections
            WHERE pelengator_id = ? AND status = 'in_progress'
            """,
            (pelengator_id,),
        ).fetchall()
        for row in active:
            connection.execute(
                "DELETE FROM inspection_answers WHERE inspection_id = ?",
                (row["id"],),
            )
            connection.execute(
                "DELETE FROM inspections WHERE id = ?",
                (row["id"],),
            )
        cursor = connection.execute(
            """
            INSERT INTO inspections (pelengator_id, started_at, finished_at, status)
            VALUES (?, ?, NULL, 'in_progress')
            """,
            (pelengator_id, _now_iso()),
        )
        inspection_id = cursor.lastrowid
        connection.commit()
        connection.close()
    return get_inspection(int(inspection_id))


def resume_inspection(inspection_id: int) -> dict | None:
    item = get_inspection(inspection_id)
    if item is None:
        return None
    if item["status"] == "incomplete":
        with _lock:
            connection = _connect()
            connection.execute(
                """
                UPDATE inspections
                SET status = 'in_progress', finished_at = NULL
                WHERE id = ?
                """,
                (inspection_id,),
            )
            connection.commit()
            connection.close()
        return get_inspection(inspection_id)
    if item["status"] == "in_progress":
        return item
    return None


def save_check_answer(inspection_id: int, question_index: int, result: str) -> dict | None:
    if result not in CHECK_RESULTS:
        return None
    if question_index < 0 or question_index >= len(CHECK_QUESTION_KEYS):
        return None
    key = CHECK_QUESTION_KEYS[question_index]
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()
        if row is None or str(row["status"]) not in ("in_progress", "incomplete"):
            connection.close()
            return None
        if str(row["status"]) == "incomplete":
            connection.execute(
                """
                UPDATE inspections
                SET status = 'in_progress', finished_at = NULL
                WHERE id = ?
                """,
                (inspection_id,),
            )
        connection.execute(
            """
            INSERT INTO inspection_answers (inspection_id, question_key, result)
            VALUES (?, ?, ?)
            ON CONFLICT(inspection_id, question_key) DO UPDATE SET result = excluded.result
            """,
            (inspection_id, key, result),
        )
        connection.commit()
        connection.close()
    item = get_inspection(inspection_id)
    if item and item.get("next_index") is None:
        return finish_inspection(inspection_id)
    return item


def finish_inspection(inspection_id: int) -> dict | None:
    item = get_inspection(inspection_id)
    if item is None:
        return None
    answers = [item["answers"][key] for key in CHECK_QUESTION_KEYS if key in item["answers"]]
    if len(answers) >= len(CHECK_QUESTION_KEYS):
        status = worst_check_result(answers)
    else:
        status = "incomplete"
    finished = _now_iso()
    with _lock:
        connection = _connect()
        connection.execute(
            """
            UPDATE inspections
            SET status = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, finished, inspection_id),
        )
        connection.commit()
        connection.close()
    return get_inspection(inspection_id)


def cancel_inspection(inspection_id: int) -> int | None:
    """Удаляет незавершённую проверку. Возвращает pelengator_id."""
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT pelengator_id, status FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        pelengator_id = int(row["pelengator_id"])
        if str(row["status"]) not in ("in_progress", "incomplete"):
            connection.close()
            return pelengator_id
        connection.execute(
            "DELETE FROM inspection_answers WHERE inspection_id = ?",
            (inspection_id,),
        )
        connection.execute(
            "DELETE FROM inspections WHERE id = ?",
            (inspection_id,),
        )
        connection.commit()
        connection.close()
    return pelengator_id


def list_errors_for_pelengator(pelengator_id: int) -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT * FROM errors
            WHERE pelengator_id = ? AND COALESCE(is_deleted, 0) = 0
            ORDER BY id
            """,
            (pelengator_id,),
        ).fetchall()
        connection.close()
    items = [_error_from_row(row) for row in rows]
    items.sort(key=_error_sort_key)
    return items


def get_error(error_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM errors WHERE id = ?",
            (error_id,),
        ).fetchone()
        connection.close()
    if row is None:
        return None
    item = _error_from_row(row)
    if item.get("is_deleted"):
        return None
    return item


def update_error(
    error_id: int,
    *,
    kind: str | None = None,
    description: str | None = None,
) -> bool:
    if kind is not None and kind not in ("hardware", "soft"):
        return False
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM errors WHERE id = ?",
            (error_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        new_kind = kind if kind is not None else row["kind"]
        new_description = description if description is not None else row["description"]
        keys = set(row.keys())
        hw_class = row["hw_class"] if "hw_class" in keys and row["hw_class"] else ""
        hw_part = row["hw_part"] if "hw_part" in keys and row["hw_part"] else ""
        if "hw_class" in keys:
            connection.execute(
                """
                UPDATE errors
                SET kind = ?, description = ?, hw_class = ?, hw_part = ?
                WHERE id = ?
                """,
                (new_kind, new_description, hw_class, hw_part, error_id),
            )
        else:
            connection.execute(
                "UPDATE errors SET kind = ?, description = ? WHERE id = ?",
                (new_kind, new_description, error_id),
            )
        connection.commit()
        connection.close()
    return True


def delete_error(error_id: int) -> bool:
    with _lock:
        connection = _connect()
        columns = _columns(connection, "errors")
        if "is_deleted" in columns:
            cursor = connection.execute(
                """
                UPDATE errors
                SET is_deleted = 1
                WHERE id = ? AND COALESCE(is_deleted, 0) = 0
                """,
                (error_id,),
            )
        else:
            cursor = connection.execute(
                "DELETE FROM errors WHERE id = ?",
                (error_id,),
            )
        connection.commit()
        deleted = cursor.rowcount > 0
        connection.close()
    return deleted


def set_error_priority(error_id: int, priority: str) -> bool:
    if priority not in ERROR_PRIORITIES:
        return False
    with _lock:
        connection = _connect()
        if "priority" not in _columns(connection, "errors"):
            connection.close()
            return False
        cursor = connection.execute(
            """
            UPDATE errors
            SET priority = ?
            WHERE id = ? AND COALESCE(is_deleted, 0) = 0
            """,
            (priority, error_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def _user_from_row(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    status = "active"
    if "status" in keys and row["status"]:
        status = str(row["status"])
    return {
        "telegram_id": int(row["telegram_id"]),
        "name": str(row["name"] or ""),
        "username": str(row["username"] or ""),
        "role": str(row["role"] or "worker"),
        "status": status,
    }


def get_user(telegram_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _user_from_row(row)


def count_users() -> int:
    with _lock:
        connection = _connect()
        row = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        connection.close()
    return int(row["n"])


def register_user(telegram_id: int, name: str, username: str | None) -> tuple[dict, bool]:
    nick = (username or "").lstrip("@")
    with _lock:
        connection = _connect()
        existing = connection.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE users SET name = ?, username = ? WHERE telegram_id = ?",
                (name, nick, telegram_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            connection.close()
            return _user_from_row(row), False
        total = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        role = "admin" if total == 0 else "worker"
        status = "active" if total == 0 else "pending"
        fields = ["telegram_id", "name", "username", "role"]
        values: list[object] = [telegram_id, name, nick, role]
        columns = _columns(connection, "users")
        if "status" in columns:
            fields.append("status")
            values.append(status)
        placeholders = ", ".join("?" for _ in fields)
        connection.execute(
            f"INSERT INTO users ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        connection.commit()
        connection.close()
    return (
        {
            "telegram_id": telegram_id,
            "name": name,
            "username": nick,
            "role": role,
            "status": status,
        },
        True,
    )


def update_user_name(telegram_id: int, name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            "UPDATE users SET name = ? WHERE telegram_id = ?",
            (name, telegram_id),
        )
        if cursor.rowcount == 0:
            connection.close()
            return False
        row = connection.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        label = booking_label(_user_from_row(row))
        if "reserved_user_id" in _columns(connection, "pelengators"):
            connection.execute(
                "UPDATE pelengators SET reserved = ? WHERE reserved_user_id = ?",
                (label, telegram_id),
            )
        connection.commit()
        connection.close()
    return True


def update_user_username(telegram_id: int, username: str | None) -> None:
    nick = (username or "").lstrip("@")
    with _lock:
        connection = _connect()
        connection.execute(
            "UPDATE users SET username = ? WHERE telegram_id = ?",
            (nick, telegram_id),
        )
        connection.commit()
        connection.close()


def list_users() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT *
            FROM users
            ORDER BY name COLLATE NOCASE, telegram_id
            """
        ).fetchall()
        connection.close()
    return [_user_from_row(row) for row in rows]


def list_admins() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT *
            FROM users
            WHERE role = 'admin' AND (status = 'active' OR status IS NULL OR status = '')
            ORDER BY telegram_id
            """
        ).fetchall()
        connection.close()
    return [_user_from_row(row) for row in rows]


def set_user_role(telegram_id: int, role: str) -> bool:
    if role not in ("admin", "worker"):
        return False
    with _lock:
        connection = _connect()
        columns = _columns(connection, "users")
        if role == "admin" and "status" in columns:
            cursor = connection.execute(
                "UPDATE users SET role = ?, status = 'active' WHERE telegram_id = ?",
                (role, telegram_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE users SET role = ? WHERE telegram_id = ?",
                (role, telegram_id),
            )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def set_user_status(telegram_id: int, status: str) -> bool:
    if status not in ("pending", "active", "blocked"):
        return False
    with _lock:
        connection = _connect()
        if "status" not in _columns(connection, "users"):
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE users SET status = ? WHERE telegram_id = ?",
            (status, telegram_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


MAX_STOCK_QTY = 1_000_000
MAX_STOCK_NAME = 80


def letter_shift_score(left: str, right: str) -> int:
    """Max matching letters across all alignments; case-insensitive."""
    a = (left or "").casefold()
    b = (right or "").casefold()
    if not a or not b:
        return 0
    best = 0
    for shift in range(-len(b) + 1, len(a)):
        matched = 0
        for i, ch in enumerate(a):
            j = i - shift
            if 0 <= j < len(b) and ch == b[j]:
                matched += 1
        if matched > best:
            best = matched
    return best


def normalize_stock_text(raw: str | None) -> str:
    return " ".join((raw or "").split())


def parse_stock_qty(raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    if value < 1 or value > MAX_STOCK_QTY:
        return None
    return value


def _stock_item_from_row(row: sqlite3.Row, lots: list[dict]) -> dict:
    keys = set(row.keys())
    total = sum(int(lot["qty"]) for lot in lots)
    return {
        "id": row["id"],
        "name": row["name"],
        "total": total,
        "lots": lots,
        "photo_file_id": (
            ""
            if "photo_file_id" not in keys or row["photo_file_id"] is None
            else str(row["photo_file_id"])
        ),
    }


def _lots_for_item(connection: sqlite3.Connection, item_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT location, qty
        FROM stock_lots
        WHERE item_id = ?
        ORDER BY CASE WHEN location = ? THEN 0 ELSE 1 END, location
        """,
        (item_id, DEFAULT_LOCATION),
    ).fetchall()
    return [
        {"location": row["location"], "qty": int(row["qty"])}
        for row in rows
    ]


def list_stock_items() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            "SELECT * FROM stock_items ORDER BY name, id"
        ).fetchall()
        items = [
            _stock_item_from_row(row, _lots_for_item(connection, row["id"]))
            for row in rows
        ]
        connection.close()
    return items


def get_stock_item(item_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        item = _stock_item_from_row(row, _lots_for_item(connection, item_id))
        connection.close()
    return item


def find_stock_item_by_name(name: str) -> dict | None:
    key = normalize_stock_text(name).casefold()
    if not key:
        return None
    with _lock:
        connection = _connect()
        rows = connection.execute(
            "SELECT * FROM stock_items ORDER BY id"
        ).fetchall()
        found = None
        for row in rows:
            if normalize_stock_text(row["name"]).casefold() == key:
                found = _stock_item_from_row(row, _lots_for_item(connection, row["id"]))
                break
        connection.close()
    return found


def best_stock_match(query: str) -> dict | None:
    query = normalize_stock_text(query)
    if not query:
        return None
    best_item = None
    best_score = 0
    for item in list_stock_items():
        score = letter_shift_score(query, item["name"])
        if score > best_score:
            best_score = score
            best_item = item
    if best_item is None or best_score <= 0:
        return None
    return {**best_item, "match_score": best_score}


def add_stock_item(name: str) -> int | None:
    name = normalize_stock_text(name)
    if not name or len(name) > MAX_STOCK_NAME:
        return None
    existing = find_stock_item_by_name(name)
    if existing is not None:
        return existing["id"]
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            "INSERT INTO stock_items (name) VALUES (?)",
            (name,),
        )
        connection.commit()
        item_id = cursor.lastrowid
        connection.close()
    return item_id


def list_known_locations() -> list[str]:
    seen: list[str] = []
    seen_exact: set[str] = set()

    def add(raw: str | None) -> None:
        loc = normalize_stock_text(raw)
        if not loc or loc in seen_exact:
            return
        seen_exact.add(loc)
        seen.append(loc)

    add(DEFAULT_LOCATION)
    with _lock:
        connection = _connect()
        for row in connection.execute(
            "SELECT DISTINCT location FROM stock_lots ORDER BY location"
        ).fetchall():
            add(row["location"])
        if "location" in _columns(connection, "pelengators"):
            for row in connection.execute(
                """
                SELECT DISTINCT location FROM pelengators
                WHERE location IS NOT NULL AND location != ''
                ORDER BY location
                """
            ).fetchall():
                add(row["location"])
        connection.close()
    return seen


def lot_qty(item: dict, location: str) -> int:
    location = normalize_stock_text(location)
    for lot in item.get("lots") or []:
        if str(lot["location"]) == location:
            return int(lot["qty"])
    return 0


def _adjust_lot(
    connection: sqlite3.Connection,
    item_id: int,
    location: str,
    delta: int,
) -> str | None:
    row = connection.execute(
        "SELECT qty FROM stock_lots WHERE item_id = ? AND location = ?",
        (item_id, location),
    ).fetchone()
    current = 0 if row is None else int(row["qty"])
    new = current + delta
    if new < 0:
        return "not_enough"
    if new == 0:
        connection.execute(
            "DELETE FROM stock_lots WHERE item_id = ? AND location = ?",
            (item_id, location),
        )
    elif row is None:
        connection.execute(
            "INSERT INTO stock_lots (item_id, location, qty) VALUES (?, ?, ?)",
            (item_id, location, new),
        )
    else:
        connection.execute(
            "UPDATE stock_lots SET qty = ? WHERE item_id = ? AND location = ?",
            (new, item_id, location),
        )
    return None


def add_stock(item_id: int, location: str, qty: int) -> str | None:
    location = normalize_stock_text(location)
    if not location:
        return "bad_location"
    if qty < 1 or qty > MAX_STOCK_QTY:
        return "bad_qty"
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT id FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return "not_found"
        error = _adjust_lot(connection, item_id, location, qty)
        if error:
            connection.close()
            return error
        connection.commit()
        connection.close()
    return None


def move_stock(item_id: int, from_location: str, to_location: str, qty: int) -> str | None:
    from_location = normalize_stock_text(from_location)
    to_location = normalize_stock_text(to_location)
    if not from_location or not to_location:
        return "bad_location"
    if from_location == to_location:
        return "same_location"
    if qty < 1 or qty > MAX_STOCK_QTY:
        return "bad_qty"
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT id FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return "not_found"
        error = _adjust_lot(connection, item_id, from_location, -qty)
        if error:
            connection.close()
            return error
        error = _adjust_lot(connection, item_id, to_location, qty)
        if error:
            connection.close()
            return error
        connection.commit()
        connection.close()
    return None


def remove_stock(item_id: int, location: str, qty: int) -> str | None:
    location = normalize_stock_text(location)
    if not location:
        return "bad_location"
    if qty < 1 or qty > MAX_STOCK_QTY:
        return "bad_qty"
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT id FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return "not_found"
        error = _adjust_lot(connection, item_id, location, -qty)
        if error:
            connection.close()
            return error
        connection.commit()
        connection.close()
    return None


def set_stock_photo(item_id: int, file_id: str | None) -> bool:
    value = "" if not file_id else str(file_id)
    with _lock:
        connection = _connect()
        columns = _columns(connection, "stock_items")
        if "photo_file_id" not in columns:
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE stock_items SET photo_file_id = ? WHERE id = ?",
            (value, item_id),
        )
        connection.commit()
        ok = cursor.rowcount > 0
        connection.close()
    return ok


def delete_stock_item(item_id: int) -> bool:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT id FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        connection.execute(
            "DELETE FROM stock_lots WHERE item_id = ?",
            (item_id,),
        )
        connection.execute(
            "DELETE FROM stock_items WHERE id = ?",
            (item_id,),
        )
        connection.commit()
        connection.close()
    return True


def booking_label(user: dict, telegram_username: str | None = None) -> str:
    name = user.get("name") or "без имени"
    nick = (telegram_username or user.get("username") or "").lstrip("@")
    if nick:
        return f"{name} (@{nick})"
    return name


init_db()
