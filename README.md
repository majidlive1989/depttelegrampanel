# Debt Collector MVP — Telegram + FastAPI + React

یک MVP یکپارچه برای پیگیری مطالبات مشتری‌ها داخل گروه‌های تلگرام، با پنل فارسی RTL.

## معماری

- **Frontend:** React + Axios + Vite
- **Backend:** Python 3.12 + FastAPI
- **Database:** SQLite (WAL mode)
- **Telegram:** `python-telegram-bot` + JobQueue/APScheduler
- **Import:** XLSX با `openpyxl` و PDF متنی با `pypdf`
- **تقویم:** Jalali با `jdatetime`
- **Runtime:** یک Docker container؛ Node فقط در مرحله Build فرانت استفاده می‌شود.

## امکانات نسخه 0.2

- داشبورد تعداد بدهکاران و مجموع طلب
- آپلود XLSX/PDF و Preview قبل از ثبت
- Upsert مشتری بر اساس کد مشتری یا نام
- اتصال هر مشتری به یک گروه تلگرام با `/bind`
- محدودکردن `/bind` به Telegram Admin IDهای مشخص
- ارسال پیام وصول برای یک مشتری یا تمام مشتری‌های متصل
- جلوگیری از ارسال تکراری ناخواسته با cooldown
- فعال‌شدن Conversation فقط بعد از شروع پیگیری
- عدم دخالت ربات در چت‌های عادی گروه
- استخراج مبلغ از متن فارسی/انگلیسی
- نمایش تقویم شمسی Inline داخل Telegram
- جلوگیری از انتخاب تاریخ گذشته
- ثبت مبلغ + تاریخ شمسی و میلادی وعده
- Reminder خودکار برای وعده‌های سررسیدشده
- تغییر وضعیت وعده‌ها از پنل
- UI فارسی RTL و Responsive
- دیتابیس persistent روی Docker Volume

## اجرای سریع روی Docker Desktop ویندوز

1. Docker Desktop را اجرا کنید.
2. فایل `.env` را با Notepad باز کنید.
3. توکن BotFather را در این خط قرار دهید:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
```

4. برای امنیت، ابتدا در تلگرام به ربات پیام `/myid` بدهید و عدد نمایش‌داده‌شده را وارد کنید:

```env
TELEGRAM_ADMIN_IDS=123456789
```

برای چند ادمین:

```env
TELEGRAM_ADMIN_IDS=123456789,987654321
```

5. روی `start.bat` دابل‌کلیک کنید، یا در Terminal اجرا کنید:

```bash
docker compose up -d --build
```

6. پنل:

```text
http://localhost:8000
```

7. Swagger API:

```text
http://localhost:8000/docs
```

برای دیدن Logها `logs.bat` و برای خاموش‌کردن `stop.bat` را اجرا کنید.

## راه‌اندازی ربات تلگرام

1. ربات را از BotFather بسازید.
2. در BotFather بخش **Group Privacy / Privacy Mode** را خاموش کنید تا ربات بتواند پاسخ‌های اعضای گروه را دریافت کند.
3. ربات را به گروه مشتری اضافه کنید.
4. مشتری را ابتدا از Excel داخل پنل Import کنید.
5. ID مشتری در پنل نمایش داده می‌شود؛ مثلاً مشتری `#12`.
6. داخل گروه مشتری بزنید:

```text
/bind 12
```

7. در پنل روی **ارسال پیام** یا **شروع پیگیری** کلیک کنید.

از این لحظه فقط برای همان مشتری `collection_active` می‌شود و ربات جواب‌های مرتبط با وصول را پردازش می‌کند. اگر پیگیری فعال نباشد، پیام‌های عادی گروه را نادیده می‌گیرد.

## جریان واقعی کار

```text
Excel/PDF
   ↓
Preview در پنل
   ↓
ثبت/آپدیت بدهکاران
   ↓
اتصال هر مشتری به Telegram Group
   ↓
Start Follow-up
   ↓
ربات مبلغ دقیق را می‌خواهد
   ↓
مشتری: «50 میلیون تومان»
   ↓
ربات تقویم شمسی نمایش می‌دهد
   ↓
مشتری تاریخ دقیق را انتخاب می‌کند
   ↓
Promise ثبت می‌شود
   ↓
در سررسید، Reminder خودکار
```

## فرمت پیشنهادی Excel

ردیف اول Header باشد:

| کد مشتری | نام مشتری | بدهی |
|---|---|---:|
| C001 | شرکت پیشرو | 120000000 |
| C002 | بازرگانی امید | 85500000 |

ستون‌های انگلیسی `customer id`, `customer name`, `debt` هم پشتیبانی می‌شوند.

فایل `sample-debtors.xlsx` داخل پروژه برای تست آماده شده است.

## تنظیمات `.env`

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
APP_TIMEZONE=Asia/Tehran
FOLLOWUP_INTERVAL_SECONDS=60
SEND_COOLDOWN_MINUTES=30
DATA_DIR=/app/data
```

`SEND_COOLDOWN_MINUTES` مانع کلیک تصادفی و ارسال چند پیام پشت‌سرهم به یک مشتری می‌شود.

## اجرای Development بدون Docker

Backend:

```bash
cd backend
python -m venv .venv
# activate virtualenv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite درخواست‌های `/api` را به FastAPI روی پورت 8000 Proxy می‌کند.

## نکات مهم MVP

- SQLite برای اجرای تک‌کاربره/تیم کوچک و یک Worker مناسب است. اگر بعداً تعداد کاربران و عملیات همزمان زیاد شد، مهاجرت به PostgreSQL ساده است.
- `uvicorn --workers 1` را در این نسخه حفظ کنید؛ Bot Polling و Scheduler داخل همان Process اجرا می‌شوند.
- PDF فقط در صورتی قابل Parse است که متن واقعی داشته باشد. PDF اسکن‌شده/OCR شده در این نسخه ورودی اصلی نیست؛ Excel پیشنهاد می‌شود.
- پنل برای اجرای Local روی Docker Desktop طراحی شده و Login ندارد. قبل از Public Internet باید Authentication و HTTPS اضافه شود.
- وضعیت `paid` یک وعده را می‌بندد؛ مانده کل مشتری بهتر است از فایل حسابداری بعدی Update شود تا منبع حقیقت همان حسابداری بماند.

## تست‌هایی که روی سورس انجام شده

- Python syntax compile
- Import نمونه XLSX
- Upsert مشتری
- اتصال گروه در دیتابیس
- ایجاد Promise
- ثبت تاریخ Promise
- خاموش‌شدن Collection Session بعد از ثبت تاریخ

Build کامل npm/pip داخل محیط تولید فایل به اینترنت دسترسی نداشت؛ Docker Desktop شما dependencyها را در زمان `docker compose build` دریافت می‌کند.
