"""事件总线 — 支持订阅、发布、持久化."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from .models import Event, EventType


class EventBus:
    """异步事件总线."""

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[[Event], Any]]] = {}
        self._history: List[Event] = []
        self._lock = asyncio.Lock()

    def subscribe(
        self, event_type: EventType, handler: Callable[[Event], Any]
    ) -> None:
        """订阅事件."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(
        self, event_type: EventType, handler: Callable[[Event], Any]
    ) -> None:
        """取消订阅."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: Event) -> None:
        """发布事件."""
        async with self._lock:
            self._history.append(event)

        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                # 事件处理失败不应影响其他处理器
                print(f"[EventBus] Handler error for {event.type}: {e}")

    def get_history(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
    ) -> List[Event]:
        """获取事件历史."""
        events = self._history
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events

    def clear_history(self) -> None:
        """清空历史."""
        self._history.clear()
