#!/opt/tethys-python
import os
import sys
import traceback

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gssha_adapter.models.app_users.gssha_model_resource import GsshaModelResource
from gsshapyorm.orm import ProjectCard, ProjectFile, ChannelInputFile, LinkNodeDatasetFile
from gssha_adapter.utilities import extract_to_temp_dir


def run(resource_db_url, model_db_url, resource_id, input_archive, srid, status_key):
    """
    Condor executable that uploads a gssha model into a database using GSSHAPY.

    Args:
        resource_db_url(str): SQLAlchemy url to the Resource database (e.g.: postgresql://postgres:pass@localhost:5432/db).
        model_db_url(str): SQLAlchemy url to the GSSHAPY model database (e.g.: postgresql://postgres:pass@localhost:5432/db).
        resource_id(str): ID of the Resource associated with the GSSHA model.
        input_archive(str): Path to the GSSHA model zip archive.
        srid(str): Spatial reference system id (e.g.: 4236).
        status_key(str): Name of status key to use for status updates on the Resource.
    """  # noqa: E501
    resource = None
    resource_db_session = None
    model_db_session = None

    try:
        resource_db_engine = create_engine(resource_db_url)
        make_resource_db_session = sessionmaker(bind=resource_db_engine)
        resource_db_session = make_resource_db_session()
        resource = resource_db_session.query(GsshaModelResource).get(resource_id)

        resource.set_status(status_key, GsshaModelResource.STATUS_PENDING)
        resource_db_session.commit()

        project_directory, project_file_name = extract_to_temp_dir(input_archive)

        # Upload to Database
        project_file = ProjectFile()

        model_db_engine = create_engine(model_db_url)
        make_model_db_session = sessionmaker(bind=model_db_engine)
        resource.set_status(status_key, GsshaModelResource.STATUS_PROCESSING)
        resource_db_session.commit()

        model_db_session = make_model_db_session()
        project_file.readInput(
            directory=project_directory,
            projectFileName=project_file_name,
            session=model_db_session,
            spatial=True,
            spatialReferenceID=srid
        )

        # Link Link-Node-Datasets
        channel_input_file = model_db_session.query(ChannelInputFile).\
            filter(ChannelInputFile.id == project_file.channelInputFileID).\
            one()

        link_node_datasets = model_db_session.query(LinkNodeDatasetFile).all()

        for link_node_dataset in link_node_datasets:
            link_node_dataset.linkToChannelInputFile(
                session=model_db_session,
                channelInputFile=channel_input_file
            )

        # Calculate model area in square miles
        msk_file_name = model_db_session.query(ProjectCard) \
            .filter(ProjectCard.name == "WATERSHED_MASK") \
            .one() \
            .value \
            .replace('\"', '')

        temp_input_msk_path = os.path.join(project_directory, msk_file_name)

        with open(temp_input_msk_path, 'r') as msk:
            msk_lines = msk.readlines()

        active_cell_count = 0
        ignore = ['north:', 'south:', 'east:', 'west:', 'rows:', 'cols:']
        for line in msk_lines:
            values = line.split()

            if values[0] not in ignore:
                for value in values:
                    if float(value) > 0:
                        active_cell_count += 1

        grid_size = model_db_session.query(ProjectCard) \
            .filter(ProjectCard.name == "GRIDSIZE") \
            .one() \
            .value

        square_meters_per_square_mile_conversion = 2589988.1103
        model_area = (float(grid_size) ** 2) * active_cell_count / square_meters_per_square_mile_conversion

        # Set Attributes
        resource.set_attribute('scenario_id', project_file.id)
        base_model_history = resource.get_attribute('base_model_history')
        base_model_history.insert(0, project_file.id)  #: using scenario_id to store current base_model_id
        resource.set_attribute('base_model_history', base_model_history)
        resource.set_attribute('area', model_area)

        # Set Status
        resource and resource.set_status(status_key, GsshaModelResource.STATUS_SUCCESS)
        resource_db_session.commit()

        sys.stdout.write('\nSuccessfully processed [INPUT] {0}\n'.format(resource_id))

    except Exception as e:
        if resource:
            resource and resource.set_status(status_key, GsshaModelResource.STATUS_ERROR)
            resource_db_session.commit()
        sys.stderr.write('Error processing {0}'.format(resource_id))
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write(repr(e))
        sys.stderr.write(str(e))
        raise e
    finally:
        resource_db_session and resource_db_session.close()
        model_db_session and model_db_session.close()


if __name__ == "__main__":
    args = sys.argv
    args.pop(0)
    run(*args)
