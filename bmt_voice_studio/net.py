"""Shared network helpers — Windows often fails GitHub / Edge TTS on broken IPv6 DNS."""

from __future__ import annotations

import socket
from contextlib import contextmanager

_installed = False
_original_getaddrinfo = socket.getaddrinfo


def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
    resolver = _original_getaddrinfo
    if family == 0:
        try:
            return resolver(host, port, socket.AF_INET, type, proto, flags)
        except OSError:
            pass
    return resolver(host, port, family, type, proto, flags)


def install_ipv4_preference() -> None:
    """Prefer IPv4 for the rest of the process (WinError 11001 / getaddrinfo failed)."""
    global _installed
    if _installed:
        return
    socket.getaddrinfo = _ipv4_first
    _installed = True


@contextmanager
def prefer_ipv4():
    """Temporarily prefer IPv4, then restore whatever resolver was active."""
    previous = socket.getaddrinfo
    socket.getaddrinfo = _ipv4_first
    try:
        yield
    finally:
        socket.getaddrinfo = previous
