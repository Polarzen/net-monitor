from __future__ import annotations

import json
import time

from net_monitor.collectors.etw.api import EtwError
from net_monitor.collectors.etw.session import EtwSession


def main() -> int:
    session: EtwSession | None = None
    try:
        session = EtwSession(lambda event: None)
        session.start()
        time.sleep(0.1)
        session.stop()
    except EtwError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "api": exc.api_name,
                    "error_code": exc.error_code,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "unexpected_error": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    finally:
        if session is not None and session.started:
            try:
                session.stop()
            except EtwError:
                pass

    print(json.dumps({"success": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
