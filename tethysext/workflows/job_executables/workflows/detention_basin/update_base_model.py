#!/opt/tethys-python
"""
********************************************************************************
* Name: detention_basin/update_base_model.py
* Author: nswain
* Created On: September 3, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from tethysext.atcore.services.resource_workflows.decorators import workflow_step_job


@workflow_step_job
def main(resource_db_session, model_db_session, resource, workflow, step, gs_private_url, gs_public_url, resource_class,
         workflow_class, params_json, params_file, cmd_args, extra_args):
    # Get project id for the detention basin project
    new_project_id = workflow.get_attribute('new_project_id')
    print(f'NEW PROJECT ID: {new_project_id}')

    # Get attributes from resource
    base_model_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id
    print(f'BASE MODEL ID: {base_model_id}')

    if int(base_model_id) == int(new_project_id):
        print(f'PROJECT WITH ID {new_project_id} IS ALREADY THE BASE MODEL. SKIPPING...')
        return

    # Overwrite the base project id
    resource.set_attribute('scenario_id', new_project_id)  #: using scenario_id to store current base_model_id
    base_model_history = resource.get_attribute('base_model_history')
    base_model_history.insert(0, new_project_id)
    resource.set_attribute('base_model_history', base_model_history)

    resource_db_session.commit()

    new_base_model_id = resource.get_attribute('scenario_id')  #: using scenario_id to store current base_model_id
    print(f'NEW BASE MODEL ID: {new_base_model_id}')
