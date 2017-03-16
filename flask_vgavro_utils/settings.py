class LazySetting(object):
    _counter = 0

    def __init__(self, callback):
        self.callback = callback
        self.__class__._counter += 1

    def resolve(self):
        return self.callback()

    @classmethod
    def resolve_context(cls, context):
        for k in sorted([k for k in context if isinstance(context[k], cls)],
                        key=lambda k: context[k]._counter):
            context[k] = context[k].resolve()


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
