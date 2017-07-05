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


class EntityError(ApiError):
    status_code = 422

    @classmethod
    def from_schema_errors(cls, errors):
        if errors:
            schema_errors = errors.pop('_schema', None)
            if schema_errors:
                errors[''] = schema_errors
                message = schema_errors[0]
            else:
                message = tuple(errors.values())[0][0]
            return cls(message, data={'errors': errors})

    @classmethod
    def from_validation_error(cls, exc):
        return cls.from_schema_errors(exc.normalized_messages())
