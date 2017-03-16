from werkzeug.utils import cached_property
from flask import json
from flask.testing import FlaskClient


class TestResponseMixin(object):
    @cached_property
    def json(self):
        return json.loads(self.data)

    @cached_property
    def content(self):
        return self.data.decode(self.charset)


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
