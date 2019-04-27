import sys
import subprocess
from urllib.parse import urlencode
import logging
import types
from functools import partial, wraps
from datetime import datetime, time, timezone
import warnings

from werkzeug.local import LocalProxy
from flask import g
from werkzeug.utils import import_string
import dateutil


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


class ContextLoggerAdapter(logging.LoggerAdapter):
    def bind(self, **extra):
        return self.__class__(self.logger, {**self.extra.copy(), **extra})

    def process(self, msg, kwargs):
        return (
            ('%s %s'
             % (' '.join('%s=%s' % (k, v) for k, v in self.extra.items()), msg)),
            kwargs)


def resolve_obj_key(obj, key):
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


def resolve_obj_path(obj, path, suppress_exc=False):
    try:
        dot_pos = path.find('.')
        if dot_pos == -1:
            return resolve_obj_key(obj, path)
        else:
            key, path = path[:dot_pos], path[(dot_pos + 1):]
            return resolve_obj_path(resolve_obj_key(obj, key), path)
    except Exception as exc:
        if suppress_exc:
            return exc
        raise


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)

    def __dir__(self):
        # Autocompletion for ipython
        return super().__dir__() + list(self.keys())

    def __getstate__(self):
        # We need it for pickle because it depends on __getattr__
        return dict(self)

    def __setstate__(self, dict_):
        self.update(dict_)


def maybe_attr_dict(data):
    if isinstance(data, dict):
        return AttrDict({k: maybe_attr_dict(v) for k, v in data.items()})
    return data


def maybe_encode(data, encoding='utf-8'):
    return data if isinstance(data, bytes) else str(data).encode('utf8')


def maybe_decode(data, encoding='utf-8'):
    return data if isinstance(data, str) else data.decode(encoding)


def maybe_import_string(value):
    return import_string(value) if isinstance(value, str) else value


def parse_timestamp(timestamp, tz=timezone.utc):
    return datetime.utcfromtimestamp(float(timestamp)).replace(tzinfo=tz)


def parse_time(data):
    hours, minutes, seconds, *_ = data.split(':') + [0, 0]
    return time(int(hours), int(minutes), int(seconds))


def parse_datetime(data, tz=timezone.utc):
    return maybe_tz(dateutil.parser.parse(data), tz)


def maybe_tz(dt, tz=timezone.utc):
    if not dt.tzinfo:
        return dt.replace(tzinfo=tz)
    return dt


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


def decorator_with_default_args(target):
    """
    This decorator should be used on other decorator that implements default kwargs,
    and therefore may be used as @decorator,  @decorator() or @decorator(key=ovveride_value).
    Definition example:
    @decorator_with_default_args
    def my_decorator(func, key=default_value):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    """

    receipt = """
    def my_decorator(func=None, **kwargs):
        if func:
            return my_decorator()(func)

        def decorator(func):
            return func
        return decorator
    """
    warnings.warn('decorator_with_default_args deprated. '
                  'Use this receipt instead: {}'.format(receipt),
                  DeprecationWarning)

    def decorator(func=None, **kwargs):
        if func and isinstance(func, types.FunctionType):
            return target(func)
        else:
            assert not func, 'You should use this decorator only with kwargs'
            return partial(target, **kwargs)
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


def monkey_patch_meth(obj, attr, safe=True):
    orig_func = getattr(obj, attr)

    def decorator(func):
        @wraps(orig_func)
        def wrapper(*args, **kwargs):
            return func(orig_func, *args, **kwargs)

        flag_attr = '_monkey_patched_{}'.format(attr)
        if not safe or not hasattr(obj, flag_attr):
            setattr(obj, attr, wrapper)
            if safe:
                setattr(obj, flag_attr, True)
    return decorator


def url_with_qs(url, **qs):
    if qs and not url.endswith('?'):
        url += '?'
    return url + urlencode(qs)


def get_argv_opt(shortname=None, longname=None, is_bool=False):
    """
    Simple and naive helper to get option from command line.
    Returns None on any error.
    """
    assert shortname or longname
    if shortname:
        assert shortname.startswith('-')
        try:
            x = sys.argv.index(shortname)
            return True if is_bool else sys.argv[x + 1]
        except (ValueError, IndexError):
            pass
    if longname:
        assert longname.startswith('--')
        for arg in sys.argv:
            if arg.startswith(longname):
                if is_bool and len(longname) == len(arg):
                    return True
                if arg[len(longname)] == '=':
                    return arg[len(longname) + 1:]
