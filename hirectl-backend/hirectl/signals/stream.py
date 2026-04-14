"""
In-memory pub/sub broker for live signal events.

This is process-local and intended for the current single-process dev setup.
"""

import asyncio
import json
from typing import Any


class SignalStreamBroker:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._queues.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            self._queues.discard(queue)

    async def publish(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        async with self._lock:
            queues = list(self._queues)

        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue


signal_stream_broker = SignalStreamBroker()
