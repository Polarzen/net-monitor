from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent
from net_monitor.collectors.etw.network import NetworkAggregator


def test_aggregator_accumulates_send_and_receive_by_pid() -> None:
    aggregator = NetworkAggregator()
    aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 100))
    aggregator.record(NetworkEvent(2.0, 10, NetworkDirection.SEND, 50))
    aggregator.record(NetworkEvent(3.0, 10, NetworkDirection.RECEIVE, 75))
    aggregator.record(NetworkEvent(4.0, 20, NetworkDirection.RECEIVE, 25))

    snapshot = aggregator.snapshot()

    assert snapshot[10].bytes_sent == 150
    assert snapshot[10].bytes_received == 75
    assert snapshot[10].send_events == 2
    assert snapshot[10].receive_events == 1
    assert snapshot[20].bytes_sent == 0
    assert snapshot[20].bytes_received == 25
    assert snapshot[20].send_events == 0
    assert snapshot[20].receive_events == 1


def test_zero_byte_event_is_counted_without_changing_bytes() -> None:
    aggregator = NetworkAggregator()
    aggregator.record(NetworkEvent(1.0, 7, NetworkDirection.SEND, 0))
    totals = aggregator.snapshot()[7]
    assert totals.bytes_sent == 0
    assert totals.send_events == 1


def test_snapshot_does_not_expose_mutable_internal_state() -> None:
    aggregator = NetworkAggregator()
    aggregator.record(NetworkEvent(1.0, 1, NetworkDirection.SEND, 10))
    snapshot = aggregator.snapshot()
    snapshot.clear()
    assert 1 in aggregator.snapshot()


def test_retain_pids_discards_inactive_processes() -> None:
    aggregator = NetworkAggregator()
    aggregator.record(NetworkEvent(1.0, 1, NetworkDirection.SEND, 10))
    aggregator.record(NetworkEvent(1.0, 2, NetworkDirection.RECEIVE, 20))

    aggregator.retain_pids({2})

    snapshot = aggregator.snapshot()
    assert 1 not in snapshot
    assert snapshot[2].bytes_received == 20


def test_retain_pids_returns_an_atomic_removed_snapshot() -> None:
    aggregator = NetworkAggregator()
    aggregator.record(NetworkEvent(1.0, 1, NetworkDirection.SEND, 100))
    aggregator.record(NetworkEvent(1.0, 2, NetworkDirection.RECEIVE, 200))

    removed = aggregator.retain_pids({2})
    aggregator.record(NetworkEvent(2.0, 1, NetworkDirection.SEND, 50))

    assert removed[1].bytes_sent == 100
    assert removed[1].send_events == 1
    assert aggregator.snapshot()[1].bytes_sent == 50
    assert aggregator.snapshot()[2].bytes_received == 200


def test_aggregator_is_thread_safe_for_basic_updates() -> None:
    aggregator = NetworkAggregator()

    def add_many() -> None:
        for _ in range(250):
            aggregator.record(NetworkEvent(1.0, 99, NetworkDirection.SEND, 4))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: add_many(), range(4)))

    totals = aggregator.snapshot()[99]
    assert totals.bytes_sent == 4000
    assert totals.send_events == 1000
