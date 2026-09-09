from html import escape
import os
import time

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut
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
    USER_NAME,
    TYPE_NAME,
    TYPE_EDIT_VALUE,
    PEL_ID,
    PEL_EDIT_VALUE,
    ERR_PEL_ID,
    ERR_DESC,
    ERR_EDIT_DESC,
    USER_EDIT_NAME,
) = range(9)

TYPE_FIELD_PROMPTS = {
    "name": "Введите новое название:",
    **{
        field: f"Введите: {label.lower()}:"
        for field, label in storage.TEXT_FIELDS.items()
    },
}


_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


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
                link_preview_options=_NO_PREVIEW,
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
        link_preview_options=_NO_PREVIEW,
    )


async def render_screen(
    update: Update,
    screen: tuple[str, object] | None,
    *,
    as_new: bool = False,
) -> None:
    if screen is None:
        text, markup = _home(update)
        await render(update, "Запись не найдена.\n\n" + text, markup, as_new=as_new)
        return
    await render(update, *screen, as_new=as_new)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await render(update, *_home(update))
    return ConversationHandler.END


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user = update.effective_user
    if user is None:
        return ConversationHandler.END
    db_user = storage.get_user(user.id)
    if db_user is None:
        await render(update, *screens.register_prompt(), as_new=True)
        return USER_NAME
    storage.update_user_username(user.id, user.username)
    status = db_user.get("status") or "active"
    if status == "pending":
        await render(update, *screens.pending_screen(), as_new=True)
        return ConversationHandler.END
    if status == "blocked":
        await render(update, *screens.blocked_screen(), as_new=True)
        return ConversationHandler.END
    pelengator_id = _parse_start_pelengator_id(context)
    if pelengator_id is not None:
        screen = _pel_card(update, pelengator_id)
        if screen is None:
            await render(
                update,
                f"Пеленгатор <code>#{pelengator_id}</code> не найден.\n\n"
                + _home(update)[0],
                _home(update)[1],
                as_new=True,
            )
        else:
            await render_screen(update, screen, as_new=True)
        return ConversationHandler.END
    await render(update, *_home(update), as_new=True)
    return ConversationHandler.END


async def user_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _non_empty(update.message.text if update.message else None)
    user = update.effective_user
    if not name:
        await render(update, *screens.register_prompt(), as_new=True)
        return USER_NAME
    if user is None:
        return ConversationHandler.END
    created, is_new = storage.register_user(user.id, name, user.username)
    context.user_data.clear()
    if is_new:
        await notify_admins_new_user(context, created, except_id=user.id)
        if created.get("status") == "pending":
            await render(update, *screens.pending_screen(), as_new=True)
            return ConversationHandler.END
    await render(update, *_home(update), as_new=True)
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user = update.effective_user
    if user is not None:
        db_user = storage.get_user(user.id)
        if db_user is None:
            await render(update, *screens.register_prompt())
            return USER_NAME
        status = db_user.get("status") or "active"
        if status == "pending":
            await render(update, *screens.pending_screen())
            return ConversationHandler.END
        if status == "blocked":
            await render(update, *screens.blocked_screen())
            return ConversationHandler.END
    await render(update, *_home(update))
    return ConversationHandler.END


def _non_empty(text: str | None) -> str:
    return (text or "").strip()


def _viewer_id(update: Update) -> int | None:
    user = update.effective_user
    return None if user is None else user.id


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    db_user = storage.get_user(user.id)
    return bool(
        db_user
        and db_user.get("role") == "admin"
        and (db_user.get("status") or "active") == "active"
    )


def _home(update: Update) -> tuple:
    return screens.home_screen(is_admin=_is_admin(update))


def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (context.bot.username or "").lstrip("@")


def _pels_screen(context: ContextTypes.DEFAULT_TYPE):
    return screens.pelengators_screen(_bot_username(context))


def _ask(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reset_callback: str | None = None,
) -> tuple[str, object]:
    return screens.prompt(
        text,
        reset_callback=reset_callback,
        back_callback=context.user_data.get("cancel_back"),
    )


def _parse_start_pelengator_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    args = context.args or []
    if not args:
        return None
    raw = (args[0] or "").strip()
    if len(raw) < 2 or raw[0] not in ("p", "P"):
        return None
    return storage.parse_pelengator_id(raw[1:])


def _profile(update: Update) -> tuple[str, object] | None:
    user_id = _viewer_id(update)
    if user_id is None:
        return None
    db_user = storage.get_user(user_id)
    if db_user is None:
        return None
    return screens.profile_screen(db_user)


def _booking_label(update: Update) -> str:
    user = update.effective_user
    if user is None:
        return "неизвестно"
    db_user = storage.get_user(user.id)
    if db_user is None:
        return "неизвестно"
    return storage.booking_label(db_user, user.username)


def need_user(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = None if user is None else storage.get_user(user.id)
        if user is None or db_user is None:
            if update.callback_query:
                try:
                    await update.callback_query.answer(
                        "Сначала /start — укажите имя",
                        show_alert=True,
                    )
                except BadRequest:
                    pass
                return USER_NAME
            return await user_reg_name(update, context)
        storage.update_user_username(user.id, user.username)
        status = db_user.get("status") or "active"
        if status != "active":
            screen = (
                screens.pending_screen()
                if status == "pending"
                else screens.blocked_screen()
            )
            if update.callback_query:
                try:
                    await update.callback_query.answer(
                        "Дождитесь подтверждения администратора"
                        if status == "pending"
                        else "Доступ заблокирован",
                        show_alert=True,
                    )
                except BadRequest:
                    pass
                return ConversationHandler.END
            await render(update, *screen, as_new=True)
            return ConversationHandler.END
        return await handler(update, context)

    wrapped.__name__ = handler.__name__
    return wrapped


def _pel_card(update: Update, pelengator_id: int):
    return screens.pelengator_card(
        pelengator_id,
        viewer_id=_viewer_id(update),
        is_admin=_is_admin(update),
    )


async def notify_admins_new_user(
    context: ContextTypes.DEFAULT_TYPE,
    new_user: dict,
    *,
    except_id: int | None = None,
) -> None:
    nick = f"@{new_user['username']}" if new_user.get("username") else "—"
    text = (
        "Новая регистрация\n"
        f"Имя: <b>{escape(new_user['name'])}</b>\n"
        f"Ник: {escape(nick)}\n\n"
        "<i>Подтвердите доступ или заблокируйте.</i>"
    )
    markup = screens.registration_review_markup(new_user["telegram_id"])
    for admin in storage.list_admins():
        if except_id is not None and admin["telegram_id"] == except_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=admin["telegram_id"],
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            continue


async def _notify_user(context: ContextTypes.DEFAULT_TYPE, telegram_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=telegram_id, text=text)
    except (BadRequest, Forbidden, NetworkError, TimedOut):
        return


async def _show_check_step(update: Update, inspection: dict | None, pelengator_id: int | None = None) -> int:
    if inspection is None:
        if pelengator_id is not None:
            await render_screen(update, _pel_card(update, pelengator_id))
        else:
            await render(update, *_home(update))
        return ConversationHandler.END
    next_index = inspection.get("next_index")
    if inspection["status"] == "in_progress" and next_index is not None:
        await render_screen(
            update, screens.check_question_screen(inspection, next_index)
        )
        return ConversationHandler.END
    await render(update, *screens.check_result_screen(inspection))
    return ConversationHandler.END


async def on_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "go":
        pelengator_id = int(parts[2])
        current = storage.get_continuable_inspection(pelengator_id)
        if current:
            await render(update, *screens.check_resume_screen(current))
            return ConversationHandler.END
        inspection = storage.start_inspection(pelengator_id)
        return await _show_check_step(update, inspection, pelengator_id)

    if action == "new":
        pelengator_id = int(parts[2])
        inspection = storage.start_inspection(pelengator_id)
        return await _show_check_step(update, inspection, pelengator_id)

    if action == "cont":
        inspection_id = int(parts[2])
        inspection = storage.resume_inspection(inspection_id)
        pelengator_id = None if inspection is None else inspection["pelengator_id"]
        return await _show_check_step(update, inspection, pelengator_id)

    if action == "a":
        inspection_id = int(parts[2])
        question_index = int(parts[3])
        result = storage.CHECK_ANSWER_FROM_CODE.get(parts[4] if len(parts) > 4 else "")
        if result is None:
            await query.answer("Неизвестный ответ")
            return ConversationHandler.END
        inspection = storage.save_check_answer(inspection_id, question_index, result)
        pelengator_id = None if inspection is None else inspection["pelengator_id"]
        if inspection and inspection.get("next_index") is None:
            await query.answer("Проверка завершена")
        return await _show_check_step(update, inspection, pelengator_id)

    if action == "cx":
        pelengator_id = storage.cancel_inspection(int(parts[2]))
        await query.answer("Проверка отменена, результаты не сохранены")
        if pelengator_id is None:
            await render(update, *_pels_screen(context))
        else:
            await render_screen(update, _pel_card(update, pelengator_id))
        return ConversationHandler.END

    if action == "end":
        inspection = storage.finish_inspection(int(parts[2]))
        pelengator_id = None if inspection is None else inspection["pelengator_id"]
        await query.answer("Проверка сохранена")
        return await _show_check_step(update, inspection, pelengator_id)

    await query.answer()
    return ConversationHandler.END


@need_user
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if query is None or not query.data:
        return None
    data = query.data

    if data == "nav:home":
        return await show_home(update, context)
    if data == "nav:profile":
        await render_screen(update, _profile(update))
        return ConversationHandler.END
    if data == "me:name":
        return await start_edit_own_name(update, context)
    if data == "nav:types":
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    if data == "nav:pels":
        await render(update, *_pels_screen(context))
        return ConversationHandler.END
    if data == "nav:errs":
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    if data == "nav:users":
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        await render(update, *screens.users_screen(_viewer_id(update)))
        return ConversationHandler.END
    if data.startswith("usr:adm:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        target_id = int(data.split(":")[2])
        storage.set_user_role(target_id, "admin")
        await query.answer("Теперь админ")
        await render(update, *screens.users_screen(_viewer_id(update)))
        return ConversationHandler.END
    if data.startswith("usr:ok:") or data.startswith("usr:bl:") or data.startswith("usr:un:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        action = data.split(":")[1]
        target_id = int(data.split(":")[2])
        viewer = _viewer_id(update)
        if action == "bl" and viewer == target_id:
            await query.answer("Нельзя заблокировать себя", show_alert=True)
            return ConversationHandler.END
        target = storage.get_user(target_id)
        if target is None:
            await query.answer("Пользователь не найден", show_alert=True)
            return ConversationHandler.END
        if action == "ok":
            storage.set_user_status(target_id, "active")
            await query.answer("Подтверждён")
            await _notify_user(context, target_id, "Доступ подтверждён. Нажмите /start.")
            result_label = "Подтверждён"
        elif action == "bl":
            storage.set_user_status(target_id, "blocked")
            await query.answer("Заблокирован")
            await _notify_user(context, target_id, "Доступ заблокирован.")
            result_label = "Заблокирован"
        else:
            storage.set_user_status(target_id, "active")
            await query.answer("Разблокирован")
            await _notify_user(context, target_id, "Доступ восстановлен. Нажмите /start.")
            result_label = "Разблокирован"
        source_text = ""
        if query.message is not None:
            source_text = query.message.text or ""
        if source_text.startswith("Новая регистрация"):
            try:
                await query.edit_message_text(
                    f"{result_label}: <b>{escape(target['name'])}</b>",
                    parse_mode=ParseMode.HTML,
                )
                return ConversationHandler.END
            except BadRequest:
                pass
        await render(update, *screens.users_screen(_viewer_id(update)))
        return ConversationHandler.END

    if data.startswith("err:list:"):
        kind = screens.kind_from_code(data.split(":")[2])
        await render(update, *screens.errors_screen(kind))
        return ConversationHandler.END
    if data == "err:all":
        await render(update, *screens.errors_all_screen())
        return ConversationHandler.END

    if data == "type:add":
        return await start_add_type(update, context)
    if data.startswith("type:v:"):
        await render_screen(update, screens.type_card(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("type:e:"):
        await render_screen(update, screens.type_edit_screen(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("type:tg:"):
        _, _, type_id, field = data.split(":", 3)
        storage.toggle_type_flag(int(type_id), field)
        await render_screen(update, screens.type_edit_screen(int(type_id)))
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
            "Нельзя: шаблон используется" if error == "in_use" else "Шаблон удалён",
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
                "Какой шаблон у нового пеленгатора?",
            ),
        )
        return ConversationHandler.END
    if data.startswith("pel:at:"):
        return await start_add_pelengator(update, context)
    if data.startswith("pel:v:"):
        await render_screen(update, _pel_card(update, int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("chk:"):
        return await on_check_callback(update, context)
    if data.startswith("pel:er:"):
        await render_screen(update, screens.pel_errors_screen(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("pel:pr:"):
        await render_screen(update, screens.pel_props_screen(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("pel:fg:"):
        _, _, pelengator_id, field = data.split(":", 3)
        storage.toggle_pelengator_flag(int(pelengator_id), field)
        await render_screen(update, screens.pel_props_screen(int(pelengator_id)))
        return ConversationHandler.END
    if data.startswith("pel:tx:"):
        return await start_edit_pel_field(update, context)
    if data.startswith("pel:mv:"):
        return await start_move_pelengator(update, context)
    if data.startswith("pel:bk:"):
        pelengator_id = int(data.split(":")[2])
        user_id = _viewer_id(update)
        if user_id is None:
            await query.answer("Не удалось определить аккаунт")
            return ConversationHandler.END
        if _is_admin(update):
            await render(update, *screens.pick_user_for_booking(pelengator_id))
            return ConversationHandler.END
        item = storage.get_pelengator(pelengator_id)
        if item and item.get("reserved_user_id"):
            await query.answer("Уже забронирован", show_alert=True)
            await render_screen(update, _pel_card(update, pelengator_id))
            return ConversationHandler.END
        storage.reserve_pelengator(pelengator_id, user_id, _booking_label(update))
        await query.answer("Забронировано на вас")
        await render_screen(update, _pel_card(update, pelengator_id))
        return ConversationHandler.END
    if data.startswith("pel:bku:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        _, _, pelengator_id, target_id = data.split(":")
        pelengator_id = int(pelengator_id)
        target_id = int(target_id)
        target = storage.get_user(target_id)
        if target is None:
            await query.answer("Пользователь не найден", show_alert=True)
            return ConversationHandler.END
        storage.reserve_pelengator(
            pelengator_id,
            target_id,
            storage.booking_label(target, target.get("username")),
        )
        await query.answer(f"Забронировано на {target['name']}")
        await render_screen(update, _pel_card(update, pelengator_id))
        return ConversationHandler.END
    if data.startswith("pel:ub:"):
        pelengator_id = int(data.split(":")[2])
        user_id = _viewer_id(update)
        if user_id is None:
            await query.answer("Не удалось определить аккаунт")
            return ConversationHandler.END
        error = storage.release_pelengator(pelengator_id, user_id)
        if error == "not_owner":
            await query.answer("Это не ваша бронь", show_alert=True)
        elif error == "not_reserved":
            await query.answer("Пеленгатор уже свободен")
        elif error:
            await query.answer("Не удалось снять бронь", show_alert=True)
        else:
            await query.answer("Бронь снята")
        await render_screen(update, _pel_card(update, pelengator_id))
        return ConversationHandler.END
    if data.startswith("pel:rs:"):
        _, _, pelengator_id, field = data.split(":", 3)
        storage.reset_pelengator_field(int(pelengator_id), field)
        context.user_data.clear()
        await query.answer("Вернул значение шаблона")
        await render_screen(update, screens.pel_props_screen(int(pelengator_id)))
        return ConversationHandler.END
    if data.startswith("pel:ct:"):
        pelengator_id = int(data.split(":")[2])
        await render(
            update,
            *screens.pelengator_pick_type_screen(
                f"pel:st:{pelengator_id}:",
                f"pel:v:{pelengator_id}",
                f"Новый шаблон для пеленгатора #{pelengator_id}:",
            ),
        )
        return ConversationHandler.END
    if data.startswith("pel:st:"):
        _, _, pelengator_id, type_id = data.split(":")
        storage.update_pelengator_type(int(pelengator_id), int(type_id))
        await query.answer("Шаблон обновлён")
        await render_screen(update, _pel_card(update, int(pelengator_id)))
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
        await render(update, *_pels_screen(context))
        return ConversationHandler.END

    if data.startswith("err:add:"):
        return await start_pick_error_pelengator(update, context)
    if data.startswith("err:at:"):
        pelengator_id = int(data.split(":")[2])
        context.user_data["error_pelengator_id"] = pelengator_id
        context.user_data["error_from_list"] = False
        await render(update, *screens.kind_screen(pelengator_id))
        return ConversationHandler.END
    if data == "err:k:h" or data == "err:k:s" or data.startswith("err:go:"):
        kind = "hardware" if data == "err:k:h" else "soft"
        if data.startswith("err:go:"):
            _, _, pelengator_id, kind_code = data.split(":")
            context.user_data["error_pelengator_id"] = int(pelengator_id)
            kind = screens.kind_from_code(kind_code)
        pelengator_id = context.user_data.get("error_pelengator_id")
        if pelengator_id is None:
            await render(update, *screens.errors_hub_screen())
            return ConversationHandler.END
        context.user_data["error_kind"] = kind
        back = (
            f"err:add:{screens.kind_code(kind)}"
            if context.user_data.get("error_from_list")
            else f"err:at:{pelengator_id}"
        )
        await render(
            update,
            *screens.error_class_screen(int(pelengator_id), kind, back),
        )
        return ConversationHandler.END
    if data.startswith("err:hw:") or data.startswith("err:sw:"):
        class_key = data.split(":")[2]
        kind = "hardware" if data.startswith("err:hw:") else "soft"
        pelengator_id = context.user_data.get("error_pelengator_id")
        if pelengator_id is None:
            await render(update, *screens.errors_hub_screen())
            return ConversationHandler.END
        context.user_data["error_kind"] = kind
        screen = screens.error_part_screen(int(pelengator_id), kind, class_key)
        await render_screen(update, screen)
        return ConversationHandler.END
    if data.startswith("err:ds:"):
        return await start_add_error(update, context)
    if data.startswith("err:np:"):
        return await start_error_description(update, context)
    if data.startswith("err:sp:"):
        _, _, error_id, priority = data.split(":")
        storage.set_error_priority(int(error_id), priority)
        await query.answer("Приоритет обновлён")
        await render_screen(update, screens.error_card(int(error_id)))
        return ConversationHandler.END
    if data.startswith("err:v:"):
        await render_screen(update, screens.error_card(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("err:e:"):
        return await start_edit_error(update, context)
    if data.startswith("err:d:"):
        await render_screen(update, screens.confirm_delete_error(int(data.split(":")[2])))
        return ConversationHandler.END
    if data.startswith("err:do:"):
        error_id = int(data.split(":")[2])
        item = storage.get_error(error_id)
        storage.delete_error(error_id)
        await query.answer("Ошибка удалена")
        if item:
            await render(update, *screens.errors_all_screen())
        else:
            await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END

    await query.answer()
    return None


@need_user
async def start_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["cancel_back"] = "nav:types"
    await render(update, *_ask(context, "Введите название шаблона:"))
    return TYPE_NAME


async def type_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _non_empty(update.message.text if update.message else None)
    if not name:
        await render(
            update,
            *_ask(context, "Название пустое. Введите название шаблона:"),
            as_new=True,
        )
        return TYPE_NAME
    type_id = storage.add_type(name)
    context.user_data.clear()
    await render_screen(update, screens.type_card(type_id), as_new=True)
    return ConversationHandler.END


@need_user
async def start_edit_type_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _, _, type_id, field = update.callback_query.data.split(":", 3)
    type_id = int(type_id)
    if field not in TYPE_FIELD_PROMPTS or storage.get_type(type_id) is None:
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    context.user_data["edit_type_id"] = type_id
    context.user_data["edit_type_field"] = field
    context.user_data["cancel_back"] = f"type:e:{type_id}"
    current = storage.get_type(type_id)[field]
    await render(
        update,
        *_ask(
            context,
            f"{TYPE_FIELD_PROMPTS[field]}\nСейчас: <code>{escape(str(current) or '—')}</code>",
        ),
    )
    return TYPE_EDIT_VALUE


async def type_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = _non_empty(update.message.text if update.message else None)
    type_id = context.user_data.get("edit_type_id")
    field = context.user_data.get("edit_type_field")
    if not value or type_id is None or field is None:
        await render(update, *_ask(context, "Введите новое значение:"), as_new=True)
        return TYPE_EDIT_VALUE
    storage.update_type_field(type_id, field, value)
    context.user_data.clear()
    await render_screen(update, screens.type_edit_screen(type_id), as_new=True)
    return ConversationHandler.END


@need_user
async def start_edit_own_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = _viewer_id(update)
    db_user = None if user_id is None else storage.get_user(user_id)
    if db_user is None:
        await render(update, *screens.register_prompt())
        return USER_NAME
    current = db_user.get("name") or "—"
    context.user_data["cancel_back"] = "nav:profile"
    await render(
        update,
        *_ask(context, f"Новое имя:\nСейчас: <code>{escape(current)}</code>"),
    )
    return USER_EDIT_NAME


async def user_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _non_empty(update.message.text if update.message else None)
    user = update.effective_user
    if not name:
        await render(
            update,
            *_ask(context, "Имя пустое. Введите новое имя:"),
            as_new=True,
        )
        return USER_EDIT_NAME
    if user is None:
        return ConversationHandler.END
    storage.update_user_name(user.id, name)
    context.user_data.clear()
    await render_screen(update, _profile(update), as_new=True)
    return ConversationHandler.END


@need_user
async def start_edit_pel_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _, _, pelengator_id, field = update.callback_query.data.split(":", 3)
    pelengator_id = int(pelengator_id)
    item = storage.get_pelengator(pelengator_id)
    if item is None or field not in storage.TEXT_FIELDS:
        await render(update, *_pels_screen(context))
        return ConversationHandler.END
    context.user_data["edit_pel_id"] = pelengator_id
    context.user_data["edit_pel_field"] = field
    context.user_data["cancel_back"] = f"pel:pr:{pelengator_id}"
    current = item["values"][field]
    tpl_val = item.get("type_values", {}).get(field, "")
    changed = current != tpl_val
    suffix = "  ❗" if changed else ""
    tpl_line = f"\nВ шаблоне: <code>{escape(str(tpl_val) or '—')}</code>"
    await render(
        update,
        *_ask(
            context,
            f"{TYPE_FIELD_PROMPTS[field]}\n"
            f"Сейчас: <code>{escape(str(current) or '—')}</code>{suffix}{tpl_line}",
            reset_callback=f"pel:rs:{pelengator_id}:{field}",
        ),
    )
    return PEL_EDIT_VALUE


@need_user
async def start_move_pelengator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pelengator_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        await render(update, *_pels_screen(context))
        return ConversationHandler.END
    context.user_data["edit_pel_id"] = pelengator_id
    context.user_data["edit_pel_field"] = "location"
    context.user_data["cancel_back"] = f"pel:v:{pelengator_id}"
    current = item.get("location") or "—"
    await render(
        update,
        *_ask(
            context,
            f"Куда переместить пеленгатор <b>#{pelengator_id}</b>?\n"
            f"Сейчас: <code>{escape(str(current))}</code>",
        ),
    )
    return PEL_EDIT_VALUE


async def pel_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = _non_empty(update.message.text if update.message else None)
    pelengator_id = context.user_data.get("edit_pel_id")
    field = context.user_data.get("edit_pel_field")
    if not value or pelengator_id is None or field is None:
        await render(update, *_ask(context, "Введите новое значение:"), as_new=True)
        return PEL_EDIT_VALUE
    if field == "location":
        storage.set_pelengator_device_field(pelengator_id, field, value)
        context.user_data.clear()
        await render_screen(update, _pel_card(update, pelengator_id), as_new=True)
        return ConversationHandler.END
    storage.set_pelengator_text(pelengator_id, field, value)
    context.user_data.clear()
    await render_screen(update, screens.pel_props_screen(pelengator_id), as_new=True)
    return ConversationHandler.END


@need_user
async def start_add_pelengator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    type_id = int(update.callback_query.data.split(":")[2])
    type_item = storage.get_type(type_id)
    if type_item is None:
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["pelengator_type_id"] = type_id
    context.user_data["cancel_back"] = "pel:add"
    await render(
        update,
        *_ask(
            context,
            f"Шаблон «{escape(type_item['name'])}».\nВведите уникальный id пеленгатора:",
        ),
    )
    return PEL_ID


async def pel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = _non_empty(update.message.text if update.message else None)
    type_id = context.user_data.get("pelengator_type_id")
    if type_id is None:
        await render(update, *_home(update), as_new=True)
        return ConversationHandler.END
    pelengator_id = storage.parse_pelengator_id(raw)
    if pelengator_id is None:
        await render(
            update,
            *_ask(
                context,
                f"id должен быть числом от 1 до {storage.MAX_PELENGATOR_ID}. Введите id:",
            ),
            as_new=True,
        )
        return PEL_ID
    error = storage.add_pelengator(pelengator_id, type_id)
    if error == "duplicate_id":
        await render(
            update,
            *_ask(context, f"id {raw} уже занят. Введите другой:"),
            as_new=True,
        )
        return PEL_ID
    if error:
        await render(update, *_pels_screen(context), as_new=True)
        return ConversationHandler.END
    context.user_data.clear()
    await render_screen(update, _pel_card(update, pelengator_id), as_new=True)
    return ConversationHandler.END


@need_user
async def start_pick_error_pelengator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind = screens.kind_from_code(update.callback_query.data.split(":")[2])
    context.user_data["error_from_list"] = True
    context.user_data["error_kind"] = kind
    context.user_data["cancel_back"] = f"err:list:{screens.kind_code(kind)}"
    await render(update, *screens.pick_pelengator_for_error(kind))
    if not storage.list_pelengators():
        return ConversationHandler.END
    return ERR_PEL_ID


async def err_pel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = _non_empty(update.message.text if update.message else None)
    kind = context.user_data.get("error_kind")
    if kind is None:
        await render(update, *screens.errors_hub_screen(), as_new=True)
        return ConversationHandler.END
    pelengator_id = storage.parse_pelengator_id(raw)
    if pelengator_id is None:
        await render(
            update,
            *_ask(
                context,
                f"id должен быть числом от 1 до {storage.MAX_PELENGATOR_ID}. "
                "Введите номер пеленгатора:",
            ),
            as_new=True,
        )
        return ERR_PEL_ID
    if storage.get_pelengator(pelengator_id) is None:
        await render(
            update,
            *_ask(context, f"Пеленгатор #{pelengator_id} не найден. Введите другой id:"),
            as_new=True,
        )
        return ERR_PEL_ID
    context.user_data["error_pelengator_id"] = pelengator_id
    await render(
        update,
        *screens.error_class_screen(
            pelengator_id, kind, f"err:add:{screens.kind_code(kind)}"
        ),
        as_new=True,
    )
    return ConversationHandler.END


@need_user
async def start_add_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parts = update.callback_query.data.split(":")
    hw_class = ""
    hw_part = ""
    if parts[1] == "go":
        pelengator_id = int(parts[2])
        kind = screens.kind_from_code(parts[3])
        context.user_data["error_pelengator_id"] = pelengator_id
    else:
        kind = screens.kind_from_code(parts[2])
        pelengator_id = context.user_data.get("error_pelengator_id")
        hw_class = parts[3] if len(parts) > 3 else ""
        hw_part = parts[4] if len(parts) > 4 else ""
    if pelengator_id is None:
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    context.user_data["error_kind"] = kind
    context.user_data["error_hw_class"] = hw_class
    context.user_data["error_hw_part"] = hw_part
    category = screens.error_category_label(
        {"kind": kind, "hw_class": hw_class, "hw_part": hw_part}
    )
    back = f"err:k:{screens.kind_code(kind)}"
    await render(
        update,
        *screens.error_priority_screen(int(pelengator_id), category, back),
    )
    return ConversationHandler.END


@need_user
async def start_error_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    priority = update.callback_query.data.split(":")[2]
    if priority not in storage.ERROR_PRIORITIES:
        priority = storage.DEFAULT_PRIORITY
    pelengator_id = context.user_data.get("error_pelengator_id")
    kind = context.user_data.get("error_kind")
    if pelengator_id is None or kind is None:
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    context.user_data["error_priority"] = priority
    if context.user_data.get("error_from_list"):
        context.user_data["cancel_back"] = "err:all"
    else:
        context.user_data["cancel_back"] = f"pel:v:{pelengator_id}"
    category = screens.error_category_label(
        {
            "kind": kind,
            "hw_class": context.user_data.get("error_hw_class") or "",
            "hw_part": context.user_data.get("error_hw_part") or "",
        }
    )
    prio = screens.error_priority_text({"priority": priority})
    await render(
        update,
        *_ask(
            context,
            f"Пеленгатор #{pelengator_id}, {category}, {prio}.\nОпишите ошибку:",
        ),
    )
    return ERR_DESC


async def err_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = _non_empty(update.message.text if update.message else None)
    pelengator_id = context.user_data.get("error_pelengator_id")
    kind = context.user_data.get("error_kind")
    if not description:
        await render(update, *_ask(context, "Описание пустое. Напишите ошибку:"), as_new=True)
        return ERR_DESC
    if pelengator_id is None or kind is None:
        await render(update, *_home(update), as_new=True)
        return ConversationHandler.END
    error_id = storage.add_error(
        pelengator_id,
        kind,
        description,
        hw_class=context.user_data.get("error_hw_class") or "",
        hw_part=context.user_data.get("error_hw_part") or "",
        priority=context.user_data.get("error_priority") or storage.DEFAULT_PRIORITY,
    )
    context.user_data.clear()
    if error_id is None:
        await render(update, *_pels_screen(context), as_new=True)
        return ConversationHandler.END
    await render_screen(update, screens.error_card(error_id), as_new=True)
    return ConversationHandler.END


@need_user
async def start_edit_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    error_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_error(error_id)
    if item is None:
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    context.user_data["edit_error_id"] = error_id
    context.user_data["cancel_back"] = f"err:v:{error_id}"
    await render(
        update,
        *_ask(
            context,
            f"Новое описание ошибки.\n"
            f"Сейчас: {escape(item['description'])}",
        ),
    )
    return ERR_EDIT_DESC


async def err_edit_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = _non_empty(update.message.text if update.message else None)
    error_id = context.user_data.get("edit_error_id")
    if not description or error_id is None:
        await render(update, *_ask(context, "Введите новое описание:"), as_new=True)
        return ERR_EDIT_DESC
    storage.update_error(error_id, description=description)
    context.user_data.clear()
    await render_screen(update, screens.error_card(error_id), as_new=True)
    return ConversationHandler.END


_last_network_log = 0.0


@need_user
async def open_pelengator_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Открывает карточку пеленгатора если пользователь отправил число."""
    text = (update.message.text or "").strip()
    if not text.isdigit():
        return
    pelengator_id = storage.parse_pelengator_id(text)
    if pelengator_id is None:
        await update.message.reply_text(
            f"id должен быть числом от 1 до {storage.MAX_PELENGATOR_ID}.",
        )
        return
    item = storage.get_pelengator(pelengator_id)
    if item is None:
        await update.message.reply_text(
            f"Пеленгатор <code>#{pelengator_id}</code> не найден.",
            parse_mode=ParseMode.HTML,
        )
        return
    await render_screen(update, _pel_card(update, pelengator_id), as_new=True)


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
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(start_add_type, pattern=r"^type:add$"),
            CallbackQueryHandler(start_edit_type_field, pattern=r"^type:f:"),
            CallbackQueryHandler(start_add_pelengator, pattern=r"^pel:at:"),
            CallbackQueryHandler(start_edit_pel_field, pattern=r"^pel:tx:"),
            CallbackQueryHandler(start_move_pelengator, pattern=r"^pel:mv:"),
            CallbackQueryHandler(start_pick_error_pelengator, pattern=r"^err:add:"),
            CallbackQueryHandler(start_add_error, pattern=r"^err:ds:"),
            CallbackQueryHandler(start_error_description, pattern=r"^err:np:"),
            CallbackQueryHandler(start_edit_error, pattern=r"^err:e:"),
            CallbackQueryHandler(start_edit_own_name, pattern=r"^me:name$"),
        ],
        states={
            USER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_reg_name)],
            USER_EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_edit_name)
            ],
            TYPE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_name)],
            TYPE_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, type_edit_value)
            ],
            PEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pel_id)],
            PEL_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pel_edit_value)
            ],
            ERR_PEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, err_pel_id)],
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
    # Ввод числа вне диалога → открыть карточку пеленгатора
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, open_pelengator_by_id))
    app.add_error_handler(on_error)

    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
