from fastapi import Depends, FastAPI

from fallback import MemoryFallback
from rate_limiters import (
    FixedWindowLimiter,
    LeakyBucketLimiter,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)

app = FastAPI()

# common fallback for any ip for all types of services
# we intent to pass only the function reference in argument not whole
# object

memory_fallback = MemoryFallback(limit=10, window=60)

fixed_limiter = FixedWindowLimiter(
    limit=5,
    window=60,
    fallback=memory_fallback.allow_request,
    FAILURE_POLICY="fail_closed",
)

sliding_limiter = SlidingWindowLimiter(
    limit=5,
    window=60,
    fallback=memory_fallback.allow_request,
    FAILURE_POLICY="fail_closed",
)

leaky_limiter = LeakyBucketLimiter(
    capacity=5,
    leak_rate=5 / 60,
    fallback=memory_fallback.allow_request,
    FAILURE_POLICY="fail_closed",
)

token_limiter = TokenBucketLimiter(
    capacity=5,
    refill_rate=5 / 60,
    fallback=memory_fallback.allow_request,
    FAILURE_POLICY="fail_closed",
)


@app.get("/fixed", dependencies=[Depends(fixed_limiter.check)])
def fixed_endpoint():
    return {"message": "Fixed window request allowed"}


@app.get("/sliding", dependencies=[Depends(sliding_limiter.check)])
def sliding_endpoint():
    return {"message": "Sliding window request allowed"}


@app.get("/leaky", dependencies=[Depends(leaky_limiter.check)])
def leaky_endpoint():
    return {"message": "Leaky bucket request allowed"}


@app.get("/token", dependencies=[Depends(token_limiter.check)])
def token_endpoint():
    return {"message": "Token bucket request allowed"}
