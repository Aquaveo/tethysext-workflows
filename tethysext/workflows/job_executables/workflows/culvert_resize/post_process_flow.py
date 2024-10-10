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
import math
import pandas as pd
from pprint import pprint
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # 1. Extract output locations geojson from params
    dcl_geojson = params_json['Define Culvert Locations']['parameters']['geometry']
    print('Define Culvert Locations GeoJSON:')
    pprint(dcl_geojson)

    # 2. Get ohl series for all jobs
    # Because this comes from a callback function, we can't simply access step.option['jobs'] in order to get the
    # post_procesing job, and from the job, the series files (transfer input files) and names.
    # We manually construct these from the params_json instead, which gives us the scenarios in use from the storm type
    # list.
    series_files = []
    series_names = []
    series_data = []
    scenarios = params_json['Select Flow Simulation Options']['parameters']['form-values']['storm_type']
    for scenario in scenarios:
        idx = scenario.rfind(':')  # Use rfind in case scenario name includes a colon
        scenario_name = scenario[:idx]
        scenario_id = scenario[idx+1:]
        series_names.append(scenario_name)
        output_filename = f'{scenario_id}_ohl_series.json'
        series_files.append(f'{output_filename}')

    for file in series_files:
        # Store the series data from each of the json files
        with open(file) as f:
            series_data.append(json.loads(f.read()))
    for name, series in zip(series_names, series_data):
        # Print out the data
        print(f'\n\nSeries {name}:')
        pprint(series, compact=True)

    # 4. Combine Series
    print('\n\nCombining series (new, using pandas.DataFrame)...')
    temp_df = pd.DataFrame(series_data)
    t = temp_df.transpose()
    combined_series = t.values.tolist()
    pprint(combined_series, compact=True)

    # 5. Add to GeoJSON
    print('\n\nAdding plot properties to GeoJSON features...')
    assert len(dcl_geojson['features']) == len(combined_series)

    discharge_units = 'cfs'

    # Find max value on y-axis for output point plots
    max_y_values = []
    for s in combined_series:
        max_y_value = 0
        for series in s:
            cur_y = max(series['y'])
            max_y_value = max(cur_y, max_y_value)
        max_y_value = math.floor(max_y_value * 1.1) + 1
        max_y_values.append(max_y_value)

    # Create plot for output points
    for series, feature, y_max in zip(combined_series, dcl_geojson['features'], max_y_values):
        if 'culv_name' in feature['properties']:
            # Handle renaming of params
            feature['properties']['culvert_name'] = feature['properties']['culv_name']
        feature['properties']['plot'] = {
            'title': f'Hydrograph for {feature["properties"]["culvert_name"]}',
            'data': series,
            'layout': {
                'autosize': True,
                'height': 415,
                'margin': {'l': 80, 'r': 80, 't': 20, 'b': 80},
                'xaxis':  {
                    'title': 'Time (min)',
                },
                'yaxis': {
                    'title': f'Discharge ({discharge_units})',
                    'range': [0, y_max],
                }
            }
        }

    pprint(dcl_geojson, compact=True)

    # 6. Create Layer on Result
    print('\n\nCreate output hydrograph layers...')
    spatial_result = step.result.get_result_by_codename('hydrographs_map')
    spatial_result.reset()
    spatial_result.add_geojson_layer(
        geojson=dcl_geojson,
        layer_id='culvert_locations',
        layer_name='culvert_locations',
        layer_title='Culvert Locations',
        layer_variable='culvert_locations',
        popup_title='Culvert Location',
        selectable=True,
        plottable=True,
        label_options={'label_property': 'culvert_name'},
    )

    # 7. Build dataframes for tables
    print('\n\nCreate discharge comparison tables...')
    peak_flows_result = step.result.get_result_by_codename('peak_flows')
    peak_flows_result.reset()

    # Build dataframe for peak flows result
    locations = []

    for feature in dcl_geojson['features']:
        properties = feature.get('properties')
        if 'culv_name' in properties:
            # Handle renaming of params
            properties['culvert_name'] = properties['culv_name']
        locations.append(properties['culvert_name'])

    df = pd.DataFrame(data={
        'Locations': locations,
    })
    for idx, name in enumerate(series_names):
        df[f'{name} ({discharge_units})'] = [round(max(site[idx]['y']), 2) for site in combined_series]

    dataset_title = 'Peak Flows'

    # Save to result
    print('\n\nSaving peak flows to result...')
    peak_flows_result.add_pandas_dataframe(dataset_title, df, show_export_button=True)

    # 8. Time series tables
    print('\n\nCreate time series tables...')
    time_series_result = step.result.get_result_by_codename('time_series')
    time_series_result.reset()

    for idx, location in enumerate(locations):
        time = combined_series[idx][0]['x']
        d = {
            'Time (min)': time
        }
        for series in combined_series[idx]:
            # Get the series for time values.  Different scenarios may have more timesteps,
            # so use the longest one found in order to create a valid DataFrame below.
            if len(series['x']) > len(d['Time (min)']):
                d['Time (min)'] = series['x']
            d[f'{location} (cfs) -- {series["name"]}'] = series['y']
        # Make the DataFrame, and fill in with NaN if a series is shorter than the time column.
        df = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in d.items()]))
        print(f'\n\nSaving time series for location {location} to results...')
        time_series_result.add_pandas_dataframe(location, df, show_export_button=True)
