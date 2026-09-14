def format_bytes_per_second(value: float | int) -> str:
    value = max(0.0, float(value))
    units = ("B/s", "KB/s", "MB/s", "GB/s", "TB/s")
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B/s" else f"{value:.2f} {unit}"
        value /= 1024.0
    raise AssertionError("unreachable")
