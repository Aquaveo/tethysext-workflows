"""
********************************************************************************
* Name: results_step.py
* Author: nswain
* Created On: March 28, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from sqlalchemy.orm import relationship
from ..mixins import ResultsMixin, AttributesMixin
from ..models import Step, step_result_association


class ResultsStep(Step, AttributesMixin, ResultsMixin):
    """
    Abstract base class of all Results Workflow Steps.
    """  # noqa: E501
    TYPE = 'results_workflow_step'

    __mapper_args__ = {
        'polymorphic_identity': TYPE
    }

    results = relationship(
        'Result',
        secondary=step_result_association,
        order_by='Result.order',
        cascade='all,delete',
        backref='steps'
    )

    @property
    def default_options(self):
        """
        Returns default options dictionary for the result.
        """
        default_options = super().default_options
        return default_options

    def init_parameters(self, *args, **kwargs):
        """
        Initialize the parameters for this step.
        Returns:
            dict<name:dict<help,value>>: Dictionary of all parameters with their initial value set.
        """
        return {}

    def reset(self):
        """
        Resets the step back to its initial state.
        """
        for result in self.results:
            result.reset()

        super().reset()
