class ImproperlyConfigured(Exception):
    pass


class ApiError(Exception):
    status_code = 400

    def __init__(self, message, code=None, data={}):
        self.message = message
        self.code = code or self.status_code
        self.data = data
        super().__init__(message, code, data)


class ApiNotFound(ApiError):
    status_code = 404


class EntityError(ApiError):
    status_code = 422

    @classmethod
    def raise_on_schema_errors(cls, errors):
        if errors:
            schema_errors = errors.pop('_schema', None)
            if schema_errors:
                errors[''] = schema_errors
                message = schema_errors[0]
            else:
                message = list(errors.values())[0]
            raise cls(message, data={'errors': errors})
