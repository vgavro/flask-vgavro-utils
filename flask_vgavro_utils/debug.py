import logging
import contextlib
from time import time
from inspect import isclass, isroutine


logger = logging.getLogger('flask-vgavro-utils.debug')

# Some things based on traced https://github.com/mzipay/Autologging/blob/master/autologging.py


def isbound(obj):
    return (
        hasattr(obj, "im_self") or  # python2
        hasattr(obj, "__self__")  # python3
    )


def safe_repr(value):
    if isinstance(value, (list, tuple)):
        try:
            return repr(value.__class__(safe_repr(v) for v in value))
        except Exception:  # try native repr then
            pass
    elif isinstance(value, dict):
        try:
            return repr(value.__class__((safe_repr(k), safe_repr(v))
                                        for k, v in value.items()))
        except Exception:
            pass  # try native repr then
    try:
        return repr(value)
    except Exception as exc:
        if hasattr(value, '__name__'):
            name = value.__name__
        else:
            name = '{} instance'.format(value.__class__)
        return '<repr {} failed with {}>'.format(name, exc)


def trace_func(pdb=False, root=''):
    root = root and '{}.'.format(root) or ''

    def decorator(func):
        def wrapper(*args, **kwargs):
            print('{}{} CALL args={} kwargs={}'.format(
                root, func.__name__, safe_repr(args[1:]), safe_repr(kwargs))
            )
            try:
                rv = func(*args, **kwargs)
            except Exception as exc:
                print('{}{} EXCEPTION {}'.format(root, func.__name__, safe_repr(exc)))
                raise
            else:
                print('{}{} RETURN {}'.format(root, func.__name__, safe_repr(rv)))
            if pdb:
                # TODO: any way to move inside function context?
                # Also ipython somehow gets to context where exception was
                # raised with %pdb switch, how to implement it here?
                __import__('pdb').set_trace()
            return rv
        return wrapper
    return decorator


def trace(obj=None, pdb=False):
    if obj:
        return trace()(obj)

    def decorator(obj):
        if isclass(obj):
            for attr in dir(obj):
                if (not (attr.startswith('__') and attr.endswith('__')) or
                    attr in ('__call__', '__init__')
                ):
                    meth = getattr(obj, attr)
                    if not isroutine(meth):
                        continue
                    if isbound(meth):
                        # TODO: this is classmethod just skip it for now,
                        # later added it from autologging, also add context id
                        # to get call/return pair by same id, not name,
                        # and object id instead of repr(self).
                        continue

                    # NOTE: for staticmethod this would fail
                    meth = trace_func(pdb, root=obj.__name__)(meth)
                    setattr(obj, attr, meth)
            return obj
        else:
            return trace_func(pdb)(obj)
    return decorator


class log_time(contextlib.ContextDecorator):
    def __init__(self, ctx_name=None, logger=None, log_start=False):
        self.ctx_name, self.logger, self.log_start  = \
            ctx_name, logger, log_start

    def __call__(self, func):
        if not self.ctx_name:
            self.ctx_name = getattr(func, '__name__', 'unknown')
        return super().__call__(func)

    def __enter__(self):
        self.log = (self.logger or logger).debug
        self.started = time()
        if self.log_start:
            self.log.debug('%s: started' % self.ctx_name)

    def __exit__(self, exc_type, exc_value, exc_tb):
        time_ = time() - self.started
        self.log('%s: finished in %0.4f seconds with %s', self.ctx_name,
                 time_, 'success' if exc_value is None else repr(exc_value))
