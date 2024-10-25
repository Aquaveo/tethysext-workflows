from sqlalchemy import Column, Integer, Table, ForeignKey
from .guid import GUID

from .base import WorkflowsBase

step_result_association = Table(
    'step_result_association',
    WorkflowsBase.metadata,
    Column('id', Integer, primary_key=True),
    Column('workflow_step_id', GUID, ForeignKey('workflow_steps.id')),
    Column('workflow_results_id', GUID, ForeignKey('workflow_results.id'))
)

step_parent_child_association = Table(
    'step_parent_child_association',
    WorkflowsBase.metadata,
    Column('id', Integer, primary_key=True),
    Column('child_id', GUID, ForeignKey('workflow_steps.id')),
    Column('parent_id', GUID, ForeignKey('workflow_steps.id'))
)
