import logging
from datetime import datetime
from collections import defaultdict
from functools import partial

import sqlalchemy as sa
from dateutil.parser import parse as dateutil_parse
from flask import current_app

from .exceptions import ImproperlyConfigured
from .sqla import transaction


logger = logging.getLogger('userflow.sync')


class SyncMixin:
    # date of sync time from userflow
    synced_at = sa.Column(sa.DateTime, nullable=True)
    # Is data changed and userfow need sync?
    sync_need = sa.Column(sa.Boolean(), nullable=True)


def _maybe_to_flat(data):
    rv = tuple(data)
    if rv and isinstance(rv[0], (tuple, list, set)):
        return tuple(x[0] for x in rv)
    return rv


def _maybe_flat_to_dict(data):
    return {
        f if isinstance(f, str) else f[0]: f if isinstance(f, str) else f[1]
        for f in data
    } if isinstance(data, (tuple, list, set)) else data


def _synchronizer_meth_decorator(type_):
    def decorator(func=None, name=None):
        if func:
            return decorator()(func)

        def decorator_(func):
            func._synchronizer = {
                'type': type_,
                'name': name or func.__name__
            }
            return func

        return decorator_
    return decorator


class Synchronizer:
    model = None
    id_attr = 'id'
    getters = {}  # {field name, attr name or callable(instance)
    setters = {}  # {field name, attr name or callable(instance, value)
    allow_create = False

    getter = staticmethod(_synchronizer_meth_decorator('getters'))
    setter = staticmethod(_synchronizer_meth_decorator('setters'))

    def __init__(self, model=None, id_attr=None, getters=None, setters=None, allow_create=None):
        self.model = model or self.model
        assert issubclass(self.model, SyncMixin)
        self.id_attr = id_attr or self.id_attr

        self.getters = _maybe_flat_to_dict(getters or self.getters)
        self.setters = _maybe_flat_to_dict(setters or self.setters)
        for attr in self.__dict__.values():
            if callable(attr) and hasattr(attr, '_synchronizer'):
                params = attr._synchronizer
                getattr(self, params['type'])[params['name']] = attr
        assert self.getters or self.setters

        self.allow_create = allow_create if allow_create is not None else self.allow_create

        self._register_model_events()

    def _register_model_events(self):
        register_data_events = False
        for attr in self.getters.values():
            if isinstance(attr, str):
                if attr in self.model.__table__.columns:
                    self._register_attr_events(getattr(self.model, attr))
                else:
                    register_data_events = True
        if register_data_events:
            self._register_attr_events(self.model.data)

    def _register_attr_events(self, attr):
        sa.event.listen(attr, 'modified', self.set_sync_need)
        sa.event.listen(attr, 'set', self.set_sync_need)

    def set_sync_need(self, target, value, oldvalue=None, initiator=None):
        target.sync_need = True

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
        rv = {
            str(getattr(obj, self.id_attr)): obj
            for obj in self._get_instances(map(int, ids))
        }
        if self.allow_create:
            for id in ids.difference(rv.keys()):
                rv[id] = self._create_instance(id)
        return rv

    def _get_instances(self, ids):
        return self.model.query.filter(getattr(self.model, self.id_attr).in_(ids))

    def _create_instance(self, id):
        instance = self.model(**{self.id_attr: int(id)})
        self.session.add(instance)
        return instance

    def preprocess(self, instance, data=None):
        pass

    def postprocess(self, instance, data=None):
        pass

    def set(self, instance, data, time):
        self._set_data(instance, data, time)
        instance.synced_at = time

    def _set_data(self, instance, data, time):
        for field in data:
            if field in self.setters:
                self._set_field(instance, field, data[field], time)

    def _set_field(self, instance, field, value, time):
        setter = self.setters[field]
        if callable(setter):
            setter(instance, value)
        else:
            if hasattr(instance, setter):
                setattr(instance, setter, value)
            else:
                if instance.data is None:
                    instance.data = {}
                instance.data[setter] = value

    def get(self, instance):
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

    def get_ids_for_sync(self):
        return (self.session.query(getattr(self.model, self.id_attr))
                .filter_by(sync_need=True))

    def finish(self):
        pass


def map_synchronizers(synchronizers):
    rv = {}
    for s in synchronizers:
        if isinstance(s, type):
            s = s()
        if s.name in rv:
            raise ImproperlyConfigured('Synchronizer already registered: %s' % s.name)
        rv[s.name] = s
    return rv


def synchronize(synchronizers, request, commit=True, batch_size=100, skip={}, **data):
    _sync_request = partial(sync_request, synchronizers, request)
    if commit:
        _sync_request = transaction(commit=True)(_sync_request)

    if data:
        for name in data.keys():
            if name not in synchronizers:
                raise ValueError('Unknown model: %s' % name)
        # TODO: batch_size and skip is ignored
        return _sync_request(data)

    data, counter = defaultdict(list), 0
    unfinished = []

    for name, synchronizer in synchronizers.items():
        for id in (set(_maybe_to_flat(synchronizer.get_ids_for_sync()))
                   .difference(skip.get(name, []))):
            data[name].append(id)
            counter += 1
            if counter >= batch_size:
                _sync_request(data)
                data = defaultdict(list)
                counter = 0
                [s.finish() for s in unfinished]
                unfinished = []

        if not counter:
            synchronizer.finish()
        else:
            unfinished.append(synchronizer)

    if counter:
        _sync_request(data)
        [s.finish() for s in unfinished]


def _repr_payload_data(name, data, debug):
    return '{}={}{}'.format(
        name, len(data),
        '({})'.format(tuple(data.keys())) if debug else ''
    )


def _repr_payload(synchronizers, data):
    return '{} {}'.format(
        data['time'],
        ', '.join(_repr_payload_data(name, data_, current_app.debug)
                  for name, data_ in data.items()
                  if name in synchronizers)
    )


@transaction(commit=True)
def sync_response(synchronizers, data, session=None):
    if not session:
        session = current_app.extensions['sqlalchemy'].db.session
    logger.info('Sync response %s', _repr_payload(synchronizers, data))

    rv = {'time': datetime.utcnow()}
    time = dateutil_parse(data['time'])
    for name, synchronizer in synchronizers.items():
        if name not in data:
            continue
        with session.no_autoflush:
            instance_map = synchronizer.get_instances(data[name].keys())
            rv[name] = {}
            for id, data_ in data[name].items():
                try:
                    instance = instance_map[id]
                except KeyError:
                    logger.warn('Skipped %s %s: no model to sync: %s',
                                name, id, data_)
                    continue
                synchronizer.preprocess(instance, data=_data)
                synchronizer.set(instance, data_, time)
                rv[name][id] = synchronizer.get(instance)
                synchronizer.postprocess(instance, data=_data)
                instance.sync_need = False

    logger.info('Sync response send %s', _repr_payload(synchronizers, rv))
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

    logger.info('Sync request %s', _repr_payload(synchronizers, payload))
    response = request(payload)
    logger.info('Sync request receive %s', _repr_payload(synchronizers, response))

    time = dateutil_parse(response['time'])
    for name, instance_map in data_map.items():
        synchronizer = synchronizers[name]
        for id, instance in instance_map.items():
            synchronizer.set(instance, response[name][id], time)
            synchronizer.postprocess(instance)
            instance.sync_need = False
