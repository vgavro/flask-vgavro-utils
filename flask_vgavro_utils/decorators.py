from functools import wraps

from marshmallow import Schema
from flask import request, make_response


def create_schema(schema_or_dict, extends=None, **kwargs):
    if extends:
        if not any(map(lambda s: issubclass(s, Schema), extends)):
            extends = tuple(extends) + (Schema,)
    else:
        extends = (Schema,)
    kwargs.setdefault('strict', True)

    if isinstance(schema_or_dict, type):
        return schema_or_dict(**kwargs)
    elif isinstance(schema_or_dict, dict):
        # NOTE: maybe deepcopy?
        return type('_Schema', extends, schema_or_dict.copy())(**kwargs)
    else:
        assert isinstance(schema_or_dict, Schema)
        assert schema_or_dict.strict, 'TypeError on silently passing errors'
        return schema_or_dict


def request_schema(schema_or_dict, extends=None, many=None, cache_schema=True, pass_data=False):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)

            data = schema.load(request.json, many=many).data
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
            data = schema.load(request.args).data
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
                return schema.dump(result, many=many).data
            return schema.dump(result, many=many).data

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
