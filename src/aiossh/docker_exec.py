"""
Docker Exec Module - v1.1.0
"""

from __future__ import annotations

from typing import Any, Optional


class DockerExecSession:
    def __init__(self, ssh_session: Any, container_name: str, sudo: bool = False):
        self._ssh = ssh_session
        self.container = container_name
        self.sudo = sudo

    @property
    def is_connected(self) -> bool:
        return getattr(self._ssh, "is_connected", False)

    async def connect(self) -> None:
        result = await self._ssh.execute(f"docker ps --filter name={self.container} --format '{{{{.Names}}}}'")
        if self.container not in result.get("stdout", ""):
            raise ConnectionError(f"Container '{self.container}' not found or not running")

    async def execute(self, command: str, timeout: int = 30, workdir: str = "/") -> dict[str, Any]:
        docker_cmd = f'docker exec -w {workdir} {self.container} {command}'
        if self.sudo:
            docker_cmd = f"sudo {docker_cmd}"
        return await self._ssh.execute(docker_cmd, timeout=timeout)

    async def close(self) -> None:
        pass
