class LazyConfigValue(object):
    """
    This class may be used to lazy resolve config after importing local overrides.
    For example:
    REDIS_URL = "redis://localhost:6379/0"
    CELERY_BROKER_URL = LazyConfigValue(lambda conf: conf['REDIS_URL'])

    After running LazyConfigValue.resolve_config(app.config)
    CELERY_BROKER_URL will be resolved to REDIS_URL, even if REDIS_URL were redefined later.
    """
    _counter = 0

    def __init__(self, callback):
        self.callback = callback
        self.__class__._counter += 1

    def resolve(self, config):
        return self.callback(config)

    @classmethod
    def resolve_config(cls, config):
        for k in sorted([k for k in config if isinstance(config[k], cls)],
                        key=lambda k: config[k]._counter):
            config[k] = config[k].resolve(config)


def update_context_from_import(context, module, warn_on_not_found=False):
    # For using with settings_local

    try:
        module_context = __import__(module).__dict__
    except ImportError as e:
        if e.args[0] and e.args[0].startswith('No module named') and module in e.args[0]:
            if warn_on_not_found:
                print('[WARNING] {} not found!'.format(module))
            module_context = {}
        else:
            raise

    context.update({k: v for k, v in module_context.items() if not k.startswith('__')})
