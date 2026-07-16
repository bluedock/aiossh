# Changelog

All notable changes to AIOSSH will be documented in this file.

## [1.1.1] - 2026-07-16

### Fixed
- **Critical**: `AIOSSHCommandError` / `AIOSSHCommandTimeoutError` now accept the `command=` keyword (previously raised `TypeError`)
- **Critical**: Resume support in `download_file` — removed non-existent `resume_offset=` kwarg to `asyncssh`; implemented real byte-range resume via `sftp.open` + seek/append
- **Critical**: `SessionRecorder.save` no longer writes `str` to binary files when `orjson` is absent (stdlib `json` fallback now always produces `bytes`)
- Connection pool: `close_session` / `close_all` now correctly call `return_connection` so pooled sessions are reused instead of being hard-closed and leaked
- Dead / inverted `split` detection logic in `ParallelSCP.download` (now correctly falls back when GNU `split` is unavailable)
- Webhook HTTP calls use proper `aiohttp.ClientTimeout` instead of bare `timeout=5` integer

### Changed
- Minor cleanup of unused imports

## [1.1.0] - 2026-07-16

### Fixed
- **Critical**: `os.geteuid()` crash on Windows and non-POSIX systems in `validators.py` (port validation)
- Connection pool idle/total count accuracy after cleanup
- `stream_command` could hang indefinitely (added `asyncio.timeout`)
- `ParallelSCP` failed on systems without GNU `split` (now has graceful fallback)
- Minor race conditions in pool return logic
- Path traversal detection strengthened

### Added
- Minimum idle connection support in ConnectionPool
- Practical usage examples in the examples/ directory
- CHANGELOG.md
- Additional modules for broader feature coverage (file encryption, proxy, webhooks, Docker exec, session replay)

### Changed
- Reduced default chunk size in parallel transfers for compatibility
- Improved command streaming with timeout protection
- Updated documentation and examples
- Bumped version to 1.1.0

### Security
- Improved session name and path validation rules
- Added documentation about host key verification risks

## [1.0.0] - Initial Release

- Initial public release with core features
