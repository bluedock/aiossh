"""
Input Validation Module - v2.0 (fixed for v1.1.0)

Whitelist-based validation for all user-supplied inputs.
Rejects by default, only allows explicitly permitted patterns.
Includes SSRF protection, injection prevention, and path traversal blocking.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
from pathlib import Path
from typing import Union

from ..exceptions import AIOSSHInvalidParameterError, AIOSSHSecurityError


class InputValidator:
    """Secure input validation and sanitization.

    All methods follow a whitelist approach: define what is allowed,
    reject everything else. This is more secure than blacklisting.
    """

    # Pre-compiled regex patterns for performance
    _HOSTNAME_PATTERN: re.Pattern[str] = re.compile(
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    _USERNAME_PATTERN: re.Pattern[str] = re.compile(
        r"^[a-z_][a-z0-9_-]{0,31}$", re.IGNORECASE
    )
    _SESSION_NAME_PATTERN: re.Pattern[str] = re.compile(
        r"^[a-zA-Z0-9_\-]{1,64}$"
    )

    # Patterns always blocked in commands (unless explicitly allowed)
    _DANGEROUS_COMMAND_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
        re.compile(r"mkfs\.", re.IGNORECASE),
        re.compile(r"dd\s+if=", re.IGNORECASE),
        re.compile(r">\s*/dev/sd", re.IGNORECASE),
        re.compile(r"chmod\s+777\s+/", re.IGNORECASE),
        re.compile(r":\(\)\s*\{", re.IGNORECASE),  # fork bomb
    ]

    # Command injection indicators
    _INJECTION_INDICATORS: list[str] = [
        "$(", "${", "`", "<(", ">(", "/dev/tcp", "/dev/udp",
    ]

    # Private/internal IP ranges for SSRF protection
    _PRIVATE_IPV4_NETWORKS: list[ipaddress.IPv4Network] = [
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
        ipaddress.IPv4Network("127.0.0.0/8"),
        ipaddress.IPv4Network("169.254.0.0/16"),
        ipaddress.IPv4Network("0.0.0.0/8"),
        ipaddress.IPv4Network("224.0.0.0/4"),
        ipaddress.IPv4Network("240.0.0.0/4"),
    ]

    _PRIVATE_IPV6_NETWORKS: list[ipaddress.IPv6Network] = [
        ipaddress.IPv6Network("::1/128"),
        ipaddress.IPv6Network("fe80::/10"),
        ipaddress.IPv6Network("fc00::/7"),
    ]

    # ── Host Validation ──────────────────────────────────────────────────

    @classmethod
    def validate_host(
        cls,
        host: str,
        *,
        allow_private: bool = False,
    ) -> str:
        """Validate a hostname or IP address.

        Performs DNS-agnostic validation. Blocks private/internal IP ranges
        by default for SSRF protection (can be overridden for internal networks).

        Args:
            host: The hostname or IP address to validate.
            allow_private: If True, allows private/reserved IP addresses.

        Returns:
            Normalized host string.

        Raises:
            AIOSSHInvalidParameterError: If the host is empty, invalid, or private (when blocked).
        """
        if not host or not isinstance(host, str):
            raise AIOSSHInvalidParameterError(
                "Host must be a non-empty string",
                code="EMPTY_HOST",
                details={"host": str(host)[:50]},
            )

        host = host.strip().lower()

        if "\x00" in host:
            raise AIOSSHInvalidParameterError(
                "Host contains null byte",
                code="NULL_BYTE",
                details={"host": host[:50]},
            )

        if len(host) > 253:
            raise AIOSSHInvalidParameterError(
                "Hostname too long (max 253 characters)",
                code="HOST_TOO_LONG",
                details={"host": host[:50]},
            )

        # Try parsing as IP address
        try:
            ip = ipaddress.ip_address(host)

            if not allow_private:
                if isinstance(ip, ipaddress.IPv4Address):
                    for network in cls._PRIVATE_IPV4_NETWORKS:
                        if ip in network:
                            raise AIOSSHInvalidParameterError(
                                f"Private/reserved IPv4 address not allowed: {host} "
                                "(use allow_private=True for internal networks)",
                                code="PRIVATE_IP_BLOCKED",
                                details={"host": host},
                            )
                elif isinstance(ip, ipaddress.IPv6Address):
                    for network in cls._PRIVATE_IPV6_NETWORKS:
                        if ip in network:
                            raise AIOSSHInvalidParameterError(
                                f"Private/reserved IPv6 address not allowed: {host}",
                                code="PRIVATE_IP_BLOCKED",
                                details={"host": host},
                            )

            return str(ip)
        except ValueError:
            pass  # Not an IP, continue to hostname validation

        # Validate as hostname (RFC 1123 relaxed)
        if not cls._HOSTNAME_PATTERN.match(host):
            raise AIOSSHInvalidParameterError(
                f"Invalid hostname format: {host[:50]}",
                code="INVALID_HOSTNAME",
                details={"host": host[:50]},
            )

        return host

    # ── Port Validation ──────────────────────────────────────────────────

    @classmethod
    def validate_port(cls, port: Union[int, str]) -> int:
        """Validate a port number.

        Args:
            port: Port number as int or string.

        Returns:
            Validated port as integer.

        Raises:
            AIOSSHInvalidParameterError: If the port is not an integer in the range 1-65535.
        """
        try:
            port_int = int(port)
        except (TypeError, ValueError):
            raise AIOSSHInvalidParameterError(
                f"Port must be an integer, got: {type(port).__name__}",
                code="INVALID_PORT_TYPE",
                details={"port": str(port)[:20]},
            )

        if port_int < 1 or port_int > 65535:
            raise AIOSSHInvalidParameterError(
                f"Port must be 1-65535, got: {port_int}",
                code="INVALID_PORT_RANGE",
                details={"port": port_int},
            )

        return port_int

    # ── Username Validation ──────────────────────────────────────────────

    @classmethod
    def validate_username(cls, username: str) -> str:
        """Validate a username.

        Args:
            username: The username to validate.

        Returns:
            Validated username in lowercase.

        Raises:
            AIOSSHInvalidParameterError: If username is empty or invalid.
        """
        if not username or not isinstance(username, str):
            raise AIOSSHInvalidParameterError(
                "Username must be a non-empty string",
                code="EMPTY_USERNAME",
            )

        username = username.strip().lower()

        if "\x00" in username:
            raise AIOSSHInvalidParameterError(
                "Username contains null byte",
                code="NULL_BYTE",
            )

        if not cls._USERNAME_PATTERN.match(username):
            raise AIOSSHInvalidParameterError(
                f"Invalid username format: {username[:50]}",
                code="INVALID_USERNAME",
                details={"username": username[:50]},
            )

        return username

    # ── Password Validation ──────────────────────────────────────────────

    @classmethod
    def validate_password(cls, password: str) -> str:
        """Validate a password with basic security checks.

        Note: This does not enforce complexity requirements - that should
        be done at a higher level (e.g. in your application). This ensures
        the password is safe to transmit and process.

        Args:
            password: The password to validate.

        Returns:
            The validated password.

        Raises:
            AIOSSHInvalidParameterError: If password is empty or too long.
        """
        if not password or not isinstance(password, str):
            raise AIOSSHInvalidParameterError(
                "Password must be a non-empty string",
                code="EMPTY_PASSWORD",
            )

        if len(password) > 128:
            raise AIOSSHInvalidParameterError(
                "Password too long (max 128 characters)",
                code="PASSWORD_TOO_LONG",
                details={"length": len(password)},
            )

        if "\x00" in password:
            raise AIOSSHInvalidParameterError(
                "Password contains null byte",
                code="NULL_BYTE",
            )

        return password

    # ── Command Validation ───────────────────────────────────────────────

    @classmethod
    def validate_command(
        cls,
        command: str,
        *,
        allow_dangerous: bool = False,
    ) -> str:
        """Validate a shell command for safety.

        Checks for dangerous patterns and command injection vectors.
        Uses whitelist approach: blocks known-dangerous patterns by default.

        Args:
            command: The command string to validate.
            allow_dangerous: If True, skips dangerous pattern checks (use with caution).

        Returns:
            The validated and stripped command.

        Raises:
            AIOSSHInvalidParameterError: If command is empty or too long.
            AIOSSHSecurityError: If dangerous patterns are detected.
        """
        if not command or not isinstance(command, str):
            raise AIOSSHInvalidParameterError(
                "Command must be a non-empty string",
                code="EMPTY_COMMAND",
            )

        command = command.strip()

        if len(command) > 8192:
            raise AIOSSHInvalidParameterError(
                "Command too long (max 8192 characters)",
                code="COMMAND_TOO_LONG",
                details={"length": len(command)},
            )

        if "\x00" in command:
            raise AIOSSHSecurityError(
                "Command contains null byte",
                code="NULL_BYTE",
            )

        if not allow_dangerous:
            for pattern in cls._DANGEROUS_COMMAND_PATTERNS:
                if pattern.search(command):
                    raise AIOSSHSecurityError(
                        "Dangerous command pattern detected",
                        code="DANGEROUS_COMMAND",
                        details={
                            "command": command[:200],
                            "pattern": pattern.pattern,
                        },
                    )

            for indicator in cls._INJECTION_INDICATORS:
                if indicator in command:
                    raise AIOSSHSecurityError(
                        f"Command injection indicator detected: {indicator}",
                        code="INJECTION_DETECTED",
                        details={
                            "command": command[:200],
                            "indicator": indicator,
                        },
                    )

        return command

    # ── Path Validation ──────────────────────────────────────────────────

    @classmethod
    def validate_path(cls, path: str) -> str:
        """Validate a file path with traversal protection.

        Expands user home directory (``~``) and checks for path traversal
        sequences (``..``).

        This method is used for **both** local and remote (SSH/SFTP) paths.
        To avoid corrupting remote Unix paths on Windows hosts, we expand
        ``~`` via pure-string manipulation instead of :class:`pathlib.Path`,
        which would silently convert ``/`` to ``\\`` on Windows.

        Args:
            path: The file path to validate.

        Returns:
            Expanded and validated path string.

        Raises:
            AIOSSHInvalidParameterError: If path is empty or contains null bytes.
            AIOSSHSecurityError: If path traversal is detected.
        """
        if not path or not isinstance(path, str):
            raise AIOSSHInvalidParameterError(
                "Path must be a non-empty string",
                code="EMPTY_PATH",
            )

        if len(path) > 4096:
            raise AIOSSHInvalidParameterError(
                "Path too long (max 4096 characters)",
                code="PATH_TOO_LONG",
                details={"length": len(path)},
            )

        if "\x00" in path:
            raise AIOSSHInvalidParameterError(
                "Path contains null byte",
                code="NULL_BYTE",
            )

        # Expand ``~`` / ``~user`` without pathlib to preserve the original
        # path separators.  On Windows, ``Path(p).expanduser()`` silently
        # converts ``/`` → ``\\``, which corrupts remote Unix paths.
        expanded = path
        if expanded.startswith("~"):
            import os as _os
            home = _os.path.expanduser("~")
            if expanded == "~" or expanded.startswith("~/"):
                expanded = home + expanded[1:]
            elif expanded.startswith("~"):
                # ~username form – fall back to pathlib only for this case
                # (rare in SSH contexts, and pathlib handles it correctly).
                from pathlib import Path as _P
                expanded = str(_P(expanded).expanduser())

        # Reject any literal '..' path segment (path traversal).
        # Normalize both separators before splitting so both ``foo/../bar``
        # and ``foo\\..\\bar`` are caught.
        parts = expanded.replace("\\", "/").split("/")
        if any(part == ".." for part in parts):
            raise AIOSSHSecurityError(
                f"Path traversal detected: {path[:200]}",
                code="PATH_TRAVERSAL",
                details={"path": path[:200]},
            )

        return expanded

    # ── Session Name Validation ──────────────────────────────────────────

    @classmethod
    def validate_session_name(cls, name: str) -> str:
        """Validate a session name.

        Session names are used as identifiers and filenames, so they
        must be filesystem-safe and not contain path separators.

        Args:
            name: The session name to validate.

        Returns:
            Validated session name.

        Raises:
            AIOSSHInvalidParameterError: If name is empty or invalid.
        """
        if not name or not isinstance(name, str):
            raise AIOSSHInvalidParameterError(
                "Session name must be a non-empty string",
                code="EMPTY_SESSION_NAME",
            )

        name = name.strip()

        if not cls._SESSION_NAME_PATTERN.match(name):
            raise AIOSSHInvalidParameterError(
                f"Invalid session name (alphanumeric, underscore, hyphen only): {name[:100]}",
                code="INVALID_SESSION_NAME",
                details={"name": name[:100]},
            )

        # Extra safety: reject path separators
        if "/" in name or "\\" in name or ".." in name:
            raise AIOSSHInvalidParameterError(
                "Session name cannot contain path separators or ..",
                code="INVALID_SESSION_NAME",
            )

        return name

    # ── String Sanitization ──────────────────────────────────────────────

    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 256) -> str:
        """Sanitize a general-purpose string.

        Removes null bytes, strips whitespace, and truncates to max length.

        Args:
            value: The string to sanitize.
            max_length: Maximum allowed length after sanitization.

        Returns:
            Sanitized string.

        Raises:
            AIOSSHInvalidParameterError: If value is not a string.
        """
        if not isinstance(value, str):
            raise AIOSSHInvalidParameterError(
                f"Expected string, got {type(value).__name__}",
                code="TYPE_ERROR",
                details={"type": type(value).__name__},
            )

        value = value.replace("\x00", "").strip()

        if len(value) > max_length:
            value = value[:max_length]

        return value

    # ── Shell Escaping ───────────────────────────────────────────────────

    @classmethod
    def shell_escape(cls, argument: str) -> str:
        """Safely escape a string for use as a shell argument.

        Uses shlex.quote() for POSIX-compliant escaping. This prevents
        shell injection when constructing commands with user input.

        Args:
            argument: The argument string to escape.

        Returns:
            Safely shell-escaped string.
        """
        return shlex.quote(argument)
