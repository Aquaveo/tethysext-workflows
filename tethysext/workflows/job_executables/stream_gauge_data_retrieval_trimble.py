import requests
import datetime as datetime
from scipy.interpolate import InterpolatedUnivariateSpline

from sqlalchemy import and_, or_

from gssha_adapter.models.app_users.rating_curve import RatingCurve
from gssha_adapter.models.app_users.return_period import ReturnPeriod
from gssha_adapter.models.app_users.stream_gauge_resource import StreamGaugeResource
from gssha_adapter.models.app_users.stream_gauge_values import StreamGaugeValues


TRIMBLE_INTERVAL_LENGTH = 300  # The interval, in seconds, to download Trimble API data


def get_trimble_unity_rm_access_token(tenant, username, password, unity_rm_url='https://us.trimbleunity.com/unity'):
    """
    Gets the Trimble Unity RM access token needed to access the API.

    Args:
        tenant (str): The tenant identifier (not the organization), viewable at the bottom of the Trimble Unity menu.
        username (str): The Trimble Unity username.
        password (str): The Trimble Unity password.
        unity_rm_url (str, optional): The Trimble Unity url. Defaults to 'https://us.trimbleunity.com/unity'.

    Returns:
        str: The access token needed by the API, or None if unable to authenticate.
    """
    retries_remaining = 3
    response = None
    while retries_remaining > 0:
        try:
            token_url = unity_rm_url + '/tokens'
            body = {
                'tenant': f'{tenant}',
                'username': f'{username}',
                'password': f'{password}',
            }

            response = requests.post(
                url=token_url,
                data=body,
            )

            if response.status_code != 200:
                print(f'Problem encountered, response.status_code = {response.status_code}')
                print(response.text)
                retries_remaining -= 1
                continue
            else:
                access_token = response.text
                return access_token
        except requests.ConnectionError:
            print('Exception found')
            retries_remaining -= 1

        break
    return None


def _retrieve_trimble_values(trimble_unity_url, trimble_telog_url, tenant, username, password, site_id,
                             measurement_name, measurement_id=None, start_time=None, seconds=86400):
    """Code for fetching Trimble API.

    Args:
        trimble_unity_url (string):  url of the Trimble Unity RM API website.
        trimble_telog_url (string):  url of the Trimble Telog DHS API website.
        tenant (string):  tenant of the Trimble Unity RM API (not the organization) to log into.
        username (string):  username to log into.
        password (string):  password to log into to download from.
        site_id (int):  the site ID of the station to query.
        measurement_name (string):  the measurement type to read.  Used if the measurement ID is None.
        measurement_id (int): the measurement ID to read.
        start_time (str):  the starting time to read from, up until now.
        seconds (int):  the number of seconds to read from now.

    returns:
        list of str: List of timestamp values.
        list of float: List of average values.
        int: Measurement ID if not given.
    """
    # Get the Trimble access token necessary to read the data
    token = get_trimble_unity_rm_access_token(tenant=tenant, username=username, password=password,
                                              unity_rm_url=trimble_unity_url)

    timestamps = []
    avg_values = []
    min_values = []
    max_values = []
    trimble_str_format = '%Y-%m-%dT%H:%M:%S%z'
    if token is not None:
        # Set up the request header containing the authorization token
        request_headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }

        # If we don't have a measurement ID, read it from the name
        if measurement_id is None:
            measure_url = trimble_telog_url + f'/api/sites/{site_id}/measurements'
            response = requests.get(
                url=measure_url,
                headers=request_headers,
            )
            if response.status_code == 200:
                measurements = response.json()
                measurement_id = None
                for measurement in measurements:
                    if measurement['name'] == measurement_name:
                        measurement_id = measurement['id']

        # Use the measurement ID to read the data for the time specified
        if measurement_id is not None:
            data_url = trimble_telog_url + f'/api/measurements/{measurement_id}/data?Last={seconds}' \
                       f'&intervalLength={TRIMBLE_INTERVAL_LENGTH}'
            if start_time is not None:
                data_url = trimble_telog_url + f'/api/measurements/{measurement_id}/data?Start={start_time}' \
                           f'&intervalLength={TRIMBLE_INTERVAL_LENGTH}'
            response = requests.get(
                url=data_url,
                headers=request_headers,
            )
            if response.status_code == 200:
                data_values = response.json()
                for data_value in data_values:
                    # timestamps.append(data_value['timestamp'])
                    date_time = datetime.datetime.strptime(data_value['timestamp'], trimble_str_format)
                    date_time_utc = date_time.astimezone(datetime.timezone.utc)
                    timestamps.append(date_time_utc.strftime(trimble_str_format))
                    avg_values.append(data_value['avg'] / 12.0)  # Trimble inches -> feet conversion
                    min_values.append(data_value['min'] / 12.0)  # Trimble inches -> feet conversion
                    max_values.append(data_value['max'] / 12.0)  # Trimble inches -> feet conversion
    else:
        print('Unable to get access token')

    return timestamps, max_values, measurement_id


def _get_rating_curve(session, stream_gauge_id, timestamp):
    """
    Try and read a rating curve for the stream gauge at the time provided.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.
        timestamp (datetime): The timestamp to query.

    Returns:
        dict: The rating curve.
        datetime:  The starting date/time.
        datetime:  The ending date/time.
    """
    rating_curve = {}
    start_date = None
    end_date = None

    result = session.query(RatingCurve) \
        .filter(and_(stream_gauge_id == RatingCurve.stream_gauge_id,
                     timestamp > RatingCurve.start_date,
                     (or_(timestamp < RatingCurve.end_date, RatingCurve.end_date == None))))  # noqa: E711
    for row in result:
        rating_curve = row.rating_curve
        start_date = row.start_date
        end_date = row.end_date

    return rating_curve, start_date, end_date


def _get_stream_level_datum(session, stream_gauge_id):
    """
    Gets the stream level datum from the stream gauge resource specified by the ID passed in.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.

    Returns:
        float: The stream level dataum (if found), else 0.0
    """
    datum = 0.0

    result = session.query(StreamGaugeResource) \
        .filter(stream_gauge_id == StreamGaugeResource.id)
    for row in result:
        datum = row.get_attribute('stream_level_datum')

    return datum


def _read_return_periods(session, stream_gauge_id):
    """
    Get the raw return period information from the ReturnPeriod table for the stream gauge id passed in.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (int): The stream gauge ID to read the return period for.

    Returns:
        list of tuple: The return period information
    """
    # Read the ReturnPeriod table for this stream gauge ID
    result = session.query(ReturnPeriod) \
        .filter(ReturnPeriod.stream_gauge_id == stream_gauge_id) \
        .all()
    return_period_info = {
        f'{ReturnPeriod.COLUMN_NAMES[0]}': {},
        f'{ReturnPeriod.COLUMN_NAMES[1]}': {}
    }
    for row in result:
        return_period_info = row.return_period

    # Store the discharge and year values
    rp_info = []
    discharges = [float(value) for value in return_period_info[f'{ReturnPeriod.COLUMN_NAMES[0]}'].values()]
    years = [float(value) for value in return_period_info[f'{ReturnPeriod.COLUMN_NAMES[1]}'].values()]
    for discharge, year in zip(discharges, years):
        rp_info.append((discharge, year))
    rp_info.sort(key=lambda x: x[1])  # Sort in case out of order years

    return rp_info


def _get_return_period_from_discharge(rp_info, discharge):
    """
    Finds the return period for the dishcarge amount passed in.

    Args:
        rp_info (list of tuple): The sorted return period information, [(discharge, year), (discharge, year)...]
        discharge (float): The discharge level to look up.

    Returns:
        float: The return period in years (if found), else 0.0
    """
    return_period = 0.0
    for value in rp_info:
        if float(discharge) >= value[0]:
            return_period = value[1]

    return return_period


def _apply_rating_curve(session, stream_gauge_id, timestamps, levels):
    """
    Interpolates height/level values from a rating curve to get discharge values.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.
        timestamps (list of datetime): List of timestamp values associated with water levels.
        levels (list of float): List of water level values.

    Returns:
        list of float: The interpolated discharge values from the rating curve.
    """
    rating_start = None
    rating_end = None
    discharges = [0.0] * len(timestamps)  # Default to zero
    rating_curve = {}

    # Loop on all of the timestamp an level values
    for i, (timestamp, level) in enumerate(zip(timestamps, levels)):
        if isinstance(timestamp, str):
            if len(timestamp) > 19:
                timestamp = timestamp.rsplit('+', 1)[0]
            try:
                timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                # We tried to fix the value, but now we give up....
                continue

        # Check if we have a valid rating curve for this timestamp
        if rating_start is None or rating_end is None or timestamp < rating_start or timestamp > rating_end:
            # Try and read a new rating curve for the timestamp
            rating_curve, rating_start, rating_end = _get_rating_curve(session, stream_gauge_id, timestamp)

        # Get the stream level datum
        stream_level_datum = _get_stream_level_datum(session, stream_gauge_id)

        # Interpolate the discharge value on the rating curve if there
        if rating_curve:
            rating_discharge = list(rating_curve['discharge'].values())  # discharge
            rating_level = list(rating_curve['level'].values())  # level
            # discharges[i] = np.interp(level + stream_level_datum, rating_level, rating_discharge)
            s = InterpolatedUnivariateSpline(rating_level, rating_discharge, k=1)
            discharges[i] = float(s(level + stream_level_datum))
            discharges[i] = 0.0 if discharges[i] < 0.0 else discharges[i]

    return discharges


def retrieve_data_trimble(session, stream_gauge_id, site_id, name, trimble_unity_url, trimble_telog_url,
                          trimble_tenant, trimble_username, trimble_password,
                          measurement_name='Level', measurement_id=None, seconds=86400, verbose=False):
    """
    Retrieve stream gauge data from either Trimble telogdhs.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.
        site_id (int): The Trimble site id to retrieve data from.
        name (str): The name of the gauge.
        trimble_unity_url (str): Url of the Trimble Unity RM API (used to get the acces token).
        trimble_telog_url (str): Url of the Trimble Telog DHS API (used to store the gauge data).
        trimble_tenant (str): Tenant of the Trimble Unity RM API (not the organization).
        trimble_username (str): Username needed to access the Trimble Telog API.
        trimble_password (str): Password needed to access the Trimble Telog API.
        measurement_name (str): The name of the measurement to read, e.g. "Level".  Used if no ID given.
        measurement_id (int): The id of the meaturement to read.
        seconds (int): The number of seconds of data to read, from now.
        verbose (bool): Verbose flag for printing output.
    """
    print(f'Reading Trimble Telog data for gauge "{name}" (Site ID: {site_id})...')

    # Retrieve the data from the Trimble Telog API
    timestamps, levels, id = _retrieve_trimble_values(trimble_unity_url, trimble_telog_url, trimble_tenant,
                                                      trimble_username, trimble_password, site_id,
                                                      measurement_name, measurement_id=measurement_id, seconds=seconds)

    # Apply the rating curve to the height/level values read
    discharges = _apply_rating_curve(session, stream_gauge_id, timestamps, levels)

    # Read the return period information for this stream gauge
    rp_info = _read_return_periods(session=session, stream_gauge_id=stream_gauge_id)

    # Store the values to the stream gauge values records
    new_gauge_values = []
    for timestamp, level, discharge in zip(timestamps, levels, discharges):
        return_period = _get_return_period_from_discharge(rp_info, discharge)
        new_value = StreamGaugeValues(stream_gauge_id=stream_gauge_id, timestamp=timestamp, level=level,
                                      discharge=discharge, return_period=return_period)
        new_gauge_values.append(new_value)
    session.add_all(new_gauge_values)
    session.commit()

    if verbose and new_gauge_values:
        print('{0:30s}{1:25s}{2:25s}'.format("Timestamp", "Level", "Discharge"))
        for timestamp, level, discharge in zip(timestamps, levels, discharges):
            print(f'{timestamp : <30}{level : <25}{discharge : <25}')
        print('\n')

    # Return the measurement ID for updating if necessary
    return id
