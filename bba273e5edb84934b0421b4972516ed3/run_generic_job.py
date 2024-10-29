#!/opt/tethys-python
"""
********************************************************************************
* Name: run_generic_job.py
* Author: nswain
* Created On: December 28, 2023
* Copyright: (c) Aquaveo 2023
********************************************************************************
"""
import json
from pprint import pprint

from tethysext.workflows.services.workflows.decorators import workflow_step_job


@workflow_step_job
def main(
    db_session, workflow, step, gs_private_url, gs_public_url,
    workflow_class, params_json, params_file, cmd_args, extra_args
):
    # Extract extra args
    point_name = extra_args[0]
    pow = int(extra_args[1]) + 1
    output_filename = extra_args[2]

    print(f'Running job for point: {point_name}')
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [i**pow for i in x]
    series = {
        'name': point_name,
        'x': x,
        'y': y,
    }

    print('Results:')
    pprint(series, compact=True)

    # Save to file
    print('Saving File... ')
    with open(output_filename, 'w') as f:
        f.write(json.dumps(series))

    print('Saved file Successfully')
