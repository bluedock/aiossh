"""
Docker Exec Module - v1.1.0
"""

from __future__ import annotations

import shlex
from typing import Any


class DockerExecSession:
    def __init__(self, ssh_session: Any, container_name: str, sudo: bool = False):
        self._ssh = ssh_session
        self.container = container_name
        self.sudo = sudo

    @property
    def is_connected(self) -> bool:
        return getattr(self._ssh, "is_connected", False)

    async def connect(self) -> None:
        c_quoted = shlex.quote(self.container)
        result = await self._ssh.execute(f"docker ps --filter name={c_quoted} --format '{{{{.Names}}}}'")
        # Compare against exact lines, not a raw substring check: "in" on the
        # unsplit stdout would also match if self.container happened to be a
        # substring of a different, unrelated container's name.
        names = result.get("stdout", "").splitlines()
        if self.container not in names:
            raise ConnectionError(f"Container '{self.container}' not found or not running")

    async def execute(self, command: str, timeout: int = 30, workdir: str = "/") -> dict[str, Any]:
        c_quoted = shlex.quote(self.container)
        w_quoted = shlex.quote(workdir)
        # `command` must be shell-quoted and handed to an explicit `sh -c`
        # inside the container. Previously it was spliced into docker_cmd
        # unquoted, and this whole string is itself run as a *remote shell*
        # command over SSH (see FastSSHSession.execute -> connection.run).
        # That meant any shell metacharacters in `command` - "&&", ";", "|",
        # etc. - were parsed by the remote HOST's shell, not by docker/the
        # container. A caller-supplied command like "nginx -t && nginx -s
        # reload" silently ran "nginx -s reload" on the host after docker
        # exec returned, and something like "echo hi; rm -rf /some/path"
        # would execute the second command directly on the host, completely
        # outside the container - a container-escape/command-injection bug,
        # not just a quoting nitpick. Wrapping the (quoted) command in
        # `sh -c '...'` makes the whole compound command a single opaque
        # argument to `docker exec`, so it is parsed by the container's
        # shell only, exactly once, as intended.
        cmd_quoted = shlex.quote(command)
        docker_cmd = f"docker exec -w {w_quoted} {c_quoted} sh -c {cmd_quoted}"
        if self.sudo:
            docker_cmd = f"sudo {docker_cmd}"
        return await self._ssh.execute(docker_cmd, timeout=timeout)

    async def close(self) -> None:
        pass
