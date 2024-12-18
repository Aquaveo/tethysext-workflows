"""
********************************************************************************
* Name: map_workflow_view.py
* Author: nswain
* Created On: November 21, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import logging

from ....steps import SpatialInputStep, SpatialStep
from ..workflow_view import WorkflowView
from ...map_view import MapView
from ....models import Step

log = logging.getLogger(f'tethys.{__name__}')


class MapWorkflowView(MapView, WorkflowView):
    """
    Controller for a map view with workflows integration.
    """
    template_name = 'workflows/workflows/map_workflow_view.html'
    valid_step_classes = [Step]
    previous_steps_selectable = False

    def get_context(self, request, session, context, workflow_id, step_id, *args, **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.Session): the session.
            context(dict): The context dictionary.
            workflow_id(str): The id of the workflow.
            step_id(str): The id of the step.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501

        # TODO reformat this function call
        map_context = MapView.get_context(self, *args, request=request, session=session, context=context, 
                                          workflow_id=workflow_id, step_id=step_id, **kwargs)

        workflow_context = WorkflowView.get_context(
            self,
            *args,
            request=request,
            session=session,
            context=context,
            workflow_id=workflow_id,
            step_id=step_id,
            **kwargs
        )

        # Combine contexts
        map_context.update(workflow_context)

        return map_context

    @staticmethod
    def set_feature_selection(map_view, enabled=True):
        """
        Set whether features are selectable or not.
        Args:
            map_view(MapView): The MapView gizmo options object.
            enabled(bool): True to enable selection, False to disable it.
        """
        # Disable feature selection on all layers so it doesn't interfere with drawing
        for layer in map_view.layers:
            layer.feature_selection = enabled
            layer.editable = enabled

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
        # Get Map View and Layer Groups
        map_view = context['map_view']
        layer_groups = context['layer_groups']

        # Generate layers for review of previous steps
        map_view, layer_groups = self.add_layers_for_previous_steps(
            request=request,
            current_step=current_step,
            map_view=map_view,
            layer_groups=layer_groups
        )

        geocode_enabled_option = current_step.options.get('geocode_enabled', False)
        # Save changes to map view and layer groups
        context.update({
            'map_view': map_view,
            'layer_groups': layer_groups,
            'geocode_enabled': geocode_enabled_option,
        })

    def add_layers_for_previous_steps(self, request, current_step, map_view, layer_groups, selectable=None):
        """
        Create layers for previous steps that have a spatial component to them for review of the previous steps.
        Args:
            request(HttpRequest): The request.
            current_step(Step): The current step to be rendered.
            map_view(MapView): The Tethys MapView object.
            layer_groups(list<dict>): List of layer group dictionaries for new layers to add.
            selectable(bool): Layers generated for previous steps are selectable when True.

        Returns:
            MapView, list<dict>: The updated MapView and layer groups.
        """
        # Process each previous step
        previous_steps = current_step.workflow.get_previous_steps(current_step)
        workflow_layers = []
        steps_to_skip = set()
        mappable_step_types = (SpatialInputStep,)

        # Get managers
        map_manager = self.get_map_manager(
            request=request
        )

        # Check if previous steps are selectable
        if selectable is None:
            selectable = self.previous_steps_selectable

        for step in previous_steps:
            # Skip these steps
            if step in steps_to_skip or not isinstance(step, mappable_step_types):
                continue

            # Get the geometry
            geometry = None
            if not step.children:
                # Get the geometry of the step if no children exist
                if isinstance(step, SpatialStep):
                    geometry = step.to_geojson()
            else:
                for child in step.children:
                    # If step has a child, get geojson from the child,
                    # which will include the properties added by the child
                    if child is not None:
                        # Child step must be a SpatialStep
                        if not isinstance(child, SpatialStep):
                            continue

                        # Child geojson should include properties it adds to the features
                        geometry = child.to_geojson()

                        # Skip child step in the future to avoid adding it twice
                        steps_to_skip.add(child)

                    # Otherwise, get the geojson from this step directly
                    else:
                        geometry = step.to_geojson()

            if not geometry:
                log.warning('Parameter "geometry" for {} was not defined.'.format(step))
                continue

            # Build the Layer
            workflow_layer = self._build_mv_layer(step, geometry, map_manager, selectable)

            # Save for building layer group later
            workflow_layers.append(workflow_layer)

        if self.map_type == "cesium_map_view":
            layers, entities, models, primitives = self.translate_layers_to_cesium(workflow_layers)
            map_view.layers = layers + map_view.layers
            map_view.entities = entities + map_view.entities
            map_view.models = models + map_view.models
            map_view.primitives = primitives + map_view.primitives
        else:
            map_view.layers = workflow_layers + map_view.layers

        # Build the Layer Group for Workflow Layers
        if workflow_layers:
            workflow_layer_group = map_manager.build_layer_group(
                id='workflow_datasets',
                display_name='{} Datasets'.format(current_step.workflow.DISPLAY_TYPE_SINGULAR),
                layer_control='checkbox',
                layers=workflow_layers
            )

            layer_groups.insert(0, workflow_layer_group)

        return map_view, layer_groups

    def _build_mv_layer(self, step, geojson, map_manager, selectable=True):
        """
        Build an MVLayer object given a step and a GeoJSON formatted geometry.

        Args:
            step(SpatialStep): The step the geometry is associated with.
            geojson(dict): GeoJSON Python equivalent.
            map_manager(MapManagerBase): The map manager for this MapView.
            selectable(bool): Layer built is selectable when True.

        Returns:
            MVLayer: the layer object.
        """
        # Derive names from step options
        plural_name = step.options.get('plural_name')
        plural_codename = plural_name.lower().replace(' ', '_')
        singular_name = step.options.get('singular_name')
        layer_name = '{}_{}'.format(step.id, plural_codename)
        layer_variable = '{}-{}'.format(step.TYPE, plural_codename)

        workflow_layer = map_manager.build_geojson_layer(
            geojson=geojson,
            layer_name=layer_name,
            layer_variable=layer_variable,
            layer_title=plural_name,
            popup_title=singular_name,
            selectable=selectable
        )

        return workflow_layer
