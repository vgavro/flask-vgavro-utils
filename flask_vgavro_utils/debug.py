from inspect import isclass, isroutine

# Some things based on traced https://github.com/mzipay/Autologging/blob/master/autologging.py


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
                root, func.__name__, safe_repr(args), safe_repr(kwargs))
            )
            rv = func(*args, **kwargs)
            print('{}{} RETURN {}'.format(root, func.__name__, safe_repr(rv)))
            if pdb:
                # TODO: any way to move inside function context?
                # Also ipython somehow gets to context where exception was
                # raised with %pdb switch, how to implement it here?
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
