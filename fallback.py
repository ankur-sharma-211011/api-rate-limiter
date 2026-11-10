# import time
# import threading

# class MemoryFallback:

#     def __init__(self, limit=10, window=60):
#         self.limit = limit
#         self.window = window
#         self.buckets = {}
#         self.lock = threading.Lock()

#     def allow_request(self, ip):

#         now = time.monotonic()

#         with self.lock:

#             window_id = int(now // self.window)

#             key = (ip, window_id)

#             count = self.buckets.get(key, 0)

#             if count >= self.limit:
#                 return False

#             self.buckets[key] = count + 1

#             return True

import threading
import time


class MemoryFallback:
    def __init__(self, limit=10, window=60):
        self.limit = limit
        self.window = window
        self.buckets = {}
        self.lock = threading.Lock()
        self.last_cleanup_window = None

    def allow_request(self, ip):

        now = time.monotonic()

        with self.lock:
            window_id = int(now // self.window)

            # Cleanup expired buckets once per new window
            if self.last_cleanup_window != window_id:
                expired_keys = [key for key in self.buckets if key[1] < window_id]

                for key in expired_keys:
                    del self.buckets[key]

                self.last_cleanup_window = window_id

            key = (ip, window_id)

            count = self.buckets.get(key, 0)

            if count >= self.limit:
                return False

            self.buckets[key] = count + 1

            return True
