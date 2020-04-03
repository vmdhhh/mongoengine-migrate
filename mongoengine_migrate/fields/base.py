import weakref
from abc import ABCMeta
from typing import Type, Iterable, List, Tuple, Optional

import mongoengine.fields
from pymongo.collection import Collection

from mongoengine_migrate.actions.fields import AlterDiff
from mongoengine_migrate.exceptions import SchemaError, MigrationError

# Mongoengine field type mapping to appropriate FieldType class
# {mongoengine_field_name: field_type_cls}
mongoengine_fields_mapping = {}


class FieldTypeMeta(ABCMeta):
    def __new__(mcs, name, bases, attrs):
        sentinel = object()
        me_classes_attr = 'mongoengine_field_cls'
        me_classes = attrs.get(me_classes_attr, sentinel)
        if me_classes is sentinel:
            me_classes = [getattr(b, me_classes_attr)
                          for b in bases
                          if hasattr(b, me_classes_attr)]
            if me_classes:
                me_classes = me_classes[-1]

        assert isinstance(me_classes, (List, Tuple)) or me_classes is None, \
            f'{me_classes_attr} must be list with class names'

        attrs['_meta'] = weakref.proxy(mcs)

        klass = super(FieldTypeMeta, mcs).__new__(mcs, name, bases, attrs)
        if me_classes:
            mapping = {c.__name__: klass for c in me_classes}
            assert not (mapping.keys() & mongoengine_fields_mapping.keys()), \
                f'FieldType classes has duplicated mongoengine class defined in {me_classes_attr}'
            mongoengine_fields_mapping.update(mapping)

        return klass


class CommonFieldType(metaclass=FieldTypeMeta):
    """FieldType used as default for mongoengine fields which does
    not have special FieldType since this class implements behavior for
    mongoengine.fields.BaseField

    Special FieldTypes should be derived from this class
    """
    mongoengine_field_classes: Iterable[Type[mongoengine.fields.BaseField]] = None

    def __init__(self,
                 collection: Collection,
                 field_schema: dict):
        self.field_schema = field_schema
        self.collection = collection
        self.db_field = field_schema.get('db_field')
        if self.db_field is None:
            raise SchemaError(f"Missed 'db_field' key in schema of collection {collection.name}")

    @classmethod
    def schema_skel(cls) -> dict:
        """
        Return db schema skeleton dict for concrete field type
        """
        # 'type_key' should contain mongoengine field class name
        params = {'db_field', 'required', 'default', 'unique', 'unique_with', 'primary_key',
                  'choices', 'null', 'sparse', 'type_key'}
        return {f: None for f in params}

    @classmethod
    def build_schema(cls, field_obj: mongoengine.fields.BaseField) -> dict:
        """
        Return db schema from a given mongoengine field object

        As for 'type_key' item it fills mongoengine field class name
        :param field_obj: mongoengine field object
        :return: schema dict
        """
        schema_skel = cls.schema_skel()
        schema = {f: getattr(field_obj, f, val) for f, val in schema_skel.items()}
        schema['type_key'] = field_obj.__class__.__name__

        return schema

    def change_param(self, name: str, diff: AlterDiff):
        """
        Return MongoDB pipeline which makes change of given
        parameter.

        This is a facade method which calls concrete method which
        changes given parameter. Such methods should be called as
        'change_NAME' where NAME is a parameter name.
        :param name: parameter name to change
        :param diff: AlterDiff object
        :return:
        """
        method_name = f'change_{name}'
        if hasattr(self, method_name):
            return getattr(self, method_name)(diff)

    # TODO: make arguments checking and that old != new
    # TODO: consider renaming before other ones
    def change_db_field(self, diff: AlterDiff):
        """
        Change db field name for a field. Simply rename this field
        :param diff:
        :return:
        """
        self.collection.update_many(
            {diff.old: {'$exists': True}},
            {'$rename': {diff.old: diff.new}}
        )
        self.db_field = diff.new

    def change_required(self, diff: AlterDiff):
        """
        Make field required, which means to add this field to all
        documents. Reverting of this doesn't require smth to do
        :param diff:
        :return:
        """
        if diff.old is False and diff.new is True:
            default = diff.default or self.field_schema.get('default')
            if default is None:
                raise MigrationError(f'Cannot mark field {self.collection.name}.{self.db_field} '
                                     f'as required because default value is not set')
            self.collection.update_many(
                {self.db_field: {'$exists': False}},
                {'$set': {self.db_field: default}}
            )

    def change_unique(self, diff: AlterDiff):
        # TODO
        pass

    def change_unique_with(self, diff: AlterDiff):
        # TODO
        pass

    def change_primary_key(self, diff: AlterDiff):
        """
        Setting field as primary key means to set it required and unique
        :param diff:
        :return:
        """
        self.change_required(diff),
        # self.change_unique([], []) or []  # TODO

    # TODO: consider Document, EmbeddedDocument as choices
    # TODO: parameter what to do with documents where choices are not met
    def change_choices(self, diff: AlterDiff):
        """
        Set choices for a field
        :param diff:
        :return:
        """
        choices = diff.new
        if isinstance(next(iter(choices)), (list, tuple)):
            # next(iter) is useful for sets
            choices = [k for k, _ in choices]

        if diff.policy == 'error':
            wrong_count = self.collection.find({self.db_field: {'$nin': choices}}).retrieved
            if wrong_count:
                raise MigrationError(f'Cannot migrate choices for '
                                     f'{self.collection.name}.{self.db_field} because '
                                     f'{wrong_count} documents with field values not in choices')
        if diff.policy == 'replace':
            default = diff.default or self.field_schema.get('default')
            if default not in choices:
                raise MigrationError(f'Cannot set new choices for '
                                     f'{self.collection.name}.{self.db_field} because default value'
                                     f'{default} not listed in choices')
            self.collection.update_many(
                {self.db_field: {'$nin': choices}},
                {'$set': {self.db_field: default}}
            )

    def change_null(self, diff: AlterDiff):
        pass

    def change_sparse(self, diff: AlterDiff):
        pass

    def change_type_key(self, diff: AlterDiff):
        """
        Change type of field. Try to convert value
        :param diff:
        :return:
        """
        def find_field_class(class_name: str,
                             field_type: CommonFieldType) -> Type[mongoengine.fields.BaseField]:
            """
            Find mongoengine field class by its name
            Return None if not class was not found
            """
            # Search in given FieldType
            if field_type.mongoengine_field_classes is not None:
                me_field_cls = [c for c in field_type.mongoengine_field_classes
                                if c.__name__ == class_name]
                if me_field_cls:
                    return me_field_cls[-1]

            # Search in mongoengine itself
            klass = getattr(mongoengine.fields, class_name, None)
            if klass is not None:
                return klass

            # Search in documents retrieved from global registry
            from mongoengine.base import _document_registry
            for model_cls in _document_registry.values():
                for field_obj in model_cls._fields.values():
                    if field_obj.__class__.__name__ == class_name:
                        return field_obj.__class__

            # Cannot find anything. Return default
            return mongoengine.fields.BaseField

        old_fieldtype = mongoengine_fields_mapping.get(diff.old, CommonFieldType)
        new_fieldtype = mongoengine_fields_mapping.get(diff.new, CommonFieldType)

        old_field_cls = find_field_class(diff.old, old_fieldtype)
        new_field_cls = find_field_class(diff.new, new_fieldtype)
        if new_field_cls is mongoengine.fields.BaseField:
            raise MigrationError(f'Cannot migrate field type because cannot find {diff.new} class')

        new_fieldtype.convert_from(old_field_cls, new_field_cls)

    def convert_from(self,
                     from_field_cls: Type[mongoengine.fields.BaseField],
                     to_field_cls: Type[mongoengine.fields.BaseField]):
        raise NotImplementedError  # TODO: probably it's needed to place smth here
