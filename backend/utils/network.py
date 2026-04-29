import asyncio
import ipaddress
import socket
import httpx

async def prevent_ssrf_hook(request: httpx.Request) -> None:
    """Event hook to prevent SSRF by blocking access to restricted IP addresses."""
    host = request.url.host
    if not host:
        return
    try:
        loop = asyncio.get_event_loop()
        addrinfo = await loop.getaddrinfo(host, None)
        for _, _, _, _, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                raise RuntimeError(
                    "URL resolves to a restricted network.",
                )
    except socket.gaierror:
        # Ignore resolution errors here, they will fail naturally during the request
        pass

def get_ssrf_event_hooks() -> dict:
    """Helper to return the event hooks dict for httpx."""
    return {"request": [prevent_ssrf_hook]}
