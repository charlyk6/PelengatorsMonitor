from html import escape
import os
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import screens
import storage

TELEGRAM_BOT_TOKEN = "8628303688:AAFp0DQ19BIYo_g_Gfl2-9Sehhj_uQR82D4"
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()

(
    TYPE_NAME,
    TYPE_BOARD,
    TYPE_MIC,
    TYPE_AXIS,
    TYPE_EDIT_VALUE,
    PEL_ID,
    ERR_DESC,
    ERR_EDIT_DESC,
) = range(8)

TYPE_FIELD_PROMPTS = {
    "name": "Введите новое название:",
    "board": "Введите новую плату:",
    "mic_distance": "Введите расстояние между микрофонами:",
    "axis_distance": "Введите расстояние между осями:",
}


async def render(
    update: Update,
    text: str,
    markup,
    *,
    as_new: bool = False,
) -> None:
    if update.callback_query and not as_new:
        try:
            await update.callback_query.answer()
        except BadRequest:
            pass
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return
        except BadRequest:
            pass

    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )


async def render_screen(
    update: Update,
    screen: tuple[str, object] | None,
    *,
    as_new: bool = False,
) -> None:
    if screen is None:
        text, markup = screens.home_screen()
        await render(update, "Запись не найдена.\n\n" + text, markup, as_new=as_new)
        return
    await render(update, *screen, as_new=as_new)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await render(update, *screens.home_screen())
    return ConversationHandler.END


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await render(update, *screens.home_screen(), as_new=True)
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await render(update, *screens.home_screen())
    return ConversationHandler.END


def _non_empty(text: str | None) -> str:
    return (text or "").strip()


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if query is None or not query.data:
        return None
    data = query.data

    if data == "nav:home":
        return await show_home(update, context)
    if data == "nav:types":
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    if data == "nav:pels":
        await render(update, *screens.pelengators_screen())
        return ConversationHandler.END
    if data == "nav:errs":
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END

    if data.startswith("err:list:"):
        kind = screens.kind_from_code(data.split(":")[2])
        await render(update, *screens.errors_screen(kind))
        return ConversationHandler.END

    if data == "type:add":
        return await start_add_type(update, context)
    if data.startswith("type:v:"):
        await render_screen(update, screens.type_card(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("type:e:"):
        await render_screen(update, screens.type_edit_screen(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("type:f:"):
        return await start_edit_type_field(update, context)
    if data.startswith("type:d:"):
        await render_screen(update, screens.confirm_delete_type(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("type:do:"):
        type_id = int(data.split(":")[2])
        error = storage.delete_type(type_id)
        await query.answer(
            "Нельзя: тип используется" if error == "in_use" else "Тип удалён",
            show_alert=bool(error),
        )
        await render(update, *screens.types_screen())
        return ConversationHandler.END

    if data == "pel:add":
        await render(
            update,
            *screens.pelengator_pick_type_screen(
                "pel:at:",
                "nav:pels",
                "Какой тип у нового пеленгатора?",
            ),
        )
        return ConversationHandler.END
    if data.startswith("pel:at:"):
        return await start_add_pelengator(update, context)
    if data.startswith("pel:v:"):
        await render_screen(update, screens.pelengator_card(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("pel:ct:"):
        pelengator_id = int(data.split(":")[2])
        await render(
            update,
            *screens.pelengator_pick_type_screen(
                f"pel:st:{pelengator_id}:",
                f"pel:v:{pelengator_id}",
                f"Новый тип для пеленгатора #{pelengator_id}:",
            ),
        )
        return ConversationHandler.END
    if data.startswith("pel:st:"):
        _, _, pelengator_id, type_id = data.split(":")
        storage.update_pelengator_type(int(pelengator_id), int(type_id))
        await query.answer("Тип обновлён")
        await render_screen(update, screens.pelengator_card(int(pelengator_id)))
        return ConversationHandler.END
    if data.startswith("pel:d:"):
        await render_screen(
            update,
            screens.confirm_delete_pelengator(int(data.split(":")[2])),
        )
        return ConversationHandler.END
    if data.startswith("pel:do:"):
        pelengator_id = int(data.split(":")[2])
        storage.delete_pelengator(pelengator_id)
        await query.answer("Пеленгатор удалён")
        await render(update, *screens.pelengators_screen())
        return ConversationHandler.END

    if data.startswith("err:add:"):
        kind = screens.kind_from_code(data.split(":")[2])
        await render(update, *screens.pick_pelengator_for_error(kind))
        return ConversationHandler.END
    if data.startswith("err:at:"):
        pelengator_id = int(data.split(":")[2])
        context.user_data["error_pelengator_id"] = pelengator_id
        await render(update, *screens.kind_screen(pelengator_id))
        return ConversationHandler.END
    if data.startswith("err:k:") or data.startswith("err:go:"):
        return await start_add_error(update, context)
    if data.startswith("err:v:"):
        await render_screen(update, screens.error_card(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("err:e:"):
        return await start_edit_error(update, context)
    if data.startswith("err:sk:"):
        _, _, error_id, kind_code = data.split(":")
        kind = "hardware" if kind_code == "h" else "soft"
        storage.update_error(int(error_id), kind=kind)
        await query.answer("Тип ошибки обновлён")
        await render_screen(update, screens.error_card(int(error_id)))
        return ConversationHandler.END
    if data.startswith("err:d:"):
        await render_screen(update, screens.confirm_delete_error(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("err:do:"):
        error_id = int(data.split(":")[2])
        item = storage.get_error(error_id)
        storage.delete_error(error_id)
        await query.answer("Ошибка удалена")
        if item:
            await render(update, *screens.errors_screen(item["kind"]))
        else:
            await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END

    await query.answer()
    return None


async def start_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await render(update, *screens.prompt("Введите название типа:"))
    return TYPE_NAME


async def type_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _non_empty(update.message.text if update.message else None)
    if not name:
        await render(update, *screens.prompt("Название пустое. Введите название типа:"), as_new=True)
        return TYPE_NAME
    context.user_data["type_name"] = name
    await render(update, *screens.prompt("Введите плату:"), as_new=True)
    return TYPE_BOARD


async def type_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    board = _non_empty(update.message.text if update.message else None)
    if not board:
        await render(update, *screens.prompt("Плата пустая. Введите плату:"), as_new=True)
        return TYPE_BOARD
    context.user_data["type_board"] = board
    await render(update, *screens.prompt("Введите расстояние между микрофонами:"), as_new=True)
    return TYPE_MIC


async def type_mic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mic_distance = _non_empty(update.message.text if update.message else None)
    if not mic_distance:
        await render(
            update,
            *screens.prompt("Значение пустое. Введите расстояние между микрофонами:"),
            as_new=True,
        )
        return TYPE_MIC
    context.user_data["type_mic_distance"] = mic_distance
    await render(update, *screens.prompt("Введите расстояние между осями:"), as_new=True)
    return TYPE_AXIS


async def type_axis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    axis_distance = _non_empty(update.message.text if update.message else None)
    if not axis_distance:
        await render(
            update,
            *screens.prompt("Значение пустое. Введите расстояние между осями:"),
            as_new=True,
        )
        return TYPE_AXIS
    type_id = storage.add_type(
        name=context.user_data["type_name"],
        board=context.user_data["type_board"],
        mic_distance=context.user_data["type_mic_distance"],
        axis_distance=axis_distance,
    )
    context.user_data.clear()
    await render_screen(update, screens.type_card(type_id), as_new=True)
    return ConversationHandler.END


async def start_edit_type_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parts = update.callback_query.data.split(":")
    type_id = int(parts[2])
    field = parts[3]
    if field not in TYPE_FIELD_PROMPTS or storage.get_type(type_id) is None:
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    context.user_data["edit_type_id"] = type_id
    context.user_data["edit_type_field"] = field
    current = storage.get_type(type_id)[field]
    await render(
        update,
        *screens.prompt(
            f"{TYPE_FIELD_PROMPTS[field]}\nСейчас: <code>{escape(str(current))}</code>"
        ),
    )
    return TYPE_EDIT_VALUE


async def type_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = _non_empty(update.message.text if update.message else None)
    type_id = context.user_data.get("edit_type_id")
    field = context.user_data.get("edit_type_field")
    if not value or type_id is None or field is None:
        await render(update, *screens.prompt("Введите новое значение:"), as_new=True)
        return TYPE_EDIT_VALUE
    storage.update_type_field(type_id, field, value)
    context.user_data.clear()
    await render_screen(update, screens.type_card(type_id), as_new=True)
    return ConversationHandler.END


async def start_add_pelengator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    type_id = int(update.callback_query.data.split(":")[2])
    type_item = storage.get_type(type_id)
    if type_item is None:
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["pelengator_type_id"] = type_id
    await render(
        update,
        *screens.prompt(
            f"Тип «{escape(type_item['name'])}».\nВведите уникальный id пеленгатора:"
        ),
    )
    return PEL_ID


async def pel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = _non_empty(update.message.text if update.message else None)
    type_id = context.user_data.get("pelengator_type_id")
    if type_id is None:
        await render(update, *screens.home_screen(), as_new=True)
        return ConversationHandler.END
    if not raw.isdigit():
        await render(update, *screens.prompt("id должен быть числом. Введите id:"), as_new=True)
        return PEL_ID
    error = storage.add_pelengator(int(raw), type_id)
    if error == "duplicate_id":
        await render(
            update,
            *screens.prompt(f"id {raw} уже занят. Введите другой:"),
            as_new=True,
        )
        return PEL_ID
    if error:
        await render(update, *screens.pelengators_screen(), as_new=True)
        return ConversationHandler.END
    context.user_data.clear()
    await render_screen(update, screens.pelengator_card(int(raw)), as_new=True)
    return ConversationHandler.END


async def start_add_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parts = update.callback_query.data.split(":")
    if parts[1] == "go":
        pelengator_id = int(parts[2])
        kind = screens.kind_from_code(parts[3])
        context.user_data["error_pelengator_id"] = pelengator_id
    else:
        kind = screens.kind_from_code(parts[2])
        pelengator_id = context.user_data.get("error_pelengator_id")
    if pelengator_id is None:
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    context.user_data["error_kind"] = kind
    label = screens.KIND_LABEL[kind]
    await render(
        update,
        *screens.prompt(
            f"Пеленгатор #{pelengator_id}, {label}.\nОпишите ошибку:"
        ),
    )
    return ERR_DESC


async def err_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = _non_empty(update.message.text if update.message else None)
    pelengator_id = context.user_data.get("error_pelengator_id")
    kind = context.user_data.get("error_kind")
    if not description:
        await render(update, *screens.prompt("Описание пустое. Напишите ошибку:"), as_new=True)
        return ERR_DESC
    if pelengator_id is None or kind is None:
        await render(update, *screens.home_screen(), as_new=True)
        return ConversationHandler.END
    error_id = storage.add_error(pelengator_id, kind, description)
    context.user_data.clear()
    if error_id is None:
        await render(update, *screens.pelengators_screen(), as_new=True)
        return ConversationHandler.END
    await render_screen(update, screens.error_card(error_id), as_new=True)
    return ConversationHandler.END


async def start_edit_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    error_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_error(error_id)
    if item is None:
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    context.user_data["edit_error_id"] = error_id
    await render(
        update,
        *screens.prompt(
            f"Новое описание ошибки #{error_id}.\n"
            f"Сейчас: {escape(item['description'])}"
        ),
    )
    return ERR_EDIT_DESC


async def err_edit_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = _non_empty(update.message.text if update.message else None)
    error_id = context.user_data.get("edit_error_id")
    if not description or error_id is None:
        await render(update, *screens.prompt("Введите новое описание:"), as_new=True)
        return ERR_EDIT_DESC
    storage.update_error(error_id, description=description)
    context.user_data.clear()
    await render_screen(update, screens.error_card(error_id), as_new=True)
    return ConversationHandler.END


_last_network_log = 0.0


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_network_log
    error = context.error
    if isinstance(error, (NetworkError, TimedOut)):
        now = time.monotonic()
        if now - _last_network_log >= 30:
            print(
                "Нет связи с Telegram API. Включите VPN или укажите TELEGRAM_PROXY "
                "в main.py."
            )
            _last_network_log = now
        return
    print(f"Ошибка бота: {error}")


def build_application() -> Application:
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if TELEGRAM_PROXY:
        builder = builder.proxy(TELEGRAM_PROXY).get_updates_proxy(TELEGRAM_PROXY)
        print(f"Используется прокси: {TELEGRAM_PROXY}")
    return builder.build()


def main() -> None:
    storage.init_db()
    print(f"База данных: {storage.DB_PATH}")
    app = build_application()

    conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_type, pattern=r"^type:add$"),
            CallbackQueryHandler(start_edit_type_field, pattern=r"^type:f:"),
            CallbackQueryHandler(start_add_pelengator, pattern=r"^pel:at:"),
            CallbackQueryHandler(start_add_error, pattern=r"^err:(k|go):"),
            CallbackQueryHandler(start_edit_error, pattern=r"^err:e:"),
        ],
        states={
            TYPE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_name)],
            TYPE_BOARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_board)],
            TYPE_MIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_mic)],
            TYPE_AXIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_axis)],
            TYPE_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, type_edit_value)
            ],
            PEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pel_id)],
            ERR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, err_desc)],
            ERR_EDIT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, err_edit_desc)
            ],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(conv_cancel, pattern=r"^conv:cancel$"),
            CallbackQueryHandler(on_callback),
        ],
        allow_reentry=True,
    )

    app.add_handler(conversation)
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_error_handler(on_error)

    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
