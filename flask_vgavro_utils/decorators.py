from functools import wraps

from marshmallow import Schema
from flask import request

from .schemas import StrictSchemaMixin


DEFAULT_BASE_SCHEMA = type('StrictSchema', (StrictSchemaMixin, Schema), {})


def create_schema(schema_or_dict, extends=None, **kwargs):
    if extends:
        if not any(map(lambda s: issubclass(s, Schema), extends)):
            extends = tuple(extends) + (Schema,)
    else:
        extends = (DEFAULT_BASE_SCHEMA,)

    if isinstance(schema_or_dict, type):
        return schema_or_dict(**kwargs)
    elif isinstance(schema_or_dict, dict):
        # NOTE: maybe deepcopy?
        return type('_Schema', extends, schema_or_dict.copy())(**kwargs)
    else:
        assert isinstance(schema_or_dict, Schema)
        return schema_or_dict


def request_schema(schema_or_dict, extends=None, many=None, cache_schema=True):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)

            data = schema.load(request.json, many=many).data
            kwargs.update({'data': data})
            return func(*args, **kwargs)

        return wrapper
    return decorator


def request_args_schema(schema_or_dict, extends=None, cache_schema=True):
    schema_ = create_schema(schema_or_dict, extends)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            schema = cache_schema and schema_ or create_schema(schema_or_dict, extends)
            request_args = schema.load(request.args).data
            kwargs.update(request_args)
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
