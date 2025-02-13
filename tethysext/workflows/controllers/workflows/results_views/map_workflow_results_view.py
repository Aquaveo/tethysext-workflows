"""
********************************************************************************
* Name: map_workflow_results_view.py
* Author: nswain
* Created On: October 15, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import logging
from django.http import JsonResponse
import json

from tethys_sdk.gizmos import SelectInput
from ....results import SpatialWorkflowResult
from ..map_workflows import MapWorkflowView
from ..workflow_results_view import WorkflowResultsView


log = logging.getLogger(f'tethys.{__name__}')


class MapWorkflowResultsView(MapWorkflowView, WorkflowResultsView):
    """
    Map Result View controller.
    """
    template_name = 'workflows/workflows/map_workflow_results_view.html'
    valid_result_classes = [SpatialWorkflowResult]
    show_legends = True

    def get_context(self, request, session, context, workflow_id, step_id, result_id, *args,
                    **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            context (dict): The context dictionary.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501
        base_context = super(MapWorkflowView, self).get_context(
            *args,
            request=request,
            session=session,
            context=context,
            workflow_id=workflow_id,
            step_id=step_id,
            **kwargs
        )

        # TODO: Look at why this approach does not work. The tab underneath the map does not show up.
        # result_workflow_context = super(WorkflowResultsView, self).get_context(
        #     request=request,
        #     session=session,
        #     context=context,
        #     workflow_id=workflow_id,
        #     step_id=step_id,
        #     result_id=result_id,
        #     *args, **kwargs
        # )
        result_workflow_context = WorkflowResultsView.get_context(
            self,
            *args,
            request=request,
            session=session,
            context=context,
            workflow_id=workflow_id,
            step_id=step_id,
            result_id=result_id,
            **kwargs
        )
        # Combine contexts
        base_context.update(result_workflow_context)

        # Add layers from geometry in data
        map_view = base_context['map_view']
        # Turn off feature selection on current layers
        self.set_feature_selection(map_view=map_view, enabled=False)

        # Get the result object for this view
        result = self.get_result(request, result_id, session)
        # Get managers
        map_manager = self.get_map_manager(
            request=request,
        )

        # Get Map View and Layer Groups
        layer_groups = base_context['layer_groups']
        # Generate MVLayers for spatial data
        results_layers = []
        legends_select_inputs = []
        legends = []
        # Build MVLayers for map
        for layer in result.layers:
            layer_type = layer.pop('type', None) or layer.get('cesium_type', None)

            if not layer_type or layer_type not in ['geojson', 'wms', 'CesiumModel', 'CesiumPrimitive']:
                log.warning('Unsupported layer type will be skipped: {}'.format(layer))
                continue

            result_layer = None
            if layer_type == 'geojson':
                result_layer = map_manager.build_geojson_layer(**layer)
            elif layer_type == 'wms':
                result_layer = map_manager.build_wms_layer(**layer)
            elif layer_type in ['CesiumModel', 'CesiumPrimitive']:
                result_layer = map_manager.build_cesium_layer(**layer)

            # build legend:
            legend = map_manager.build_legend(layer, units=result.options.get('units', ''))

            if legend:
                legend_input_options = [(color_ramp, color_ramp) for color_ramp in legend['color_list']]
                legend_attrs = {"onchange": f"MAP_VIEW.reload_legend( this, {legend['min_value']}, "
                                            f"{legend['max_value']}, '{legend['prefix']}', '{legend['color_prefix']}', "
                                            f"{legend['first_division']}, '{legend['layer_id']}' )"}

                legend_select_input = SelectInput(name=f"tethys-color-ramp-picker-{legend['legend_id']}",
                                                  options=legend_input_options,
                                                  initial=[legend['color_ramp']],
                                                  attributes=legend_attrs)

                legends_select_inputs.append(legend_select_input)
            legends.append(legend)

            if result_layer:
                results_layers.append(result_layer)

        # Build the Layer Group for Workflow Layers
        if results_layers:
            results_layer_group = map_manager.build_layer_group(
                id='workflow_results',
                display_name=result.options.get('layer_group_title', 'Results'),
                layer_control=result.options.get('layer_group_control', 'checkbox'),
                layers=results_layers
            )

            layer_groups.insert(0, results_layer_group)

        if self.map_type == "cesium_map_view":
            layers, entities, models, primitives = self.translate_layers_to_cesium(results_layers)
            map_view.layers = layers + map_view.layers
            map_view.entities = entities + map_view.entities
            map_view.models = models + map_view.models
            map_view.primitives = primitives + map_view.primitives
        else:
            map_view.layers = results_layers + map_view.layers

        base_context.update({
            'legends': list(zip(legends, legends_select_inputs)),
        })
        return base_context

    def get_plot_data(self, request, session, result_id, *args, **kwargs):
        """
        Load plot from given parameters.

        Args:
            request (HttpRequest): The request.
            session(sqlalchemy.Session): The database session.


        Returns:
            JsonResponse: title, data, and layout options for the plot.
        """
        layer_name = request.POST.get('layer_name', '')
        layer_id = request.POST.get('layer_id', layer_name)
        feature_id = request.POST.get('feature_id', '')

        result = self.get_result(request, result_id, session)

        layer = result.get_layer(layer_id)

        layer_type = layer.get('type', None)

        if not layer_type or layer_type not in ['geojson', 'wms']:
            raise TypeError('Unsupported layer type: {}'.format(layer))

        if layer_type == 'geojson':
            title, data, layout = self.get_plot_for_geojson(layer, feature_id)

        elif layer_type == 'wms':
            title, data, layout = super().get_plot_data(request, session)

        return JsonResponse({'title': title, 'data': data, 'layout': layout})

    def get_plot_for_geojson(self, layer, feature_id):
        """
        Retrieves plot for feature from given layer.

        Args:
            layer(dict): layer dictionary.
            feature_id(str): id of the feature in the layer to plot.

        Returns:
            title, data, layout: Plot dictionary.
        """
        plot = None
        try:
            # Example layer:
            # {
            #     'type': 'geojson',
            #     'geojson':
            #         {
            #             'type': 'FeatureCollection',
            #             'crs': {...},
            #             'features': [...]
            #         },
            #     'layer_name': 'detention_basin_boundaries',
            #     'layer_variable': 'detention_basin_boundaries',
            #     'layer_title': 'Detention Basins',
            #     'popup_title': 'Detention Basin',
            #     'selectable': False
            # }
            for feature in layer['geojson']['features']:
                # Example of a feature:
                # {
                #     'type': 'Feature',
                #     'geometry': {'type': 'Point', 'coordinates': [-87.87625096273638, 30.65151178301437]},
                #     'properties': {
                #         'id': 1,
                #         'plot': {
                #             'title': 'Plot 1',
                #             'data': [
                #                 {
                #                     'name': 'Foo',
                #                     'x': [2, 4, 6, 8],
                #                     'y': [10, 15, 20, 25]
                #                 },
                #                 {
                #                     'name': 'Bar',
                #                     'x': [1, 3, 5, 9],
                #                     'y': [9, 6, 12, 15]
                #                 },
                #             ],
                #         }
                #     }
                # }
                if str(feature['properties']['id']) == str(feature_id):
                    plot = feature['properties'].get('plot', None)
                    break

        except KeyError:
            log.warning('Ill formed geojson: {}'.format(layer))

        title = plot.get('title', '') if plot else None
        data = plot.get('data', []) if plot else None
        layout = plot.get('layout', {}) if plot else None

        return title, data, layout

    def update_result_layer(self, request, session, *args, **kwargs):
        """
        Update color ramp of a layer in the result. In the future, we can add more things to update here.
        """
        # Get Managers Hook
        result = self.get_result(request, kwargs['result_id'], session)
        layer_id = json.loads(request.POST.get('layer_id'))
        color_ramp = json.loads(request.POST.get('color_ramp'))
        update_layer = ''

        # Find the layer based on layer_id and update its color ramp.
        for layer in result.layers:
            if layer['layer_id'] == layer_id or layer['layer_name'] == layer_id:
                update_layer = layer
                update_layer['color_ramp_division_kwargs']['color_ramp'] = color_ramp
                break

        if update_layer:
            result.update_layer(update_layer=update_layer)

        return JsonResponse({'success': True})
