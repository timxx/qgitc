# -*- coding: utf-8 -*-

import socket
import struct
from datetime import datetime, timezone

from PySide6.QtCore import QDateTime, QTimeZone

NTP_SERVER = "pool.ntp.org"
NTP_PORT = 123
TIME1970 = 2208988800  # seconds since 1900-01-01 00:00:00 UTC


def getNtpDateTime():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            data = b'\x1b' + 47 * b'\0'
            s.sendto(data, (NTP_SERVER, NTP_PORT))
            data, _ = s.recvfrom(48)
            if len(data) == 48:
                t = struct.unpack("!I", data[40:44])[0]
                t -= TIME1970
                utcTime = datetime.fromtimestamp(t, timezone.utc)
                return QDateTime(utcTime.date(), utcTime.time(), QTimeZone.UTC).toLocalTime()
    except:
        pass
    return None
