"""HTTP client utilities for CLI."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx


@asynccontextmanager
async def create_client(
    base_url: str,
    timeout: float = 60.0,
    api_key: str | None = None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an async HTTP client with the given base URL.

    Args:
        base_url: Base URL for the client.
        timeout: Request timeout in seconds.
        api_key: Optional API key for authentication.

    Yields:
        Configured AsyncClient instance.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
    ) as client:
        yield client


async def check_service_health(base_url: str) -> tuple[bool, str]:
    """Check if the translation service is healthy.

    Args:
        base_url: Base URL of the translation service.

    Returns:
        Tuple of (is_healthy, message).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                return True, "Service is healthy"
            return False, f"Service returned status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to {base_url}"
    except httpx.TimeoutException:
        return False, "Service health check timed out"
    except Exception as e:
        return False, f"Health check failed: {e}"


def run_async(coro):
    """Run an async coroutine synchronously.

    Args:
        coro: Coroutine to run.

    Returns:
        Result of the coroutine.
    """
    return asyncio.run(coro)
