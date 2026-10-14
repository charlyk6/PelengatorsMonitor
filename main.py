from html import escape
from io import BytesIO
import asyncio
import os
import time

from telegram import InputFile, InputMediaPhoto, LinkPreviewOptions, Update
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

import mail
import screens
import storage

TELEGRAM_BOT_TOKEN = "8628303688:AAFp0DQ19BIYo_g_Gfl2-9Sehhj_uQR82D4"
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()
MAIL_FROM = os.getenv("MAIL_FROM", "botintelnus@mail.ru").strip()
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "apNadc8IPcKi4gfHCJQ3").strip()
mail.MAIL_FROM = MAIL_FROM
mail.MAIL_PASSWORD = MAIL_PASSWORD
mail.MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "smtp.mail.ru").strip()
mail.MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "2525"))

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
    STK_NAME,
    STK_QTY,
    STK_LOC,
    STK_PHOTO,
    LOGS_TIME_FROM,
    LOGS_TIME_TO,
    LOGS_PEL_FILTER,
    BUY_PHOTO,
    BUY_NAME,
    BUY_SUPPLIER,
    BUY_INVOICE,
    BUY_DATE,
    BUY_EDIT,
    REQ_DESC,
    USER_EDIT_EMAIL,
) = range(24)

STOCK_ERROR_TEXT = {
    "not_enough": "Недостаточно на этом месте.",
    "same_location": "Это то же самое место.",
    "not_found": "Товар не найден.",
    "bad_location": "Укажите место.",
    "bad_qty": "Некорректное количество.",
}

TYPE_FIELD_PROMPTS = {
    "name": "Введите новое название:",
    **{
        field: f"Введите: {label.lower()}:"
        for field, label in storage.TEXT_FIELDS.items()
    },
}


_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
_application: Application | None = None


async def _send_email_notice(to_email: str, subject: str, html_body: str) -> None:
    if not mail.configured() or not to_email:
        return
    try:
        await asyncio.to_thread(mail.send_mail, to_email, subject, html_body)
    except Exception as error:
        print(f"Не удалось отправить письмо на {to_email}: {error}")


async def _flush_activity_notices() -> None:
    events = storage.drain_activity_events()
    if not events:
        return
    subscribers = storage.list_activity_subscribers()
    mail_users = storage.list_email_subscribers()
    if not subscribers and not mail_users:
        return
    bot = None if _application is None else _application.bot
    for event in events:
        text = screens.activity_notify_text(event)
        if bot is not None:
            for telegram_id in subscribers:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        link_preview_options=_NO_PREVIEW,
                    )
                except (Forbidden, BadRequest, NetworkError, TimedOut):
                    continue
        for user in mail_users:
            await _send_email_notice(user.get("email") or "", "Событие", text)


async def render(
    update: Update,
    text: str,
    markup,
    *,
    as_new: bool = False,
) -> None:
    try:
        await _render_message(update, text, markup, as_new=as_new)
    finally:
        await _flush_activity_notices()


async def _render_message(
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


async def render_stock_card(
    update: Update,
    item_id: int,
    *,
    as_new: bool = False,
) -> None:
    try:
        await _render_stock_card(update, item_id, as_new=as_new)
    finally:
        await _flush_activity_notices()


async def render_purchase_card(
    update: Update,
    purchase_id: int,
    *,
    as_new: bool = False,
) -> None:
    screen = screens.purchase_card(purchase_id, _bot_username_from_update(update))
    if screen is None:
        await render_screen(update, None, as_new=as_new)
        return
    text, markup = screen
    item = storage.get_purchase(purchase_id)
    photos = (item or {}).get("photos") or []
    photo = photos[0] if photos else ""
    query = update.callback_query
    chat = update.effective_chat

    async def send_new() -> None:
        if chat is None:
            return
        if photo:
            await chat.send_photo(
                photo=photo,
                caption=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return
        await chat.send_message(
            text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=_NO_PREVIEW,
        )

    if query and not as_new:
        try:
            await query.answer()
        except BadRequest:
            pass
        try:
            if photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(
                        media=photo,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=markup,
                )
            else:
                await query.edit_message_text(
                    text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=_NO_PREVIEW,
                )
            return
        except BadRequest:
            pass
        if query.message is not None:
            try:
                await query.message.delete()
            except BadRequest:
                pass
        await send_new()
        return

    await send_new()


async def _send_purchase_photos(update: Update, photos: list[str]) -> None:
    chat = update.effective_chat
    if chat is None or not photos:
        return
    if len(photos) == 1:
        await chat.send_photo(photo=photos[0])
        return
    media = [
        InputMediaPhoto(media=file_id)
        for file_id in photos[: storage.MAX_PURCHASE_PHOTOS]
    ]
    await chat.send_media_group(media=media)


def _bot_username_from_update(_update: Update) -> str:
    if _application is None:
        return ""
    return (_application.bot.username or "").lstrip("@")


async def _render_stock_card(
    update: Update,
    item_id: int,
    *,
    as_new: bool = False,
) -> None:
    screen = screens.stock_item_card(item_id)
    if screen is None:
        await render_screen(update, None, as_new=as_new)
        return
    text, markup = screen
    item = storage.get_stock_item(item_id)
    photo = (item or {}).get("photo_file_id") or ""
    query = update.callback_query
    chat = update.effective_chat

    async def send_new() -> None:
        if chat is None:
            return
        if photo:
            await chat.send_photo(
                photo=photo,
                caption=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return
        await chat.send_message(
            text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=_NO_PREVIEW,
        )

    if query and not as_new:
        try:
            await query.answer()
        except BadRequest:
            pass
        try:
            if photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(
                        media=photo,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=markup,
                )
            else:
                await query.edit_message_text(
                    text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=_NO_PREVIEW,
                )
            return
        except BadRequest:
            pass
        if query.message is not None:
            try:
                await query.message.delete()
            except BadRequest:
                pass
        await send_new()
        return

    await send_new()


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
    kind, entity_id = _parse_start_arg(context)
    if kind == "pel" and entity_id is not None and not _is_purchaser(update):
        screen = _pel_card(update, entity_id)
        if screen is None:
            await render(
                update,
                f"Пеленгатор <code>#{entity_id}</code> не найден.\n\n"
                + _home(update)[0],
                _home(update)[1],
                as_new=True,
            )
        else:
            await render_screen(update, screen, as_new=True)
        return ConversationHandler.END
    if kind == "stock" and entity_id is not None:
        if storage.get_stock_item(entity_id) is None:
            await render(
                update,
                "Товар не найден.\n\n" + _home(update)[0],
                _home(update)[1],
                as_new=True,
            )
        else:
            await render_stock_card(update, entity_id, as_new=True)
        return ConversationHandler.END
    if kind == "buy" and entity_id is not None and _is_purchaser(update):
        if storage.get_purchase(entity_id) is None:
            await render(
                update,
                f"Закупка <code>#{entity_id}</code> не найдена.\n\n"
                + _home(update)[0],
                _home(update)[1],
                as_new=True,
            )
        else:
            await render_purchase_card(update, entity_id, as_new=True)
        return ConversationHandler.END
    if kind == "req" and entity_id is not None:
        screen = screens.request_card(
            entity_id,
            as_purchaser=_is_purchaser(update),
            viewer_id=_viewer_id(update),
        )
        if screen is None:
            await render(
                update,
                f"Заявка <code>#{entity_id}</code> не найдена.\n\n"
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


def _viewer_user(update: Update) -> dict | None:
    user = update.effective_user
    if user is None:
        return None
    return storage.get_user(user.id)


def _role(update: Update) -> str:
    db_user = _viewer_user(update)
    if db_user is None:
        return "worker"
    return str(db_user.get("role") or "worker")


def _is_admin(update: Update) -> bool:
    db_user = _viewer_user(update)
    return bool(
        db_user
        and db_user.get("role") in ("owner", "admin")
        and (db_user.get("status") or "active") == "active"
    )


def _is_owner(update: Update) -> bool:
    db_user = _viewer_user(update)
    return bool(
        db_user
        and db_user.get("role") == "owner"
        and (db_user.get("status") or "active") == "active"
    )


def _is_purchaser(update: Update) -> bool:
    db_user = _viewer_user(update)
    return bool(
        db_user
        and db_user.get("role") == "purchaser"
        and (db_user.get("status") or "active") == "active"
    )


def _home(update: Update) -> tuple:
    return screens.home_screen(_role(update), viewer_id=_viewer_id(update))


def _users_view(update: Update) -> tuple:
    return screens.users_screen(_viewer_user(update))


def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (context.bot.username or "").lstrip("@")


def _pels_screen(context: ContextTypes.DEFAULT_TYPE):
    return screens.pelengators_screen(_bot_username(context))


def _arch_screen(context: ContextTypes.DEFAULT_TYPE):
    return screens.pelengators_screen(_bot_username(context), archived=True)


def _stock_hub(context: ContextTypes.DEFAULT_TYPE):
    return screens.stock_hub_screen(_bot_username(context))


def _add_pel_pick(*, from_arch: bool) -> tuple:
    return screens.pelengator_pick_type_screen(
        "pel:aa:" if from_arch else "pel:at:",
        "nav:arch" if from_arch else "nav:pels",
        "Какой шаблон у нового пеленгатора?",
    )


def _stk_back(context: ContextTypes.DEFAULT_TYPE) -> str:
    item_id = context.user_data.get("stk_item_id")
    if item_id:
        return f"stk:v:{item_id}"
    return "nav:stock"


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


def _parse_start_arg(context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, int | None]:
    args = context.args or []
    if not args:
        return None, None
    raw = (args[0] or "").strip()
    if len(raw) < 2:
        return None, None
    prefix = raw[0].lower()
    rest = raw[1:]
    if prefix == "p":
        return "pel", storage.parse_pelengator_id(rest)
    if prefix == "s":
        try:
            item_id = int(rest)
        except ValueError:
            return None, None
        if item_id <= 0:
            return None, None
        return "stock", item_id
    if prefix == "b":
        item_id = storage.parse_purchase_id(rest)
        if item_id is None:
            return None, None
        return "buy", item_id
    if prefix == "r":
        item_id = storage.parse_purchase_id(rest)
        if item_id is None:
            return None, None
        return "req", item_id
    return None, None


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


def _bind_actor(update: Update) -> None:
    user = update.effective_user
    if user is None:
        storage.set_activity_actor(None, "")
        return
    db_user = storage.get_user(user.id)
    if db_user is None:
        storage.set_activity_actor(user.id, user.full_name or user.username or "")
        return
    storage.set_activity_actor(
        user.id,
        storage.booking_label(db_user, user.username),
    )


def _copy_log_filters(src) -> dict:
    data = src if isinstance(src, dict) else {}
    pel_ids: list[int] = []
    for item in data.get("pel_ids") or []:
        try:
            pel_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    stock_ids: list[int] = []
    for item in data.get("stock_ids") or []:
        try:
            stock_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    actor_ids: list[int] = []
    for item in data.get("actor_ids") or []:
        try:
            actor_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return {
        "pel_ids": pel_ids,
        "stock_ids": stock_ids,
        "actor_ids": actor_ids,
        "actions": [str(item) for item in (data.get("actions") or [])],
        "time_preset": str(data.get("time_preset") or ""),
        "time_from": str(data.get("time_from") or ""),
        "time_to": str(data.get("time_to") or ""),
    }


def _logs_draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = context.user_data.get("logs_draft")
    if not isinstance(draft, dict):
        draft = _copy_log_filters(context.user_data.get("logs_filters"))
        context.user_data["logs_draft"] = draft
    return draft


def _start_logs_draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = _copy_log_filters(context.user_data.get("logs_filters"))
    context.user_data["logs_draft"] = draft
    return draft


async def _show_logs(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int = 0,
) -> None:
    role = _role(update)
    raw = storage.normalize_activity_filters(
        context.user_data.get("logs_filters") or {}
    )
    context.user_data["logs_filters"] = raw
    filters = storage.activity_filters_for_role(raw, role)
    hide_pels = role == "purchaser"
    if _is_admin(update):
        await render(
            update,
            *screens.logs_screen(offset, filters, hide_pels=hide_pels),
        )
        return
    await render(
        update,
        *screens.logs_request_screen(raw, hide_pels=hide_pels),
    )


async def notify_admins_log_request(
    context: ContextTypes.DEFAULT_TYPE,
    request: dict,
    *,
    except_id: int | None = None,
) -> int:
    text = screens.log_request_admin_text(request)
    markup = screens.log_request_admin_markup(request["id"])
    sent = 0
    for admin in storage.list_admins():
        if except_id is not None and admin["telegram_id"] == except_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=admin["telegram_id"],
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_PREVIEW,
            )
            sent += 1
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            continue
    return sent


async def _deliver_log_history(
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
    filters: dict | None,
) -> None:
    requester = storage.get_user(telegram_id)
    src = storage.activity_filters_for_role(
        filters,
        None if requester is None else requester.get("role"),
    )
    total = storage.count_activity(src)
    items = storage.list_activity(
        offset=0,
        limit=storage.LOG_EXPORT_LIMIT,
        filters=src,
    )
    summary = screens._logs_filter_summary(src)
    header = "<b>История</b>"
    if summary:
        header += "\n" + summary
    if not items:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=header + "\n\nЗаписей нет.",
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_PREVIEW,
            )
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            return
        return
    file_text = screens.logs_history_file_text(src, items, total)
    use_file = total > 25 or len(file_text) > 3500
    if use_file:
        payload = BytesIO(file_text.encode("utf-8"))
        try:
            await context.bot.send_document(
                chat_id=telegram_id,
                document=InputFile(payload, filename="history.txt"),
                caption="История по запросу",
            )
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            return
        return
    chunks: list[str] = []
    current = header + "\n"
    for item in items:
        block = "\n" + screens._activity_event_line(item) + "\n"
        if len(current) + len(block) > 3500 and current != header + "\n":
            chunks.append(current.rstrip())
            current = block.lstrip("\n")
        else:
            current += block
    if current.strip():
        chunks.append(current.rstrip())
    for chunk in chunks:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_PREVIEW,
            )
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            return


async def submit_log_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    user_id = _viewer_id(update)
    if user_id is None:
        return ConversationHandler.END
    filters = storage.activity_filters_for_role(
        context.user_data.get("logs_filters") or {},
        _role(update),
    )
    request = storage.create_log_request(user_id, _booking_label(update), filters)
    sent = await notify_admins_log_request(context, request, except_id=user_id)
    await render(update, *screens.logs_request_sent_screen(no_admins=not sent))
    return ConversationHandler.END


async def decide_log_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    approved: bool,
) -> int:
    query = update.callback_query
    data = "" if query is None or not query.data else query.data
    try:
        request_id = int(data.split(":")[2])
    except (IndexError, ValueError):
        return ConversationHandler.END
    status = "approved" if approved else "denied"
    request = storage.set_log_request_status(request_id, status)
    if request is None:
        if query is not None:
            try:
                await query.answer("Запрос уже обработан", show_alert=True)
            except BadRequest:
                pass
        await render(update, *screens.log_request_done_screen(already=True))
        return ConversationHandler.END
    if approved:
        if query is not None:
            try:
                await query.answer("История выдана")
            except BadRequest:
                pass
        await render(update, *screens.log_request_done_screen(approved=True))
        await _deliver_log_history(
            context,
            request["requester_id"],
            request["filters"],
        )
    else:
        if query is not None:
            try:
                await query.answer("Запрос отклонён")
            except BadRequest:
                pass
        await render(update, *screens.log_request_done_screen(approved=False))
        await _notify_user(
            context,
            request["requester_id"],
            "Администратор отклонил запрос логов.",
        )
    return ConversationHandler.END


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
        storage.set_activity_actor(
            user.id,
            storage.booking_label(db_user, user.username),
        )
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
        try:
            return await handler(update, context)
        finally:
            await _flush_activity_notices()

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


async def notify_purchasers(
    context: ContextTypes.DEFAULT_TYPE,
    item: dict,
    *,
    created: bool = False,
    except_id: int | None = None,
) -> None:
    markup = screens.request_notify_markup(item["id"])
    recipients: dict[int, bool] = {}
    for user in storage.list_purchasers():
        recipients[int(user["telegram_id"])] = False
    if not created:
        recipients[int(item["created_by"])] = True
    if except_id is not None:
        recipients.pop(int(except_id), None)
    for telegram_id, for_author in recipients.items():
        text = screens.request_notify_text(
            item,
            created=created,
            for_author=for_author,
        )
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_PREVIEW,
            )
        except (BadRequest, Forbidden, NetworkError, TimedOut):
            pass
        user = storage.get_user(telegram_id)
        if user and user.get("notify_email") and user.get("email"):
            subject = (
                f"Новая заявка #{item['id']}"
                if created
                else f"Статус заявки #{item['id']}"
            )
            await _send_email_notice(user["email"], subject, text)


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


def _toggle_list_value(values: list, value) -> list:
    values = list(values)
    if value in values:
        values.remove(value)
    else:
        values.append(value)
    return values


async def on_logs_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    data = "" if query is None or not query.data else query.data
    admin = _is_admin(update)
    if (
        data.startswith("logs:p:")
        or data.startswith("logs:ya:")
        or data.startswith("logs:na:")
    ) and not admin:
        if query is not None:
            try:
                await query.answer("Недостаточно прав", show_alert=True)
            except BadRequest:
                pass
        else:
            await _show_logs(update, context)
        return ConversationHandler.END
    if data == "nav:logs":
        context.user_data.pop("logs_draft", None)
        await _show_logs(update, context)
        return ConversationHandler.END
    if data.startswith("logs:p:"):
        try:
            offset = int(data.split(":")[2])
        except (IndexError, ValueError):
            offset = 0
        if offset < 0:
            offset = 0
        await _show_logs(update, context, offset)
        return ConversationHandler.END
    if data == "logs:add":
        context.user_data.pop("logs_draft", None)
        await render(
            update,
            *screens.logs_add_filter_screen(hide_pels=_is_purchaser(update)),
        )
        return ConversationHandler.END
    if data == "logs:clr":
        context.user_data["logs_filters"] = {}
        context.user_data.pop("logs_draft", None)
        await _show_logs(update, context)
        return ConversationHandler.END
    if data.startswith("logs:rm:"):
        kind = data.split(":")[2] if len(data.split(":")) > 2 else ""
        filters = _copy_log_filters(context.user_data.get("logs_filters"))
        if kind == "pels":
            filters["pel_ids"] = []
        elif kind == "stock":
            filters["stock_ids"] = []
        elif kind == "users":
            filters["actor_ids"] = []
        elif kind == "time":
            filters["time_preset"] = ""
            filters["time_from"] = ""
            filters["time_to"] = ""
        elif kind == "ops":
            filters["actions"] = []
        context.user_data["logs_filters"] = storage.normalize_activity_filters(filters)
        await _show_logs(update, context)
        return ConversationHandler.END
    if data == "logs:fk:pels":
        if _is_purchaser(update):
            if query is not None:
                try:
                    await query.answer("Недоступно для закупщика", show_alert=True)
                except BadRequest:
                    pass
            await _show_logs(update, context)
            return ConversationHandler.END
        return await start_logs_pels_filter(update, context)
    if data == "logs:pels":
        await render(
            update,
            *screens.logs_pels_filter_screen(_logs_draft(context)),
        )
        return LOGS_PEL_FILTER
    if data == "logs:fk:stock":
        draft = _start_logs_draft(context)
        context.user_data["logs_stock_page"] = 0
        await render(update, *screens.logs_stock_filter_screen(draft, 0))
        return ConversationHandler.END
    if data == "logs:fk:users":
        draft = _start_logs_draft(context)
        await render(update, *screens.logs_users_filter_screen(draft))
        return ConversationHandler.END
    if data == "logs:fk:ops":
        draft = _start_logs_draft(context)
        await render(
            update,
            *screens.logs_ops_filter_screen(
                draft,
                hide_pels=_is_purchaser(update),
            ),
        )
        return ConversationHandler.END
    if data == "logs:fk:time":
        draft = _start_logs_draft(context)
        await render(update, *screens.logs_time_filter_screen(draft))
        return ConversationHandler.END
    if data == "logs:time":
        await render(update, *screens.logs_time_filter_screen(_logs_draft(context)))
        return ConversationHandler.END
    if data.startswith("logs:tp:"):
        try:
            pel_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return LOGS_PEL_FILTER
        draft = _logs_draft(context)
        ids = list(draft.get("pel_ids") or [])
        if pel_id in ids:
            ids.remove(pel_id)
        draft["pel_ids"] = ids
        await render(update, *screens.logs_pels_filter_screen(draft))
        return LOGS_PEL_FILTER
    if data.startswith("logs:sp:"):
        try:
            page = int(data.split(":")[2])
        except (IndexError, ValueError):
            page = 0
        if page < 0:
            page = 0
        context.user_data["logs_stock_page"] = page
        await render(
            update,
            *screens.logs_stock_filter_screen(_logs_draft(context), page),
        )
        return ConversationHandler.END
    if data.startswith("logs:si:"):
        try:
            item_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return ConversationHandler.END
        draft = _logs_draft(context)
        draft["stock_ids"] = _toggle_list_value(draft.get("stock_ids") or [], item_id)
        page = int(context.user_data.get("logs_stock_page") or 0)
        await render(update, *screens.logs_stock_filter_screen(draft, page))
        return ConversationHandler.END
    if data.startswith("logs:tu:"):
        try:
            user_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return ConversationHandler.END
        draft = _logs_draft(context)
        draft["actor_ids"] = _toggle_list_value(draft.get("actor_ids") or [], user_id)
        await render(update, *screens.logs_users_filter_screen(draft))
        return ConversationHandler.END
    if data.startswith("logs:to:"):
        action = data[len("logs:to:") :]
        if action not in storage.ACTIVITY_ACTION_KEYS:
            return ConversationHandler.END
        draft = _logs_draft(context)
        if _is_purchaser(update) and action in storage.PURCHASER_HIDDEN_ACTIONS:
            return ConversationHandler.END
        draft["actions"] = _toggle_list_value(draft.get("actions") or [], action)
        await render(
            update,
            *screens.logs_ops_filter_screen(
                draft,
                hide_pels=_is_purchaser(update),
            ),
        )
        return ConversationHandler.END
    if data.startswith("logs:ts:"):
        preset = data.split(":")[2] if len(data.split(":")) > 2 else ""
        if preset not in storage.ACTIVITY_TIME_PRESETS or preset == "custom":
            return ConversationHandler.END
        draft = _logs_draft(context)
        if draft.get("time_preset") == preset:
            draft["time_preset"] = ""
            draft["time_from"] = ""
            draft["time_to"] = ""
        else:
            draft["time_preset"] = preset
            draft["time_from"] = ""
            draft["time_to"] = ""
        await render(update, *screens.logs_time_filter_screen(draft))
        return ConversationHandler.END
    if data == "logs:tc":
        return await start_logs_time(update, context)
    if data == "logs:ask":
        if admin:
            await _show_logs(update, context)
            return ConversationHandler.END
        return await submit_log_request(update, context)
    if data.startswith("logs:ya:"):
        return await decide_log_request(update, context, approved=True)
    if data.startswith("logs:na:"):
        return await decide_log_request(update, context, approved=False)
    if data == "logs:ok":
        draft = _logs_draft(context)
        context.user_data["logs_filters"] = storage.normalize_activity_filters(draft)
        context.user_data.pop("logs_draft", None)
        await _show_logs(update, context)
        return ConversationHandler.END
    await _show_logs(update, context)
    return ConversationHandler.END


@need_user
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if query is None or not query.data:
        return None
    data = query.data

    if _is_purchaser(update) and (
        data in {"nav:types", "nav:pels", "nav:arch", "nav:errs"}
        or data.startswith(("type:", "pel:", "err:", "chk:"))
    ):
        await query.answer("Недоступно для закупщика", show_alert=True)
        return ConversationHandler.END
    if not _is_purchaser(update) and (
        data in {"nav:buys", "nav:buyarch"} or data.startswith("buy:")
    ):
        await query.answer("Закупки доступны закупщику", show_alert=True)
        return ConversationHandler.END

    if data == "nav:home":
        return await show_home(update, context)
    if data == "nav:profile":
        await render_screen(update, _profile(update))
        return ConversationHandler.END
    if data == "nav:logs" or data.startswith("logs:"):
        return await on_logs_callback(update, context)
    if data == "me:name":
        return await start_edit_own_name(update, context)
    if data == "me:ntf":
        user_id = _viewer_id(update)
        db_user = None if user_id is None else storage.get_user(user_id)
        if db_user is None:
            await render(update, *screens.register_prompt())
            return USER_NAME
        enabled = not bool(db_user.get("notify_activity"))
        storage.set_user_notify(user_id, enabled)
        try:
            await query.answer(
                "Уведомления в тг включены"
                if enabled
                else "Уведомления в тг выключены"
            )
        except BadRequest:
            pass
        await render_screen(update, _profile(update))
        return ConversationHandler.END
    if data == "me:mail":
        return await start_edit_own_email(update, context)
    if data == "me:entf":
        user_id = _viewer_id(update)
        db_user = None if user_id is None else storage.get_user(user_id)
        if db_user is None:
            await render(update, *screens.register_prompt())
            return USER_NAME
        if not db_user.get("email"):
            await query.answer("Сначала укажите почту", show_alert=True)
            return ConversationHandler.END
        enabled = not bool(db_user.get("notify_email"))
        storage.set_user_notify_email(user_id, enabled)
        try:
            await query.answer(
                "Письма включены" if enabled else "Письма выключены"
            )
        except BadRequest:
            pass
        await render_screen(update, _profile(update))
        return ConversationHandler.END
    if data == "nav:types":
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    if data == "nav:pels":
        await render(update, *_pels_screen(context))
        return ConversationHandler.END
    if data == "nav:arch":
        await render(update, *_arch_screen(context))
        return ConversationHandler.END
    if data == "nav:stock":
        context.user_data.clear()
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    if data == "nav:errs":
        await render(update, *screens.errors_hub_screen())
        return ConversationHandler.END
    if data == "nav:users":
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        await render(update, *_users_view(update))
        return ConversationHandler.END
    if data.startswith("usr:role:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        target_id = int(data.split(":")[2])
        target = storage.get_user(target_id)
        if target is None:
            await query.answer("Пользователь не найден", show_alert=True)
            return ConversationHandler.END
        await render(
            update,
            *screens.user_role_screen(target, _viewer_user(update)),
        )
        return ConversationHandler.END
    if data.startswith("usr:set:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        parts = data.split(":")
        target_id = int(parts[2])
        new_role = parts[3] if len(parts) > 3 else ""
        target = storage.get_user(target_id)
        actor = _viewer_user(update)
        if not storage.can_assign_role(actor, target, new_role):
            await query.answer("Недостаточно прав", show_alert=True)
            return ConversationHandler.END
        storage.set_user_role(target_id, new_role)
        await query.answer(storage.ROLE_LABELS.get(new_role, new_role))
        await render(update, *_users_view(update))
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
        if action == "bl" and target.get("role") == "owner":
            await query.answer("Владельца заблокировать нельзя", show_alert=True)
            return ConversationHandler.END
        if (
            action == "bl"
            and target.get("role") == "admin"
            and not _is_owner(update)
        ):
            await query.answer("Админа может заблокировать только владелец", show_alert=True)
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
        await render(update, *_users_view(update))
        return ConversationHandler.END
    if data == "nav:buys":
        context.user_data.clear()
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
        )
        return ConversationHandler.END
    if data == "nav:buyarch":
        context.user_data.clear()
        await render(
            update,
            *screens.purchases_screen(_bot_username(context), archived=True),
        )
        return ConversationHandler.END
    if data == "nav:reqs" or data.startswith("req:") or data.startswith("buy:"):
        return await on_buy_callback(update, context)

    if data.startswith("err:list:"):
        kind = screens.kind_from_code(data.split(":")[2])
        await render(update, *screens.errors_screen(kind))
        return ConversationHandler.END
    if data == "err:all":
        await render(update, *screens.errors_all_screen())
        return ConversationHandler.END

    if data == "type:add" or data == "type:add:a":
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
    if data.startswith("type:ar:"):
        type_id = int(data.split(":")[2])
        item = storage.get_type(type_id)
        if item is None:
            await render(update, *screens.types_screen())
            return ConversationHandler.END
        now_archive = not bool(item.get("is_archive"))
        storage.set_type_archive(type_id, now_archive)
        await query.answer(
            "Шаблон архивный" if now_archive else "Шаблон обычный"
        )
        await render_screen(update, screens.type_card(type_id))
        return ConversationHandler.END

    if data == "pel:add" or data == "pel:adda":
        await render(update, *_add_pel_pick(from_arch=data == "pel:adda"))
        return ConversationHandler.END
    if data.startswith("pel:at:") or data.startswith("pel:aa:"):
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
    if data.startswith("pel:ar:"):
        pelengator_id = int(data.split(":")[2])
        item = storage.get_pelengator(pelengator_id)
        if item is None:
            await render(update, *_pels_screen(context))
            return ConversationHandler.END
        now_archived = not bool(item.get("is_archived"))
        storage.set_pelengator_archived(pelengator_id, now_archived)
        await query.answer("В архиве" if now_archived else "Достали из архива")
        await render_screen(update, _pel_card(update, pelengator_id))
        return ConversationHandler.END
    if data.startswith("pel:d:"):
        await render_screen(
            update,
            screens.confirm_delete_pelengator(int(data.split(":")[2])),
        )
        return ConversationHandler.END
    if data.startswith("pel:do:"):
        pelengator_id = int(data.split(":")[2])
        item = storage.get_pelengator(pelengator_id)
        was_archived = bool(item and item.get("is_archived"))
        storage.delete_pelengator(pelengator_id)
        await query.answer("Пеленгатор удалён")
        await render(
            update,
            *(_arch_screen(context) if was_archived else _pels_screen(context)),
        )
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

    if data.startswith("stk:"):
        return await on_stock_callback(update, context)

    await query.answer()
    return None


async def _ask_stock_qty(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    as_new: bool = False,
) -> int:
    item_id = context.user_data.get("stk_item_id")
    item = None if item_id is None else storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context), as_new=as_new)
        return ConversationHandler.END
    op = context.user_data.get("stk_op")
    name = escape(item["name"])
    if op == "add":
        text = f"Сколько добавить «{name}» в лабу?"
    elif op == "return":
        loc = context.user_data.get("stk_from") or "—"
        avail = storage.lot_qty(item, loc)
        text = (
            f"Сколько «{name}» вернуть в лабу из «{escape(str(loc))}»?\n"
            f"На месте: <b>{avail}</b> шт."
        )
    elif op == "move":
        loc = context.user_data.get("stk_from") or "—"
        dest = context.user_data.get("stk_to") or "—"
        avail = storage.lot_qty(item, loc)
        text = (
            f"Сколько «{name}» переместить из «{escape(str(loc))}» "
            f"в «{escape(str(dest))}»?\n"
            f"На месте: <b>{avail}</b> шт."
        )
    else:
        loc = context.user_data.get("stk_from") or "—"
        avail = storage.lot_qty(item, loc)
        text = (
            f"Сколько «{name}» списать из «{escape(str(loc))}»?\n"
            f"На месте: <b>{avail}</b> шт."
        )
    context.user_data["cancel_back"] = _stk_back(context)
    await render(update, *_ask(context, text), as_new=as_new)
    return STK_QTY


async def _ask_move_dest(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    as_new: bool = False,
) -> int:
    item_id = context.user_data.get("stk_item_id")
    item = None if item_id is None else storage.get_stock_item(item_id)
    from_loc = context.user_data.get("stk_from") or ""
    if item is None or not from_loc:
        await render(update, *_stock_hub(context), as_new=as_new)
        return ConversationHandler.END
    context.user_data["stk_pick"] = "to"
    context.user_data["cancel_back"] = _stk_back(context)
    await render(
        update,
        *_ask(
            context,
            f"Куда переместить «{escape(item['name'])}» "
            f"из «{escape(from_loc)}»?\n"
            "Напишите место.",
        ),
        as_new=as_new,
    )
    return STK_LOC


async def _apply_stock_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    location: str,
    *,
    as_new: bool = False,
) -> int:
    item_id = context.user_data.get("stk_item_id")
    op = context.user_data.get("stk_op")
    location = storage.normalize_stock_text(location)
    from_loc = storage.normalize_stock_text(context.user_data.get("stk_from") or "")
    if item_id is None or not location or op != "move":
        await render(update, *_stock_hub(context), as_new=as_new)
        return ConversationHandler.END
    if location.lower() == from_loc.lower():
        await render(
            update,
            *_ask(
                context,
                STOCK_ERROR_TEXT.get("same_location", "Это то же самое место.")
                + "\nВведите другое место:",
            ),
            as_new=True,
        )
        return STK_LOC
    context.user_data["stk_to"] = location
    return await _ask_stock_qty(update, context, as_new=as_new)


@need_user
async def on_stock_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if query is None or not query.data:
        return None
    data = query.data
    if data.startswith("stk:v:"):
        context.user_data.clear()
        await render_stock_card(update, int(data.split(":")[2]))
        return ConversationHandler.END
    if data == "stk:in" or data.startswith("stk:in:"):
        return await start_stock_income(update, context)
    if data.startswith("stk:mv:"):
        return await start_stock_move(update, context)
    if data.startswith("stk:rt:"):
        return await start_stock_return(update, context)
    if data.startswith("stk:rm:"):
        return await start_stock_remove(update, context)
    if data == "stk:ok":
        return await start_stock_create(update, context)
    if data.startswith("stk:use:"):
        return await start_stock_use(update, context)
    if data.startswith("stk:ph:"):
        return await start_stock_photo(update, context)
    if data.startswith("stk:px:"):
        item_id = int(data.split(":")[2])
        storage.set_stock_photo(item_id, None)
        await query.answer("Фото убрано")
        await render_stock_card(update, item_id)
        return ConversationHandler.END
    if data.startswith("stk:do:"):
        item_id = int(data.split(":")[2])
        storage.delete_stock_item(item_id)
        await query.answer("Карточка удалена")
        context.user_data.clear()
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    if data.startswith("stk:d:"):
        await render_screen(
            update,
            screens.confirm_delete_stock_item(int(data.split(":")[2])),
        )
        return ConversationHandler.END
    if data.startswith("stk:fl:") or data.startswith("stk:rl:") or data.startswith("stk:rf:"):
        return await stock_pick_from(update, context)
    await query.answer()
    return None


@need_user
async def start_stock_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parts = (update.callback_query.data or "").split(":")
    item_id = int(parts[2]) if len(parts) > 2 else None
    context.user_data.clear()
    context.user_data["stk_op"] = "add"
    if item_id is not None:
        item = storage.get_stock_item(item_id)
        if item is None:
            await render(update, *_stock_hub(context))
            return ConversationHandler.END
        context.user_data["stk_item_id"] = item_id
        context.user_data["cancel_back"] = f"stk:v:{item_id}"
        return await _ask_stock_qty(update, context)
    context.user_data["cancel_back"] = "nav:stock"
    await render(update, *_ask(context, "Введите название товара:"))
    return STK_NAME


async def stock_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = storage.normalize_stock_text(update.message.text if update.message else None)
    if not name:
        await render(
            update,
            *_ask(context, "Название пустое. Введите название товара:"),
            as_new=True,
        )
        return STK_NAME
    if len(name) > storage.MAX_STOCK_NAME:
        await render(
            update,
            *_ask(
                context,
                f"Слишком длинное название (макс. {storage.MAX_STOCK_NAME}). "
                "Введите название товара:",
            ),
            as_new=True,
        )
        return STK_NAME
    context.user_data["stk_name"] = name
    exact = storage.find_stock_item_by_name(name)
    if exact is not None:
        context.user_data["stk_item_id"] = exact["id"]
        return await _ask_stock_qty(update, context, as_new=True)
    best = storage.best_stock_match(name)
    await render(
        update,
        *screens.stock_add_choice_screen(name, best),
        as_new=True,
    )
    return STK_NAME


@need_user
async def start_stock_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = context.user_data.get("stk_name")
    if not name:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    item_id = storage.add_stock_item(name)
    if item_id is None:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    context.user_data["stk_op"] = "add"
    context.user_data["stk_item_id"] = item_id
    context.user_data["cancel_back"] = f"stk:v:{item_id}"
    return await _ask_stock_qty(update, context)


@need_user
async def start_stock_use(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    context.user_data["stk_op"] = "add"
    context.user_data["stk_item_id"] = item_id
    context.user_data["cancel_back"] = f"stk:v:{item_id}"
    return await _ask_stock_qty(update, context)


@need_user
async def start_stock_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = int(update.callback_query.data.split(":")[2])
    return await _start_stock_from_lots(update, context, item_id, op="move")


@need_user
async def start_stock_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = int(update.callback_query.data.split(":")[2])
    return await _start_stock_from_lots(update, context, item_id, op="return")


@need_user
async def start_stock_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = int(update.callback_query.data.split(":")[2])
    return await _start_stock_from_lots(update, context, item_id, op="remove")


def _stock_from_lots(item: dict, op: str) -> list[dict]:
    lots = list(item.get("lots") or [])
    if op != "return":
        return lots
    lab = storage.DEFAULT_LOCATION.lower()
    return [
        lot
        for lot in lots
        if str(lot.get("location") or "").lower() != lab
    ]


async def _start_stock_from_lots(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    item_id: int,
    *,
    op: str,
) -> int:
    item = storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    lots = _stock_from_lots(item, op)
    if op == "return":
        empty_text = (
            "Всё уже в лабе"
            if item.get("lots")
            else "Нечего возвращать"
        )
    elif op == "move":
        empty_text = "Нечего перемещать"
    else:
        empty_text = "Нечего списывать"
    if not lots:
        try:
            await update.callback_query.answer(empty_text, show_alert=True)
        except BadRequest:
            pass
        await render_stock_card(update, item_id)
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["stk_op"] = op
    context.user_data["stk_item_id"] = item_id
    context.user_data["stk_from_choices"] = [lot["location"] for lot in lots]
    context.user_data["cancel_back"] = f"stk:v:{item_id}"
    if len(lots) == 1:
        context.user_data["stk_from"] = lots[0]["location"]
        if op == "move":
            return await _ask_move_dest(update, context)
        return await _ask_stock_qty(update, context)
    context.user_data["stk_pick"] = "from"
    if op == "return":
        title = f"Откуда вернуть «{escape(item['name'])}» в лабу?"
        prefix = "stk:rf:"
    elif op == "move":
        title = f"Откуда переместить «{escape(item['name'])}»?"
        prefix = "stk:fl:"
    else:
        title = f"Откуда списать «{escape(item['name'])}»?"
        prefix = "stk:rl:"
    await render(
        update,
        *screens.stock_lot_pick_screen(
            item,
            callback_prefix=prefix,
            title=title,
            back=f"stk:v:{item_id}",
            lots=lots,
        ),
    )
    return STK_LOC


@need_user
async def stock_pick_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data.get("stk_item_id")
    item = None if item_id is None else storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    try:
        index = int(update.callback_query.data.split(":")[2])
        choices = context.user_data.get("stk_from_choices")
        if choices:
            location = choices[index]
        else:
            location = item["lots"][index]["location"]
    except (IndexError, ValueError, KeyError, TypeError):
        await render_stock_card(update, item_id)
        return ConversationHandler.END
    context.user_data["stk_from"] = location
    if context.user_data.get("stk_op") == "move":
        return await _ask_move_dest(update, context)
    return await _ask_stock_qty(update, context)


async def stock_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _bind_actor(update)
    qty = storage.parse_stock_qty(update.message.text if update.message else None)
    item_id = context.user_data.get("stk_item_id")
    item = None if item_id is None else storage.get_stock_item(item_id)
    op = context.user_data.get("stk_op")
    if item is None or op not in ("add", "move", "remove", "return"):
        await render(update, *_stock_hub(context), as_new=True)
        return ConversationHandler.END
    if qty is None:
        await render(
            update,
            *_ask(
                context,
                f"Нужно целое число от 1 до {storage.MAX_STOCK_QTY}. "
                "Введите количество:",
            ),
            as_new=True,
        )
        return STK_QTY
    if op in ("move", "remove", "return"):
        avail = storage.lot_qty(item, context.user_data.get("stk_from") or "")
        if qty > avail:
            await render(
                update,
                *_ask(
                    context,
                    f"На этом месте только <b>{avail}</b> шт. Введите количество:",
                ),
                as_new=True,
            )
            return STK_QTY
    context.user_data["stk_qty"] = qty
    if op == "add":
        error = storage.add_stock(item_id, storage.DEFAULT_LOCATION, qty)
        if error:
            await render(
                update,
                *_ask(
                    context,
                    STOCK_ERROR_TEXT.get(error, "Не получилось.")
                    + "\nВведите количество:",
                ),
                as_new=True,
            )
            return STK_QTY
        context.user_data.clear()
        await render_stock_card(update, item_id, as_new=True)
        return ConversationHandler.END
    if op == "remove":
        error = storage.remove_stock(
            item_id,
            context.user_data.get("stk_from") or "",
            qty,
        )
        if error:
            await render(
                update,
                *_ask(
                    context,
                    STOCK_ERROR_TEXT.get(error, "Не получилось.")
                    + "\nВведите количество:",
                ),
                as_new=True,
            )
            return STK_QTY
        context.user_data.clear()
        await render_stock_card(update, item_id, as_new=True)
        return ConversationHandler.END
    if op == "return":
        error = storage.move_stock(
            item_id,
            context.user_data.get("stk_from") or "",
            storage.DEFAULT_LOCATION,
            qty,
            returned=True,
        )
        if error:
            await render(
                update,
                *_ask(
                    context,
                    STOCK_ERROR_TEXT.get(error, "Не получилось.")
                    + "\nВведите количество:",
                ),
                as_new=True,
            )
            return STK_QTY
        context.user_data.clear()
        await render_stock_card(update, item_id, as_new=True)
        return ConversationHandler.END
    dest = context.user_data.get("stk_to") or ""
    if not dest:
        return await _ask_move_dest(update, context, as_new=True)
    error = storage.move_stock(
        item_id,
        context.user_data.get("stk_from") or "",
        dest,
        qty,
    )
    if error:
        await render(
            update,
            *_ask(
                context,
                STOCK_ERROR_TEXT.get(error, "Не получилось.")
                + "\nВведите количество:",
            ),
            as_new=True,
        )
        return STK_QTY
    context.user_data.clear()
    await render_stock_card(update, item_id, as_new=True)
    return ConversationHandler.END


async def stock_loc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("stk_pick") == "from":
        await render(
            update,
            *_ask(context, "Выберите место кнопкой, не сообщением."),
            as_new=True,
        )
        return STK_LOC
    location = storage.normalize_stock_text(
        update.message.text if update.message else None
    )
    if not location:
        await render(
            update,
            *_ask(context, "Место пустое. Введите место:"),
            as_new=True,
        )
        return STK_LOC
    return await _apply_stock_location(update, context, location, as_new=True)


def _message_photo_id(message) -> str | None:
    if message is None:
        return None
    if message.photo:
        return message.photo[-1].file_id
    document = message.document
    if document is not None and (document.mime_type or "").startswith("image/"):
        return document.file_id
    return None


@need_user
async def start_stock_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context))
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["stk_item_id"] = item_id
    context.user_data["cancel_back"] = f"stk:v:{item_id}"
    await render(update, *screens.stock_photo_prompt(item_id, item["name"]))
    return STK_PHOTO


async def stock_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _bind_actor(update)
    item_id = context.user_data.get("stk_item_id")
    file_id = _message_photo_id(update.message)
    if item_id is None:
        await render(update, *_stock_hub(context), as_new=True)
        return ConversationHandler.END
    item = storage.get_stock_item(item_id)
    if item is None or not file_id:
        await render(
            update,
            *screens.stock_photo_prompt(
                item_id,
                (item or {}).get("name") or "товар",
            ),
            as_new=True,
        )
        return STK_PHOTO
    storage.set_stock_photo(item_id, file_id)
    context.user_data.clear()
    await render_stock_card(update, item_id, as_new=True)
    return ConversationHandler.END


async def stock_photo_wrong(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data.get("stk_item_id")
    item = None if item_id is None else storage.get_stock_item(item_id)
    if item is None:
        await render(update, *_stock_hub(context), as_new=True)
        return ConversationHandler.END
    await render(
        update,
        *screens.stock_photo_prompt(item_id, item["name"]),
        as_new=True,
    )
    return STK_PHOTO


@need_user
async def start_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_archive = (update.callback_query.data or "") == "type:add:a"
    context.user_data.clear()
    context.user_data["new_type_archive"] = is_archive
    context.user_data["cancel_back"] = "nav:types"
    prompt = (
        "Введите название архивного шаблона:"
        if is_archive
        else "Введите название шаблона:"
    )
    await render(update, *_ask(context, prompt))
    return TYPE_NAME


async def type_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _non_empty(update.message.text if update.message else None)
    is_archive = bool(context.user_data.get("new_type_archive"))
    empty_prompt = (
        "Название пустое. Введите название архивного шаблона:"
        if is_archive
        else "Название пустое. Введите название шаблона:"
    )
    if not name:
        await render(
            update,
            *_ask(context, empty_prompt),
            as_new=True,
        )
        return TYPE_NAME
    type_id = storage.add_type(name, is_archive=is_archive)
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
async def start_edit_own_email(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    user_id = _viewer_id(update)
    db_user = None if user_id is None else storage.get_user(user_id)
    if db_user is None:
        await render(update, *screens.register_prompt())
        return USER_NAME
    current = db_user.get("email") or "—"
    context.user_data["cancel_back"] = "nav:profile"
    await render(
        update,
        *_ask(
            context,
            "Почта Яндекса, например <code>name@yandex.ru</code>.\n"
            f"Сейчас: <code>{escape(current)}</code>\n\n"
            "Чтобы убрать, напишите <code>удалить</code>.",
        ),
    )
    return USER_EDIT_EMAIL


async def user_edit_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = storage.parse_yandex_email(
        update.message.text if update.message else None
    )
    user = update.effective_user
    if parsed is None:
        await render(
            update,
            *_ask(
                context,
                "Нужен адрес вида <code>name@yandex.ru</code>. "
                "Либо напишите <code>удалить</code>.",
            ),
            as_new=True,
        )
        return USER_EDIT_EMAIL
    if user is None:
        return ConversationHandler.END
    storage.set_user_email(user.id, parsed)
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
    _bind_actor(update)
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
    parts = update.callback_query.data.split(":")
    from_arch = parts[1] == "aa"
    type_id = int(parts[2])
    type_item = storage.get_type(type_id)
    if type_item is None:
        await render(update, *screens.types_screen())
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["pelengator_type_id"] = type_id
    context.user_data["cancel_back"] = "pel:adda" if from_arch else "pel:add"
    await render(
        update,
        *_ask(
            context,
            f"Шаблон «{escape(type_item['name'])}».\nВведите уникальный id пеленгатора:",
        ),
    )
    return PEL_ID


async def pel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _bind_actor(update)
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
    _bind_actor(update)
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


BUY_FIELD_PROMPTS = {
    "name": "Введите наименование:",
    "supplier_name": "Введите поставщика:",
    "invoice_number": "Введите номер счёта:",
    "invoice_date": "Введите дату счёта, например <code>13.10.2026</code>:",
}


@need_user
async def on_buy_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int | None:
    query = update.callback_query
    if query is None or not query.data:
        return None
    data = query.data
    if data == "nav:buys":
        context.user_data.clear()
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
        )
        return ConversationHandler.END
    if data == "nav:buyarch":
        context.user_data.clear()
        await render(
            update,
            *screens.purchases_screen(_bot_username(context), archived=True),
        )
        return ConversationHandler.END
    if data == "nav:reqs":
        await render(
            update,
            *screens.requests_screen(
                viewer_id=_viewer_id(update) or 0,
                as_purchaser=_is_purchaser(update),
                bot_username=_bot_username(context),
            ),
        )
        return ConversationHandler.END
    if data == "buy:add":
        return await start_add_purchase(update, context)
    if data == "buy:noph":
        if not _is_purchaser(update):
            await query.answer("Закупки доступны закупщику", show_alert=True)
            return ConversationHandler.END
        context.user_data["buy_photo_file_id"] = ""
        context.user_data["cancel_back"] = "nav:buys"
        await render(update, *_ask(context, "Введите наименование:"))
        return BUY_NAME
    if data.startswith("buy:v:"):
        await render_purchase_card(update, int(data.split(":")[2]))
        return ConversationHandler.END
    if data.startswith("buy:ar:"):
        purchase_id = int(data.split(":")[2])
        item = storage.get_purchase(purchase_id)
        if item is None:
            await render(
                update,
                *screens.purchases_screen(_bot_username(context)),
            )
            return ConversationHandler.END
        now_archived = not bool(item.get("is_archived"))
        storage.set_purchase_archived(purchase_id, now_archived)
        await query.answer("В архиве" if now_archived else "Достали из архива")
        await render_purchase_card(update, purchase_id)
        return ConversationHandler.END
    if data.startswith("buy:ph:"):
        return await start_purchase_photo(update, context)
    if data.startswith("buy:ps:"):
        purchase_id = int(data.split(":")[2])
        item = storage.get_purchase(purchase_id)
        photos = [] if item is None else (item.get("photos") or [])
        if not photos:
            await query.answer("Фото нет")
            return ConversationHandler.END
        await query.answer()
        await _send_purchase_photos(update, photos)
        return ConversationHandler.END
    if data.startswith("buy:px:"):
        purchase_id = int(data.split(":")[2])
        storage.clear_purchase_photos(purchase_id)
        await query.answer("Фото удалены")
        await render_purchase_card(update, purchase_id)
        return ConversationHandler.END
    if data.startswith("buy:e:"):
        return await start_edit_purchase_field(update, context)
    if data == "req:add":
        return await start_add_request(update, context)
    if data.startswith("req:v:"):
        request_id = int(data.split(":")[2])
        screen = screens.request_card(
            request_id,
            as_purchaser=_is_purchaser(update),
            viewer_id=_viewer_id(update),
        )
        await render_screen(update, screen)
        return ConversationHandler.END
    if data.startswith("req:st:"):
        if not _is_purchaser(update):
            await query.answer("Статус меняет закупщик", show_alert=True)
            return ConversationHandler.END
        parts = data.split(":")
        request_id = int(parts[2])
        status = storage.REQUEST_STATUS_CODES.get(parts[3] if len(parts) > 3 else "")
        if not status:
            await query.answer("Неизвестный статус", show_alert=True)
            return ConversationHandler.END
        item = storage.set_purchase_request_status(request_id, status)
        if item is None:
            await query.answer("Не удалось сменить статус", show_alert=True)
            return ConversationHandler.END
        await query.answer(storage.REQUEST_STATUS_LABELS.get(status, status))
        await notify_purchasers(
            context,
            item,
            except_id=_viewer_id(update),
        )
        await render_screen(
            update,
            screens.request_card(
                request_id,
                as_purchaser=True,
                viewer_id=_viewer_id(update),
            ),
        )
        return ConversationHandler.END
    return None


@need_user
async def start_add_purchase(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not _is_purchaser(update):
        if update.callback_query:
            await update.callback_query.answer(
                "Закупки доступны закупщику",
                show_alert=True,
            )
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["buy_creating"] = True
    context.user_data["cancel_back"] = "nav:buys"
    await render(update, *screens.purchase_wizard_photo())
    return BUY_PHOTO


@need_user
async def start_purchase_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not _is_purchaser(update):
        return ConversationHandler.END
    purchase_id = int(update.callback_query.data.split(":")[2])
    item = storage.get_purchase(purchase_id)
    if item is None:
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
        )
        return ConversationHandler.END
    photos = item.get("photos") or []
    if len(photos) >= storage.MAX_PURCHASE_PHOTOS:
        if update.callback_query:
            await update.callback_query.answer(
                f"Максимум {storage.MAX_PURCHASE_PHOTOS} фото",
                show_alert=True,
            )
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["buy_id"] = purchase_id
    context.user_data["cancel_back"] = f"buy:v:{purchase_id}"
    await render(
        update,
        *screens.purchase_photo_prompt(
            purchase_id,
            item["name"],
            count=len(photos),
        ),
    )
    return BUY_PHOTO


@need_user
async def start_edit_purchase_field(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not _is_purchaser(update):
        return ConversationHandler.END
    _, _, purchase_id, field = update.callback_query.data.split(":", 3)
    purchase_id = int(purchase_id)
    if field not in BUY_FIELD_PROMPTS:
        return ConversationHandler.END
    item = storage.get_purchase(purchase_id)
    if item is None:
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
        )
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["buy_id"] = purchase_id
    context.user_data["buy_field"] = field
    context.user_data["cancel_back"] = f"buy:v:{purchase_id}"
    await render(update, *_ask(context, BUY_FIELD_PROMPTS[field]))
    return BUY_EDIT


@need_user
async def start_add_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if _is_purchaser(update):
        if update.callback_query:
            await update.callback_query.answer(
                "Заявку создаёт работник или админ",
                show_alert=True,
            )
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data["cancel_back"] = "nav:reqs"
    await render(
        update,
        *_ask(context, "Опишите, что нужно закупить:"),
    )
    return REQ_DESC


async def buy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _bind_actor(update)
    file_id = _message_photo_id(update.message)
    if context.user_data.get("buy_creating"):
        if not file_id:
            await render(update, *screens.purchase_wizard_photo(), as_new=True)
            return BUY_PHOTO
        context.user_data["buy_photo_file_id"] = file_id
        context.user_data["cancel_back"] = "nav:buys"
        await render(
            update,
            *_ask(context, "Введите наименование:"),
            as_new=True,
        )
        return BUY_NAME
    purchase_id = context.user_data.get("buy_id")
    item = None if purchase_id is None else storage.get_purchase(purchase_id)
    if item is None or not file_id:
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
            as_new=True,
        )
        return ConversationHandler.END
    error = storage.add_purchase_photo(purchase_id, file_id)
    if error == "too_many":
        context.user_data.clear()
        await render_purchase_card(update, purchase_id, as_new=True)
        return ConversationHandler.END
    item = storage.get_purchase(purchase_id)
    photos = [] if item is None else (item.get("photos") or [])
    if len(photos) >= storage.MAX_PURCHASE_PHOTOS:
        context.user_data.clear()
        await render_purchase_card(update, purchase_id, as_new=True)
        return ConversationHandler.END
    await render(
        update,
        *screens.purchase_photo_prompt(
            purchase_id,
            item["name"],
            count=len(photos),
        ),
        as_new=True,
    )
    return BUY_PHOTO


async def buy_photo_wrong(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if context.user_data.get("buy_creating"):
        await render(update, *screens.purchase_wizard_photo(), as_new=True)
        return BUY_PHOTO
    purchase_id = context.user_data.get("buy_id")
    item = None if purchase_id is None else storage.get_purchase(purchase_id)
    if item is None:
        await render(
            update,
            *screens.purchases_screen(_bot_username(context)),
            as_new=True,
        )
        return ConversationHandler.END
    await render(
        update,
        *screens.purchase_photo_prompt(
            purchase_id,
            item["name"],
            count=len(item.get("photos") or []),
        ),
        as_new=True,
    )
    return BUY_PHOTO


async def buy_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = storage.normalize_stock_text(update.message.text if update.message else None)
    if not name:
        await render(
            update,
            *_ask(context, "Название пустое. Введите наименование:"),
            as_new=True,
        )
        return BUY_NAME
    if len(name) > storage.MAX_PURCHASE_NAME:
        await render(
            update,
            *_ask(
                context,
                f"Слишком длинное название (макс. {storage.MAX_PURCHASE_NAME}). "
                "Введите наименование:",
            ),
            as_new=True,
        )
        return BUY_NAME
    context.user_data["buy_name"] = name
    await render(update, *_ask(context, "Введите поставщика:"), as_new=True)
    return BUY_SUPPLIER


async def buy_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = storage.normalize_stock_text(update.message.text if update.message else None)
    if not value or len(value) > storage.MAX_PURCHASE_FIELD:
        await render(
            update,
            *_ask(context, "Введите поставщика:"),
            as_new=True,
        )
        return BUY_SUPPLIER
    context.user_data["buy_supplier"] = value
    await render(update, *_ask(context, "Введите номер счёта:"), as_new=True)
    return BUY_INVOICE


async def buy_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = storage.normalize_stock_text(update.message.text if update.message else None)
    if not value or len(value) > storage.MAX_PURCHASE_FIELD:
        await render(
            update,
            *_ask(context, "Введите номер счёта:"),
            as_new=True,
        )
        return BUY_INVOICE
    context.user_data["buy_invoice"] = value
    await render(
        update,
        *_ask(
            context,
            "Введите дату счёта, например <code>13.10.2026</code>:",
        ),
        as_new=True,
    )
    return BUY_DATE


async def buy_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = storage.parse_invoice_date(
        _non_empty(update.message.text if update.message else None)
    )
    if not parsed:
        await render(
            update,
            *_ask(
                context,
                "Не понял дату. Введите как <code>13.10.2026</code>:",
            ),
            as_new=True,
        )
        return BUY_DATE
    user_id = _viewer_id(update)
    if user_id is None:
        return ConversationHandler.END
    purchase_id = storage.create_purchase(
        context.user_data.get("buy_name") or "",
        created_by=user_id,
        supplier_name=context.user_data.get("buy_supplier") or "",
        invoice_number=context.user_data.get("buy_invoice") or "",
        invoice_date=parsed,
        photo_file_id=context.user_data.get("buy_photo_file_id") or "",
    )
    context.user_data.clear()
    if purchase_id is None:
        await render(
            update,
            "Не удалось создать закупку.\n\n" + _home(update)[0],
            _home(update)[1],
            as_new=True,
        )
        return ConversationHandler.END
    await render_purchase_card(update, purchase_id, as_new=True)
    return ConversationHandler.END


async def buy_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    purchase_id = context.user_data.get("buy_id")
    field = context.user_data.get("buy_field")
    raw = _non_empty(update.message.text if update.message else None)
    if purchase_id is None or field not in BUY_FIELD_PROMPTS:
        await render(update, *_home(update), as_new=True)
        return ConversationHandler.END
    ok = storage.update_purchase_field(purchase_id, field, raw)
    if not ok:
        await render(
            update,
            *_ask(context, BUY_FIELD_PROMPTS[field]),
            as_new=True,
        )
        return BUY_EDIT
    context.user_data.clear()
    await render_purchase_card(update, purchase_id, as_new=True)
    return ConversationHandler.END


async def req_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = storage.normalize_stock_text(
        update.message.text if update.message else None
    )
    if not description:
        await render(
            update,
            *_ask(context, "Опишите, что нужно закупить:"),
            as_new=True,
        )
        return REQ_DESC
    if len(description) > storage.MAX_REQUEST_DESC:
        await render(
            update,
            *_ask(
                context,
                f"Слишком длинно (макс. {storage.MAX_REQUEST_DESC}). "
                "Опишите короче:",
            ),
            as_new=True,
        )
        return REQ_DESC
    user_id = _viewer_id(update)
    if user_id is None:
        return ConversationHandler.END
    item = storage.create_purchase_request(description, user_id)
    context.user_data.clear()
    if item is None:
        await render(update, *_home(update), as_new=True)
        return ConversationHandler.END
    await notify_purchasers(context, item, created=True, except_id=user_id)
    await render_screen(
        update,
        screens.request_card(
            item["id"],
            as_purchaser=False,
            viewer_id=user_id,
        ),
        as_new=True,
    )
    return ConversationHandler.END


@need_user
async def open_by_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = storage.normalize_stock_text(update.message.text if update.message else None)
    if not text:
        return
    if _is_purchaser(update):
        if text.isdigit():
            purchase_id = storage.parse_purchase_id(text)
            if purchase_id is None:
                await update.message.reply_text(
                    f"id должен быть числом от 1 до {storage.MAX_PELENGATOR_ID}.",
                )
                return
            item = storage.get_purchase(purchase_id)
            if item is None:
                await update.message.reply_text(
                    f"Закупка <code>#{purchase_id}</code> не найдена.",
                    parse_mode=ParseMode.HTML,
                )
                return
            await render_purchase_card(update, purchase_id, as_new=True)
            return
        if not any(ch.isalpha() for ch in text):
            return
        matches = storage.best_purchase_matches(text)
        if not matches:
            await update.message.reply_text("Ничего не нашлось.")
            return
        await render(
            update,
            *screens.purchase_search_screen(
                text,
                matches,
                _bot_username(context),
            ),
            as_new=True,
        )
        return
    if text.isdigit():
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
        return
    if not any(ch.isalpha() for ch in text):
        return
    match = storage.find_stock_item_by_name(text) or storage.best_stock_match(text)
    if match is None:
        await update.message.reply_text(
            f"Товар «{text}» не найден.",
        )
        return
    await render_stock_card(update, match["id"], as_new=True)


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


@need_user
async def start_logs_pels_filter(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if _is_purchaser(update):
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Недоступно для закупщика",
                    show_alert=True,
                )
            except BadRequest:
                pass
        await _show_logs(update, context)
        return ConversationHandler.END
    draft = _start_logs_draft(context)
    await render(update, *screens.logs_pels_filter_screen(draft))
    return LOGS_PEL_FILTER


async def logs_pel_filter_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    pel_id = storage.parse_pelengator_id(
        _non_empty(update.message.text if update.message else None)
    )
    draft = _logs_draft(context)
    if pel_id is None:
        await render(
            update,
            *screens.logs_pels_filter_screen(
                draft,
                note="Нужен номер пеленгатора, например <code>23</code>.",
            ),
            as_new=True,
        )
        return LOGS_PEL_FILTER
    ids = list(draft.get("pel_ids") or [])
    if pel_id not in ids:
        ids.append(pel_id)
    draft["pel_ids"] = ids
    await render(
        update,
        *screens.logs_pels_filter_screen(draft),
        as_new=True,
    )
    return LOGS_PEL_FILTER


@need_user
async def start_logs_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _logs_draft(context)
    context.user_data["cancel_back"] = "logs:time"
    await render(
        update,
        *_ask(
            context,
            "С какой даты?\n"
            "Например <code>13.10.2026</code> или <code>13.10.2026 07:00</code>",
        ),
    )
    return LOGS_TIME_FROM


async def logs_time_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = storage.parse_log_datetime(
        _non_empty(update.message.text if update.message else None)
    )
    if not parsed:
        await render(
            update,
            *_ask(
                context,
                "Не понял дату. Введите как <code>13.10.2026</code> "
                "или <code>13.10.2026 07:00</code>:",
            ),
            as_new=True,
        )
        return LOGS_TIME_FROM
    context.user_data["logs_time_from"] = parsed
    await render(
        update,
        *_ask(
            context,
            "По какую дату? (включительно)\n"
            "Например <code>13.10.2026</code> или слово <code>сейчас</code>",
        ),
        as_new=True,
    )
    return LOGS_TIME_TO


async def logs_time_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = _non_empty(update.message.text if update.message else None)
    if raw.casefold() in {"сейчас", "now"}:
        parsed = storage.now_iso()
    else:
        parsed = storage.parse_log_datetime(raw, end_of_day=True)
    if not parsed:
        await render(
            update,
            *_ask(
                context,
                "Не понял дату. Введите как <code>13.10.2026</code> "
                "или слово <code>сейчас</code>:",
            ),
            as_new=True,
        )
        return LOGS_TIME_TO
    started = str(context.user_data.get("logs_time_from") or "")
    if not started:
        return await start_logs_time(update, context)
    if parsed < started:
        started, parsed = parsed, started
    draft = _logs_draft(context)
    draft["time_preset"] = "custom"
    draft["time_from"] = started
    draft["time_to"] = parsed
    context.user_data.pop("logs_time_from", None)
    await render(
        update,
        *screens.logs_time_filter_screen(draft),
        as_new=True,
    )
    return ConversationHandler.END


def build_application() -> Application:
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if TELEGRAM_PROXY:
        builder = builder.proxy(TELEGRAM_PROXY).get_updates_proxy(TELEGRAM_PROXY)
        print(f"Используется прокси: {TELEGRAM_PROXY}")
    return builder.build()


def main() -> None:
    global _application
    storage.init_db()
    print(f"База данных: {storage.DB_PATH}")
    app = build_application()
    _application = app

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(start_add_type, pattern=r"^type:add(?:\:a)?$"),
            CallbackQueryHandler(start_edit_type_field, pattern=r"^type:f:"),
            CallbackQueryHandler(start_add_pelengator, pattern=r"^pel:a[ta]:"),
            CallbackQueryHandler(start_edit_pel_field, pattern=r"^pel:tx:"),
            CallbackQueryHandler(start_move_pelengator, pattern=r"^pel:mv:"),
            CallbackQueryHandler(start_pick_error_pelengator, pattern=r"^err:add:"),
            CallbackQueryHandler(start_add_error, pattern=r"^err:ds:"),
            CallbackQueryHandler(start_error_description, pattern=r"^err:np:"),
            CallbackQueryHandler(start_edit_error, pattern=r"^err:e:"),
            CallbackQueryHandler(start_edit_own_name, pattern=r"^me:name$"),
            CallbackQueryHandler(start_edit_own_email, pattern=r"^me:mail$"),
            CallbackQueryHandler(on_stock_callback, pattern=r"^stk:"),
            CallbackQueryHandler(start_logs_time, pattern=r"^logs:tc$"),
            CallbackQueryHandler(start_logs_pels_filter, pattern=r"^logs:fk:pels$"),
            CallbackQueryHandler(start_add_purchase, pattern=r"^buy:add$"),
            CallbackQueryHandler(start_purchase_photo, pattern=r"^buy:ph:"),
            CallbackQueryHandler(start_edit_purchase_field, pattern=r"^buy:e:"),
            CallbackQueryHandler(start_add_request, pattern=r"^req:add$"),
        ],
        states={
            USER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_reg_name)],
            USER_EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_edit_name)
            ],
            USER_EDIT_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_edit_email)
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
            STK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_name)],
            STK_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_qty)],
            STK_LOC: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_loc)],
            STK_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, stock_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stock_photo_wrong),
            ],
            LOGS_TIME_FROM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, logs_time_from)
            ],
            LOGS_TIME_TO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, logs_time_to)
            ],
            LOGS_PEL_FILTER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, logs_pel_filter_add)
            ],
            BUY_PHOTO: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    buy_photo,
                ),
                CallbackQueryHandler(on_buy_callback, pattern=r"^buy:noph$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_photo_wrong),
            ],
            BUY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_name)],
            BUY_SUPPLIER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_supplier)
            ],
            BUY_INVOICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_invoice)
            ],
            BUY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_date)],
            BUY_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_edit)],
            REQ_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, req_desc)],
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, open_by_message))
    app.add_error_handler(on_error)

    print("Бот запущен!")
    if not TELEGRAM_PROXY:
        print("Если нет связи с Telegram — включите VPN или задайте TELEGRAM_PROXY.")
    if not mail.configured():
        print("Почта не настроена: задайте MAIL_FROM и MAIL_PASSWORD.")
    try:
        app.run_polling(bootstrap_retries=-1)
    except (TimedOut, NetworkError) as error:
        print(
            "Нет связи с Telegram API. Включите VPN или укажите TELEGRAM_PROXY "
            f"в окружении. ({error})"
        )


if __name__ == "__main__":
    main()
