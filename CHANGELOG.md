# Changelog

All notable changes to this project are documented in this file. Each entry
describes the specific behavior that changed and, where relevant, the file
or component it affects.

## [1.1.3] - 2026-07-19

### Added

- **asyncssh boundary regression tests (`tests/test_asyncssh_boundary.py`).**
  A new scenario suite locks down the layer between aiossh and the
  underlying `asyncssh` library. It uses a strict, keyword-only `connect`
  double (mirroring the exact `asyncssh.connect` arguments aiossh is
  allowed to use, with no `**kwargs` catch-all) so that any stray,
  renamed, or removed keyword argument raises `TypeError` and fails the
  test. The scenarios assert that: only asyncssh-compatible keyword
  arguments cross the boundary (compression is sent as an algorithm list,
  never a bare bool; `known_hosts` defaults to `None`, never a bool or
  callable; a legacy proxy *string* is not smuggled through as `tunnel`
  while an `SSHClientConnection` proxy *is*); and that no request reaches
  asyncssh before aiossh validates it (invalid host/port/username never
  dial out, and dangerous or injection-style commands are never handed to
  `connection.run`). This guards against the historical class of bug
  where requests were passed straight to asyncssh and failed with opaque
  errors.
- **Secure-memory regression tests (`tests/test_secure_memory.py`).**
  New tests assert that `SecureMemory.secure_clear` mutates the actual
  buffer in place, that `SessionFileManager._derive_key` returns a
  mutable `bytearray` (so the derived key can really be wiped), and
  that encrypted-session round-trips still succeed after the fix.
- **Trilingual documentation.** The README is now available in English
  (`README.md`), Persian (`README.fa.md`), and Arabic (`README.ar.md`),
  each a full translation with a language switcher at the top and a
  complete command/API reference for every public class and method.

### Fixed

- **Encrypted session files never actually wiped the derived key or
  plaintext credentials from memory.** `SessionFileManager` called
  `SecureMemory.secure_clear(bytearray(key))` (and the same for the
  plaintext) in its `finally` blocks, but `bytearray(key)` builds a
  throwaway *copy*: the copy was zeroed while the real derived key
  and the plaintext credential bytes were left intact in memory,
  defeating the whole point of the "secure memory clearing" the
  library advertises. `_derive_key()` now returns a mutable
  `bytearray`, the plaintext is held in a `bytearray`, and the
  `finally` blocks wipe those exact objects in place (AES-GCM and
  HMAC both accept the `bytearray` directly, so encryption is
  unchanged).
- **`InputValidator.validate_port()` rejected the default SSH port (and
  every port below 1024) for non-root users.**  The validator applied a
  "privileged port" check that raised `AIOSSHInvalidParameterError`
  (`code="PRIVILEGED_PORT"`) whenever a port `< 1024` was validated by a
  process not running as root. This is incorrect for an SSH *client*:
  privileged-port restrictions apply only to *binding/listening* on a
  local port, never to *connecting* to a remote one. As written, the
  check made it impossible to connect to a server on port 22 (or any
  other well-known port) without root, breaking the most common usage of
  the library. The privileged-port check (and its `_is_privileged_port_check()`
  helper) has been removed entirely; `validate_port()` now only enforces
  the 1–65535 integer range.

- **`TelegramWebhook` built an invalid API URL.**  The endpoint was
  constructed with an f-string that used doubled braces
  (`f"https://…/sendMessage"`), which emit *literal* `{` and `}`
  characters. Every Telegram notification was therefore POSTed to a
  malformed URL wrapped in curly braces and silently failed. The URL is
  now built correctly as `https://api.telegram.org/bot<token>/sendMessage`.

- **`ParallelSCP.download()` remote size-probe passed the wrong argument
  vector to `python3 -c`.**  The probe invoked
  `python3 -c "…" -- <path>`, which makes `sys.argv[1]` equal to `"--"`
  instead of the file path, so the primary size check always failed and
  silently fell through to the `stat`/`wc` fallback. The spurious `--`
  separator has been removed so the `python3` probe works as intended.

- **`AIOSSHFileDiskFullError` and `AIOSSHPluginError` were not
  importable from the top-level package.**  Both exceptions are defined
  in `exceptions.py` and documented in the README exception table, but
  they were missing from `aiossh/__init__.py`, so
  `from aiossh import AIOSSHFileDiskFullError` raised `ImportError`. Both
  are now exported and included in `__all__`.

- **Remote path corruption on Windows hosts in `InputValidator.validate_path()`.**
  `validate_path()` used `pathlib.Path(path).expanduser()` to expand the
  ``~`` home-directory prefix.  On Windows, `Path` silently converts
  forward slashes to backslashes, so a remote path like
  `/home/user/.ssh/id_rsa` became `\home\user\.ssh\id_rsa`.  This
  broke SFTP uploads, downloads, and SCP transfers whenever aiossh was
  run on a Windows machine targeting a Linux remote host.  The method now
  expands ``~`` via pure-string manipulation, preserving the original
  path separators regardless of the local platform.

- **Disk-space check in `FastSSHSession.upload_file()` corrupted remote
  paths on Windows.**  The method used `Path(remote_path).parent` to
  derive the remote directory for the SFTP `statvfs` call.  On Windows,
  `Path` converts ``/`` to ``\\``, sending `\home\user\remote` to the
  remote server instead of `/home/user/remote`.  The disk-space check
  now uses pure-string `rsplit("/", 1)` to extract the parent directory,
  preserving the original path separators.

- **`RateLimiter.current_rate` was not async-safe.**  The synchronous
  `current_rate` property mutated the internal `_requests` deque without
  holding the asyncio lock, creating a potential data race with
  concurrent `acquire()` calls.  The property now documents its
  best-effort nature and uses a guarded `popleft()` to avoid IndexError
  races.

- **`SSHTunnelManager.close_all()` did not await `wait_closed()`.**
  After calling `listener.close()`, the method returned immediately
  without waiting for the listener's socket to actually release.  This
  could leave sockets in `TIME_WAIT` state and cause "address already in
  use" errors when quickly recreating tunnels.  `close_all()` now calls
  `await listener.wait_closed()` for each listener.

- **`ParallelSCP.download()` leaked remote chunk files on failure.**
  When individual chunk downloads failed or the reassembled file's size
  did not match the expected size, the method raised an error but left
  the remote `.part*` files behind.  Both error paths now attempt to
  clean up remote chunk files before raising.

- **`AIOSSH.execute_command()` did not check the `_closed` flag.**
  After calling `close_all()`, it was still possible to call
  `execute_command()` on the client instance.  This would resolve the
  session (which had already been removed from `_active_sessions`) and
  raise a misleading "session not found" error instead of the clear
  "Client closed" message.  The method now checks `_closed` up front.

- **`FastSSHSession.close()` leaked the connection reference when the
  underlying connection was already closed.**  If `_connection` was not
  `None` but `_connection.is_closed()` returned `True`, the `if` block
  was skipped entirely and `_connection` was never set to `None`,
  keeping a stale reference alive.  The method now always clears
  `_connection` when closing, regardless of its current state.

- **`decorators.retry()` crashed with `TypeError` when `max_retries=0`.**
  The retry decorator's loop would not execute at all, leaving
  `last_exc` as `None`, and `raise None` is invalid in Python.  The
  decorator now validates `max_retries >= 1` at decoration time and
  raises `ValueError` for invalid values.

- **`webhook.py` used deprecated `asyncio.iscoroutinefunction()`.**
  Python 3.14 deprecated `asyncio.iscoroutinefunction()` in favour of
  `inspect.iscoroutinefunction()`.  The webhook module now uses the
  `inspect` variant to avoid the deprecation warning.

### Changed

- **Reorganized the package into a professional, tree-structured layout.**
  The previously flat `src/aiossh/*.py` modules are now grouped into
  focused subpackages: `core/` (`client`, `session`, `pool`),
  `security/` (`config`, `validators`, `file_manager`), `transfer/`
  (`scp`), `integrations/` (`proxy`, `webhook`, `docker`, `replay`), and
  `utils/` (`decorators`), with `exceptions.py` remaining at the top
  level. The public API is unchanged — `from aiossh import ...` still
  exposes every class via the same lazy-loaded `__all__` — so this is a
  non-breaking internal restructuring.

- Version bumped to 1.1.3.
- Removed the unused `aiofiles` runtime dependency from `pyproject.toml`
  (it was declared but never imported anywhere in the codebase).
- Removed the misleading `kubernetes` keyword from `pyproject.toml`; the
  library provides no Kubernetes-specific functionality.
- Corrected the README: the stated version is now 1.1.3, the project-tree
  and testing sections reflect the full 228-test suite
  (`tests/test_all.py`, `tests/test_deep_audit.py`, and
  `tests/test_asyncssh_boundary.py`), and the
  `validate_port()` description no longer references privileged ports.
- Fixed a mislabeled entry in the 1.1.1 changelog section that read
  "Bumped version to 1.1.2".
- Improved docstrings in `InputValidator.validate_path()` and
  `RateLimiter.current_rate` explaining platform-specific behaviour and
  thread-safety guarantees.
- Added comprehensive deep-audit test suite (`tests/test_deep_audit.py`)
  with 180 tests covering edge cases, concurrency, security, and
  platform-specific behaviour.
- Removed promotional/superlative phrasing from the README in favour of
  factual, reference-style documentation, and expanded the command
  documentation so every public entry point is covered.
- Project authorship and all repository URLs now point to the creator,
  **bluedock** (https://github.com/bluedock): updated `pyproject.toml`
  (`authors`, Homepage/Repository/Issues), `LICENSE` (copyright holder),
  and the README clone/license/credits sections.

## [1.1.2] - 2026-07-17

### Security

- **Command injection / container escape in `DockerExecSession.execute()`.**
  The caller-supplied `command` was inserted unquoted into the
  `docker exec ...` string, which is itself executed as a single shell
  command over SSH. Shell metacharacters in `command` (`&&`, `;`, `|`) were
  therefore interpreted by the remote host's shell rather than the
  container's. For example, `execute("nginx -t && nginx -s reload")` caused
  `nginx -s reload` to run on the host after `docker exec` returned, and a
  command such as `"echo hi; rm -rf /some/path"` executed its second half
  directly on the host, outside the container entirely. `command` is now
  passed through `shlex.quote()` and executed via an explicit `sh -c`
  inside the container, so it is parsed exactly once, inside the container.

- **Command injection in `ParallelSCP.download()`.** The remote
  file-size check and the remote cleanup command (`rm -f ...`) interpolated
  `remote_path` directly into a shell command string without escaping. A
  `remote_path` containing a single quote could break out of the intended
  command and inject arbitrary shell commands on the remote host.
  `remote_path` is now validated with `InputValidator.validate_path()` and
  consistently escaped with `shlex.quote()` everywhere it is used.

- **Path traversal in `SessionRecorder`.** The `session_id` constructor
  argument was used directly in the recording's output filename without
  validation, so a value such as `"../../etc/cron.d/evil"` could write
  outside the configured `storage_dir`. `session_id` is now validated with
  `InputValidator.validate_session_name()`.

- **Connection pool limit bypass in `AIOSSH.connect(use_pool=True)`.** Any
  exception raised by `ConnectionPool.get_connection()`, including
  `AIOSSHPoolExhaustedError`, was caught by a broad `except Exception` and
  silently followed by opening a new connection outside the pool's
  accounting. This defeated `max_connections`: once the pool reported
  itself full, every subsequent `connect()` call simply opened an unpooled
  connection instead of failing. `AIOSSHPoolExhaustedError` is now
  propagated to the caller.

### Fixed

- `DockerExecSession.connect()` matched the target container name against
  the raw, unsplit stdout of `docker ps`, so a container name that was a
  substring of another running container's name could produce a false
  positive. It now compares against the exact list of returned container
  names.

- `ParallelSCP.download()` discarded exceptions raised by individual chunk
  downloads and proceeded to reassemble the file regardless, producing a
  truncated or corrupted local file without raising an error. Failed
  chunks are now tracked; if any chunk fails, the call raises
  `AIOSSHFileDownloadError` instead of completing silently. The reassembled
  file's size is also verified against the expected size before the remote
  parts are removed.

- `ConnectionPool.get_connection()` held the pool's lock for the entire
  duration of a new connection attempt, blocking all other pool operations
  while a single connection was being established over the network. The
  connection is now established outside the lock, with the pool's
  accounting rolled back if the attempt fails.

- Removed an unused `Path.resolve()` call in `validators.py`. Its result
  was discarded and had no effect, but its presence was misleading, since
  `validate_path()` is also used for remote/SFTP paths, which must not be
  resolved against the local filesystem.

### Changed

- All remote paths and container names used in shell commands in
  `scp_speed.py` and `docker_exec.py` are now consistently escaped with
  `shlex.quote()`.
- `ParallelSCP`'s remote `split` invocation now uses `-a 4` so generated
  part suffixes (`.part0000`, `.part0001`, ...) match the naming convention
  used elsewhere in the module.
- Removed a misleading comment in `scp_speed.py`'s chunk-download error
  handling.

## [1.1.1] - 2026-07-16

### Fixed

- `InputValidator`'s privileged-port check called `os.geteuid()`
  unconditionally, which raises `AttributeError` on Windows and other
  non-POSIX platforms. The check is now skipped on non-POSIX systems.
- `ConnectionPool.return_connection()` was defined but never called from
  `AIOSSH`, so every session acquired with `use_pool=True` remained counted
  against `max_connections` even after the caller closed it. `AIOSSH` now
  tracks pooled sessions and returns them to the pool from
  `close_session()` and `close_all()`.
- `FastSSHSession.stream_command()` had no timeout and could hang
  indefinitely if the remote command produced no output. It now runs under
  `asyncio.timeout()` and raises `AIOSSHCommandTimeoutError` on expiry.
- `ParallelSCP` assumed GNU `split` was present on the remote host and
  failed on systems without it. It now probes for `split` first and falls
  back to a plain, non-chunked download when the probe fails.
- `AIOSSHCommandError` and `AIOSSHCommandTimeoutError` raised `TypeError`
  when constructed with a `command` keyword argument, which callers in
  `session.py` did on every command failure. Both exceptions now accept
  `command` directly.
- `FastSSHSession.download_file(resume=True)` raised `TypeError`, since
  asyncssh's `SFTPClient.get()` has no `resume_offset` parameter. Resume is
  now implemented manually via seek and chunked read/append.
- `SessionRecorder.save()` raised
  `TypeError: a bytes-like object is required, not 'str'` when `orjson`
  was not installed, because the stdlib `json` fallback returned `str`
  instead of `bytes`. The fallback now always produces `bytes`.
- `ParallelSCP.download()`'s remote-`split`-availability probe ran but its
  result was discarded, so downloads always attempted to use `split` even
  when the probe had detected it was missing.
- Corrected minor race conditions in `ConnectionPool`'s idle/total
  connection counters after cleanup cycles.
- Strengthened path-traversal detection in `InputValidator.validate_path()`.

### Added

- `min_connections` (warm pool) support in `ConnectionPool` / `PoolConfig`.
- `examples/` directory with six runnable usage examples.
- `CHANGELOG.md`.
- Additional modules: encrypted session storage (`file_manager.py`), SSH
  tunneling (`proxy.py`), webhook notifications (`webhook.py`), Docker exec
  (`docker_exec.py`), and session recording/replay (`session_replay.py`).

### Changed

- Reduced the default chunk size in `ParallelSCP` for broader
  compatibility with remote hosts.
- Bumped version to 1.1.1.
- Removed unused imports, a redundant f-string, and an unused variable
  flagged by `ruff`.

### Security

- Strengthened session-name and path validation rules.
- Documented the risk of the default host-key handler, which accepts all
  host keys and must be replaced with proper verification before use in
  production.

## [1.0.0] - Initial Release

- Initial public release: asynchronous SSH client, connection pooling,
  input validation, and the core exception hierarchy.
