# -*- coding: utf-8 -*-

import platform
import sys
import uuid

CURSOR_CLIENT_KEY = b"182ca6255603669db02eae7703b593611e33b37a748ad64d7e6817c5e4538035"
CURSOR_CHECKSUM = b"pjU3LzCn323291706119eb9147e937e4cfbfb9ad2b9177411972a7d4e32cf1864dce02bf/620842d179f31a42da1a7ba3c473c517821f741c71037e257be0a8e302eb31e3"
CURSOR_API_URL = "https://api2.cursor.sh"


def makeHeaders(bearerToken: str):
    machine = platform.machine()
    if machine in ("AMD64", "x86_64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = machine

    return {
        b"authorization": f"Bearer {bearerToken}".encode(),
        b"Accept-Encoding": b"gzip",
        b"connect-protocol-version": b"1",
        b"content-type": b"application/proto",
        b"user-agent": b"connect-es/1.6.1",
        b"x-amzn-trace-id": f"Root={uuid.uuid4()}".encode(),
        b"x-client-key": CURSOR_CLIENT_KEY,
        b"x-cursor-checksum": CURSOR_CHECKSUM,
        b"x-cursor-client-version": b"2.4.28",
        b"x-cursor-config-version": str(uuid.uuid4()).encode(),
        b"x-cursor-client-arch": arch.encode(),
        b"x-cursor-client-device-type": b"desktop",
        b"x-cursor-client-os": sys.platform.encode(),
        b"x-cursor-client-type": b"ide",
        b"x-cursor-config-version": b"59f30bd3-78be-4696-93e5-07ea3dceb531",
        b"x-cursor-timezone": b"Asia/Shanghai",
        b"x-ghost-mode": b"true",
        b"x-request-id": str(uuid.uuid4()).encode(),
        b"Host": b"api2.cursor.sh"
    }
