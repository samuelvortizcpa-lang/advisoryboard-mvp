"""
Process-based isolation for CPU-intensive tasks.

Uses ProcessPoolExecutor to offload heavy work (OCR, PDF processing) to a
separate process, keeping the main asyncio event loop responsive.

Max 1 worker to avoid OOM on Railway Hobby plan (512MB–1GB RAM).
"""

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

_executor = ProcessPoolExecutor(max_workers=1)


async def run_in_process(func, *args, **kwargs):
    """Run a CPU-intensive function in a separate process.

    This prevents OCR/PDF processing from blocking the asyncio event loop,
    keeping the API responsive during heavy document processing.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            partial(func, *args, **kwargs),
        )
        return result
    except Exception as e:
        logger.error("Background process failed: %s", e)
        raise


def shutdown_executor():
    """Call during app shutdown to clean up the process pool."""
    _executor.shutdown(wait=False)
