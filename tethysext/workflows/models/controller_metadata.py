"""
********************************************************************************
* Name: controller_metadata
* Author: nswain
* Created On: April 18, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import inspect
import uuid

from sqlalchemy import Column, String, PickleType
from .guid import GUID
from .base import WorkflowsBase
from ..utilities import import_from_string

__all__ = ['ControllerMetadata']


class ControllerMetadata(WorkflowsBase):
    """
    Data model that stores controller metadata for objects associated with controllers.
    """
    __tablename__ = 'controller_metadata'

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    path = Column(String)
    kwargs = Column(PickleType, default={})
    http_methods = Column(PickleType, default=['get', 'post', 'delete'])

    def instantiate(self, **kwargs):
        """
        Instantiate an instance of the TethysController referenced by the path with the given kwargs.

        Args:
            kwargs: any kwargs that would be passed to the as_controller method of TethysControllers (i.e.: class-based view property overrides).
z
        Returns:
            function: the controller method.
        """  # noqa: E501
        from tethys_sdk.base import TethysController
        from ..mixins.workflow_mixins import WorkflowMixin
        from ..controllers.workflows.workflow_view import WorkflowView

        try:
            controller = import_from_string(self.path)

        except (ValueError, AttributeError, ImportError) as e:
            raise ImportError(f'Unable to import controller "{self.path}": {e}')

        # Get entry point for class based views
        if inspect.isclass(controller) and issubclass(controller, TethysController):
            # Call with all kwargs if is instance of an WorkflowView
            if issubclass(controller, WorkflowView):
                kwargs.update(self.kwargs)
                controller = controller.as_controller(**kwargs)

            # Call with all but workflow kwargs if TethysWorkflowLayout
            elif issubclass(controller, WorkflowMixin):
                kwargs.pop('_Workflow', None)
                kwargs.pop('_Step', None)
                kwargs.update(self.kwargs)
                controller = controller.as_controller(**kwargs)

            # Otherwise, don't call with any kwargs
            else:
                kwargs.update(self.kwargs)
                controller = controller.as_controller(**kwargs)

        return controller
