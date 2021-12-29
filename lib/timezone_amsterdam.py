from adafruit_datetime import datetime, timedelta, tzinfo


class TimeZoneAmsterdam(tzinfo):
    def __new__(cls):
        return super(tzinfo, cls).__new__(cls)

    def utcoffset(self, dt):
        transition = self._get_transition(dt);
        return timedelta(hours=transition[1])

    def tzname(self, dt):
        return "Europe/Amsterdam"

    def dst(self, dt):
        if self._get_transition(dt)[2]:
            return timedelta(hours=1)
        else:
            return timedelta(hours=0)

    def fromutc(self, dt):
        if not isinstance(dt, datetime):
            raise TypeError("fromutc() requires a datetime argument")
        if dt.tzinfo is not None:
            raise ValueError("dt.tzinfo is another timezone")

        offset = self.utcoffset(dt)
        return (dt + offset).replace(tzinfo=self)

    def _get_transition(self, dt):
        if not isinstance(dt, datetime):
            raise TypeError("dst() requires a datetime argument")

        transition = (None, 1, False)
        for t in self.transitions:
            if self._rawtimestamp(t[0]) < self._rawtimestamp(dt):
                transition = t
            else:
                break

        return transition

    @staticmethod
    def _rawtimestamp(dt):
        if not isinstance(dt, datetime):
            raise TypeError("_rawtimestamp() requires a datetime argument")
        days = dt.toordinal()
        secs = dt.second + dt.minute * 60 + dt.hour * 3600
        return timedelta(
            days, secs, dt.microsecond
        )

    transitions = [
        # 28-03-2021 2:00 UTC+2h
        (datetime(2021, 3, 28, 2, 00, 00), 2, True),
        # 25-10-2021 3:00 UTC+1h
        (datetime(2021, 10, 25, 3, 00, 00), 1, False),
        # 27-03-2022 2:00 UTC+2h
        (datetime(2022, 3, 27, 2, 00, 00), 2, True),
        # 31-10-2022 3:00 UTC+1h
        (datetime(2022, 10, 31, 3, 00, 00), 1, False),
        # 26-03-2023 2:00 UTC+2h
        (datetime(2023, 3, 26, 2, 00, 00), 2, True),
        # 29-10-2023 3:00 UTC+1h
        (datetime(2023, 10, 29, 3, 00, 00), 1, False),
        # 31-03-2024 2:00 UTC+2h
        (datetime(2024, 3, 27, 2, 00, 00), 2, True),
        # 27-10-2024 3:00 UTC+1h
        (datetime(2024, 10, 27, 3, 00, 00), 1, False)
    ]
