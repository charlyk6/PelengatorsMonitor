import sqlite3
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
    item = {"id": row["id"], "name": row["name"]}
    keys = set(row.keys())
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


def add_type(name: str) -> int:
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


def list_pelengators() -> list[dict]:
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
                (
                    SELECT COUNT(*) FROM errors
                    WHERE errors.pelengator_id = pelengators.id
                      AND COALESCE(errors.is_deleted, 0) = 0
                ) AS error_count
            FROM pelengators
            JOIN pelengator_types ON pelengator_types.id = pelengators.type_id
            ORDER BY pelengators.id
            """
        ).fetchall()
        connection.close()
    return [
        {
            "id": row["id"],
            "type_id": row["type_id"],
            "type_name": row["type_name"],
            "location": "" if row["location"] is None else str(row["location"]),
            "reserved": "" if row["reserved"] is None else str(row["reserved"]),
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
                (SELECT COUNT(*) FROM pelengators) AS pelengators,
                (SELECT COUNT(*) FROM errors WHERE COALESCE(is_deleted, 0) = 0) AS errors,
                (SELECT COUNT(*) FROM errors WHERE kind = 'hardware' AND COALESCE(is_deleted, 0) = 0) AS hardware,
                (SELECT COUNT(*) FROM errors WHERE kind = 'soft' AND COALESCE(is_deleted, 0) = 0) AS soft
            """
        ).fetchone()
        connection.close()
    return {
        "types": row["types"],
        "pelengators": row["pelengators"],
        "errors": row["errors"],
        "hardware": row["hardware"],
        "soft": row["soft"],
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


def booking_label(user: dict, telegram_username: str | None = None) -> str:
    name = user.get("name") or "без имени"
    nick = (telegram_username or user.get("username") or "").lstrip("@")
    if nick:
        return f"{name} (@{nick})"
    return name


init_db()
