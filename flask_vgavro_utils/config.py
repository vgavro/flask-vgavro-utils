from werkzeug.utils import ImportStringError
from flask.config import Config


class LazyValue(object):
    """
    This class may be used to lazy resolve config after importing local overrides.
    For example:
    REDIS_URL = "redis://localhost:6379/0"
    CELERY_BROKER_URL = LazyValue(lambda conf: conf['REDIS_URL'])

    After running Config.resolve_lazy_values()
    CELERY_BROKER_URL will be resolved to REDIS_URL, even if REDIS_URL were redefined later.
    """
    _counter = 0

    def __init__(self, callback):
        self.callback = callback
        self.__class__._counter += 1

    def resolve(self, config):
        return self.callback(config)


class Config(Config):
    def from_object(self, obj, raise_no_module=True):
        if isinstance(obj, str) and not raise_no_module:
            try:
                super().from_object(obj)
            except ImportStringError as exc:
                exc = exc.exception
                if not (exc.args[0] and exc.args[0].startswith('No module named') and
                   obj in exc.args[0]):
                    # skip if override module not exist, raise otherwise
                    raise
        else:
            super().from_object(obj)

    def resolve_lazy_values(self):
        for k in sorted([k for k in self if isinstance(self[k], LazyValue)],
                        key=lambda k: self[k]._counter):
            self[k] = self[k].resolve(self)

    def update_from_namespace(self, namespace):
        self.update(self.get_namespace(namespace, lowercase=False))
