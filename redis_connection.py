import os

import redis

r = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# Check whether Redis is reachable
# r.ping()
