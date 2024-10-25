#!/opt/tethys-python
"""
********************************************************************************
* Name: detention_basin/post_process.py
* Author: nswain
* Created On: May 30, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import json
import math
import pandas as pd
from pprint import pprint
from gsshapyorm.orm import ProjectFile
from tethysext.atcore.services.workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # 1. Extract output locations geojson from params
    dol_geojson = params_json['Define Output Locations']['parameters']['geometry']
    print('Output Locations GeoJSON:')
    pprint(dol_geojson)

    # 2. Get ohl series for all jobs
    with open('original_ohl_series.json', 'r') as original_ohl:
        original_series = json.loads(original_ohl.read())

    print('Original Basin Series:')
    pprint(original_series, compact=True)

    with open('latest_ohl_series.json', 'r') as latest_ohl:
        latest_series = json.loads(latest_ohl.read())

    print('Latest Series:')
    pprint(latest_series, compact=True)

    with open('pre_detention_basin_ohl_series.json', 'r') as det_pre_ohl:
        det_pre_series = json.loads(det_pre_ohl.read())

    print('Detention Basin Pre Series:')
    pprint(det_pre_series, compact=True)

    with open('post_detention_basin_ohl_series.json', 'r') as det_post_ohl:
        det_post_series = json.loads(det_post_ohl.read())

    print('Detention Basin Post Series:')
    pprint(det_post_series, compact=True)

    # 4. Combine Series
    print('Combining series...')
    assert len(original_series) == len(latest_series)
    assert len(original_series) == len(det_pre_series)
    assert len(original_series) == len(det_post_series)
    combined_series = [[o, b, d_pre, d_post] for o, b, d_pre, d_post
                       in zip(original_series, latest_series, det_pre_series, det_post_series)]
    pprint(combined_series, compact=True)

    # 5. Add to GeoJSON
    print('Adding plot properties to GeoJSON features...')
    assert len(dol_geojson['features']) == len(combined_series)

    project_id = cmd_args.scenario_id
    project_file = model_db_session.query(ProjectFile).get(project_id)

    discharge_units = 'cfs'

    # Find max value on y-axis for output point plots
    max_y_value = 0
    for s in combined_series:
        original_y = max(s[0]['y'])
        latest_y = max(s[1]['y'])
        pre_y = max(s[2]['y'])
        post_y = max(s[3]['y'])

        current_y_max = max(original_y, latest_y, pre_y, post_y)
        max_y_value = max(max_y_value, current_y_max)

    max_y_value = math.floor(max_y_value * 1.1) + 1

    # Create plot for output points
    for series, feature in zip(combined_series, dol_geojson['features']):
        # Set the 'Original Baseline Model' and 'Latest Approved Model' plots to start off disabled, but still be
        # available on the plot if you click on them in the legend
        legend_only = ['Original Baseline Model', 'Latest Approved Model']
        for cur_series in series:
            cur_series['visible'] = 'legendonly' if cur_series['name'] in legend_only else True

        if 'loc_name' in feature['properties']:
            # Handle renamed params
            feature['properties']['location_name'] = feature['properties']['loc_name']
        feature['properties']['plot'] = {
            'title': f'Hydrograph Comparison for {feature["properties"]["location_name"]}',
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
                    'range': [0, max_y_value],
                }
            }
        }

    pprint(dol_geojson, compact=True)

    # 6. Create Layer on Result
    print('Create output hydrograph layers...')
    spatial_result = step.result.get_result_by_codename('output_hydrographs')
    spatial_result.reset()
    spatial_result.add_geojson_layer(
        geojson=dol_geojson,
        layer_name='output_locations',
        layer_title='Output Locations',
        layer_variable='output_locations',
        popup_title='Output Location',
        selectable=True,
        plottable=True,
        label_options={'label_property': 'location_name'},
    )

    # 7. Build pandas tables
    print('Create discharge comparison tables...')
    discharge_result = step.result.get_result_by_codename('discharge_comparisons')
    discharge_result.reset()

    # Build dataframe for comparision tab
    locations = []

    for feature in dol_geojson['features']:
        properties = feature.get('properties')
        if 'loc_name' in properties:
            # Handle renamed params
            properties['location_name'] = properties['loc_name']
        locations.append(properties['location_name'])

    max_pre_discharges = [round(max(site[2]['y']), 2) for idx, site in enumerate(combined_series)]
    max_post_discharges = [round(max(site[3]['y']), 2) for idx, site in enumerate(combined_series)]
    difference_discharges = []
    for x, y in zip(max_pre_discharges, max_post_discharges):
        difference_discharges.append(round(y - x, 2))

    d = {
        'Location': locations,
        f'Original Baseline Model ({discharge_units})':
            [round(max(site[0]['y']), 2) for idx, site in enumerate(combined_series)],
        f'Latest Approved Model ({discharge_units})':
            [round(max(site[1]['y']), 2) for idx, site in enumerate(combined_series)],
        f'User Pre Basin ({discharge_units})': max_pre_discharges,
        f'User Post Routed Basin ({discharge_units})': max_post_discharges,
        f'Difference ({discharge_units})': difference_discharges
    }

    df = pd.DataFrame(data=d)

    base_model_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id

    if not base_model_id:
        base_model_id = 1
        print('WARNING: No base model id was found. Using default base model id of 1.')

    print(f'Base Model ID: {base_model_id}')
    project_file = model_db_session.query(ProjectFile).get(base_model_id)

    dataset_title = 'Generic'

    if project_file.getCard('PRECIP_UNIF'):
        intensity = project_file.getCard('RAIN_INTENSITY').value
        duration = project_file.getCard('RAIN_DURATION').value
        dataset_title = f'Uniform: {intensity} mm/hr for {duration} minutes'
    elif project_file.getCard('PRECIP_FILE'):
        precip_events = project_file.precipFile.precipEvents

        if len(precip_events) > 0:
            dataset_title = precip_events[0].description

            if len(precip_events) > 1:
                dataset_title += '+'

    # Save to result
    discharge_result.add_pandas_dataframe(dataset_title, df, show_export_button=True)

    # Build dataframe for Time Series
    time_series = step.result.get_result_by_codename('time_series')
    time_series.reset()

    # Add Original hydrographs to time series
    time = original_series[0]['x']

    d = {
        'Time (min)': time
    }

    output_id = 0
    for location in locations:
        d[f'{location} (cfs)'] = original_series[output_id]['y']
        output_id += 1

    df = pd.DataFrame(data=d)
    time_series.add_pandas_dataframe('Original Baseline Model', df, show_export_button=True)

    # Add Latest hydrographs to time series
    time = latest_series[0]['x']

    d = {
        'Time (min)': time
    }

    output_id = 0
    for location in locations:
        d[f'{location} (cfs)'] = latest_series[output_id]['y']
        output_id += 1

    df = pd.DataFrame(data=d)
    time_series.add_pandas_dataframe('Latest Approved Model', df, show_export_button=True)

    # Add Pre hydrographs to time series
    time = det_pre_series[0]['x']

    d = {
        'Time (min)': time
    }

    output_id = 0
    for location in locations:
        d[f'{location} (cfs)'] = det_pre_series[output_id]['y']
        output_id += 1

    df = pd.DataFrame(data=d)
    time_series.add_pandas_dataframe('User Pre Basin', df, show_export_button=True)

    # Add Post hydrographs to time series
    time = det_post_series[0]['x']

    d = {
        'Time (min)': time
    }

    output_id = 0
    for location in locations:
        d[f'{location} (cfs)'] = det_post_series[output_id]['y']
        output_id += 1

    df = pd.DataFrame(data=d)
    time_series.add_pandas_dataframe('User Post Basin', df, show_export_button=True)

    print('Saving results...')
    resource_db_session.commit()
