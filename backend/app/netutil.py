"""The real client address, for rate limits."""

from fastapi import Request

from .config import get_settings


def client_ip(request: Request) -> str:
    """With TRUSTED_PROXY_HOPS = N > 0, the Nth address from the right of X-Forwarded-For.

    Each proxy appends the address it received the request from, so the right-most entries are
    written by our own proxies; everything further left is chosen by the client and can be faked.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        forwarded = [a.strip() for h in request.headers.getlist("x-forwarded-for") for a in h.split(",")]
        forwarded = [a for a in forwarded if a]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "?"
