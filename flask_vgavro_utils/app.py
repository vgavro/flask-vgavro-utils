import os
import sys
import logging
import logging.config
import datetime
import decimal
import enum
import traceback

from werkzeug.utils import ImportStringError
from flask import Flask, Response, jsonify, request, current_app
from flask.json import JSONEncoder
from marshmallow import ValidationError
from flask_cors import CORS

from .exceptions import ApiError, EntityError
from .config import LazyConfigValue

try:
    from celery.result import EagerResult, AsyncResult
except ImportError:
    EagerResult, AsyncResult = (), ()  # for isinstance False


class ApiJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if isinstance(obj, enum.Enum):
            return obj.name
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)


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
            rv = jsonify(current_app.response_wrapper(resp.to_dict()))
            rv.status_code = resp.status_code

        elif isinstance(resp, dict):
            rv = jsonify(current_app.response_wrapper(resp))

        return super().force_type(rv, environ)


class ApiFlask(Flask):
    response_class = ApiResponse
    json_encoder = ApiJSONEncoder

    def __init__(self, *args, config_object=None, config_override_object=None,
                 cors=False, response_wrapper=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure(config_object, config_override_object, cors)
        self._register_api_error_handlers()
        if response_wrapper:
            self.response_wrapper = response_wrapper

    def _configure(self, config_object, config_override_object, cors):
        self.config['TESTING'] = (os.environ.get('FLASK_TESTING', False) or
                                  sys.argv[0].endswith('pytest'))

        if config_object:
            self.config.from_object(config_object)

        if config_override_object:
            try:
                self.config.from_object(config_override_object)
            except ImportStringError as exc:
                exc = exc.exception
                if not (exc.args[0] and exc.args[0].startswith('No module named') and
                   config_override_object in exc.args[0]):
                    # skip if override module not exist, raise otherwise
                    raise

        LazyConfigValue.resolve_config(self.config)

        if self.testing:
            for key, value in self.config.items():
                if key.startswith('TESTING_'):
                    self.config[key[8:]] = value

        if cors:
            # options parsed from config
            # see https://github.com/corydolphin/flask-cors/blob/master/flask_cors/core.py
            CORS(self)

        if self.config.get('LOGGING'):
            # Turn off werkzeug default handlers not to duplicate logs
            logging.getLogger('werkzeug').handlers = []
            logging.config.dictConfig(self.config['LOGGING'])

    def response_wrapper(self, response):
        """Wrapper before jsonify, to extend response dict with meta-data"""
        return response

    def _register_api_error_handlers(self):
        def response(status_code, error):
            response = jsonify(self.response_wrapper({'error': error}))
            response.status_code = status_code
            return response

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
                               self.config.get('FLASK_DEBUGGER_ALWAYS_ON_ERROR')):
                raise  # raising exception to werkzeug debugger

            err = {
                'code': 500,
                'message': str(exc),
                'repr': repr(exc),
            }
            if self.debug:
                err.update({
                    'traceback': [tuple(row) for row in traceback.extract_tb(exc.__traceback__)],
                    'stack': [tuple(row) for row in traceback.extract_stack()],
                })
            self.logger.exception('Unexpected exception: %r', exc)
            return response(500, err)
