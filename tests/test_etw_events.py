from __future__ import annotations

import pytest

from net_monitor.collectors.etw.constants import PROVIDER_GUID
from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent
from net_monitor.collectors.etw.parser import EventIdentity, parse_network_event


def test_network_event_rejects_negative_size() -> None:
    with pytest.raises(ValueError):
        NetworkEvent(0.0, 1, NetworkDirection.SEND, -1)


@pytest.mark.parametrize(
    ("task", "opcode", "direction", "protocol"),
    [
        (10, 10, NetworkDirection.SEND, "tcp"),
        (10, 11, NetworkDirection.RECEIVE, "tcp"),
        (11, 42, NetworkDirection.SEND, "udp"),
        (11, 43, NetworkDirection.RECEIVE, "udp"),
    ],
)
def test_parser_maps_manifest_backed_direction(
    task: int,
    opcode: int,
    direction: NetworkDirection,
    protocol: str,
) -> None:
    identity = EventIdentity(PROVIDER_GUID, 10, 0, task, opcode, 123.0)
    values = {"PID": 4321, "size": 2048}
    event = parse_network_event(identity, values.__getitem__)
    assert event == NetworkEvent(123.0, 4321, direction, 2048, protocol)


def test_parser_ignores_unknown_version() -> None:
    identity = EventIdentity(PROVIDER_GUID, 10, 99, 10, 10, 0.0)
    assert parse_network_event(identity, {"PID": 1, "size": 1}.__getitem__) is None


def test_parser_ignores_unknown_opcode() -> None:
    identity = EventIdentity(PROVIDER_GUID, 10, 0, 10, 200, 0.0)
    assert parse_network_event(identity, {"PID": 1, "size": 1}.__getitem__) is None


def test_parser_ignores_zero_size() -> None:
    identity = EventIdentity(PROVIDER_GUID, 10, 0, 10, 10, 0.0)
    assert parse_network_event(identity, {"PID": 1, "size": 0}.__getitem__) is None
