"""
********************************************************************************
* Name: report_workflow_results_view.py
* Author: nswain, htran, msouffront
* Created On: October 14, 2020
* Copyright: (c) Aquaveo 2020
********************************************************************************
"""
import logging
import os
import tempfile
import base64
import urllib.parse
import json
from io import BytesIO
from zipfile import ZipFile
from django.http import HttpResponse
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
        dataset_zip_files = []
        for result in current_step.results:
            if isinstance(result, DatasetWorkflowResult):
                for ds in result.datasets:
                    # Check if the export options is there
                    if 'show_in_report' in ds and not ds['show_in_report']:
                        continue
                    data_table = DataTableView(
                        column_names=ds['dataset'].columns,
                        rows=[list(record.values()) for record in ds['dataset'].to_dict(orient='records',
                                                                                        into=OrderedDict)],
                        searching=False,
                        paging=False,
                        info=False
                    )
                    ds.update({'data_table': data_table})
                    description = ds['description'] if 'description' in ds and ds['description'] else result.description
                    ds.update({'data_description': description})

                    # Create a zip file for the dataset
                    zip_file_path = None
                    try:
                        # Create a temporary CSV file
                        csv_file_handle, csv_file_path = tempfile.mkstemp(suffix='.csv')
                        os.close(csv_file_handle)

                        # Write the dataframe to CSV
                        ds['dataset'].to_csv(csv_file_path, index=False)

                        # Create a zip file
                        zip_file_handle, zip_file_path = tempfile.mkstemp(suffix='.zip')
                        os.close(zip_file_handle)

                        with ZipFile(zip_file_path, 'w') as zip_file:
                            # Add CSV to zip with a clean filename
                            dataset_name = ds.get('title', 'dataset').replace(' ', '_')
                            zip_file.write(csv_file_path, f"{dataset_name}.csv")

                        # Clean up the CSV file
                        if os.path.exists(csv_file_path):
                            os.remove(csv_file_path)

                        # Add zip file path to dataset
                        ds.update({'zip_file_path': zip_file_path})

                        # Add to zip files list for context
                        dataset_zip_files.append({
                            'title': ds.get('title', 'dataset'),
                            'path': zip_file_path,
                            'filename': f"{dataset_name}.zip"
                        })

                    except Exception as e:
                        log.error(f"Error creating zip file for dataset: {e}")
                        # Clean up on error
                        if zip_file_path and os.path.exists(zip_file_path):
                            os.remove(zip_file_path)
                        if 'csv_file_path' in locals() and os.path.exists(csv_file_path):
                            os.remove(csv_file_path)

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

        # Check if download data button should be shown (check ReportWorkflowResult options)
        show_download_button = False
        for result in current_step.results:
            if isinstance(result, ReportWorkflowResult):
                # Get the option from the ReportWorkflowResult (defaults to True if not specified)
                option_value = result.options.get('show_download_button', True)
                # Show button if option is True and there are any downloadable results
                has_downloadable_results = any(
                    isinstance(r, (DatasetWorkflowResult, PlotWorkflowResult,
                                   ImageWorkflowResult, SpatialWorkflowResult))
                    for r in current_step.results
                )
                show_download_button = True if option_value and has_downloadable_results else False
                break  # Use the first ReportWorkflowResult's setting

        # Save changes to map view and layer groups
        context.update({
            'has_tabular_data': has_tabular_data,
            'tabular_data': tabular_data,
            'report_results': results,
            'workflow_name': workflow_name,
            'dataset_zip_files': dataset_zip_files,
            'show_download_button': show_download_button,
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

    def download_datasets(self, request, session, workflow_id, step_id, result_id, *args, **kwargs):
        """
        Download all dataset zip files and plot images as a single combined zip file.

        Args:
            request (HttpRequest): The request.
            session (sqlalchemy.Session): the session.
            workflow_id (int): The workflow id.
            step_id (int): The step id.
            result_id (int): The result id.

        Returns:
            HttpResponse: Zip file download response.
        """
        current_step = self.get_step(request, step_id, session)
        workflow_name = current_step.workflow.name

        # Create a combined zip file in memory
        in_memory = BytesIO()

        with ZipFile(in_memory, 'w') as combined_zip:
            for result in current_step.results:
                if isinstance(result, DatasetWorkflowResult):
                    for ds in result.datasets:
                        # Check if the export options is there
                        if 'show_in_report' in ds and not ds['show_in_report']:
                            continue

                        try:
                            # Create a temporary CSV file
                            csv_file_handle, csv_file_path = tempfile.mkstemp(suffix='.csv')
                            os.close(csv_file_handle)

                            # Write the dataframe to CSV
                            ds['dataset'].to_csv(csv_file_path, index=False)

                            # Add CSV to combined zip with a clean filename
                            dataset_name = ds.get('title', 'dataset').replace(' ', '_')
                            combined_zip.write(csv_file_path, f"{dataset_name}.csv")

                            # Clean up the CSV file
                            if os.path.exists(csv_file_path):
                                os.remove(csv_file_path)

                        except Exception as e:
                            log.error(f"Error adding dataset to zip: {e}")
                            # Clean up on error
                            if 'csv_file_path' in locals() and os.path.exists(csv_file_path):
                                os.remove(csv_file_path)

                elif isinstance(result, PlotWorkflowResult):
                    try:
                        renderer = result.options.get('renderer', 'plotly')
                        plot_object = result.get_plot_object()
                        plot_name = result.name.replace(' ', '_')

                        if renderer == 'plotly':
                            # Export plotly plot as HTML (static image export requires kaleido)
                            import plotly
                            html_file_handle, html_file_path = tempfile.mkstemp(suffix='.html')
                            os.close(html_file_handle)

                            plotly.offline.plot(plot_object, filename=html_file_path, auto_open=False)
                            combined_zip.write(html_file_path, f"{plot_name}.html")

                            # Clean up
                            if os.path.exists(html_file_path):
                                os.remove(html_file_path)

                        elif renderer == 'bokeh':
                            # Export bokeh plot as HTML
                            from bokeh.embed import file_html
                            from bokeh.resources import CDN

                            html_content = file_html(plot_object, CDN, plot_name)
                            html_file_handle, html_file_path = tempfile.mkstemp(suffix='.html')
                            os.close(html_file_handle)

                            with open(html_file_path, 'w') as f:
                                f.write(html_content)

                            combined_zip.write(html_file_path, f"{plot_name}.html")

                            # Clean up
                            if os.path.exists(html_file_path):
                                os.remove(html_file_path)

                    except Exception as e:
                        log.error(f"Error adding plot to zip: {e}")
                        # Clean up on error
                        if 'html_file_path' in locals() and os.path.exists(html_file_path):
                            os.remove(html_file_path)

                elif isinstance(result, ImageWorkflowResult):
                    try:
                        image_object = result.get_image_object()
                        image_uri = image_object.get('image_uri', '')
                        image_description = image_object.get('image_description', '')
                        image_name = result.name.replace(' ', '_')

                        if image_description:
                            image_name = f"{image_name}_{image_description.replace(' ', '_')}"

                        # Decode base64 image
                        # The image_uri is URL-encoded base64 string
                        decoded_uri = urllib.parse.unquote(image_uri)
                        image_data = base64.b64decode(decoded_uri)

                        # Create temporary PNG file
                        png_file_handle, png_file_path = tempfile.mkstemp(suffix='.png')
                        os.close(png_file_handle)

                        # Write image data to file
                        with open(png_file_path, 'wb') as f:
                            f.write(image_data)

                        # Add to zip
                        combined_zip.write(png_file_path, f"{image_name}.png")

                        # Clean up
                        if os.path.exists(png_file_path):
                            os.remove(png_file_path)

                    except Exception as e:
                        log.error(f"Error adding image to zip: {e}")
                        # Clean up on error
                        if 'png_file_path' in locals() and os.path.exists(png_file_path):
                            os.remove(png_file_path)

                elif isinstance(result, SpatialWorkflowResult):
                    try:
                        spatial_name = result.name.replace(' ', '_')
                        layer_count = 0

                        for layer in result.layers:
                            layer_type = layer.get('type', None)

                            if layer_type == 'geojson':
                                # Export as GeoJSON
                                geojson_data = layer.get('geojson', None)
                                if geojson_data:
                                    layer_title = layer.get('layer_title', f'layer_{layer_count}').replace(' ', '_')
                                    geojson_file_handle, geojson_file_path = tempfile.mkstemp(suffix='.geojson')
                                    os.close(geojson_file_handle)

                                    # Write GeoJSON to file
                                    with open(geojson_file_path, 'w') as f:
                                        json.dump(geojson_data, f, indent=2)

                                    # Add to zip
                                    combined_zip.write(geojson_file_path, f"{spatial_name}_{layer_title}.geojson")

                                    # Clean up
                                    if os.path.exists(geojson_file_path):
                                        os.remove(geojson_file_path)

                                    layer_count += 1

                            elif layer_type == 'wms':
                                # For WMS layers, save layer metadata as JSON
                                layer_title = layer.get('layer_title', f'layer_{layer_count}').replace(' ', '_')
                                metadata = {
                                    'type': 'WMS',
                                    'endpoint': layer.get('endpoint', ''),
                                    'layer_name': layer.get('layer_name', ''),
                                    'layer_title': layer.get('layer_title', ''),
                                    'layer_variable': layer.get('layer_variable', ''),
                                    'extent': layer.get('extent', None)
                                }

                                metadata_file_handle, metadata_file_path = tempfile.mkstemp(suffix='.json')
                                os.close(metadata_file_handle)

                                with open(metadata_file_path, 'w') as f:
                                    json.dump(metadata, f, indent=2)

                                combined_zip.write(metadata_file_path, f"{spatial_name}_{layer_title}_wms_info.json")

                                # Clean up
                                if os.path.exists(metadata_file_path):
                                    os.remove(metadata_file_path)

                                layer_count += 1

                    except Exception as e:
                        log.error(f"Error adding spatial layer to zip: {e}")
                        # Clean up on error
                        if 'geojson_file_path' in locals() and os.path.exists(geojson_file_path):
                            os.remove(geojson_file_path)
                        if 'metadata_file_path' in locals() and os.path.exists(metadata_file_path):
                            os.remove(metadata_file_path)

        # Prepare the response
        response = HttpResponse(content_type='application/zip')
        filename = f"{workflow_name.replace(' ', '_')}_datasets.zip"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        in_memory.seek(0)
        response.write(in_memory.read())

        return response

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
