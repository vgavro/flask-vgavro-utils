class SAModelMixin(object):
    def to_dict(self, exclude=[]):
        fields = [c.name for c in self.__table__.columns]
        return dict((f, getattr(self, f)) for f in fields if f not in exclude)

    def __repr__(self):
        items = self.to_dict().items()
        items_str = ', '.join((u'{}={}'.format(k, v) for k, v in items))
        return '<{}({})>'.format(self.__class__.__name__, items_str)
