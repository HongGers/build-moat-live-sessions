import ipaddress
from urllib.parse import urlparse, urlunparse


MAX_URL_LENGTH = 2048

BLOCKED_DOMAINS = {
    "evil.com",
    "malware.example.com",
    "phishing.example.com",
}


def _is_blocked_host(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS)


def _is_private_or_local_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved


def validate_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        raise ValueError("URL is required")
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("URL is too long")

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("URL scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URL must not include credentials")

    host = parsed.hostname.lower().rstrip(".")
    if _is_blocked_host(host) or _is_private_or_local_ip(host):
        raise ValueError("URL host is blocked")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL includes an invalid port") from exc

    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = parsed.path or ""
    if path == "/":
        path = ""
    elif path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, netloc, path, "", parsed.query, parsed.fragment))
