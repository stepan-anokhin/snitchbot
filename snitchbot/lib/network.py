"""
A collection of network-related utilities.
"""
import asyncio
from urllib.parse import urlparse

import aiodns


def is_valid_url(url: str) -> bool:
    """Validate url."""
    parsed = urlparse(url)
    return bool(parsed.netloc)


async def domain_exists(url: str) -> bool:
    """Check if domain name exists."""
    parsed = urlparse(url)
    domain_name = parsed.netloc.split(":")[0]
    resolver = aiodns.DNSResolver(loop=asyncio.get_running_loop())
    try:
        result = await resolver.query(domain_name, 'A')
        return len(result) > 0
    except aiodns.error.DNSError:
        return False
