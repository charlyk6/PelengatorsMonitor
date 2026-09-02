from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import storage

TELEGRAM_BOT_TOKEN = "8628303688:AAFp0DQ19BIYo_g_Gfl2-9Sehhj_uQR82D4"

BTN_ADD = "Добавить устройство"
BTN_EDIT = "Изменить устройство"
BTN_DELETE = "Удалить устройство"
BTN_CANCEL = "Отмена"

ADD_NUMBER, EDIT_NUMBER, EDIT_DESCRIPTION, DELETE_NUMBER = range(4)

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_ADD],
        [BTN_EDIT],
        [BTN_DELETE],
    ],
    resize_keyboard=True,
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_CANCEL]],
    resize_keyboard=True,
)

MENU_FILTER = filters.Regex(
    f"^({BTN_ADD}|{BTN_EDIT}|{BTN_DELETE}|{BTN_CANCEL})$"
)


def format_devices() -> str:
    devices = storage.list_devices()
    if not devices:
        return "Устройств пока нет."

    lines = ["Текущие устройства:"]
    for device in devices:
        description = device["description"] or "без описания"
        lines.append(f"• {device['number']} — {description}")
    return "\n".join(lines)


async def show_menu(update: Update, text: str) -> None:
    await update.message.reply_text(
        f"{text}\n\n{format_devices()}",
        reply_markup=MENU_KEYBOARD,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, "Выберите действие:")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, "Действие отменено.")
    return ConversationHandler.END


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Введите уникальный номер устройства:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return ADD_NUMBER


async def add_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = (update.message.text or "").strip()
    if not number:
        await update.message.reply_text(
            "Номер не может быть пустым. Введите уникальный номер:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return ADD_NUMBER

    if not storage.add_device(number):
        await update.message.reply_text(
            f"Устройство с номером {number} уже есть. Введите другой номер:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return ADD_NUMBER

    await show_menu(update, f"Устройство {number} добавлено.")
    return ConversationHandler.END


async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Введите номер устройства, которое нужно изменить:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return EDIT_NUMBER


async def edit_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = (update.message.text or "").strip()
    device = storage.get_device(number)
    if device is None:
        await update.message.reply_text(
            "Устройство с таким номером не найдено. Введите номер ещё раз:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return EDIT_NUMBER

    context.user_data["edit_number"] = device["number"]
    current = device["description"] or "пока нет"
    await update.message.reply_text(
        f"Текущее описание: {current}\n\nВведите новое описание:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return EDIT_DESCRIPTION


async def edit_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = context.user_data.get("edit_number")
    description = (update.message.text or "").strip()
    if not number:
        await show_menu(update, "Не удалось определить устройство. Начните заново.")
        return ConversationHandler.END

    storage.update_description(number, description)
    context.user_data.clear()
    await show_menu(update, f"Описание устройства {number} обновлено.")
    return ConversationHandler.END


async def start_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Введите номер устройства, которое нужно удалить:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return DELETE_NUMBER


async def delete_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = (update.message.text or "").strip()
    if not storage.delete_device(number):
        await update.message.reply_text(
            "Устройство с таким номером не найдено. Введите номер ещё раз:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return DELETE_NUMBER

    await show_menu(update, f"Устройство {number} удалено.")
    return ConversationHandler.END


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{BTN_ADD}$"), start_add),
            MessageHandler(filters.Regex(f"^{BTN_EDIT}$"), start_edit),
            MessageHandler(filters.Regex(f"^{BTN_DELETE}$"), start_delete),
        ],
        states={
            ADD_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~MENU_FILTER, add_number),
            ],
            EDIT_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~MENU_FILTER, edit_number),
            ],
            EDIT_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~MENU_FILTER,
                    edit_description,
                ),
            ],
            DELETE_NUMBER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~MENU_FILTER,
                    delete_number,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel),
            MessageHandler(filters.Regex(f"^{BTN_ADD}$"), start_add),
            MessageHandler(filters.Regex(f"^{BTN_EDIT}$"), start_edit),
            MessageHandler(filters.Regex(f"^{BTN_DELETE}$"), start_delete),
        ],
    )

    app.add_handler(conversation)
    app.add_handler(CommandHandler("start", start))

    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
