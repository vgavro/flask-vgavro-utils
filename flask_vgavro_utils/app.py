from flask import Response, jsonify

from .exceptions import ApiError
from .schemas import dump_with_schemas


def register_api_error_handlers(app, exception=ApiError, wrapper=lambda r: r):
    @app.errorhandler(exception)
    def handle_api_error(exc):
        error = exc.data.copy()
        error['message'] = exc.message
        error['code'] = exc.code
        response = jsonify(wrapper({'error': error}))
        response.status_code = exc.status_code
        return response


def register_api_response(app, schemas_map, wrapper=lambda r: r):
    from celery.result import AsyncResult

    class ApiResponse(Response):
        @classmethod
        def force_type(cls, response, environ=None):
            if isinstance(response, AsyncResult):
                response = jsonify(wrapper({'task_id': response.id})), 202
            elif isinstance(response, dict):
                response = jsonify(wrapper(dump_with_schemas(response, schemas_map)))
            return super(ApiResponse, cls).force_type(response, environ)

    app.response_class = ApiResponse
