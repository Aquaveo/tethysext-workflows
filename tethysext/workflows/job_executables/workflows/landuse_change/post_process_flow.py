#!/opt/tethys-python
"""
********************************************************************************
* Name: landuse_change/post_process_flow.py
* Created On: September 8, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import copy
import json
import math
import pandas as pd
from pprint import pprint
from gssha_adapter.utilities import safe_str
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # 1. Extract output locations geojson from params
    dac_geojson = params_json['Define Areas to Change']['parameters']['geometry']
    print('Define Areas to Change GeoJSON:')
    pprint(dac_geojson)
    dol_geojson = params_json['Choose Evaluation Points']['parameters']['geometry']
    print('Choose Evaluation Points GeoJSON:')
    pprint(dol_geojson)

    # 2. Get routed series for all jobs
    options = ['unchanged', 'changed']

    # Get the input filenames, and store the routed flow json value
    # The filenames for the routed flows follow a naming convention because they use dynamic jobs,
    # rather than simply grabbing the transfer_input_files, etc.
    calculated = {}
    inflow_series = {}
    # job_names = []
    scenario_names = []
    scenario_fnames = []
    scenarios = params_json['Select Flow Simulation Options']['parameters']['form-values']['storm_type']
    for scenario in scenarios:
        idx = scenario.rfind(':')  # Use rfind in case scenario name includes a colon
        scenario_name = scenario[:idx]
        scenario_fname = safe_str(scenario_name)
        scenario_id = scenario[idx+1:]
        for option in options:
            # Get the json file for this combination of option (Existing, Run 1, etc) and scenario ID
            job_name = f'run_{scenario_fname}_{option}'
            output_filename = f'{option}_{scenario_id}_ohl_series.json'
            with open(output_filename, 'r') as f:
                calculated[job_name] = json.loads(f.read())
            print(f'{job_name} Series:')
            pprint(calculated[job_name])

        scenario_names.append(scenario_name)
        scenario_fnames.append(scenario_fname)
        inflow_series[scenario_name] = []

    # 5. Add to GeoJSON (NEW)
    scenario_geojson = {}
    print('Adding plot properties to GeoJSON features...')
    for scenario_name, scenario_fname in zip(scenario_names, scenario_fnames):
        scenario_geojson[scenario_name] = copy.deepcopy(dol_geojson)
        discharge_units = 'cfs'

        cur_calculated_names = []
        calculated_options = []
        for option in options:
            job_name = f'run_{scenario_fname}_{option}'
            cur_calculated_names.append(job_name)
            calculated_options.extend(calculated[job_name])

        for idx, feature in enumerate(scenario_geojson[scenario_name]['features']):
            # Get the calculated values for this point index
            max_values = []
            cur_calculated = []
            calculated_idx = list(range(idx, len(calculated_options), len(scenario_geojson[scenario_name]['features'])))
            for r_idx in calculated_idx:
                cur_calculated.append(calculated_options[r_idx])
            for r in cur_calculated:
                max_values.append(max(r['y']))

            # Find max value on y-axis for output point plots
            max_y_value = max(max_values) if max_values else 0.0
            max_y_value = math.floor(max_y_value * 1.1) + 1

            # Add the routed series
            feature['properties']['plot'] = {
                'title': f'{scenario_name} Hydrographs for {feature["properties"]["point_name"]}',
                'data': cur_calculated,
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

    pprint(scenario_geojson)

    # 6. Create Layer on Result
    print('Create output hydrograph layers...')
    for (_, geojson), name, fname in zip(scenario_geojson.items(), scenario_names, scenario_fnames):
        curr_spatial_result = step.result.get_result_by_codename(f'{fname}_map')
        if curr_spatial_result:
            # Hydrographs for evaluation points
            curr_spatial_result.reset()
            curr_spatial_result.add_geojson_layer(
                geojson=geojson,
                layer_id=f'routed_eval_points{name}',
                layer_name=f'routed_eval_points{name}',
                layer_title='Evaluation Points',
                layer_variable=f'routed_eval_points{name}',
                popup_title='Evaluation Points',
                selectable=True,
                plottable=True,
                label_options={'label_property': 'point_name'},
            )

    # 7. Create Peak Flows Result
    print('Create peak flows results...')
    peak_flows_result = step.result.get_result_by_codename('peak_flows')
    peak_flows_result.reset()

    # Build dataframe for peak flows result
    locations = []

    for feature in dol_geojson['features']:
        properties = feature.get('properties')
        locations.append(properties['point_name'])

    df = pd.DataFrame(data={
        'Locations': locations,
    })
    for key, item in calculated.items():
        d_key = key.removeprefix('run_').replace('_', ' ')
        df[d_key] = [round(max(vals['y']), 2) for vals in item]

    dataset_title = 'Peak Flows'

    # Save to result
    print('\n\nSaving peak flows to result...')
    peak_flows_result.add_pandas_dataframe(dataset_title, df, show_export_button=True)

    # 8. Create Time Series Result
    print('Create time series results...')
    time_series_result = step.result.get_result_by_codename('time_series')
    time_series_result.reset()

    for key, item in calculated.items():
        # Set up the key and common time values
        d_key = key.removeprefix('run_').replace('_', ' ')
        time = item[0]['x']
        d = {
            'Time (min)': time
        }

        # Add flow values for each location
        for idx, location in enumerate(locations):
            d[location] = item[idx]['y']

        # Set up the data frame
        df = pd.DataFrame(data=d)
        print(f'\n\nSaving time series for {d_key} to results...')
        time_series_result.add_pandas_dataframe(d_key, df, show_export_button=True)
