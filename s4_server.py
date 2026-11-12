"""Local S4 server with graceful SIGINT/SIGTERM lease shutdown."""

import os
import signal

from s4_app import create_app


def main():
    app = create_app()
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5004")), debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        lifecycle = app.extensions.get("registry_lifecycle")
        if lifecycle is not None:
            lifecycle.stop()


if __name__ == "__main__":
    main()
