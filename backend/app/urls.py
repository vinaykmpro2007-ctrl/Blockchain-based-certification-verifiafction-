"""Work out the address that goes into QR codes and "copy link" buttons.

A QR code printed with http://localhost:8000/... only works on the computer
that runs the server: a phone scanning it looks for "localhost" on the phone
itself and shows a "page can't be reached / reload page" error.

Order of preference:
  1. PUBLIC_BASE_URL from .env (use this on a real domain or behind a proxy).
  2. The address the request came in on.
  3. If that address is localhost / 127.0.0.1, the computer's LAN address
     instead, so a phone on the same Wi-Fi can open the link.
"""

import ipaddress
import os
import socket
from urllib.parse import urlsplit, urlunsplit

LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "0.0.0.0", "::", "::1"}


def is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return True

    if hostname.lower() in LOOPBACK_NAMES:
        return True

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    return address.is_loopback or address.is_unspecified


def lan_ip() -> str | None:
    """This computer's address on the local network, or None if unknown.

    Connecting a UDP socket sends no packets; it only makes the OS pick the
    network interface that would be used to reach the internet.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1: never actually contacted
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()

    return None if is_loopback(address) else address


def public_base_url(request_base_url: str) -> str:
    """Base address (no trailing slash) for links that other devices open."""
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()

    if configured:
        return configured.rstrip("/")

    parts = urlsplit(request_base_url)

    if is_loopback(parts.hostname):
        address = lan_ip()

        if address:
            host = f"[{address}]" if ":" in address else address
            netloc = f"{host}:{parts.port}" if parts.port else host
            parts = parts._replace(netloc=netloc)

    return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
