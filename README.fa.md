# AIOSSH

[English](README.md) · **فارسی (Persian)** · [العربية (Arabic)](README.ar.md)

AIOSSH یک کتابخانهٔ کلاینت SSH ناهمگام (async) برای پایتون است که روی
[`asyncssh`](https://asyncssh.readthedocs.io/) ساخته شده است. این کتابخانه یک
کلاینت سطح‌بالا با امکانات زیر ارائه می‌دهد: مدیریت استخر اتصال (connection
pool)، اعتبارسنجی ورودی، ذخیره‌سازی رمزنگاری‌شدهٔ اطلاعات ورود، تونل‌زنی SSH،
انتقال موازی و پرسرعت فایل، ضبط و بازپخش نشست، اجرای فرمان درون کانتینر داکر،
و کمک‌کننده‌های ارسال اعلان (webhook).

نسخهٔ فعلی: **۱.۱.۴**. برای تاریخچهٔ کامل تغییرات به [`CHANGELOG.md`](CHANGELOG.md)
مراجعه کنید.

---

## فهرست مطالب

- [پیش‌نیازها](#پیشنیازها)
- [نصب](#نصب)
- [شروع سریع](#شروع-سریع)
- [ساختار پروژه](#ساختار-پروژه)
- [قابلیت‌ها](#قابلیتها)
- [مرجع دستورات و API](#مرجع-دستورات-و-api)
- [مثال‌ها](#مثالها)
- [ملاحظات امنیتی](#ملاحظات-امنیتی)
- [تست](#تست)
- [توسعه](#توسعه)
- [مجوز](#مجوز)
- [سازنده](#سازنده)

---

## پیش‌نیازها

- پایتون ۳.۱۱ یا بالاتر
- چندسکویی: لینوکس، مک‌اواس و ویندوز

وابستگی‌های زمان اجرا (به‌طور خودکار نصب می‌شوند):

| بسته | کاربرد |
|---|---|
| `asyncssh` | اتصال‌های SSH/SFTP و تونل‌زنی |
| `cryptography` | ذخیره‌سازی رمزنگاری‌شدهٔ نشست با AES-256-GCM / PBKDF2 |
| `orjson` | سریال‌سازی سریع‌تر JSON در صورت وجود (در زمان اجرا اختیاری است: ماژول‌های `security/file_manager.py` و `integrations/replay.py` در صورت نبود `orjson` به ماژول استاندارد `json` برمی‌گردند) |

بستهٔ `aiohttp` فقط برای تحویل webhook لازم است و از طریق افزونهٔ اختیاری `web`
نصب می‌شود:

```bash
pip install "aiossh[web]"
```

بدون نصب `aiohttp`، متدهای `DiscordWebhook.send()`، `TelegramWebhook.send()`
و تحویل HTTP در `WebhookManager` مقدار `False` برمی‌گردانند یا نادیده گرفته
می‌شوند و استثنا پرتاب نمی‌کنند.

---

## نصب

```bash
pip install aiossh

# همراه با پشتیبانی webhook (دیسکورد/تلگرام/webhook عمومی HTTP)
pip install "aiossh[web]"

# نصب توسعه (لینت، بررسی نوع، تست)
pip install -e ".[dev]"
```

---

## شروع سریع

```python
import asyncio
from aiossh import AIOSSH

async def main():
    async with AIOSSH() as client:
        session = await client.connect("server.example.com", "admin", password="secret")
        result = await client.execute_command(session, "uptime")
        print(result["stdout"])

asyncio.run(main())
```

برای نسخهٔ کامل — شامل اجرای `sudo` و اجرای یک فرمان روی همهٔ نشست‌های فعال به‌طور
هم‌زمان — به [`examples/01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py)
مراجعه کنید.

---

## ساختار پروژه

```
aiossh-1.1.3/
├── src/aiossh/
│   ├── __init__.py             # سطح API عمومی (خروجی‌های با بارگذاری تنبل)
│   ├── core/                   # کلاینت اصلی، نشست و استخر
│   │   ├── __init__.py
│   │   ├── client.py           # AIOSSH: نمای سطح‌بالای کلاینت
│   │   ├── session.py          # FastSSHSession, SSHConfig
│   │   └── pool.py             # ConnectionPool, PoolConfig
│   ├── security/               # اعتبارسنجی، سیاست و ذخیرهٔ رمزنگاری‌شده
│   │   ├── __init__.py
│   │   ├── config.py           # SecurityConfig, RateLimiter, AuditLogger, SecureMemory, SecureChannel
│   │   ├── validators.py       # InputValidator (اعتبارسنجی لیست مجاز، بررسی SSRF/مسیر/فرمان)
│   │   └── file_manager.py     # SessionFileManager (ذخیرهٔ رمزنگاری‌شدهٔ نشست با AES-256-GCM)
│   ├── transfer/               # انتقال پرسرعت فایل
│   │   ├── __init__.py
│   │   └── scp.py              # ParallelSCP, TransferProgress
│   ├── integrations/           # یکپارچگی‌های اختیاری
│   │   ├── __init__.py
│   │   ├── proxy.py            # ProxyConfig, SSHTunnelManager, create_tunnel
│   │   ├── webhook.py          # WebhookManager, DiscordWebhook, TelegramWebhook
│   │   ├── docker.py           # DockerExecSession
│   │   └── replay.py           # SessionRecorder, SessionReplayer
│   ├── utils/                  # ابزارهای داخلی
│   │   ├── __init__.py
│   │   └── decorators.py       # retry, timing (بخشی از خروجی عمومی __all__ نیستند)
│   ├── exceptions.py           # سلسله‌مراتب استثناها
│   └── py.typed
│
├── examples/                # شش مثال قابل‌اجرا (پایین را ببینید)
├── tests/                   # مجموعهٔ تست آفلاین unittest (۲۲۸ تست، بدون نیاز به شبکه)
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

---

## قابلیت‌ها

- مدیریت ناهمگام اتصال SSH و اجرای فرمان، شامل اجرای `sudo`، اجرای دسته‌ای
  (موازی یا ترتیبی) و پخش خط‌به‌خط خروجی با محافظت زمانی (timeout).
- استخر اتصال با حداقل/حداکثر تعداد اتصال قابل‌تنظیم، استفادهٔ مجدد از
  اتصال‌های بی‌کار، پاک‌سازی دوره‌ای اتصال‌های کهنه یا منقضی، و محدودسازی نرخ
  اتصال در هر استخر.
- اعتبارسنجی ورودی مبتنی بر لیست مجاز برای میزبان، پورت، نام کاربری، رمز عبور،
  فرمان و مسیر — شامل محافظت SSRF (بازه‌های IP خصوصی/رزروشده به‌طور پیش‌فرض مسدود
  می‌شوند) و تشخیص پیمایش مسیر (path traversal).
- ذخیره‌سازی رمزنگاری‌شدهٔ اطلاعات ورود با AES-256-GCM و مشتق‌گیری کلید
  PBKDF2-HMAC-SHA512 (۶۰۰٬۰۰۰ تکرار) به‌همراه یک بررسی یکپارچگی مستقل
  HMAC-SHA512 روی فایل ذخیره‌شده.
- بارگذاری و دریافت فایل با SFTP، همراه با پشتیبانی اختیاری از ازسرگیری و بررسی
  بهترین‌تلاش فضای دیسک راه دور پیش از بارگذاری.
- انتقال پرسرعت فایل از طریق بارگذاری/دریافت موازی و تکه‌ای (`ParallelSCP`)،
  به‌همراه callback پیشرفت و محدودسازی اختیاری پهنای باند.
- پراکسی SOCKS5 و فورواردینگ پورت TCP محلی روی یک اتصال SSH برقرارشده.
- ضبط و بازپخش نشست، با فشرده‌سازی اختیاری gzip جریان رویدادهای ضبط‌شده.
- اجرای فرمان درون کانتینرهای داکر روی یک اتصال SSH موجود، به‌طوری‌که فرمان
  shell-escape شده و درون کانتینر با `sh -c` اجرا می‌شود.
- کمک‌کننده‌های اعلان webhook برای دیسکورد و تلگرام، به‌علاوهٔ یک رجیستری عمومی
  دیسپچ رویداد callback/webhook.
- سلسله‌مراتبی از بیش از ۲۵ نوع استثنای مشخص برای مدیریت دقیق خطا، که هرکدام یک
  `code` قابل‌خواندن توسط ماشین و `details` ساختاریافتهٔ اختیاری دارند.
- پشتیبانی چندسکویی (لینوکس، مک‌اواس، ویندوز) روی پایتون ۳.۱۱ به بالا.

---

## مرجع دستورات و API

همهٔ کلاس‌ها و توابع عمومی از بستهٔ سطح‌بالای `aiossh` بازصادر می‌شوند
(مثلاً `from aiossh import AIOSSH, ParallelSCP`) و در نخستین دسترسی به‌صورت تنبل
بارگذاری می‌شوند.

### کلاینت اصلی — `AIOSSH`

نقطهٔ ورود اصلی سطح‌بالا. ساخت نشست، استخر اتصال، محدودسازی نرخ و کمک‌کننده‌های
فایل نشست رمزنگاری‌شده را در بر می‌گیرد.

```python
AIOSSH(
    *,
    master_password: str | None = None,   # برای استفاده از save/load_session_*_file لازم است
    security_config: SecurityConfig | None = None,
    pool_config: PoolConfig | None = None,
    session_dir: str = "~/.aiossh/sessions",
    enable_audit: bool = True,
)
```

| متد | توضیح |
|---|---|
| `async connect(host, username, *, password=None, port=22, private_key_path=None, session_name=None, use_pool=True, timeout=30) -> FastSSHSession` | یک نشست SSH را اعتبارسنجی و باز می‌کند (یا از طریق استخر، مجدداً استفاده می‌کند). اگر `session_name` داده شود، نشست با آن نام برای بازیابی بعدی ردیابی می‌شود. |
| `async execute_command(session_id, command, *, timeout=30, sudo=False, **kwargs) -> dict` | یک فرمان را روی نشستی که با نام یا با خودِ شیء `FastSSHSession` ارجاع داده شده اجرا می‌کند. مشمول محدودیت نرخ سراسری فرمان (پیش‌فرض ۵۰ فرمان در ثانیه). |
| `async execute_on_all(command, **kwargs) -> dict[str, dict]` | یک فرمان را روی هر نشست فعال نام‌گذاری‌شده اجرا می‌کند؛ خطاهای هر نشست در نتیجه ثبت می‌شوند نه پرتاب. |
| `async close_session(session_id)` | یک نشست نام‌گذاری‌شده را می‌بندد (یا به استخر برمی‌گرداند). |
| `async close_all()` | همهٔ نشست‌های ردیابی‌شده را می‌بندد/آزاد می‌کند و استخر اتصال را خاموش می‌کند. هنگام خروج از `async with` به‌طور خودکار فراخوانی می‌شود. |
| `async save_session_to_file(session_name, host, username, password, port=22)` | اطلاعات ورود را در یک فایل نشست رمزنگاری‌شده ذخیره می‌کند. نیازمند `master_password` در زمان ساخت است. |
| `async load_session_from_file(session_name) -> FastSSHSession` | یک فایل نشست ذخیره‌شده را رمزگشایی و با اطلاعات آن متصل می‌شود. |
| `list_saved_sessions() -> list[str]` | نام نشست‌های موجود روی دیسک را فهرست می‌کند. |
| `list_active_sessions() -> list[dict]` | نشست‌های فعال حافظه را همراه با میزبان و وضعیت اتصال فهرست می‌کند. |

`AIOSSH` همچنین دو نمونهٔ داخلی `RateLimiter` اعمال می‌کند: تلاش‌های اتصال به ۳۰
مورد در هر ۶۰ ثانیه و اجرای فرمان به ۵۰ مورد در ثانیه محدود می‌شوند و در صورت
تجاوز، `AIOSSHRateLimitError` پرتاب می‌شود.

### نشست — `FastSSHSession`, `SSHConfig`

`SSHConfig` یک دیتاکلاس تغییرناپذیر (`frozen=True`) است که یک اتصال را توصیف
می‌کند:

```python
SSHConfig(
    host, username, port=22, password=None, private_key_path=None,
    timeout=30, keepalive_interval=30,
    security=SecurityConfig(), compression=True,
    host_key_callback=None, proxy=None,
)
```

`FastSSHSession` یک اتصال زندهٔ ساخته‌شده از یک `SSHConfig` را در بر می‌گیرد:

| متد / ویژگی | توضیح |
|---|---|
| `async connect()` | اتصال زیرین `asyncssh` را باز می‌کند. |
| `is_connected` (ویژگی) | اگر اتصال زنده و بازی وجود داشته باشد `True` است. |
| `connection` (ویژگی) | اتصال زیرین `asyncssh.SSHClientConnection` برای کاربردهای پیشرفته (مثلاً تونل‌زنی دستی). |
| `stats` (ویژگی) | دیکشنری تعداد فرمان‌های اجراشده، بایت‌های منتقل‌شده، خطاها، اتصال‌های مجدد، آپ‌تایم، میزبان و نام کاربری. |
| `async execute(command, *, timeout=30, sudo=False, allow_dangerous=False) -> dict` | یک فرمان را اجرا می‌کند؛ `stdout`، `stderr`، `exit_code`، `success`، `execution_time` و `truncated` را برمی‌گرداند. |
| `async execute_batch(commands, *, parallel=True, max_concurrent=5, **kwargs) -> list[dict]` | چند فرمان را به‌صورت موازی (محدود با `max_concurrent`) یا ترتیبی اجرا می‌کند؛ خطاهای هر فرمان در فهرست بازگشتی ثبت می‌شوند نه پرتاب. |
| `async upload_file(local_path, remote_path, *, check_disk_space=True) -> dict` | بارگذاری SFTP با بررسی اختیاری پیش‌ازپرواز فضای دیسک راه دور. |
| `async download_file(remote_path, local_path, *, resume=False) -> dict` | دریافت SFTP؛ با `resume=True` دریافت قطع‌شده را با پرش از بایت‌های موجود محلی ادامه می‌دهد. |
| `async stream_command(command, timeout=300) -> AsyncIterator[str]` | خروجی استاندارد را حین اجرا خط‌به‌خط و زیر یک timeout بازمی‌گرداند. |
| `async close()` | اتصال را می‌بندد؛ اگر بستن آرام ظرف ۵ ثانیه کامل نشود، به‌اجبار متوقف می‌کند. |

مدیریت‌کنندهٔ پیش‌فرض کلید میزبان همهٔ کلیدها را می‌پذیرد. پیش از استفاده در محیط
تولید، بخش [ملاحظات امنیتی](#ملاحظات-امنیتی) را ببینید.

### استخر اتصال — `ConnectionPool`, `PoolConfig`

```python
PoolConfig(
    max_connections: int = 10,
    min_connections: int = 2,
    max_idle_time: int = 300,     # ثانیه
    cleanup_interval: int = 60,   # ثانیه
    max_lifetime: int = 3600,     # ثانیه
)
```

| متد | توضیح |
|---|---|
| `async start()` | وظیفهٔ پس‌زمینهٔ پاک‌سازی را آغاز می‌کند. |
| `async ensure_min_connections(sample_config=None)` | گرم‌کردن بهترین‌تلاش تا `min_connections` اتصال بی‌کار برای پیکربندی داده‌شده. |
| `async get_connection(config) -> FastSSHSession` | اگر اتصالی بی‌کار و سالم موجود باشد آن را برمی‌گرداند، در غیر این صورت اتصال جدیدی باز می‌کند (مشمول `max_connections`). در صورت پُر بودن استخر `AIOSSHPoolExhaustedError` پرتاب می‌کند. |
| `async return_connection(config, connection)` | اتصالی را به استخر بی‌کار برمی‌گرداند یا در صورت ناسالم بودن آن را می‌بندد. |
| `async close()` | وظیفهٔ پاک‌سازی را متوقف و همهٔ اتصال‌های استخر را می‌بندد. |
| `stats` (ویژگی) | دیکشنری شمارش اتصال‌های کل/بی‌کار/در حال استفاده، محدودیت‌های پیکربندی‌شده و نرخ فعلی اتصال. |

اتصال‌ها بر اساس `username@host:port` استخر می‌شوند. اتصال‌های بی‌کار فراتر از
`max_idle_time` یا هر اتصال فراتر از `max_lifetime` توسط وظیفهٔ پاک‌سازی دوره‌ای
بسته می‌شوند.

### اعتبارسنجی ورودی — `InputValidator`

متدهای استاتیک/کلاسی؛ همه به‌جای پاک‌سازی خاموش، در ورودی نامعتبر
`AIOSSHInvalidParameterError` یا `AIOSSHSecurityError` پرتاب می‌کنند.

| متد | توضیح |
|---|---|
| `validate_host(host, *, allow_private=False) -> str` | یک نام میزبان یا IP را اعتبارسنجی می‌کند؛ بازه‌های خصوصی/رزروشدهٔ IPv4 و IPv6 را مگر با `allow_private=True` رد می‌کند. |
| `validate_port(port) -> int` | بررسی می‌کند که پورت یک عدد صحیح در بازهٔ ۱ تا ۶۵۵۳۵ باشد و آن را به‌صورت `int` برمی‌گرداند. |
| `validate_username(username) -> str` | در برابر یک الگوی نام کاربری سبک POSIX اعتبارسنجی می‌کند. |
| `validate_password(password) -> str` | رمز خالی، رمز بیش از ۱۲۸ کاراکتر و بایت null را رد می‌کند. |
| `validate_command(command, *, allow_dangerous=False) -> str` | فرمان‌های بیش از ۸۱۹۲ کاراکتر، بایت null، مجموعه‌ای ثابت از الگوهای مخرب شل (مثل `rm -rf /`، fork bomb) و نشانگرهای رایج تزریق (`` $( ``، `` ` ``، `/dev/tcp` و…) را مگر با `allow_dangerous=True` رد می‌کند. |
| `validate_path(path) -> str` | مسیرهای بیش از ۴۰۹۶ کاراکتر، بایت null و هر بخش مسیر `..` را رد می‌کند. `~` را بسط می‌دهد اما مسیر را در برابر فایل‌سیستم محلی resolve نمی‌کند (مسیرها ممکن است راه دور باشند). |
| `validate_session_name(name) -> str` | نام نشست را به `[a-zA-Z0-9_-]`، ۱ تا ۶۴ کاراکتر و بدون جداکنندهٔ مسیر محدود می‌کند. |
| `sanitize_string(value, max_length=256) -> str` | بایت null و فاصله‌ها را حذف و به `max_length` کوتاه می‌کند. |
| `shell_escape(argument) -> str` | پوششی بر `shlex.quote()` برای ساخت آرگومان‌های امنِ شل. |

### ذخیرهٔ رمزنگاری‌شدهٔ نشست — `SessionFileManager`

```python
SessionFileManager(session_dir: str = "~/.aiossh/sessions")
```

اطلاعات ورود را به‌صورت فایل‌های `<name>.seshn` (حالت `0600`، حالت دایرکتوری
`0700`) رمزنگاری‌شده با AES-256-GCM ذخیره می‌کند. کلید رمزنگاری از رمز اصلی با
PBKDF2-HMAC-SHA512 (۶۰۰٬۰۰۰ تکرار، نمک تصادفی ۳۲ بایتی) مشتق می‌شود و پیش از
تلاش برای رمزگشایی، یک HMAC-SHA512 مستقل روی `salt + nonce + ciphertext`
تأیید می‌گردد.

| متد | توضیح |
|---|---|
| `create_session_file(filename, credentials, master_password) -> Path` | `credentials` (یک دیکشنری) را رمزنگاری و به‌صورت اتمیک روی دیسک می‌نویسد (نوشتن در فایل موقت، سپس تغییر نام). |
| `load_session_file(filename, master_password) -> dict` | HMAC را تأیید، سپس رمزگشایی می‌کند و اطلاعات ذخیره‌شده را برمی‌گرداند. در صورت دستکاری `AIOSSHIntegrityError` و در صورت خرابی فایل `AIOSSHSessionCorruptedError` پرتاب می‌کند. |
| `list_sessions() -> list[str]` | نام نشست‌های ذخیره‌شده را فهرست می‌کند. |
| `delete_session(filename) -> bool` | در صورت وجود، فایل نشست ذخیره‌شده را حذف می‌کند. |

### ابزارهای امنیتی

- **`SecurityConfig`** — دیتاکلاسی که رمزها (ciphers)، الگوریتم‌های تبادل کلید و
  MACهای مجاز هنگام باز کردن اتصال را فهرست می‌کند. پیش‌فرض آن مجموعه‌ای مدرن و
  با اولویت AEAD است (مثلاً `aes256-gcm@openssh.com`، `curve25519-sha256`،
  `hmac-sha2-256-etm@openssh.com`).
- **`RateLimiter(max_requests, window_seconds)`** — محدودکنندهٔ نرخ ناهمگام با
  پنجرهٔ لغزان، دارای `await acquire() -> bool` و ویژگی `current_rate`. به‌صورت
  داخلی توسط `AIOSSH` و `ConnectionPool` استفاده می‌شود و می‌توان مستقیم هم از
  آن بهره برد.
- **`AuditLogger`** — متد `async log(event, data=None)` را ارائه می‌دهد. پیاده‌سازی
  پیش‌فرض بی‌اثر (no-op) است؛ به‌صورت داخلی برای علامت‌گذاری رویدادهای
  `session_connect` / `session_close` استفاده می‌شود و برای یکپارچگی با یک سامانهٔ
  لاگ/ممیزی بیرونی طراحی شده تا زیرکلاس یا جایگزین شود.
- **`SecureMemory`** — `secure_clear(buffer: bytearray)` یک بافر را با بایت‌های
  تصادفی بازنویسی می‌کند؛ `secure_compare(a, b)` مقایسهٔ بایتیِ زمان‌ثابت با
  `hmac.compare_digest` انجام می‌دهد.
- **`SecureChannel`** — برای قابلیت کانال امن در آینده رزرو شده است. برای سازگاری
  رو‌به‌جلو در API عمومی حضور دارد اما فعلاً رفتاری ندارد.

### تونل‌زنی SSH — `ProxyConfig`, `SSHTunnelManager`, `create_tunnel`

```python
ProxyConfig(
    socks_port: int = 1080,
    local_forwards: list[tuple[int, str, int]] = [],  # (local_port, remote_host, remote_port)
    remote_forwards: list[tuple[int, str, int]] = [],
    enable_socks: bool = True,
)
```

| متد | توضیح |
|---|---|
| `SSHTunnelManager(connection).start_socks_proxy(port=1080, host="127.0.0.1")` | یک پراکسی محلی SOCKS5 تونل‌شده از طریق اتصال SSH را آغاز می‌کند. |
| `SSHTunnelManager(connection).add_local_forward(local_port, remote_host, remote_port)` | یک پورت TCP محلی را به میزبان/پورت قابل‌دسترس از سرور راه دور فوروارد می‌کند. |
| `SSHTunnelManager(connection).close_all()` | همهٔ شنونده‌های بازشده توسط مدیر را می‌بندد. |
| `create_tunnel(connection, config=None)` | مدیر زمینهٔ ناهمگام که پراکسی SOCKS (در صورت `enable_socks`) و همهٔ ورودی‌های `local_forwards` را از یک `ProxyConfig` آغاز و هنگام خروج جمع می‌کند. |

`ProxyConfig.remote_forwards` برای سازگاری رو‌به‌جلو حضور دارد اما در این نسخه
هنوز توسط `create_tunnel()` یا `SSHTunnelManager` مصرف نمی‌شود — فعلاً فقط
پراکسی SOCKS5 و فورواردینگ پورت محلی پیاده‌سازی شده‌اند.

### اعلان‌های Webhook — `WebhookManager`, `DiscordWebhook`, `TelegramWebhook`

`DiscordWebhook(webhook_url)` و `TelegramWebhook(bot_token, chat_id)` هرکدام
`async send(message, ...) -> bool` را ارائه می‌دهند و می‌توان مستقل از بقیهٔ
کتابخانه از آن‌ها استفاده کرد، همان‌طور که در
[`examples/05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py)
نشان داده شده است.

`WebhookManager` یک رجیستری رویداد عمومی با چهار رویداد نام‌گذاری‌شده است:
`on_connect`، `on_disconnect`، `on_command_complete`، `on_error`.

| متد | توضیح |
|---|---|
| `on(event, callback)` | یک callback محلی (همگام یا ناهمگام) را برای یک رویداد ثبت می‌کند. |
| `add_webhook(event, url)` | یک نقطهٔ پایانی HTTP را برای دریافت یک POST از نوع JSON هنگام وقوع رویداد ثبت می‌کند. |
| `async trigger(event, data)` | همهٔ callbackهای ثبت‌شده را فراخوانی و به همهٔ URLهای webhook ثبت‌شده برای `event` پست می‌کند. برای تحویل HTTP نیازمند `aiohttp` (افزونهٔ `web`) است؛ callbackهای محلی صرف‌نظر از آن اجرا می‌شوند. |

`WebhookManager.trigger()` به‌طور خودکار توسط `AIOSSH` یا `FastSSHSession`
فراخوانی نمی‌شود؛ برنامه مسئول فراخوانی آن در نقطهٔ مناسب است (مثلاً پس از یک
`connect()` موفق یا یک فرمان ناموفق).

### اجرای داکر — `DockerExecSession`

```python
DockerExecSession(ssh_session: FastSSHSession, container_name: str, sudo: bool = False)
```

| متد | توضیح |
|---|---|
| `async connect()` | پیش از اجازهٔ اجرای فرمان، در حال اجرا بودن کانتینر هدف را تأیید می‌کند (تطبیق نام دقیق با خروجی `docker ps`). |
| `async execute(command, timeout=30, workdir="/") -> dict` | فرمان را shell-escape و درون کانتینر با `docker exec ... sh -c '<command>'` اجرا می‌کند، تا فرمان‌های مرکب (`&&`، `;`، `|`) یک‌بار و توسط شل کانتینر تفسیر شوند. |
| `is_connected` (ویژگی) | به نشست SSH زیرین واگذار می‌شود. |
| `async close()` | بی‌اثر (no-op)؛ چرخهٔ حیات اتصال متعلق به نشست SSH زیرین است. |

### ضبط و بازپخش نشست — `SessionRecorder`, `SessionReplayer`

`SessionRecorder(session_id, storage_dir="~/.aiossh/recordings")` یک جریان رویداد
زمان‌دار (`session_start`، `command`، `result`، `session_end`) را در یک فایل
`.iossh` (یا `.iossh.gz` در حالت فشرده) ضبط می‌کند.

| متد | توضیح |
|---|---|
| `start()` | ضبط را آغاز می‌کند. |
| `record_command(command)` | یک رویداد فرمان ثبت می‌کند. |
| `record_result(result)` | یک رویداد نتیجه ثبت می‌کند. |
| `stop()` | ضبط را پایان می‌دهد. |
| `async save(compress=True) -> str` | ضبط را روی دیسک می‌نویسد (پیش‌فرض فشرده با gzip) و مسیر فایل را برمی‌گرداند. |

`SessionReplayer(filepath)` یک ضبط را بارگذاری و با زمان‌بندی نسبی اصلی بازپخش
می‌کند.

| متد | توضیح |
|---|---|
| `async load()` | ضبط را می‌خواند و (در صورت لزوم) از فشرده خارج می‌کند. |
| `async replay(speed=1.0, callback=None)` | رویدادها را بازپخش می‌کند و بین آن‌ها بر اساس زمان اصلی تقسیم بر `speed` مکث می‌کند؛ برای هر رویداد `callback(event_type, data)` را فرا می‌خواند. |
| `get_summary() -> dict` | تعداد کل رویدادها، تعداد فرمان‌ها و فهرست فرمان‌های اجراشده را برمی‌گرداند. |

### انتقال موازی پرسرعت — `ParallelSCP`, `TransferProgress`

```python
ParallelSCP(session: FastSSHSession, chunk_size: int = 8 * 1024 * 1024, max_parallel: int = 4)
```

| متد | توضیح |
|---|---|
| `on_progress(callback)` | یک callback ثبت می‌کند که حین پیشرفت انتقال با یک نمونهٔ `TransferProgress` فراخوانی می‌شود. |
| `async upload(local_path, remote_path, *, max_speed_mbps=0) -> dict` | فایل محلی را به تکه‌ها می‌شکند، آن‌ها را هم‌زمان (محدود با `max_parallel`) بارگذاری و در راه دور با `cat` بازسازی می‌کند. برای فایل‌های کوچک‌تر از `chunk_size` به یک فراخوانی `upload_file()` برمی‌گردد. `max_speed_mbps=0` یعنی بدون محدودیت. |
| `async download(remote_path, local_path, *, max_speed_mbps=0) -> dict` | فایل راه دور را با ابزار `split` راه دور می‌شکند (ابتدا در دسترس بودن آن بررسی می‌شود؛ در نبود، به دریافت ساده برمی‌گردد) و تکه‌ها را هم‌زمان دریافت می‌کند. پیش از پاک‌سازی تکه‌های راه دور، اندازهٔ فایل بازسازی‌شده را تأیید می‌کند؛ اگر هر تکه‌ای شکست بخورد یا اندازهٔ نهایی مطابقت نداشته باشد `AIOSSHFileDownloadError` پرتاب می‌کند. |

`TransferProgress` یک دیتاکلاس با فیلدهای `total_bytes`، `transferred`،
`speed_mbps`، `eta_seconds` و `complete` است.

### استثناها

همهٔ استثناها از `AIOSSHException` مشتق می‌شوند که `message`، `code` (رشتهٔ
قابل‌خواندن توسط ماشین)، `details` (یک دیکشنری)، `cause` (استثنای اصلی در صورت
وجود) و `timestamp` را در بر دارد.

| دسته | استثناها |
|---|---|
| اتصال | `AIOSSHConnectionError`, `AIOSSHConnectionTimeoutError`, `AIOSSHConnectionRefusedError`, `AIOSSHHostKeyVerificationError` |
| احراز هویت | `AIOSSHAuthenticationError`, `AIOSSHInvalidCredentialsError` |
| نشست | `AIOSSHSessionError`, `AIOSSHSessionExpiredError`, `AIOSSHSessionNotFoundError`, `AIOSSHSessionCorruptedError` |
| اجرای فرمان | `AIOSSHCommandError`, `AIOSSHCommandTimeoutError` (هر دو آرگومان کلیدی `command` را می‌پذیرند) |
| انتقال فایل | `AIOSSHFileTransferError`, `AIOSSHFileTransferNotFoundError`, `AIOSSHFileUploadError`, `AIOSSHFileDownloadError`, `AIOSSHFileDiskFullError` |
| امنیت / اعتبارسنجی | `AIOSSHSecurityError`, `AIOSSHIntegrityError`, `AIOSSHEncryptionError`, `AIOSSHValidationError`, `AIOSSHInvalidParameterError` |
| محدودیت منابع | `AIOSSHRateLimitError`, `AIOSSHPoolExhaustedError` |
| پیکربندی / سایر | `AIOSSHConfigurationError`, `AIOSSHProxyError`, `AIOSSHPluginError` (رزروشده؛ فعلاً توسط کتابخانه پرتاب نمی‌شود) |

### دکوریتورهای کمکی — `aiossh.decorators`

بخشی از API عمومی سطح‌بالای `aiossh` نیستند؛ صریحاً از زیرماژول import کنید:

```python
from aiossh.decorators import retry, timing
```

| دکوریتور | توضیح |
|---|---|
| `retry(max_retries=3, exceptions=(Exception,))` | یک تابع ناهمگام را می‌پیچد؛ روی نوع‌های استثنای داده‌شده با تأخیر خطی‌افزایشی (`0.5s * attempt`) دوباره تلاش می‌کند و پس از `max_retries` تلاش، آخرین استثنا را دوباره پرتاب می‌کند. |
| `timing` | یک تابع ناهمگام را می‌پیچد؛ پس از هر فراخوانی زمان اجرای آن را در stdout چاپ می‌کند. |

---

## مثال‌ها

همهٔ مثال‌ها در [`examples/`](examples/) قرار دارند و پس از ویرایش جزئیات اتصال
در بالای هر فایل، آمادهٔ اجرا روی یک میزبان واقعی هستند.

| # | فایل | نمایش می‌دهد |
|---|---|---|
| ۱ | [`01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py) | اتصال، اجرای فرمان، اجرای `sudo` و `execute_on_all` |
| ۲ | [`02_high_speed_parallel_transfer.py`](examples/02_high_speed_parallel_transfer.py) | بارگذاری/دریافت با `ParallelSCP` همراه با گزارش زندهٔ پیشرفت |
| ۳ | [`03_ssh_tunneling_socks5_and_port_forward.py`](examples/03_ssh_tunneling_socks5_and_port_forward.py) | پراکسی SOCKS5 و فورواردینگ پورت محلی از طریق یک میزبان واسط |
| ۴ | [`04_session_recording_and_replay.py`](examples/04_session_recording_and_replay.py) | ضبط یک نشست و بازپخش آن |
| ۵ | [`05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py) | اجرای فرمان در کانتینر داکر و ارسال اعلان دیسکورد/تلگرام |
| ۶ | [`06_encrypted_session_storage.py`](examples/06_encrypted_session_storage.py) | ذخیره و بارگذاری اطلاعات ورود با `SessionFileManager` |

```bash
python examples/01_basic_connect_and_execute.py
```

---

## ملاحظات امنیتی

- مدیریت‌کنندهٔ پیش‌فرض کلید میزبان (`FastSSHSession._default_host_key_handler`)
  همهٔ کلیدهای میزبان را می‌پذیرد و در برابر حملات MITM محافظت نمی‌کند. پیش از
  استفاده در برابر شبکه‌های نامعتمد در محیط تولید، یک `host_key_callback` در
  `SSHConfig` تعیین کنید یا تأیید known-hosts در `asyncssh` را پیکربندی نمایید.
- در صورت امکان، کلیدهای خصوصی SSH را به احراز هویت با رمز عبور ترجیح دهید.
- بازه‌های IP خصوصی و رزروشده به‌طور پیش‌فرض توسط
  `InputValidator.validate_host()` مسدود می‌شوند (محافظت SSRF)؛ هنگام اتصال به
  شبکه‌های داخلی صریحاً `allow_private=True` بدهید.
- مجموعه‌ای ثابت از الگوهای مخرب فرمان و نشانگرهای رایج تزریق توسط
  `InputValidator.validate_command()` مگر با `allow_dangerous=True` رد می‌شوند؛
  این یک تدبیر دفاع‌در‌عمق است، نه جایگزینی برای اعتماد به منبع فرمان‌هایی که
  اجرا می‌کنید.
- هنگام استفاده از ذخیرهٔ رمزنگاری‌شدهٔ نشست، از یک رمز اصلی دست‌کم ۱۲ کاراکتری
  استفاده کنید (توسط `AIOSSH.__init__` اجباری است)؛ کلید مشتق‌شده هرگز روی دیسک
  نمی‌رود و پس از استفاده از حافظه پاک می‌شود.
- از `async with` / مدیر زمینه استفاده کنید تا نشست‌ها، استخرها و تونل‌ها همیشه —
  حتی در خطا — پاک‌سازی شوند.

---

## تست

دایرکتوری `tests/` یک مجموعهٔ خودبسندهٔ `unittest` (۲۲۸ تست) دارد که
`InputValidator`، `RateLimiter`، `ConnectionPool`، `FastSSHSession`،
`SessionFileManager` (با استفاده از بستهٔ واقعی `cryptography` برای AES-256-GCM /
PBKDF2) و تست‌های رگرسیون برای رفع command-injection در `DockerExecSession` و
رفع‌های `ParallelSCP` / `ConnectionPool` را پوشش می‌دهد. هیچ دسترسی شبکهٔ واقعی یا
بستهٔ واقعی `asyncssh` لازم نیست — یک `asyncssh` جعلی کمینه
(`tests/_fake_asyncssh/`) فقط نوع‌های استثنا و سطح اتصالی را که کتابخانه به آن
وابسته است فراهم می‌کند. این مجموعه بین `tests/test_all.py` (رفتار اصلی)،
`tests/test_deep_audit.py` (حالت‌های مرزی، هم‌زمانی، امنیت و رفتار وابسته به
سکو) و `tests/test_asyncssh_boundary.py` (سناریوهای رگرسیون که تضمین می‌کنند فقط
درخواست‌های اعتبارسنجی‌شده و آرگومان‌های کلیدی سازگار با asyncssh از مرز به
کتابخانهٔ زیرین `asyncssh` عبور می‌کنند) تقسیم شده است.

```bash
pip install cryptography
PYTHONPATH="src:tests/_fake_asyncssh:tests" python -m unittest tests.test_all tests.test_deep_audit tests.test_asyncssh_boundary tests.test_secure_memory -v
```

---

## توسعه

```bash
git clone https://github.com/bluedock/aiossh.git
cd aiossh
pip install -e ".[dev]"
ruff check .
mypy src/aiossh
```

---

## مجوز

مجوز MIT © ۲۰۲۶ bluedock. برای متن کامل به [`LICENSE`](LICENSE) مراجعه کنید.

---

## سازنده

AIOSSH را [**bluedock**](https://github.com/bluedock) ساخته و نگهداری می‌کند.
