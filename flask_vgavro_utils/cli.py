import os

from werkzeug.utils import import_string
from flask import current_app
from flask.cli import with_appcontext
import click

from .tests import register_test_helpers
from .sqla import db_reinit


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


def register_shell_context(app, *context_paths, test_helpers=True):
    @app.shell_context_processor
    def shell_context_processor():
        ctx = {}
        if test_helpers:
            register_test_helpers(app)
            ctx['client'] = app.test_client()
        ctx.update(create_shell_context(*context_paths))
        return ctx


@click.command()
@click.option('--verbose', '-v', is_flag=True)
@click.option('--no-confirm', is_flag=True)
@click.option('--bind', '-b', default=None)
@with_appcontext
def dbreinit(verbose, no_confirm, bind=None):
    """Reinitialize database (temporary before using alembic migrations)"""
    if not no_confirm:
        click.confirm('This will drop ALL DATA. Do you want to continue?', abort=True)
    db = current_app.extensions['sqlalchemy'].db
    if verbose:
        echo_ = db.engine.echo
        db.engine.echo = True
    db_reinit(db, bind)
    if verbose:
        db.engine.echo = echo_


@click.command()
@with_appcontext
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
