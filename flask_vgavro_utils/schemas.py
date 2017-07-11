import marshmallow as ma
from marshmallow import fields, validate


class SeparatedStr(fields.List):
    """
    Used for loading "value1,value2" strings. Works like marshmallow.fields.List,
    so you may pass another field in init (defaults to marshmallow.fields.String).
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


class NestedLazy(fields.Nested):
    """
    Nested schema with difference, that it may not be cached on field and
    initialized from callback.
    Usage: some_field = NestedLazy(lambda field: schema_cls_or_instance)
    """
    def __init__(self, nested_callable, *args, **kwargs):
        self.nested_cache = kwargs.pop('cache', False)
        self.nested_callable = nested_callable
        super().__init__(None, *args, **kwargs)

    @property
    def schema(self):
        if hasattr(self, '_Nested__schema'):
            if self.nested_cache:
                return self._Nested__schema
            else:
                self._Nested__schema = None
        self.nested = self.nested_callable(self)
        return super().schema


class StrictSchemaMixin:
    """
    As there is no schema.Meta inheritance, defaults to strict=True on initialization.
    """
    def __init__(self, *args, **kwargs):
        if 'strict' not in kwargs and not hasattr(self.Meta, 'strict'):
            kwargs.update({'strict': True})
        super().__init__(*args, **kwargs)


def attach_marshmallow_helpers(ma_):
    ma_.SeparatedStr = SeparatedStr
    ma_.NestedLazy = NestedLazy
    ma_.validate = validate
    ma_.ValidationError = ma.ValidationError
    for decorator_name in ('pre_dump', 'post_dump', 'pre_load', 'post_load',
                           'validates', 'validates_schema'):
        setattr(ma_, decorator_name, getattr(ma, decorator_name))
