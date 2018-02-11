from decimal import Decimal
from enum import Enum
from datetime import datetime, date, timezone

from flask.json import JSONEncoder


class ApiJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.name
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)


class TimedeltaJSONEncoder(JSONEncoder):
    def __init__(self, timedelta_from=None, **kwargs):
        super().__init__(**kwargs)
        self.timedelta_from = timedelta_from or datetime.utcnow()

    def default(self, obj):
        if isinstance(obj, datetime):
            if obj.tzinfo:
                obj = obj.astimezone(timezone.utc).replace(tzinfo=None)
            return str(self.timedelta_from - obj)
        return super().default(obj)
