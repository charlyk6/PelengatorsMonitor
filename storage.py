import sqlite3
from pathlib import Path
from threading import Lock

DB_PATH = Path(__file__).resolve().parent / "pelengators.db"

_lock = Lock()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with _lock:
        connection = _connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pelengator_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                board TEXT NOT NULL,
                mic_distance TEXT NOT NULL,
                axis_distance TEXT NOT NULL
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
            """
        )
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(errors)")
        ]
        if "kind" not in columns:
            connection.execute(
                "ALTER TABLE errors ADD COLUMN kind TEXT NOT NULL DEFAULT 'soft'"
            )
        connection.commit()
        connection.close()


def _row_to_type(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "board": row["board"],
        "mic_distance": row["mic_distance"],
        "axis_distance": row["axis_distance"],
    }


def list_types() -> list[dict]:
    with _lock:
        connection = _connect()
        rows = connection.execute(
            """
            SELECT id, name, board, mic_distance, axis_distance
            FROM pelengator_types
            ORDER BY id
            """
        ).fetchall()
        connection.close()
    return [_row_to_type(row) for row in rows]


def get_type(type_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            """
            SELECT id, name, board, mic_distance, axis_distance
            FROM pelengator_types
            WHERE id = ?
            """,
            (type_id,),
        ).fetchone()
        connection.close()
    return None if row is None else _row_to_type(row)


def add_type(
    name: str,
    board: str,
    mic_distance: str,
    axis_distance: str,
) -> int:
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            """
            INSERT INTO pelengator_types (name, board, mic_distance, axis_distance)
            VALUES (?, ?, ?, ?)
            """,
            (name, board, mic_distance, axis_distance),
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
                (
                    SELECT COUNT(*) FROM errors
                    WHERE errors.pelengator_id = pelengators.id
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
            "error_count": row["error_count"],
        }
        for row in rows
    ]


def add_pelengator(pelengator_id: int, type_id: int) -> str | None:
    """Returns an error code or None on success."""
    with _lock:
        connection = _connect()
        type_row = connection.execute(
            "SELECT id FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone()
        if type_row is None:
            connection.close()
            return "type_not_found"

        existing = connection.execute(
            "SELECT id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if existing is not None:
            connection.close()
            return "duplicate_id"

        connection.execute(
            "INSERT INTO pelengators (id, type_id) VALUES (?, ?)",
            (pelengator_id, type_id),
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
                pelengators.id AS id,
                pelengators.type_id AS type_id,
                pelengator_types.name AS type_name,
                pelengator_types.board AS board,
                pelengator_types.mic_distance AS mic_distance,
                pelengator_types.axis_distance AS axis_distance
            FROM pelengators
            JOIN pelengator_types ON pelengator_types.id = pelengators.type_id
            WHERE pelengators.id = ?
            """,
            (pelengator_id,),
        ).fetchone()
        connection.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "type_id": row["type_id"],
        "type_name": row["type_name"],
        "board": row["board"],
        "mic_distance": row["mic_distance"],
        "axis_distance": row["axis_distance"],
    }


def list_errors(kind: str | None = None) -> list[dict]:
    with _lock:
        connection = _connect()
        if kind is None:
            rows = connection.execute(
                """
                SELECT id, pelengator_id, kind, description
                FROM errors
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, pelengator_id, kind, description
                FROM errors
                WHERE kind = ?
                ORDER BY id
                """,
                (kind,),
            ).fetchall()
        connection.close()
    return [
        {
            "id": row["id"],
            "pelengator_id": row["pelengator_id"],
            "kind": row["kind"],
            "description": row["description"],
        }
        for row in rows
    ]


def add_error(pelengator_id: int, kind: str, description: str) -> int | None:
    if kind not in ("hardware", "soft"):
        return None
    with _lock:
        connection = _connect()
        pelengator = connection.execute(
            "SELECT id FROM pelengators WHERE id = ?",
            (pelengator_id,),
        ).fetchone()
        if pelengator is None:
            connection.close()
            return None
        cursor = connection.execute(
            """
            INSERT INTO errors (pelengator_id, kind, description)
            VALUES (?, ?, ?)
            """,
            (pelengator_id, kind, description),
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
                (SELECT COUNT(*) FROM errors) AS errors,
                (SELECT COUNT(*) FROM errors WHERE kind = 'hardware') AS hardware,
                (SELECT COUNT(*) FROM errors WHERE kind = 'soft') AS soft
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
    columns = {
        "name": "name",
        "board": "board",
        "mic_distance": "mic_distance",
        "axis_distance": "axis_distance",
    }
    column = columns.get(field)
    if column is None:
        return False
    with _lock:
        connection = _connect()
        cursor = connection.execute(
            f"UPDATE pelengator_types SET {column} = ? WHERE id = ?",
            (value, type_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return updated


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


def update_pelengator_type(pelengator_id: int, type_id: int) -> str | None:
    with _lock:
        connection = _connect()
        if connection.execute(
            "SELECT id FROM pelengator_types WHERE id = ?",
            (type_id,),
        ).fetchone() is None:
            connection.close()
            return "type_not_found"
        cursor = connection.execute(
            "UPDATE pelengators SET type_id = ? WHERE id = ?",
            (type_id, pelengator_id),
        )
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
    return None if updated else "not_found"


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
            SELECT id, pelengator_id, kind, description
            FROM errors
            WHERE pelengator_id = ?
            ORDER BY id
            """,
            (pelengator_id,),
        ).fetchall()
        connection.close()
    return [
        {
            "id": row["id"],
            "pelengator_id": row["pelengator_id"],
            "kind": row["kind"],
            "description": row["description"],
        }
        for row in rows
    ]


def get_error(error_id: int) -> dict | None:
    with _lock:
        connection = _connect()
        row = connection.execute(
            """
            SELECT id, pelengator_id, kind, description
            FROM errors
            WHERE id = ?
            """,
            (error_id,),
        ).fetchone()
        connection.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "pelengator_id": row["pelengator_id"],
        "kind": row["kind"],
        "description": row["description"],
    }


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
            "SELECT id, kind, description FROM errors WHERE id = ?",
            (error_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return False
        new_kind = kind if kind is not None else row["kind"]
        new_description = description if description is not None else row["description"]
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
        cursor = connection.execute(
            "DELETE FROM errors WHERE id = ?",
            (error_id,),
        )
        connection.commit()
        deleted = cursor.rowcount > 0
        connection.close()
    return deleted


init_db()
