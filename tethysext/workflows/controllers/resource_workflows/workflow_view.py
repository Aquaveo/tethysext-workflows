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
from ...utilities import grammatically_correct_join # TODO CHECK THIS IMPORT
from ...services.resource_workflows.decorators import workflow_step_controller
from ..resource_view import ResourceView
from .mixins import WorkflowViewMixin
from ..utilities import get_style_for_status
from ...models import Step


log = logging.getLogger('tethys.' + __name__)


class WorkflowView(ResourceView, WorkflowViewMixin):
    """
    Base class for workflow views.
    """
    view_title = ''
    view_subtitle = ''
    template_name = 'workflows/workflows/resource_workflow_view.html'
    previous_title = 'Previous'
    next_title = 'Next'
    finish_title = 'Finish'
    valid_step_classes = [Step]

    def get_context(self, request, session, resource, context, workflow_id, step_id, *args, **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior. This method is called during initialization of the view.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            resource (Resource): the resource for this request.
            context (dict): The context dictionary.
            workflow_id (str): The id of the workflow.
            step_id (str): The id of the step.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501
        workflow = self.get_workflow(request, workflow_id, session=session)
        current_step = self.get_step(request, step_id=step_id, session=session)
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
            resource=resource,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

        # Process lock options when the view is initializing
        self.process_lock_options_on_init(
            request=request,
            session=session,
            resource=resource,
            step=current_step
        )

        # Build step cards
        steps = self.build_step_cards(request, workflow)

        # Get the current app
        step_url_name = self.get_step_url_name(request, workflow)

        # Configure workflow lock display
        lock_display_options = self.build_lock_display_options(request, workflow)

        # Can user reset step
        user_has_active_role = self.user_has_active_role(request, current_step)
        workflow_locked_for_user = self.workflow_locked_for_request_user(request, workflow)
        show_reset_btn = user_has_active_role and not workflow_locked_for_user

        context.update({
            'workflow': workflow,
            'steps': steps,
            'current_step': current_step,
            'previous_step': previous_step,
            'next_step': next_step,
            'step_url_name': step_url_name,
            'nav_title': 'Replacement Resource Name: replacement workflow name',
            # 'nav_title': '{}: {}'.format(resource.name, workflow.name), # TODO fix this 
            'nav_subtitle': workflow.DISPLAY_TYPE_SINGULAR,
            'previous_title': self.previous_title,
            'next_title': self.next_title,
            'finish_title': self.finish_title,
            'lock_display_options': lock_display_options,
            'show_reset_btn': show_reset_btn
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
    def save_step_data(self, request, session, resource, workflow, step, back_url, *args, **kwargs):
        """
        Handle POST requests with input named "method" with value "save-step-data". This is called at end-of-life for the view.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the resource, workflow, and step instances.
            resource(Resource): the resource this workflow applies to.
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

        # User has active role?

        if 'reset-submit' in request.POST:
            step.workflow.reset_next_steps(step, include_current=True)
            session.commit()
            return redirect(current_url)
        
        # Hook for processing step data when the user has the active role
        response = self.process_step_data(
            request=request,
            session=session,
            step=step,
            resource=resource,
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
        workflow_locked_for_user = self.workflow_locked_for_request_user(request, workflow)

        for workflow_step in workflow.steps:
            step_status = workflow_step.get_status(workflow_step.ROOT_STATUS_KEY)
            step_in_progress = step_status != workflow_step.STATUS_PENDING and step_status is not None
            create_link = previous_status in workflow_step.COMPLETE_STATUSES \
                or previous_status is None \
                or step_in_progress

            user_has_active_role = self.user_has_active_role(request, workflow_step)
            show_lock = not user_has_active_role or workflow_locked_for_user
            step_locked = show_lock and not workflow_step.complete

            # Determine appropriate help text to show
            help_text = workflow_step.help
            active_roles = workflow_step.active_roles if workflow_step.active_roles else []

            if show_lock:
                if not workflow_step.complete:
                    # Locks take precedence over active role
                    if workflow_locked_for_user:
                        help_text = 'Editing is not allowed at this time, because the workflow is locked by another ' \
                                    'user.'
                    elif not user_has_active_role:
                        _AppUser = self.get_app_user_model()
                        user_friendly_roles = \
                            [_AppUser.ROLES.get_display_name_for(role) for role in active_roles]
                        grammatically_correct_list = grammatically_correct_join(user_friendly_roles, conjunction='or')
                        help_text = f'A user with one of the following roles needs to complete this ' \
                                    f'step: {grammatically_correct_list}.'
                else:
                    help_text = ''

            card_dict = {
                'id': workflow_step.id,
                'help': help_text,
                'name': workflow_step.name,
                'type': workflow_step.type,
                'status': step_status.lower(),
                'style': self.get_style_for_status(step_status),
                'link': create_link,
                'display_as_inactive': not user_has_active_role,
                'active_roles': active_roles,
                'show_lock': show_lock,
                'is_locked': step_locked
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
    def build_lock_display_options(request, workflow):
        """
        Build an object with the workflow lock indicator display options.
        Args:
            request(HttpRequest): The request.
            workflow(TethysWorkflow): the workflow.

        Returns:
            dict<style,message,show>: Dictionary containing the display options for the workflow lock indicator.
        """
        lock_display_options = {
            'style': 'warning',
            'message': 'The workflow is not locked.',
            'show': False
        }

        # TODO fix all of this
        # # Check for user locks on resource.
        # resource = workflow.resource
        # if resource.is_user_locked:
        #     lock_display_options['show'] = True

        #     # Workflow is locked for all users
        #     if resource.is_locked_for_all_users:
        #         lock_display_options['message'] = f'The workflow is locked for editing for all users, ' \
        #                                           f'because the {resource.DISPLAY_TYPE_SINGULAR} is locked.'

        #     # Request user has permission to override permissions
        #     elif has_permission(request, 'can_override_user_locks'):
        #         lock_display_options['message'] = f'The workflow is locked for editing for user ' \
        #                                           f'{resource.user_lock}, because the ' \
        #                                           f'{resource.DISPLAY_TYPE_SINGULAR} is locked.'

        #     # Different user possesses the user lock
        #     elif resource.is_locked_for_request_user(request):
        #         lock_display_options['message'] = f'The workflow is locked for editing by another user, ' \
        #                                           f'because the {resource.DISPLAY_TYPE_SINGULAR} is locked.'

        #     # Current user possesses the user lock
        #     else:
        #         lock_display_options['message'] = f'The workflow is locked for editing for all other users, ' \
        #                                           f'because the {resource.DISPLAY_TYPE_SINGULAR} is locked.'

        # # Check for user locks on the workflow
        # elif workflow.is_user_locked:
        #     lock_display_options['show'] = True

        #     # Workflow is locked for all users
        #     if workflow.is_locked_for_all_users:
        #         lock_display_options['message'] = 'The workflow is locked for editing for all users.'
        #         lock_display_options['style'] = 'info'

        #     # Request user has permission to override permissions
        #     elif has_permission(request, 'can_override_user_locks'):
        #         lock_display_options['message'] = f'The workflow is locked for editing for user: {workflow.user_lock}'

        #     # Different user possesses the user lock
        #     elif workflow.is_locked_for_request_user(request):
        #         lock_display_options['message'] = 'The workflow is locked for editing by another user.'

        #     # Current user possesses the user lock
        #     else:
        #         lock_display_options['message'] = 'The workflow is locked for editing for all other users.'

        return lock_display_options

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

    def workflow_locked_for_request_user(self, request, workflow):
        """
        Checks if the workflow is locked for the request user--either directly or via the resource being locked.

        Args:
            request(HttpRequest): The request.
            workflow(): the workflow.

        Returns:
            bool: True if the workflow is locked.
        """
        return False
        # TODO fix this
        # is_locked = workflow.is_locked_for_request_user(request) or \
        #     workflow.resource.is_locked_for_request_user(request)
        # return is_locked

    def user_has_active_role(self, request, step):
        """
        Checks if the request user has active role for step.

        Args:
            request(HttpRequest): The request.
            step(Step): the step.

        Returns:
            bool: True if user has active role.
        """
        pm = self.get_permissions_manager()
        active_roles = step.active_roles

        # All roles are considered "active" if no active roles are provided.
        if len(active_roles) < 1:
            return True

        # Determine if user's role is one of the active ones.
        has_active_role = False

        for role in active_roles:
            permission_name = pm.get_has_role_permission_for(role)
            has_active_role = has_permission(request, permission_name)
            if has_active_role:
                break

        return has_active_role

    def is_read_only(self, request, step):
        """
        Determine if the view should be rendered in read-only mode.

        Args:
            request(HttpRequest): The request.
            step(Step): The step.

        Returns:
            bool: True if the view should be rendered in read-only mode.
        """
        user_has_active_role = self.user_has_active_role(request, step)
        workflow_locked_for_user = self.workflow_locked_for_request_user(request, step.workflow)
        readonly = not user_has_active_role or workflow_locked_for_user
        return readonly

    def process_lock_options_on_init(self, request, session, resource, step):
        """
        Process lock options when the view initializes.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the resource, workflow, and step instances.
            resource(Resource): the resource this workflow applies to.
            step(Step): the step.
        """
        user_has_active_role = self.user_has_active_role(request, step)

        # Process lock options - only active users or permitted users can acquire user locks
        if user_has_active_role:
            # release locks before acquiring a new lock
            # release workflow lock
            if step.options.get('release_workflow_lock_on_init'):
                self.release_lock_and_log(request, session, step.workflow)

            # release resource lock
            if step.options.get('release_resource_lock_on_init'):
                self.release_lock_and_log(request, session, resource)

            # only acquire locks when the step is not completed
            if not step.complete:
                # acquire workflow lock
                if step.options.get('workflow_lock_required'):
                    self.acquire_lock_and_log(request, session, step.workflow)

                # acquire resource lock
                if step.options.get('resource_lock_required'):
                    self.acquire_lock_and_log(request, session, resource)

            # Process lock when finished after releasing other locks - will be a lock for all users
            if step.workflow.complete and step.workflow.lock_when_finished:
                self.acquire_lock_and_log(request, session, step.workflow, for_all_users=True)

    def process_lock_options_after_submission(self, request, session, resource, step):
        """
        Process lock options after the step has been submitted and processed.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the resource, workflow, and step instances.
            resource(Resource): the resource this workflow applies to.
            step(Step): the step.
        """
        # Only release locks at the end of a step if the step is complete
        if step.complete:
            # release workflow lock
            if step.options.get('release_workflow_lock_on_completion'):
                self.release_lock_and_log(request, session, step.workflow)

            # release resource lock
            if step.options.get('release_resource_lock_on_completion'):
                self.release_lock_and_log(request, session, resource)

        # Process lock when finished after releasing other locks - will be a lock for all users
        if step.workflow.complete and step.workflow.lock_when_finished:
            self.acquire_lock_and_log(request, session, step.workflow, for_all_users=True)

    @staticmethod
    def acquire_lock_and_log(request, session, lockable, for_all_users=False):
        """
        Attempt to acquire the lock on the lockable object and log the outcome.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            lockable(UserLockMixin): Object on which to acquire a lock.
            for_all_users(bool): Lock for all users when True.
        """
        #TODO delete this
        if not isinstance(lockable, UserLockMixin):
            raise ValueError('Argument "lockable" must implement UserLockMixin.')

        if not for_all_users:
            lock_acquired = lockable.acquire_user_lock(request)
        else:
            lock_acquired = lockable.acquire_user_lock()

        if not lock_acquired:
            log.warning(f'User "{request.user.username}" attempted to acquire a lock on "{lockable}", '
                        f'but was unsuccessful.')
        else:
            log.debug(f'User "{request.user.username}" successfully acquired a lock on "{lockable}".')

        session.commit()

    @staticmethod
    def release_lock_and_log(request, session, lockable):
        """
        Attempt to release the lock on the lockable object and log the outcome.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            lockable(UserLockMixin): Object to on which to release a lock.
        """
        # TODO delete this
        if not isinstance(lockable, UserLockMixin):
            raise ValueError('Argument "lockable" must implement UserLockMixin.')

        # No check for active user b/c user locks can only be released by the users who acquired them
        lock_released = lockable.release_user_lock(request)

        if not lock_released:
            log.warning(f'User "{request.user.username}" attempted to release a lock on "{lockable}", '
                        f'but was unsuccessful.')
        else:
            log.debug(f'User "{request.user.username}" successfully released a lock on "{lockable}".')

        session.commit()

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

    def on_get(self, request, session, resource, workflow_id, step_id, *args, **kwargs):
        """
        Override hook that is called at the beginning of the get request, before any other controller logic occurs.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            resource (Resource): the resource for this request.

        Returns:
            None or HttpResponse: If an HttpResponse is returned, render that instead.
        """  # noqa: E501
        workflow = self.get_workflow(request, workflow_id, session=session)
        _, real_next_step = workflow.get_next_step()
        current_step = self.get_step(request, step_id=step_id, session=session)

        if real_next_step and current_step.id != real_next_step.id:
            if current_step.get_status() not in current_step.COMPLETE_STATUSES:
                workflow_url_name = self.get_workflow_url_name(request, workflow)
                workflow_url = reverse(workflow_url_name, args=(resource.id, workflow.id))
                return redirect(workflow_url)

        previous_step, next_step = workflow.get_adjacent_steps(current_step)
        return self.on_get_step(request, session, resource, workflow, current_step, previous_step, next_step,
                                *args, **kwargs)

    def on_get_step(self, request, session, resource, workflow, current_step, previous_step, next_step,
                    *args, **kwargs):
        """
        Hook that is called at the beginning of the get request for a workflow step, before any other controller logic occurs.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): the session.
            resource(Resource): the resource for this request.
            workflow(TethysWorkflow): The current workflow.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.

        Returns:
            None or HttpResponse: If an HttpResponse is returned, render that instead.
        """  # noqa: E501

    def process_step_data(self, request, session, step, resource, current_url, previous_url, next_url):
        """
        Hook for processing user input data coming from the map view. Process form data found in request.POST and request.GET parameters and then return a redirect response to one of the given URLs. Only called if the user has an active role.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            step(Step): The step to be updated.
            resource(Resource): The resource for this request.
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
        Navigate to next or previous step without processing/saving data. Called instead of process_step_data when the user doesn't have an active role.

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
            # Workflow is locked for request user
            workflow_locked_for_user = self.workflow_locked_for_request_user(request, step.workflow)

            if workflow_locked_for_user:
                messages.warning(request, 'You man not proceed until this step is completed by the user who '
                                          'started it.')
            # Request user is not the active user
            elif not self.user_has_active_role(request, step):
                _AppUser = self.get_app_user_model()
                user_friendly_roles = [_AppUser.ROLES.get_display_name_for(role) for role in step.active_roles]
                grammatically_correct_list = grammatically_correct_join(user_friendly_roles, conjunction='or')
                messages.warning(request, f'You may not proceed until this step is completed by a user with '
                                          f'one of the following roles: {grammatically_correct_list}.')

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
    def process_step_options(self, request, session, context, resource, current_step, previous_step, next_step,
                             **kwargs):
        """
        Hook for processing step options (i.e.: modify map or context based on step options).

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            context(dict): Context object for the map view template.
            resource(Resource): the resource for this request.
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
