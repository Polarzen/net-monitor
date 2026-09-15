from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from net_monitor.collectors.etw.constants import (
    PROVIDER_GUID,
    SUPPORTED_EVENT_VERSION,
    TCP_RECEIVE_OPCODE,
    TCP_SEND_OPCODE,
    TCP_TASK,
    UDP_RECEIVE_OPCODE,
    UDP_SEND_OPCODE,
    UDP_TASK,
)
from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent


@dataclass(frozen=True, slots=True)
class EventIdentity:
    provider_guid: str
    event_id: int
    version: int
    task: int
    opcode: int
    timestamp: float


_DIRECTION_BY_TASK_OPCODE: dict[tuple[int, int], tuple[NetworkDirection, str]] = {
    (TCP_TASK, TCP_SEND_OPCODE): (NetworkDirection.SEND, "tcp"),
    (TCP_TASK, TCP_RECEIVE_OPCODE): (NetworkDirection.RECEIVE, "tcp"),
    (UDP_TASK, UDP_SEND_OPCODE): (NetworkDirection.SEND, "udp"),
    (UDP_TASK, UDP_RECEIVE_OPCODE): (NetworkDirection.RECEIVE, "udp"),
}


def parse_network_event(
    identity: EventIdentity,
    read_property: Callable[[str], int],
) -> NetworkEvent | None:
    if identity.provider_guid.casefold() != PROVIDER_GUID.casefold():
        return None
    if identity.version != SUPPORTED_EVENT_VERSION:
        return None

    direction_info = _DIRECTION_BY_TASK_OPCODE.get((identity.task, identity.opcode))
    if direction_info is None:
        return None

    direction, protocol = direction_info
    pid = read_property("PID")
    size = read_property("size")
    if size <= 0:
        return None

    return NetworkEvent(
        timestamp=identity.timestamp,
        pid=pid,
        direction=direction,
        size=size,
        protocol=protocol,
    )
