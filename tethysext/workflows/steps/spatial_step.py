"""
********************************************************************************
* Name: spatial_step.py
* Author: nswain
* Created On: March 28, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import json
from ..models import Step


class SpatialStep(Step):
    """
    Abstract base class of all Spatial Workflow Steps.
    """  # noqa: #501
    TYPE = 'spatial_workflow_step'

    __mapper_args__ = {
        'polymorphic_identity': TYPE
    }

    @property
    def default_options(self):
        default_options = super().default_options
        default_options.update({
            'geocode_enabled': False,
            'label_options': None,
        })
        return default_options

    def __init__(self, geoserver_name, map_manager, spatial_manager, *args, **kwargs):
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
            '_SpatialManager': spatial_manager
        }

    def to_geojson(self, as_str=False):
        """
        Serialize SpatialStep to GeoJSON.

        Args:
            as_str(bool): Returns GeoJSON string if True, otherwise returns dict equivalent.

        Returns:
            str or dict: GeoJSON string or dict equivalent representation of the spatial portions of a SpatialStep.
        """  # noqa: E501
        geojson_dict = self.get_parameter('geometry')

        if as_str:
            return json.dumps(geojson_dict)

        return geojson_dict
