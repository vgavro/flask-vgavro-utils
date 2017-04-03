from .exceptions import EntityError


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


def attach_marshmallow_helpers(ma):
    import marshmallow
    import marshmallow.validate

    ma.validate = marshmallow.validate
    ma.ValidationError = marshmallow.ValidationError
    for decorator_name in ('pre_dump', 'post_dump', 'pre_load,' 'post_load',
                           'validates', 'validates_schema'):
        setattr(ma, decorator_name, getattr(marshmallow, decorator_name))
