"""Desktop launcher for the local FastAPI control center."""
import threading
import time

import uvicorn
import webview


def start_backend():
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    threading.Thread(target=start_backend, daemon=True).start()
    # Give the local server a moment to bind before opening the desktop window.
    time.sleep(1.0)
    webview.create_window(
        "Forex AI Hybrid Scalper",
        "http://127.0.0.1:8000",
        width=1360,
        height=900,
        min_size=(900, 650),
    )
    webview.start()
