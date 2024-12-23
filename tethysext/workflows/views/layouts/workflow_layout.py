"""
********************************************************************************
* Name: workflow_layout.py
* Author: jakeymac
* Created On: September 9th, 2024
* Copyright: (c) Aquaveo 2021
********************************************************************************
"""
from tethys_layouts.views.tethys_layout import TethysLayout
from ...gizmos.workflow_tab import WorkflowTab, NewWorkflowModal, DeleteWorkflowModal
from ...models import TethysWorkflow
from ...controllers.utilities import get_style_for_status
from django.middleware.csrf import get_token

from django.http import HttpResponseNotFound, HttpResponse, JsonResponse
from django.shortcuts import redirect, reverse
from django.contrib import messages

from ...services import BaseSpatialManager, MapManagerBase

from abc import abstractmethod
import logging

log = logging.getLogger('tethys.' + __name__)


class WorkflowLayout(TethysLayout):
    """
    Workflow layout class.
    """

    http_method_names = ["get", "post", "delete"]

    def __init__(self, spatial_manager, map_manager, db_name, **kwargs):
        """
        Constructor
        """
        super(WorkflowLayout, self).__init__(**kwargs)
        self.template_name = 'workflow_layout/workflow_layout.html'
        self.spatial_manager = spatial_manager
        self.map_manager = map_manager
        self.db_name = db_name

    def get_context(self, request, context, *args, **kwargs):
        """
        Get the context for the layout.

        Args:
            request(HttpRequest): The request.
            context(dict): The context dictionary.

        Returns:
            dict: modified context dictionary.
        """
        token = get_token(request)
        Session = self.get_sessionmaker()
        session = Session() 
        workflows = self.get_workflows(request, session)

        context['workflow_tab'] = WorkflowTab(workflows)
        context['new_workflow_modal'] = NewWorkflowModal(token, workflow_types=self.get_workflow_types())
        context['delete_workflow_modal'] = DeleteWorkflowModal()
    
        return context

    def get_template(self):
        """
        Get the template for the layout.

        Returns:
            str: path to the template.
        """
        return 'workflow_layout/workflow_layout.html'
    
    def get_workflows(self, request, session):
        query = session.query(TethysWorkflow)
        
        workflows = query.order_by(TethysWorkflow.date_created.desc()).all()

        workflow_cards = []
        for workflow in workflows:
            status = workflow.get_status()
            app_namespace = self.app.root_url.replace("-", "_") # TODO: get app_namespace from app
            #app_namespace = "app_namespace"
            url_name = f'{app_namespace}:{workflow.TYPE}_workflow'
            href = reverse(url_name, kwargs={'workflow_id': workflow.id})
            status_style = get_style_for_status(status)
        
            if status == workflow.STATUS_PENDING or status == '' or status is None:
                statusdict = {
                    'title': 'Begin',
                    'style': 'primary',
                    'href': href
                }

            elif status == workflow.STATUS_WORKING:
                statusdict = {
                    'title': 'Running',
                    'style': status_style,
                    'href': href
                }

            elif status == workflow.STATUS_COMPLETE:
                statusdict = {
                    'title': 'View Results',
                    'style': status_style,
                    'href': href
                }

            elif status == workflow.STATUS_ERROR:
                statusdict = {
                    'title': 'Continue',
                    'style': 'primary',
                    'href': href
                }

            elif status == workflow.STATUS_FAILED:
                statusdict = {
                    'title': 'Failed',
                    'style': status_style,
                    'href': href  # TODO: MAKE IT POSSIBLE TO RESTART WORKFLOW?
                }

            else:
                statusdict = {
                    'title': status,
                    'style': status_style,
                    'href': href
                }

            workflow_cards.append({
                'id': str(workflow.id),
                'name': workflow.name,
                'type': workflow.DISPLAY_TYPE_SINGULAR,
                'creator': workflow.creator_name if workflow.creator_name else 'Unknown',
                'date_created': workflow.date_created,
                'status': statusdict,
                'can_delete': True
            })

        return workflow_cards

    def get_sessionmaker(self):
        if not self.app:
            raise NotImplementedError('The app attribute must be set before calling get_sessionmaker.')
        
        return self.app.get_persistent_store_database(self.db_name, as_sessionmaker=True)

    def post(self, request, *args, **kwargs):
        """
        Route POST requests to Python methods on the class.
        """
        params = request.POST
        all_workflow_types = self.get_workflow_types()

        Session = self.get_sessionmaker()
        session = Session()

        if 'new-workflow' in params:
            workflow_name = params.get('workflow-name')
            workflow_type = params.get('workflow-type')
            description = params.get('description', None)

            if not workflow_name:
                messages.error(request, 'Unable to create new workflow: no name given.')
                return redirect(request.path)

            if not workflow_type or workflow_type not in all_workflow_types:
                messages.error(request, 'Unable to create new workflow: invalid workflow type.')
                return redirect(request.path)

            try:
                workflow_model = all_workflow_types[workflow_type]
                workflow = workflow_model.new(
                    app=self.app,
                    name=workflow_name,
                    description=description,
                    creator_id = request.user.id,
                    creator_name = request.user.username,
                    geoserver_name = self.app.GEOSERVER_NAME, 
                    map_manager= self.map_manager, 
                    spatial_manager=self.spatial_manager
                )
                session.add(workflow)
                session.commit()

            except Exception:
                message = 'An unexpected error occurred while creating the new workflow.'
                log.exception(message)
                messages.error(request, message)
                return redirect(request.path)
            finally:
                session.close()
            

            messages.success(request, f'Successfully created new {all_workflow_types[workflow_type].DISPLAY_TYPE_SINGULAR}: {workflow_name}')
            return redirect(request.path)
            

        # Redirect/render the normal GET page by default with warning message.
        messages.warning(request, 'Unable to perform requested action.')
        return redirect(request.path)
    
    def delete(self, request, *args, **kwargs):
        """
        Handle DELETE requests for this tab.
        """
        session = None
        try:
            workflow_id = request.GET.get('id', '')
            log.debug(f'Workflow ID: {workflow_id}')

            Session = self.get_sessionmaker()
            session = Session()

            # Get the workflow
            workflow = session.query(TethysWorkflow).get(workflow_id)

            # Delete the workflow
            session.delete(workflow)
            session.commit()
            log.info(f'Deleted Workflow: {workflow.name}')
        except Exception:  # noqa: E722
            log.exception('An error occurred while attempting to delete a workflow.')
            return JsonResponse({'success': False, 'error': 'An unexpected error has occurred.'})
        finally:
            session and session.close()

        return JsonResponse({'success': True})

    def request_to_method(self, request):
        """
        Derive python method on this class from "method" GET or POST parameter.

        Args:
            request (HttpRequest): The request.

        Returns:
            callable: the method or None if not found.
        """
        if request.method == "POST":
            method = request.POST.get("method", "")
        elif request.method == "GET":
            method = request.GET.get("method", "")
        else:
            return None
        python_method = method.replace("-", "_")
        the_method = getattr(self, python_method, None)
        return the_method
    
    @classmethod
    @abstractmethod
    def get_workflow_types(cls, request=None, context=None):
        """
        A hook that must be used to define a the TethysWorkflows supported by this tab view. The list of available workflows in the New Workflow dialog is derived from this object.

        request (HttpRequest): The requestion, optional.
        context (dict): The context dictionary, optional.

        Returns:
            dict: mapping of TethysWorkflow.TYPE to TethysWorkflow classes (e.g. {MyWorkflow.TYPE: MyWorkflow} ).
        """
        return {}
