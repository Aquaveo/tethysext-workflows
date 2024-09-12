from sqlalchemy import Column, Integer, Table, ForeignKey
from .guid import GUID

from .base import WorkflowsBase

step_result_association = Table(
    'step_result_association',
    WorkflowsBase.metadata,
    Column('id', Integer, primary_key=True),
    Column('resource_workflow_step_id', GUID, ForeignKey('resource_workflow_steps.id')),
    Column('resource_workflow_result_id', GUID, ForeignKey('resource_workflow_results.id'))
)

step_parent_child_association = Table(
    'step_parent_child_association',
    WorkflowsBase.metadata,
    Column('id', Integer, primary_key=True),
    Column('child_id', GUID, ForeignKey('resource_workflow_steps.id')),
    Column('parent_id', GUID, ForeignKey('resource_workflow_steps.id'))
)
