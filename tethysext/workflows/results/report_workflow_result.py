"""
********************************************************************************
* Name: spatial_workflow_result
* Author: nswain
* Created On: April 30, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
from ..models.workflow_result import Result


__all__ = ['ReportWorkflowResult']


class ReportWorkflowResult(Result):
    """
    Data model for storing spatial information about workflow results.
    """
    CONTROLLER = 'tethysext.workflows.controllers.workflows.results_views.report_workflow_results_view.ReportWorkflowResultsView'  # noqa: E501
    TYPE = 'report_workflow_result'

    __mapper_args__ = {
        'polymorphic_on': 'type',
        'polymorphic_identity': TYPE
    }

    def __init__(self, geoserver_name, map_manager, spatial_manager, map_renderer='tethys_map_view', *args, **kwargs):
        """
        Constructor.

        Args:
            geoserver_name(str): Name of geoserver setting to use.
            map_manager(MapManager): Instance of MapManager to use for the map view.
            spatial_manager(SpatialManager): Instance of SpatialManager to use for the map view.
        """
        super().__init__(*args, **kwargs)
        self.controller.kwargs = {
            'geoserver_name': geoserver_name,
            '_MapManager': map_manager,
            'map_type': map_renderer,
            '_SpatialManager': spatial_manager
        }

    @property
    def default_options(self):
        """
        Returns default options dictionary for the object.
        """
        default_options = super().default_options
        return default_options
