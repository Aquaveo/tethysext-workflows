#!/opt/tethys-python
"""
********************************************************************************
* Name: run_post_process.py
* Author: nswain
* Created On: December 28, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import json
import math
from pprint import pprint

import pandas as pd

from tethysext.workflows.services.workflows.decorators import workflow_step_job


@workflow_step_job
def main(
    db_session, workflow, step, gs_private_url, gs_public_url,
    workflow_class, params_json, params_file, cmd_args, extra_args
):
    # Extract extra args
    input_files = extra_args[0].split(',')
    print(f'Input Files: {input_files}')

    # Get points geometry from spatial input step
    points = params_json['Generic Spatial Input Step']['parameters']['geometry']
    print('Points:')
    pprint(points)

    # Get series data from input files
    series = {}
    for series_file in input_files:
        # Store the series data from each of the json files
        with open(series_file) as f:
            s = json.loads(f.read())
        series[s['name']] = s

    for name, s in series.items():
        # Print out the data
        print(f'Series {name}:')
        
        pprint(s, compact=True)

    # 5. Add to GeoJSON
    print('\n\nAdding plot properties to GeoJSON features...')
    assert len(points['features']) == len(series)

    # Find max value on y-axis for output point plots
    max_y_value = 0
    for _, s in series.items():
        cur_y = max(s['y'])
        max_y_value = max(cur_y, max_y_value)

    max_y_value = math.floor(max_y_value * 1.1) + 1

    # Create plot for output points
    for point in points['features']:
        point_name = point['properties']['point_name']
        point['properties']['plot'] = {
            'title': f'Values for {point_name}',
            'data': [series[point_name]],
            'layout': {
                'autosize': True,
                'height': 415,
                'margin': {
                    'l': 80,
                    'r': 80,
                    't': 20,
                    'b': 80
                },
                'xaxis': {
                    'title': 'X',
                },
                'yaxis': {
                    'title': 'Y',
                    'range': [0, max_y_value],
                }
            }
        }

    pprint(points, compact=True)

    # Create Layer on Result
    print('Create result map layers...')
    generic_map_result = step.result.get_result_by_codename('generic_map')
    generic_map_result.reset()
    generic_map_result.add_geojson_layer(
        geojson=points,
        layer_id='point_locations',
        layer_name='point_locations',
        layer_title='Point Locations',
        layer_variable='point_locations',
        popup_title='Culvert Location',
        selectable=True,
        plottable=True,
        label_options={'label_property': 'point_name'},
    )

    # Add series to table result
    print('Create series tables...')
    generic_table_result = step.result.get_result_by_codename('generic_table')
    generic_table_result.reset()

    for point_name, s in series.items():
        df = pd.DataFrame({'x': s['x'], 'y': s['y']})
        generic_table_result.add_pandas_dataframe(point_name, df, show_export_button=True)

    # Add series to plot
    print('Adding series to plot...')
    generic_plot_result = step.result.get_result_by_codename('generic_plot')
    generic_plot_result.reset()
    for s_name, s in series.items():
        generic_plot_result.add_series(s_name, [s['x'], s['y']])
