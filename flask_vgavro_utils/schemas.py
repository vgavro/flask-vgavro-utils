import marshmallow as ma
from marshmallow import fields, validate

from .exceptions import EntityError


class SeparatedStr(fields.List):
    """
    Used for loading "value1,value2". works like List,
    so you may pass another field in init (defaults to String).
    """

    def __init__(self, cls_or_instance=None, separator=',', **kwargs):
        self.separator = separator
        super().__init__(cls_or_instance or ma.Str, **kwargs)

    def _serialize(self, value, attr, obj):
        value = self.separator.join(map(str, value))
        return super()._deserialize(value, attr, obj)

    def _deserialize(self, value, attr, data):
        value = tuple(filter(None, value.split(self.separator)))
        return super()._deserialize(value, attr, data)


class SchemaRaiseOnErrorsMixin(object):
    def load(self, *args, **kwargs):
        raise_on_errors = kwargs.pop('raise_on_errors', True)
        data, errors = super().load(*args, **kwargs)
        if raise_on_errors:
            self.raise_on_load_errors(errors)
        return data, errors

    def dump(self, *args, **kwargs):
        raise_on_errors = kwargs.pop('raise_on_errors', True)
        data, errors = super().dump(*args, **kwargs)
        if raise_on_errors:
            assert (not errors), errors  # TODO: raise 500 with description
        return data, errors

    def raise_on_load_errors(self, errors):
        EntityError.raise_on_schema_errors(errors)


def attach_marshmallow_helpers(ma_):
    ma_.SeparatedStr = SeparatedStr
    ma_.validate = validate
    ma_.ValidationError = ma.ValidationError
    for decorator_name in ('pre_dump', 'post_dump', 'pre_load', 'post_load',
                           'validates', 'validates_schema'):
        setattr(ma_, decorator_name, getattr(ma, decorator_name))
