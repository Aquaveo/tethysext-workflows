"""
********************************************************************************
* Name: job_step.py
* Author: nswain
* Created On: December 17, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
from .spatial_step import SpatialStep


class JobStep(SpatialStep):
    """
    Workflow step used for reviewing previous step parameters and submitting processing jobs to Condor.

    Options:
        scheduler(str): Name of the Condor scheduler to use.
        jobs(list<dict>): A list of dictionaries, each containing the kwargs for a CondorWorkflowJobNode.
        workflow_kwargs(dict): Additional keyword arguments to pass to the CondorWorkflow.
    """  # noqa: #501
    CONTROLLER = 'tethysext.workflows.controllers.workflows.map_workflows.JobStepMWV'
    TYPE = 'job_workflow_step'

    __mapper_args__ = {
        'polymorphic_identity': TYPE
    }

    @property
    def default_options(self):
        default_options = super().default_options
        default_options.update({
            'scheduler': '',
            'jobs': [],
            'workflow_kwargs': {},
            'working_message': '',
            'error_message': '',
            'pending_message': '',
        })
        return default_options

    def init_parameters(self, *args, **kwargs):
        """
        Initialize the parameters for this step.

        Returns:
            dict<name:dict<help,value>>: Dictionary of all parameters with their initial value set.
        """
        return {}

    def validate(self):
        """
        Validates parameter values of this this step.

        Returns:
            bool: True if data is valid, else Raise exception.

        Raises:
            ValueError
        """
        # Run super validate method first to perform built-in checks (e.g.: Required)
        super().validate()
