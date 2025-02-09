"""
********************************************************************************
* Name: set_status_wv.py
* Author: nswain
* Created On: August 19, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import logging

from ..workflow_view import WorkflowView
from ....steps import SetStatusStep
log = logging.getLogger(f'tethys.{__name__}')


class SetStatusWV(WorkflowView):
    """
    Controller for SetStatusStep.
    """
    template_name = 'workflows/workflows/set_status_wv.html'
    valid_step_classes = [SetStatusStep]
    default_status_label = 'Status'

    def process_step_options(self, request, session, context, current_step, previous_step, next_step):
        """
        Hook for processing step options (i.e.: modify map or context based on step options).

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            context(dict): Context object for the map view template.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.
        """
        # Validate the statuses option
        current_step.validate_statuses()

        # Status style
        status = current_step.get_status()
        status_style = self.get_style_for_status(status)
        status_label = current_step.options.get('status_label', self.default_status_label) or self.default_status_label
        form_title = current_step.options.get('form_title', current_step.name) or current_step.name

        # Save changes to map view and layer groups
        context.update({
            # 'read_only': self.is_read_only(request, current_step), # TODO remove this from templates
            'form_title': form_title,
            'status_label': status_label,
            'statuses': current_step.options.get('statuses', []),
            'comments': current_step.get_parameter('comments'),
            'status': status,
            'status_style': status_style
        })

    def process_step_data(self, request, session, step, current_url, previous_url, next_url):
        """
        Hook for processing user input data coming from the map view. Process form data found in request.POST and request.GET parameters and then return a redirect response to one of the given URLs.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            step(Step): The step to be updated.
            current_url(str): URL to step.
            previous_url(str): URL to the previous step.
            next_url(str): URL to the next step.

        Returns:
            HttpResponse: A Django response.

        Raises:
            ValueError: exceptions that occur due to user error, provide helpful message to help user solve issue.
            RuntimeError: exceptions that require developer attention.
        """  # noqa: E501
        status = request.POST.get('status', None)
        comments = request.POST.get('comments', '')
        status_label = step.options.get('status_label', self.default_status_label) or self.default_status_label

        if not status:
            raise ValueError(f'The "{status_label}" field is required.')

        if status not in step.valid_statuses():
            raise RuntimeError(f'Invalid status given: "{status}".')

        # Save parameters
        step.set_parameter('comments', comments)
        session.commit()

        # Validate the parameters
        step.validate()

        # Set the status
        step.set_status(status=status)
        step.set_attribute(step.ATTR_STATUS_MESSAGE, None)
        session.commit()

        response = super().process_step_data(
            request=request,
            session=session,
            step=step,
            current_url=current_url,
            previous_url=previous_url,
            next_url=next_url
        )

        return response
