import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only public HTTP and HTTPS URLs are allowed.")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".local"):
        raise UnsafeUrlError("Local network addresses are not allowed.")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port)}
    except socket.gaierror as exc:
        raise UnsafeUrlError("The hostname could not be resolved.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise UnsafeUrlError("Private, loopback, and reserved addresses are not allowed.")

