class ImproperlyConfigured(Exception):
    pass


class ApiError(Exception):
    status_code = 400

    def __init__(self, message, code=None, data=None, **kwargs):
        self.message = message
        self.code = code or self.status_code
        self.data = data or {}
        self.data.update(kwargs)
        super().__init__(message, self.code, self.data)

    def to_dict(self):
        result = self.data.copy()
        result['message'] = self.message
        result['code'] = self.code
        return result


class NotFoundError(ApiError):
    status_code = 404


def _convert_int_keys_to_str(dict_):
    for k, v in dict_.items():
        if isinstance(k, int):
            dict_[str(k)] = v
            del dict_[k]
        if isinstance(v, dict):
            _convert_int_keys_to_str(v)


class EntityError(ApiError):
    status_code = 422

    @classmethod
    def from_schema_errors(cls, errors):
        if errors:
            message = cls._get_first_error(errors)
            # To sort keys on json dump (default flask behaviour)
            _convert_int_keys_to_str(errors)
            return cls(message, data={'errors': errors})

    @classmethod
    def from_validation_error(cls, exc):
        return cls.from_schema_errors(exc.normalized_messages())

    @classmethod
    def _get_first_error(cls, errors):
        if '_schema' in errors:
            return errors['_schema'][0]
        field_errors = tuple(errors.values())[0]
        if isinstance(field_errors, (tuple, list)):
            return field_errors[0]
        elif isinstance(field_errors, dict):
            # nested schema error
            return cls._get_first_error(field_errors)
        raise ValueError('Unknown field error type: {}'.format(field_errors))
