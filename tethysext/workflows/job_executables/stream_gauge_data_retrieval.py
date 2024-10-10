#!/opt/tethys-python
import argparse
import datetime
import sys
import traceback

from sqlalchemy import func
from sqlalchemy.engine import create_engine
from sqlalchemy.orm.session import Session

from gssha_adapter.models.app_users.stream_gauge_resource import StreamGaugeResource
from gssha_adapter.models.app_users.stream_gauge_values import StreamGaugeValues
from stream_gauge_data_retrieval_trimble import retrieve_data_trimble
from stream_gauge_data_retrieval_usgs import retrieve_data_usgs
from gssha_adapter.models.app_users import AgwaOrganization


def _parse_args():
    """
    Parses and validates command line arguments for stream gauge data retrieval.

    Returns:
        argparse.Namespace: The parsed and validated arguments.
    """
    parser = argparse.ArgumentParser(description='A script to retrieve stream gauge data')
    parser.add_argument('resource_db_url', type=str, help='The sqlalchemy URL format for the database '
                        'connection (e.g. postgresql://user:pass@host:port/database)')
    parser.add_argument('-o', '--organization_id', type=str,
                        help='The organization ID for the gauges to retrieve data for')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    return args


def _seconds_since_last_value(session, stream_gauge_id):
    """
    Gets the number of seconds since the last stream gauge value.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge.

    Returns:
        int: The number of seconds since the last stream gauge values was stored.
    """
    seconds = 86400  # Default return value of 1 day in seconds

    result = session.query(func.max(StreamGaugeValues.timestamp)) \
        .filter(StreamGaugeValues.stream_gauge_id == stream_gauge_id)
    last_timestamp = None
    for row in result:
        # timestamp = row.timestamp
        timestamp = row[0]
        if timestamp is not None:
            if last_timestamp is None:
                last_timestamp = timestamp
            if timestamp > last_timestamp:
                last_timestamp = timestamp

    # Calculate the number of seconds between now and the max timestep value
    if last_timestamp is not None:
        seconds = int((datetime.datetime.now(datetime.timezone.utc) -
                       last_timestamp.replace(tzinfo=datetime.timezone.utc)).total_seconds())

    return seconds


def retrieve_stream_gauge_data(inputs):
    """
    Retrieve stream gauge data from either Trimble telogdhs or USGS.

    Args:
        inputs (argparse.ArgumentParser): Argument parser.
    """
    print('Reading stream gauge data...')

    # Loop on all of the organizations
    engine = create_engine(inputs.resource_db_url)
    connection = engine.connect()
    session = Session(connection)
    if inputs.organization_id:
        all_organizations = [session.query(AgwaOrganization).get(inputs.organization_id)]
    else:
        all_organizations = session.query(AgwaOrganization).all()
    for organization_resource in all_organizations:
        # Get the organization ID and the Trimble credentials (if there)
        organization_name = organization_resource.name
        organization_id = organization_resource.id
        trimble_unity_url = organization_resource.get_attribute('trimble_unity_url')
        trimble_telog_url = organization_resource.get_attribute('trimble_telog_url')
        trimble_tenant = organization_resource.get_attribute('trimble_tenant')
        trimble_username = organization_resource.get_attribute('trimble_username')
        trimble_password = organization_resource.get_attribute('trimble_password')
        trimble_unity_url = 'https://us.trimbleunity.com/unity' if not trimble_unity_url else trimble_unity_url
        trimble_telog_url = 'https://api.telogdhs.net' if not trimble_telog_url else trimble_telog_url

        print(f'Retrieving available stream gauge stations for organization {organization_name}:\n')

        # Loop on all of the stream gauges with this organization id
        all_resources = session.query(StreamGaugeResource) \
            .join(StreamGaugeResource.organizations) \
            .filter(AgwaOrganization.id == organization_id).all()
        for resource in all_resources:
            # Find out attributes of this stream gauge
            gauge_name = resource.name
            gauge_type = resource.get_attribute('gauge_type')
            gauge_id = resource.get_attribute('gauge_id')
            measurement_id = resource.get_attribute('measurement_id')

            try:
                # Find the number of seconds since the last value was stored
                seconds = _seconds_since_last_value(session, resource.id)

                # Retrieve the stream gauge data for the time period found
                if gauge_type == 'USGS':
                    # Read data from the USGS
                    retrieve_data_usgs(session, resource.id, gauge_id, gauge_name, seconds=seconds,
                                       verbose=inputs.verbose)
                elif gauge_type == 'Trimble' and trimble_tenant and trimble_username and trimble_password:
                    # Read data from the Trimble Telog API
                    id = retrieve_data_trimble(session, resource.id, gauge_id, gauge_name, trimble_unity_url,
                                               trimble_telog_url, trimble_tenant, trimble_username,
                                               trimble_password, measurement_name='Level',
                                               measurement_id=measurement_id, seconds=seconds, verbose=inputs.verbose)
                    if measurement_id is None:
                        # Update the measurement ID for faster queries in the future
                        resource.set_attribute('measurement_id', id)
                        session.commit()
            except Exception as e:
                print(f'WARNING: Error retrieving data for stream gauge "{gauge_name}" ({gauge_type} ID: {gauge_id}).')
                traceback.print_exc(file=sys.stderr)
                sys.stderr.write(type(e).__name__)
                sys.stderr.write(repr(e))
                continue
        print('\n\n')

    # Close the session
    session.close()


def main():
    inputs = _parse_args()
    retrieve_stream_gauge_data(inputs)


if __name__ == '__main__':
    main()
