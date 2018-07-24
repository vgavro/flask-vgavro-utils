from decimal import Decimal
from enum import Enum
from datetime import datetime, date, timezone

from flask.json import JSONEncoder


class ApiJSONEncoder(JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__iter__'):
            return tuple(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, Enum):
            return obj.name
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()

        elif self.sort_keys and isinstance(obj, dict):
            # Python 3.6 in particular has bug(?) with int/str sorting
            obj = {str(k): v for k, v in obj.items()}

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
