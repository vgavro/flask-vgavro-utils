from .utils import ReprMixin


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
