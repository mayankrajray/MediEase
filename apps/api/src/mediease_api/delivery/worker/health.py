"""``python -m mediease_api.delivery.worker.health``: the container health check (spec R11a)."""

from mediease_api.delivery.worker.heartbeat import main

if __name__ == "__main__":
    raise SystemExit(main())
