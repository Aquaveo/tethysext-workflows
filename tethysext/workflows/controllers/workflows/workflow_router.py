"""
********************************************************************************
* Name: workflow_router.py
* Author: nswain
* Created On: November 19, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import logging
from sqlalchemy.exc import StatementError
from sqlalchemy.orm.exc import NoResultFound
from django.shortcuts import redirect, reverse
from django.contrib import messages
from tethys_apps.utilities import get_active_app
from ...exceptions import TethysWorkflowsException
from ...mixins.workflow_mixins import WorkflowViewMixin
from ...steps import ResultsStep 


log = logging.getLogger(f'tethys.{__name__}')


class WorkflowRouter(WorkflowViewMixin):
    """
    Router for workflow views. Routes to appropriate step controller.
    """
    base_template = 'workflows/base.html'
    http_method_names = ['get', 'post', 'delete']

    def get(self, request, workflow_id, step_id=None, result_id=None, *args, **kwargs):
        """
        Route GET requests.

        Controller for the following url patterns:

        /my-custom-workflow/<workflow_id>/
        /my-custom-workflow/<workflow_id>/step/<step_id>/
        /my-custom-workflow/<workflow_id>/step/<step_id>/result/<result_id>/

        Args:
            request(HttpRequest): The request.
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render. Optional. Required if result_id given.
            result_id(str): ID of the result to render. Optional.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        step_id_given = step_id is not None
        result_id_given = result_id is not None

        _Workflow = self.get_workflow_model()
        session = None

        try:
            make_session = self.get_sessionmaker()
            session = make_session()
            workflow = self.get_workflow(request, workflow_id, session=session)

            if not step_id_given:
                _, step = workflow.get_next_step()
                # Get step id
                step_id = step.id if step else None

                if not step_id:
                    messages.warning(request, 'Could not identify next step.')
                    return redirect(self.back_url)
            else:
                step = self.get_step(request, step_id, session)

            # Determine if step is result step
            is_result_step = isinstance(step, ResultsStep)

            # Handle result steps
            if is_result_step and not result_id_given:
                result = step.get_last_result()
                result_id = str(result.id) if result else None

                if not result_id:
                    messages.warning(request, 'Could not identify a result.')
                    return redirect(self.back_url)

            # If any of the required ids were not given originally, redirect to the appropriate url with derived ids
            active_app = get_active_app(request)
            app_namespace = active_app.url_namespace
            url_kwargs = {'workflow_id': workflow_id, 'step_id': step_id}
            if is_result_step and not result_id_given:
                # Redirect to the result page
                url_name = '{}:{}_workflow_step_result'.format(app_namespace, _Workflow.TYPE)
                url_kwargs.update({'result_id': result_id})
                return redirect(reverse(url_name, kwargs=url_kwargs))

            elif not is_result_step and not step_id_given:
                # Redirect to next step page
                url_name = '{}:{}_workflow_step'.format(app_namespace, _Workflow.TYPE)
                return redirect(reverse(url_name, kwargs=url_kwargs))

        except (StatementError, NoResultFound):
            messages.warning(request, 'The {} could not be found.'.format(
                _Workflow.DISPLAY_TYPE_SINGULAR.lower()
            ))
            return redirect(self.back_url)
        except TethysWorkflowsException as e:
            error_message = str(e)
            messages.warning(request, error_message)
            return redirect(self.back_url)
        finally:
            session and session.close()

        response = self._get_response(request, workflow_id, step_id, result_id, args, kwargs)

        return response

    def post(self, request, workflow_id, step_id, result_id=None, *args, **kwargs):
        """
        Route POST requests.
        Args:
            request(HttpRequest): The request.
           
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render.
            result_id(str): ID of the result to render.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        response = self._get_response(request, workflow_id, step_id, result_id, args, kwargs)

        return response

    def delete(self, request, workflow_id, step_id, result_id=None, *args, **kwargs):
        """
        Route DELETE requests.
        Args:
            request(HttpRequest): The request.
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render.
            result_id(str): ID of the result to render.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        response = self._get_response(request, workflow_id, step_id, result_id, args, kwargs)

        return response

    def _get_response(self, request, workflow_id, step_id, result_id, args, kwargs):
        """
        Get controller from step or result that will handle the request.

        Args:
            request(HttpRequest): The request.
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render.
            result_id(str): ID of the result to render.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        if result_id:
            response = self._route_to_result_controller(
                *args,
                request=request,
                workflow_id=workflow_id,
                step_id=step_id,
                result_id=result_id,
                **kwargs
            )

        else:
            response = self._route_to_step_controller(
                *args,
                request=request,
                workflow_id=workflow_id,
                step_id=step_id,
                **kwargs
            )
        return response

    def _route_to_step_controller(self, request, workflow_id, step_id, *args, **kwargs):
        """
        Get controller from step that will handle the request.

        Args:
            request(HttpRequest): The request.
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        
       
        _Workflow = self.get_workflow_model()
        session = None

        try:
            make_session = self.get_sessionmaker()
            session = make_session()
            step = self.get_step(request, step_id, session=session)

            # Validate HTTP method
            if request.method.lower() not in step.controller.http_methods:
                raise RuntimeError('An unexpected error has occurred: Method not allowed ({}).'.format(request.method))
            
            controller = step.controller.instantiate(
                _app=self._app,
                _persistent_store_name=self._persistent_store_name,
                _TethysWorkflow=self._TethysWorkflow,
                _Step=self._Step,
                base_template=self.base_template
            )

            response = controller(
                *args,
                request=request,
                workflow_id=workflow_id,
                step_id=step_id,
                back_url=self.back_url,
                **kwargs
            )

            return response

        except (StatementError, NoResultFound):
            messages.warning(request, 'Invalid step for workflow: {}.'.format(
                _Workflow.DISPLAY_TYPE_SINGULAR.lower()
            ))
            return redirect(self.back_url)
        except TethysWorkflowsException as e:
            error_message = str(e)
            messages.warning(request, error_message)
            return redirect(self.back_url)
        finally:
            session and session.close()

    def _route_to_result_controller(self, request, workflow_id, step_id, result_id, *args, **kwargs):
        """
        Get controller from result that will handle the request.

        Args:
            request(HttpRequest): The request.
            workflow_id(str): ID of the workflow.
            step_id(str): ID of the step to render.
            result_id(str): ID of the result to render.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        _Workflow = self.get_workflow_model()
        session = None

        try:
            make_session = self.get_sessionmaker()
            session = make_session()
            step = self.get_step(request, step_id, session=session)

            # Check if step is ResultsStep
            if not isinstance(step, ResultsStep):
                raise RuntimeError('Step must be a ResultsStep.')

            # Get the result from the step
            result = step.get_result(result_id=result_id)

            # Validate HTTP method
            if not result:
                messages.error(request, 'Result not found.')
                return redirect(self.back_url)

            if request.method.lower() not in result.controller.http_methods:
                raise RuntimeError('An unexpected error has occurred: Method not allowed ({}).'.format(request.method))

            controller = result.controller.instantiate(
                _app=self._app,
                _persistent_store_name=self._persistent_store_name,
                _TethysWorkflow=self._TethysWorkflow,
                _Step=self._Step,
                base_template=self.base_template
            )

            response = controller(
                *args,
                request=request,
                workflow_id=workflow_id,
                step_id=step_id,
                result_id=result_id,
                back_url=self.back_url,
                **kwargs
            )

            return response

        except (StatementError, NoResultFound):
            messages.warning(request, 'Invalid step for workflow: {}.'.format(
                _Workflow.DISPLAY_TYPE_SINGULAR.lower()
            ))
            return redirect(self.back_url)
        except TethysWorkflowsException as e:
            error_message = str(e)
            messages.warning(request, error_message)
            return redirect(self.back_url)
        finally:
            session and session.close()
