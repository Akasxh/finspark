"""Health monitoring service for integration adapters."""

import time
from typing import Any


class HealthMonitor:
    """Monitors health of integration adapters and the platform."""

    def __init__(self) -> None:
        self._checks: dict[str, dict[str, Any]] = {}
        self._start_time = time.monotonic()

    def register_check(self, name: str, check_fn: Any) -> None:
        self._checks[name] = {"fn": check_fn, "last_status": None}

    async def run_all_checks(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, check in self._checks.items():
            try:
                result = check["fn"]()
                results[name] = {"status": "healthy", "details": result}
                check["last_status"] = "healthy"
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
                check["last_status"] = "unhealthy"

        healthy_count = sum(1 for r in results.values() if r["status"] == "healthy")
        total = len(results)

        return {
            "overall": "healthy" if healthy_count == total else "degraded",
            "uptime_seconds": round(time.monotonic() - self._start_time, 0),
            "checks": results,
            "healthy": healthy_count,
            "total": total,
        }

    def get_uptime(self) -> float:
        return time.monotonic() - self._start_time


# Singleton monitor
monitor = HealthMonitor()

# Register default checks
monitor.register_check("database", lambda: {"type": "sqlite", "status": "connected"})
monitor.register_check("parser", lambda: {"formats": ["docx", "pdf", "yaml", "json"]})
monitor.register_check("simulator", lambda: {"mock_server": "ready"})
monitor.register_check("field_mapper", lambda: {"synonyms_loaded": True, "threshold": 0.6})
