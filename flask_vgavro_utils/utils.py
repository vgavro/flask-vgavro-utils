import subprocess
import logging
import time
import contextlib
from datetime import datetime, date, timezone
import json

from werkzeug.local import LocalProxy
from werkzeug.utils import import_string
from flask import g


class classproperty(property):
    """
    A decorator that behaves like @property except that operates
    on classes rather than instances.
    Copy of sqlalchemy.util.langhelpers.classproperty, because first one executed
    on class declaration.
    """

    def __init__(self, fget, *arg, **kw):
        super(classproperty, self).__init__(fget, *arg, **kw)
        self.__doc__ = fget.__doc__

    def __get__(desc, self, cls):
        return desc.fget(cls)


@classproperty
def NotImplementedProperty(self):
    raise NotImplementedError()


NotImplementedClassProperty = NotImplementedProperty


class EntityLoggerAdapter(logging.LoggerAdapter):
    """
    Adds info about the entity to the logged messages.
    """
    def __init__(self, logger, entity):
        self.logger = logger
        self.entity = entity or '?'

    def process(self, msg, kwargs):
        return '[{}] {}'.format(self.entity, msg), kwargs


def _resolve_obj_key(obj, key):
    if key.isdigit():
        try:
            return obj[int(key)]
        except Exception:
            try:
                return obj[key]
            except Exception as exc:
                raise ValueError('Could not resolve "{}" on {} object: {!r}'
                                 .format(key, obj, exc))
    else:
        try:
            return obj[key]
        except Exception:
            try:
                return getattr(obj, key)
            except Exception as exc:
                raise ValueError('Could not resolve "{}" on {} object: {!r}'
                                 .format(key, obj, exc))


def resolve_obj_path(obj, path, supress_exc=False):
    try:
        dot_pos = path.find('.')
        if dot_pos == -1:
            return _resolve_obj_key(obj, path)
        else:
            key, path = path[:dot_pos], path[(dot_pos + 1):]
            return resolve_obj_path(_resolve_obj_key(obj, key), path)
    except Exception as exc:
        if supress_exc:
            return exc
        raise


class AttrDict(dict):
    __getattr__ = dict.__getitem__

    def __dir__(self):
        # autocompletion for ipython
        return super().__dir__() + list(self.keys())


def maybe_attr_dict(data):
    if isinstance(data, dict):
        return AttrDict({k: maybe_attr_dict(v) for k, v in data.items()})
    return data


def hstore_dict(value):
    return {k: str(v) for k, v in value.items()}


def maybe_encode(string, encoding='utf-8'):
    return isinstance(string, bytes) and string or str(string).encode(encoding)


def maybe_decode(string, encoding='utf-8'):
    return isinstance(string, str) and string.decode(encoding) or string


def maybe_import(value):
    return isinstance(value, str) and import_string(value) or value


def datetime_from_utc_timestamp(timestamp):
    return datetime.utcfromtimestamp(float(timestamp)).replace(tzinfo=timezone.utc)


def utcnow():
    return datetime.now(tz=timezone.utc)


def is_instance_or_proxied(obj, cls):
    if isinstance(obj, LocalProxy):
        obj = obj._get_current_object()
    return isinstance(obj, cls)


def local_proxy_on_g(attr_name=None):
    def decorator(func):
        attr = attr_name or func.__name__

        def wrapper():
            if g:
                if not hasattr(g, attr):
                    setattr(g, attr, func())
                return getattr(g, attr)
        return LocalProxy(wrapper)

    return decorator


def get_git_repository_info(path='./'):
    if not hasattr(get_git_repository_info, '_info'):
        get_git_repository_info._info = {}
    info = get_git_repository_info._info

    if path not in info:
        try:
            pipe = subprocess.Popen(['git', 'log', '-1', '--pretty=format:"%h|%ce|%cd"'],
                                    stdout=subprocess.PIPE, cwd=path)
            out, err = pipe.communicate()
            info[path] = dict(zip(('rev', 'email', 'time'), out.split('|')))
        except Exception:
            # do not retry on first fail
            info[path] = {}
            # raise

    return info[path]


def string_repr_short(value, length=64):
    value = str(value)
    if len(value) > length:
        return value[:length - 3] + '...'
    return value


class ReprMixin:
    def __repr__(self, *args, exclude=[]):
        attrs = ', '.join((u'{}={}'.format(k, string_repr_short(v))
                          for k, v in self.to_dict(*args, exclude=exclude).items()))
        return '<{}({})>'.format(self.__class__.__name__, attrs)

    def to_dict(self, *args, exclude=[]):
        args = args or self.__dict__.keys()
        return {key: getattr(self, key) for key in args
                if not key.startswith('_') and key not in exclude}


def pprint(obj, indent=2, colors=True):
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, ReprMixin):
            return obj.to_dict()
        raise TypeError('Type %s not serializable' % type(obj))

    rv = json.dumps(obj, default=default, indent=indent, ensure_ascii=False)

    if colors:
        try:
            from pygments import highlight
            from pygments.lexers import JsonLexer
            from pygments.formatters import TerminalFormatter
        except ImportError:
            pass
        else:
            rv = highlight(rv, JsonLexer(), TerminalFormatter())

    print(rv)


class db_transaction(contextlib.ContextDecorator):
    def __init__(self, db, commit=True, rollback=False):
        assert not (commit and rollback)
        self.db, self.commit, self.rollback = db, commit, rollback
        db.session.flush()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_tb):
        if not exc_type and self.commit:
            try:
                self.db.session.commit()
            except BaseException:
                self.db.session.close()
                raise
        elif exc_type or self.rollback:
            self.db.session.rollback()

        self.db.session.close()


def _create_gevent_switch_time_tracer(max_blocking_time, logger):
    import gevent.hub

    def _gevent_switch_time_tracer(what, origin_target):
        origin, target = origin_target
        if not hasattr(_gevent_switch_time_tracer, '_last_switch_time'):
            _gevent_switch_time_tracer._last_switch_time = None
        then = _gevent_switch_time_tracer._last_switch_time
        now = _gevent_switch_time_tracer._last_switch_time = time.time()
        if then is not None:
            blocking_time = now - then
            if origin is not gevent.hub.get_hub():
                if blocking_time > max_blocking_time:
                    msg = "Greenlet blocked the eventloop for %.4f seconds\n"
                    logger.warning(msg, blocking_time)

    return _gevent_switch_time_tracer


def set_gevent_switch_time_tracer(max_blocking_time, logger):
    # based on http://www.rfk.id.au/blog/entry/detect-gevent-blocking-with-greenlet-settrace/
    import greenlet

    greenlet.settrace(_create_gevent_switch_time_tracer(max_blocking_time, logger))
