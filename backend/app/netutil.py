"""The real client address, for rate limits, and addresses the server must never call."""

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import Request

from .config import get_settings

# Cloud metadata services hand out the server's own credentials to whoever asks from inside.
# The AI server address is typed by the platform owner, so it must not point there (a local
# Ollama or a private vLLM server is fine).
_METADATA_HOSTS = {"metadata", "metadata.google.internal", "metadata.goog", "instance-data",
                   "instance-data.ec2.internal"}
_METADATA_IPS = {ipaddress.ip_address("100.100.100.200"), ipaddress.ip_address("fd00:ec2::254")}


def _literal_ip(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:  # short and numeric IPv4 forms the resolver also accepts: 2852039166, 0xa9.254.169.254
        return ipaddress.ip_address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def is_metadata_url(url: str) -> bool:
    """True when the address points to a cloud metadata service (169.254.x.x and friends)."""
    try:
        host = (urlparse((url or "").strip()).hostname or "").rstrip(".").lower()
    except ValueError:
        return True  # not a valid address: never call it
    if not host:
        return False
    if host in _METADATA_HOSTS:
        return True
    ip = _literal_ip(host)
    if ip is None:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_link_local or ip in _METADATA_IPS


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
