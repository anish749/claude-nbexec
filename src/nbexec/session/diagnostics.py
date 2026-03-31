"""Diagnose connection failures to Jupyter servers."""

import requests
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException


# Exceptions that indicate the WebSocket transport broke,
# rather than a problem with the code being executed.
CONNECTION_ERRORS = (
    WebSocketConnectionClosedException,
    WebSocketTimeoutException,
    ConnectionError,
    OSError,
)

HEALTH_CHECK_TIMEOUT = 5  # seconds


def is_connection_error(exc: Exception) -> bool:
    """Return True if the exception indicates a connection/network failure."""
    if isinstance(exc, CONNECTION_ERRORS):
        return True
    # jupyter_kernel_client raises RuntimeError for lost connections
    if isinstance(exc, RuntimeError) and "connection" in str(exc).lower():
        return True
    return False


def diagnose_connection_error(
    server_url: str,
    token: str | None,
    kernel_id: str | None,
) -> str:
    """Probe the Jupyter server to explain why a connection failed.

    Makes a short HTTP health check and returns a human-readable message
    describing the most likely cause of the failure.
    """
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # First check: can we reach the server at all?
    try:
        resp = requests.get(
            f"{server_url}/api/status",
            headers=headers,
            timeout=HEALTH_CHECK_TIMEOUT,
        )
    except requests.ConnectionError:
        return (
            f"Cannot reach Jupyter server at {server_url}. "
            "Check network connectivity and VPN."
        )
    except requests.Timeout:
        return (
            f"Jupyter server at {server_url} is not responding "
            f"(timed out after {HEALTH_CHECK_TIMEOUT}s)."
        )
    except Exception:
        return (
            f"Cannot reach Jupyter server at {server_url}. "
            "Check network connectivity and VPN."
        )

    if resp.status_code >= 400:
        return (
            f"Jupyter server at {server_url} returned HTTP {resp.status_code}. "
            "The server may be restarting or misconfigured."
        )

    # Server is reachable. If we have a kernel_id, check if the kernel is alive.
    if kernel_id:
        try:
            kresp = requests.get(
                f"{server_url}/api/kernels/{kernel_id}",
                headers=headers,
                timeout=HEALTH_CHECK_TIMEOUT,
            )
        except Exception:
            return (
                f"WebSocket connection lost. Jupyter server at {server_url} "
                "is reachable but the kernel status check failed."
            )

        if kresp.status_code == 404:
            return (
                f"Kernel {kernel_id} is no longer running on {server_url}. "
                "It may have been shut down, restarted, or timed out. "
                "Create a new session to continue."
            )

        if kresp.status_code == 200:
            return (
                f"WebSocket connection lost but kernel {kernel_id} is still "
                f"running on {server_url}. "
                "This is likely a network interruption or proxy/load-balancer timeout. "
                "Reconnecting the session may recover it."
            )

        return (
            f"WebSocket connection lost. Kernel status check returned "
            f"HTTP {kresp.status_code}."
        )

    # Server reachable but no kernel_id to check
    return (
        f"WebSocket connection to {server_url} was lost. "
        "The server is reachable, so this is likely a transient network issue."
    )
