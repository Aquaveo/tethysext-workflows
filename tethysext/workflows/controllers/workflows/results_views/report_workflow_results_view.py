"""
********************************************************************************
* Name: report_workflow_results_view.py
* Author: nswain, htran, msouffront
* Created On: October 14, 2020
* Copyright: (c) Aquaveo 2020
********************************************************************************
"""
import logging
from ....results import ReportWorkflowResult, DatasetWorkflowResult, PlotWorkflowResult, SpatialWorkflowResult, \
    ImageWorkflowResult
from ..map_workflows.map_workflow_view import MapWorkflowView
from ..workflow_results_view import WorkflowResultsView

from tethys_sdk.gizmos import DataTableView
from tethys_sdk.gizmos import BokehView
from tethys_sdk.gizmos import PlotlyView
from collections import OrderedDict


log = logging.getLogger(f'tethys.{__name__}')


class ReportWorkflowResultsView(MapWorkflowView, WorkflowResultsView):
    """
    Report Result View controller.
    """
    template_name = 'workflows/workflows/report_workflow_results_view.html'
    valid_result_classes = [ReportWorkflowResult]

    previous_steps_selectable = True

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
        # Turn off feature selection on model layers
        map_view = context['map_view']
        self.set_feature_selection(map_view=map_view, enabled=False)

        # get tabular data if any
        tabular_data = current_step.workflow.get_tabular_data_for_previous_steps(current_step, request, session)
        has_tabular_data = len(tabular_data) > 0

        # get workflow name
        workflow_name = current_step.workflow.name
        # Generate MVLayers for spatial data
        # Get managers
        map_manager = self.get_map_manager(
            request=request
        )

        # Get DatasetWorkflowResult
        results = list()
        for result in current_step.results:
            if isinstance(result, DatasetWorkflowResult):
                for ds in result.datasets:
                    # Check if the export options is there
                    data_table = DataTableView(
                        column_names=ds['dataset'].columns,
                        rows=[list(record.values()) for record in ds['dataset'].to_dict(orient='records',
                                                                                        into=OrderedDict)],
                        searching=False,
                        paging=False,
                        info=False
                    )
                    ds.update({'data_table': data_table})
                    ds.update({'data_description': result.description})
                    results.append({'dataset': ds})
            elif isinstance(result, PlotWorkflowResult):
                renderer = result.options.get('renderer', 'plotly')
                plot_view_params = dict(plot_input=result.get_plot_object(), height='95%', width='95%')
                plot_view = BokehView(**plot_view_params) if renderer == 'bokeh' else PlotlyView(**plot_view_params)
                results.append({'plot': {'name': result.name, 'description': result.description, 'plot': plot_view}})
            elif isinstance(result, ImageWorkflowResult):
                image = result.get_image_object()
                if image['image_description']:
                    image_description = f'{result.description}: {image["image_description"]}'
                else:
                    image_description = result.description
                results.append({'image': {'name': result.name,
                                          'description': image_description,
                                          'image': image['image_uri']}})
            elif isinstance(result, SpatialWorkflowResult):
                result_map_layers = list()
                legend_info = None
                for layer in result.layers:
                    layer_type = layer.pop('type', None)
                    if not layer_type or layer_type not in ['geojson', 'wms']:
                        log.warning(f'Unsupported layer type will be skipped: {layer_type}')
                        continue

                    result_layer = None

                    if layer_type == 'geojson':
                        result_layer = map_manager.build_geojson_layer(**layer)

                    elif layer_type == 'wms':
                        result_layer = map_manager.build_wms_layer(**layer)
                    if result_layer:
                        # Get layer params
                        params = ""
                        if 'params' in result_layer.options.keys():
                            params = result_layer.options['params']
                        if params:
                            if 'TILED' in params.keys():
                                params.pop('TILED')
                            if 'TILESORIGIN' in params.keys():
                                params.pop('TILESORIGIN')

                        # Update env param
                        result_layer.options['params'] = params

                        # Build Legend
                        if legend_info is None:
                            legend_info = map_manager.build_legend(layer, units=result.options.get('units', ''))
                        if 'url' in result_layer.options.keys():
                            result_layer.options['url'] = self.geoserver_url(result_layer.options['url'])
                    result_map_layers.append(result_layer)
                # Append to final results list.
                results.append({'map': {'name': result.name, 'description': result.description,
                                        'legend': legend_info, 'map': result_map_layers}})

        # Save changes to map view and layer groups
        context.update({
            'has_tabular_data': has_tabular_data,
            'tabular_data': tabular_data,
            'report_results': results,
            'workflow_name': workflow_name,
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

    def get_context(self, request, session, context, workflow_id, step_id, result_id, *args,
                    **kwargs):
        """
        Hook to add additional content to context. Avoid removing or modifying items in context already to prevent unexpected behavior.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            context (dict): The context dictionary.
            workflow_id (int): The workflow id.
            step_id (int): The step id.
            result_id (int): The result id.

        Returns:
            dict: modified context dictionary.
        """  # noqa: E501
        base_context = MapWorkflowView.get_context(
            self,
            *args,
            request=request,
            session=session,
            context=context,
            workflow_id=workflow_id,
            step_id=step_id,
            **kwargs
        )

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

        return base_context

    @staticmethod
    def geoserver_url(link):
        """
        link: 'http://admin:geoserver@192.168.99.163:8181/geoserver/wms/'
        :return: 'http://192.168.99.163:8181/geoserver/wms/'
        """
        start_remove_index = link.find('//') + 2
        end_remove_index = link.find('@') + 1
        link = link[:start_remove_index] + link[end_remove_index:]
        return link
