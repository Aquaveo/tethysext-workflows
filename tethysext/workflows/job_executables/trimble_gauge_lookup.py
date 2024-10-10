#!/opt/tethys-python
import argparse
import requests

from tethysapp.agwa.job_executables.stream_gauge_data_retrieval_trimble import get_trimble_unity_rm_access_token


def _parse_args():
    """
    Parses and validates command line arguments for stream gauge data retrieval.

    Returns:
        argparse.Namespace: The parsed and validated arguments.
    """
    parser = argparse.ArgumentParser(description='A script to retrieve the site ID and location of a Trimble gauge')
    parser.add_argument('trimble_tenant', type=str,
                        help='Tenant of the Trimble Unity RM API storing the data (not the organization)')
    parser.add_argument('trimble_username', type=str, help='Username of the Trimble Unity RM API storing the data')
    parser.add_argument('trimble_password', type=str, help='Password of the Trimble Unity RM API storing the data')
    parser.add_argument('site_names', type=str, nargs='+', help='Name(s) of the Trimble Unity RM site to look up')
    parser.add_argument('-u', '--unity_rm_url', type=str,
                        help='URL of the Trimble Unity RM API (default: https://us.trimbleunity.com/unity)',
                        default='https://us.trimbleunity.com/unity')
    parser.add_argument('-t', '--telog_url', type=str,
                        help='URL of the Trimble Telog DHS API storing the data (default: https://api.telogdhs.net)',
                        default='https://api.telogdhs.net')
    args = parser.parse_args()

    return args


def site_id_lookup(tenant, username, password, site_names, unity_rm_url='https://us.trimbleunity.com/unity',
                   telog_url='https://api.telogdhs.net'):
    """
    A utility to lookup and find the site ID value of a Trimble Unity gauge based on its name.

    Args:
        tenant (str): The tenant identifier (not the organization), viewable at the bottom of the Trimble Unity menu.
        username (str): The Trimble Unity username.
        password (str): The Trimble Unity password.
        site_names (list of str): The names of the sites to look up.
        unity_rm_url (str): The Trimble Unity RM url. Defaults to 'https://us.trimbleunity.com/unity'.
        telog_url (str): The Trimble Telog url. Defaults to 'https://api.telogdhs.net'.

    Returns:
        dict: Dictionary of names and site_ids, else None
    """
    site_ids_found = {}
    token = get_trimble_unity_rm_access_token(tenant=tenant, username=username, password=password,
                                              unity_rm_url=unity_rm_url)
    if token is not None:
        for name in site_names:
            url = telog_url + f'/api/sites?name={name}'
            request_headers = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}'
            }

            response = requests.get(
                url=url,
                headers=request_headers,
            )

            if response.status_code != 200:
                print(f'Site ID Problem encountered, response.status_code = {response.status_code}')
                print(response.text)
            else:
                response_json = response.json()
                if len(response_json) > 0:
                    site_id = response_json[0]['id']
                    x = response_json[0]['x']
                    y = response_json[0]['y']
                    z = response_json[0]['z']
                    print(f'NAME = {name}\t\tID = {site_id}\t\tXYZ = ({x}, {y}, {z})')
                    site_ids_found[name] = site_id
                else:
                    print(f'NAME = {name}\t\tID = Not found')

    return site_ids_found


def main():
    inputs = _parse_args()
    site_id_lookup(inputs.trimble_tenant, inputs.trimble_username, inputs.trimble_password, inputs.site_names,
                   inputs.unity_rm_url, inputs.telog_url)


if __name__ == '__main__':
    main()
