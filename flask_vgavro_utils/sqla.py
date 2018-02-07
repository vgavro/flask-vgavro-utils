import logging
import contextlib
from threading import get_ident
from time import time

from flask import current_app
from flask_sqlalchemy import SQLAlchemy

from .utils import ReprMixin


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
    def to_dict(self, *args, **kwargs):
        fields = args or [c.name for c in self.__table__.columns]
        return super().to_dict(*fields, **kwargs)


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
    def __init__(self, commit=True, rollback=False, db=None, log_name=None):
        assert not (commit and rollback), 'Specify commit or rollback'
        self.db, self.commit, self.rollback, self.log_name = \
            db, commit, rollback, log_name

    def __enter__(self):
        if not self.db:
            self.db = current_app.extensions['sqlalchemy'].db
        if self.log_name:
            logger.debug('%s: transaction started ident=%s',
                         self.log_name, get_ident())
        self.started = time()
        self.db.session.flush()

    def __exit__(self, exc_type, exc_value, exc_tb):
        delta = time() - self.started
        if not exc_type and self.commit:
            try:
                self.db.session.commit()
                if self.log_name:
                    logger.debug('%s: transaction commit ident=%s time=%.3f',
                                 self.log_name, get_ident(), delta)
            except BaseException as exc:
                self.db.session.close()
                if self.log_name:
                    logger.debug('%s: transaction commit aborted ident=%s time=%.3f exc=%r',
                                 self.log_name, get_ident(), delta, exc)
                raise
        elif exc_type or self.rollback:
            self.db.session.rollback()
            if self.log_name:
                logger.debug('%s: transaction rollback ident=%s time=%.3f exc=%r',
                             self.log_name, get_ident(), delta, exc_value)
        elif self.log_name:
            logger.debug('%s: transaction close ident=%s time=%.3f',
                         self.log_name, get_ident(), delta)
        self.db.session.close()
