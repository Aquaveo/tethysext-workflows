"""
********************************************************************************
* Name: workflows.py
* Author: nswain
* Created On: November 19, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import inspect
from django.utils.text import slugify
from ..controllers.workflows.workflow_router import WorkflowRouter
from ..models import TethysWorkflow
from ..handlers import panel_step_handler

DEFAULT_HANDLER = {
    'handler': panel_step_handler,
    'type': 'bokeh'
}


def urls(url_map_maker, app, persistent_store_name, workflow_pairs, base_url_path='',
         custom_permissions_manager=None, base_template='workflows/base.html', handler=DEFAULT_HANDLER['handler'],
         handler_type=DEFAULT_HANDLER['type']):
    """
    Generate UrlMap objects for each workflow model-controller pair provided.

    ::

        {% url 'my_first_app:a_workflow_workflow', workflow_id=workflow.id %}

        OR

        reverse('my_first_app:a_workflow_workflow_step', kwargs={'workflow_id': workflow.id, 'step_id': step.id})

    Args:
        url_map_maker(UrlMap): UrlMap class bound to app root url.
        app(TethysAppBase): instance of Tethys app class.
        persistent_store_name(str): name of persistent store database setting the controllers should use to create sessions.
        workflow_pairs(2-tuple<TethysWorkflow, WorkflowRouter>): Pairs of TethysWorkflow models and TethysWorkFlow views.
        base_url_path(str): url path to prepend to all urls (e.g.: 'foo/bar').
        custom_permissions_manager(cls): Custom AppPermissionsManager class. Defaults to AppPermissionsManager.
        base_template(str): relative path to base template (e.g.: 'my_first_app/base.html'). Useful for customizing styles or overriding navigation of all views.

    Url Map Names:
        <workflow_type>_workflow <workflow_id>
        <workflow_type>_workflow_step <workflow_id> <step_id>
        <workflow_type>_workflow_step_result <workflow_id> <step_id> <result_id>

    Returns:
        tuple: UrlMap objects
    """  # noqa: F401, E501
    # Validate kwargs
    if base_url_path:
        if base_url_path.startswith('/'):
            base_url_path = base_url_path[1:]
        if base_url_path.endswith('/'):
            base_url_path = base_url_path[:-1]

    url_maps = []

    for _TethysWorkflow, _WorkflowRouter in workflow_pairs:
        if not _TethysWorkflow or not inspect.isclass(_TethysWorkflow) \
           or not issubclass(_TethysWorkflow, TethysWorkflow):
            raise ValueError('Must provide a valid TethysWorkflow model as the first item in the '
                             'workflow_pairs argument.')

        if not _WorkflowRouter or not inspect.isclass(_WorkflowRouter) \
           or not issubclass(_WorkflowRouter, WorkflowRouter):
            raise ValueError('Must provide a valid WorkflowRouter controller as the second item in the '
                             'workflow_pairs argument.')

        slugged_name = slugify(_TethysWorkflow.TYPE)
        workflow_name = '{}_workflow'.format(_TethysWorkflow.TYPE)
        workflow_step_name = '{}_workflow_step'.format(_TethysWorkflow.TYPE)
        workflow_step_result_name = '{}_workflow_step_result'.format(_TethysWorkflow.TYPE)

        # Url Patterns
        workflow_url = slugged_name + '/{workflow_id}'  # noqa: E222, E501
        workflow_step_url = slugged_name + '/{workflow_id}/step/{step_id}'  # noqa: E222, E501
        workflow_step_result_url = slugged_name + '/{workflow_id}/step/{step_id}/result/{result_id}'  # noqa: E222, E501

        workflow_url_maps = [
            url_map_maker(
                name=workflow_name,
                url='/'.join([base_url_path, workflow_url]) if base_url_path else workflow_url,
                controller=_WorkflowRouter.as_controller(
                    _app=app,
                    _persistent_store_name=persistent_store_name,
                    _TethysWorkflow=_TethysWorkflow,
                    base_template=base_template
                )
            ),
            url_map_maker(
                name=workflow_step_name,
                url='/'.join([base_url_path, workflow_step_url]) if base_url_path else workflow_step_url,
                controller=_WorkflowRouter.as_controller(
                    _app=app,
                    _persistent_store_name=persistent_store_name,
                    _TethysWorkflow=_TethysWorkflow,
                    base_template=base_template
                ),
                handler=handler,
                handler_type=handler_type,
                regex=['[0-9A-Za-z-_.]+', '[0-9A-Za-z-_.{}]+', '[0-9A-Za-z-_.]+']
            ),
            url_map_maker(
                name=workflow_step_result_name,
                url='/'.join([base_url_path, workflow_step_result_url]) if base_url_path else workflow_step_result_url,
                controller=_WorkflowRouter.as_controller(
                    _app=app,
                    _persistent_store_name=persistent_store_name,
                    base_template=base_template
                )
            )
        ]

        url_maps.extend(workflow_url_maps)

    return url_maps
