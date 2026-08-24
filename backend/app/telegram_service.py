import re
from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import repository as repo
from .config import (
    APP_TIMEZONE,
    FOLLOWUP_INTERVAL_SECONDS,
    SEND_COOLDOWN_MINUTES,
    TELEGRAM_ADMIN_IDS,
    TELEGRAM_BOT_TOKEN,
)

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PERSIAN_MONTHS = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
LOCAL_TZ = ZoneInfo(APP_TIMEZONE)


def normalize_digits(text):
    return (text or "").translate(PERSIAN_DIGITS)


def extract_amount(text):
    """Extract the most plausible toman amount from Persian/English text."""
    s = normalize_digits(text).replace("٬", ",")
    candidates = []
    pattern = re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(میلیون|هزار|تومان|ریال)?")
    for m in pattern.finditer(s):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        unit = m.group(2) or ""
        if unit == "میلیون":
            value *= 1_000_000
        elif unit == "هزار":
            value *= 1_000
        elif unit == "ریال":
            value /= 10
        if value >= 10_000:
            candidates.append(int(value))
    return max(candidates) if candidates else None


def _jalali_month_days(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    try:
        jdatetime.date(jy, 12, 30)
        return 30
    except ValueError:
        return 29


def month_keyboard(promise_id, jy=None, jm=None):
    local_today = datetime.now(LOCAL_TZ).date()
    today = jdatetime.date.fromgregorian(date=local_today)
    jy, jm = jy or today.year, jm or today.month
    title = f"{PERSIAN_MONTHS[jm]} {jy}"
    rows = [[
        InlineKeyboardButton("‹", callback_data=f"n:{promise_id}:{jy}:{jm}:-1"),
        InlineKeyboardButton(title, callback_data="noop"),
        InlineKeyboardButton("›", callback_data=f"n:{promise_id}:{jy}:{jm}:1"),
    ]]
    rows.append([InlineKeyboardButton(x, callback_data="noop") for x in ["ش", "ی", "د", "س", "چ", "پ", "ج"]])

    first_g = jdatetime.date(jy, jm, 1).togregorian()
    offset = (first_g.weekday() + 2) % 7  # Saturday-first calendar.
    cells = [None] * offset + list(range(1, _jalali_month_days(jy, jm) + 1))
    while len(cells) % 7:
        cells.append(None)
    for i in range(0, len(cells), 7):
        rows.append([
            InlineKeyboardButton(" ", callback_data="noop") if d is None
            else InlineKeyboardButton(str(d), callback_data=f"d:{promise_id}:{jy}:{jm}:{d}")
            for d in cells[i:i + 7]
        ])
    return InlineKeyboardMarkup(rows)


def shift_month(jy, jm, delta):
    jm += delta
    if jm < 1:
        return jy - 1, 12
    if jm > 12:
        return jy + 1, 1
    return jy, jm


def _is_admin(update: Update):
    if not TELEGRAM_ADMIN_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in TELEGRAM_ADMIN_IDS)


class TelegramService:
    def __init__(self):
        self.app = None
        self.enabled = bool(TELEGRAM_BOT_TOKEN)
        self.username = None

    async def start(self):
        if not self.enabled:
            return
        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("myid", self.cmd_myid))
        self.app.add_handler(CommandHandler("bind", self.cmd_bind))
        self.app.add_handler(CallbackQueryHandler(self.on_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))

        await self.app.initialize()
        me = await self.app.bot.get_me()
        self.username = me.username
        # Run reminder checks inside the official PTB JobQueue (APScheduler-backed).
        if self.app.job_queue:
            self.app.job_queue.run_repeating(
                self.check_due_promises,
                interval=FOLLOWUP_INTERVAL_SECONDS,
                first=10,
                name="due-promise-check",
            )
        await self.app.updater.start_polling(drop_pending_updates=True)
        await self.app.start()

    async def stop(self):
        if not self.app:
            return
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        if self.app.running:
            await self.app.stop()
        await self.app.shutdown()
        self.app = None

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.effective_message.reply_text(
            "ربات پیگیری مطالبات فعال است.\n"
            "برای دیدن شناسه تلگرام خودتان /myid را بزنید.\n"
            "برای اتصال گروه به مشتری، داخل همان گروه از /bind CUSTOMER_ID استفاده کنید."
        )

    async def cmd_myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else "نامشخص"
        await update.effective_message.reply_text(f"Telegram User ID: {uid}")

    async def cmd_bind(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ("group", "supergroup"):
            await update.effective_message.reply_text("این دستور را داخل گروه مشتری اجرا کنید.")
            return
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ شما اجازه اتصال گروه به مشتری را ندارید.")
            return
        if not context.args or not context.args[0].isdigit():
            await update.effective_message.reply_text("نمونه: /bind 12")
            return
        customer = repo.get_customer(int(context.args[0]))
        if not customer:
            await update.effective_message.reply_text("مشتری پیدا نشد.")
            return
        repo.bind_group(customer["id"], update.effective_chat.id, update.effective_chat.title or "")
        await update.effective_message.reply_text(f"✅ این گروه به «{customer['name']}» متصل شد.")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ("group", "supergroup"):
            return
        customer = repo.get_customer_by_chat(update.effective_chat.id)
        if not customer or not customer.get("collection_active"):
            return
        if not update.effective_message or not update.effective_message.text:
            return
        if update.effective_user and update.effective_user.is_bot:
            return

        text = update.effective_message.text.strip()
        repo.add_message(customer["id"], "in", text, update.effective_message.message_id)

        awaiting = repo.latest_awaiting_promise(customer["id"])
        if awaiting:
            await update.effective_message.reply_text(
                f"مبلغ {awaiting['amount']:,} تومان ثبت شده است. لطفاً تاریخ دقیق واریز را از تقویم انتخاب کنید 👇",
                reply_markup=month_keyboard(awaiting["id"]),
            )
            return

        amount = extract_amount(text)
        if not amount:
            await update.effective_message.reply_text(
                "ممنون. لطفاً مبلغ دقیق واریزی را به تومان اعلام کنید؛ مثال: 50,000,000 تومان"
            )
            return

        pid = repo.create_promise(customer["id"], amount, text)
        await update.effective_message.reply_text(
            f"مبلغ {amount:,} تومان ثبت شد. لطفاً تاریخ دقیق واریز را انتخاب کنید 👇",
            reply_markup=month_keyboard(pid),
        )

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        data = q.data or ""
        if data == "noop":
            await q.answer()
            return
        parts = data.split(":")
        if parts[0] == "n" and len(parts) == 5:
            _, pid, jy, jm, delta = parts
            jy, jm = shift_month(int(jy), int(jm), int(delta))
            await q.answer()
            await q.edit_message_reply_markup(reply_markup=month_keyboard(int(pid), jy, jm))
            return
        if parts[0] == "d" and len(parts) == 5:
            _, pid, jy, jm, jd = parts
            jy, jm, jd = int(jy), int(jm), int(jd)
            try:
                jdate = jdatetime.date(jy, jm, jd)
                gdate = jdate.togregorian()
            except Exception:
                await q.answer("تاریخ انتخاب‌شده معتبر نیست.", show_alert=True)
                return

            local_today = datetime.now(LOCAL_TZ).date()
            if gdate < local_today:
                await q.answer("تاریخ گذشته قابل انتخاب نیست.", show_alert=True)
                return

            promise = repo.set_promise_date(int(pid), gdate.isoformat(), f"{jy:04d}/{jm:02d}/{jd:02d}")
            if not promise:
                await q.answer("این وعده دیگر در سیستم وجود ندارد.", show_alert=True)
                return
            await q.answer("وعده ثبت شد ✅")
            await q.edit_message_text(
                f"✅ وعده پرداخت ثبت شد\n"
                f"مبلغ: {promise['amount']:,} تومان\n"
                f"تاریخ واریز: {promise['due_date_jalali']}"
            )

    async def send_collection_message(self, customer_id, force=False):
        customer = repo.get_customer(customer_id)
        if not self.app or not customer or not customer.get("telegram_chat_id"):
            raise RuntimeError("ربات فعال نیست یا گروه تلگرام مشتری متصل نشده است.")
        if customer["debt_amount"] <= 0:
            raise RuntimeError("مانده حساب این مشتری صفر است.")
        if not force and repo.recent_contact_within(customer_id, SEND_COOLDOWN_MINUTES):
            raise RuntimeError(f"برای جلوگیری از پیام تکراری، تا {SEND_COOLDOWN_MINUTES} دقیقه امکان ارسال مجدد نیست.")

        body = (
            "سلام وقت بخیر 🌷\n"
            f"طبق حساب ما مانده حساب «{customer['name']}» مبلغ {customer['debt_amount']:,} تومان است.\n"
            "لطفاً مبلغی که واریز می‌کنید را دقیق اعلام بفرمایید. "
            "پس از ثبت مبلغ، تاریخ دقیق واریز را از تقویم انتخاب کنید."
        )
        msg = await self.app.bot.send_message(chat_id=customer["telegram_chat_id"], text=body)
        repo.add_message(customer_id, "out", body, msg.message_id)
        repo.set_collection_active(customer_id, True)
        return True

    async def check_due_promises(self, context: ContextTypes.DEFAULT_TYPE):
        today_iso = datetime.now(LOCAL_TZ).date().isoformat()
        for p in repo.due_promises(today_iso):
            try:
                body = (
                    "یادآوری محترمانه 🌷\n"
                    f"وعده واریز مبلغ {p['amount']:,} تومان برای {p['due_date_jalali']} ثبت شده بود.\n"
                    "لطفاً وضعیت واریز را اعلام بفرمایید."
                )
                msg = await context.bot.send_message(chat_id=p["telegram_chat_id"], text=body)
                repo.add_message(p["customer_id"], "out", body, msg.message_id)
                repo.mark_promise_reminded(p["id"])
            except Exception as exc:
                print("reminder error:", p.get("id"), exc)

    def status(self):
        return {
            "enabled": self.enabled,
            "running": bool(self.app and self.app.running),
            "username": self.username,
            "admin_lock": bool(TELEGRAM_ADMIN_IDS),
            "admin_count": len(TELEGRAM_ADMIN_IDS),
        }


telegram_service = TelegramService()
