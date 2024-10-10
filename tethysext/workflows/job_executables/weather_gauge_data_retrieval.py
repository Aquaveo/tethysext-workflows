#!/opt/tethys-python
import argparse
import datetime
import hashlib
import hmac
import json
import os
import requests
import traceback

from sqlalchemy import and_
from sqlalchemy.engine import create_engine
from sqlalchemy.orm.session import Session

from gssha_adapter.models.app_users.weather_gauge_resource import WeatherGaugeResource
from gssha_adapter.models.app_users.weather_gauge_values import WeatherGaugeValues
from gssha_adapter.models.app_users import AgwaOrganization


WEATHERLINK_API_URL = 'https://api.weatherlink.com/v2'


def _parse_args():
    """
    Parses and validates command line arguments for weather gauge data retrieval.

    Returns:
        argparse.Namespace: The parsed and validated arguments.
    """
    parser = argparse.ArgumentParser(description='A script to retrieve weather gauge data')
    parser.add_argument('resource_db_url', type=str, help='The sqlalchemy URL format for the database '
                        'connection (e.g. postgresql://user:pass@host:port/database)')
    parser.add_argument('-o', '--organization_id', type=str,
                        help='The organization ID for the gauges to retrieve data for')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-s', '--stations', action='store_true',
                        help='Get a list of available weather stations only (no gauge data retrieval)')
    args = parser.parse_args()

    return args


def _compute_weatherlink_api_signature(access_token, app_secret):
    """
    Computes the Weatherlink API signature using the API Secret and parameters to hash.

    Args:
        access_token (str): The message to hash.
        app_secret (str): The HMAC secret key.
    """
    digest = hmac.new(bytes(app_secret, 'UTF-8'),
                      bytes(access_token, 'UTF-8'),
                      hashlib.sha256)
    return digest.hexdigest()


def _datetime_precip_accum_of_last_value(session, weather_gauge_id):
    """
    Gets the datetime and cumulative flow accumulation of the last weather gauge value.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        weather_gauge_id (uuid): UUID of the weather gauge.

    Returns:
        datetime.datetime: the date time of the last stored value of this weather gauge.
    """
    # Set the default time to be 1 day ago
    last_timestamp = None
    yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=86400)
    last_precip_accum = None

    # Query the WeatherGaugeValues table for the last timestamp value and the corresponding flow accumulation
    result = session.query(WeatherGaugeValues) \
        .filter(WeatherGaugeValues.weather_gauge_id == weather_gauge_id) \
        .order_by(WeatherGaugeValues.timestamp.desc()) \
        .first()
    if result:
        last_timestamp = result.timestamp
        last_precip_accum = result.precip_accum

    # Get the last datetime (if there) or the default value (1 day ago)
    timestamp = last_timestamp.replace(tzinfo=datetime.timezone.utc) if last_timestamp else yesterday
    precip_accum = last_precip_accum if last_precip_accum is not None else 0.0
    return timestamp, precip_accum


def _get_all_station_ids(api_key, app_secret, verbose, date_time=None):
    """
    Gets list of available station ids for the API credentials and time given.

    Uses the following url:
    https://api.weatherlink.com/v2/stations?api-key={api_key}&t={time}&api-signature={api_signature}

    Args:
        api_key (str): The WeatherLink v2 API Key.
        app_secret (str): The WeatherLink v2 API Secret.
        verbose (bool): Flag for printing verbose data about the stations read.
        date_time (datetime.datetime, optional): Timestamp to query from.  Defaults to datetime.datetime.now(UTC).

    Returns:
        list of tuple: The station ID's, names, and locations available for this API key at the date specified.
    """
    date_time = datetime.datetime.now() if date_time is None else date_time
    station_ids = []

    # Compute the API signature
    message = f'api-key{api_key}t{int(date_time.timestamp())}'
    api_signature = _compute_weatherlink_api_signature(message, app_secret)

    # Set up the request header and url
    request_headers = {
        'Accept': 'application/json',
    }
    stations_url = WEATHERLINK_API_URL + \
        f'/stations?api-key={api_key}&t={int(date_time.timestamp())}&api-signature={api_signature}'

    # Get the response from the url
    response = requests.get(
        url=stations_url,
        headers=request_headers,
    )

    if response.status_code == 200:
        json_data = response.json()

        if verbose:
            print(f'Raw station data:\n{json_data}\n')
        if 'stations' in json_data:
            for station in json_data['stations']:
                station_ids.append((station['station_id'],
                                    station['station_name'],
                                    station['latitude'],
                                    station['longitude']))

    return station_ids


def _calculate_return_period(accumulation, quantiles, interval=5):
    """
    Calculates the return period for the rainfall accumulation data and PF quantiles.

    Args:
        accumulation (list of float): list of rainfall accumulation values at equal minute (usually 5) intervals.
        quantiles (dict): Dictionary of point Precipitation Frequency estimates from NOAA 14 Atlas.
        interval (int): Interval in minutes in between accumulation values.  Defaults to 5.

    Returns:
        int: the return period (in years)
    """
    calculated_return_period = 1
    recurrence_intervals = [1, 2, 5, 10, 25, 50, 100, 200, 500, 1000]
    durations = [5, 10, 15, 30, 60]

    # Skip calculation if quantiles not read
    if not quantiles:
        print('No point precipitation frequency data found, skipping return period calculation')
        return calculated_return_period

    for j, minute in enumerate(durations):
        # Skip calculation if the current duration being calculated is less than the interval
        if interval >= minute:
            rain_intervals = []
            for i in range(int(minute / interval), len(accumulation)):
                rain_intervals.append(accumulation[i] - accumulation[i - int(minute / interval)])
            if rain_intervals:
                max_interval = max(rain_intervals)
                lookup = quantiles[j]
                cur_year = 0
                for i, cur_pf in enumerate(lookup):
                    cur_year = recurrence_intervals[i] if max_interval > cur_pf else cur_year
                calculated_return_period = max(calculated_return_period, cur_year)

    return calculated_return_period


def _cardinal_direction_from_degrees(degrees):
    """
    Converts the degree direction into a cardinal direction string.

    Args:
        degrees (float): Degree direction

    Returns:
        str: the cardinal direction, e.g. "N", "NE", etc.
    """
    if degrees is None:
        return None

    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int(round(degrees / (360.0 / len(directions))))
    return directions[idx % len(directions)]


def get_sensor_data(session, weather_gauge_id, api_key, app_secret, station_id,
                    quantiles_pf, date_start=None, date_end=None, last_accumulation=0.0):
    """
    Gets sensor data for a particular station ID.

    Args:
        session (sqlalchemy.orm.session.Session): The sqlalchemy session.
        weather_gauge_id (uuid): UUID of the stream gauge associated with the data to retrieve.
        api_key (str): The WeatherLink v2 API Key.
        app_secret (str): The WeatherLink v2 API Secret.
        station_id (int): The ID of the station to read.
        quantiles_pf (list of list of float): The PF estimates for this location.
        date_start (datetime.datetime): The starting date to read data, None if only last date is read.
        date_end (datetime.datetime): The starting date to read data.
        last_accumulation (float): The last precip accumulation value read.

    Returns:
        list of dict: List of dictionaries for each sensor at the station.
        int: The return period calculated
        float: The last cumulative precip accumulation value calculated.
    """
    response = None
    request_headers = {
        'Accept': 'application/json',
    }
    now_time = int(datetime.datetime.now().timestamp())

    # Compute the API signature and get the url for the request
    if date_start is None:
        # Grab the current/last date only
        message = f'api-key{api_key}station-id{station_id}t{now_time}'
        api_signature = _compute_weatherlink_api_signature(message, app_secret)

        # Set up the request url
        sensors_url = WEATHERLINK_API_URL + \
            f'/current/{station_id}?api-key={api_key}&t={now_time}&api-signature={api_signature}'
    else:
        # Grab a historic range of data
        start_time = int(date_start.timestamp())
        end_time = int(date_end.timestamp())
        message = f'api-key{api_key}end-timestamp{end_time}start-timestamp{start_time}station-id{station_id}t{now_time}'
        api_signature = _compute_weatherlink_api_signature(message, app_secret)

        # Set up the request url
        sensors_url = WEATHERLINK_API_URL + \
            f'/historic/{station_id}?api-key={api_key}&t={now_time}&start-timestamp={start_time}' + \
            f'&end-timestamp={end_time}&api-signature={api_signature}'

    # Get the response from the sensors url
    response = requests.get(
        url=sensors_url,
        headers=request_headers,
    )

    # Get the sensors data if got a correct response
    sensor_data = []
    if response and response.status_code == 200:
        json_data = response.json()
        if 'sensors' in json_data:
            sensor_data = json_data['sensors']
    elif response:
        print(f"Unable to download weather gauge data.  Response status code: {response.status_code}")
    else:
        print("Unable to download weather gauge data.")

    # Parse the weather data from each sensor and timestamp
    weather_data = {}
    for sensor in sensor_data:
        for i, value in enumerate(sensor['data']):
            # Initialize values for new timestamp
            if i not in weather_data:
                weather_data[i] = {
                    'timestamp': None,  # DateTime:  date and time value recorded
                    'timestamp_local': None,  # DateTime:  date and time value recorded, local to the sensor
                    'temperature': None,  # Float:  temperature in °F
                    'dew_point': None,  # Float:  dew point temperature in °F
                    'humidity': None,  # Integer:  percent humidity (0-100)
                    'wind': None,  # String:  wind direction (e.g. SE)
                    'speed': None,  # Float:  wind speed in mph
                    'gust': None,  # Float:  wind gust in mph
                    'pressure': None,  # Float:  barometric pressure in inches
                    'precip_rate': None,  # Float:  precip rate in inches
                    'precip_accum': None,  # Float:  accumulated precipitation in inches
                    'uv': None,  # Integer:  uv index
                    'solar': None,  # Float:  solar radiation in watts/sq. meter
                    'return_period': None,  # String:  return period of rainfall event
                }

            # Read and store values from the sensor at this value
            if 'ts' in value and 'rainfall_in' in value and value['ts'] is not None:
                # Just keep track of the timestamp associated with the rainfall data
                # Store as UTC time
                weather_data[i]['timestamp'] = datetime.datetime.fromtimestamp(value['ts'], tz=datetime.timezone.utc)
                weather_data[i]['timestamp_local'] = datetime.datetime.fromtimestamp(value['ts'])
            if 'temp_avg' in value and value['temp_avg'] is not None:
                weather_data[i]['temperature'] = value['temp_avg']
            elif 'temp_out' in value and value['temp_out'] is not None:
                weather_data[i]['temperature'] = value['temp_out']
            if 'dew_point_last' in value and value['dew_point_last'] is not None:
                weather_data[i]['dew_point'] = value['dew_point_last']
            elif 'dew_point_out' in value and value['dew_point_out'] is not None:
                weather_data[i]['dew_point'] = value['dew_point_out']
            if 'hum_last' in value and value['hum_last'] is not None:
                weather_data[i]['humidity'] = value['hum_last']
            elif 'hum_out' in value and value['hum_out'] is not None:
                weather_data[i]['humidity'] = value['hum_out']
            if 'wind_dir_of_prevail' in value and value['wind_dir_of_prevail'] is not None:
                weather_data[i]['wind'] = _cardinal_direction_from_degrees(value['wind_dir_of_prevail'])
            if 'wind_speed_avg' in value and value['wind_speed_avg'] is not None:
                weather_data[i]['speed'] = value['wind_speed_avg']
            if 'wind_speed_hi' in value and value['wind_speed_hi'] is not None:
                weather_data[i]['gust'] = value['wind_speed_hi']
            if 'bar_sea_level' in value and value['bar_sea_level'] is not None:
                weather_data[i]['pressure'] = value['bar_sea_level']
            elif 'bar' in value and value['bar'] is not None:
                weather_data[i]['pressure'] = value['bar']
            if 'rain_rate_hi_in' in value and value['rain_rate_hi_in'] is not None:
                weather_data[i]['precip_rate'] = value['rain_rate_hi_in']
            if 'rainfall_in' in value and value['rainfall_in'] is not None:
                weather_data[i]['precip_accum'] = value['rainfall_in']
            if 'uv_index_avg' in value and value['uv_index_avg'] is not None:
                weather_data[i]['uv'] = value['uv_index_avg']
            if 'solar_rad_avg' in value and value['solar_rad_avg'] is not None:
                weather_data[i]['solar'] = value['solar_rad_avg']

    # Convert raw rainfall data (rainfall_in) just read to accumulation
    rp_accumulation = 0.0
    return_accumulation = []
    calc_ts = []
    local_day = None
    for key in weather_data:
        # Make sure we only get duplicate timestamps
        cur_ts_val = weather_data[key]['timestamp']
        cur_precip_accum = weather_data[key]['precip_accum']
        if isinstance(cur_ts_val, datetime.datetime) and cur_ts_val not in calc_ts:
            if isinstance(weather_data[key]['timestamp_local'], datetime.datetime):
                # Handle cumulative accumulation values for the plot/database
                # Cumulative accumulation will reset on a new day (local to the sensor)
                if local_day is None:
                    local_day = weather_data[key]['timestamp_local'].day
                # Check if the local day has change for the sensor
                if local_day != weather_data[key]['timestamp_local'].day:
                    # Reset cumulative accumulation for a new day (local to the sensor) and update the day
                    last_accumulation = 0.0
                    local_day = weather_data[key]['timestamp_local'].day
            if isinstance(cur_precip_accum, float) or isinstance(cur_precip_accum, int):
                cur_accum = weather_data[key]['precip_accum']
                # Handle cumulative plot/database accumulation values:
                last_accumulation += cur_accum
                weather_data[key]['precip_accum'] = last_accumulation

                # Handle accumulation values for return period calculation (return period calculation can cross days):
                rp_accumulation += cur_accum
                return_accumulation.append(rp_accumulation)
            if isinstance(weather_data[key]['timestamp'], datetime.datetime):
                # Store the UTC timestamp for calculation
                calc_ts.append(weather_data[key]['timestamp'])

    # Compute the return period from the accumulation read
    increment = 5 if len(calc_ts) <= 1 else ((calc_ts[-1] - calc_ts[-2]).seconds // 60) % 60
    if increment != 5:
        print(f'Warning:  For gauge {weather_gauge_id}, id {id}, the differnce in time values is:  {increment}')
    return_period = _calculate_return_period(accumulation=return_accumulation, quantiles=quantiles_pf,
                                             interval=increment)

    # Create new weather gauge values for the data read
    new_gauge_values = []
    for key in weather_data:
        # Check if this time exists already.... if it does, don't add it
        result = session.query(WeatherGaugeValues) \
            .filter(and_(WeatherGaugeValues.weather_gauge_id == weather_gauge_id,
                         WeatherGaugeValues.timestamp == weather_data[key]['timestamp'])) \
            .first()
        if not result:
            # Timestamp doesn't already exist for this gauge, so create a value and store it
            new_value = WeatherGaugeValues(
                weather_gauge_id=weather_gauge_id,
                timestamp=weather_data[key]['timestamp'],
                temperature=weather_data[key]['temperature'],
                dew_point=weather_data[key]['dew_point'],
                humidity=weather_data[key]['humidity'],
                wind=weather_data[key]['wind'],
                speed=weather_data[key]['speed'],
                gust=weather_data[key]['gust'],
                pressure=weather_data[key]['pressure'],
                precip_rate=weather_data[key]['precip_rate'],
                precip_accum=weather_data[key]['precip_accum'],
                uv=weather_data[key]['uv'],
                solar=weather_data[key]['solar'],
                return_period=return_period,
            )
            new_gauge_values.append(new_value)

    # Add weather gauge values and commit if found
    if len(new_gauge_values):
        session.add_all(new_gauge_values)
        session.commit()

    # Return sensor data (or empty list if nothing read)
    return sensor_data, return_period, last_accumulation


def _get_pf_from_response_text(response_text):
    """
    Gets the quantiles, upper, and lower as lists from the NOAA Atlas 14 response text.

    Args:
        response_text (str): NOAA Atlas 14 response text.

    Returns:
        list of list of float: the quantiles values.
        list of list of float: the confidence interval upper values.
        list of list of float: the confidence interval lower values.
    """
    # Format response text into JSON friendly text
    noaa_text = response_text
    noaa_text = noaa_text.replace('\n', '')
    noaa_text = '{' + noaa_text + '}'
    noaa_text = noaa_text.replace("result = ", "'result': ")
    noaa_text = noaa_text.replace("quantiles = ", "'quantiles': ")
    noaa_text = noaa_text.replace("upper = ", "'upper': ")
    noaa_text = noaa_text.replace("lower = ", "'lower': ")
    noaa_text = noaa_text.replace("file = ", "'file': ")
    noaa_text = noaa_text.replace("lat = ", "'lat': ")
    noaa_text = noaa_text.replace("lon = ", "'lon': ")
    noaa_text = noaa_text.replace("datatype = ", "'datatype': ")
    noaa_text = noaa_text.replace("type = ", "'type': ")
    noaa_text = noaa_text.replace("ser = ", "'ser': ")
    noaa_text = noaa_text.replace("unit = ", "'unit': ")
    noaa_text = noaa_text.replace("region = ", "'region': ")
    noaa_text = noaa_text.replace("reg = ", "'reg': ")
    noaa_text = noaa_text.replace("volume = ", "'volume': ")
    noaa_text = noaa_text.replace("version = ", "'version': ")
    noaa_text = noaa_text.replace("authors = ", "'authors': ")
    noaa_text = noaa_text.replace("pyRunTime = ", "'pyRunTime': ")
    noaa_text = noaa_text.replace(";", ",")
    noaa_text = noaa_text.replace("'", '"')
    noaa_text = noaa_text.replace(",}", '}')

    # Load the string as JSON, and convert the string PF numbers to float
    noaa_json = json.loads(noaa_text)
    l_quantiles = [list(map(float, i)) for i in noaa_json['quantiles']]
    l_upper = [list(map(float, i)) for i in noaa_json['upper']]
    l_lower = [list(map(float, i)) for i in noaa_json['lower']]

    return l_quantiles, l_lower, l_upper


def _get_noaa_atlas_14_pf_estimates(latitude, longitude):
    """
    Gets the NOAA Atlas 14 Point Precipitation Frequency (PF) Estimates.

    Args:
        latitude (float): Latitude of the site to read estimates from.
        longitude (float): Longitude of the site to read estimates from.

    Returns:
        list of list of float: the quantiles values.
        list of list of float: the confidence interval upper values.
        list of list of float: the confidence interval lower values.
    """
    import gssha_adapter
    # Set up request to download the NOAA Atlas 14 PF estimates
    data_type = 'depth'
    # data_type = 'intensity'
    intensity_url = 'https://hdsc.nws.noaa.gov/cgi-bin/hdsc/new/cgi_readH5.py?' + \
        f'lat={latitude}&lon={longitude}&type=pf&data={data_type}&units=english&series=pds'
    request_headers = {
        'Accept': 'application/json',
    }
    # Base64 encoded ASCII certificate chain needed to access NOAA 14 data:
    request_cert = os.path.join(os.path.dirname(os.path.abspath(gssha_adapter.__file__)), 'resources', 'certs',
                                'hdsc.nws.noaa.gov.pem')
    response = requests.get(
        url=intensity_url,
        headers=request_headers,
        verify=request_cert,  # Verify using the certificate chain file
    )

    # Convert the NOAA Atlas 14 text into Precipitation Frequency (PF) estimates
    if response.status_code == 200:
        return _get_pf_from_response_text(response.text)

    return [], [], []


def get_available_station_information(inputs):
    """
    Retrieves available station information for each organization, such as gauge ID, name, location, etc.

    Args:
        inputs (argparse.ArgumentParser): Argument parser.
    """
    print('Reading available weather gauge stations...')

    # Loop on all of the organizations
    engine = create_engine(inputs.resource_db_url)
    connection = engine.connect()
    session = Session(connection)
    if inputs.organization_id:
        all_organizations = [session.query(AgwaOrganization).get(inputs.organization_id)]
    else:
        all_organizations = session.query(AgwaOrganization).all()
    for organization_resource in all_organizations:
        # Get the organization ID and the WeatherLink credentials (if there)
        organization_name = organization_resource.name
        wl_apikey = organization_resource.get_attribute('weatherlink_apikey')
        wl_apisecret = organization_resource.get_attribute('weatherlink_apisecret')

        # Check for the credentials, and only attempt to read data if found
        if wl_apikey and wl_apisecret:
            print(f'Retrieving available weather gauge stations for organization {organization_name}:\n')

            station_info = _get_all_station_ids(wl_apikey, wl_apisecret, inputs.verbose)
            print('{0:10s}{1:30s}{2:12s}{3:12s}'.format("ID", "Name", "Latitude", "Longitude"))
            for station in station_info:
                print(f'{station[0] : <10}{station[1] : <30}{station[2] : <12}{station[3] : <12}')
            print('\n')
    session.close()


def retrieve_weather_gauge_data(inputs):
    """
    Retrieve weather gauge data from WeatherLink and NOAA.

    Args:
        inputs (argparse.ArgumentParser): Argument parser.
    """
    print('Reading weather gauge data...')

    # Loop on all of the organizations
    engine = create_engine(inputs.resource_db_url)
    connection = engine.connect()
    session = Session(connection)
    if inputs.organization_id:
        all_organizations = [session.query(AgwaOrganization).get(inputs.organization_id)]
    else:
        all_organizations = session.query(AgwaOrganization).all()
    for organization_resource in all_organizations:
        # Get the organization ID and the WeatherLink credentials (if there)
        organization_name = organization_resource.name
        organization_id = organization_resource.id
        wl_apikey = organization_resource.get_attribute('weatherlink_apikey')
        wl_apisecret = organization_resource.get_attribute('weatherlink_apisecret')

        # Check for the credentials, and only attempt to read data if found
        if wl_apikey and wl_apisecret:
            print(f'Retrieving weather gauge data for organization {organization_name}:\n')

            # Get the weather gauge resources associated with this organization id
            all_resources = session.query(WeatherGaugeResource) \
                .join(WeatherGaugeResource.organizations) \
                .filter(AgwaOrganization.id == organization_id).all()
            for resource in all_resources:
                # Find out attributes of this weather gauge
                gauge_name = resource.name
                gauge_id = resource.get_attribute('gauge_id')

                try:
                    # Find the number of seconds since the last value was stored
                    start_time, precip_accum = _datetime_precip_accum_of_last_value(session, resource.id)
                    end_time = utc_now = datetime.datetime.now(datetime.timezone.utc)
                    read_gauge = True
                    if end_time - start_time > datetime.timedelta(seconds=86400):
                        end_time = start_time + datetime.timedelta(seconds=86400)

                    if gauge_id:
                        print(f'Reading data for gauge "{gauge_name}" (WeatherLink ID: {gauge_id})...')
                        # Retrieve the NOAA Atlas 14 Precipitation Frequency (PF) Estimates
                        quantiles_pf = []
                        try:
                            location_json = json.loads(resource.get_location('geojson'))
                            if location_json and 'coordinates' in location_json:
                                print('Reading NOAA Atlas 14 PF data...')
                                longitude_value = location_json['coordinates'][0]
                                latitude_value = location_json['coordinates'][1]
                                quantiles_pf, _, _ = _get_noaa_atlas_14_pf_estimates(longitude=longitude_value,
                                                                                     latitude=latitude_value)
                        except requests.exceptions.SSLError:
                            quantiles_pf = []
                            print('SSL Error reading NOAA 14 PF estimates')
                        except json.decoder.JSONDecodeError:
                            quantiles_pf = []
                            print('JSON Error reading location from gauge')
                        except Exception as e:
                            quantiles_pf = []
                            print(f'Unexpected error reading NOAA 14 PF data from gauge: {e}')
                            traceback.print_exc()

                        # Retrieve the WeatherLink weather gauge sensor data for the date time found
                        while read_gauge:
                            sensor_data, return_period, precip_accum = get_sensor_data(session, resource.id, wl_apikey,
                                                                                       wl_apisecret, gauge_id,
                                                                                       quantiles_pf, start_time,
                                                                                       end_time, precip_accum)
                            if inputs.verbose:
                                # Optional verbose data output
                                print(f'Sensor data:\t{sensor_data}')
                                print(f'Return period:\t{return_period}')
                            start_time = end_time
                            end_time = start_time + datetime.timedelta(seconds=86400)
                            if start_time >= utc_now:
                                read_gauge = False
                except Exception:
                    print(f'WARNING: Error retrieving data for weather gauge "{gauge_name}" '
                          f'(WeatherLink ID: {gauge_id})')
                    print(traceback.format_exc())
                    continue

    # Close the session
    session.close()


def main():
    inputs = _parse_args()
    if inputs.stations:
        # Option to just print out information about the weather gauges available
        get_available_station_information(inputs)
    else:
        # Option to download weather gauge values
        retrieve_weather_gauge_data(inputs)


if __name__ == '__main__':
    main()
