from __future__ import unicode_literals

from django.db.models import Q, signals
from django.dispatch.dispatcher import receiver

from ....management import FIELD_DEFINITION_POST_SAVE_UID, perform_ddl
from ....models import ModelDefinition
from ....signals import mutable_class_prepared
from ....utils import popattr

from ..models import ManyToManyFieldDefinition


@receiver(mutable_class_prepared)
def mutable_model_prepared(signal, sender, definition):
    """
    Make sure all related model class are created and marked as dependency
    when a mutable model class is prepared
    """
    related_model_defs = ModelDefinition.objects.filter(
        Q(fielddefinitions__foreignkeydefinition__to=definition) |
        Q(fielddefinitions__manytomanyfielddefinition__to=definition)
    ).distinct()
    for model_def in related_model_defs:
        if model_def != definition:
            sender._dependencies.add((ModelDefinition, model_def.pk))
            model_def.model_class()


signals.post_save.disconnect(
    sender=ManyToManyFieldDefinition,
    dispatch_uid=FIELD_DEFINITION_POST_SAVE_UID % ManyToManyFieldDefinition._meta.module_name
)

@receiver(signals.post_save, sender=ManyToManyFieldDefinition,
          dispatch_uid='mutant.contrib.related.management.many_to_many_field_definition_post_save')
def many_to_many_field_definition_post_save(sender, instance, created, **kwargs):
    if created:
        if instance.through is None:
            # Create the intermediary table
            field = instance.get_bound_field()
            model = field.rel.through
            opts = field.rel.through._meta
            table_name = opts.db_table
            fields = tuple((field.name, field) for field in opts.fields)
            perform_ddl(model, 'create_table', table_name, fields)
    else:
        # Flush the intermediary table
        pass


@receiver(signals.pre_delete, sender=ManyToManyFieldDefinition,
          dispatch_uid='mutant.contrib.related.management.many_to_many_field_definition_pre_delete')
def many_to_many_field_definition_pre_delete(sender, instance, **kwargs):
    model_class = instance.model_def.model_class()
    field = model_class._meta.get_field(str(instance.name))
    intermediary_model_class = field.rel.through
    intermediary_table_name = intermediary_model_class._meta.db_table
    instance._state._m2m_deletion = (
        intermediary_model_class,
        intermediary_table_name
    )


@receiver(signals.post_delete, sender=ManyToManyFieldDefinition,
          dispatch_uid='mutant.contrib.related.management.many_to_many_field_definition_post_delete')
def many_to_many_field_definition_post_delete(sender, instance, **kwargs):
    model, table_name = popattr(instance._state, '_m2m_deletion')
    perform_ddl(model, 'delete_table', table_name)
