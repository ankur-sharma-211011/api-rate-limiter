import time

from fastapi import HTTPException, Request
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from redis_connection import r

# ip spoofing protection is not currently implemented
# intended approach is to allow access to only authenticated users


def get_ip(request: Request):
    return request.client.host


def reject():
    raise HTTPException(status_code=429, detail="Too many requests")


# inteded to enforce either failure modes
# 1. FAIL OPEN -> use "fail_open"
# 2. FAIL CLOSED -> use "fail_closed"


def execute_script(script, fallback, FAILURE_POLICY, *args):

    if FAILURE_POLICY not in ("fail_open", "fail_closed", "fallback_memory"):
        raise ValueError("Invalid failure policy")

    try:
        return r.eval(script, *args)

    except (RedisConnectionError, RedisTimeoutError):
        if FAILURE_POLICY == "fail_open":
            return None

        if FAILURE_POLICY == "fallback_memory":
            if fallback is None:
                raise HTTPException(
                    status_code=503, detail="Memory fallback unavailable"
                )

            return fallback()

        raise HTTPException(status_code=503, detail="Rate limiting service unavailable")


# Lua scripts for atomic execution of redis commands

FIXED_WINDOW_SCRIPT = """

    local count = redis.call("INCR", KEYS[1])
    
    if count == 1 then
        redis.call("EXPIRE", KEYS[1], ARGV[1])
    end
    
    local limit = tonumber(ARGV[2])
    
    if count > limit then
        return 0
    end

    return 1
"""

SLIDING_WINDOW_SCRIPT = """
    
    local key = KEYS[1];
    local now = tonumber(ARGV[1]);
    local window = tonumber(ARGV[2]);
    local limit = tonumber(ARGV[3]);
    local member = ARGV[4];

    redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)

    local count = redis.call("ZCARD", key)

    if count >= limit then
       return 0
    end

    redis.call("ZADD", key, now, member)
    redis.call("EXPIRE", key, window)

    return 1
"""

TOKEN_BUCKET_SCRIPT = """

    local key = KEYS[1]
    
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    
    -- Read existing bucket data
    local data = redis.call("HMGET", key, "tokens", "last")
    
    local tokens
    local last
    
    if data[1] then
        tokens = tonumber(data[1])
        last = tonumber(data[2])
    
        -- Refill tokens according to elapsed time
        tokens = math.min(
            capacity,
            tokens + (now - last) * refill_rate
        )
    else
        -- First request: start with a full bucket
        tokens = capacity
    end
    
    -- Check whether one token is available
    if tokens < 1 then
    
        redis.call("HSET", key,
            "tokens", tokens,
            "last", now
        )
    
        redis.call("EXPIRE", key, 86400)
    
        return 0
    end

    -- Consume one token
    tokens = tokens - 1
    
    redis.call("HSET", key,
        "tokens", tokens,
        "last", now
    )
    
    redis.call("EXPIRE", key, 86400)
    
    return 1
"""


LEAKY_BUCKET_SCRIPT = """

    local key = KEYS[1]
    
    local capacity = tonumber(ARGV[1])
    local leak_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    
    -- Read existing bucket state
    local data = redis.call("HMGET", key, "water", "last")
    
    local water
    local last
    
    if data[1] then
        water = tonumber(data[1])
        last = tonumber(data[2])
    
        -- Leak water according to elapsed time
        water = math.max(
            0,
            water - (now - last) * leak_rate
        )
    else
        -- First request: bucket is empty
        water = 0
    end
    
    -- Check whether another request can enter
    if water + 1 > capacity then
    
        redis.call("HSET", key,
            "water", water,
            "last", now
        )
    
        redis.call("EXPIRE", key, 86400)
    
        return 0
    end
    
    -- Add the incoming request
    water = water + 1
    
    redis.call("HSET", key,
        "water", water,
        "last", now
    )
    
    redis.call("EXPIRE", key, 86400)
    
    return 1
    """


class FixedWindowLimiter:
    def __init__(self, limit=5, window=60, fallback=None, FAILURE_POLICY="fail_closed"):
        self.limit = limit
        self.window = window
        self.fallback = fallback
        self.FAILURE_POLICY = FAILURE_POLICY

    def check(self, request: Request):
        ip = get_ip(request)
        window_id = int(time.time() // self.window)
        key = f"fixed:{ip}:{window_id}"

        # issue without this is that lambda itself is a function
        # so lambda: self.fallback(ip) can never be None
        # when self.fallback is None
        # so deliberately checking and assigning None for currect
        # working and repeating this in all constructors

        fallback = (lambda: self.fallback(ip)) if self.fallback is not None else None

        result = execute_script(
            FIXED_WINDOW_SCRIPT,
            fallback,
            self.FAILURE_POLICY,
            1,
            key,
            self.window,
            self.limit,
        )

        if result == 0:
            reject()


class SlidingWindowLimiter:
    def __init__(self, limit=5, window=60, fallback=None, FAILURE_POLICY="fail_closed"):
        self.limit = limit
        self.window = window
        self.fallback = fallback
        self.FAILURE_POLICY = FAILURE_POLICY

    def check(self, request: Request):
        ip = get_ip(request)
        key = f"sliding:{ip}"
        now = time.time()

        fallback = (lambda: self.fallback(ip)) if self.fallback is not None else None

        result = execute_script(
            SLIDING_WINDOW_SCRIPT,
            fallback,
            self.FAILURE_POLICY,
            1,
            key,
            now,
            self.window,
            self.limit,
            str(time.time_ns()),
        )

        if result == 0:
            reject()


class LeakyBucketLimiter:
    def __init__(
        self, capacity=5, leak_rate=5 / 60, fallback=None, FAILURE_POLICY="fail_closed"
    ):
        self.capacity = capacity
        self.leak_rate = leak_rate
        self.fallback = fallback
        self.FAILURE_POLICY = FAILURE_POLICY

    def check(self, request: Request):
        ip = get_ip(request)
        key = f"leaky:{ip}"
        now = time.time()

        fallback = (lambda: self.fallback(ip)) if self.fallback is not None else None

        result = execute_script(
            LEAKY_BUCKET_SCRIPT,
            fallback,
            self.FAILURE_POLICY,
            1,
            key,
            self.capacity,
            self.leak_rate,
            now,
        )

        if result == 0:
            reject()


class TokenBucketLimiter:
    def __init__(
        self,
        capacity=5,
        refill_rate=5 / 60,
        fallback=None,
        FAILURE_POLICY="fail_closed",
    ):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.fallback = fallback
        self.FAILURE_POLICY = FAILURE_POLICY

    def check(self, request: Request):
        ip = get_ip(request)
        key = f"token:{ip}"
        now = time.time()

        fallback = (lambda: self.fallback(ip)) if self.fallback is not None else None

        result = execute_script(
            TOKEN_BUCKET_SCRIPT,
            fallback,
            self.FAILURE_POLICY,
            1,
            key,
            self.capacity,
            self.refill_rate,
            now,
        )

        if result == 0:
            reject()
