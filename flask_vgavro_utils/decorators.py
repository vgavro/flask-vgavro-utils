from functools import wraps

from flask import request, make_response

from .exceptions import ApiError
from .schemas import create_schema, ma_version_lt_300b7


def request_schema(schema_or_dict, extends=None, many=None, cache_schema=True, pass_data=False):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)
            if request.json is None:
                # NOTE: this should be fixed with marshmallow 3 (and 2.16?)
                raise ApiError('JSON data required')

            data = schema.load(request.json, many=many)
            if ma_version_lt_300b7:
                data = data.data
            if pass_data:
                kwargs.update({'data' if pass_data is True else pass_data: data})
            else:
                kwargs.update(data)
            return func(*args, **kwargs)

        return wrapper
    return decorator


def request_args_schema(schema_or_dict, extends=None, cache_schema=True, pass_data=False):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)
            data = schema.load(request.args)
            if ma_version_lt_300b7:
                data = data.data
            if pass_data:
                kwargs.update({'data' if pass_data is True else pass_data: data})
            else:
                kwargs.update(data)
            return func(*args, **kwargs)

        return wrapper
    return decorator


def response_schema(schema_or_dict, extends=None, many=None, cache_schema=True):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)
            result = func(*args, **kwargs)
            if isinstance(result, (list, tuple)) and (schema.many or many):
                data = schema.dump(result, many=many)
            else:
                data = schema.dump(result, many=many)
            if ma_version_lt_300b7:
                data = data.data
            return data

        return wrapper
    return decorator


def response_headers(headers={}):
    """
    This decorator adds the headers passed in to the response
    """
    # http://flask.pocoo.org/snippets/100/
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            resp = make_response(func(*args, **kwargs))
            h = resp.headers
            for header, value in headers.items():
                h[header] = value
            return resp
        return wrapper
    return decorator


def response_headers_no_cache(func):
    @wraps(func)
    @response_headers({
        'Cache-Control': 'no-store',
        'Pragma': 'no-cache',
    })
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
