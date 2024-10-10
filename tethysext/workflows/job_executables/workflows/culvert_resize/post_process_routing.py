#!/opt/tethys-python
"""
********************************************************************************
* Name: culvert_resize/post_process_routing.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import copy
import json
import math
import re
import pandas as pd
from pprint import pprint
from gssha_adapter.utilities import safe_str
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # 1. Extract output locations geojson from params
    dcl_geojson = params_json['Define Culvert Locations']['parameters']['geometry']
    print('Define Culvert Locations GeoJSON:')
    pprint(dcl_geojson)
    dol_geojson = params_json['Choose Evaluation Points']['parameters']['geometry']
    print('Choose Evaluation Points GeoJSON:')
    pprint(dol_geojson)

    # 2. Get routed series for all jobs
    # Get the option names from the discharge curve (Existing, Option 1, Option 2, Option 3, etc)
    discharge_datasets_param = params_json["Enter Elevation-Discharge Curves"]["parameters"]["datasets"]
    culverts_discharge = []
    elevation_discharge = []
    for item in discharge_datasets_param.items():
        culverts_discharge.append(item[0])
        elevation_discharge.append(item[1])

    options = []
    if elevation_discharge:
        test_options = list(elevation_discharge[0].keys())
        test_options = test_options[1:]
        df = pd.DataFrame(elevation_discharge[0])
        for option in test_options:
            # Skip over columns that are entirely NODATA values
            is_nodata = list(df[option].isin([-99999.9]))
            if not any(is_nodata):
                options.append(option)
    options = [re.sub(r'\([^)]*\)', '', val).rstrip().replace(' ', '_') for val in options]

    # Get the input filenames, and store the routed flow json value
    # The filenames for the routed flows follow a naming convention because they use dynamic jobs,
    # rather than simply grabbing the transfer_input_files, etc.
    routed = {}
    modified_puls = {}
    inflow_series = {}
    job_names = []
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
                routed[job_name] = json.loads(f.read())
            print(f'{job_name} Series:')
            pprint(routed[job_name])
            mp_filename = f'{option}_{scenario_id}_mp_series.json'
            with open(mp_filename, 'r') as f:
                modified_puls[job_name] = json.loads(f.read())
            pprint(modified_puls[job_name])
            job_names.append(job_name)
        scenario_names.append(scenario_name)
        scenario_fnames.append(scenario_fname)
        inflow_series[scenario_name] = []

    # Get the previous result step
    flow_results_step = workflow.get_step_by_name('Review Flows')
    flow_map_result = flow_results_step.get_result_by_codename('hydrographs_map')
    flow_result_layer = flow_map_result.get_layer('culvert_locations')
    flow_result_layer_features = flow_result_layer['geojson']['features']

    for feature in flow_result_layer_features:
        feature_series = feature['properties']['plot']['data']

        for key, series in zip(inflow_series.keys(), feature_series):
            series['name'] = f'Flow Simulation {key}'  # Update name, as it also has the scenario name in it
            inflow_series[key].append(series)

    # 5. Add to GeoJSON (NEW)
    scenario_geojson = {}
    print('Adding plot properties to GeoJSON features...')
    for scenario_name, scenario_fname in zip(scenario_names, scenario_fnames):
        scenario_geojson[scenario_name] = copy.deepcopy(dol_geojson)
        discharge_units = 'cfs'

        cur_routed_names = []
        routed_options = []
        for option in options:
            job_name = f'run_{scenario_fname}_{option}'
            cur_routed_names.append(job_name)
            routed_options.extend(routed[job_name])

        for idx, feature in enumerate(scenario_geojson[scenario_name]['features']):
            # Get the routed values for this point index
            max_values = []
            cur_routed = []
            routed_idx = list(range(idx, len(routed_options), len(scenario_geojson[scenario_name]['features'])))
            for r_idx in routed_idx:
                cur_routed.append(routed_options[r_idx])
            for r in cur_routed:
                max_values.append(max(r['y']))

            # Find max value on y-axis for output point plots
            max_y_value = max(max_values) if max_values else 0.0
            max_y_value = math.floor(max_y_value * 1.1) + 1

            # Add the routed series
            feature['properties']['plot'] = {
                'title': f'{scenario_name} Routed Hydrographs for {feature["properties"]["point_name"]}',
                'data': cur_routed,
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
        curr_spatial_result = step.result.get_result_by_codename(f'{fname}_routed_map')
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

            # Now add the culvert results, but just for this scenario name
            culvert_layer = copy.deepcopy(flow_result_layer)
            culvert_layer_features = culvert_layer['geojson']['features']
            for feature in culvert_layer_features:
                # Update the plot
                feature_series = feature['properties']['plot']['data']
                filtered_data = [i for i in feature_series if (i['name'].endswith(name))]
                feature['properties']['plot']['data'] = filtered_data

                # Get the max plot length for cutting off modified puls later
                cutoff_length = 0
                for filtered in filtered_data:
                    cutoff_length = len(filtered['x']) if len(filtered['x']) > cutoff_length else cutoff_length

                # Add modified puls hydrographs to the culvert point
                mp_plot_data = []
                for option in options:
                    mp_option_data = modified_puls[f'run_{fname}_{option}']
                    for mp_opt in mp_option_data:
                        if 'culv_name' in feature['properties']:
                            # Handle renaming of params
                            feature['properties']['culvert_name'] = feature['properties']['culv_name']
                        if mp_opt['name'] == feature['properties']['culvert_name']:
                            mp_opt['name'] = f'{mp_opt["name"]} Routed ({option})'
                            mp_opt['x'] = mp_opt['x'][:cutoff_length]
                            mp_opt['y'] = mp_opt['y'][:cutoff_length]
                            mp_plot_data.append(mp_opt)
                feature['properties']['plot']['data'] = mp_plot_data + filtered_data

                # Update the max y as well
                max_y = []
                for plot_data in filtered_data:
                    max_y.append(max(plot_data['y']))
                max_y_value = max(max_y)
                feature['properties']['plot']['layout']['yaxis']['range'] = [0, max_y_value]

            curr_spatial_result.add_geojson_layer(
                geojson=culvert_layer['geojson'],
                layer_id='culvert_locations',
                layer_name='culvert_locations',
                layer_title='Culvert Locations',
                layer_variable='culvert_locations',
                popup_title='Culvert Locations',
                selectable=True,
                plottable=True,
                label_options={'label_property': 'culvert_name'},
            )

    # # 7. Create Peak Flows Result
    # print('Create peak flows results...')
    # peak_flows_result = step.result.get_result_by_codename('peak_flows')
    # peak_flows_result.reset()

    # # Build dataframe for peak flows result
    # locations = []

    # for feature in dol_geojson['features']:
    #     properties = feature.get('properties')
    #     locations.append(properties['point_name'])

    # df = pd.DataFrame(data={
    #     'Locations': locations,
    # })
    # for key, item in routed.items():
    #     d_key = key.removeprefix('run_').replace('_', ' ')
    #     df[d_key] = [round(max(vals['y']), 2) for vals in item]

    # dataset_title = 'Peak Flows'

    # # Save to result
    # print('\n\nSaving peak flows to result...')
    # peak_flows_result.add_pandas_dataframe(dataset_title, df, show_export_button=True)

    # # 8. Create Time Series Result
    # print('Create time series results...')
    # time_series_result = step.result.get_result_by_codename('time_series')
    # time_series_result.reset()

    # for key, item in routed.items():
    #     # Set up the key and common time values
    #     d_key = key.removeprefix('run_').replace('_', ' ')
    #     time = item[0]['x']
    #     d = {
    #         'Time (min)': time
    #     }

    #     # Add flow values for each location
    #     for idx, location in enumerate(locations):
    #         d[location] = item[idx]['y']

    #     # Set up the data frame
    #     df = pd.DataFrame(data=d)
    #     print(f'\n\nSaving time series for {d_key} to results...')
    #     time_series_result.add_pandas_dataframe(d_key, df, show_export_button=True)
