import os

from werkzeug.utils import import_string
from flask import current_app


def create_shell_context(*paths):
    result = {}
    for path in paths:
        if '.' in path:
            name = path.split('.')[-1]
            if name == '*':
                path = '.'.join(path.split('.')[:-1])
                module = import_string(path)
                result.update(module.__dict__)
            else:
                result[name] = import_string(path)
        else:
            result[path] = import_string(path)

    return {k: v for k, v in result.items() if not k.startswith('__')}


def register_shell_context(app, *paths):
    @app.shell_context_processor
    def shell_context_processor():
        return create_shell_context(*paths)


def dbshell():
    """Database shell (currently only PostgreSQL supported)."""

    db = current_app.extensions['sqlalchemy'].db
    assert db.engine.name == 'postgresql'
    cmd, url = 'psql', db.engine.url
    url_map = (('U', 'username'), ('h', 'host'), ('p', 'port'), ('d', 'database'))
    for psql_key, url_attr in url_map:
        if getattr(url, url_attr, None):
            cmd += ' -{} {}'.format(psql_key, getattr(url, url_attr))
    return os.system(cmd)


def register_cli_dbshell(app):
    # TODO: make it easier and without this function using click directly
    app.cli.command()(dbshell)
