"""
A collection of network-related utilities.
"""
import asyncio
import ipaddress
from urllib.parse import urlparse

import aiodns


class URL:
    """Utilities to work with URLs"""

    @staticmethod
    def has_netloc(url: str) -> bool:
        """Check if the argument is a valid network address."""
        parsed = urlparse(url)
        return bool(parsed.netloc)

    @staticmethod
    def ensure_scheme(url: str, default_scheme: str = "https") -> str:
        """Ensure url has schema."""
        parsed = urlparse(url)
        if not parsed.scheme:
            return f'{default_scheme}://{url}'
        return url


class DNS:
    """Domain name utilities."""

    @staticmethod
    async def exists(url: str) -> bool:
        """Check if domain name exists."""
        parsed = urlparse(url)
        address = parsed.netloc.split(":")[0]
        if IP.is_address(address):
            return True

        resolver = aiodns.DNSResolver(loop=asyncio.get_running_loop())
        try:
            result = await resolver.query(address, 'A')
            return len(result) > 0
        except aiodns.error.DNSError:
            return False


class IP:
    """Ip protocol utilities."""

    @staticmethod
    def is_address(address: str) -> bool:
        """Check if string is a valid IPv4 or IPv6 address."""
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False
