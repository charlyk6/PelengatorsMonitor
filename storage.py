import json
import sqlite3
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

DB_PATH = Path(__file__).resolve().parent / "pelengators.db"

_lock = Lock()
_pending_activity: list[dict] = []
_activity_actor_id: ContextVar[int | None] = ContextVar(
    "activity_actor_id", default=None
)
_activity_actor_name: ContextVar[str] = ContextVar(
    "activity_actor_name", default=""
)

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


def _users_table_sql(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if row is None:
        return ""
    return str(row["sql"] or "")


def _ensure_owner(connection: sqlite3.Connection) -> None:
    owner = connection.execute(
        "SELECT telegram_id FROM users WHERE role = 'owner' LIMIT 1"
    ).fetchone()
    if owner is not None:
        return
    first = connection.execute(
        """
        SELECT telegram_id FROM users
        WHERE role = 'admin'
        ORDER BY rowid
        LIMIT 1
        """
    ).fetchone()
    if first is None:
        first = connection.execute(
            "SELECT telegram_id FROM users ORDER BY rowid LIMIT 1"
        ).fetchone()
    if first is None:
        return
    connection.execute(
        """
        UPDATE users
        SET role = 'owner', status = 'active'
        WHERE telegram_id = ?
        """,
        (first["telegram_id"],),
    )


def _migrate_users_roles(connection: sqlite3.Connection) -> None:
    sql = _users_table_sql(connection)
    if not sql:
        return
    if "owner" in sql and "purchaser" in sql:
        _ensure_owner(connection)
        return
    columns = _columns(connection, "users")
    connection.execute(
        """
        CREATE TABLE users_mig (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'worker', 'purchaser')),
            status TEXT NOT NULL DEFAULT 'active',
            notify_activity INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    rows = connection.execute("SELECT * FROM users").fetchall()
    for row in rows:
        keys = set(row.keys())
        role = str(row["role"] or "worker")
        if role not in USER_ROLES:
            role = "worker"
        status = "active"
        if "status" in keys and row["status"]:
            status = str(row["status"])
        notify = 0
        if "notify_activity" in keys:
            notify = int(row["notify_activity"] or 0)
        connection.execute(
            """
            INSERT INTO users_mig (
                telegram_id, name, username, role, status, notify_activity
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["telegram_id"],
                row["name"],
                row["username"] or "",
                role,
                status,
                notify,
            ),
        )
    connection.execute("DROP TABLE users")
    connection.execute("ALTER TABLE users_mig RENAME TO users")
    _ensure_owner(connection)


ACTIVITY_PAGE_SIZE = 12
ACTIVITY_FILTER_PAGE_SIZE = 10
LOG_EXPORT_LIMIT = 2000

ACTIVITY_ACTIONS = [
    ("pel.created", "Пеленгатор создан"),
    ("pel.moved", "Пеленгатор перемещён"),
    ("pel.reserved", "Бронь"),
    ("pel.released", "Бронь снята"),
    ("pel.type_changed", "Смена шаблона"),
    ("pel.archived", "В архив"),
    ("pel.restored", "Из архива"),
    ("pel.deleted", "Пеленгатор удалён"),
    ("error.created", "Ошибка добавлена"),
    ("error.deleted", "Ошибка удалена"),
    ("stock.added", "Приход"),
    ("stock.moved", "Перемещение склада"),
    ("stock.returned", "Возврат"),
    ("stock.removed", "Списание"),
    ("stock.deleted", "Карточка удалена"),
]
ACTIVITY_ACTION_LABELS = {key: label for key, label in ACTIVITY_ACTIONS}
ACTIVITY_ACTION_KEYS = [key for key, _label in ACTIVITY_ACTIONS]
ACTIVITY_TIME_PRESETS = {
    "today": "Сегодня",
    "yesterday": "Вчера",
    "7d": "7 дней",
    "30d": "30 дней",
    "custom": "Свой период",
}

USER_ROLES = ("owner", "admin", "worker", "purchaser")
ASSIGNABLE_ROLES = ("admin", "worker", "purchaser")
ROLE_LABELS = {
    "owner": "Владелец",
    "admin": "Администратор",
    "worker": "Работник",
    "purchaser": "Закупщик",
}
PURCHASER_HIDDEN_ACTIONS = tuple(
    key
    for key in ACTIVITY_ACTION_KEYS
    if key.startswith("pel.") or key.startswith("error.")
)
PURCHASER_ALLOWED_ACTIONS = tuple(
    key for key in ACTIVITY_ACTION_KEYS if key not in PURCHASER_HIDDEN_ACTIONS
)
REQUEST_STATUSES = ("new", "in_progress", "closed")
REQUEST_STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "Принята в работу",
    "closed": "Закрыта",
}
REQUEST_STATUS_CODES = {
    "n": "new",
    "w": "in_progress",
    "c": "closed",
}
REQUEST_STATUS_TO_CODE = {value: key for key, value in REQUEST_STATUS_CODES.items()}
MAX_PURCHASE_NAME = 80
MAX_PURCHASE_FIELD = 80
MAX_PURCHASE_PHOTOS = 10
MAX_REQUEST_DESC = 500


def set_activity_actor(user_id: int | None, name: str = "") -> None:
    _activity_actor_id.set(user_id)
    _activity_actor_name.set(name or "")


def _log_activity(
    connection: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    action: str,
    payload: dict | None = None,
) -> None:
    created_at = datetime.now().isoformat(timespec="seconds")
    actor_id = _activity_actor_id.get()
    actor_name = _activity_actor_name.get() or ""
    data = payload or {}
    connection.execute(
        """
        INSERT INTO activity (
            created_at, actor_id, actor_name,
            entity_type, entity_id, action, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            actor_id,
            actor_name,
            entity_type,
            int(entity_id),
            action,
            json.dumps(data, ensure_ascii=False),
        ),
    )
    _pending_activity.append(
        {
            "created_at": created_at,
            "actor_id": None if actor_id is None else int(actor_id),
            "actor_name": actor_name,
            "entity_type": entity_type,
            "entity_id": int(entity_id),
            "action": action,
            "payload": data,
        }
    )


def drain_activity_events() -> list[dict]:
    with _lock:
        events = list(_pending_activity)
        _pending_activity.clear()
    return events


def _stock_name_locked(connection: sqlite3.Connection, item_id: int) -> str:
    row = connection.execute(
        "SELECT name FROM stock_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    return "" if row is None else str(row["name"] or "")


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
                role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'worker', 'purchaser'))
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

            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor_id INTEGER,
                actor_name TEXT NOT NULL DEFAULT '',
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS log_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                requester_id INTEGER NOT NULL,
                requester_name TEXT NOT NULL DEFAULT '',
                filters TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                photo_file_id TEXT NOT NULL DEFAULT '',
                photos TEXT NOT NULL DEFAULT '[]',
                supplier_name TEXT NOT NULL DEFAULT '',
                invoice_number TEXT NOT NULL DEFAULT '',
                invoice_date TEXT NOT NULL DEFAULT '',
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purchase_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        _ensure_column(
            connection,
            "users",
            "notify_activity",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "users",
            "email",
            "TEXT NOT NULL DEFAULT ''",
        )
        _ensure_column(
            connection,
            "users",
            "notify_email",
            "INTEGER NOT NULL DEFAULT 0",
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
        _ensure_column(
            connection,
            "purchases",
            "photos",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        _migrate_purchase_photos(connection)
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
        _migrate_users_roles(connection)
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
        if cursor.rowcount > 0:
            _log_activity(
                connection,
                "pelengator",
                pelengator_id,
                "pel.archived" if archived else "pel.restored",
                {},
            )
        connection.commit()
        ok = cursor.rowcount > 0
        connection.close()
    return ok


def list_pelengators(*, archived: bool | None = False) -> list[dict]:
    sql = """
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
    """
    args: list = []
    if archived is None:
        sql += """
            ORDER BY COALESCE(pelengators.is_archived, 0),
                     pelengator_types.id, pelengators.id
        """
    else:
        sql += """
            WHERE COALESCE(pelengators.is_archived, 0) = ?
            ORDER BY pelengator_types.id, pelengators.id
        """
        args.append(1 if archived else 0)
    with _lock:
        connection = _connect()
        rows = connection.execute(sql, args).fetchall()
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


def parse_purchase_id(raw: str) -> int | None:
    return parse_pelengator_id(raw)


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
        _log_activity(
            connection,
            "pelengator",
            pelengator_id,
            "pel.created",
            {
                "type_id": type_id,
                "type_name": str(tpl["name"] or ""),
                "location": DEFAULT_LOCATION if "location" in pel_columns else "",
                "archived": bool(archived) if "is_archived" in pel_columns else False,
            },
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
        error_id = cursor.lastrowid
        if error_id:
            _log_activity(
                connection,
                "error",
                error_id,
                "error.created",
                {
                    "pelengator_id": pelengator_id,
                    "kind": kind,
                    "description": description,
                    "hw_class": hw_class or "",
                    "hw_part": hw_part or "",
                    "priority": priority,
                },
            )
        connection.commit()
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
                (SELECT COALESCE(SUM(qty), 0) FROM stock_lots) AS stock_qty,
                (SELECT COUNT(*) FROM purchases WHERE COALESCE(is_archived, 0) = 0) AS purchases,
                (SELECT COUNT(*) FROM purchases WHERE COALESCE(is_archived, 0) = 1) AS archived_purchases,
                (SELECT COUNT(*) FROM purchase_requests) AS requests,
                (SELECT COUNT(*) FROM purchase_requests WHERE status != 'closed') AS requests_open
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
        "purchases": row["purchases"],
        "archived_purchases": row["archived_purchases"],
        "requests": row["requests"],
        "requests_open": row["requests_open"],
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
        old_row = connection.execute(
            f"SELECT {field} FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if old_row is None:
            connection.close()
            return False
        old_value = "" if old_row[field] is None else str(old_row[field])
        cursor = connection.execute(
            f"UPDATE pelengators SET {field} = ? WHERE id = ?",
            (value, pelengator_id),
        )
        updated = cursor.rowcount > 0
        if updated and field == "location" and old_value != value:
            _log_activity(
                connection,
                "pelengator",
                pelengator_id,
                "pel.moved",
                {"from": old_value, "to": value},
            )
        connection.commit()
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
        if cursor.rowcount > 0:
            _log_activity(
                connection,
                "pelengator",
                pelengator_id,
                "pel.reserved",
                {"holder_id": user_id, "holder_name": display_name},
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
        holder_row = connection.execute(
            "SELECT reserved FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        holder_name = "" if holder_row is None else str(holder_row["reserved"] or "")
        started = connection.execute(
            """
            SELECT created_at FROM activity
            WHERE entity_type = 'pelengator'
              AND entity_id = ?
              AND action = 'pel.reserved'
            ORDER BY id DESC
            LIMIT 1
            """,
            (pelengator_id,),
        ).fetchone()
        started_at = "" if started is None else str(started["created_at"] or "")
        ended_at = datetime.now().isoformat(timespec="seconds")
        seconds = None
        if started_at:
            try:
                seconds = int(
                    (
                        datetime.fromisoformat(ended_at)
                        - datetime.fromisoformat(started_at)
                    ).total_seconds()
                )
            except ValueError:
                seconds = None
        connection.execute(
            """
            UPDATE pelengators
            SET reserved = '', reserved_user_id = NULL
            WHERE id = ?
            """,
            (pelengator_id,),
        )
        _log_activity(
            connection,
            "pelengator",
            pelengator_id,
            "pel.released",
            {
                "holder_id": int(owner),
                "holder_name": holder_name,
                "started_at": started_at,
                "ended_at": ended_at,
                "seconds": seconds,
            },
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
        old_name = str(old_tpl["name"] or "") if old_tpl is not None else ""
        _log_activity(
            connection,
            "pelengator",
            pelengator_id,
            "pel.type_changed",
            {
                "from_type_id": int(device_row["type_id"]),
                "from_type_name": old_name,
                "to_type_id": new_type_id,
                "to_type_name": str(new_tpl["name"] or ""),
            },
        )
        connection.commit()
        connection.close()
    return None


def delete_pelengator(pelengator_id: int) -> bool:
    with _lock:
        connection = _connect()
        snap = connection.execute(
            """
            SELECT
                pelengators.location AS location,
                pelengator_types.name AS type_name
            FROM pelengators
            LEFT JOIN pelengator_types
                ON pelengator_types.id = pelengators.type_id
            WHERE pelengators.id = ?
            """,
            (pelengator_id,),
        ).fetchone()
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
        if cursor.rowcount > 0:
            _log_activity(
                connection,
                "pelengator",
                pelengator_id,
                "pel.deleted",
                {
                    "location": "" if snap is None else str(snap["location"] or ""),
                    "type_name": "" if snap is None else str(snap["type_name"] or ""),
                },
            )
        connection.commit()
        deleted = cursor.rowcount > 0
        connection.close()
    return deleted


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_iso() -> str:
    return _now_iso()


def format_check_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso


def format_hold_duration(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds} с"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    rest = minutes % 60
    if rest:
        return f"{hours} ч {rest} мин"
    return f"{hours} ч"


def _int_id_list(raw) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for item in raw or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def parse_log_datetime(raw: str | None, *, end_of_day: bool = False) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%d.%m.%Y" and end_of_day:
            moment = moment.replace(hour=23, minute=59, second=59)
        return moment.isoformat(timespec="seconds")
    return None


def activity_filters_for_role(filters: dict | None, role: str | None) -> dict:
    src = normalize_activity_filters(filters)
    if role != "purchaser":
        return src
    src.pop("pel_ids", None)
    allowed = set(PURCHASER_ALLOWED_ACTIONS)
    selected = src.get("actions")
    if selected:
        kept = [key for key in selected if key in allowed]
        src["actions"] = kept if kept else ["__denied__"]
    else:
        src["actions"] = list(PURCHASER_ALLOWED_ACTIONS)
    return src


def normalize_activity_filters(filters: dict | None) -> dict:
    src = filters if isinstance(filters, dict) else {}
    out: dict = {}
    pel_ids = _int_id_list(src.get("pel_ids"))
    if pel_ids:
        out["pel_ids"] = pel_ids
    stock_ids = _int_id_list(src.get("stock_ids"))
    if stock_ids:
        out["stock_ids"] = stock_ids
    actor_ids = _int_id_list(src.get("actor_ids"))
    if actor_ids:
        out["actor_ids"] = actor_ids
    wanted = set(src.get("actions") or [])
    actions = [key for key in ACTIVITY_ACTION_KEYS if key in wanted]
    if actions:
        out["actions"] = actions
    preset = str(src.get("time_preset") or "")
    time_from = str(src.get("time_from") or "")
    time_to = str(src.get("time_to") or "")
    if preset in ACTIVITY_TIME_PRESETS:
        out["time_preset"] = preset
        if preset == "custom":
            if time_from:
                out["time_from"] = time_from
            if time_to:
                out["time_to"] = time_to
            if not time_from and not time_to:
                out.pop("time_preset", None)
    elif time_from or time_to:
        out["time_preset"] = "custom"
        if time_from:
            out["time_from"] = time_from
        if time_to:
            out["time_to"] = time_to
    return out


def resolve_activity_time(filters: dict | None) -> tuple[str | None, str | None]:
    src = filters if isinstance(filters, dict) else {}
    preset = str(src.get("time_preset") or "")
    now = datetime.now().replace(microsecond=0)
    today = now.replace(hour=0, minute=0, second=0)
    if preset == "today":
        return today.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")
    if preset == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(seconds=1)
        return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")
    if preset == "7d":
        start = now - timedelta(days=7)
        return start.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")
    if preset == "30d":
        start = now - timedelta(days=30)
        return start.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")
    time_from = str(src.get("time_from") or "") or None
    time_to = str(src.get("time_to") or "") or None
    return time_from, time_to


def format_activity_range_label(filters: dict | None) -> str:
    src = filters if isinstance(filters, dict) else {}
    preset = str(src.get("time_preset") or "")
    if preset in ACTIVITY_TIME_PRESETS and preset != "custom":
        return ACTIVITY_TIME_PRESETS[preset].lower()
    time_from, time_to = resolve_activity_time(src)
    if not time_from and not time_to:
        return ""
    start = format_check_time(time_from) if time_from else "…"
    end = format_check_time(time_to) if time_to else "…"
    return f"{start} — {end}"


def _activity_where(filters: dict | None) -> tuple[str, list]:
    src = normalize_activity_filters(filters)
    clauses: list[str] = []
    args: list = []
    entity_clauses: list[str] = []
    pel_ids = src.get("pel_ids") or []
    if pel_ids:
        placeholders = ", ".join("?" for _ in pel_ids)
        entity_clauses.append(
            f"""(
                (entity_type = 'pelengator' AND entity_id IN ({placeholders}))
                OR (
                    entity_type = 'error'
                    AND CAST(json_extract(payload, '$.pelengator_id') AS INTEGER)
                        IN ({placeholders})
                )
            )"""
        )
        args.extend(pel_ids)
        args.extend(pel_ids)
    stock_ids = src.get("stock_ids") or []
    if stock_ids:
        placeholders = ", ".join("?" for _ in stock_ids)
        entity_clauses.append(
            f"(entity_type = 'stock' AND entity_id IN ({placeholders}))"
        )
        args.extend(stock_ids)
    if entity_clauses:
        clauses.append("(" + " OR ".join(entity_clauses) + ")")
    actor_ids = src.get("actor_ids") or []
    if actor_ids:
        placeholders = ", ".join("?" for _ in actor_ids)
        clauses.append(f"actor_id IN ({placeholders})")
        args.extend(actor_ids)
    actions = src.get("actions") or []
    if actions:
        placeholders = ", ".join("?" for _ in actions)
        clauses.append(f"action IN ({placeholders})")
        args.extend(actions)
    time_from, time_to = resolve_activity_time(src)
    if time_from:
        clauses.append("created_at >= ?")
        args.append(time_from)
    if time_to:
        clauses.append("created_at <= ?")
        args.append(time_to)
    if not clauses:
        return "", args
    return "WHERE " + " AND ".join(clauses), args


def count_activity(filters: dict | None = None) -> int:
    where, args = _activity_where(filters)
    with _lock:
        connection = _connect()
        row = connection.execute(
            f"SELECT COUNT(*) AS n FROM activity {where}",
            args,
        ).fetchone()
        connection.close()
    return int(row["n"]) if row else 0


def list_activity(
    *,
    offset: int = 0,
    limit: int = ACTIVITY_PAGE_SIZE,
    filters: dict | None = None,
) -> list[dict]:
    if offset < 0:
        offset = 0
    if limit < 1:
        limit = ACTIVITY_PAGE_SIZE
    where, args = _activity_where(filters)
    with _lock:
        connection = _connect()
        rows = connection.execute(
            f"""
            SELECT * FROM activity
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*args, limit, offset],
        ).fetchall()
        connection.close()
    items = []
    for row in rows:
        raw = row["payload"] if "payload" in row.keys() else "{}"
        try:
            payload = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        items.append(
            {
                "id": row["id"],
                "created_at": str(row["created_at"] or ""),
                "actor_id": (
                    None if row["actor_id"] is None else int(row["actor_id"])
                ),
                "actor_name": str(row["actor_name"] or ""),
                "entity_type": str(row["entity_type"] or ""),
                "entity_id": int(row["entity_id"]),
                "action": str(row["action"] or ""),
                "payload": payload,
            }
        )
    return items


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
        row = connection.execute(
            "SELECT * FROM errors WHERE id = ?",
            (error_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        keys = set(row.keys())
        if "is_deleted" in keys and int(row["is_deleted"] or 0):
            connection.close()
            return False
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
        deleted = cursor.rowcount > 0
        if deleted:
            payload = {
                "pelengator_id": int(row["pelengator_id"]),
                "kind": str(row["kind"] or ""),
                "description": str(row["description"] or ""),
            }
            if "hw_class" in keys:
                payload["hw_class"] = str(row["hw_class"] or "")
            if "hw_part" in keys:
                payload["hw_part"] = str(row["hw_part"] or "")
            if "priority" in keys:
                payload["priority"] = str(row["priority"] or "")
            _log_activity(
                connection,
                "error",
                error_id,
                "error.deleted",
                payload,
            )
        connection.commit()
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
        "notify_activity": (
            int(row["notify_activity"] or 0)
            if "notify_activity" in keys
            else 0
        ),
        "email": (
            str(row["email"] or "")
            if "email" in keys
            else ""
        ),
        "notify_email": (
            int(row["notify_email"] or 0)
            if "notify_email" in keys
            else 0
        ),
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
        role = "owner" if total == 0 else "worker"
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
            WHERE role IN ('owner', 'admin')
              AND (status = 'active' OR status IS NULL OR status = '')
            ORDER BY telegram_id
            """
        ).fetchall()
        connection.close()
    return [_user_from_row(row) for row in rows]


def list_purchasers() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT *
            FROM users
            WHERE role = 'purchaser'
              AND (status = 'active' OR status IS NULL OR status = '')
            ORDER BY telegram_id
            """
        ).fetchall()
        connection.close()
    return [_user_from_row(row) for row in rows]


def can_assign_role(actor: dict | None, target: dict | None, new_role: str) -> bool:
    if actor is None or target is None:
        return False
    if (actor.get("status") or "active") != "active":
        return False
    if actor.get("telegram_id") == target.get("telegram_id"):
        return False
    if target.get("role") == "owner":
        return False
    if new_role not in ASSIGNABLE_ROLES:
        return False
    actor_role = actor.get("role")
    if actor_role == "owner":
        return True
    if actor_role == "admin":
        return (
            target.get("role") not in ("owner", "admin")
            and new_role in ("worker", "purchaser")
        )
    return False


def set_user_role(telegram_id: int, role: str) -> bool:
    if role not in ASSIGNABLE_ROLES:
        return False
    with _lock:
        connection = _connect()
        current = connection.execute(
            "SELECT role FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if current is None or str(current["role"] or "") == "owner":
            connection.close()
            return False
        columns = _columns(connection, "users")
        if role in ("admin", "purchaser") and "status" in columns:
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


def set_user_notify(telegram_id: int, enabled: bool) -> bool:
    with _lock:
        connection = _connect()
        if "notify_activity" not in _columns(connection, "users"):
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE users SET notify_activity = ? WHERE telegram_id = ?",
            (1 if enabled else 0, telegram_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def parse_yandex_email(raw: str | None) -> str | None:
    text = (raw or "").strip().casefold()
    if text in {"-", "нет", "удалить", "убрать"}:
        return ""
    if not text.endswith("@yandex.ru"):
        return None
    local = text[: -len("@yandex.ru")]
    if not local or any(ch.isspace() for ch in local):
        return None
    return text


def set_user_email(telegram_id: int, email: str) -> bool:
    email = (email or "").strip().casefold()
    with _lock:
        connection = _connect()
        if "email" not in _columns(connection, "users"):
            connection.close()
            return False
        if not email:
            cursor = connection.execute(
                """
                UPDATE users
                SET email = '', notify_email = 0
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
        else:
            cursor = connection.execute(
                "UPDATE users SET email = ? WHERE telegram_id = ?",
                (email, telegram_id),
            )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def set_user_notify_email(telegram_id: int, enabled: bool) -> bool:
    with _lock:
        connection = _connect()
        if "notify_email" not in _columns(connection, "users"):
            connection.close()
            return False
        cursor = connection.execute(
            "UPDATE users SET notify_email = ? WHERE telegram_id = ?",
            (1 if enabled else 0, telegram_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def list_email_subscribers() -> list[dict]:
    with _lock:
        connection = _connect()
        columns = _columns(connection, "users")
        if "notify_email" not in columns or "email" not in columns:
            connection.close()
            return []
        rows = connection.execute(
            """
            SELECT *
            FROM users
            WHERE COALESCE(notify_email, 0) = 1
              AND email IS NOT NULL
              AND email != ''
              AND (status = 'active' OR status IS NULL OR status = '')
            """
        ).fetchall()
        connection.close()
    return [_user_from_row(row) for row in rows]


def list_activity_subscribers() -> list[int]:
    with _lock:
        connection = _connect()
        if "notify_activity" not in _columns(connection, "users"):
            connection.close()
            return []
        rows = connection.execute(
            """
            SELECT telegram_id FROM users
            WHERE COALESCE(notify_activity, 0) = 1
              AND (status = 'active' OR status IS NULL OR status = '')
            """
        ).fetchall()
        connection.close()
    return [int(row["telegram_id"]) for row in rows]


def _log_request_from_row(row: sqlite3.Row) -> dict:
    raw = row["filters"] if "filters" in row.keys() else "{}"
    try:
        filters = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        filters = {}
    if not isinstance(filters, dict):
        filters = {}
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"] or ""),
        "requester_id": int(row["requester_id"]),
        "requester_name": str(row["requester_name"] or ""),
        "filters": normalize_activity_filters(filters),
        "status": str(row["status"] or "pending"),
    }


def create_log_request(
    requester_id: int,
    requester_name: str,
    filters: dict | None,
) -> dict:
    payload = json.dumps(normalize_activity_filters(filters), ensure_ascii=False)
    with _lock:
        connection = _connect()
        connection.execute(
            """
            UPDATE log_requests
            SET status = 'cancelled'
            WHERE requester_id = ? AND status = 'pending'
            """,
            (requester_id,),
        )
        cursor = connection.execute(
            """
            INSERT INTO log_requests (
                created_at, requester_id, requester_name, filters, status
            ) VALUES (?, ?, ?, ?, 'pending')
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                requester_id,
                requester_name or "",
                payload,
            ),
        )
        request_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM log_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.commit()
        connection.close()
    return _log_request_from_row(row)


def get_log_request(request_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM log_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.close()
    if row is None:
        return None
    return _log_request_from_row(row)


def set_log_request_status(request_id: int, status: str) -> dict | None:
    if status not in ("approved", "denied", "cancelled"):
        return None
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM log_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if row is None or str(row["status"] or "") != "pending":
            connection.close()
            return None
        connection.execute(
            "UPDATE log_requests SET status = ? WHERE id = ?",
            (status, request_id),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM log_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.close()
    return None if updated is None else _log_request_from_row(updated)


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


def _parse_photo_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item or "").strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return [text] if text else []
        if isinstance(data, list):
            return [str(item) for item in data if str(item or "").strip()]
        return []
    return [text]


def _dump_photo_list(photos: list[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in photos:
        file_id = str(item or "").strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        cleaned.append(file_id)
        if len(cleaned) >= MAX_PURCHASE_PHOTOS:
            break
    return json.dumps(cleaned, ensure_ascii=False)


def _migrate_purchase_photos(connection: sqlite3.Connection) -> None:
    if "purchases" not in {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }:
        return
    columns = _columns(connection, "purchases")
    if "photos" not in columns:
        return
    rows = connection.execute("SELECT * FROM purchases").fetchall()
    for row in rows:
        keys = set(row.keys())
        photos = _parse_photo_list(row["photos"] if "photos" in keys else "[]")
        if not photos and "photo_file_id" in keys and row["photo_file_id"]:
            photos = [str(row["photo_file_id"])]
        dumped = _dump_photo_list(photos)
        current = "" if "photos" not in keys or row["photos"] is None else str(row["photos"])
        if current != dumped:
            connection.execute(
                "UPDATE purchases SET photos = ? WHERE id = ?",
                (dumped, row["id"]),
            )


def parse_invoice_date(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return None


def _purchase_from_row(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    photos = _parse_photo_list(row["photos"] if "photos" in keys else [])
    if not photos and "photo_file_id" in keys and row["photo_file_id"]:
        photos = [str(row["photo_file_id"])]
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or ""),
        "photos": photos,
        "photo_file_id": photos[0] if photos else "",
        "supplier_name": str(row["supplier_name"] or ""),
        "invoice_number": str(row["invoice_number"] or ""),
        "invoice_date": str(row["invoice_date"] or ""),
        "is_archived": int(row["is_archived"] or 0) if "is_archived" in keys else 0,
        "created_by": int(row["created_by"] or 0),
        "created_at": str(row["created_at"] or ""),
    }


def create_purchase(
    name: str,
    *,
    created_by: int,
    supplier_name: str = "",
    invoice_number: str = "",
    invoice_date: str = "",
    photo_file_id: str = "",
) -> int | None:
    name = normalize_stock_text(name)
    if not name or len(name) > MAX_PURCHASE_NAME:
        return None
    supplier_name = normalize_stock_text(supplier_name)
    invoice_number = normalize_stock_text(invoice_number)
    invoice_date = normalize_stock_text(invoice_date)
    if len(supplier_name) > MAX_PURCHASE_FIELD:
        return None
    if len(invoice_number) > MAX_PURCHASE_FIELD:
        return None
    with _lock:
        connection = _connect()
        photos = _dump_photo_list([photo_file_id] if photo_file_id else [])
        columns = _columns(connection, "purchases")
        fields = [
            "name",
            "photo_file_id",
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "is_archived",
            "created_by",
            "created_at",
        ]
        values: list[object] = [
            name,
            photo_file_id or "",
            supplier_name,
            invoice_number,
            invoice_date,
            0,
            created_by,
            _now_iso(),
        ]
        if "photos" in columns:
            fields.insert(2, "photos")
            values.insert(2, photos)
        placeholders = ", ".join("?" for _ in fields)
        cursor = connection.execute(
            f"INSERT INTO purchases ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        purchase_id = cursor.lastrowid
        connection.commit()
        connection.close()
    return purchase_id


def get_purchase(purchase_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM purchases WHERE id = ?",
            (purchase_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _purchase_from_row(row)


def list_purchases(*, archived: bool | None = False) -> list[dict]:
    with _lock:
        connection = _connect()
        if archived is None:
            rows = connection.execute(
                "SELECT * FROM purchases ORDER BY id DESC"
            ).fetchall()
        else:
            flag = 1 if archived else 0
            rows = connection.execute(
                """
                SELECT * FROM purchases
                WHERE COALESCE(is_archived, 0) = ?
                ORDER BY id DESC
                """,
                (flag,),
            ).fetchall()
        connection.close()
    return [_purchase_from_row(row) for row in rows]


def set_purchase_archived(purchase_id: int, archived: bool) -> bool:
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            "UPDATE purchases SET is_archived = ? WHERE id = ?",
            (1 if archived else 0, purchase_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def _save_purchase_photos(
    connection: sqlite3.Connection,
    purchase_id: int,
    photos: list[str],
) -> bool:
    dumped = _dump_photo_list(photos)
    columns = _columns(connection, "purchases")
    if "photos" in columns:
        cursor = connection.execute(
            "UPDATE purchases SET photos = ?, photo_file_id = ? WHERE id = ?",
            (dumped, photos[0] if photos else "", purchase_id),
        )
    else:
        cursor = connection.execute(
            "UPDATE purchases SET photo_file_id = ? WHERE id = ?",
            (photos[0] if photos else "", purchase_id),
        )
    return cursor.rowcount > 0


def add_purchase_photo(purchase_id: int, file_id: str) -> str | None:
    file_id = (file_id or "").strip()
    if not file_id:
        return "bad_photo"
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM purchases WHERE id = ?",
            (purchase_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return "not_found"
        photos = _purchase_from_row(row)["photos"]
        if file_id in photos:
            connection.close()
            return None
        if len(photos) >= MAX_PURCHASE_PHOTOS:
            connection.close()
            return "too_many"
        photos.append(file_id)
        _save_purchase_photos(connection, purchase_id, photos)
        connection.commit()
        connection.close()
    return None


def clear_purchase_photos(purchase_id: int) -> bool:
    with _lock:
        connection = _connect()
        updated = _save_purchase_photos(connection, purchase_id, [])
        connection.commit()
        connection.close()
    return updated


def set_purchase_photo(purchase_id: int, file_id: str | None) -> bool:
    if file_id:
        return add_purchase_photo(purchase_id, file_id) is None
    return clear_purchase_photos(purchase_id)


def update_purchase_field(purchase_id: int, field: str, value: str) -> bool:
    allowed = {
        "name": MAX_PURCHASE_NAME,
        "supplier_name": MAX_PURCHASE_FIELD,
        "invoice_number": MAX_PURCHASE_FIELD,
        "invoice_date": MAX_PURCHASE_FIELD,
    }
    if field not in allowed:
        return False
    if field == "invoice_date":
        parsed = parse_invoice_date(value)
        if parsed is None:
            return False
        value = parsed
    else:
        value = normalize_stock_text(value)
        if not value or len(value) > allowed[field]:
            return False
        if field == "name" and not value:
            return False
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            f"UPDATE purchases SET {field} = ? WHERE id = ?",
            (value, purchase_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


def best_purchase_matches(query: str) -> list[dict]:
    query = normalize_stock_text(query)
    if not query:
        return []
    scored: list[tuple[int, dict]] = []
    for item in list_purchases(archived=None):
        score = letter_shift_score(query, item["name"])
        scored.append((score, item))
    if not scored:
        return []
    best = max(score for score, _item in scored)
    if best <= 1:
        return []
    return [
        {**item, "match_score": best}
        for score, item in scored
        if score == best
    ]


def _request_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "description": str(row["description"] or ""),
        "status": str(row["status"] or "new"),
        "created_by": int(row["created_by"] or 0),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def create_purchase_request(description: str, created_by: int) -> dict | None:
    description = normalize_stock_text(description)
    if not description or len(description) > MAX_REQUEST_DESC:
        return None
    now = _now_iso()
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            """
            INSERT INTO purchase_requests (
                description, status, created_by, created_at, updated_at
            ) VALUES (?, 'new', ?, ?, ?)
            """,
            (description, created_by, now, now),
        )
        request_id = cursor.lastrowid
        connection.commit()
        row = connection.execute(
            "SELECT * FROM purchase_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _request_from_row(row)


def get_purchase_request(request_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            "SELECT * FROM purchase_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _request_from_row(row)


def list_purchase_requests(*, created_by: int | None = None) -> list[dict]:
    with _lock:
        connection = _connect()
        if created_by is None:
            rows = connection.execute(
                """
                SELECT * FROM purchase_requests
                ORDER BY CASE status
                    WHEN 'new' THEN 0
                    WHEN 'in_progress' THEN 1
                    ELSE 2
                END, id DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM purchase_requests
                WHERE created_by = ?
                ORDER BY CASE status
                    WHEN 'new' THEN 0
                    WHEN 'in_progress' THEN 1
                    ELSE 2
                END, id DESC
                """,
                (created_by,),
            ).fetchall()
        connection.close()
    return [_request_from_row(row) for row in rows]


def count_purchase_requests(*, created_by: int | None = None) -> dict:
    with _lock:
        connection = _connect()
        if created_by is None:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status != 'closed' THEN 1 ELSE 0 END) AS open
                FROM purchase_requests
                """
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status != 'closed' THEN 1 ELSE 0 END) AS open
                FROM purchase_requests
                WHERE created_by = ?
                """,
                (created_by,),
            ).fetchone()
        connection.close()
    return {
        "total": int(row["total"] or 0),
        "open": int(row["open"] or 0),
    }


def set_purchase_request_status(request_id: int, status: str) -> dict | None:
    if status not in REQUEST_STATUSES:
        return None
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            """
            UPDATE purchase_requests
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, _now_iso(), request_id),
        )
        if cursor.rowcount == 0:
            connection.close()
            return None
        connection.commit()
        row = connection.execute(
            "SELECT * FROM purchase_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _request_from_row(row)


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
        item_id = cursor.lastrowid
        connection.commit()
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
        _log_activity(
            connection,
            "stock",
            item_id,
            "stock.added",
            {
                "name": _stock_name_locked(connection, item_id),
                "qty": qty,
                "location": location,
            },
        )
        connection.commit()
        connection.close()
    return None


def move_stock(
    item_id: int,
    from_location: str,
    to_location: str,
    qty: int,
    *,
    returned: bool = False,
) -> str | None:
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
        _log_activity(
            connection,
            "stock",
            item_id,
            "stock.returned" if returned else "stock.moved",
            {
                "name": _stock_name_locked(connection, item_id),
                "qty": qty,
                "from": from_location,
                "to": to_location,
            },
        )
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
        _log_activity(
            connection,
            "stock",
            item_id,
            "stock.removed",
            {
                "name": _stock_name_locked(connection, item_id),
                "qty": qty,
                "location": location,
            },
        )
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
            "SELECT id, name FROM stock_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        name = str(row["name"] or "")
        qty_row = connection.execute(
            "SELECT COALESCE(SUM(qty), 0) AS n FROM stock_lots WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        qty = int(qty_row["n"] if qty_row else 0)
        connection.execute(
            "DELETE FROM stock_lots WHERE item_id = ?",
            (item_id,),
        )
        connection.execute(
            "DELETE FROM stock_items WHERE id = ?",
            (item_id,),
        )
        if qty > 0:
            _log_activity(
                connection,
                "stock",
                item_id,
                "stock.deleted",
                {"name": name, "qty": qty},
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
