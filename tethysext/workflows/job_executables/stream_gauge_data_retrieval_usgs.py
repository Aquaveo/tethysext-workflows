import datetime
import numpy as np
import pandas as pd
import requests
from scipy.interpolate import interp1d

from sqlalchemy import and_, or_

from gssha_adapter.models.app_users.rating_curve import RatingCurve
from gssha_adapter.models.app_users.return_period import ReturnPeriod
from gssha_adapter.models.app_users.stream_gauge_values import StreamGaugeValues


def _retrieve_usgs_values(site_id, seconds=86400):
    """
    Code for fetching USGS data.

    Args:
        site_id (int): ID of the station to read
        seconds (int, optional): Number of seconds to read from now. Defaults to 86400.

    returns:
        list of str: List of timestamp values
        list of float: List of average values
    """
    levels_timestamps = []
    levels = []
    discharges_timestamps = []
    discharges = []
    usgs_str_format = '%Y-%m-%dT%H:%M:%S.%f%z'

    # JSON version:
    json_url = 'https://waterservices.usgs.gov/nwis/iv/?format=json'
    json_url += f'&sites={str(site_id).zfill(8)}'
    json_url += f'&period=PT{seconds}S'
    json_url += '&parameterCd=00060,00065&siteType=ST&siteStatus=all'
    request_headers = {
        'Accept': 'application/json',
    }
    response = requests.get(
        url=json_url,
        headers=request_headers,
    )

    if response.status_code == 200:
        json_data = response.json()

        water_levels = None
        water_flow = None
        for i, usgs_var in enumerate(json_data['value']['timeSeries']):
            if usgs_var['variable']['variableCode'][0]['variableID'] == 45807202:
                water_levels = i
            if usgs_var['variable']['variableCode'][0]['variableID'] == 45807197:
                water_flow = i

        # Water level
        if water_levels is not None:
            for data_val in json_data['value']['timeSeries'][water_levels]['values'][0]['value']:
                # Get the datetime and level value
                dt_str = data_val['dateTime']
                dt_str = dt_str[0:-3] + dt_str[-2:] if dt_str[-3] == ':' else dt_str  # Remove ':' in timezone if there
                date_time = datetime.datetime.strptime(dt_str, usgs_str_format)
                date_time_utc = date_time.astimezone(datetime.timezone.utc)
                levels_timestamps.append(date_time_utc.strftime(usgs_str_format))
                levels.append(data_val['value'])
        # Water discharge
        if water_flow is not None:
            for data_val in json_data['value']['timeSeries'][water_flow]['values'][0]['value']:
                # Get the datetime and discharge value
                dt_str = data_val['dateTime']
                dt_str = dt_str[0:-3] + dt_str[-2:] if dt_str[-3] == ':' else dt_str  # Remove ':' in timezone if there
                date_time = datetime.datetime.strptime(dt_str, usgs_str_format)
                date_time_utc = date_time.astimezone(datetime.timezone.utc)
                discharges_timestamps.append(date_time_utc.strftime(usgs_str_format))
                discharges.append(data_val['value'])

    levels = np.float_(levels).tolist()
    discharges = np.float_(discharges).tolist()
    return levels_timestamps, levels, discharges_timestamps, discharges


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
        # Check if we have a valid rating curve for this timestamp
        if rating_start is None or rating_end is None or timestamp < rating_start or timestamp > rating_end:
            # Try and read a new rating curve for the timestamp
            rating_curve, rating_start, rating_end = _get_rating_curve(session, stream_gauge_id, timestamp)

        # Interpolate the discharge value on the rating curve if there
        if rating_curve:
            temp_levels = [i for i in rating_curve['level'].values()]
            temp_discharges = [i for i in rating_curve['discharge'].values()]
            i1d = interp1d(temp_levels, temp_discharges, kind='quadratic', fill_value='extrapolate')
            discharges[i] = float(i1d(float(level)))

    return discharges


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
        if discharge is not None and float(discharge) >= value[0]:
            return_period = value[1]

    return return_period


def retrieve_data_usgs(session, stream_gauge_id, usgs_number, name, seconds=86400, verbose=False):
    """
    Retrieve and store stream gauge data from the USGS.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        stream_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.
        usgs_number (int): The USGS stream gauge number.
        name (str): Name of the stream gauge.
        seconds (int): The number of seconds of data to read, from now.
        verbose (bool): Verbose flag for printing output.
    """
    print(f'Reading USGS data for gauge "{name}" (USGS ID: {usgs_number})...')

    # Retrieve the data from the USGS API
    levels_timestamps, levels, discharges_timestamps, discharges = _retrieve_usgs_values(usgs_number, seconds=seconds)

    # Apply the rating curve to the height/level values read (if necessary)
    if len(discharges) == 0:
        discharges = _apply_rating_curve(session, stream_gauge_id, levels_timestamps, levels)

    # Read the return period information for this stream gauge
    rp_info = _read_return_periods(session=session, stream_gauge_id=stream_gauge_id)

    # Clean up data, where the levels and discharges are not equal in length
    if len(levels) != len(discharges):
        # Put level and discharge time & values in a dataframe
        df_levels = pd.DataFrame({'dt': levels_timestamps, 'levels': levels})
        df_discharges = pd.DataFrame({'dt': discharges_timestamps, 'discharges': discharges})
        # Merge the dataframes, with outer, which will result in NaN empty areas where data is missing
        df_merge = pd.merge(df_levels, df_discharges, how='outer').sort_values('dt')  # Merge the dataframes
        df_clean = df_merge.where(pd.notnull(df_merge), None)  # Change NaN values to None
        # Put back into lists for processing below
        levels_timestamps = df_clean['dt'].tolist()
        levels = df_clean['levels'].tolist()
        discharges = df_clean['discharges'].tolist()

    # Store the values to the stream gauge values records
    new_gauge_values = []
    for timestamp, level, discharge in zip(levels_timestamps, levels, discharges):
        return_period = _get_return_period_from_discharge(rp_info, discharge)
        new_value = StreamGaugeValues(stream_gauge_id=stream_gauge_id, timestamp=timestamp, level=level,
                                      discharge=discharge, return_period=return_period)
        new_gauge_values.append(new_value)
    session.add_all(new_gauge_values)
    session.commit()

    if verbose and new_gauge_values:
        print('{0:35s}{1:15s}{2:15s}'.format("Timestamp", "Level", "Discharge"))
        for timestamp, level, discharge in zip(levels_timestamps, levels, discharges):
            level = '' if level is None else level  # Format in case level is None
            discharge = '' if discharge is None else discharge  # Format in case discharge is None
            print(f'{timestamp : <35}{level : <15}{discharge : <15}')
        print('\n')
