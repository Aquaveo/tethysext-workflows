"""
********************************************************************************
* Name: image_workflow_result_view.py
* Author: nathan, htran, msouff
* Created On: Oct 7, 2020
* Copyright: (c) Aquaveo 2020
********************************************************************************
"""
import logging
from ....results import ImageWorkflowResult
from ..workflow_results_view import WorkflowResultsView


log = logging.getLogger(f'tethys.{__name__}')


class ImageWorkflowResultView(WorkflowResultsView):
    """
    Image Result View Controller
    """
    template_name = 'workflows/workflows/image_workflow_results_view.html'
    valid_result_classes = [ImageWorkflowResult]

    def get_context(self, request, session, context, workflow_id, step_id, result_id, *args,
                    **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            context (dict): The context dictionary.
            workflow_id (str): The id of the workflow.
            step_id (str): The id of the step.
            result_id (str): The id of the result.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501
        base_context = super().get_context(
            *args,
            request=request,
            session=session,
            context=context,
            workflow_id=workflow_id,
            step_id=step_id,
            result_id=result_id,
            **kwargs
        )

        # Get the result
        result = self.get_result(request=request, result_id=result_id, session=session)

        # Get options.
        options = result.options

        # Get image view gizmo
        image = result.get_image_object()
        image_view = image.get('image_uri', '')
        image_description = image.get('image_description', '')

        # Page title same as result name.
        page_title = options.get('page_title', result.name)

        base_context.update({
            'page_title': page_title,
            'no_dataset_message': options.get('no_dataset_message', 'No dataset found.'),
            'image_view_input': image_view,
            'image_view_description': image_description,
        })

        return base_context
