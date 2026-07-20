# AIOSSH

[English](README.md) · [فارسی (Persian)](README.fa.md) · **العربية (Arabic)**

AIOSSH هي مكتبة عميل SSH غير متزامن (async) للغة Python، مبنية فوق
[`asyncssh`](https://asyncssh.readthedocs.io/). توفّر عميلًا رفيع المستوى
مزوّدًا بإدارة مجمّع الاتصالات (connection pool)، والتحقق من صحة المدخلات،
والتخزين المشفّر لبيانات الاعتماد، وأنفاق SSH، ونقل الملفات المتوازي عالي السرعة،
وتسجيل الجلسات وإعادة تشغيلها، وتنفيذ الأوامر داخل حاويات Docker، ومساعدات إشعارات
(webhook).

الإصدار الحالي: **١.١.٤**. للاطّلاع على سجل التغييرات الكامل راجع
[`CHANGELOG.md`](CHANGELOG.md).

---

## جدول المحتويات

- [المتطلبات](#المتطلبات)
- [التثبيت](#التثبيت)
- [بداية سريعة](#بداية-سريعة)
- [بنية المشروع](#بنية-المشروع)
- [الميزات](#الميزات)
- [مرجع الأوامر والـ API](#مرجع-الأوامر-وال-api)
- [أمثلة](#أمثلة)
- [اعتبارات أمنية](#اعتبارات-أمنية)
- [الاختبار](#الاختبار)
- [التطوير](#التطوير)
- [الرخصة](#الرخصة)
- [المنشئ](#المنشئ)

---

## المتطلبات

- Python 3.11 أو أحدث
- متعدد المنصّات: Linux و macOS و Windows

تبعيات وقت التشغيل (تُثبّت تلقائيًا):

| الحزمة | الغرض |
|---|---|
| `asyncssh` | اتصالات SSH/SFTP وإنشاء الأنفاق |
| `cryptography` | تخزين الجلسات المشفّر بـ AES-256-GCM / PBKDF2 |
| `orjson` | تسلسل JSON أسرع عند توفّره (اختياري في وقت التشغيل: تعود وحدتا `security/file_manager.py` و `integrations/replay.py` إلى وحدة `json` القياسية إذا لم يكن `orjson` مثبّتًا) |

تُطلب حزمة `aiohttp` فقط لتسليم إشعارات webhook، وتُثبّت عبر الإضافة
الاختيارية `web`:

```bash
pip install "aiossh[web]"
```

دون تثبيت `aiohttp`، تُرجِع دوال `DiscordWebhook.send()` و `TelegramWebhook.send()`
وتسليم HTTP في `WebhookManager` القيمة `False` أو تُتجاهَل دون إطلاق استثناء.

---

## التثبيت

```bash
pip install aiossh

# مع دعم webhook (Discord / Telegram / webhook HTTP عام)
pip install "aiossh[web]"

# تثبيت للتطوير (الفحص البرمجي، فحص الأنواع، الاختبارات)
pip install -e ".[dev]"
```

---

## بداية سريعة

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

للاطّلاع على نسخة أكثر اكتمالًا — تشمل تنفيذ `sudo` وتشغيل أمر واحد على جميع
الجلسات النشطة تزامنًا — راجع [`examples/01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py).

---

## بنية المشروع

```
aiossh-1.1.3/
├── src/aiossh/
│   ├── __init__.py             # واجهة API العامة (تصديرات بتحميل كسول)
│   ├── core/                   # العميل الأساسي والجلسة والتجميع
│   │   ├── __init__.py
│   │   ├── client.py           # AIOSSH: الواجهة رفيعة المستوى للعميل
│   │   ├── session.py          # FastSSHSession, SSHConfig
│   │   └── pool.py             # ConnectionPool, PoolConfig
│   ├── security/               # التحقق والسياسة والتخزين المشفّر
│   │   ├── __init__.py
│   │   ├── config.py           # SecurityConfig, RateLimiter, AuditLogger, SecureMemory, SecureChannel
│   │   ├── validators.py       # InputValidator (تحقق قائم على قائمة السماح، فحوص SSRF/المسار/الأمر)
│   │   └── file_manager.py     # SessionFileManager (تخزين جلسات مشفّر بـ AES-256-GCM)
│   ├── transfer/               # نقل ملفات عالي السرعة
│   │   ├── __init__.py
│   │   └── scp.py              # ParallelSCP, TransferProgress
│   ├── integrations/           # تكاملات اختيارية
│   │   ├── __init__.py
│   │   ├── proxy.py            # ProxyConfig, SSHTunnelManager, create_tunnel
│   │   ├── webhook.py          # WebhookManager, DiscordWebhook, TelegramWebhook
│   │   ├── docker.py           # DockerExecSession
│   │   └── replay.py           # SessionRecorder, SessionReplayer
│   ├── utils/                  # أدوات داخلية
│   │   ├── __init__.py
│   │   └── decorators.py       # retry, timing (ليست ضمن التصدير العام __all__)
│   ├── exceptions.py           # تسلسل الاستثناءات
│   └── py.typed
│
├── examples/                # ستة أمثلة قابلة للتشغيل (انظر أدناه)
├── tests/                   # مجموعة اختبارات unittest غير متصلة (٢٢٨ اختبارًا، دون شبكة)
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

---

## الميزات

- إدارة غير متزامنة لاتصال SSH وتنفيذ الأوامر، بما في ذلك تنفيذ `sudo`، والتنفيذ
  الدفعي (متوازٍ أو تسلسلي) وبث المخرجات سطرًا بسطر مع حماية زمنية (timeout).
- مجمّع اتصالات بحدّين أدنى/أقصى قابلين للضبط، وإعادة استخدام الاتصالات الخاملة،
  وتنظيف دوري للاتصالات القديمة أو منتهية الصلاحية، وتحديد معدل الاتصال لكل مجمّع.
- تحقق من المدخلات قائم على قائمة السماح للمضيف والمنفذ واسم المستخدم وكلمة المرور
  والأمر والمسار — يشمل حماية SSRF (تُحظر افتراضيًا نطاقات IP الخاصة/المحجوزة)
  واكتشاف اجتياز المسار (path traversal).
- تخزين مشفّر لبيانات الاعتماد بـ AES-256-GCM واشتقاق مفتاح PBKDF2-HMAC-SHA512
  (٦٠٠٬٠٠٠ تكرار) مع تحقق سلامة مستقل بـ HMAC-SHA512 على الملف المخزّن.
- رفع وتنزيل الملفات عبر SFTP، مع دعم اختياري للاستئناف وفحص أفضل-جهد لمساحة
  قرص الخادم البعيد قبل الرفع.
- نقل ملفات عالي السرعة عبر رفع/تنزيل متوازٍ ومجزّأ (`ParallelSCP`)، مع دالة رد (callback)
  للتقدّم وتحديد اختياري لعرض النطاق الترددي.
- وكيل SOCKS5 وإعادة توجيه منفذ TCP محلي عبر اتصال SSH قائم.
- تسجيل وإعادة تشغيل الجلسات، مع ضغط gzip اختياري لتدفّق الأحداث المسجّلة.
- تنفيذ الأوامر داخل حاويات Docker عبر اتصال SSH قائم، بحيث يُعزل الأمر (shell-escape)
  ويُنفّذ داخل الحاوية بـ `sh -c`.
- مساعدات إشعارات webhook لـ Discord و Telegram، إضافة إلى سجل أحداث عام يوزّع
  استدعاءات الرد/الـ webhook.
- تسلسل يضمّ أكثر من ٢٥ نوع استثناء محدد لمعالجة دقيقة للأخطاء، ولكل منها `code`
  قابل للقراءة آليًا و `details` مُهيكلة اختيارية.
- دعم متعدد المنصّات (Linux ، macOS ، Windows) على Python 3.11 فما فوق.

---

## مرجع الأوامر والـ API

تُصدّر جميع الفئات والدوال العامة من حزمة `aiossh` رفيعة المستوى
(مثلاً `from aiossh import AIOSSH, ParallelSCP`) وتُحمّل بكسل عند أول وصول.

### العميل الرئيسي — `AIOSSH`

نقطة الدخول الرئيسية رفيعة المستوى. تغلّف إنشاء الجلسات، ومجمّع الاتصالات،
وتحديد المعدل، ومساعدات ملفات الجلسات المشفّرة.

```python
AIOSSH(
    *,
    master_password: str | None = None,   # مطلوب لاستخدام save/load_session_*_file
    security_config: SecurityConfig | None = None,
    pool_config: PoolConfig | None = None,
    session_dir: str = "~/.aiossh/sessions",
    enable_audit: bool = True,
)
```

| الدالة | الوصف |
|---|---|
| `async connect(host, username, *, password=None, port=22, private_key_path=None, session_name=None, use_pool=True, timeout=30) -> FastSSHSession` | يتحقق من جلسة SSH ويفتحها (أو يعيد استخدامها من المجمّع). إذا أُعطي `session_name`، تُتعقّب الجلسة بذلك الاسم لاسترجاعها لاحقًا. |
| `async execute_command(session_id, command, *, timeout=30, sudo=False, **kwargs) -> dict` | ينفّذ أمرًا على جلسة مُشار إليها بالاسم أو بكائن `FastSSHSession` نفسه. يخضع لتحديد معدل أوامر عام (افتراضيًا ٥٠ أمرًا في الثانية). |
| `async execute_on_all(command, **kwargs) -> dict[str, dict]` | ينفّذ أمرًا على كل جلسة نشطة مسمّاة؛ تُسجّل أخطاء كل جلسة في النتيجة بدل إطلاقها. |
| `async close_session(session_id)` | يغلق جلسة مسمّاة (أو يعيدها إلى المجمّع). |
| `async close_all()` | يغلق/يحرّر جميع الجلسات المتعقّبة ويوقف مجمّع الاتصالات. يُستدعى تلقائيًا عند الخروج من `async with`. |
| `async save_session_to_file(session_name, host, username, password, port=22)` | يخزّن بيانات الاعتماد في ملف جلسة مشفّر. يتطلّب `master_password` عند الإنشاء. |
| `async load_session_from_file(session_name) -> FastSSHSession` | يفكّ تشفير ملف جلسة مخزّن ويتصل باستخدام بياناته. |
| `list_saved_sessions() -> list[str]` | يسرد أسماء الجلسات المتوفرة على القرص. |
| `list_active_sessions() -> list[dict]` | يسرد الجلسات النشطة في الذاكرة مع المضيف وحالة الاتصال. |

يُطبّق `AIOSSH` أيضًا محدّدي معدل (`RateLimiter`) داخليين: محاولات الاتصال
محدودة بـ ٣٠ في كل ٦٠ ثانية، وتنفيذ الأوامر محدود بـ ٥٠ في الثانية، ويُطلَق
`AIOSSHRateLimitError` عند التجاوز.

### الجلسة — `FastSSHSession`, `SSHConfig`

`SSHConfig` هي dataclass غير قابلة للتغيير (`frozen=True`) تصف اتصالًا:

```python
SSHConfig(
    host, username, port=22, password=None, private_key_path=None,
    timeout=30, keepalive_interval=30,
    security=SecurityConfig(), compression=True,
    host_key_callback=None, proxy=None,
)
```

يغلّف `FastSSHSession` اتصالًا حيًا مبنيًا من `SSHConfig`:

| الدالة / الخاصية | الوصف |
|---|---|
| `async connect()` | يفتح اتصال `asyncssh` الأساسي. |
| `is_connected` (خاصية) | `True` إذا وُجد اتصال حي ومفتوح. |
| `connection` (خاصية) | اتصال `asyncssh.SSHClientConnection` الأساسي للاستخدامات المتقدمة (مثل إنشاء الأنفاق يدويًا). |
| `stats` (خاصية) | قاموس يضم عدد الأوامر المنفّذة والبايتات المنقولة والأخطاء وإعادات الاتصال ووقت التشغيل والمضيف واسم المستخدم. |
| `async execute(command, *, timeout=30, sudo=False, allow_dangerous=False) -> dict` | ينفّذ أمرًا؛ يرجِع `stdout` و `stderr` و `exit_code` و `success` و `execution_time` و `truncated`. |
| `async execute_batch(commands, *, parallel=True, max_concurrent=5, **kwargs) -> list[dict]` | ينفّذ أوامر متعددة بالتوازي (محدودًا بـ `max_concurrent`) أو تسلسليًا؛ تُسجّل أخطاء الأوامر في القائمة المُرجعة بدل إطلاقها. |
| `async upload_file(local_path, remote_path, *, check_disk_space=True) -> dict` | رفع عبر SFTP مع فحص اختياري مسبق لمساحة قرص الخادم البعيد. |
| `async download_file(remote_path, local_path, *, resume=False) -> dict` | تنزيل عبر SFTP؛ مع `resume=True` يستأنف تنزيلًا مقطوعًا بتخطّي البايتات المحلية الموجودة. |
| `async stream_command(command, timeout=300) -> AsyncIterator[str]` | يبث المخرجات القياسية سطرًا بسطر أثناء التنفيذ تحت مهلة زمنية. |
| `async close()` | يغلق الاتصال؛ ويلجأ للإنهاء القسري إذا لم يكتمل الإغلاق اللطيف خلال ٥ ثوانٍ. |

معالج مفتاح المضيف الافتراضي يقبل جميع المفاتيح. راجع قسم
[اعتبارات أمنية](#اعتبارات-أمنية) قبل الاستخدام في الإنتاج.

### مجمّع الاتصالات — `ConnectionPool`, `PoolConfig`

```python
PoolConfig(
    max_connections: int = 10,
    min_connections: int = 2,
    max_idle_time: int = 300,     # ثانية
    cleanup_interval: int = 60,   # ثانية
    max_lifetime: int = 3600,     # ثانية
)
```

| الدالة | الوصف |
|---|---|
| `async start()` | يبدأ مهمة التنظيف الخلفية. |
| `async ensure_min_connections(sample_config=None)` | تسخين بأفضل جهد حتى `min_connections` اتصال خامل للتهيئة المُعطاة. |
| `async get_connection(config) -> FastSSHSession` | يرجِع اتصالًا خاملًا سليمًا إن وُجد، وإلا فتح اتصال جديد (خاضعًا لـ `max_connections`). يُطلق `AIOSSHPoolExhaustedError` إذا امتلأ المجمّع. |
| `async return_connection(config, connection)` | يعيد اتصالًا إلى المجمّع الخامل أو يغلقه إذا كان غير سليم. |
| `async close()` | يوقف مهمة التنظيف ويغلق جميع اتصالات المجمّع. |
| `stats` (خاصية) | قاموس يضم عدد الاتصالات الكلي/الخامل/قيد الاستخدام، والحدود المُهيأة، ومعدل الاتصال الحالي. |

تُجمّع الاتصالات حسب `username@host:port`. الاتصالات الخاملة التي تتجاوز
`max_idle_time`، أو أي اتصال يتجاوز `max_lifetime`، تُغلَق بواسطة مهمة التنظيف
الدورية.

### التحقق من المدخلات — `InputValidator`

دوال ساكنة/صنفية؛ جميعها تُطلق `AIOSSHInvalidParameterError` أو `AIOSSHSecurityError`
عند مدخل غير صالح بدلاً من التنظيف الصامت.

| الدالة | الوصف |
|---|---|
| `validate_host(host, *, allow_private=False) -> str` | يتحقق من اسم مضيف أو IP؛ يرفض نطاقات IPv4 و IPv6 الخاصة/المحجوزة إلا مع `allow_private=True`. |
| `validate_port(port) -> int` | يتحقق من أن المنفذ عدد صحيح بين ١ و ٦٥٥٣٥ ويرجعه كـ `int`. |
| `validate_username(username) -> str` | يتحقق مقابل نمط اسم مستخدم على نمط POSIX. |
| `validate_password(password) -> str` | يرفض كلمات المرور الفارغة، والتي تتجاوز ١٢٨ حرفًا، وبايت null. |
| `validate_command(command, *, allow_dangerous=False) -> str` | يرفض الأوامر التي تتجاوز ٨١٩٢ حرفًا، وبايت null، ومجموعة ثابتة من أنماط الأوامر المدمّرة (مثل `rm -rf /`، fork bomb) ومؤشرات الحقن الشائعة (`` $( ``، `` ` ``، `/dev/tcp`…) إلا مع `allow_dangerous=True`. |
| `validate_path(path) -> str` | يرفض المسارات التي تتجاوز ٤٠٩٦ حرفًا، وبايت null، وأي جزء مسار `..`. يوسّع `~` لكنه لا يحلّ المسار مقابل نظام الملفات المحلي (قد تكون المسارات بعيدة). |
| `validate_session_name(name) -> str` | يقيّد اسم الجلسة إلى `[a-zA-Z0-9_-]`، وطول ١ إلى ٦٤ حرفًا، دون فواصل مسار. |
| `sanitize_string(value, max_length=256) -> str` | يحذف بايت null والمسافات ويقتطع إلى `max_length`. |
| `shell_escape(argument) -> str` | غلاف حول `shlex.quote()` لبناء وسائط shell آمنة. |

### تخزين الجلسات المشفّر — `SessionFileManager`

```python
SessionFileManager(session_dir: str = "~/.aiossh/sessions")
```

يخزّن بيانات الاعتماد كملفات `<name>.seshn` (وضع `0600`، وضع الدليل
`0700`) مشفّرة بـ AES-256-GCM. يُشتق مفتاح التشفير من كلمة المرور الرئيسية بـ
PBKDF2-HMAC-SHA512 (٦٠٠٬٠٠٠ تكرار، ملح عشوائي ٣٢ بايت)، ويُتحقق من HMAC-SHA512
مستقل على `salt + nonce + ciphertext` قبل محاولة فك التشفير.

| الدالة | الوصف |
|---|---|
| `create_session_file(filename, credentials, master_password) -> Path` | يشفّر `credentials` (قاموس) ويكتبه بشكل ذري إلى القرص (كتابة إلى ملف مؤقت ثم إعادة تسمية). |
| `load_session_file(filename, master_password) -> dict` | يتحقق من HMAC ثم يفك التشفير ويرجِع البيانات المخزّنة. يُطلق `AIOSSHIntegrityError` عند العبث و `AIOSSHSessionCorruptedError` عند تلف الملف. |
| `list_sessions() -> list[str]` | يسرد أسماء الجلسات المخزّنة. |
| `delete_session(filename) -> bool` | يحذف ملف الجلسة المخزّن إن وُجد. |

### أدوات الأمان

- **`SecurityConfig`** — dataclass تسرد الشيفرات (ciphers) وخوارزميات تبادل المفاتيح
  وخوارزميات MAC المسموحة عند فتح الاتصال. الافتراض مجموعة حديثة تفضّل AEAD
  (مثل `aes256-gcm@openssh.com`، `curve25519-sha256`، `hmac-sha2-256-etm@openssh.com`).
- **`RateLimiter(max_requests, window_seconds)`** — محدّد معدل غير متزامن بنافذة
  منزلقة، يوفّر `await acquire() -> bool` والخاصية `current_rate`. يُستخدم داخليًا
  من `AIOSSH` و `ConnectionPool` ويمكن استخدامه مباشرة.
- **`AuditLogger`** — يوفّر `async log(event, data=None)`. التطبيق الافتراضي بلا
  أثر (no-op)؛ يُستخدم داخليًا لتعليم أحداث `session_connect` / `session_close`،
  ومُصمّم ليُورَث أو يُستبدل للتكامل مع نظام تدقيق/تسجيل خارجي.
- **`SecureMemory`** — `secure_clear(buffer: bytearray)` يعيد كتابة المخزّن المؤقت
  ببايتات عشوائية؛ `secure_compare(a, b)` مقارنة بايتية ثابتة الزمن عبر
  `hmac.compare_digest`.
- **`SecureChannel`** — محجوزة لقدرة قناة آمنة مستقبلًا. موجودة في الـ API العام
  للتوافق المستقبلي لكنها حاليًا بلا سلوك.

### أنفاق SSH — `ProxyConfig`, `SSHTunnelManager`, `create_tunnel`

```python
ProxyConfig(
    socks_port: int = 1080,
    local_forwards: list[tuple[int, str, int]] = [],  # (local_port, remote_host, remote_port)
    remote_forwards: list[tuple[int, str, int]] = [],
    enable_socks: bool = True,
)
```

| الدالة | الوصف |
|---|---|
| `SSHTunnelManager(connection).start_socks_proxy(port=1080, host="127.0.0.1")` | يبدأ وكيل SOCKS5 محلي مُنفقًا عبر اتصال SSH. |
| `SSHTunnelManager(connection).add_local_forward(local_port, remote_host, remote_port)` | يوجّه منفذ TCP محلي إلى مضيف/منفذ يمكن الوصول إليه من الخادم البعيد. |
| `SSHTunnelManager(connection).close_all()` | يغلق جميع المُنصِتات التي فتحها المدير. |
| `create_tunnel(connection, config=None)` | مدير سياق غير متزامن يبدأ وكيل SOCKS (إذا `enable_socks`) وجميع مدخلات `local_forwards` من `ProxyConfig` ثم ينظّفها عند الخروج. |

`ProxyConfig.remote_forwards` موجود للتوافق المستقبلي لكنه لا يُستهلَك بعد في
هذا الإصدار من قبل `create_tunnel()` أو `SSHTunnelManager` — المنفّذ حاليًا هو
وكيل SOCKS5 وإعادة توجيه المنفذ المحلي فقط.

### إشعارات Webhook — `WebhookManager`, `DiscordWebhook`, `TelegramWebhook`

يوفّر كل من `DiscordWebhook(webhook_url)` و `TelegramWebhook(bot_token, chat_id)`
الدالة `async send(message, ...) -> bool` ويمكن استخدامهما بمعزل عن بقية
المكتبة، كما هو موضّح في
[`examples/05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py).

`WebhookManager` هو سجل أحداث عام بأربعة أحداث مسمّاة:
`on_connect`، `on_disconnect`، `on_command_complete`، `on_error`.

| الدالة | الوصف |
|---|---|
| `on(event, callback)` | يسجّل دالة رد محلية (متزامنة أو غير متزامنة) لحدث. |
| `add_webhook(event, url)` | يسجّل نقطة نهاية HTTP تتلقّى POST من نوع JSON عند وقوع الحدث. |
| `async trigger(event, data)` | يستدعي جميع دوال الرد المسجّلة ويُرسل POST إلى جميع عناوين webhook المسجّلة لـ `event`. يتطلّب `aiohttp` (إضافة `web`) لتسليم HTTP؛ تُشغّل دوال الرد المحلية بغض النظر. |

لا يُستدعى `WebhookManager.trigger()` تلقائيًا من `AIOSSH` أو `FastSSHSession`؛
التطبيق مسؤول عن استدعائه في الموضع المناسب (مثلاً بعد `connect()` ناجح أو أمر
فاشل).

### تنفيذ Docker — `DockerExecSession`

```python
DockerExecSession(ssh_session: FastSSHSession, container_name: str, sudo: bool = False)
```

| الدالة | الوصف |
|---|---|
| `async connect()` | يتحقق من أن الحاوية الهدف قيد التشغيل قبل السماح بتنفيذ الأوامر (مطابقة اسم دقيقة مع مخرج `docker ps`). |
| `async execute(command, timeout=30, workdir="/") -> dict` | يعزل الأمر (shell-escape) وينفّذه داخل الحاوية بـ `docker exec ... sh -c '<command>'`، بحيث تُفسّر الأوامر المركّبة (`&&`، `;`، `|`) مرة واحدة داخل شيل الحاوية. |
| `is_connected` (خاصية) | تُفوّض إلى جلسة SSH الأساسية. |
| `async close()` | بلا أثر (no-op)؛ دورة حياة الاتصال مملوكة لجلسة SSH الأساسية. |

### تسجيل وإعادة تشغيل الجلسات — `SessionRecorder`, `SessionReplayer`

`SessionRecorder(session_id, storage_dir="~/.aiossh/recordings")` يسجّل تدفّق
أحداث موقّتة زمنيًا (`session_start`، `command`، `result`، `session_end`) في ملف
`.iossh` (أو `.iossh.gz` في وضع الضغط).

| الدالة | الوصف |
|---|---|
| `start()` | يبدأ التسجيل. |
| `record_command(command)` | يسجّل حدث أمر. |
| `record_result(result)` | يسجّل حدث نتيجة. |
| `stop()` | ينهي التسجيل. |
| `async save(compress=True) -> str` | يكتب التسجيل إلى القرص (مضغوط بـ gzip افتراضيًا) ويرجِع مسار الملف. |

`SessionReplayer(filepath)` يحمّل تسجيلًا ويعيد تشغيله بتوقيت نسبي أصلي.

| الدالة | الوصف |
|---|---|
| `async load()` | يقرأ التسجيل ويفك ضغطه إن لزم. |
| `async replay(speed=1.0, callback=None)` | يعيد تشغيل الأحداث ويتوقّف بينها وفقًا للتوقيت الأصلي مقسومًا على `speed`؛ يستدعي `callback(event_type, data)` لكل حدث. |
| `get_summary() -> dict` | يرجِع إجمالي الأحداث وعدد الأوامر وقائمة الأوامر المنفّذة. |

### النقل المتوازي عالي السرعة — `ParallelSCP`, `TransferProgress`

```python
ParallelSCP(session: FastSSHSession, chunk_size: int = 8 * 1024 * 1024, max_parallel: int = 4)
```

| الدالة | الوصف |
|---|---|
| `on_progress(callback)` | يسجّل دالة رد تُستدعى بكائن `TransferProgress` أثناء تقدّم النقل. |
| `async upload(local_path, remote_path, *, max_speed_mbps=0) -> dict` | يجزّئ الملف المحلي ويرفع الأجزاء تزامنًا (محدودًا بـ `max_parallel`) ثم يعيد بناءه بعيدًا بـ `cat`. يعود إلى استدعاء `upload_file()` واحد للملفات الأصغر من `chunk_size`. القيمة `max_speed_mbps=0` تعني بلا حد. |
| `async download(remote_path, local_path, *, max_speed_mbps=0) -> dict` | يجزّئ الملف البعيد بأداة `split` البعيدة (يفحص توفّرها أولاً؛ وإلا يعود إلى تنزيل بسيط) وينزّل الأجزاء تزامنًا. يتحقق من حجم الملف المُعاد بناؤه قبل إزالة الأجزاء البعيدة؛ ويُطلق `AIOSSHFileDownloadError` إذا فشل أي جزء أو لم يطابق الحجم النهائي. |

`TransferProgress` هي dataclass بالحقول `total_bytes`، `transferred`،
`speed_mbps`، `eta_seconds`، `complete`.

### الاستثناءات

ترث جميع الاستثناءات من `AIOSSHException` التي تضم `message`، `code` (سلسلة قابلة
للقراءة آليًا)، `details` (قاموس)، `cause` (الاستثناء الأصلي إن وُجد)، و `timestamp`.

| الفئة | الاستثناءات |
|---|---|
| الاتصال | `AIOSSHConnectionError`, `AIOSSHConnectionTimeoutError`, `AIOSSHConnectionRefusedError`, `AIOSSHHostKeyVerificationError` |
| المصادقة | `AIOSSHAuthenticationError`, `AIOSSHInvalidCredentialsError` |
| الجلسة | `AIOSSHSessionError`, `AIOSSHSessionExpiredError`, `AIOSSHSessionNotFoundError`, `AIOSSHSessionCorruptedError` |
| تنفيذ الأوامر | `AIOSSHCommandError`, `AIOSSHCommandTimeoutError` (كلاهما يقبل الوسيط `command`) |
| نقل الملفات | `AIOSSHFileTransferError`, `AIOSSHFileTransferNotFoundError`, `AIOSSHFileUploadError`, `AIOSSHFileDownloadError`, `AIOSSHFileDiskFullError` |
| الأمان / التحقق | `AIOSSHSecurityError`, `AIOSSHIntegrityError`, `AIOSSHEncryptionError`, `AIOSSHValidationError`, `AIOSSHInvalidParameterError` |
| حدود الموارد | `AIOSSHRateLimitError`, `AIOSSHPoolExhaustedError` |
| التهيئة / أخرى | `AIOSSHConfigurationError`, `AIOSSHProxyError`, `AIOSSHPluginError` (محجوز؛ لا تُطلقه المكتبة حاليًا) |

### المُزيّنات المساعدة — `aiossh.decorators`

ليست جزءًا من الـ API العام رفيع المستوى لـ `aiossh`؛ استوردها صراحةً من الوحدة الفرعية:

```python
from aiossh.decorators import retry, timing
```

| المُزيّن | الوصف |
|---|---|
| `retry(max_retries=3, exceptions=(Exception,))` | يغلّف دالة غير متزامنة؛ يعيد المحاولة على أنواع الاستثناء المُعطاة مع تأخير خطي متزايد (`0.5s * attempt`)، ثم يعيد إطلاق آخر استثناء بعد `max_retries` محاولة. |
| `timing` | يغلّف دالة غير متزامنة؛ يطبع زمن تنفيذها في stdout بعد كل استدعاء. |

---

## أمثلة

جميع الأمثلة في [`examples/`](examples/) وجاهزة للتشغيل على مضيف حقيقي بعد تعديل
تفاصيل الاتصال أعلى كل ملف.

| # | الملف | يوضّح |
|---|---|---|
| ١ | [`01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py) | الاتصال، تنفيذ الأوامر، تنفيذ `sudo`، و `execute_on_all` |
| ٢ | [`02_high_speed_parallel_transfer.py`](examples/02_high_speed_parallel_transfer.py) | رفع/تنزيل بـ `ParallelSCP` مع إبلاغ حي عن التقدّم |
| ٣ | [`03_ssh_tunneling_socks5_and_port_forward.py`](examples/03_ssh_tunneling_socks5_and_port_forward.py) | وكيل SOCKS5 وإعادة توجيه منفذ محلي عبر مضيف وسيط |
| ٤ | [`04_session_recording_and_replay.py`](examples/04_session_recording_and_replay.py) | تسجيل جلسة وإعادة تشغيلها |
| ٥ | [`05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py) | تنفيذ أمر في حاوية Docker وإرسال إشعار Discord/Telegram |
| ٦ | [`06_encrypted_session_storage.py`](examples/06_encrypted_session_storage.py) | حفظ وتحميل بيانات الاعتماد بـ `SessionFileManager` |

```bash
python examples/01_basic_connect_and_execute.py
```

---

## اعتبارات أمنية

- معالج مفتاح المضيف الافتراضي (`FastSSHSession._default_host_key_handler`) يقبل
  جميع مفاتيح المضيف ولا يحمي من هجمات MITM. قبل الاستخدام مقابل شبكات غير
  موثوقة في الإنتاج، عيّن `host_key_callback` في `SSHConfig` أو هيئ التحقق من
  known-hosts في `asyncssh`.
- فضّل المفاتيح الخاصة لـ SSH على المصادقة بكلمة المرور كلما أمكن.
- تُحظر نطاقات IP الخاصة والمحجوزة افتراضيًا بواسطة
  `InputValidator.validate_host()` (حماية SSRF)؛ مرّر `allow_private=True`
  صراحةً عند الاتصال بالشبكات الداخلية.
- تُرفض مجموعة ثابتة من أنماط الأوامر المدمّرة ومؤشرات الحقن
  الشائعة بواسطة `InputValidator.validate_command()` إلا مع `allow_dangerous=True`؛
  وهي تدبير دفاع متعمّق وليست بديلاً عن الثقة بمصدر الأوامر.
- عند استخدام تخزين الجلسات المشفّر، استخدم كلمة مرور رئيسية
  من ١٢ حرفًا على الأقل (يفرضها `AIOSSH.__init__`)؛ المفتاح المشتق لا
  يُكتب أبدًا إلى القرص ويُمسح من الذاكرة بعد الاستخدام.
- استخدم `async with` / مدير السياق لضمان تنظيف الجلسات
  والمجمّعات والأنفاق دائمًا — حتى عند حدوث خطأ.

---

## الاختبار

يحتوي الدليل `tests/` على مجموعة `unittest` مكتفية ذاتًا (٢٢٨ اختبارًا)
تغطي `InputValidator` و `RateLimiter` و `ConnectionPool` و `FastSSHSession` و
`SessionFileManager` (باستخدام حزمة `cryptography` الحقيقية لـ AES-256-GCM /
PBKDF2) واختبارات انحدار لمعالجة حقن الأوامر في `DockerExecSession`
وإصلاحات `ParallelSCP` / `ConnectionPool`. لا تحتاج إلى وصول شبكي حقيقي
أو حزمة `asyncssh` الحقيقية — يوفّر `asyncssh` وهمي مصغّر
(`tests/_fake_asyncssh/`) أنواع الاستثناءات وسطح الاتصال التي تعتمد
عليها المكتبة فقط. تنقسم المجموعة بين `tests/test_all.py` (السلوك
الأساسي) و `tests/test_deep_audit.py` (الحالات الحدّية والتزامن
والأمان والسلوك الخاص بالمنصّة) و `tests/test_asyncssh_boundary.py`
(سيناريوهات انحدار تضمن أن الطلبات المُتحقّق منها فقط
والوسائط المفتاحية المتوافقة مع asyncssh تعبر الحدّ إلى مكتبة
`asyncssh` الأساسية).

```bash
pip install cryptography
PYTHONPATH="src:tests/_fake_asyncssh:tests" python -m unittest tests.test_all tests.test_deep_audit tests.test_asyncssh_boundary tests.test_secure_memory -v
```

---

## التطوير

```bash
git clone https://github.com/bluedock/aiossh.git
cd aiossh
pip install -e ".[dev]"
ruff check .
mypy src/aiossh
```

---

## الرخصة

رخصة MIT © ٢٠٢٦ bluedock. راجع [`LICENSE`](LICENSE) للنص الكامل.

---

## المنشئ

يُنشئ AIOSSH ويصونه [**bluedock**](https://github.com/bluedock).
