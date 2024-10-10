#!/opt/tethys-python
"""
********************************************************************************
* Name: landuse_change/run_scenario.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import datetime
import json
import os
from pprint import pprint
import shutil

from sqlalchemy import and_, create_engine
from sqlalchemy.orm import sessionmaker
from gsshapyorm.orm import IndexMap, MapTable, ProjectFile, gag, prj

from gssha_adapter.workflows.detention_basin.grid import Grid
from gssha_adapter.workflows.gssha_helpers import find_ohl_link_nodes_for_stream_cell, get_stream_cell_nodes, \
    run_gssha, read_ohl_to_series, add_num_threads_to_prj, reproject_point
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job
from gssha_adapter.workflows.detention_basin.modifier_landuse import ModifierLanduse


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # This is necessary to prevent the job from being put on hold if it fails prematurely
    print('Creating empty output file... ')
    with open(f'{extra_args[0]}_{extra_args[1]}_ohl_series.json', 'w') as f:
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
        lat_long_boundary = geometry['coordinates'][0]

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
        return model_native_boundary

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

    # Get Landuse Changes areas and properties
    landuse_areas = {}
    landuse_features = params_json['Define Areas to Change']['parameters']['geometry']['features']
    for feature in landuse_features:
        feature_id = feature['properties']['id']  # Use the id as the key
        landuse_areas[feature_id] = feature['properties']  # Store the landuse properties (name, landuse, etc)
        landuse_areas[feature_id]['geometry'] = feature['geometry']
        landuse_areas[feature_id]['location'] = _location_from_geometry(feature['geometry'], model_srid)
        if 'lu_class' in feature['properties']:
            # Handle renamed params
            feature['properties']['landuse_classification'] = feature['properties']['lu_class']
        landuse_areas[feature_id]['landuse_code'] = int(feature['properties']['landuse_classification'].split(":")[0])

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
    cds_filename = project_name + '.cds'  # OVERLAND_Q_CUM_LOCATION
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
    shutil.copy(temp_input_msk_path, new_input_msk_path)

    # Get the landuse area polygons
    dac_features = params_json['Define Areas to Change']['parameters']['geometry']['features']
    print('Areas to Change Features:')
    pprint(dac_features)

    # Extract evaluation point locations from params_json
    eval_features = params_json['Choose Evaluation Points']['parameters']['geometry']['features']
    print('Evaluation Point Locations:')
    pprint(eval_features)
    output_stream_nodes = []
    output_non_stream_coords = []
    series_types = {}
    idx_ohl = 0
    idx_cds = 0

    # Read the grid to calculate grid cell locations of points
    grd = Grid()
    grd.readGrass(project_dir, project_name + '.msk')

    for idx, feature in enumerate(eval_features):
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
        num_stream_nodes, grid_stream_nodes = get_stream_cell_nodes(scenario_model_db_session, eval_ij[0], eval_ij[1])

        # Check if there are stream cells or not
        if num_stream_nodes and grid_stream_nodes:
            max_ln_coords = find_ohl_link_nodes_for_stream_cell(grid_stream_nodes, scenario_model_db_session, x_lng,
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

    print("\nReading index maps for land use and soil type information...")

    # Find the index maps needed for the land use change calculations
    idx_roughness = -1
    idx_green_ampt_moisture = -1
    idx_green_ampt_infiltration = -1
    map_tables = scenario_model_db_session.query(MapTable).\
        filter(MapTable.mapTableFileID == base_model_id).\
        all()
    for map_table in map_tables:
        if map_table.name.upper() == "ROUGHNESS":
            idx_roughness = map_table.idxMapID
        elif map_table.name.upper() == "GREEN_AMPT_INITIAL_SOIL_MOISTURE":
            idx_green_ampt_moisture = map_table.idxMapID
        elif map_table.name.upper() == "GREEN_AMPT_INFILTRATION":
            idx_green_ampt_infiltration = map_table.idxMapID
    if idx_roughness == -1:
        raise RuntimeError("Failed to find the ROUGHNESS index map")
    if idx_green_ampt_moisture == -1:
        raise RuntimeError("Failed to find the GREEN_AMPT_INITIAL_SOIL_MOISTURE index map")
    if idx_green_ampt_infiltration == -1:
        raise RuntimeError("Failed to find the GREEN_AMPT_INFILTRATION index map")

    # Read the ROUGHESS index map (land use)
    landuse_info = {}
    landuse_idx_file = ''
    index_maps = scenario_model_db_session.query(IndexMap).\
        filter(and_(IndexMap.mapTableFileID == project_file.mapTableFileID,
                    IndexMap.id == idx_roughness)).\
        all()
    for index_map in index_maps:
        landuse_idx_file = index_map.filename
        for idx in index_map.indices:
            landuse_info[idx.index] = idx.description1

    # Read the GREEN_AMPT_INITIAL_SOIL_MOISTURE index map (soil type)
    soiltype_info = {}
    soiltype_idx_file = ''
    index_maps = scenario_model_db_session.query(IndexMap).\
        filter(and_(IndexMap.mapTableFileID == project_file.mapTableFileID,
                    IndexMap.id == idx_green_ampt_moisture)).\
        all()
    for index_map in index_maps:
        soiltype_idx_file = index_map.filename
        for idx in index_map.indices:
            soiltype_info[idx.index] = idx.description1

    # Read the GREEN_AMPT_INFILTRATION index map (combination)
    combined_info = {}
    combined_idx_file = ''
    index_maps = scenario_model_db_session.query(IndexMap).\
        filter(and_(IndexMap.mapTableFileID == project_file.mapTableFileID,
                    IndexMap.id == idx_green_ampt_infiltration)).\
        all()
    for index_map in index_maps:
        combined_idx_file = index_map.filename
        for idx in index_map.indices:
            combined_info[idx.index] = [idx.description1, idx.description2]

    # Combine index map data
    index_map_info = {
        'landuse_info': landuse_info,
        'landuse_idx_file': landuse_idx_file,
        'soiltype_info': soiltype_info,
        'soiltype_idx_file': soiltype_idx_file,
        'combined_info': combined_info,
        'combined_idx_file': combined_idx_file
    }
    print("Index Map information:")
    pprint(index_map_info)

    scenario_model_db_session.close()

    # Set up the params dict to store what is needed for the ModifierLanduse class
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
        'ihl_new_file_name': ihl_filename,
        'ohl_new_file_name': ohl_filename,
        'cdl_new_file_name': cdl_filename,
        'cds_new_file_name': cds_filename,
        'output_stream_nodes': output_stream_nodes,
        'output_non_stream_coords': output_non_stream_coords,
        'index_map_info': index_map_info,
        'change': extra_args[0],
        'landuse_areas': landuse_areas,
    }

    # Execute model file modifier
    mod = ModifierLanduse(params)
    mod.process()
    mod.write_files()
    add_num_threads_to_prj(os.path.join(project_dir, project_file_name))

    # 4. Run the model
    print('Running GSSHA...')
    run_gssha(project_dir, project_file_name)

    # 5. Post-Process Output
    print('Post-processing model results...')

    # Parse ohl into json
    series_name = f'Flow Simulation {extra_args[0]}'
    ohl_path = os.path.join(project_dir, ohl_filename)
    shutil.copy2(ohl_path, '/home/michael/testing.csv')
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
    print(f'Saving File:  {extra_args[0]}_{extra_args[1]}_ohl_series.json')
    with open(f'{extra_args[0]}_{extra_args[1]}_ohl_series.json', 'w') as f:
        f.write(json.dumps(series))

    print('Saved file Successfully')
