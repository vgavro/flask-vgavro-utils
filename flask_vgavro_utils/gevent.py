import sys
import time
from functools import wraps
from collections import UserDict
from datetime import datetime
import signal

from flask import current_app
from werkzeug.utils import cached_property
from greenlet import settrace as greenlet_settrace
import gevent
import gevent.monkey
from gevent.hub import get_hub
from gevent.pool import Pool
from gevent.greenlet import Greenlet
from gevent.lock import Semaphore, BoundedSemaphore
from gevent.pywsgi import WSGIServer

from .app import Flask
from .utils import get_argv_opt, monkey_patch_meth


class LockedFactoryDict(UserDict):
    def __init__(self, factory=None, timeout=None):
        self._factory = factory
        self.timeout = timeout
        super().__init__()

    def __getitem__(self, key):
        if key not in self.data:
            self[key] = lambda: self.factory(key)
        return self.get(key)

    def get(self, key):
        if key in self.data:
            if isinstance(self.data[key], BoundedSemaphore):
                self.data[key].wait(self.timeout)
                assert not isinstance(self.data[key], BoundedSemaphore)
            return self.data[key]

    def __setitem__(self, key, factory):
        if not callable(factory):
            raise ValueError('value %s should be callable' % factory)
        lock = self.data[key] = BoundedSemaphore()
        lock.acquire()
        self.data[key] = factory()
        assert not isinstance(self.data[key], BoundedSemaphore)
        lock.release()

    def factory(self, key):
        if self._factory is not None:
            return self._factory(key)
        raise NotImplementedError()


class CachedBulkProcessor:
    def __init__(self, pool, cache, cache_key, cache_timeout, cache_fail_timeout=None,
                 update_timeout=10, join_timeout=30, join_timeout_raise=False,
                 worker=None, logger=None):
        self.pool = pool
        self.cache = cache
        assert '{}' in cache_key, 'Cache key should have format placeholder'
        self.cache_key = cache_key
        self.cache_timeout = cache_timeout
        self.cache_fail_timeout = cache_fail_timeout or cache_timeout
        self.update_timeout = update_timeout
        self.join_timeout = join_timeout
        self.join_timeout_raise = join_timeout_raise
        if worker:
            self._worker = worker
        self._logger = logger

        self.workers = {}

    @cached_property
    def logger(self):
        return self._logger or current_app.logger

    def __call__(self, *entity_ids, update=True, join=False):
        entity_ids = set(entity_ids)
        # TODO: actualy this timeout is only related to pool waiting,
        # so maybe move it to self.pool.spawn?
        timeout = gevent.Timeout.start_new(self.update_timeout)
        try:
            rv, workers = self._get_or_update(entity_ids, update)
        except gevent.Timeout:
            self.logger.warn('Update timeout: %s', entity_ids)
            raise
        else:
            self.logger.debug('Processing: rv=%s spawned=%s pool=%s',
                set(rv.keys()) or '{}', [w.args[0] for w in workers], _pool_status(self.pool))
            timeout.cancel()  # TODO: api?

        if workers and join:
            finished_workers = gevent.joinall(workers, timeout=self.join_timeout)
            if len(workers) != len(finished_workers):
                self.logger.warn('Join timeout: %d, not finished workers: %s', self.join_timeout,
                                 [w.args[0] for w in set(workers).difference(finished_workers)])
            rv_, _ = self._get_or_update(set(entity_ids) - set(rv), update=False)
            rv.update(rv_)
        return rv

    def _get_or_update(self, entity_ids, update):
        rv, workers = {}, []
        for entity_id in entity_ids:
            data = self.cache.get(self.cache_key.format(entity_id))
            if data:
                rv[entity_id] = data
            elif data is False:
                rv[entity_id] = None
            elif update:
                workers.append(self.get_or_create_worker(entity_id))
        return rv, workers

    def get_or_create_worker(self, entity_id):
        if entity_id in self.workers:
            return self.workers[entity_id]
        self.workers[entity_id] = self.pool.spawn(self.worker, entity_id)
        return self.workers[entity_id]

    def worker(self, entity_id):
        self.logger.debug('Starting worker: %s', entity_id)
        try:
            rv = self._worker(entity_id)
        except Exception as exc:
            self.logger.exception('Worker failed: %s %r', entity_id, exc)
        except BaseException as exc:
            self.logger.debug('Worker failed: %s %r', entity_id, exc)
            raise
        else:
            timeout = self.cache_fail_timeout if rv is False else self.cache_timeout
            self.cache.set(self.cache_key.format(entity_id), rv, timeout)
        del self.workers[entity_id]

    def _worker(self, entity_id):
        raise NotImplementedError()


class Semaphore(Semaphore):
    # TODO: looks like it's already implemented in newer gevent versions
    """Extends gevent.lock.Semaphore with context."""
    def __enter__(self):
        self.acquire()

    def __exit__(self, *args, **kwargs):
        self.release()


def _create_switch_time_tracer(max_blocking_time, logger):
    def _switch_time_tracer(what, origin_target):
        origin, target = origin_target
        if not hasattr(_switch_time_tracer, '_last_switch_time'):
            _switch_time_tracer._last_switch_time = None
        then = _switch_time_tracer._last_switch_time
        now = _switch_time_tracer._last_switch_time = time.time()
        if then is not None:
            blocking_time = now - then
            if origin is not get_hub():
                if blocking_time > max_blocking_time:
                    msg = "Greenlet blocked the eventloop for %.4f seconds\n"
                    logger.warning(msg, blocking_time)

    return _switch_time_tracer


def set_switch_time_tracer(max_blocking_time, logger):
    # based on http://www.rfk.id.au/blog/entry/detect-gevent-blocking-with-greenlet-settrace/
    greenlet_settrace(_create_switch_time_tracer(max_blocking_time, logger))


def set_hub_exception_logger(logger):
    # NOTE: traceback is not printed with logger, but with exception_stream
    # also see http://www.gevent.org/gevent.hub.html
    # get_hub().handle_error and exeption_stream
    @monkey_patch_meth(get_hub(), 'print_exception')
    def print_exception(orig, context, type, value, tb):
        logger.error('%s failed with %r', context, value)
        return orig(context, type, value, tb)


def app_context(app):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with app.app_context():
                return func(*args, **kwargs)
        return wrapper
    return decorator


def app_greenlet_class(app):
    @wraps(Greenlet)
    def wrapper(run, *args, **kwargs):
        return Greenlet(app_context(app)(run), *args, **kwargs)
    return wrapper


def spawn(*args, **kwargs):
    # TODO: move this to flask-gevent module and remove app.* methods
    current_app.spawn(*args, **kwargs)


def spawn_later(*args, **kwargs):
    # TODO: move this to flask-gevent module and remove app.* methods
    current_app.spawn_later(*args, **kwargs)


def greenlet_class(*args, **kwargs):
    # TODO: move this to flask-gevent module and remove app.* methods
    current_app.greenlet_class(*args, **kwargs)


class GeventFlask(Flask):
    _work_forever = []

    def configure(self, *args, **kwargs):
        super().configure(*args, **kwargs)

        self.started_at = datetime.utcnow()
        self.pools = {}
        self.greenlet_class = app_greenlet_class(self)

        # if not gevent.monkey.is_module_patched('__builtin__'):
        #     raise RuntimeError('Looks like gevent.monkey is not applied')

        if 'sqlalchemy' in self.extensions:
            db = self.extensions['sqlalchemy'].db
            db.engine.pool._use_threadlocal = True

        switch_trace_seconds = self.config.get('GEVENT_SWITCH_TRACE_SECONDS')
        if switch_trace_seconds:
            set_switch_time_tracer(switch_trace_seconds, self.logger)

        set_hub_exception_logger(self.logger)

    def spawn(self, func, *args, **kwargs):
        return gevent.spawn(app_context(self)(func), *args, **kwargs)

    def spawn_later(self, seconds, func, *args, **kwargs):
        return gevent.spawn_later(seconds, app_context(self)(func), *args, **kwargs)

    def greenlet(self, *args, **kwargs):
        return self.greenlet_class(*args, **kwargs)

    def create_pool(self, name=None, size=None):
        if not name:
            assert size, 'Anonymous pools can\'t be without size'
            return Pool(size, greenlet_class=self.greenlet_class)
        else:
            assert name not in self.pools, 'Pool {} already created'.format(name.upper())
            size = size or self.config.get('{}_POOL_SIZE'.format(name.upper()))
            self.pools[name] = Pool(size, greenlet_class=self.greenlet_class)
            return self.pools[name]

    def work_forever(self, wait_seconds=None):
        wait_seconds = wait_seconds or self.config.get('WORK_FOREVER_WAIT_SECONDS', 0)

        def decorator(func):
            def wrapper():
                try:
                    while True:
                        func()
                        if wait_seconds:
                            self.logger.info('work_forever sleep for %s', wait_seconds)
                            gevent.sleep(wait_seconds)
                except Exception as exc:
                    # TODO: stop server and log error
                    self.logger.exception('work_forever failed: %r', exc)
                    print(exc, file=sys.stderr)
                    sys.exit(1)
            self._work_forever.append(app_context(self)(wrapper))
        return decorator

    def stop(self, timeout=None):
        """
        Use it to execute before server teardown.
        """
        if timeout:
            raise NotImplementedError()

        def decorator(func):
            self._stop = app_context(self)(func)
        return decorator


def _pool_status(pool):
    return '{}/{}'.format(pool.free_count(), pool.size)


def get_app_status():
    rv = {'started_at': current_app.started_at}
    if 'sqlalchemy' in current_app.extensions:
        rv['sqlalchemy'] = current_app.extensions['sqlalchemy'].db.session.bind.pool.status()
    for name, pool in current_app.pools.items():
        rv[name + '_pool'] = _pool_status(pool)
    return rv


def serve_forever(app, stop_signals=[signal.SIGTERM, signal.SIGINT], listen=None):
    host, port = (get_argv_opt('-l', '--listen') or listen or
                  app.config.get('GEVENT_LISTEN', '127.0.0.1:8088')).split(':')
    server = WSGIServer((host, int(port)), app, spawn=app.create_pool('server'))

    def stop():
        if hasattr(stop, 'stopping'):
            try:
                app.logger.warn('Multiple exit signals received - aborting.')
            finally:
                return sys.exit('Multiple exit signals received - aborting.')
        stop.stopping = True

        app.logger.info('Stopping server')
        for worker in app._work_forever:
            if isinstance(worker, Greenlet):
                worker.kill(timeout=5)
        if hasattr(app, '_stop'):
            app._stop()
        for pool in app.pools.values():
            pool.kill(timeout=5)
        # TODO: we should stop serving requests before app._stop, but for some reason
        # app._stop is not finishing in this case (maybe timeout?)
        server.stop(5)
        app.logger.info('Server stopped')

    [gevent.signal(sig, stop) for sig in stop_signals]

    app.logger.info('Starting server on %s:%s', host, port)
    app._work_forever = [gevent.spawn(w) for w in app._work_forever]
    server.serve_forever()
