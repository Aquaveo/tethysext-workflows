#!/opt/tethys-python
"""
********************************************************************************
* Name: culvert_resize/post_process_flow.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import json
from pprint import pprint
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # 1. Extract output locations geojson from params
    dcl_geojson = params_json['Define Culvert Locations']['parameters']['geometry']
    print('Define Culvert Locations GeoJSON:')
    pprint(dcl_geojson)

    duc_geojson = params_json['Define Upstream Cells']['parameters']['geometry']
    print('Define Upstream Cells Location Features:')
    pprint(duc_geojson)

    # 2. Get GeoJSON upstream polygons for all jobs
    # Because this comes from a callback function, we can't simply access step.option['jobs'] in order to get the
    # post_procesing job, and from the job, the series files (transfer input files) and names.
    # We manually construct these from the params_json instead, which gives us the scenarios in use from the storm type
    # list.
    upstream_files = []
    series_names = []
    series_data = []
    scenarios = params_json['Select Flow Simulation Options']['parameters']['form-values']['storm_type']
    for scenario in scenarios:
        idx = scenario.rfind(':')  # Use rfind in case scenario name includes a colon
        scenario_name = scenario[:idx]
        scenario_id = scenario[idx+1:]
        series_names.append(scenario_name)
        output_filename = f'{scenario_id}_delineate_polygons.json'
        upstream_files.append(f'{output_filename}')

    spatial_result = step.result.get_result_by_codename('polygons_map')
    spatial_result.reset()
    spatial_result.add_geojson_layer(
        geojson=dcl_geojson,
        layer_id='culvert_locations',
        layer_name='culvert_locations',
        layer_title='Culvert Locations',
        layer_variable='culvert_locations',
        popup_title='Culvert Location',
        selectable=True,
        plottable=False,
        label_options={'label_property': 'culvert_name'},
    )
    spatial_result.add_geojson_layer(
        geojson=duc_geojson,
        layer_id='delineate_locations',
        layer_name='delineate_locations',
        layer_title='Delineate Locations',
        layer_variable='delineate_locations',
        popup_title='Delineate Location',
        selectable=True,
        plottable=False,
        label_options={'label_property': 'culvert_name'},
    )
    for file in upstream_files:
        # Store the series data from each of the json files
        with open(file) as f:
            series_data.append(json.loads(f.read()))
    for name, series in zip(series_names, series_data):
        # Print out the data
        print(f'\n\nSeries {name}:')
        pprint(series, compact=True)

        # Add polygons for each Series
        spatial_result.add_geojson_layer(
            geojson=series,
            layer_id=f'{name}',
            layer_name=f'{name}_upstream_area',
            layer_title=f'{name} Upstream Area',
            layer_variable=f'{name}',
            popup_title=f'{name} Upstream Area',
            selectable=True,
            plottable=False,
            label_options={},
        )
