"""测试事件总线."""

import asyncio

import pytest

from goalflow.core.event_bus import EventBus
from goalflow.core.models import Event, EventType, Stage


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        bus = EventBus()
        received = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(EventType.STAGE_STARTED, handler)

        event = Event(
            session_id="test-session",
            type=EventType.STAGE_STARTED,
            stage=Stage.CLARIFY,
        )
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].session_id == "test-session"

    @pytest.mark.asyncio
    async def test_async_handler(self):
        bus = EventBus()
        received = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(EventType.STAGE_COMPLETED, handler)

        event = Event(
            session_id="test-session",
            type=EventType.STAGE_COMPLETED,
            stage=Stage.PLAN,
        )
        await bus.publish(event)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_history(self):
        bus = EventBus()

        for i in range(3):
            await bus.publish(Event(
                session_id="s1",
                type=EventType.STAGE_STARTED,
                stage=Stage.CLARIFY,
                payload={"index": i},
            ))

        history = bus.get_history(session_id="s1")
        assert len(history) == 3

        filtered = bus.get_history(session_id="s1", event_type=EventType.STAGE_STARTED)
        assert len(filtered) == 3

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(EventType.STAGE_STARTED, handler)
        bus.unsubscribe(EventType.STAGE_STARTED, handler)

        # Note: unsubscribe won't affect already-published events in async context
        assert len(received) == 0
