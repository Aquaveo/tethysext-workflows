#!/opt/tethys-python
"""
********************************************************************************
* Name: grab_discharge/run_scenario.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import json
import os
from pprint import pprint

from gsshapyorm.orm import ProjectFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gssha_adapter.workflows.detention_basin.grid import Grid
from gssha_adapter.workflows.gssha_helpers import find_ohl_link_nodes_for_stream_cell, get_stream_cell_nodes, \
    run_gssha, read_ohl_to_series, add_num_threads_to_prj, reproject_point
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # This is necessary to prevent the job from being put on hold if it fails prematurely
    print('Creating empty output file... ')
    with open(f'{extra_args[1]}_ohl_series.json', 'w') as f:
        f.write(json.dumps({}))

    # Other files
    project_name = 'temp'
    project_file_name = project_name + '.prj'
    ihl_filename = project_name + '.ihl'  # IN_HYD_LOCATION
    ohl_filename = project_name + '.ohl'  # OUT_HYD_LOCATION
    cdl_filename = project_name + '.cdl'  # OVERLAND_Q_CUM_LOCATION
    cds_filename = project_name + '.cds'  # CUM_DISCHARGE

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
    scenario_model_db_session.execute("SET SESSION postgis.gdal_enabled_drivers = 'ENABLE_ALL';")

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

    # Populate Args
    project_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gssha_files')

    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)

    # Write all input files
    project_file.writeInput(scenario_model_db_session, project_dir, project_name)

    # Change the prj file to use the correct values and flags
    prj_path = os.path.join(project_dir, project_file_name)
    with open(prj_path, 'r') as prj_file:
        prj_lines = prj_file.readlines()
    with open(prj_path, 'w') as prj_file:
        has_qout_cfs = False
        has_cdl = False
        has_cds = False
        for prj_line in prj_lines:
            if 'IN_HYD_LOCATION' in prj_line:
                prj_file.write(f'IN_HYD_LOCATION          "{ihl_filename}"\n')
            elif 'OUT_HYD_LOCATION' in prj_line:
                prj_file.write(f'OUT_HYD_LOCATION         "{ohl_filename}"\n')
            elif 'OVERLAND_Q_CUM_LOCATION' in prj_line:
                has_cdl = True
                prj_file.write(f'OVERLAND_Q_CUM_LOCATION  "{cdl_filename}"\n')
            elif 'CUM_DISCHARGE' in prj_line:
                has_cds = True
                prj_file.write(f'CUM_DISCHARGE            "{cds_filename}"\n')
            elif 'QOUT_CFS' in prj_line:
                has_qout_cfs = True
                prj_file.write(prj_line)
            else:
                prj_file.write(prj_line)

        if not has_cdl:
            prj_file.write(f'OVERLAND_Q_CUM_LOCATION  "{cdl_filename}"\n')
        if not has_cds:
            prj_file.write(f'CUM_DISCHARGE            "{cds_filename}"\n')
        if not has_qout_cfs:
            prj_file.write('QOUT_CFS\n')
    add_num_threads_to_prj(prj_path)

    # Extract output locations from params_file
    dcl_features = params_json['Choose Evaluation Points']['parameters']['geometry']['features']
    print('Evaluation Point Features:')
    pprint(dcl_features)
    dcl_stream_nodes = []
    dcl_non_stream_coords = []
    series_types = {}
    idx_ohl = 0
    idx_cds = 0

    # Read the grid to calculate grid cell locations of points
    grd = Grid()
    grd.readGrass(project_dir, project_name + '.msk')

    for idx, feature in enumerate(dcl_features):
        geometry = feature['geometry']
        if geometry['type'].lower() != 'point' and geometry['type'].lower() != 'linestring':
            continue

        if geometry['type'].lower() == 'point':
            # Point location
            x_lng, y_lat = geometry['coordinates']

        # The following code looks to see if evaluation points are at link node stream cells or not.
        # If so, they will be considered stream cell nodes, and be processed in the IHL file.
        # If not, they will be considered overland flow locations, and be processed in the CDL file.

        # Get row/col of the cell the evaluation point falls in (convert to GSSHA model SRID first)
        x_out, y_out = reproject_point(x=x_lng, y=y_lat, out_srid=model_srid)
        eval_ij = grd.getIJfromCoords((x_out, y_out))
        eval_ij = [val + 1 for val in eval_ij]  # getIJfromCoords is 0 based, so add 1 to each item

        # Use gsshapyorm, to see if there are any streams in this evaluation cell
        num_stream_nodes, grid_stream_nodes = get_stream_cell_nodes(scenario_model_db_session, eval_ij[0], eval_ij[1])

        # Check if there are stream cells or not
        if num_stream_nodes and grid_stream_nodes:
            max_ln_coords = find_ohl_link_nodes_for_stream_cell(grid_stream_nodes, scenario_model_db_session, x_lng,
                                                                y_lat, model_srid)

            dcl_stream_nodes.append(max_ln_coords)
            series_types[idx] = ('OHL', idx_ohl)
            idx_ohl += 1
        else:
            # We have an overland evaluation point
            dcl_non_stream_coords.append((x_lng, y_lat))
            series_types[idx] = ('CDS', idx_cds)
            idx_cds += 1

    scenario_model_db_session.close()

    print('Link-Node Evaluation Points:')
    pprint(dcl_stream_nodes)
    print('Evaluation Points not on stream:')
    pprint(dcl_non_stream_coords)

    # Overwrite ihl file
    with open(os.path.join(project_dir, ihl_filename), 'w') as cdl:
        cdl.write('{}\n'.format(len(dcl_stream_nodes)))
        for link, node in dcl_stream_nodes:
            cdl.write('{} {}\n'.format(link, node))

    # Overwrite cdl file
    with open(os.path.join(project_dir, cdl_filename), 'w') as cdl:
        cdl.write('{}\n'.format(len(dcl_non_stream_coords)))
        if len(dcl_non_stream_coords) > 0:
            for coords in dcl_non_stream_coords:
                x_out, y_out = reproject_point(x=coords[0], y=coords[1], out_srid=model_srid)
                ij = grd.getIJfromCoords((x_out, y_out))
                cdl.write(f'{ij[0] + 1} {ij[1] + 1}\n')

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
    pprint(ohl_series)

    # Parse cds into json -- flow values are cumulative, so we'll need to convert to flow intervals
    series_name = f'Flow Simulation {extra_args[0]}'
    cds_path = os.path.join(project_dir, cds_filename)
    cds_series = read_ohl_to_series(cds_path, series_name) if os.path.exists(cds_path) else []
    hyd_freq = float(project_file.getCard('HYD_FREQ').value.split()[0])
    for cds in cds_series:
        # Convert the cumuluative flow values from the CDS file to intervals like a standard hydrograph
        cur_cds_reg = [0.0]
        for idx in range(1, len(cds['y'])):
            # Subtract the current cumulative value from the previous cumulative value to get the volume for this time,
            # and then convert to cubic meters per second based on the project's HYD_FREQ value (in minutes).
            incremental_cms = (cds['y'][idx] - cds['y'][idx-1]) / (hyd_freq * 60.0)
            # Convert units to cubic feet per second, and store
            # (The QOUT_CFS card does not appear to apply to the .cds file, so do the units conversion)
            incremental_cfs = incremental_cms * 35.3146667215
            cur_cds_reg.append(incremental_cfs)
        cds['y'] = cur_cds_reg

    print('\n\nCDS Series (converted):')
    pprint(cds_series)

    # Combine the series data from the OHL and CDS files into one, in the order of the features read
    series = []
    for _, series_type in series_types.items():
        # For the current feature, check if we need to grab the series data from the OHL or CDS series data read
        if series_type[0] == 'OHL':
            series.append(ohl_series[series_type[1]])
        elif series_type[0] == 'CDS':
            series.append(cds_series[series_type[1]])

    # Save to file
    print('Saving File... ')
    with open('latest_ohl_series.json', 'w') as f:
        f.write(json.dumps(series))

    print('Saving Output to Files... ')
    with open(f'{extra_args[1]}_ohl_series.json', 'w') as f:
        f.write(json.dumps(series))

    print('Saved file Successfully')
