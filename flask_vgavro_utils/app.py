import os
import sys
import logging
import logging.config
import traceback

from flask import Flask, Response, jsonify, request, current_app
from marshmallow import ValidationError

from .config import Config
from .exceptions import ApiError, EntityError
from .tests import register_test_helpers
from .cli import register_shell_context
from .json import ApiJSONEncoder

try:
    from celery.result import EagerResult, AsyncResult
except ImportError:
    EagerResult, AsyncResult = (), ()  # for isinstance False


class ApiResponse(Response):
    @classmethod
    def force_type(cls, resp, environ=None):
        if isinstance(resp, EagerResult):
            resp.maybe_throw()
            resp = resp.result  # TODO: also wrapper here?

        rv = resp

        if isinstance(resp, AsyncResult):
            task_url = current_app.extensions['celery'].task_url.replace('<task_id>', resp.id)
            rv = jsonify(current_app.response_wrapper({
                'task_id': resp.id,
                'task_url': request.url_root + task_url,
            }))
            rv.status_code = 202

        elif isinstance(resp, ApiError):
            rv = resp.to_dict()
            rv['status'] = 'ERROR'
            rv = jsonify(current_app.response_wrapper(rv))
            rv.status_code = resp.status_code

        elif isinstance(resp, dict):
            rv.setdefault('status', 'OK')
            rv = jsonify(current_app.response_wrapper(resp))

        elif resp is None:
            rv = jsonify(current_app.response_wrapper({'status': 'OK'}))

        return super().force_type(rv, environ)


class Flask(Flask):
    response_class = ApiResponse
    json_encoder = ApiJSONEncoder
    config_class = Config

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_api_error_handlers()

    def configure(self, cors=False, sqlalchemy=False, marshmallow=False,
                  redis=False, celery=False):
        self.config['TESTING'] = (os.environ.get('FLASK_TESTING', False) or
                                  sys.argv[0].endswith('pytest') or
                                  self.config.get('TESTING', False))

        self.config.resolve_lazy_values()

        if self.testing:
            for key, value in self.config.items():
                if key.startswith('TESTING_'):
                    self.config[key[8:]] = value
            register_test_helpers(self)

        if self.config.get('LOGGING'):
            # Turn off werkzeug default handlers not to duplicate logs
            logging.getLogger('werkzeug').handlers = []
            logging.config.dictConfig(self.config['LOGGING'])

        if self.config.get('FLASK_SHELL_CONTEXT'):
            register_shell_context(self, *self.config['FLASK_SHELL_CONTEXT'])

        if self.config.get('DOZER'):
            from dozer import Dozer
            self.wsgi_app = Dozer(self.wsgi_app)

        if self.config.get('DOZER_PROFILER'):
            from dozer import Profiler
            self.wsgi_app = Profiler(self.wsgi_app)

        if cors:
            # options parsed from config
            # see https://github.com/corydolphin/flask-cors/blob/master/flask_cors/core.py
            from flask_cors import CORS
            CORS(self)

        if sqlalchemy:
            from .sqla import SQLAlchemy
            db = SQLAlchemy(self)
            try:
                from flask_migrate import Migrate
            except ImportError:
                pass
            else:
                Migrate(self, db, compare_type=True)

        if marshmallow:
            from flask_marshmallow import Marshmallow
            Marshmallow(self)

        if redis:
            from .redis import create_redis
            create_redis(self)

        if celery:
            from .celery import create_celery
            create_celery(self, task_views=True)

    def response_wrapper(self, resp):
        """Wrapper before jsonify, to extend response dict with meta-data"""
        return resp

    def _register_api_error_handlers(self):
        def response(status_code, error):
            error['status'] = 'ERROR'
            resp = jsonify(self.response_wrapper(error))
            resp.status_code = status_code
            return resp

        @self.errorhandler(ValidationError)
        def handle_validation_error(exc):
            return handle_api_error(EntityError.from_validation_error(exc))

        @self.errorhandler(ApiError)
        def handle_api_error(exc):
            return response(exc.status_code, exc.to_dict())

        @self.errorhandler(404)
        def handle_404_error(exc):
            return response(404, {
                'message': 'URL not found: {}'.format(request.url),
                'code': 404,
            })

        @self.errorhandler(400)
        def handle_400_error(exc):
            return response(400, {
                'message': 'Bad request: {}'.format(exc.description),
                'code': 400,
            })

        @self.errorhandler(Exception)
        def handle_internal_error(exc):
            if self.debug and (self.testing or request.headers.get('X-DEBUGGER') or
                               self.config.get('FLASK_DEBUGGER_ALWAYS')):
                raise  # raising exception to werkzeug debugger

            err = {
                'code': 500,
                'message': str(exc),
                'type': exc.__class__.__name__,
                'args': [str(x) for x in getattr(exc, 'args', [])],
            }
            if self.debug:
                err.update({
                    'traceback': [tuple(row) for row in traceback.extract_tb(exc.__traceback__)],
                    'stack': [tuple(row) for row in traceback.extract_stack()],
                })
            self.logger.exception('Unexpected exception: %r', exc)
            return response(500, err)
