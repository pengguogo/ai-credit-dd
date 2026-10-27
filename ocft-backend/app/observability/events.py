"""run 事件：执行中经内存总线实时推送，结束后持久化到 run_events 表。

@why 单进程部署（比赛演示与评测）用内存总线足够，不引入消息中间件；
     多进程部署时执行中的实时推送只在执行所在进程可见，结束后任一进程都能从表中重放。
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator

# 已结束的通道保留多久（秒），供刚连上的客户端从内存读取完整事件
CLOSED_TTL_SECONDS = 300.0


@dataclass
class _Channel:
    owner_id: str
    # 执行中 run 的只读视图：runId / conversationId / scenarioId / question（已掩码）
    meta: dict
    events: list[tuple[str, dict]] = field(default_factory=list)
    done: bool = False
    closed_at: float | None = None
    cond: threading.Condition = field(default_factory=threading.Condition)


class EventBus:
    def __init__(self) -> None:
        self._channels: dict[str, _Channel] = {}
        self._lock = threading.Lock()

    def open(self, run_id: str, owner_id: str, meta: dict) -> None:
        with self._lock:
            self._prune()
            self._channels[run_id] = _Channel(owner_id=owner_id, meta=dict(meta))

    def get(self, run_id: str) -> _Channel | None:
        with self._lock:
            return self._channels.get(run_id)

    def publish(self, run_id: str, event: tuple[str, dict]) -> None:
        channel = self.get(run_id)
        if channel is None:
            return
        with channel.cond:
            channel.events.append(event)
            channel.cond.notify_all()

    def close(self, run_id: str) -> None:
        channel = self.get(run_id)
        if channel is None:
            return
        with channel.cond:
            channel.done = True
            channel.closed_at = time.monotonic()
            channel.cond.notify_all()

    def iter_events(self, run_id: str, after: int, *, keepalive_seconds: float,
                    max_wait_seconds: float) -> Iterator[tuple[str, dict] | None]:
        """依次产出 eventIndex > after 的事件；等待超过 keepalive 时产出 None（用于心跳）。"""
        channel = self.get(run_id)
        if channel is None:
            return
        position = 0
        deadline = time.monotonic() + max_wait_seconds
        while True:
            with channel.cond:
                while position >= len(channel.events) and not channel.done:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return
                    if not channel.cond.wait(timeout=min(keepalive_seconds, remaining)):
                        break  # 等待超时，先发心跳
                pending = channel.events[position:]
                position = len(channel.events)
                finished = channel.done and position >= len(channel.events)
            if not pending and not finished:
                yield None
            for event in pending:
                if event[1]["eventIndex"] > after:
                    yield event
            if finished:
                return

    def _prune(self) -> None:
        now = time.monotonic()
        stale = [rid for rid, ch in self._channels.items()
                 if ch.done and ch.closed_at is not None and now - ch.closed_at > CLOSED_TTL_SECONDS]
        for rid in stale:
            del self._channels[rid]


bus = EventBus()


class RunEventRecorder:
    """为一次 run 分配事件序号，同时推送总线并留存待持久化。"""

    def __init__(self, run_id: str, event_bus: EventBus = bus) -> None:
        self.run_id = run_id
        self.events: list[tuple[str, dict]] = []
        self._bus = event_bus

    def emit(self, event_type: str, data: dict) -> None:
        event = (event_type, {"eventIndex": len(self.events) + 1, "runId": self.run_id, **data})
        self.events.append(event)
        self._bus.publish(self.run_id, event)
