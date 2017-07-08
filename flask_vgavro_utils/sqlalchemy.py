from .utils import ReprMixin


class ModelReprMixin(ReprMixin):
    def to_dict(self, *args, exclude=[]):
        fields = args or [c.name for c in self.__table__.columns]
        return super().to_dict(fields, exclude=exclude)


def dbreinit(db):
    """Reinitialize database"""
    from sqlalchemy.schema import DropTable
    from sqlalchemy.ext.compiler import compiles

    @compiles(DropTable, "postgresql")
    def _compile_drop_table(element, compiler, **kwargs):
        return compiler.visit_drop_table(element) + " CASCADE"

    db.drop_all()
    db.create_all()
    db.session.commit()
