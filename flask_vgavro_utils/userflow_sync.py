from datetime import datetime

import sqlalchemy as sa
from dateutil.parser import parse as dateutil_parse
from flask import current_app

from .exceptions import ImproperlyConfigured


class SyncMixin:
    # date of sync time from userflow
    synced_at = sa.Column(sa.DateTime, nullable=True)
    # Is data changed and userfow need sync?
    sync_need = sa.Column(sa.Boolean(), nullable=True)


def _maybe_flat_to_dict(data):
    return {f: f for f in data} if isinstance(data, (tuple, list, set)) else data


def _synchronizer_meth_decorator(type_):
    def decorator(func):
        func._synchronizer = {'type': type_, 'name': func.__name__}
        return func


class Synchronizer:
    model = None
    id_attr = 'id'
    getters = {}  # field name, field name or callable(instance)
    setters = {}  # field name, field name or callable(
    allow_create = False

    getter = staticmethod(_synchronizer_meth_decorator('getters'))
    setter = staticmethod(_synchronizer_meth_decorator('setters'))

    def __init__(self, model=None, getters=None, setters=None, allow_create=None):
        self.model = model or self.model
        assert issubclass(self.model, SyncMixin)

        self.getters = _maybe_flat_to_dict(getters or self.getters)
        self.setters = _maybe_flat_to_dict(setters or self.setters)
        for attr in self.__dict__.values():
            if callable(attr) and hasattr(attr, '_synchronizer'):
                params = attr._synchronizer
                getattr(self, params['type'])[params['name']] = attr
        assert self.getters or self.setters

        self.allow_create = allow_create if allow_create is not None else self.allow_create

    @property
    def name(self):
        return self.model.__name__.lower()

    @property
    def session(self):
        # TODO: don't use current_app, this should work without scoped session
        return current_app.extensions['sqlalchemy'].db.session

    def get_instances(self, ids):
        # Return keys as string to be json-compatible
        ids = set(map(str, ids))

        rv = {str(obj.id): obj for obj in
              self.model.query.filter(getattr(self.model, self.id_attr).in_(ids))}

        if self.allow_create:
            for id in ids.difference(rv.keys()):
                rv[id] = self.create_instance(id)

        return rv

    def create_instance(self, id):
        instance = self.model(**{self.id_attr: id})
        self.session.add(instance)
        return instance

    def preprocess(self, instance):
        pass

    def postprocess(self, instance):
        pass

    def set(self, instance, data, time):
        self._set_data(instance, data, time)
        instance.synced_at = time

    def _set_data(self, instance, data, time):
        for field in data:
            self._set_field(instance, field, data[field], time)

    def _set_field(self, instance, field, value, time):
        setter = self.setters[field]
        if callable(setter):
            setter(instance, value)
        else:
            if hasattr(instance, setter):
                setattr(instance, setter, value)
            else:
                instance.data[setter] = value

    def get(self, instance):
        instance.sync_need = False
        return self._get_data(instance)

    def _get_data(self, instance):
        return {field: self._get_field(instance, field)
                for field in self.getters}

    def _get_field(self, instance, field):
        getter = self.getters[field]
        if callable(getter):
            return getter(instance)
        else:
            if hasattr(instance, field):
                return getattr(instance, field)
            else:
                return instance.data.get(field)


def map_synchronizers(synchronizers):
    rv = {}
    for s in synchronizers:
        if isinstance(s, type):
            s = s()
        if s.name in rv:
            raise ImproperlyConfigured('Synchronizer already registered: {}'.format(s.name))
        rv[s.name] = s
    return rv


def sync_response(synchronizers, data, session=None):
    if not session:
        session = current_app.extensions['sqlalchemy'].db.session

    rv = {'time': datetime.utcnow()}
    time = dateutil_parse(data['time'])
    for name, synchronizer in synchronizers.items():
        if name not in data:
            continue
        with session.no_autoflush:
            instance_map = synchronizer.get_instances(data[name].keys())
            rv[name] = {}
            for id, data in data[name].items():
                try:
                    instance = instance_map[id]
                except KeyError:
                    # TODO: warning! No model to sync
                    continue
                synchronizer.preprocess(instance)
                synchronizer.set(instance, data, time)
                rv[name][id] = synchronizer.get(instance)
                synchronizer.postprocess(instance)
    return rv


def sync_request(synchronizers, request, data, time=None):
    payload = {'time': (time or datetime.utcnow()).isoformat()}
    data_map = {}

    for name, ids_or_instances in data.items():
        synchronizer = synchronizers[name]

        if not isinstance(ids_or_instances[0], SyncMixin):
            data_map[name] = synchronizer.get_instances(ids_or_instances)
        else:
            data_map[name] = {
                str(getattr(instance, synchronizer.id_attr)): instance
                for instance in ids_or_instances
            }

        payload[name] = {}
        for id, instance in data_map[name].items():
            synchronizer.preprocess(instance)
            payload[name][id] = synchronizer.get(instance)

    response = request(payload)

    time = dateutil_parse(response['time'])
    for name, instance_map in data_map.items():
        synchronizer = synchronizers[name]
        for id, instance in instance_map.items():
            synchronizer.set(instance, response[name][id], time)
            synchronizer.postprocess(instance)
