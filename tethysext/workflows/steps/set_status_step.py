"""
********************************************************************************
* Name: set_status_step.py
* Author: nswain
* Created On: August 19, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from ..models import Step


class SetStatusStep(Step):
    """
    Workflow step that can be used to change the status of a workflow with the click of a button.
    
    Options:
        form_title(str): Title to be displayed at the top of the form. Defaults to the name of the step.
        status_label(str): Custom label for the status select form field. Defaults to "Status".
        statuses(list<dicts<status,label>>): List of dictionaries with two keys: "status" and "label". The value of "status" must be a valid status from the StatusMixin as determined by the valid_statuses() method on the step. The value of the "label" will be what is displayed to the user. If "label" is None or not given, the value of "status" will be displayed to the user.
    """  # noqa: #501
    CONTROLLER = 'tethysext.workflows.controllers.workflows.workflow_views.SetStatusWV'
    TYPE = 'set_status_workflow_step'

    __mapper_args__ = {
        'polymorphic_identity': TYPE
    }

    @property
    def default_options(self):
        default_options = super().default_options
        default_options.update({
            'form_title': None,
            'status_label': None,
            'statuses': [
                {'status': SetStatusStep.STATUS_COMPLETE,
                 'label': None}
            ],
        })
        return default_options

    def init_parameters(self, *args, **kwargs):
        """
        Initialize the parameters for this step.

        Returns:
            dict<name:dict<help,value,required>>: Dictionary of all parameters with their initial value set.
        """
        return {
            'comments': {
                'help': 'Comments on reason for changing status to this status.',
                'value': '',
                'required': False
            },
        }

    def validate_statuses(self):
        """
        Validate the status dictionaries given in the "statuses" option.

        Raises:
            RuntimeError: Invalid statuses or malformed status dictionaries.
        """
        valid_statuses = self.valid_statuses()

        # Validate the statuses
        for status_dict in self.options.get('statuses', []):
            if 'status' not in status_dict.keys():
                raise RuntimeError(f'Key "status" not found in status dict provided by option '
                                   f'"statuses": {status_dict}')

            status = status_dict['status']
            if status not in valid_statuses:
                raise RuntimeError(f'Status "{status}" is not a valid status for {self.__class__.__name__}. '
                                   f'Must be one of: {", ".join(valid_statuses)}')
