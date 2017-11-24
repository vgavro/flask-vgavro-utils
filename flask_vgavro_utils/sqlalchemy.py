from flask_sqlalchemy import SQLAlchemy

from .utils import ReprMixin


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
           info.drivername == 'postgresql'):
            timeout = int(app.config['SQLALCHEMY_STATEMENT_TIMEOUT']) * 1000
            assert 'connect_args' not in options
            options['connect_args'] = {'options': '-c statement_timeout={:d}'.format(timeout)}


class ModelReprMixin(ReprMixin):
    def to_dict(self, *args, exclude=[]):
        fields = args or [c.name for c in self.__table__.columns]
        return super().to_dict(*fields, exclude=exclude)


def dbreinit(db):
    """Reinitialize database"""
    from sqlalchemy.schema import DropTable
    from sqlalchemy.ext.compiler import compiles

    @compiles(DropTable, "postgresql")
    def _compile_drop_table(element, compiler, **kwargs):
        return compiler.visit_drop_table(element) + " CASCADE"

    # NOTE: bind=None to drop_all and create_all only default database
    db.drop_all(bind=None)
    db.create_all(bind=None)
    db.session.commit()
