"""
Rate limiting stuff
"""

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int, window: float):
        self.max_requests = max_requests
        self.window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self):
        while True:
            sleep_time = 0.0
            with self._lock:
                now = time.time()
                while self._timestamps and self._timestamps[0] < now - self.window:
                    self._timestamps.popleft()
                if len(self._timestamps) >= self.max_requests:
                    sleep_time = self._timestamps[0] + self.window - now + 0.05
                else:
                    self._timestamps.append(now)
                    return
            if sleep_time > 0:
                time.sleep(sleep_time)
