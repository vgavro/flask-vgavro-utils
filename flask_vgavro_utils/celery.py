def create_celery(app, task_views=False):
    from celery import Celery

    celery = Celery(app.import_name, backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)

    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask

    if task_views is True:
        task_views = '/task/<task_id>'
    assert '<task_id>' in task_views
    if task_views:
        register_task_views(app, task_views)

    celery.task_url = task_views
    app.extensions['celery'] = celery
    return celery


def register_task_views(app, rule='/task/<task_id>'):
    celery = app.extensions['celery']

    @app.route(rule, methods=['GET'])
    def get_task(task_id):
        task = celery.AsyncResult(task_id)
        if task.ready():
            return task.get()  # raises Exception if error was occured
        return task  # should be processed Response.force_type for 202

    @app.route(rule, methods=['DELETE'])
    def delete_task(task_id):
        task = celery.AsyncResult(task_id)
        task.cancel()
