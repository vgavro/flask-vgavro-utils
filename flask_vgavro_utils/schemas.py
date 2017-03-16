from marshmallow import post_load

from .exceptions import EntityError
from .utils import is_instance_or_proxied


class SchemaRaiseOnErrorsMixin(object):
    def load(self, *args, **kwargs):
        raise_on_errors = kwargs.pop('raise_on_errors', True)
        data, errors = super().load(*args, **kwargs)
        if raise_on_errors:
            self.raise_on_load_errors(errors)
        return data

    def dump(self, *args, **kwargs):
        raise_on_errors = kwargs.pop('raise_on_errors', True)
        data, errors = super().dump(*args, **kwargs)
        if raise_on_errors:
            assert (not errors), errors  # TODO: raise 500 with description
        return data

    def raise_on_load_errors(self, errors):
        EntityError.raise_on_schema_errors(errors)


def dump_with_schemas(data, schemas_map):
    """
    Recursively search for key in model schemas, dump if sqlalchemy model matches
    """

    for key, value in data.items():
        if key in schemas_map:
            schema = schemas_map[key]

            if (isinstance(value, (list, tuple)) and len(value) and
               schema.many and is_instance_or_proxied(value[0], schema.Meta.model)):
                data[key] = schema.dump(value).data

            elif is_instance_or_proxied(value, schema.Meta.model):
                data[key] = schema.dump(value).data

        elif (isinstance(value, (list, tuple)) and len(value) and
              isinstance(value[0], dict)):
            data[key] = [dump_with_schemas(d, schemas_map) for d in value]

        elif isinstance(value, dict):
            data[key] = dump_with_schemas(value, schemas_map)

    return data


def attach_marshmallow_helpers(ma):
    import marshmallow
    import marshmallow.validate

    ma.validate = marshmallow.validate
    ma.ValidationError = marshmallow.ValidationError
    for decorator_name in ('pre_dump', 'post_dump', 'pre_load,' 'post_load',
                           'validates', 'validates_schema'):
        setattr(ma, decorator_name, getattr(marshmallow, decorator_name))
