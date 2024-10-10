#!/opt/tethys-python
import sys
import traceback

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tethys_dataset_services.engines.geoserver_engine import GeoServerSpatialDatasetEngine
from tethysext.atcore.services.model_database import ModelDatabaseConnection
from gssha_adapter.models.app_users.gssha_model_resource import GsshaModelResource
from gssha_adapter.services.gssha_spatial_manager import GsshaSpatialManager
from gssha_adapter.utilities import extract_to_temp_dir


def run(resource_db_url, model_db_url, resource_id, scenario_id, input_archive, srid, geoserver_endpoint,
        geoserver_public_endpoint, geoserver_username, geoserver_password, geoserver_job_type, with_link_node_datasets,
        status_key):
    """
    Condor executable that creates the geoserver layers for GSSHA projects.

    Args:
        resource_db_url(str): SQLAlchemy url to the Resource database (e.g.: postgresql://postgres:pass@localhost:5432/db).
        model_db_url(str): SQLAlchemy url to the GSSHAPY model database (e.g.: postgresql://postgres:pass@localhost:5432/db).
        resource_id(str): ID of the Resource associated with the GSSHA model.
        scenario_id(str): ID of the scenario.
        input_archive(str): Path to the GSSHA model zip archive.
        srid(str): Spatial reference system id (e.g.: 4236).
        geoserver_endpoint(str): Url to the GeoServer public endpoint (e.g.: http://localhost:8181/geoserver/rest/).
        geoserver_public_endpoint(str): Url to the GeoServer public endpoint (e.g.: https://geoserver.aquaveo.com/geoserver/rest/).
        geoserver_username(str): Administrator username for given GeoServer.
        geoserver_password(str): Administrator password for given GeoServer.
        geoserver_job_type(str): The type of GeoServer job type to run. One of 'ALL'.
        with_link_node_datasets(bool): Create the link node dataset layers if True.
        status_key(str): Name of status key to use for status updates on the Resource.
    """  # noqa: E501
    resource = None
    resource_db_session = None

    try:
        make_session = sessionmaker()
        model_db = ModelDatabaseConnection(model_db_url)
        gs_engine = GeoServerSpatialDatasetEngine(
            endpoint=geoserver_endpoint,
            username=geoserver_username,
            password=geoserver_password,
            node_ports=[8081, 8082, 8083, 8084]
        )
        gs_engine.public_endpoint = geoserver_public_endpoint
        gs_manager = GsshaSpatialManager(gs_engine)
        project_directory, _ = extract_to_temp_dir(input_archive)

        _type_to_function_mapping = {
            'ALL': gs_manager.create_all_layers,
        }

        resource_db_engine = create_engine(resource_db_url)
        resource_db_session = make_session(bind=resource_db_engine)
        resource = resource_db_session.query(GsshaModelResource).get(resource_id)

        # Derive scenario_id
        print(f"GIVEN SCENARIO_ID, TYPE: {scenario_id}, {type(scenario_id)}")
        if scenario_id is None or scenario_id == 'None':
            scenario_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id
            print(f"BASE_MODEL_ID: {scenario_id}")

        if not scenario_id:
            scenario_id = 1
            print('WARNING: No base_model_id was found in the resource and no scenario id was supplied. '
                  'Using default scenario id of 1.')

        if geoserver_job_type == 'ALL':
            gs_manager.link_geoserver_to_db(model_db, reload_config=False)

        _type_to_function_mapping[geoserver_job_type](
            model_db=model_db,
            srid=srid,
            project_dir=project_directory,
            scenario_id=scenario_id,
            with_link_node_datasets=with_link_node_datasets,
            reload_config=True
        )

        resource.set_status(status_key, GsshaModelResource.STATUS_SUCCESS)
        resource_db_session.commit()
        sys.stdout.write('\nSuccessfully processed {0}\n'.format(scenario_id))

    except Exception as e:
        if resource:
            resource.set_status(status_key, GsshaModelResource.STATUS_ERROR)
            resource_db_session.commit()
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write(type(e).__name__)
        sys.stderr.write(repr(e))
        raise e
    finally:
        resource_db_session and resource_db_session.close()


if __name__ == "__main__":
    args = sys.argv
    args.pop(0)
    run(*args)
