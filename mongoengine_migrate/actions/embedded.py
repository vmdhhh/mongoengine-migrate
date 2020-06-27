from mongoengine_migrate.flags import EMBEDDED_DOCUMENT_NAME_PREFIX
from mongoengine_migrate.schema import Schema
from .base import BaseCreateDocument, BaseDropDocument, BaseRenameDocument


class CreateEmbedded(BaseCreateDocument):
    """
    Create new embedded document
    Should have the highest priority and be at top of every migration
    since fields actions could refer to this document and its schema
    representation.
    """
    priority = 4

    @classmethod
    def build_object(cls, document_type: str, left_schema: Schema, right_schema: Schema):
        if not document_type.startswith(EMBEDDED_DOCUMENT_NAME_PREFIX):
            # This is not an embedded document
            return None

        return super(CreateEmbedded, cls).build_object(document_type, left_schema, right_schema)

    def run_forward(self):
        """Embedded documents are not required to do anything"""

    def run_backward(self):
        """Embedded documents are not required to do anything"""


class DropEmbedded(BaseDropDocument):
    """
    Drop embedded document
    Should have the lowest priority and be at bottom of every migration
    since fields actions could refer to this document and its schema
    representation.
    """
    priority = 18

    @classmethod
    def build_object(cls, document_type: str, left_schema: Schema, right_schema: Schema):
        if not document_type.startswith(EMBEDDED_DOCUMENT_NAME_PREFIX):
            # This is not an embedded document
            return None

        return super(DropEmbedded, cls).build_object(document_type, left_schema, right_schema)

    def run_forward(self):
        """Embedded documents are not required to do anything"""

    def run_backward(self):
        """Embedded documents are not required to do anything"""


class RenameEmbedded(BaseRenameDocument):
    """
    Rename embedded document
    Should be checked before CreateEmbedded in order to detect renaming
    """
    priority = 2

    @classmethod
    def build_object(cls, document_type: str, left_schema: Schema, right_schema: Schema):
        if not document_type.startswith(EMBEDDED_DOCUMENT_NAME_PREFIX):
            # This is not an embedded document
            return None

        return super(RenameEmbedded, cls).build_object(document_type, left_schema, right_schema)

    def run_forward(self):
        """Embedded documents are not required to do anything"""

    def run_backward(self):
        """Embedded documents are not required to do anything"""
