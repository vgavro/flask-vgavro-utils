import logging
import contextlib
from threading import get_ident

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
    def to_dict(self, *args, exclude=[]):
        fields = args or [c.name for c in self.__table__.columns]
        return super().to_dict(*fields, exclude=exclude)


def db_reinit(db, bind=None):
    """Reinitialize database"""
    from sqlalchemy.schema import DropTable
    from sqlalchemy.ext.compiler import compiles

    @compiles(DropTable, "postgresql")
    def _compile_drop_table(element, compiler, **kwargs):
        return compiler.visit_drop_table(element) + " CASCADE"

    # NOTE: bind=None to drop_all and create_all only default database
    db.drop_all(bind=bind)
    db.create_all(bind=bind)
    db.session.commit()


class db_transaction(contextlib.ContextDecorator):
    def __init__(self, db, commit=True, rollback=False, log_name=None):
        assert not (commit and rollback)
        self.db, self.commit, self.rollback, self.log_name = \
            db, commit, rollback, log_name
        if log_name:
            logger.debug('%s: %s transaction started', log_name, get_ident())
        db.session.flush()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_tb):
        if not exc_type and self.commit:
            try:
                self.db.session.commit()
                if self.log_name:
                    logger.debug('%s: %s transaction commit',
                                 self.log_name, get_ident())
            except BaseException as exc:
                self.db.session.close()
                if self.log_name:
                    logger.debug('%s: %s transaction commit aborted: %r',
                                 self.log_name, get_ident(), exc)
                raise
        elif exc_type or self.rollback:
            self.db.session.rollback()
            if self.log_name:
                logger.debug('%s: %s transaction rollback',
                             self.log_name, get_ident())
        elif self.log_name:
            logger.debug('%s: %s transaction close',
                         self.log_name, get_ident())
        self.db.session.close()
