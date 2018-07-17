from inspect import isclass, isroutine

# Some things based on traced https://github.com/mzipay/Autologging/blob/master/autologging.py


def trace_func(pdb=False, root=''):
    root = root and '{}.'.format(root) or ''

    def decorator(func):
        def wrapper(*args, **kwargs):
            print('{}{} CALL args={} kwargs={}'.format(root, func.__name__, args, kwargs))
            rv = func(*args, **kwargs)
            print('{}{} RETURN {}'.format(root, func.__name__, rv))
            if pdb:
                __import__('pdb').set_trace()
            return rv
        return wrapper
    return decorator


def trace(pdb=False):
    def decorator(obj):
        if isclass(obj):
            for attr in dir(obj):
                if (not (attr.startswith('__') and attr.endswith('__')) or
                    attr in ('__call__', '__init__')
                ):
                    meth = getattr(obj, attr)
                    if isroutine(meth):
                        meth = trace_func(pdb, root=obj.__name__)(meth)
                        setattr(obj, attr, meth)
            return obj
        else:
            return trace_func(pdb)(obj)
    return decorator
