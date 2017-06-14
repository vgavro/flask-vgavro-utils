from .utils import ReprMixin


class SAModelMixin(ReprMixin):
    def to_dict(self, exclude=[]):
        fields = [c.name for c in self.__table__.columns]
        return dict((f, getattr(self, f)) for f in fields if f not in exclude)


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
