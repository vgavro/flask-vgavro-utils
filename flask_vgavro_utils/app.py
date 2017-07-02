import datetime
from decimal import Decimal
import traceback

from flask import Response, jsonify, request
from flask.json import JSONEncoder

from .exceptions import ApiError


class ApiJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def register_api_error_handlers(app, exception=ApiError, wrapper=lambda r: r):
    def response(status_code, error):
        response = jsonify(wrapper({'error': error}))
        response.status_code = status_code
        return response

    @app.errorhandler(exception)
    def handle_api_error(exc):
        error = exc.data.copy()
        error['message'] = exc.message
        error['code'] = exc.code
        return response(exc.status_code, error)

    @app.errorhandler(404)
    def handle_404_error(exc):
        return response(404, {
            'message': 'URL not found: {}'.format(request.url),
            'code': 404,
        })

    @app.errorhandler(Exception)
    def handle_internal_error(exc):
        if app.debug and (request.headers.get('X-FLASK-DEBUGGER') or
                          app.config.get('FLASK_DEBUGGER')):
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
    from celery.result import EagerResult, AsyncResult

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
