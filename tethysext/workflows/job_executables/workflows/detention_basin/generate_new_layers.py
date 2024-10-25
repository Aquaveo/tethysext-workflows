#!/opt/tethys-python
"""
********************************************************************************
* Name: detention_basin/generate_new_layers.py
* Author: nswain
* Created On: September 3, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import os
from tethys_dataset_services.engines.geoserver_engine import GeoServerSpatialDatasetEngine
from gsshapyorm.orm import ProjectFile
from tethysext.workflows.services.workflows.decorators import workflow_step_job
from tethysext.workflows.services.model_database import ModelDatabaseConnection
from tethysext.workflowss.utilities import parse_url
from gssha_adapter.services.gssha_spatial_manager import GsshaSpatialManager


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # Parse GeoServer URLs
    gs_endpoint = parse_url(gs_private_url)
    gs_public_endpoint = parse_url(gs_public_url)
    print(f'Private GeoServer Endpoint: {gs_endpoint}')
    print(f'Public GeoServer Endpoint: {gs_public_endpoint}')

    gs_engine = GeoServerSpatialDatasetEngine(
        endpoint=gs_endpoint.endpoint,
        username=gs_endpoint.username,
        password=gs_endpoint.password,
        node_ports=[8081, 8082, 8083, 8084]
    )
    gs_engine.public_endpoint = gs_public_endpoint.endpoint
    gs_manager = GsshaSpatialManager(gs_engine)

    # Get attributes from workflow
    new_project_id = workflow.get_attribute('new_project_id')
    print(f'NEW PROJECT ID: {new_project_id}')

    # Get attributes from resource
    base_model_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id
    print(f'BASE MODEL ID: {base_model_id}')

    if int(base_model_id) == int(new_project_id):
        print(f'LAYERS FOR PROJECT ID {new_project_id} ALREADY GENERATED. SKIPPING...')
        return

    srid = resource.get_attribute('srid')
    print(f'SRID: {srid}')

    # Retrieve the project file
    project_file = model_db_session.query(ProjectFile).get(new_project_id)

    # Create workspace for writing files out
    project_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'gssha_files')

    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)

    # Enable the GDAL drivers for exporting the rasters
    model_db_session.execute("SET SESSION postgis.gdal_enabled_drivers = 'ENABLE_ALL';")

    # Write all files
    project_file.writeProject(session=model_db_session, directory=project_dir, name='temp')

    # Create all GeoServer Layers
    model_db = ModelDatabaseConnection(cmd_args.model_db_url)

    gs_manager.create_all_layers(
        model_db=model_db,
        srid=srid,
        project_dir=project_dir,
        scenario_id=new_project_id,
        with_link_node_datasets=False,  # TODO: Make this dynamic?
        for_scenario=True,
        reload_config=True
    )
