# The MIT License (MIT)
#
# Copyright (c) 2019 Brent Rubell for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
`adafruit_ntp`
================================================================================
Network Time Protocol (NTP) helper for CircuitPython
 * Author(s): Brent Rubell
Implementation Notes
--------------------
**Hardware:**
**Software and Dependencies:**
 * Adafruit CircuitPython firmware for the supported boards:
   https://github.com/adafruit/circuitpython/releases
"""
import struct
import time

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_NTP.git"

NTP_TO_UNIX_EPOCH = 2208988800  # 1970-01-01 00:00:00

class NTP:
    """Network Time Protocol (NTP) helper module for CircuitPython.
    This module does not handle daylight savings or local time. It simply requests
    UTC from a NTP server.
    :param object socketpool: A socket provider such as CPython's `socket` module.
    """

    def __init__(self, socketpool, *, server="pool.ntp.org", port=123):
        self._pool = socketpool
        self._server = server
        self._port = port
        self._packet = bytearray(48)


        # This is our estimated start time for the monotonic clock.
        # We adjust it based on the ntp responses.
        self._monotonic_start = 0

        self.next_sync = 0

    @property
    def datetime(self):
        if time.monotonic_ns() > self.next_sync:
            self._packet[0] = 0b00100011  # Not leap second, NTP version 4, Client mode
            for i in range(1, len(self._packet)):
                self._packet[i] = 0
            with self._pool.socket(self._pool.AF_INET, self._pool.SOCK_DGRAM) as sock:
                sock.sendto(self._packet, (self._server, self._port))
                size, address = sock.recvfrom_into(self._packet)
                # Get the time in the context to minimize the difference between it and receiving
                # the packet.
                destination = time.monotonic_ns()
            poll = struct.unpack_from("!B", self._packet, offset=2)[0]
            self.next_sync = destination + (2 ** poll) * 1_000_000_000
            seconds = struct.unpack_from("!I", self._packet, offset=len(self._packet) - 8)[0]
            self._monotonic_start = seconds - NTP_TO_UNIX_EPOCH - (destination // 1_000_000_000)

        return time.localtime(time.monotonic_ns() // 1_000_000_000 + self._monotonic_start)