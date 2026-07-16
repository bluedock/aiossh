"""
Docker Container Exec Support - AIOSSH

Execute commands inside Docker containers using SSH or Docker API.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional


class DockerExecSession:
    """Execute commands inside a Docker container via SSH to host."""

    def __init__(
        self,
        ssh_session: Any,
        container_name: str,
        sudo: bool = False,
    ) -> None:
        """Initialize Docker exec session.

        Args:
            ssh_session: FastSSHSession connected to Docker host.
            container_name: Name or ID of the target container.
            sudo: Use sudo for docker commands if True.
        """
        self._ssh = ssh_session
        self.container = container_name
        self.sudo = sudo
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._ssh.is_connected if hasattr(self._ssh, "is_connected") else self._connected

    async def connect(self) -> None:
        """Verify container is running."""
        result = await self._ssh.execute(
            f"docker ps --filter name={self.container} --format '{{{{.Names}}}}'"
        )
        if self.container in result.get("stdout", ""):
            self._connected = True
        else:
            raise ConnectionError(f"Container '{self.container}' not found or not running")

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        workdir: str = "/",
    ) -> dict[str, Any]:
        """Execute a command inside the container."""
        docker_cmd = f'docker exec -w {workdir} {self.container} {command}'

        if self.sudo:
            docker_cmd = f"sudo {docker_cmd}"

        return await self._ssh.execute(docker_cmd, timeout=timeout)

    async def execute_interactive(
        self,
        command: str,
        stdin_data: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a command with stdin input."""
        docker_cmd = f'docker exec -i {self.container} {command}'

        if stdin_data:
            docker_cmd = f"echo '{stdin_data}' | {docker_cmd}"

        return await self._ssh.execute(docker_cmd)

    async def copy_to_container(self, local_path: str, container_path: str) -> dict[str, Any]:
        """Copy a file into the container."""
        docker_cmd = f"docker cp {local_path} {self.container}:{container_path}"
        return await self._ssh.execute(docker_cmd)

    async def copy_from_container(self, container_path: str, local_path: str) -> dict[str, Any]:
        """Copy a file from the container."""
        docker_cmd = f"docker cp {self.container}:{container_path} {local_path}"
        return await self._ssh.execute(docker_cmd)

    async def list_processes(self) -> dict[str, Any]:
        """List running processes in the container."""
        return await self.execute("ps aux")

    async def get_logs(self, lines: int = 100, tail: bool = True) -> dict[str, Any]:
        """Get container logs."""
        cmd = f"docker logs --tail {lines} {self.container}"
        return await self._ssh.execute(cmd)

    async def restart_container(self) -> dict[str, Any]:
        """Restart the container."""
        cmd = f"docker restart {self.container}"
        return await self._ssh.execute(cmd)

    async def close(self) -> None:
        """Close the session."""
        self._connected = False