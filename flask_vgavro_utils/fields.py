from collections import defaultdict

from marshmallow import fields
from marshmallow.utils import missing

from .utils import resolve_obj_key


class SeparatedStr(fields.List):
    """
    Used for loading "value1,value2" strings. Works like marshmallow.fields.List,
    so you may pass another field in init (defaults to marshmallow.fields.String).
    """

    def __init__(self, cls_or_instance=None, separator=',', **kwargs):
        self.separator = separator
        super().__init__(cls_or_instance or fields.Str, **kwargs)

    def _serialize(self, value, attr, obj):
        value = self.separator.join(map(str, value))
        return super()._deserialize(value, attr, obj)

    def _deserialize(self, value, attr, data):
        value = tuple(filter(None, value.split(self.separator)))
        return super()._deserialize(value, attr, data)


class Nested(fields.Nested):
    # NOTE: Fix to fallback schema load to schema defaults
    # instead of overriding unknown='raise'.
    # While not merged https://github.com/marshmallow-code/marshmallow/pull/963

    def __init__(self, nested, **kwargs):
        kwargs.setdefault('unknown', None)
        super().__init__(nested, **kwargs)


class NestedLazy(Nested):
    """
    Nested schema with difference, that it may not be cached on field and
    initialized from callback.
    Usage: some_field = NestedLazy(lambda field: schema_cls_or_instance)
    """
    def __init__(self, nested_callable, *args, **kwargs):
        # if not callable(nested_callable):
        #     raise ValueError('nested_schema must be callable')
        self.nested_callable = nested_callable
        self.nested_cache = kwargs.pop('cache', False)
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


class NestedFromValue(NestedLazy):
    """
    Nested schema that is based on value of other parent schema field.
    Usage:
    class MySchema(ma.Schema):
        TYPE_DATA_SCHEMA_MAP = {
            'type1': Type1DataSchema,
            'type2': Type2DataSchema,
        }
        type = ma.fields.Str()
        data = NestedFromValue('type', TYPE_DATA_SCHEMA_MAP)
    """
    def __init__(self, key_or_getter, schema_map, *args, **kwargs):
        if kwargs.get('many'):
            raise NotImplementedError()
        if callable(key_or_getter):
            self._getter = key_or_getter
        else:
            self._getter = lambda obj: resolve_obj_key(obj, key_or_getter)
        self._value = missing
        self.schema_map = schema_map
        super().__init__(self._get_schema_from_value, cache=False, **kwargs)

    def _get_schema_from_value(self, field):
        # NOTE: self and field is different instances, because self is not binded,
        # and field is binded (marshmallow do it using deepcopy)
        try:
            return self.schema_map[field._value]
        except KeyError:
            raise ValueError('Unknown schema for {}'.format(field._value))

    def _pre_load(self, obj):
        self._value = self._getter(obj)
        return obj

    _pre_load.__marshmallow_kwargs__ = _pre_load.__marshmallow_hook__ = defaultdict(dict)
    _pre_dump = _pre_load

    # Actually we don't need post processors, but just for sanity reasons
    def _post_load(self, obj):
        self._value = missing
        return obj

    _post_load.__marshmallow_kwargs__ = _post_load.__marshmallow_hook__ = defaultdict(dict)
    _post_dump = _post_load

    def _bind_to_schema(self, field_name, parent):
        super()._bind_to_schema(field_name, parent)

        # Binding tag processors to parent schema,
        # tricky shit because of marshmallow design...
        # We're setting processors for instance, not for class!
        for tag in ('pre_load', 'pre_dump', 'post_load', 'post_dump'):
            attr = '_{}_{}_schema'.format(tag, field_name)
            if hasattr(parent, attr):
                # Is fields binded on each load? wtf?
                continue
            setattr(parent, attr, getattr(self, '_{}'.format(tag)))
            if hasattr(parent, '__processors__'):
                # Older versions for 2.x and possible some beta versions
                hooks = parent.__processors__ = parent.__processors__.copy()
            else:
                # New version (at least since 3.0.0.b12)
                hooks = parent._hooks = parent._hooks.copy()
            # (tag, many?) - for now only for many=False just not to test other case,
            # there may be issues with many=True
            hooks[(tag, False)].append(attr)
