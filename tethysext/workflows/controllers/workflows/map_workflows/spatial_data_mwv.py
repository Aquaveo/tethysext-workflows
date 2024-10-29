"""
********************************************************************************
* Name: spatial_data_mwv.py
* Author: nswain
* Created On: March 5, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from .map_workflow_view import MapWorkflowView
from ....steps import SpatialDatasetStep, SpatialAttributesRWS
from ....services.workflows.decorators import workflow_step_controller


class SpatialDataMWV(MapWorkflowView):
    """
    Abstract controller for a map workflow view data assigned to each feature.
    """
    template_name = 'workflows/workflows/spatial_data_mwv.html'
    valid_step_classes = [SpatialDatasetStep, SpatialAttributesRWS]

    # Disable the properties popup so we can create a custom pop-up
    properties_popup_enabled = False

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
        if not current_step.options['geometry_source']:
            raise RuntimeError('The geometry option is required.')

        # Get geometry from option
        geometry = current_step.to_geojson()

        # Turn off feature selection
        map_view = context['map_view']
        self.set_feature_selection(map_view=map_view, enabled=False)

        # Get managers
        map_manager = self.get_map_manager(
            request=request
        )

        parent_name = None

        for parent in current_step.parents:
            if parent and 'singular_name' in parent.options:
                parent_name = parent.options['singular_name']
                break

        if parent_name:
            title = parent_name
        else:
            title = current_step.options['dataset_title']

        label_options = current_step.options['label_options'] if 'label_options' in current_step.options else None

        geometry_layer = map_manager.build_geojson_layer(
            geojson=geometry,
            layer_name='_pop_up_features',
            layer_variable='pop_up_features',
            layer_title='Pop Up Features',
            popup_title=title,
            selectable=True,
            label_options=label_options,
        )

        map_view.layers.insert(0, geometry_layer)

        

        # Save changes to map view
        context.update({
            'map_view': map_view,
            # 'enable_properties_popup': enable_readonly_properties,
            # 'enable_spatial_data_popup': not enable_readonly_properties # TODO fix these in templates
        })

        # Note: new layer created by super().process_step_options will have feature selection enabled by default
        super().process_step_options(
            request=request,
            session=session,
            context=context,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

    @workflow_step_controller(is_rest_controller=True)
    def get_popup_form(self, request, session, workflow, step, back_url, *args, **kwargs):
        """
        Handle GET requests with method get-attributes-form.
        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the workflow and step instances.
            workflow(TethysWorkflow): the workflow.
            step(Step): the step.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        pass

    @workflow_step_controller(is_rest_controller=True)
    def save_spatial_data(self, request, session, workflow, step, back_url, *args, **kwargs):
        """
        Handle GET requests with method get-attributes-form.
        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): Session bound to the workflow and step instances.
            workflow(TethysWorkflow): the workflow.
            step(Step): the step.
            args, kwargs: Additional arguments passed to the controller.

        Returns:
            HttpResponse: A Django response.
        """
        pass
