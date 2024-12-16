import argparse


def set_step_status(db_session, step, status):
    """
    Sets the status on the provided step to the provided status.
    Args:
        db_session(sqlalchemy.orm.Session): Session bound to the step.
        step(Step): The step to modify
        status(str): The status to set.
    """
    db_session.refresh(step)
    step_statuses = step.get_attribute('condor_job_statuses')
    step_statuses.append(status)
    step.set_attribute('condor_job_statuses', step_statuses)
    db_session.commit()


def  parse_workflow_step_args():
    """
    Parses and validates command line arguments for workflow_step_job.
    Returns:
        argparse.Namespace: The parsed and validated arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'db_url',
        help='SQLAlchemy URL to the database containing the Workflow data.'
    )
    parser.add_argument(
        'workflow_id',
        help='ID of the TethysWorkflow this job is associated with.'
    )
    parser.add_argument(
        'workflow_step_id',
        help='ID of the Step this job is associated with.'
    )
    parser.add_argument(
        'gs_private_url',
        help='Private url to GeoServer.'
    )
    parser.add_argument(
        'gs_public_url',
        help='Public url to GeoServer.'
    )
    parser.add_argument(
        'workflow_class',
        help='Dot path to workflow class.'
    )
    parser.add_argument(
        'workflow_params_file',
        help='Path to a file containing the JSON-serialized parameters from the workflow.'
    )
    parser.add_argument(
        '-a', '--app_namespace',
        help='Namespace of the app the database belongs to.',
        dest='app_namespace',
        default='agwa'
    )
    args, unknown_args = parser.parse_known_args()
    return args, unknown_args
