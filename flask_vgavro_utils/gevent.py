import sys
import time
from functools import wraps
from datetime import datetime
import signal

from flask import current_app
import greenlet
import gevent
import gevent.monkey
from gevent.hub import get_hub
from gevent.pool import Pool
from gevent.greenlet import Greenlet
from gevent.pywsgi import WSGIServer

from .app import Flask
from .utils import get_argv_opt, monkey_patch_meth


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
    greenlet.settrace(_create_switch_time_tracer(max_blocking_time, logger))


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


class GeventFlask(Flask):
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

    def create_pool(self, name, size=None):
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
            self._work_forever = app_context(self)(wrapper)
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
    return 'Pool {}/{}'.format(pool.free_count(), pool.size)


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
        if hasattr(app, '_work_forever') and isinstance(app._work_forever, Greenlet):
            app._work_forever.kill()
        if hasattr(app, '_stop'):
            app._stop()
        # TODO: we should stop serving requests before app._stop, but for some reason
        # app._stop is not finishing in this case (maybe timeout?)
        server.stop(5)
        app.logger.info('Server stopped')

    [gevent.signal(sig, stop) for sig in stop_signals]

    app.logger.info('Starting server on %s:%s', host, port)
    if hasattr(app, '_work_forever'):
        app._work_forever = gevent.spawn(app._work_forever)
    server.serve_forever()
