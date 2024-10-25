#!/opt/tethys-python
"""
********************************************************************************
* Name: culvert_resize/run_scenario.py
* Author: nswain
* Created On: January 18, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import json
import os
from pprint import pprint
import shutil

from gsshapyorm.orm import ProjectFile
import numpy as np
from osgeo import gdal, ogr, osr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gssha_adapter.workflows.detention_basin.grid import Grid
from gssha_adapter.workflows.disable_upstream_cells import DisableUpstreamCells
from gssha_adapter.workflows.gssha_helpers import reproject_point
from tethysext.atcore.services.workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # This is necessary to prevent the job from being put on hold if it fails prematurely
    print('Creating empty output file... ')
    with open(f'{extra_args[1]}_delineate_polygons.json', 'w') as f:
        f.write(json.dumps({}))

    # Other files
    project_name = 'temp'

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

    # Extract output locations from params_file
    dcl_features = params_json['Define Culvert Locations']['parameters']['geometry']['features']
    print('Culvert Location Features:')
    pprint(dcl_features)

    # Extract output locations from params_file
    duc_features = params_json['Define Upstream Cells']['parameters']['geometry']['features']
    print('Define Upstream Cells Location Features:')
    pprint(duc_features)
    duc_coords = []

    # Read the grid to calculate grid cell locations of delineation points
    grd = Grid()
    grd.readGrass(project_dir, project_name + '.msk')

    for _, feature in enumerate(duc_features):
        geometry = feature['geometry']
        if geometry['type'].lower() != 'point':
            continue

        if geometry['type'].lower() == 'point':
            # Point location
            x_lng, y_lat = geometry['coordinates']
            duc_coords.append((x_lng, y_lat))

    print('Delineation locations:')
    pprint(duc_coords)

    # Processing upstream areas for each delineation location
    if grd:
        # Use the mask file previously read to get the dimensions of the grid
        # Use the elevation and mask files to send data to TOPAZ
        x_min = grd.west
        y_max = grd.north
        delta_x = grd.deltax
        delta_y = grd.deltay
        elev_raster = os.path.join(project_dir, project_name + '.ele')
        mask_raster = os.path.join(project_dir, project_name + '.msk')
        elevations = np.loadtxt(elev_raster, dtype=np.float32, skiprows=6)
        with open(mask_raster, 'r') as f:
            # Store the header of the mask file (origin, num cells, size, etc)
            mask_header = [next(f) for _ in range(6)]
        orig_watershed_mask = np.loadtxt(mask_raster, dtype=int, skiprows=6)

        print('Getting Upstream Cells from TOPAZ...')
        for duc_feature in duc_features:
            print(f'Disabling Cells for Delineation Location: {duc_feature["geometry"]["coordinates"]}')
            x_out, y_out = reproject_point(x=duc_feature['geometry']['coordinates'][0],
                                           y=duc_feature['geometry']['coordinates'][1], out_srid=model_srid)
            disable_cells = DisableUpstreamCells(orig_watershed_mask, elevations, x_min, y_max, delta_x, -delta_y,
                                                 (x_out, y_out))
            disable_cells.run()
            watershed_mask = disable_cells.watershed_mask
            duc_feature['mask_raster'] = watershed_mask

        # Combine the watershed masks and write
        # (This will be used for gssha model runs)
        watershed_mask = orig_watershed_mask
        for duc_feature in duc_features:
            watershed_mask = np.logical_and(duc_feature['mask_raster'], watershed_mask)
        out_mask_raster = f'{extra_args[1]}_new_mask_combined.asc'
        np.savetxt(out_mask_raster, watershed_mask, '%d')  # Write mask values
        with open(out_mask_raster, 'r+') as f:
            # Make sure the header is included at the beginning of the file
            lines = f.readlines()
            for header_part in reversed(mask_header):
                lines.insert(0, header_part)
            f.seek(0)
            f.writelines(lines)

        # Make a difference between the original watershed mask and the new one with upstream cells
        # (This will be used for displaying a simple upstream area in the results in post processing)
        diff_mask = orig_watershed_mask - watershed_mask
        out_diff_mask_raster = f'{extra_args[1]}_diff_mask.asc'
        np.savetxt(out_diff_mask_raster, diff_mask, '%d')  # Write diff mask values
        with open(out_diff_mask_raster, 'r+') as f:
            # Make sure the header is included at the beginning of the file
            lines = f.readlines()
            for header_part in reversed(mask_header):
                lines.insert(0, header_part)
            f.seek(0)
            f.writelines(lines)

        # Polygonize the raster (gdal) from the difference in the original vs. new mask
        # This should leave us with a mask of all zeros, except for the new upstream areas just found.
        # When Polygonize is finished, it will have a polygon feature around the new upstream areas only.
        bounds_file = f'{extra_args[1]}_bounds.shp'
        layer_name = f'{extra_args[1]}_bounds'
        srs_raster = osr.SpatialReference()
        srs_raster.ImportFromEPSG(int(model_srid))
        vec_ds = ogr.GetDriverByName('ESRI Shapefile').CreateDataSource(bounds_file)
        vec_lyr = vec_ds.CreateLayer(layer_name, srs=srs_raster, geom_type=ogr.wkbMultiPolygon)
        orig_ds = gdal.OpenEx(os.path.join(project_dir, project_name + '.msk'))
        orig_band = orig_ds.GetRasterBand(1)
        diff_ds = gdal.OpenEx(out_diff_mask_raster)
        diff_band = diff_ds.GetRasterBand(1)
        gdal.Polygonize(orig_band, diff_band, vec_lyr, -1)
        del vec_ds  # del the dataset, to force it to write all the way

        # gdal VectorTranslate polygon output to the _delineate_polygons.json file in GeoJSON format, in Lat/Long
        vec_ds = gdal.OpenEx(bounds_file)
        ds_sl = gdal.VectorTranslate(  # noqa: F841
            f'{extra_args[1]}_temp_delineate_polygons.json',  # temp filename, becaues GeoJSON driver can't overwrite
            srcDS=vec_ds,
            dstSRS="EPSG:4326",  # geojson layer needs lat/long for display later
            format='GeoJSON'
        )
        del ds_sl  # del the dataset, to force it to write all the way
        del vec_ds
        del orig_ds
        del diff_ds

        # Copy over the VectorTranslate results (GeoJSON driver can't overwrite existing files)
        print(f'\nSaving GeoJSON file {extra_args[1]}_delineate_polygons.json\n')
        shutil.copy2(f'{extra_args[1]}_temp_delineate_polygons.json', f'{extra_args[1]}_delineate_polygons.json')

        # Set the attributes of the new watershed mask (convert numpy array to list, so JSON serialize work)
        step.set_attribute('upstream_watershed_mask', watershed_mask.tolist())
        resource_db_session.commit()

    model_db_session.commit()
    scenario_model_db_session.close()

    print('\nSaved file Successfully\n')
