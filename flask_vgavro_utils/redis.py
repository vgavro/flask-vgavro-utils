import inspect
import functools
import hashlib
import pickle
import time

from flask import current_app
from redis.client import StrictRedis
from redis.lock import LuaLock
from redis.exceptions import LockError


def create_redis(app):
    redis_url = app.config['REDIS_URL']
    app.extensions['redis'] = Redis(redis_url)
    app.extensions['cache'] = RedisSerializedCache(redis_url)
    app.extensions['func_cache'] = RedisSerializedCache(redis_url, 'FUNC_CACHE')
    return app.extensions['redis']


class RedisLock(LuaLock):
    expire_at = None

    def __enter__(self):
        # Redis default lock __enter__ is always blocking
        if not self.acquire():
            raise LockError('Lock was not acquired')
        return self

    def acquire(self, *args, **kwargs):
        rv = super().acquire(*args, **kwargs)
        if rv and self.timeout:
            self.expire_at = time.time() + self.timeout
        return rv

    def release(self, *args, **kwargs):
        self.expire_at = None
        return super().release(*args, *kwargs)

    def maybe_extend(self, timeout_factor=0.33):
        if not self.expire_at:
            raise LockError('Lock was not acquired or no timeout')
        left = self.expire_at - time.time()
        if left < 0:
            raise LockError('Lock was already expired')
        if left < (self.timeout * timeout_factor):
            self.extend(self.timeout - left)


class Redis:
    _redis_map = {}

    def __init__(self, redis_url='redis://localhost:6379/0', base_key=None):
        self.base_key = base_key
        if redis_url not in self._redis_map:
            self._redis_map[redis_url] = StrictRedis.from_url(redis_url)
        self._redis = self._redis_map[redis_url]

    def _build_key(self, key):
        return self.base_key and '{}:{}'.format(self.base_key, key) or key

    def get(self, key, default=None):
        result = self._redis.get(self._build_key(key))
        return result if result is not None else default

    def set(self, key, value, timeout=None):
        self._redis.set(self._build_key(key), value, ex=timeout)

    def incr(self, key, value):
        self._redis.incr(self._build_key(key), value)

    def decr(self, key, value):
        self._redis.decr(self._build_key(key), value)

    def delete(self, *keys):
        self._redis.delete(*map(self._build_key, keys))

    def flush(self):
        self._redis.flushdb()

    def lock(self, name, timeout, **kwargs):
        name = self._build_key('LOCK:{}'.format(name))
        return RedisLock(self._redis, name, timeout, **kwargs)


class RedisSerializedCache(Redis):
    def _serialize(self, value):
        return pickle.dumps(value)

    def _deserialize(self, value):
        return pickle.loads(value)

    def get(self, key, default=None):
        result = super(RedisSerializedCache, self).get(key, None)
        return default if result is None else self._deserialize(result)

    def set(self, key, value, timeout=None):
        super(RedisSerializedCache, self).set(key, self._serialize(value), timeout)


def _get_function_hash_key(func, self_callback=lambda self: None, args=[], kwargs={}):

    # getting fully qualified function/method name
    module = inspect.getmodule(func)
    module_name = module.__name__
    class_ = getattr(func, 'im_class', None)
    class_name = class_ and class_.__name__ or ''
    method_name = func.__name__
    func_name = '.'.join((module_name, class_name, method_name))

    # getting args/kwargs
    callargs = inspect.getcallargs(func, *args, **kwargs)
    argspec = inspect.getargspec(func)
    nargs = argspec.args
    argspec.varargs and nargs.append(argspec.varargs)
    argspec.keywords and nargs.append(argspec.keywords)
    if inspect.ismethod(func) and func.im_self is not None:
        # replacing "self" or "cls" with callback if any
        callargs[nargs[0]] = self_callback(args[0])
    callargs = pickle.dumps([callargs[arg] for arg in nargs])

    key = ':'.join((func_name, callargs))
    m = hashlib.md5()
    m.update(key)
    return m.hexdigest()


def cache_function(timeout, self_callback=lambda self: None):
    """
    Wraps function or bounded method. If this is bounded method - self_callback
    may be passed to get unique cache value for object. Else all methods of same
    class will have common cache.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = _get_function_hash_key(func, self_callback, args, kwargs)

            result = current_app.extensions['func_cache'].get(cache_key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            current_app.extensions['func_cache'].set(cache_key, result, timeout)
            return result

        return wrapper
    return decorator


def cache_method(timeout, self_callback=lambda self: None):
    """
    Wraps unbounded method. Instance should be passed to wrapper as first argument.
    """
    def decorator(func):
        # TODO: not obvious when python gives method or when just function...
        assert (not inspect.ismethod(func) and not getattr(func, 'im_self', None))

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            args_ = (self_callback(args[0]),) + args[1:]
            cache_key = _get_function_hash_key(func, args=args_, kwargs=kwargs)

            result = current_app.extensions['func_cache'].get(cache_key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            current_app.extensions['func_cache'].set(cache_key, result, timeout)
            return result

        return wrapper
    return decorator


def cache_method_generator(timeout, self_callback=lambda self: None, cache_on_break=False):
    """
    Wraps unbounded method. Instance should be passed to wrapper as first argument.
    """
    def decorator(func):
        # TODO: not obvious when python gives method or when just function...
        assert (not inspect.ismethod(func) and not getattr(func, 'im_self', None))

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            args_ = (self_callback(args[0]),) + args[1:]
            cache_key = _get_function_hash_key(func, args=args_, kwargs=kwargs)

            result = current_app.extensions['func_cache'].get(cache_key)
            if result is not None:
                for item in result:
                    yield item
                return

            result = []
            try:
                for item in func(*args, **kwargs):
                    result.append(item)
                    yield item
            except GeneratorExit:
                if cache_on_break:
                    current_app.extensions['func_cache'].set(cache_key, result, timeout)
                raise
            else:
                current_app.extensions['func_cache'].set(cache_key, result, timeout)

        return wrapper
    return decorator
