import json
from datetime import datetime, date


def repr_response(resp, full=False):
    # requests.models.Response
    if not full and len(resp.content) > 128:
        content = '{}...{}b'.format(resp.content[:128],
                                    len(resp.content))
    else:
        content = resp.content
    return '{} {} {}: {}'.format(
        resp.request.method,
        resp.status_code,
        resp.url,
        content
    )


def repr_str_short(value, length=32):
    if len(value) > length:
        return value[:length] + '...'
    return value


class ReprMixin:
    def __repr__(self, *args, full=False, required=False, **kwargs):
        attrs = self.to_dict(*args, required=required, **kwargs)
        attrs = ', '.join(u'{}={}'.format(k, repr(v) if full else repr_str_short(repr(v)))
                          for k, v in attrs.items())
        return '<{}({})>'.format(self.__class__.__name__, attrs)

    def to_dict(self, *args, exclude=[], required=True):
        keys = args or (self.__dict__.keys() if hasattr(self, '__dict__') else self.__slots__)
        return {k: getattr(self, k) for k in keys
                if not k.startswith('_') and
                (hasattr(self, k) or (args and required and k in args)) and
                k not in exclude}

    def _pprint(self, *args, **kwargs):
        return pprint(self, *args, **kwargs)


def pprint(obj, indent=2, colors=True):
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return repr(obj)

    rv = json.dumps(obj, default=default, indent=indent, ensure_ascii=False)

    if colors:
        try:
            from pygments import highlight
            from pygments.lexers import JsonLexer
            from pygments.formatters import TerminalFormatter
        except ImportError:
            pass
        else:
            rv = highlight(rv, JsonLexer(), TerminalFormatter())

    print(rv)
