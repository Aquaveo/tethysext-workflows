from ..app_users.mixins import ResourceViewMixin
from ...models import TethysWorkflow, Step, Result


class WorkflowViewMixin(ResourceViewMixin):
    """
    Mixin for class-based views that adds convenience methods for working with resources and workflows.
    """
    _TethysWorkflow = TethysWorkflow
    _Step = Step

    def get_workflow_model(self):
        return self._TethysWorkflow
    
    def get_workflow_step_model(self):
        return self._Step

    def get_workflow(self, request, workflow_id, session=None):
        """
        Get the workflow and check permissions.

        Args:
            request: Django HttpRequest.
            workflow_id: ID of the workflow.
            session: SQLAlchemy session. Optional

        Returns:
            TethysWorkflow: the resource.
        """
        # Setup
        _TethysWorkflow = self.get_workflow_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            workflow = session.query(_TethysWorkflow). \
                filter(_TethysWorkflow.id == workflow_id). \
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
            TethysWorkflow: the resource.
        """
        _Step = self.get_workflow_step_model()
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
    _Result = Result

    def get_workflow_result_model(self):
        return self._Result

    def get_result(self, request, result_id, session=None):
        """
        Get the workflow and check permissions.

        Args:
            request: Django HttpRequest.
            result_id: ID of the workflow.
            session: SQLAlchemy session. Optional

        Returns:
            TethysWorkflow: the resource result. # TODO review this
        """
        # Setup
        _Result = self.get_workflow_result_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            workflow = session.query(_Result). \
                filter(_Result.id == result_id). \
                one()

        finally:
            if manage_session:
                session.close()

        return workflow
