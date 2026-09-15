from __future__ import annotations

from net_monitor.collectors.etw.api import GUID
from net_monitor.collectors.etw.constants import PROVIDER_GUID


def test_guid_round_trip() -> None:
    guid = GUID.from_string(PROVIDER_GUID)
    assert "{" + str(guid.as_uuid()).upper() + "}" == PROVIDER_GUID
