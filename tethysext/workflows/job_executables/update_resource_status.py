#!/opt/tethys-python
import sys
import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from gssha_adapter.models.app_users.gssha_model_resource import GsshaModelResource


def run(workflow, resource_db_url, resource_id):
    resource_db_session = None

    try:
        # Get resource
        resource_db_engine = create_engine(resource_db_url)
        make_resource_db_session = sessionmaker(bind=resource_db_engine)
        resource_db_session = make_resource_db_session()
        resource = resource_db_session.query(GsshaModelResource).get(resource_id)

        status_success = False

        # Get status for upload keys
        if workflow == 'upload':
            upload_status = resource.get_status(GsshaModelResource.UPLOAD_STATUS_KEY, None)
            upload_gs_status = resource.get_status(GsshaModelResource.UPLOAD_GS_STATUS_KEY, None)

            upload_status_ok = upload_status in GsshaModelResource.OK_STATUSES
            upload_gs_status_ok = upload_gs_status in GsshaModelResource.OK_STATUSES

            status_success = upload_status_ok and upload_gs_status_ok

        # Set root status accordingly
        if status_success:
            resource.set_status(GsshaModelResource.ROOT_STATUS_KEY, GsshaModelResource.STATUS_SUCCESS)
        else:
            resource.set_status(GsshaModelResource.ROOT_STATUS_KEY, GsshaModelResource.STATUS_FAILED)

        resource_db_session.commit()
    except Exception as e:
        sys.stderr.write('Error processing {0}'.format(resource_id))
        sys.stderr.write(str(e))
        traceback.print_exc(file=sys.stderr)
    finally:
        resource_db_session and resource_db_session.close()


if __name__ == '__main__':
    args = sys.argv
    args.pop(0)
    run(*args)
