import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dvc.ui import Console

logger = logging.getLogger(__name__)


class SlowWarning:
    def __init__(self, ui: "Console", msg: str, timeout: int):
        self.msg = msg

        self.start = 0

        self.warning_timeout = timeout
        self._warning_printed = False

        self._thread = None
        self._event = threading.Event()

        self.ui = ui

    def __enter__(self):
        self.start = time.time()

        self._thread = threading.Thread(
            target=self.monitor_progress, name="ourcontextmanager"
        )
        self._thread.start()
        # print("starting")

    def __exit__(self, exc_type, exc_value, traceback):
        # TODO: handle exceptions?
        self._event.set()
        self._thread.join()

    def monitor_progress(self, *args, **kwargs):
        while True:
            if self._event.wait(1):
                break
            if not self._warning_printed and (
                time.time() - self.start >= self.warning_timeout
            ):
                self.ui.warn(self.msg)
                self._warning_printed = True
