#!/opt/tethys-python
"""
********************************************************************************
* Name: detention_basin/run_pre_detention_basin_scenario.py
* Author: nswain
* Created On: December 07, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
import os
import json
import datetime as dt
from pprint import pprint
from gsshapyorm.orm import ProjectFile, gag, prj
from gssha_adapter.workflows.detention_basin.grid import Grid
from gssha_adapter.workflows.detention_basin.modifier import Modifier
from gssha_adapter.workflows.gssha_helpers import find_ohl_link_nodes_for_stream_cell, get_stream_cell_nodes, \
    run_gssha, reproject_point, read_ohl_to_series, add_num_threads_to_prj
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # Needed model files
    ele_filename = 'temp.ele'
    msk_filename = 'original.msk'
    gst_filename = 'temp.gst'

    # Out files
    inflow_new_filename = 'det_basin_outlet.idx'
    msk_new_filename = 'temp.msk'
    ts_new_filename = 'det_basin_cell_inflow.xys'
    ihl_new_filename = 'det_basin_output_locations.ihl'

    # Other files
    project_name = 'temp'
    project_file_name = project_name + '.prj'
    mapping_table_file_name = project_name + '.cmt'
    ohl_filename = project_name + '.ohl'
    cdl_filename = project_name + '.cdl'  # OVERLAND_Q_CUM_LOCATION
    cds_filename = project_name + '.cds'  # OVERLAND_Q_CUM_LOCATION

    # Make sure we're running on a model resource, not a group resource
    if resource.children:
        raise Exception('ERROR:  Cannot run Detention Basin workflow from a group.  Please run from a model resource.')

    model_srid = resource.get_attribute('srid')
    print('SRID: {}'.format(model_srid))

    # Enable the GDAL drivers for exporting the rasters
    model_db_session.execute("SET SESSION postgis.gdal_enabled_drivers = 'ENABLE_ALL';")

    # Get GSSHA Project File
    base_model_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id
    if not base_model_id:
        base_model_id = 1
        print('WARNING: No base model id was found. Using default base model id of 1.')
    print(f'Base Model ID: {base_model_id}')

    project_file = model_db_session.query(ProjectFile).get(base_model_id)

    # Populate Args
    project_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gssha_files')

    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)

    # Write all input files
    project_file.writeInput(model_db_session, project_dir, project_name)

    # Rename the Mask file
    temp_input_msk_path = os.path.join(project_dir, msk_new_filename)
    new_input_msk_path = os.path.join(project_dir, msk_filename)
    os.rename(temp_input_msk_path, new_input_msk_path)

    # Extract and reformat job parameters from params_json
    detention_basins = {}

    # Get Detention Basins
    cdt_features = params_json['Create Detention Basins']['parameters']['geometry']['features']

    for feature in cdt_features:
        s_fid = str(feature['properties']['id'])
        lat_long_boundary = feature['geometry']['coordinates'][0]

        # Reproject the coordinates from Lat/Long to coordinate system of the model
        model_native_boundary = []
        for x_lng, y_lat in lat_long_boundary:
            x_native, y_native = reproject_point(
                x=x_lng,
                y=y_lat,
                in_srid=4326,
                out_srid=model_srid,
            )
            model_native_boundary.append([x_native, y_native])

        detention_basins[s_fid] = {'boundary': model_native_boundary}

    # Get the absolute start time
    has_precip_unif_card = model_db_session.query(prj.ProjectCard).\
        filter(prj.ProjectCard.projectFileID == base_model_id).\
        filter(prj.ProjectCard.name == "PRECIP_UNIF").\
        all()
    has_precip_file_card = model_db_session.query(prj.ProjectCard).\
        filter(prj.ProjectCard.projectFileID == base_model_id).\
        filter(prj.ProjectCard.name == "PRECIP_FILE").\
        all()

    if has_precip_unif_card and has_precip_file_card:
        raise RuntimeError("Project file has PRECIP_UNIF and PRECIP_FILE")

    start_of_simulation = None
    if has_precip_unif_card:
        start_date = model_db_session.query(prj.ProjectCard). \
            filter(prj.ProjectCard.projectFileID == base_model_id). \
            filter(prj.ProjectCard.name == "START_DATE"). \
            one()
        start_time = model_db_session.query(prj.ProjectCard). \
            filter(prj.ProjectCard.projectFileID == base_model_id). \
            filter(prj.ProjectCard.name == "START_TIME"). \
            one()

        start_of_simulation = dt.datetime.strptime(start_date.value + " " + start_time.value, '%Y %m %d %H %M')
    elif has_precip_file_card:
        gage_value_row = model_db_session.query(gag.PrecipValue).\
            join(gag.PrecipEvent).\
            join(gag.PrecipFile). \
            join(ProjectFile). \
            filter(ProjectFile.id == base_model_id).\
            first()

        start_of_simulation = gage_value_row.dateTime

    if not start_of_simulation:
        raise RuntimeError("Failed to determine the starting time")

    print('START DATE TIME: {}'.format(start_of_simulation))

    # Extract outlet locations from params_file
    ddbo_features = params_json['Define Detention Basin Outlets']['parameters']['geometry']['features']

    # Get hydrograph for each feature
    dh_datasets = params_json['Define Pre Basin Hydrographs']['parameters']['datasets']

    # Combine outlets hydrographs
    outlets = {}
    for feature_id, dataset in dh_datasets.items():
        s_fid = str(feature_id)

        found_match = False
        for outlet_feature in ddbo_features:
            if outlet_feature['properties']['id'] == s_fid:
                # Convert the hydrograph
                hydrograph = []
                for minutes, discharge in zip(dataset['Time (min)'], dataset['Discharge (cfs)']):
                    time_offset = dt.timedelta(minutes=minutes)
                    date_time_step = start_of_simulation + time_offset
                    hydrograph.append([date_time_step, discharge])

                # Convert the outlet coordinates
                coordinates = outlet_feature['geometry']['coordinates']
                x_native, y_native = reproject_point(
                    x=coordinates[0],
                    y=coordinates[1],
                    in_srid=4326,
                    out_srid=model_srid,
                )

                outlets[s_fid] = {
                    'location': [x_native, y_native],
                    'hydrograph': hydrograph
                }
                found_match = True
                break

        if not found_match:
            print('WARNING: Dataset defined for FID "{}", but no features with that FID provided.'.format(s_fid))
            continue

    print('Outlet Locations:')
    pprint(outlets)

    print('Detention Basins:')
    pprint(detention_basins)

    # Extract output locations from params_file
    dol_features = params_json['Define Output Locations']['parameters']['geometry']['features']
    print('Output Location:')
    pprint(dol_features)
    output_stream_nodes = []
    output_non_stream_coords = []
    series_types = {}
    idx_ohl = 0
    idx_cds = 0

    # Read the grid to calculate grid cell locations of points
    grd = Grid()
    grd.readGrass(project_dir, msk_filename)

    for idx, feature in enumerate(dol_features):
        geometry = feature['geometry']
        if geometry['type'].lower() != 'point':
            continue

        x_lng, y_lat = geometry['coordinates']

        # The following code looks to see if evaluation points are at link node stream cells or not.
        # If so, they will be considered stream cell nodes, and be processed in the IHL file.
        # If not, they will be considered overland flow locations, and be processed in the CDL file.

        # Get row/col of the cell the evaluation point falls in (convert to GSSHA model SRID first)
        x_out, y_out = reproject_point(x=x_lng, y=y_lat, out_srid=model_srid)
        eval_ij = grd.getIJfromCoords((x_out, y_out))
        eval_ij = [val + 1 for val in eval_ij]  # getIJfromCoords is 0 based, so add 1 to each item

        # Use gsshapyorm, to see if there are any streams in this evaluation cell
        num_stream_nodes, grid_stream_nodes = get_stream_cell_nodes(model_db_session, eval_ij[0], eval_ij[1])

        # Check if there are stream cells or not
        if num_stream_nodes and grid_stream_nodes:
            max_ln_coords = find_ohl_link_nodes_for_stream_cell(grid_stream_nodes, model_db_session, x_lng,
                                                                y_lat, model_srid)

            output_stream_nodes.append(max_ln_coords)
            series_types[idx] = ('OHL', idx_ohl)
            idx_ohl += 1
        else:
            # We have an overland evaluation point
            x_out, y_out = reproject_point(x=x_lng, y=y_lat, out_srid=model_srid)
            ij = grd.getIJfromCoords((x_out, y_out))
            output_non_stream_coords.append(ij)
            series_types[idx] = ('CDS', idx_cds)
            idx_cds += 1

    model_db_session.close()

    print('Link-Node Output Locations:')
    pprint(output_stream_nodes)

    # Prepare modify parameters
    params = {
        'path': project_dir,
        'project_file_name': project_file_name,
        'mapping_table_file_name': mapping_table_file_name,
        'msk_file_name': msk_filename,
        'msk_new_file_name': msk_new_filename,
        'gst_file_name': gst_filename,
        'ele_file_name': ele_filename,
        'inflow_new_file_name': inflow_new_filename,
        'ts_new_file_name': ts_new_filename,
        'ihl_new_file_name': ihl_new_filename,
        'ohl_new_file_name': ohl_filename,
        'cdl_new_file_name': cdl_filename,
        'cds_new_file_name': cds_filename,
        'detention_basins': detention_basins,
        'output_stream_nodes': output_stream_nodes,
        'output_non_stream_coords': output_non_stream_coords,
        'outlets': outlets
    }

    # Execute model file modifier
    mod = Modifier(params)
    worked = mod.process()

    if worked:
        mod.write_files()
        add_num_threads_to_prj(os.path.join(project_dir, project_file_name))
    else:
        raise RuntimeError('Unable to modify model.')

    # 4. Run the model
    print('Running GSSHA...')
    run_gssha(project_dir, project_file_name)

    # 5. Post-Process Output
    print('Post-processing model results...')

    # Parse ohl into json
    series_name = 'User Pre Basin'
    ohl_path = os.path.join(project_dir, ohl_filename)
    ohl_series = read_ohl_to_series(ohl_path, series_name)

    print('OHL Series:')
    pprint(ohl_series)

    # Parse cds into json -- flow values are cumulative, so we'll need to convert to flow intervals
    series_name = 'User Pre Basin - Overland Flow'
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
    with open('pre_detention_basin_ohl_series.json', 'w') as f:
        f.write(json.dumps(series))

    print('Saved File Successfully')
