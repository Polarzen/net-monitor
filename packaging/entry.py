"""Thin GUI entry point; PyInstaller's windowed bootloader reports startup errors."""
from net_monitor.app import main

raise SystemExit(main())
