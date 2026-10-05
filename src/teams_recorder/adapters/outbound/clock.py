from datetime import datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().replace(microsecond=0)
