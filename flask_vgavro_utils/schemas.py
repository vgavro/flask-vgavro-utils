# TODO: rename this module to ma

import marshmallow as ma
from .fields import *  # noqa (compatibility)

# https://github.com/marshmallow-code/marshmallow/pull/711/files
ma_version_lt_300b7 = hasattr(ma.schema, 'MarshalResult')


if ma_version_lt_300b7:
    class StrictSchemaMixin:
        """
        As there is no schema.Meta inheritance, defaults to strict=True on initialization.
        """
        def __init__(self, *args, **kwargs):
            if 'strict' not in kwargs and not hasattr(self.Meta, 'strict'):
                kwargs['strict'] = True
            super().__init__(*args, **kwargs)
else:
    # It's strict by default and can't be changed
    class StrictSchemaMixin:
        pass


if (
    hasattr(ma.schema.BaseSchema, 'unknown')
    # Introduced in 3.0.0b12 (2018-07-04)
    # https://github.com/marshmallow-code/marshmallow/pull/838
    or 'unknown' in getattr(ma.schema.BaseSchema, '_default_error_messages', {})
    # in marshmallow 3.2 unknown attribute not in Schema class, but is set after __init__,
    # maybe introduced in earlier versions..
):
    class UnknownExcludeSchemaMixin:
        """
        As there is no schema.Meta inheritance, defaults to unknown='exclude' on initialization.
        """
        def __init__(self, *args, **kwargs):
            if 'unknown' not in kwargs and not hasattr(self.Meta, 'unknown'):
                kwargs['unknown'] = 'exclude'
            super().__init__(*args, **kwargs)
else:
    class UnknownExcludeSchemaMixin:
        pass


class Schema(UnknownExcludeSchemaMixin, ma.Schema):
    def handle_error(self, exc, obj, **kwargs):
        # TODO: maybe it's not actual already,
        # because in marshmallow 3 wee set this anyway?
        exc.schema = self
        raise exc


def create_schema(schema_or_dict, extends=None, **kwargs):
    if extends:
        if not any(map(lambda s: issubclass(s, ma.Schema), extends)):
            extends = tuple(extends) + (Schema,)
    else:
        extends = (Schema,)

    if ma_version_lt_300b7:
        kwargs.setdefault('strict', True)

    if isinstance(schema_or_dict, type):
        return schema_or_dict(**kwargs)
    elif isinstance(schema_or_dict, dict):
        # NOTE: maybe deepcopy?
        return type('_Schema', extends, schema_or_dict.copy())(**kwargs)
    else:
        assert isinstance(schema_or_dict, ma.Schema)
        if ma_version_lt_300b7:
            assert schema_or_dict.strict, 'TypeError on silently passing errors'
        return schema_or_dict
