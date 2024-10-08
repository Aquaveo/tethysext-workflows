from ..app_users.mixins import ResourceViewMixin
from ...models import ResourceWorkflow, Step, ResourceWorkflowResult


class WorkflowViewMixin(ResourceViewMixin):
    """
    Mixin for class-based views that adds convenience methods for working with resources and workflows.
    """
    _ResourceWorkflow = ResourceWorkflow
    _Step = Step

    def get_resource_workflow_model(self):
        return self._ResourceWorkflow
    
    def get_resource_workflow_step_model(self):
        return self._Step

    def get_workflow(self, request, workflow_id, session=None):
        """
        Get the workflow and check permissions.

        Args:
            request: Django HttpRequest.
            workflow_id: ID of the workflow.
            session: SQLAlchemy session. Optional

        Returns:
            ResourceWorkflow: the resource.
        """
        # Setup
        _ResourceWorkflow = self.get_resource_workflow_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            workflow = session.query(_ResourceWorkflow). \
                filter(_ResourceWorkflow.id == workflow_id). \
                one()

        finally:
            if manage_session:
                session.close()

        return workflow

    def get_step(self, request, step_id, session=None):
        """
        Get the step and check permissions.

        Args:
            request: Django HttpRequest.
            step_id: ID of the step to get.
            session: SQLAlchemy session.

        Returns:
            ResourceWorkflow: the resource.
        """
        _Step = self.get_resource_workflow_step_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            step = session.query(_Step). \
                filter(_Step.id == step_id). \
                one()

        finally:
            if manage_session:
                session.close()

        return step


class ResultViewMixin(ResourceViewMixin):
    """
    Mixin for class-based views that adds convenience methods for working with resources, workflows, and results.
    """
    _ResourceWorkflowResult = ResourceWorkflowResult

    def get_resource_workflow_result_model(self):
        return self._ResourceWorkflowResult

    def get_result(self, request, result_id, session=None):
        """
        Get the workflow and check permissions.

        Args:
            request: Django HttpRequest.
            result_id: ID of the workflow.
            session: SQLAlchemy session. Optional

        Returns:
            ResourceWorkflow: the resource.
        """
        # Setup
        _ResourceWorkflowResult = self.get_resource_workflow_result_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            workflow = session.query(_ResourceWorkflowResult). \
                filter(_ResourceWorkflowResult.id == result_id). \
                one()

        finally:
            if manage_session:
                session.close()

        return workflow
