"""
********************************************************************************
* Name: form_input_step.py
* Author: glarsen, mlebaron
* Created On: October 17, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from ..models import Step


class FormInputStep(Step):
    """
    Workflow step that can be used to get form input from a user.

    Options:
        form_title(str): Title to be displayed at the top of the form. Defaults to the name of the step.
        status_label(str): Custom label for the status select form field. Defaults to "Status".
        param_class(dict): A param class to represent form fields.
        renderer(str): Renderer option. Available values are 'django' and 'bokeh'. Defauls to 'django'. 
    """  # noqa: #501

    CONTROLLER = 'tethysext.workflows.controllers.workflows.workflow_views.FormInputWV'
    TYPE = 'form_input_workflow_step'

    __mapper_args__ = {
        'polymorphic_identity': TYPE
    }

    @property
    def default_options(self):
        default_options = super().default_options
        default_options.update({
            'form_title': None,
            'status_label': None,
            'param_class': {},
            'renderer': 'django'
        })
        return default_options

    def init_parameters(self, *args, **kwargs):
        return {
            'form-values': {
                'help': 'Values from form',
                'value': {},
                'required': True
            },
        }
