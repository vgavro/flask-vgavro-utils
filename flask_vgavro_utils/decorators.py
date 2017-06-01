from functools import wraps

from flask_marshmallow import Schema
from flask import request

from .schemas import SchemaRaiseOnErrorsMixin

DEFAULT_BASE_SCHEMA = type('Schema', (SchemaRaiseOnErrorsMixin, Schema), {})


def _create_schema(schema, extends=None):
    extends = extends or (DEFAULT_BASE_SCHEMA,)
    if not any(map(lambda s: issubclass(s, Schema), extends)):
        extends = tuple(extends) + (Schema,)

    if isinstance(schema, type):
        return schema()
    elif isinstance(schema, dict):
        return type('_Schema', extends, schema)()
    else:
        return schema


def request_schema(schema, extends=None, many=None):
    schema = _create_schema(schema, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = schema.load(request.json, many=many)[0]
            kwargs.update({'data': data})
            return func(*args, **kwargs)
        return wrapper
    return decorator


def request_args_schema(schema, extends=None):
    schema = _create_schema(schema, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request_args = schema.load(request.args)[0]
            kwargs.update(request_args)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def response_schema(schema, extends=None, many=None):
    schema = _create_schema(schema, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, (list, tuple)) and (schema.many or many):
                return schema.dump(result, many=many)[0]
            return schema.dump(result, many=many)[0]
            return result
        return wrapper
    return decorator
