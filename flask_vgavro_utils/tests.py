from werkzeug.utils import cached_property
from flask import json
from flask.testing import FlaskClient
from .repr import repr_str_short


class TestResponseMixin(object):
    @cached_property
    def json(self):
        return json.loads(self.data)

    @cached_property
    def content(self):
        return self.data.decode(self.charset)

    def __repr__(self, full=False):
        content = self.content if full else repr_str_short(self.content, 128)
        return '<Response {}: {}>'.format(self.status, content)


class TestClient(FlaskClient):
    def open(self, *args, **kwargs):
        if 'json' in kwargs:
            kwargs['data'] = json.dumps(kwargs.pop('json'))
            kwargs['content_type'] = 'application/json'
        return super(TestClient, self).open(*args, **kwargs)


def register_test_helpers(app):
    if not issubclass(app.response_class, TestResponseMixin):
        class TestResponse(TestResponseMixin, app.response_class):
            pass
        app.response_class = TestResponse

    app.test_client_class = TestClient


def check_gevent_concurrency(sleep='time.sleep', callback=None):
    if isinstance(sleep, str):
        module = __import__(''.join(sleep.split('.')[:-1]))
        sleep = getattr(module, sleep.split('.')[-1])
    callback = callback or (lambda x: print('concurrency={}'.format(x)))

    check_gevent_concurrency._flag = False

    def _set_concurrency():
        sleep(0.01)
        check_gevent_concurrency._flag = True

    def _check_concurrency():
        sleep(0.02)
        callback(check_gevent_concurrency._flag)

    import gevent
    gevent.joinall([
        gevent.spawn(_check_concurrency),
        gevent.spawn(_set_concurrency),
    ])
