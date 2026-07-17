# Changelog

All notable changes to this project are documented in this file. Each entry
describes the specific behavior that changed and, where relevant, the file
or component it affects.

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
- Bumped version to 1.1.2.
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
