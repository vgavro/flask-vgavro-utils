import logging
import logging.config
import datetime
import decimal
import enum
import traceback

from flask import Flask, Response, jsonify, request, current_app
from flask.json import JSONEncoder
from marshmallow import ValidationError

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
    def force_type(cls, response, environ=None):
        if isinstance(response, EagerResult):
            response.maybe_throw()
            response = response.result  # TODO: also wrapper here?
        if isinstance(response, AsyncResult):
            response = jsonify(current_app.response_wrapper({'task_id': response.id}))
            response.status_code = 202
        elif isinstance(response, dict):
            response = jsonify(current_app.response_wrapper(response))
        return super().force_type(response, environ)


class ApiFlask(Flask):
    response_class = ApiResponse
    json_encoder = ApiJSONEncoder

    def __init__(self, *args, config_from_object=None, **kwargs):
        super().__init__(*args, **kwargs)
        if config_from_object:
            self.config.from_object(config_from_object)

        LazyConfigValue.resolve_config(self.config)

        if self.testing:
            for key, value in self.config.items():
                if key.startswith('TESTING_'):
                    self.config[key[8:]] = value

        if self.config.get('LOGGING'):
            # Turn off werkzeug default handlers not to duplicate logs
            logging.getLogger('werkzeug').handlers = []
            logging.config.dictConfig(self.config['LOGGING'])

        self._register_api_error_handlers()

    def response_wrapper(self, response):
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
