from __future__ import annotations
import asyncio
from typing import AsyncIterator, Dict, List

class MemoryBus:
    def __init__(self) -> None:
        self._topics: Dict[str, List[asyncio.Queue]] = {}

    async def publish(self, topic: str, item: dict) -> None:
        for q in self._topics.get(topic, []):
            await q.put(item)

    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._topics.setdefault(topic, []).append(q)
        try:
            while True:
                item = await q.get()
                yield item
        finally:
            self._topics[topic].remove(q)
