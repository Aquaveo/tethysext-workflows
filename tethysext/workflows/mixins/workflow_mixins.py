from ..models import TethysWorkflow, Step, Result

from tethys_apps.utilities import get_active_app
from tethys_sdk.base import TethysController
from django.shortcuts import reverse


class WorkflowMixin(TethysController):
    """
    TODO fix this doc string
    Mixin for class-based views that adds convenience methods for working with workflows.
    """
    _app = None
    _persistent_store_name = ''
    _back_url = ''

    def get_app(self):
        """
        Get the app object.
        """
        return self._app

    def get_sessionmaker(self):
        """
        Get the sessionmaker for the persistent store database.
        """
        if not self._app:
            raise NotImplementedError('get_sessionmaker method not implemented.')

        return self._app.get_persistent_store_database(self._persistent_store_name, as_sessionmaker=True)

    def dispatch(self, request, *args, **kwargs):
        """
        Intercept kwargs before calling handler method.
        """
        # Handle back_url
        self.back_url = kwargs.get('back_url', '')

        # Default to the details page
        if not self.back_url:
            self.back_url = self.default_back_url(
                *args,
                request=request,
                **kwargs
            )
        return super().dispatch(request, *args, **kwargs)
    
    def default_back_url(self, request, *args, **kwargs):
        """
        Hook for custom back url. Defaults to the details page.

        Returns:
            str: back url.
        """
        active_app = get_active_app(request)
        app_namespace = active_app.url_namespace
        back_controller = f'{app_namespace}:{active_app.index}'
        return reverse(back_controller)


class WorkflowViewMixin(WorkflowMixin):
    """
    Mixin for class-based views that adds convenience methods for working with workflows.
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
            TethysWorkflow: the workflow.
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
            Step: the workflow step
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


class ResultViewMixin(WorkflowMixin):
    """
    Mixin for class-based views that adds convenience methods for working with workflows, and results.
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
            result: the workflow result. # TODO review this
        """
        # Setup
        _Result = self.get_workflow_result_model()
        manage_session = False

        if not session:
            manage_session = True
            make_session = self.get_sessionmaker()
            session = make_session()

        try:
            result = session.query(_Result). \
                filter(_Result.id == result_id). \
                one()

        finally:
            if manage_session:
                session.close()

        return result
