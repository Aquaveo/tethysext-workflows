import uuid
from sqlalchemy import Table, Column, ForeignKey
from ...models import WorkflowsBase, GUID 

resource_file_collection_association = Table(
    'resource_file_collections_association',
    WorkflowsBase.metadata,
    Column('id', GUID, primary_key=True, default=uuid.uuid4),
    Column('resource_id', GUID, ForeignKey('app_users_resources.id')),
    Column('file_collection_id', GUID, ForeignKey('file_collections.id'))
)
