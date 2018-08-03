import logging
import contextlib
# from threading import get_ident
from time import time

from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.exc import DetachedInstanceError

from .repr import ReprMixin


logger = logging.getLogger('flask-vgavro-utils.sqla')


class SQLAlchemy(SQLAlchemy):
    """
    Extends driver and session with custom options.
    """
    def __init__(self, app=None, use_native_unicode=True, session_options={}, **kwargs):
        if app and 'SQLALCHEMY_AUTOCOMMIT' in app.config:
            session_options['autocommit'] = app.config['SQLALCHEMY_AUTOCOMMIT']
        super().__init__(app, use_native_unicode, session_options, **kwargs)

    def apply_driver_hacks(self, app, info, options):
        super().apply_driver_hacks(app, info, options)
        if (app and 'SQLALCHEMY_STATEMENT_TIMEOUT' in app.config and
           info.drivername in ('postgresql', 'postgresql+psycopg2')):
            timeout = int(app.config['SQLALCHEMY_STATEMENT_TIMEOUT']) * 1000
            assert 'connect_args' not in options
            options['connect_args'] = {'options': '-c statement_timeout={:d}'.format(timeout)}


class ModelReprMixin(ReprMixin):
    # See for all fields https://stackoverflow.com/a/2448930/450103
    def __repr__(self, *args, **kwargs):
        try:
            return super().__repr__(*args, **kwargs)
        except DetachedInstanceError as exc:
            return '<{} {!r}>'.format(self.__class__.__name__, exc)

    def to_dict(self, *args, **kwargs):
        fields = args or [c.name for c in self.__table__.columns]
        return super().to_dict(*fields, **kwargs)


class InstantDefaultsMixin:
    # https://github.com/kvesteri/sqlalchemy-utils/blob/master/sqlalchemy_utils/listeners.py#L24
    # instant_defaults_listener
    # TODO: maybe remove it and use from sqlalchemy_utils?
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, column in self.__table__.columns.items():
            if (
                hasattr(column, 'default') and
                column.default is not None and
                getattr(self, key, None) is None and
                key not in kwargs
            ):
                if callable(column.default.arg):
                    setattr(self, key, column.default.arg(self))
                else:
                    setattr(self, key, column.default.arg)


def db_reinit(db=None, bind=None):
    """Reinitialize database"""
    from sqlalchemy.schema import DropTable
    from sqlalchemy.ext.compiler import compiles

    @compiles(DropTable, "postgresql")
    def _compile_drop_table(element, compiler, **kwargs):
        return compiler.visit_drop_table(element) + " CASCADE"

    if not db:
        db = current_app.extensions['sqlalchemy'].db
    # NOTE: bind=None to drop_all and create_all only default database
    db.drop_all(bind=bind)
    db.create_all(bind=bind)
    db.session.commit()


class transaction(contextlib.ContextDecorator):
    def __init__(self, commit=False, rollback=False, session=None,
                 ctx_name=None, logger=None):
        assert not (commit and rollback), 'Specify commit or rollback, not both'
        self.session, self.commit, self.rollback, self.ctx_name, self.logger = \
            session, commit, rollback, ctx_name, logger

    def __call__(self, func):
        if not self.ctx_name:
            self.ctx_name = func.__name__
        return super().__call__(func)

    def __enter__(self):
        if not self.session:
            self.session = current_app.extensions['sqlalchemy'].db.session

        # TODO: add option for transaction logging in app config
        # logger_ = ((self.logger is not True and self.logger) or
        #            (current_app and current_app.logger) or logger)

        # def log(msg, *args, **kwargs):
        #     msg = '{}: transaction {} ({})'.format(self.ctx_name or '?', msg,
        #                                            self.session.bind.pool.status())
        #     logger_.debug(msg, *args, **kwargs)
        # self.log = log
        # self.log('started ident=%s', get_ident())

        self.started = time()
        self.session.flush()  # TODO: wtf? looks like we need it in userflow?

    def __exit__(self, exc_type, exc_value, exc_tb):
        # delta = time() - self.started
        if not exc_type and self.commit:
            try:
                self.session.commit()
                # self.log('commit ident=%s time=%.3f', get_ident(), delta)
            except BaseException as exc:
                self.session.close()
                # self.log('commit aborted ident=%s time=%.3f exc=%r',
                #          get_ident(), delta, exc)
                raise
        elif exc_type or self.rollback:
            self.session.rollback()
            # self.log('rollback ident=%s time=%.3f exc=%r',
            #          get_ident(), delta, exc_value)
        else:
            # NOTE: looks like close explicitly do the rollback anyway
            # self.log('close ident=%s time=%.3f', get_ident(), delta)
            self.session.close()
