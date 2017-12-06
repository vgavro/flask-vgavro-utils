import datetime
import decimal
import enum
import traceback

from flask import Response, jsonify, request
from flask.json import JSONEncoder
from marshmallow import ValidationError

from .exceptions import ApiError, EntityError


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


def register_api_error_handlers(app, exception=ApiError, wrapper=lambda r: r):
    def response(status_code, error):
        response = jsonify(wrapper({'error': error}))
        response.status_code = status_code
        return response

    @app.errorhandler(ValidationError)
    def handle_validation_error(exc):
        return handle_api_error(EntityError.from_validation_error(exc))

    @app.errorhandler(exception)
    def handle_api_error(exc):
        return response(exc.status_code, exc.to_dict())

    @app.errorhandler(404)
    def handle_404_error(exc):
        return response(404, {
            'message': 'URL not found: {}'.format(request.url),
            'code': 404,
        })

    @app.errorhandler(Exception)
    def handle_internal_error(exc):
        if app.debug and (app.testing or request.headers.get('X-DEBUGGER') or
                          app.config.get('FLASK_DEBUGGER_ALWAYS_ON_ERROR')):
            raise  # raising exception to werkzeug debugger

        err = {
            'code': 500,
            'message': str(exc),
            'repr': repr(exc),
        }
        if app.debug:
            err.update({
                'traceback': [tuple(row) for row in traceback.extract_tb(exc.__traceback__)],
                'stack': [tuple(row) for row in traceback.extract_stack()],
            })
        return response(500, err)


def register_api_response(app, wrapper=lambda r: r):
    try:
        from celery.result import EagerResult, AsyncResult
    except ImportError:
        EagerResult, AsyncResult = (), ()  # for isinstance False

    class ApiResponse(Response):
        @classmethod
        def force_type(cls, response, environ=None):
            if isinstance(response, EagerResult):
                response.maybe_throw()
                response = response.result
            if isinstance(response, AsyncResult):
                response = jsonify(wrapper({'task_id': response.id}))
                response.status_code = 202
            elif isinstance(response, dict):
                response = jsonify(wrapper(response))
            return super().force_type(response, environ)

    app.response_class = ApiResponse
    app.json_encoder = ApiJSONEncoder
