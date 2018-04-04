from datetime import datetime

import sqlalchemy as sa
from dateutil.parser import parse as dateutil_parse
from flask import current_app


class SyncMixin:
    # date of sync time from userflow
    synced_at = sa.Column(sa.DateTime, nullable=True)
    # Is data changed and userfow need sync?
    sync_need = sa.Column(sa.Boolean(), nullable=True)


class Synchronizer:
    model = None
    get_fields = []
    set_fields = []
    allow_create = False

    def __init__(self, model=None, get_fields=None, set_fields=None, allow_create=None):
        self.model = model or self.model
        assert issubclass(self.model, SyncMixin)
        self.get_fields = get_fields or self.get_fields
        self.set_fields = set_fields or self.set_fields   # TODO: do we need it here?
        assert self.get_fields or self.set_fields
        self.allow_create = allow_create if allow_create is not None else self.allow_create

    @property
    def session(self):
        # TODO: don't use current_app, this should work without scoped session
        return current_app.db.extensions['sqlalchemy'].db.session

    def get_instances(self, ids):
        # Return keys as string to be json-compatible
        ids = set(map(str, ids))

        rv = {str(obj.id): obj for obj in
              self.model.query.filter(self.model.id.in_(ids))}

        if self.allow_create:
            for id in ids.difference(rv.keys()):
                rv[id] = self.create_instance(id)

        return rv

    def create_instance(self, id):
        instance = self.model(id=id)
        self.session.add(instance)
        return instance

    def preprocess(self, instance):
        pass

    def postprocess(self, instance):
        pass

    def set(self, instance, data, time):
        self._set_fields(instance, data, time)
        instance.synced_at = time

    def _set_fields(self, instance, data, time):
        for field in data:
            self._set_field(self, instance, field, data[field], time)

    def _set_field(self, instance, field, value, time):
        assert field in self.set_fields
        if hasattr(instance, field):
            setattr(instance, field, value)
        else:
            instance.data[field] = value

    def get(self, instance):
        instance.sync_need = False
        return self._get_fields(instance)

    def _get_fields(self, instance):
        return {field: self._get_field(instance, field)
                for field in self.get_fields}

    def _get_field(self, instance, field):
        if hasattr(instance, field):
            return getattr(instance, field)
        else:
            return instance.data.get(field)


def map_synchronizers(synchronizers):
    rv = {}
    for synchronizer in synchronizers:
        name = synchronizer.model.__name__.lower()
        assert name not in rv, 'Synchronizer already registered: {}'.format(name)
        rv[name] = synchronizer
    return rv


def sync_response(synchronizers, data):
    time = dateutil_parse(data['time'])
    rv = {}
    for name, synchronizer in synchronizers:
        if name not in data:
            continue
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


def sync_request(synchronizers, real_request, data, time=None):
    payload = {'time': (time or datetime.utcnow()).isoformat()}
    data_map = {}

    for name, ids_or_instances in data:
        synchronizer = synchronizers[name]

        if not isinstance(ids_or_instances[0], SyncMixin):
            data_map[name] = synchronizer.get_instances(ids_or_instances)
        else:
            data_map[name] = {instance.id: instance for instance in ids_or_instances}

        payload[name] = {}
        for id, instance in data_map[name].items():
            synchronizer.preprocess(instance)
            payload[name][id] = synchronizer.get(instance)

    response = real_request(payload)

    time = dateutil_parse(response['time'])
    for name, instance_map in data_map.items():
        synchronizer = synchronizers[name]
        for id, instance in instance_map.items():
            synchronizer.set(instance, response[name][id], time)
            synchronizer.postprocess(instance)
