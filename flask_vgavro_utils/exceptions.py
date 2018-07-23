class ImproperlyConfigured(Exception):
    pass


class ApiError(Exception):
    status_code = 400

    def __init__(self, message, code=None, data=None, **kwargs):
        self.message = message
        self.code = code
        if not code or code > 600:
            self.code = self.status_code
        self.data = data and dict(data) or {}
        self.data.update(kwargs)
        super().__init__(message, self.code, self.data)

    def to_dict(self):
        result = self.data.copy()
        result['message'] = self.message or self.data.get('message')
        result['code'] = self.code
        return result


class ForbiddenError(ApiError):
    status_code = 403

    def __init__(self, message='Access forbidden', *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class NotFoundError(ApiError):
    status_code = 404


class EntityError(ApiError):
    status_code = 422

    @classmethod
    def from_validation_error(cls, exc):
        errors = exc.normalized_messages()
        message = cls._get_first_error(errors)
        data = {
            'errors': errors,
            'data': exc.data,
            'valid_data': exc.valid_data,
        }
        if hasattr(exc, 'schema'):
            data['schema'] = exc.schema.__class__.__name__
        return cls(message, data=data)

    @classmethod
    def for_fields(cls, data=None, **errors):
        message = data.get('message') or cls._get_first_error(errors)
        return cls(message, data=data, errors=errors)

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
