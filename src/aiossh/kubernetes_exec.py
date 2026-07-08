"""
Kubernetes Pod Exec Support - AIOSSH

Execute commands inside Kubernetes pods using the Kubernetes API.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

try:
    import aiohttp
    from aiohttp import ClientTimeout
except ImportError:
    aiohttp = None
    ClientTimeout = None

try:
    import orjson
    json_dumps = orjson.dumps
except ImportError:
    json_dumps = lambda x: json.dumps(x).encode("utf-8")


class KubeExecSession:
    """Execute commands inside Kubernetes pods via API."""

    def __init__(
        self,
        namespace: str,
        pod_name: str,
        container: Optional[str] = None,
        api_server: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
    ) -> None:
        self.namespace = namespace
        self.pod_name = pod_name
        self.container = container
        self.api_server = api_server or "https://kubernetes.default.svc"
        self.token = token
        self.ca_cert = ca_cert
        self._connected = False

        # Load in-cluster config if no token provided
        if not token:
            self._load_incluster_config()

    def _load_incluster_config(self) -> None:
        """Load Kubernetes in-cluster configuration."""
        try:
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r") as f:
                self.token = f.read().strip()
            self.ca_cert = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        except FileNotFoundError:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Verify connectivity to the pod."""
        if not aiohttp:
            raise ImportError("aiohttp required for Kubernetes exec")

        # Test connection by checking pod exists
        url = f"{self.api_server}/api/v1/namespaces/{self.namespace}/pods/{self.pod_name}"

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            ssl_context = self.ca_cert if self.ca_cert else False

            async with session.get(url, headers=headers, verify_ssl=ssl_context) as resp:
                if resp.status == 200:
                    self._connected = True
                else:
                    raise ConnectionError(f"Pod not accessible: {resp.status}")

    async def execute(self, command: str, timeout: int = 30) -> dict[str, object]:
        """Execute a command in the pod.

        NOTE: This is a *basic* implementation. Real Kubernetes exec requires
        WebSocket/SPDY upgrade for interactive streams (stdin/stdout/stderr channels).
        Simple POST to /exec does not work for command execution in most clusters.
        For full support, use the official 'kubernetes' or 'kubernetes-asyncio' client.
        This method currently only performs a basic connectivity check in connect().
        """
        if not aiohttp:
            raise ImportError("aiohttp required for Kubernetes exec")

        # The /exec subresource in Kubernetes does not support simple HTTP POST + JSON
        # for running commands. It requires a streaming protocol upgrade.
        # We return a clear limitation message so users know it's not fully functional.
        return {
            "command": command,
            "error": "Kubernetes exec via simple HTTP is not supported. "
                     "Use official Kubernetes client for full exec functionality. "
                     "This placeholder only verifies pod reachability via connect().",
            "success": False,
            " limitation": True,
        }

    async def close(self) -> None:
        """Close the session."""
        self._connected = False


class KubeExecManager:
    """Manage multiple Kubernetes exec sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, KubeExecSession] = {}

    def create_session(
        self,
        name: str,
        namespace: str,
        pod_name: str,
        container: Optional[str] = None,
        **kwargs,
    ) -> KubeExecSession:
        """Create a named KubeExec session."""
        session = KubeExecSession(
            namespace=namespace,
            pod_name=pod_name,
            container=container,
            **kwargs,
        )
        self._sessions[name] = session
        return session

    def get_session(self, name: str) -> Optional[KubeExecSession]:
        """Get a session by name."""
        return self._sessions.get(name)

    async def execute_on_all(self, command: str) -> dict[str, dict[str, object]]:
        """Execute a command on all sessions."""
        results: dict[str, dict[str, object]] = {}

        async def _exec_one(name: str, session: KubeExecSession) -> tuple[str, dict[str, object]]:
            try:
                if not session.is_connected:
                    await session.connect()
                result = await session.execute(command)
                return name, result
            except Exception as e:
                return name, {"error": str(e), "success": False}

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(_exec_one(name, session))
                for name, session in self._sessions.items()
            ]

        for task in tasks:
            name, result = task.result()
            results[name] = result

        return results

    async def close_all(self) -> None:
        """Close all sessions."""
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()