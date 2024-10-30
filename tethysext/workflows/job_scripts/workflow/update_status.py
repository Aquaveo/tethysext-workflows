#!/opt/tethys-python
"""
********************************************************************************
* Name: update_status.py
* Author: nswain
* Created On: April 22, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import sys
import traceback
from tethysext.workflows.services.workflows.decorators import workflow_step_job


@workflow_step_job
def main(db_session, workflow, step, gs_private_url, gs_public_url,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    print('Given Arguments 2:')
    print(str(cmd_args))

    # Write out needed files
    try:
        print('Updating status...')
        job_statuses = step.get_attribute('condor_job_statuses')
        print(job_statuses)
        if step.STATUS_FAILED in job_statuses:
            step.set_status(step.ROOT_STATUS_KEY, step.STATUS_FAILED)
        else:
            step.set_status(step.ROOT_STATUS_KEY, step.STATUS_COMPLETE)

        db_session.commit()

    except Exception as e:
        if step and db_session:
            step.set_status(step.ROOT_STATUS_KEY, step.STATUS_FAILED)
            db_session.commit()
        sys.stderr.write('Error processing step {0}'.format(cmd_args.workflow_step_id))
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write(repr(e))
        sys.stderr.write(str(e))

    print('Updating Status Complete')
