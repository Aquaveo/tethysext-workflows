#!/opt/tethys-python
"""
********************************************************************************
* Name: culvert_resize/run_with_routed_flows.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import datetime
import json
import os
import sys
import traceback

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from gsshapyorm.orm import ProjectFile, gag, prj
from shapely.geometry import LineString

from gssha_adapter.workflows.gssha_helpers import run_gssha, get_link_node_for_point, \
    read_ohl_to_series, add_num_threads_to_prj, reproject_point
from gssha_adapter.workflows.detention_basin.modified_puls import ModifiedPuls
from tethysext.atcore.services.workflows.decorators import workflow_step_job
from gssha_adapter.workflows.detention_basin.modifier_culvert import ModifierCulvert


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # This is necessary to prevent the job from being put on hold if it fails prematurely
    print('Creating empty output file... ')
    with open(f'{extra_args[0]}_{extra_args[1]}_ohl_series.json', 'w') as f:
        f.write(json.dumps({}))
    with open(f'{extra_args[0]}_{extra_args[1]}_mp_series.json', 'w') as f:
        f.write(json.dumps({}))

    def _location_from_geometry(geometry, model_srid):
        """
        Reprojects a culvert geometry to the model SRID.

        Args:
            geometry (list): Point or LineString geometry location of the culvert.
            model_srid (int): The model spatial reference ID.

        Returns:
            _type_: _description_
        """
        if geometry['type'].lower() == 'point':
            # Point location
            x_lng, y_lat = geometry['coordinates']
        else:
            # Interpolate along the line to find the midpoint
            line = LineString(geometry['coordinates'])
            midpoint = line.interpolate(0.5, normalized=True)
            x_lng, y_lat = midpoint.x, midpoint.y

        # Convert the outlet coordinates
        x_native, y_native = reproject_point(
            x=x_lng,
            y=y_lat,
            in_srid=4326,
            out_srid=model_srid,
        )
        return [x_native, y_native]

    # Get scenario resource that is running.
    # If there are multiple scenarios and dynamic jobs, the resource passed in is the source resource,
    # not necessarily the resource we want to be running on.
    # Ex:  workflow was created on a 2 year storm model, but this needs to be a dynamic job for a
    #      100 year storm.  Grab the scenario resource and use that instead of the base 2 year resource.
    scenario_resource = resource_db_session.query(resource_class).get(extra_args[1])
    db_id = scenario_resource.get_attribute('database_id')
    scenario_model_db_url = f'{cmd_args.model_db_url.rsplit("/", 1)[0]}/agwa_{db_id.replace("-", "_")}'
    scenario_model_db_engine = create_engine(scenario_model_db_url)
    make_scenario_model_db_session = sessionmaker(bind=scenario_model_db_engine)
    scenario_model_db_session = make_scenario_model_db_session()

    # Get scenario model Spatial Reference ID (from the scenario resource)
    model_srid = scenario_resource.get_attribute('srid')
    print('Scenario SRID: {}'.format(model_srid))

    # Get GSSHA Project File (from the scenario model db session)
    base_model_id = scenario_resource.get_attribute('scenario_id')
    if not base_model_id:
        base_model_id = 1
        print('WARNING: No base model id was found. Using default base model id of 1.')
    print(f'Scenario Base Model ID: {base_model_id}')
    project_file = scenario_model_db_session.query(ProjectFile).get(base_model_id)

    # Get Culverts and culvert characteristics
    culverts = {}
    culvert_features = params_json['Define Culvert Locations']['parameters']['geometry']['features']
    for feature in culvert_features:
        feature_id = feature['properties']['id']  # Use the id as the key
        culverts[feature_id] = feature['properties']  # Store the culvert properties (name, type, width, height, etc.)
        culverts[feature_id]['geometry'] = feature['geometry']
        native_location = _location_from_geometry(feature['geometry'], model_srid)
        culverts[feature_id]['location'] = native_location
        culverts[feature_id]['native_location'] = native_location

    # Get Delineate Upstream step, and associated mask
    delineate_step = workflow.get_step_by_name('Delineate Upstream Areas')
    delineate_mask = delineate_step.get_attribute('upstream_watershed_mask', [])
    print(f'Using delineated polygon: {delineate_mask != []}')

    # Get Inflows calculated in the Compute Flows Run
    flow_results_step = workflow.get_step_by_name('Review Flows')
    flow_map_result = flow_results_step.get_result_by_codename('hydrographs_map')
    flow_result_layer = flow_map_result.get_layer('culvert_locations')
    flow_result_layer_features = flow_result_layer['geojson']['features']

    # Ge the Inflows curve for the culvert locations
    for feature in flow_result_layer_features:
        inflow_series = {}
        feature_id = feature['properties']['id']
        for series in feature['properties']['plot']['data']:
            inflow_series[series['name']] = series
        culverts[feature_id]['inflow_series'] = inflow_series

    # Get Elevation-Storage curve for the culvert locations
    for feature_id, culvert in culverts.items():
        culvert['storage'] = params_json['Enter Elevation-Storage Curves']['parameters']['datasets'][feature_id]
        # Check if the storage curve used is all nodata.  If so, calculate it.
        if all(val == -99999.9 for val in culvert['storage']['Storage (cu-ft)']):
            # Calculate the storage ((surface[i] + surface[i-1]) / 2) * (elev[i] - elev[i-1]) + storage[i-1]
            culvert['storage']['Storage (cu-ft)'] = [0.0] * len(culvert['storage']['Elevation (ft)'])
            for i in range(1, len(culvert['storage']['Elevation (ft)'])):
                surf = culvert['storage']['Surface (sq-ft)'][i]
                surf_1 = culvert['storage']['Surface (sq-ft)'][i-1]
                elev = culvert['storage']['Elevation (ft)'][i]
                elev_1 = culvert['storage']['Elevation (ft)'][i-1]
                sto_1 = culvert['storage']['Storage (cu-ft)'][i-1]
                culvert['storage']['Storage (cu-ft)'][i] = ((surf + surf_1) / 2.0) * (elev - elev_1) + sto_1

    # Get the Elevation-Discharge curve for the culvert locations
    for feature_id, culvert in culverts.items():
        culvert['discharge'] = params_json['Enter Elevation-Discharge Curves']['parameters']['datasets'][feature_id]

    # Run Modified Puls culvert routing for each culvert location
    for _, culvert in culverts.items():
        storage_info = [val[1] for val in culvert['storage'].items()]
        storage_elevation = storage_info[0]
        storage_vals = storage_info[2]
        storage_vals = [storage_cuft * 2.295684E-5 for storage_cuft in storage_vals]  # Convert from ft^3 to acre-ft
        input_discharge = []
        for discharge_key, discharge in culvert['discharge'].items():
            # Get the discharge curve matching the current option on the dynamic job
            if discharge_key.startswith(extra_args[0].replace("_", " ")):
                input_discharge = discharge
        input_hydro = []
        for inflow_key, inflow in culvert['inflow_series'].items():
            # Get the inflow series matching the current scenario on the dynamic job
            if inflow_key.removeprefix("Flow Simulation ") == extra_args[2]:
                input_hydro = [[x, y] for x, y in zip(inflow['x'], inflow['y'])]
        mp = ModifiedPuls(storage_elevation, storage_vals, input_discharge, input_hydro)
        output_hydro, storage_curve = mp.run()
        culvert['modified_puls'] = output_hydro
        culvert['mp_storage_curve'] = storage_curve

    # Get the absolute start time of the simulation (needed for writing time series data later)
    has_precip_unif_card = scenario_model_db_session.query(prj.ProjectCard).\
        filter(prj.ProjectCard.projectFileID == base_model_id).\
        filter(prj.ProjectCard.name == "PRECIP_UNIF").\
        all()
    has_precip_file_card = scenario_model_db_session.query(prj.ProjectCard).\
        filter(prj.ProjectCard.projectFileID == base_model_id).\
        filter(prj.ProjectCard.name == "PRECIP_FILE").\
        all()

    if has_precip_unif_card and has_precip_file_card:
        raise RuntimeError("Project file has PRECIP_UNIF and PRECIP_FILE")

    start_of_simulation = None
    if has_precip_unif_card:
        start_date = scenario_model_db_session.query(prj.ProjectCard). \
            filter(prj.ProjectCard.projectFileID == base_model_id). \
            filter(prj.ProjectCard.name == "START_DATE"). \
            one()
        start_time = scenario_model_db_session.query(prj.ProjectCard). \
            filter(prj.ProjectCard.projectFileID == base_model_id). \
            filter(prj.ProjectCard.name == "START_TIME"). \
            one()

        start_of_simulation = datetime.datetime.strptime(start_date.value + " " + start_time.value, '%Y %m %d %H %M')
    elif has_precip_file_card:
        gage_value_row = scenario_model_db_session.query(gag.PrecipValue).\
            join(gag.PrecipEvent).\
            join(gag.PrecipFile). \
            join(ProjectFile). \
            filter(ProjectFile.id == base_model_id).\
            first()

        start_of_simulation = gage_value_row.dateTime

    if not start_of_simulation:
        raise RuntimeError("Failed to determine the starting time")

    print('START DATE TIME: {}'.format(start_of_simulation))

    # Other files
    project_name = 'temp'
    project_file_name = project_name + '.prj'
    mapping_table_file_name = project_name + '.cmt'
    ihl_filename = project_name + '.ihl'  # IN_HYD_LOCATION
    ohl_filename = project_name + '.ohl'  # OUT_HYD_LOCATION
    cdl_filename = project_name + '.cdl'  # OVERLAND_Q_CUM_LOCATION
    cds_filename = project_name + '.cds'  # CUM_DISCHARGE
    gst_filename = project_name + '.gst'
    ele_filename = 'temp.ele'
    inflow_new_filename = 'culvert_outlet.idx'
    ts_new_filename = 'culvert_cell_inflow.xys'
    msk_filename = 'original.msk'
    msk_new_filename = project_name + '.msk'

    # Enable the GDAL drivers for exporting the rasters
    scenario_model_db_session.execute("SET SESSION postgis.gdal_enabled_drivers = 'ENABLE_ALL';")

    # Populate Args
    project_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gssha_files')

    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)

    # Write all input files
    project_file.writeInput(scenario_model_db_session, project_dir, project_name)

    # Rename the Mask file
    temp_input_msk_path = os.path.join(project_dir, msk_new_filename)
    new_input_msk_path = os.path.join(project_dir, msk_filename)
    os.rename(temp_input_msk_path, new_input_msk_path)

    # Separate the overland flow culverts from the ones on the channel
    dcl_features = params_json['Define Culvert Locations']['parameters']['geometry']['features']
    print('Culvert Location Features:')
    print(dcl_features)

    channel_culverts = {}
    overland_culverts = {}
    for _, feature in enumerate(dcl_features):
        geometry = feature['geometry']
        if geometry['type'].lower() != 'point' and geometry['type'].lower() != 'linestring':
            continue

        if geometry['type'].lower() == 'point':
            # Point location
            x_lng, y_lat = geometry['coordinates']
        else:
            # Interpolate along the line to find the midpoint
            line = LineString(geometry['coordinates'])
            midpoint = line.interpolate(0.5, normalized=True)
            x_lng, y_lat = midpoint.x, midpoint.y

        x_native, y_native = _location_from_geometry(geometry, model_srid)

        # Get the hydrograph, and convert to date time
        cur_culvert = culverts[feature['properties']['id']]
        hydrograph = cur_culvert['modified_puls']
        hydrograph = [[start_of_simulation + datetime.timedelta(minutes=val[0]), val[1]] for val in hydrograph]

        link_node_coords = get_link_node_for_point(scenario_model_db_session, x_lng, y_lat, model_srid,
                                                   model_tolerance=500.0)
        if link_node_coords[0]:
            channel_culverts[feature['properties']['id']] = {
                'location': [x_native, y_native],
                'hydrograph': hydrograph
            }
        else:
            overland_culverts[feature['properties']['id']] = {
                'location': [x_native, y_native],
                'hydrograph': hydrograph
            }
        culverts[feature['properties']['id']]['hydrograph'] = hydrograph

    print('Channel culverts:')
    print(channel_culverts)
    print('Overland flow culverts:')
    print(overland_culverts)

    # Extract evaluation point locations from params_json
    eval_features = params_json['Choose Evaluation Points']['parameters']['geometry']['features']
    print('Evaluation Point Locations:')
    print(eval_features)
    output_stream_nodes = []

    for feature in eval_features:
        geometry = feature['geometry']
        if geometry['type'].lower() != 'point':
            continue

        x_lng, y_lat = geometry['coordinates']

        # Get the link node for the evaluation point
        link_node_coords = get_link_node_for_point(scenario_model_db_session, x_lng, y_lat, model_srid)

        if link_node_coords is not None:
            output_stream_nodes.append(link_node_coords)

    scenario_model_db_session.close()

    # Set up the params dict to store what is needed for the ModifierCulvert class
    params = {
        'path': project_dir,
        'project_file_name': project_file_name,
        'mapping_table_file_name': mapping_table_file_name,
        'msk_file_name': msk_filename,
        'msk_new_file_name': msk_new_filename,
        'gst_file_name': gst_filename,
        'ele_file_name': ele_filename,
        'inflow_new_file_name': inflow_new_filename,
        'ihl_new_file_name': ihl_filename,
        'ohl_new_file_name': ohl_filename,
        'cdl_new_file_name': cdl_filename,
        'cds_new_file_name': cds_filename,
        'ts_new_file_name': ts_new_filename,
        'ihl_new_file_name': ihl_filename,
        'output_stream_nodes': output_stream_nodes,
        'overland_culverts': overland_culverts,
        'channel_culverts': channel_culverts,
        'culverts': culverts,
        'delineate_upstream': delineate_mask,
    }
    print('ModifierCulvert Params:')
    print(params)

    # Execute model file modifier
    try:
        mod = ModifierCulvert(params)
        mod.process()
        mod.write_files()
        add_num_threads_to_prj(os.path.join(project_dir, project_file_name))
    except Exception:
        sys.stderr.write('ERROR: Failed to modify GSSHA files because of the following error:\n')
        traceback.print_exc()

    try:
        print('Updated Files:')
        print('Original Mask File:')
        print(open(os.path.join(project_dir, msk_filename), 'r').read())
        print('New Mask File:')
        print(open(os.path.join(project_dir, msk_new_filename), 'r').read())
        print('GST File:')
        print(open(os.path.join(project_dir, gst_filename), 'r').read())
        print('ELE File:')
        print(open(os.path.join(project_dir, ele_filename), 'r').read())
    except Exception as e:
        print('Failed to print updated files because of the following error:')
        print(e)

    # 4. Run the model
    print('Running GSSHA...')
    run_gssha(project_dir, project_file_name)

    # 5. Post-Process Output
    print('Post-processing model results...')

    # Parse ohl into json
    series_name = f'Flow Simulation {extra_args[0]}'
    ohl_path = os.path.join(project_dir, ohl_filename)
    ohl_series = read_ohl_to_series(ohl_path, series_name) if os.path.exists(ohl_path) else []

    print('\n\nOHL Series:')
    print(ohl_series)

    # Save to file
    print('Saving File... ')
    with open(f'{extra_args[0]}_{extra_args[1]}_ohl_series.json', 'w') as f:
        f.write(json.dumps(ohl_series))

    # Save Modified Puls culvert routing to file
    print('Saving Modified Puls info... ')
    mp_data = []
    culvert_names = []
    for feature in dcl_features:
        if 'culv_name' in feature['properties']:
            # Handle renaming of params
            feature['properties']['culvert_name'] = feature['properties']['culv_name']
    culvert_names = [feature['properties']['culvert_name'] for feature in dcl_features]
    for c_name, (_, culvert) in zip(culvert_names, culverts.items()):
        # Get the modified puls hydrograph, ex:  [[x1, y1], [x2, y2], ...]
        mp_hydro = culvert['modified_puls']
        mp_dict = {'name': c_name, 'x': [], 'y': []}
        mp_dict['x'] = [val[0] for val in mp_hydro]
        mp_dict['y'] = [val[1] for val in mp_hydro]
        mp_data.append(mp_dict)
    with open(f'{extra_args[0]}_{extra_args[1]}_mp_series.json', 'w') as f:
        f.write(json.dumps(mp_data))

    print('Saved file Successfully')
