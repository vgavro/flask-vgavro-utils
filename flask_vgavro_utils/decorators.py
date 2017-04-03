from flask_marshmallow import Schema
from flask import request

from .schemas import SchemaRaiseOnErrorsMixin

DEFAULT_BASE_SCHEMA = type('Schema', (SchemaRaiseOnErrorsMixin, Schema), {})


def _create_schema(schema, inherit=None):
    inherit = inherit or (DEFAULT_BASE_SCHEMA,)
    if isinstance(schema, type):
        return schema()
    elif isinstance(schema, dict):
        return type('_Schema', inherit, schema)()
    else:
        return schema


def request_schema(schema, inherit=None, many=None):
    schema = _create_schema(schema, inherit)

    def decorator(func):
        def wrapper(*args, **kwargs):
            data = schema.load(request.json, many=many)[0]
            kwargs.update({'data': data})
            return func(*args, **kwargs)
        return wrapper
    return decorator


def request_args_schema(schema, inherit=None):
    schema = _create_schema(schema, inherit)

    def decorator(func):
        def wrapper(*args, **kwargs):
            request_args = schema.load(request.args)[0]
            kwargs.update(request_args)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def response_schema(schema, inherit=None, many=None):
    schema = _create_schema(schema, inherit)

    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                return schema.dump(result, many=many)[0]
            elif isinstance(result, list) and (schema.many or many):
                return schema.dump(result, many=many)[0]
            return result
        return wrapper
    return decorator
