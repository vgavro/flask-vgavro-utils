import subprocess

from werkzeug.local import LocalProxy
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


@property
def NotImplementedProperty(self):
    raise NotImplementedError()


class AttrDict(dict):
    """
    http://stackoverflow.com/a/14620633
    """
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


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
