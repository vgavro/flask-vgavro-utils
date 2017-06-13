import subprocess
import logging
from datetime import datetime

from werkzeug.local import LocalProxy
from werkzeug.utils import import_string
from flask import g
from marshmallow.utils import UTC


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


def _resolve_obj_key(obj, key, supress_exc):
    if key.isdigit():
        try:
            return obj[int(key)]
        except:
            try:
                return obj[key]
            except Exception as exc:
                if supress_exc:
                    return exc
                raise ValueError('Could not resolve "{}" on {} object: {}'.format(key, obj))
    else:
        try:
            return obj[key]
        except:
            try:
                return getattr(obj, key)
            except Exception as exc:
                if supress_exc:
                    return exc
                raise ValueError('Could not resolve "{}" on {} object'.format(key, obj))


def resolve_obj_path(obj, path, suppress_exc=False):
    dot_pos = path.find('.')
    if dot_pos == -1:
        return _resolve_obj_key(obj, path, suppress_exc)
    else:
        key, path = path[:dot_pos], path[(dot_pos + 1):]
        return resolve_obj_path(_resolve_obj_key(obj, key, suppress_exc),
                                path, suppress_exc)


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
    return datetime.utcfromtimestamp(float(timestamp)).replace(tzinfo=UTC)


def utcnow():
    return datetime.now(tz=UTC)


def is_instance_or_proxied(obj, cls):
    if isinstance(obj, LocalProxy):
        obj = obj._get_current_object()
    return isinstance(obj, cls)


def local_proxy_on_g(attr, callback):
    def wrapper():
        if g:
            if not hasattr(g, attr):
                setattr(g, attr, callback())
            return getattr(g, attr)
    return LocalProxy(wrapper)


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
        except:
            # do not retry on first fail
            info[path] = {}
            # raise

    return info[path]
