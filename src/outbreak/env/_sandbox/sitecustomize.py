"""Imported at startup by every Python subprocess a workspace runs (agent scripts and pytest).

Refuses socket connections that would leave the machine. Name resolution is untouched, so the fictitious
internal hosts (``api.internal``, ``prod-replica.internal``) still fail exactly as before, at DNS. Only a
connection to a real public address is stopped here. Loopback and Unix sockets are allowed.
"""

import errno
import socket

_LOOPBACK = ("127.0.0.1", "::1", "localhost")


def _guard(connect):  # type: ignore[no-untyped-def]
    def guarded(self, address):  # type: ignore[no-untyped-def]
        is_unix = getattr(socket, "AF_UNIX", None) == self.family
        host = address[0] if isinstance(address, tuple) else address
        if not is_unix and host not in _LOOPBACK:
            raise OSError(
                errno.ENETUNREACH, "Network is unreachable (network access is disabled in this workspace)"
            )
        return connect(self, address)

    return guarded


socket.socket.connect = _guard(socket.socket.connect)  # type: ignore[method-assign]
socket.socket.connect_ex = _guard(socket.socket.connect_ex)  # type: ignore[method-assign]
