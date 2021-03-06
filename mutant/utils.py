from __future__ import unicode_literals

from contextlib import contextmanager
from copy import deepcopy
from itertools import groupby
from operator import itemgetter

from django.db.models.loading import cache as app_cache
from django.utils.datastructures import SortedDict
from django.utils.encoding import force_unicode
from django.utils.functional import lazy


# TODO: Remove when support for django 1.4 is dropped
def get_concrete_model(model):
    """
    Prior to django r17573 (django 1.4), `proxy_for_model` returned the
    actual concrete model of a proxy and there was no `concrete_model`
    property so we try to fetch the `concrete_model` from the opts
    and fallback to `proxy_for_model` if it's not defined.
    """
    return getattr(model._meta, 'concrete_model', model._meta.proxy_for_model)


NOT_PROVIDED = object()


def popattr(obj, attr, default=NOT_PROVIDED):
    """
    Useful for retrieving an object attr and removing it if it's part of it's 
    dict while allowing retrieving from subclass.
    i.e.
    class A:
        a = 'a'
    class B(A):
        b = 'b'
    >>> popattr(B, 'a', None)
    'a'
    >>> A.a
    'a'
    """
    val = getattr(obj, attr, default)
    try:
        delattr(obj, attr)
    except AttributeError:
        if default is NOT_PROVIDED:
            raise
    return val


def _string_format(string, *args, **kwargs):
    if args:
        return string % tuple(force_unicode(s) for s in args)
    elif kwargs:
        return string % dict((k, force_unicode(v)) for k, v in kwargs.iteritems())
lazy_string_format = lazy(_string_format, unicode)


def get_db_table(app_label, model):
    return "mutant_%s_%s" % (app_label, model)


if hasattr(app_cache, 'write_lock'):
    def app_cache_lock():
        return app_cache.write_lock
else:
    # django >= 1.5 use imp.lock instead
    import imp
    @contextmanager
    def app_cache_lock():
        try:
            imp.acquire_lock()
            yield
        finally:
            imp.release_lock()


def remove_from_app_cache(model_class):
    opts = model_class._meta
    app_label, model_name = opts.app_label, opts.object_name.lower()
    with app_cache_lock():
        app_models = app_cache.app_models.get(app_label, False)
        if app_models:
            model = app_models.pop(model_name, False)
            if model:
                app_cache._get_models_cache.clear()
                return model


def _app_cache_deepcopy(obj):
    """
    An helper that correctly deepcopy model cache state
    """
    if isinstance(obj, dict):
        return dict((_app_cache_deepcopy(key), _app_cache_deepcopy(val))
                    for key, val in obj.iteritems())
    elif isinstance(obj, list):
        return list(_app_cache_deepcopy(val) for val in obj)
    elif isinstance(obj, SortedDict):
        return deepcopy(obj)
    return obj


@contextmanager
def app_cache_restorer():
    """
    A context manager that restore model cache state as it was before
    entering context.
    """
    state = _app_cache_deepcopy(app_cache.__dict__)
    try:
        yield state
    finally:
        with app_cache_lock():
            app_cache.__dict__ = state


group_item_getter = itemgetter('group')
def choices_from_dict(choices):
    for grp, choices in groupby(choices, key=group_item_getter):
        if grp is None:
            for choice in choices:
                yield (choice['value'], choice['label'])
        else:
            yield (grp, tuple((choice['value'], choice['label'])
                                for choice in choices))
