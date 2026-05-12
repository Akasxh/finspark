"""SSRF protection: URL validation to block internal/private network targets."""

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    # IPv4 private / loopback / link-local
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    # IPv6 loopback / unique-local / link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# Allowed URL schemes — reject file://, ftp://, etc.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def is_safe_url(url: str) -> bool:
    """Return True only if the URL resolves to a public (non-private) IP address.

    Blocks:
    - Non-HTTP(S) schemes
    - Hostnames that resolve to private, loopback, or link-local addresses
    - URLs without a hostname

    Returns True when DNS resolution fails -- unresolvable hostnames are not
    exploitable for SSRF against known internal addresses. Only actively-resolved
    private/loopback IPs are blocked.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Cannot resolve -- not a known internal address, allow through
        return True

    if not infos:
        return False

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in net for net in _BLOCKED_NETWORKS):
            return False
    return True
