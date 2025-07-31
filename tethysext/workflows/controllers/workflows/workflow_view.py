"""
********************************************************************************
* Name: workflow_view.py
* Author: nswain
* Created On: November 21, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import abc
import logging
from django.shortcuts import redirect, reverse
from django.contrib import messages
from tethys_apps.utilities import get_active_app
from tethys_sdk.permissions import has_permission
from ...services.workflows.decorators import workflow_step_controller
from ...mixins.workflow_mixins import WorkflowViewMixin
from ..tethys_workflow_layout import TethysWorkflowLayout
from ..utilities import get_style_for_status
from ...models import Step


log = logging.getLogger('tethys.' + __name__)


class WorkflowView(TethysWorkflowLayout, WorkflowViewMixin):
    """
    Base class for workflow views.
    """
    view_title = ''
    view_subtitle = ''
    template_name = 'workflows/workflows/workflow_view.html'
    previous_title = 'Previous'
    next_title = 'Next'
    finish_title = 'Finish'
    valid_step_classes = [Step]

    def get_context(self, request, session, context, workflow_id, step_id, *args, **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior. This method is called during initialization of the view.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            context (dict): The context dictionary.
            workflow_id (str): The id of the workflow.
            step_id (str): The id of the step.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501
        workflow = self.get_workflow(request, workflow_id, session=session)
        current_step = self.get_step(request, step_id=step_id, session=session)
        current_step_info_text = current_step.options.get('info_text', None)
        previous_step, next_step = workflow.get_adjacent_steps(current_step)

        # Hook for validating the current step
        self.validate_step(
            request=request,
            session=session,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

        # Handle any status message from previous requests
        status_message = current_step.get_attribute(current_step.ATTR_STATUS_MESSAGE)
        if status_message:
            step_status = current_step.get_status()
            if step_status in (current_step.STATUS_ERROR, current_step.STATUS_FAILED):
                messages.error(request, status_message)
            elif step_status in (current_step.STATUS_COMPLETE,):
                messages.success(request, status_message)
            else:
                messages.info(request, status_message)

        # Hook for handling step options
        self.process_step_options(
            request=request,
            session=session,
            context=context,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

        # Build step cards
        steps = self.build_step_cards(request, workflow)

        # Get the current app
        step_url_name = self.get_step_url_name(request, workflow)

        context.update({
            'workflow': workflow,
            'steps': steps,
            'current_step': current_step,
            'previous_step': previous_step,
            'next_step': next_step,
            'step_url_name': step_url_name,
            'nav_title': workflow.name,
            'description': workflow.description,
            'nav_subtitle': workflow.DISPLAY_TYPE_SINGULAR,
            'previous_title': self.previous_title,
            'next_title': self.next_title,
            'finish_title': self.finish_title,
            'workflow_info_text': current_step_info_text,
        })

        # Hook for extending the context
        additional_context = self.get_step_specific_context(
            request=request,
            session=session,
            context=context,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

        context.update(additional_context)

        return context

    @workflow_step_controller()
    def save_step_data(self, request, session, workflow, step, back_url, *args, **kwargs):
        """
        Handle POST requests with input named "method" with value "save-step-data". This is called at end-of-life for the view.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the workflow and step instances.
            workflow(TethysWorkflow): the workflow.
            step(Step): the step.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """  # noqa: E501
        previous_step, next_step = workflow.get_adjacent_steps(step)

        # Create for previous, next, and current steps
        previous_url = None
        step_url_name = self.get_step_url_name(request, workflow)
        current_url = reverse(step_url_name, args=(workflow.id, str(step.id)))

        if next_step:
            next_url = reverse(step_url_name, args=(workflow.id, str(next_step.id)))
        else:
            # Return to back_url if there is no next step
            next_url = back_url

        if previous_step:
            previous_url = reverse(step_url_name, args=(workflow.id, str(previous_step.id)))

        if 'reset-submit' in request.POST:
            step.workflow.reset_next_steps(step, include_current=True)
            session.commit()
            return redirect(current_url)
        
        # Process the step data
        response = self.process_step_data(
            request=request,
            session=session,
            step=step,
            current_url=current_url,
            previous_url=previous_url,
            next_url=next_url
        )

        return response

    def build_step_cards(self, request, workflow):
        """
        Build cards used by template to render the list of steps for the workflow.

        Args:
            request (HttpRequest): The request.
            workflow(TethysWorkflow): the workflow with the steps to render.

        Returns:
            list<dict>: one dictionary for each step in the workflow.
        """
        previous_status = None
        steps = []

        for workflow_step in workflow.steps:
            step_status = workflow_step.get_status(workflow_step.ROOT_STATUS_KEY)
            step_in_progress = step_status != workflow_step.STATUS_PENDING and step_status is not None
            create_link = previous_status in workflow_step.COMPLETE_STATUSES \
                or previous_status is None \
                or step_in_progress

            # Determine appropriate help text to show
            help_text = workflow_step.help

            card_dict = {
                'id': workflow_step.id,
                'help': help_text,
                'name': workflow_step.name,
                'type': workflow_step.type,
                'status': step_status.lower(),
                'style': self.get_style_for_status(step_status),
                'link': create_link,
            }

            # Hook to allow subclasses to extend the step card attributes
            extended_card_options = self.extend_step_cards(
                workflow_step=workflow_step,
                step_status=step_status
            )

            card_dict.update(extended_card_options)
            steps.append(card_dict)

            previous_status = step_status
        return steps

    @staticmethod
    def get_step_url_name(request, workflow):
        """
        Derive url map name for the given workflow step views.
        Args:
            request(HttpRequest): The request.
            workflow(TethysWorkflow): The current workflow.

        Returns:
            str: name of the url pattern for the given workflow step views.
        """
        active_app = get_active_app(request)
        url_map_name = '{}:{}_workflow_step'.format(active_app.url_namespace, workflow.type)
        return url_map_name

    @staticmethod
    def get_workflow_url_name(request, workflow):
        """
        Derive url map name for the given workflow view.
        Args:
            request(HttpRequest): The request.
            workflow(TethysWorkflow): The current workflow.

        Returns:
            str: name of the url pattern for the given workflow views.
        """
        active_app = get_active_app(request)
        url_map_name = '{}:{}_workflow'.format(active_app.url_namespace, workflow.type)
        return url_map_name

    @staticmethod
    def get_style_for_status(status):
        """
        Return appropriate style for given status.

        Args:
            status(str): One of StatusMixin statuses.

        Returns:
            str: style for the given status.
        """
        return get_style_for_status(status)


    def validate_step(self, request, session, current_step, previous_step, next_step):
        """
        Validate the step being used for this view. Raises TypeError if current_step is invalid.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.

        Raises:
            TypeError: if step is invalid.
        """
        # Initialize drawing tools for spatial input parameter types.
        if not any([isinstance(current_step, valid_class) for valid_class in self.valid_step_classes]):
            raise TypeError('Invalid step type for view: "{}". Must be one of "{}".'.format(
                type(current_step).__name__,
                '", "'.join([valid_class.__name__ for valid_class in self.valid_step_classes])
            ))

    def on_get(self, request, session, workflow_id, step_id, *args, **kwargs):
        """
        Override hook that is called at the beginning of the get request, before any other controller logic occurs.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.

        Returns:
            None or HttpResponse: If an HttpResponse is returned, render that instead.
        """  # noqa: E501
        workflow = self.get_workflow(request, workflow_id, session=session)
        _, real_next_step = workflow.get_next_step()
        current_step = self.get_step(request, step_id=step_id, session=session)

        if real_next_step and current_step.id != real_next_step.id:
            if current_step.get_status() not in current_step.COMPLETE_STATUSES:
                workflow_url_name = self.get_workflow_url_name(request, workflow)
                workflow_url = reverse(workflow_url_name, args=(workflow.id))
                return redirect(workflow_url)

        previous_step, next_step = workflow.get_adjacent_steps(current_step)
        return self.on_get_step(request, session, workflow, current_step, previous_step, next_step,
                                *args, **kwargs)

    def on_get_step(self, request, session, workflow, current_step, previous_step, next_step,
                    *args, **kwargs):
        """
        Hook that is called at the beginning of the get request for a workflow step, before any other controller logic occurs.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): the session.
            workflow(TethysWorkflow): The current workflow.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.

        Returns:
            None or HttpResponse: If an HttpResponse is returned, render that instead.
        """  # noqa: E501

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
        if step.dirty:
            step.workflow.reset_next_steps(step)
            step.dirty = False
            session.commit()

        return self.next_or_previous_redirect(request, next_url, previous_url)

    def navigate_only(self, request, step, current_url, next_url, previous_url):
        """
        Navigate to next or previous step without processing/saving data. Called instead of process_step_data when the user doesn't have an active role. (THIS COMES FROM ATCORE)

        Args:
            request(HttpRequest): The request.
            step(Step): The step to be updated.
            current_url(str): URL to step.
            previous_url(str): URL to the previous step.
            next_url(str): URL to the next step.

        Returns:
            HttpResponse: A Django response.
        """  # noqa: E501
        if not step.complete and 'next-submit' in request.POST:
            response = redirect(current_url)
        else:
            response = self.next_or_previous_redirect(request, next_url, previous_url)

        return response

    def next_or_previous_redirect(self, request, next_url, previous_url):
        """
        Generate a redirect to either the next or previous step, depending on what button was pressed.

        Args:
            request(HttpRequest): The request.
            previous_url(str): URL to the previous step.
            next_url(str): URL to the next step.

        Returns:
            HttpResponse: A Django response.
        """
        if 'next-submit' in request.POST:
            response = redirect(next_url)
        else:
            response = redirect(previous_url)
        return response

    @abc.abstractmethod
    def process_step_options(self, request, session, context, current_step, previous_step, next_step,
                             **kwargs):
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

    def extend_step_cards(self, workflow_step, step_status):
        """
        Hook for extending step card attributes.

        Args:
            workflow_step(Step): The current step for which a card is being created.
            step_status(str): Status of the workflow_step.

        Returns:
            dict: dictionary containing key-value attributes to add to the step card.
        """
        return {}

    def get_step_specific_context(self, request, session, context, current_step, previous_step, next_step):
        """
        Hook for extending the view context.

        Args:
           request(HttpRequest): The request.
           session(sqlalchemy.orm.Session): Session bound to the steps.
           context(dict): Context object for the map view template.
           current_step(Step): The current step to be rendered.
           previous_step(Step): The previous step.
           next_step(Step): The next step.

        Returns:
            dict: key-value pairs to add to context.
        """
        return {}
        
