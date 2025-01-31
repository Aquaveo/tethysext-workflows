---
id: manager_files_documentation
title: Managers
sidebar_label: Managers
excerpt: "Documentation for Manager Classes for Workflows Apps"
sidebar_position: 3
---

When creating applications using the Tethys Workflows Extension, you'll often need a Map Manager class and a Spatial Manager class. This documentation will provide help on creating those files.

## Map Manager
Map Managers help us prepare and configure the interactive maps used in workflows. The best way to build a map manager class is to build on the MapManagerBase class included in the Workflows Extension.

To do so, you'll need the following imports:

```python
from tethys_gizmos.gizmo_options import MapView, MVView
from tethysext.workflows.services.map_manager import MapManagerBase
```

### Methods:

#### `__init__(self, spatial_manager)`
    - Description: Initializer used for the Map Manager class.
    - Parameters:
        - spatial_manager(tethysext.workflows.services.base_spatial_manager.BaseSpatialManager): the spatial manager class assigned to this map manager
    
#### `compose_map(self, request, *args, **kwargs)`
    - Description: Abstract method to be overriden to prepare the map with any desired layer(s)
    - Parameters:
        - request(HttpRequest): A Django request object.
    - Returns:
        - MapView object
        - extent
    - Example: 
        ```python
        def compose_map(self, request):
            layers = []
            layer_groups = []

            with open('/path/to/geojson_file', 'r') as geojson_file:
                geojson_data = geojson_file.read()
            geojson_layer = self.build_geojson_layer(geojson_data, "GeoJSON Layer Name", "GeoJSON Layer Title", "geojson_layer_var", "geojson_layer_id")
            layers.append(geojson_layer)

            layer_group = self.build_Layer_group("layer_group_id", "GeoJSON Layers", layers)
            layer_groups.append(layer_group)


            map_view = MapView(
                height='600px',
                width='100%',
                controls=['ZoomSlider', 'Rotate', 'FullScreen'],
                layers=layers,
                view=MVView(
                    projection='EPSG:4326',
                    center=self.DEFAULT_CENTER,
                    zoom=13,
                    maxZoom=28,
                    minZoom=4,
                ),
                basemap=['ESRI', 'OpenStreetMap',],
                legend=True
            )

            _, extent = self.get_map_extent()


            return map_view, extent, layer_groups
        ```

#### `get_cesium_token(self)`
    - Description: Get the cesium token for Cesium Views (meant to be overriden with actual cesium API token)
    - Returns:
        - token(str): the cesium API token

#### `build_param_string(self, **kwargs)`
    - Description: Build a VIEWPARAMS or ENV string with given kwargs (e.g.: 'foo:1;bar:baz')
    - Parameters:
        - kwargs: key-value pairs of paramaters
    - Returns:
        - param_string(str): parameter string

#### `build_geojson_layer(self, geojson, layer_name, layer_title, layer_variable, layer_id='', visible=True, public=True, selectable=False, plottable=False, has_action=False, extent=None, popup_title=None, excluded_properties=None, show_download=False, label_options=None)`
    - Description: Build a GeoJSON MVLayer object with supplied arguments
    - Parameters:
        - geojson(dict): Python equivalent GeoJSON FeatureCollection.
        - layer_name(str): Name of GeoServer layer (e.g.: agwa:3a84ff62-aaaa-bbbb-cccc-1a2b3c4d5a6b7c8d-model_boundaries).
        - layer_title(str): Title of MVLayer (e.g.: Model Boundaries).
        - layer_variable(str): Variable type of the layer (e.g.: model_boundaries).
        - layer_id(UUID, int, str): layer_id for non geoserver layer where layer_name may not be unique.
        - visible(bool): Layer is visible when True. Defaults to True.
        - public(bool): Layer is publicly accessible when app is running in Open Portal Mode if True. Defaults to True.
        - selectable(bool): Enable feature selection. Defaults to False.
        - plottable(bool): Enable "Plot" button on pop-up properties. Defaults to False.
        - has_action(bool): Enable "Action" button on pop-up properties. Defaults to False.
        - extent(list): Extent for the layer (optional)
        - popup_title(str): Title to display on feature popups. Defaults to layer title.
        - excluded_properties(list): List of properties to exclude from feature popups.
        - show_download(boolean): enable download geojson as shapefile. Default is False.
        - label_options(dict): Dictionary for labeling.  Possibilities include label_property (the name of the
            property to label), font (label font), text_align (alignment of the label), offset_x (x offset) (optional)

    - Returns:
        mv_layer(MVLayer): the layer object

#### `build_cesium_layer(self, cesium_type, cesium_json, layer_name, layer_title, layer_variable, layer_id='', visible=True, public=True, selectable=False, plottable=False, has_action=False, extent=None, popup_title=None, excluded_properties=None, show_download=False)`
    - Description: Build a cesium MVLayer object with supplied arguments.
    - Parameters:
        - cesium_type(enum): 'CesiumModel' or 'CesiumPrimitive'.
        - cesium_json(dict): Cesium dictionary to describe the layer.
        - layer_name(str): Name of GeoServer layer (e.g.: agwa:3a84ff62-aaaa-bbbb-cccc-1a2b3c4d5a6b7c8d-model_boundaries).
        - layer_title(str): Title of MVLayer (e.g.: Model Boundaries).
        - layer_variable(str): Variable type of the layer (e.g.: model_boundaries).
        - layer_id(UUID, int, str): layer_id for non geoserver layer where layer_name may not be unique.
        - visible(bool): Layer is visible when True. Defaults to True.
        - public(bool): Layer is publicly accessible when app is running in Open Portal Mode if True. Defaults to True.
        - selectable(bool): Enable feature selection. Defaults to False.
        - plottable(bool): Enable "Plot" button on pop-up properties. Defaults to False.
        - has_action(bool): Enable "Action" button on pop-up properties. Defaults to False.
        - extent(list): Extent for the layer (optional)
        - popup_title(str): Title to display on feature popups. Defaults to layer title.
        - excluded_properties(list): List of properties to exclude from feature popups.
        - show_download(boolean): enable download geojson as shapefile. Default is False.
    - Returns: 
        - mv_layer(MVLayer): the layer object

#### `build_wms_layer(self, endpoint, layer_name, layer_title, layer_variable, viewparams=None, env=None, visible=True, tiled=True, selectable=False, plottable=False, has_action=False, extent=None, public=True, geometry_attribute='geometry', layer_id='', excluded_properties=None, popup_title=None, color_ramp_division_kwargs=None, times=None)`
    - Description: Build a WMS MVLayer object with supplied arguments.
    - Parameters:
        - endpoint(str): URL to GeoServer WMS interface.
        - layer_name(str): Name of GeoServer layer (e.g.: agwa:3a84ff62-aaaa-bbbb-cccc-1a2b3c4d5a6b7c8d-model_boundaries).
        - layer_title(str): Title of MVLayer (e.g.: Model Boundaries).
        - layer_variable(str): Variable type of the layer (e.g.: model_boundaries).
        - layer_id(UUID, int, str): layer_id for non geoserver layer where layer_name may not be unique.
        - viewparams(str): VIEWPARAMS string.
        - env(str): ENV string.
        - visible(bool): Layer is visible when True. Defaults to True.
        - public(bool): Layer is publicly accessible when app is running in Open Portal Mode if True. Defaults to True.
        - tiled(bool): Configure as tiled layer if True. Defaults to True.
        - selectable(bool): Enable feature selection. Defaults to False.
        - plottable(bool): Enable "Plot" button on pop-up properties. Defaults to False.
        - has_action(bool): Enable "Action" button on pop-up properties. Defaults to False.
        - extent(list): Extent for the layer (optional)
        - popup_title(str): Title to display on feature popups. Defaults to layer title.
        - excluded_properties(list): List of properties to exclude from feature popups.
        - geometry_attribute(str): Name of the geometry attribute. Defaults to "geometry".
        - color_ramp_division_kwargs(dict): arguments from map_manager.generate_custom_color_ramp_divisions
        - times (list): List of time steps if layer is time-enabled. Times should be represented as strings in ISO 8601 format (e.g.: ["20210322T112511Z",      "20210322T122511Z", "20210322T132511Z"]). Currently only supported in CesiumMapView.
    - Returns: 
        - mv_layer(MVLayer): the layer object

#### `build_arc_gis_layer(self, endpoint, layer_name, layer_title, layer_variable, viewparams=None, env=None, visible=True, tiled=True, selectable=False, plottable=False, has_action=False, extent=None, public=True, geometry_attribute='geometry', layer_id='', excluded_properties=None, popup_title=None)`
    - Description: Build an AcrGIS Map Server MVLayer object with supplied arguments
    - Parameters:
        - endpoint(str): URL to GeoServer WMS interface.
        - layer_name(str): Name of GeoServer layer (e.g.: agwa:3a84ff62-aaaa-bbbb-cccc-1a2b3c4d5a6b7c8d-model_boundaries).
        - layer_title(str): Title of MVLayer (e.g.: Model Boundaries).
        - layer_variable(str): Variable type of the layer (e.g.: model_boundaries).
        - layer_id(UUID, int, str): layer_id for non geoserver layer where layer_name may not be unique.
        - viewparams(str): VIEWPARAMS string.
        - env(str): ENV string.
        - visible(bool): Layer is visible when True. Defaults to True.
        - public(bool): Layer is publicly accessible when app is running in Open Portal Mode if True. Defaults to True.
        - tiled(bool): Configure as tiled layer if True. Defaults to True.
        - selectable(bool): Enable feature selection. Defaults to False.
        - plottable(bool): Enable "Plot" button on pop-up properties. Defaults to False.
        - has_action(bool): Enable "Action" button on pop-up properties. Defaults to False.
        - extent(list): Extent for the layer (optional)
        - popup_title(str): Title to display on feature popups. Defaults to layer title.
        - excluded_properties(list): List of properties to exclude from feature popups.
        - geometry_attribute(str): Name of the geometry attribute. Defaults to "geometry".
    - Returns:
        - mv_layer(MVLayer): the layer object

#### `_build_mv_layer(self, layer_source, layer_name, layer_title, layer_variable, options, layer_id=None, extent=None, visible=True, public=True, selectable=False, plottable=False, has_action=False, excluded_properties=None, popup_title=None, geometry_attribute=None, style_map=None, show_download=False, times=None,label_options=None)`
    - Description: Build an MVLayer object with supplied arguments.
    - Parameters:
        - layer_source(str): OpenLayers Source to use for the MVLayer (e.g.: "TileWMS", "ImageWMS", "GeoJSON").
        - layer_name(str): Name of GeoServer layer (e.g.: agwa:3a84ff62-aaaa-bbbb-cccc-1a2b3c4d5a6b7c8d-model_boundaries).
        - layer_title(str): Title of MVLayer (e.g.: Model Boundaries).
        - layer_variable(str): Variable type of the layer (e.g.: model_boundaries).
        - layer_id(UUID, int, str): layer_id for non geoserver layer where layer_name may not be unique.
        - visible(bool): Layer is visible when True. Defaults to True.
        - selectable(bool): Enable feature selection. Defaults to False.
        - plottable(bool): Enable "Plot" button on pop-up properties. Defaults to False.
        - has_action(bool): Enable "Action" button on pop-up properties. Defaults to False.
        - extent(list): Extent for the layer (optional)
        - popup_title(str): Title to display on feature popups. Defaults to layer title.
        - excluded_properties(list): List of properties to exclude from feature popups.
        - geometry_attribute(str): Name of the geometry attribute (optional)
        - style_map(dict): Style map dictionary. See MVLayer documentation for examples of style maps (optional)
        - show_download(boolean): enable download layer. (only works for geojson layer).
        - times (list): List of time steps if layer is time-enabled. Times should be represented as strings in ISO 8601 format (e.g.: ["20210322T112511Z", "20210322T122511Z", "20210322T132511Z"]). Currently only supported in CesiumMapView.
        - label_options(dict): Dictionary for labeling.  Possibilities include label_property (the name of the property to label), font (label font), text_align (alignment of the label), offset_x (x offset) (optional)
    - Returns:
        - mv_layer(MVLayer): the MVLayer object

#### `build_layer_group(self, id, display_name, layers, layer_control='checkbox', visible=True, public=True)`
    - Description: Build a layer group object
    - Parameters:
        - id(str): Unique identifier for the layer group.
        - display_name(str): Name displayed in MapView layer selector/legend.
        - layers(list(MVLayer)): List of layers to include in the layer group.
        - layer_control(str): Type of control for layers. Either 'checkbox' or 'radio'. Defaults to checkbox.
        - visible(bool): Whether layer group is initially visible. Defaults to True.
        - public(bool): enable public to see this layer group if True.
    - Returns:
        - layer_group(dict): layer group definition
        
#### get_vector_style_map(self)
    - Description: Builds the style map for vector layers. Override this to change the styles of features on the map.
    - Returns:
        - style_map(dict): the style map
    - Example:
        ```python
            point_fill_color = 'darkgreen'
            point_outline_color = 'green'
            
            line_color = 'yellow'

            polygon_outline_color = 'orange'
            polygon_fill_color = 'red'
            style_map = {
                'Point': {'ol.style.Style': {
                    'image': {'ol.style.Circle': {
                        'radius': 5,
                        'fill': {'ol.style.Fill': {
                            'color': color,
                        }},
                        'stroke': {'ol.style.Stroke': {
                            'color': color,
                        }}
                    }}
                }},
                'LineString': {'ol.style.Style': {
                    'stroke': {'ol.style.Stroke': {
                        'color': color,
                        'width': 2
                    }}
                }},
                'Polygon': {'ol.style.Style': {
                    'stroke': {'ol.style.Stroke': {
                        'color': color,
                        'width': 2
                    }},
                    'fill': {'ol.style.Fill': {
                        'color': 'rgba(255, 215, 0, 0.1)'
                    }}
                }},
            }

            return style_map   
        ```
    
#### `get_wms_endpoint(self)`
    - Description: Get the public WMS endpoint for GeoServer
    - Returns: 
        - endpoint(str): the public WMS endpoint

#### `get_map_extent(self)`
    - Description: Get the default view and extent for the project.
    - Returns: 
        - mv_view(MVView): the default view
        - extent(list): the extent of the project

#### `build_legend(self, layer, units="")`
    - Description: Build Legend data for a given layer
    - Parameters:
        - layer: result.layer object
        - units: unit for the legend.
    - Returns: 
        legend_info(dict): Legend data associated with the layer
        
#### `generate_custom_color_ramp_division(self, min_value, max_value, num_divisions=10, value_precision=2, first_division=1, top_offset=0, bottom_offset=0,  color_ramp="", color_prefix='color', no_data_value=None)`
    - Description: Generate custom elevation divisions.
    - Parameters:
        - min_value(number): minimum value.
        - max_value(number): maximum value.
        - num_divisison(int): number of divisions.
        - value_precision(int): level of precision for legend values.
        - first_division(int): first division number (defaults to 1).
        - top_offset(number): offset from top of color ramp (defaults to 0).
        - bottom_offset(number): offset from bottom of color ramp (defaults to 0).
        - prefix(str): name of division variable prefix (i.e.: 'val' for pattern 'val1').
        - color_ramp(str): color ramp name in COLOR_RAMPS dict. Options are ['Blue', 'Blue and Red', 'Flower Field', 'Galaxy Berries', 'Heat Map', 'Olive Harmony', 'Mother Earth', 'Rainforest Frogs', 'Retro FLow', 'Sunset Fade']
        - color_prefix(str): name of color variable prefix (i.e.: 'color' for pattern 'color1').
        - no_data_value (str): set no data value for the color ramp. (defaults to None).
    - Returns: 
        - divisions(dict(name, value)): custom divisions

#### `get_plot_for_layer_feature(self, layer_name, feature_id)`
    - Description: Get plot data for given feature on given layer. Override this for your specific application's features' data.
    - Parameters:
        - layer_name(str): Name/id of layer.
        - feature_id(str): PostGIS Feature ID of feature.
    - Returns:
        - plot_title(str): title to appear on plot
        - plot_data(list(dict)): plot data
        - layout(dict): layout options

## Spatial Manager
Spatial Managers help us work with geoserver and manage certain configurations for our map managers to use.

You'll need to use the BaseSpatialManager class to build your own SpatialManager class to use in your workflows application. 

```python 
from tethysext.workflows.services.base_spatial_manager import BaseSpatialManager
```

There are some methods you'll need to override in order to use, along with some that are built in and can be used out the gate. Feel free to override any of these methods to fit your application's needs.

### Built-in Methods
#### `__init__(self, geoserver_engine)`
    - Description: Initializer used for the Spatial Manager class. 
    - Parameters: 
        - geoserver_engine(tethys_dataset_services.GeoServerEngine): Tethys GeoServer engine

#### `create_workspace(self)`
    - Description: Creates a workspace in GeoServer

#### `get_ows_endpoint(self, public_endpoint=True)`
    - Description: Returns the GeoServer endpoint for OWS services (with trailing slash).
    - Parameters:
        - public_endpoint(bool): return with the public endpoint if True.

#### `get_wms_endpoint(self, public=True)`
    - Description: Returns the GeoServer endpoint for WMS services (with trailing slash).
    - Parameters:
        - public(bool): return with the public endpoint if True.

#### `reload(self, ports=None, public_endpoint=True)`
    - Description: Reload the in memory catalog of each member of the geoserver cluster.
    - Parameters:
        - ports(list): list of ports for GeoServer to use
        - public_endpoint(bool): use the public geoserver endpoint if True, otherwise use the internal endpoint

## Methods to Override
#### `get_extent_for_project(self, *args, **kwargs)`
    - Description: Get extent of the project. This method needs to be overrided and to return a set of four coordinates with the lowest x and y values first, followed by the highest x and y values in this format: [min_x, min_y, max_x, max_y]
    - Example:
        ``` python
        def get_extent_for_project(self, project=None):
            default_extent = [-124.67, 25.84, -66.95, 49.38]  # Default for continental USA
            if project is None:
                return default_extent

            project_extent = project.get_attribute('project_extent')
            if project_extent is None:
                corners = [(default_extent[0], default_extent[1]), (default_extent[2], default_extent[3])]
            else:
                corners = [(project_extent[0], project_extent[1]), (project_extent[2], project_extent[3])]
            # get min_x, min_y, max_x, max_y from corners
            min_x = min([corner[0] for corner in corners])
            min_y = min([corner[1] for corner in corners])
            max_x = max([corner[0] for corner in corners])
            max_y = max([corner[1] for corner in corners])

            return [min_x, min_y, max_x, max_y]
        ```

#### `get_projection_units(self, *args, **kwargs)`
    - Description: Get units of the given projection
    - Example: 
        ```python
        from tethysext.atcore.services.exceptions import UnitsNotFound, UnknownUnits
        ...
        def get_projection_units(self, model_db, srid):
            if srid not in self._projection_units:
                db_engine = model_db.get_engine()
                try:
                    sql = "SELECT srid, proj4text FROM spatial_ref_sys WHERE srid = {}".format(srid)
                    ret = db_engine.execute(sql)

                    # Parse proj4text to get units
                    # e.g.: +proj=utm +zone=21 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs
                    proj4text = ''
                    units = ''

                    for row in ret:
                        proj4text = row.proj4text
                finally:
                    db_engine.dispose()

                proj4parts = proj4text.split('+')

                for part in proj4parts:
                    spart = part.strip()
                    if 'units' in spart:
                        units = spart.replace('units=', '')

                if not units:
                    raise UnitsNotFound('Unable to determine units of project with srid: {}'.format(srid))

                if 'ft' in units:
                    self._projection_units[srid] = self.U_IMPERIAL
                elif 'm' in units:
                    self._projection_units[srid] = self.U_METRIC
                else:
                    raise UnknownUnits('"{}" is an unrecognized form of units. From srid: {}'.format(units, srid))

            return self._projection_units[srid]
        ```

#### `get_projection_string(self, *args, **kwargs)`
    - Description: Get the projection string as either wkt or proj4 format
    - Example: 
        ```python
        def get_projection_string(self, model_db, srid, proj_format=''):
            if not proj_format:
                proj_format = self.PRO_WKT

            if proj_format not in (self.PRO_WKT, self.PRO_PROJ4):
                raise ValueError('Invalid projection format given: {}. Use either SpatialManager.PRO_WKT or '
                                'SpatialManager.PRO_PROJ4.'.format(proj_format))

            if srid not in self._projection_string or proj_format not in self._projection_string[srid]:
                db_engine = model_db.get_engine()
                try:
                    if proj_format is self.PRO_WKT:
                        sql = "SELECT srtext AS proj_string FROM spatial_ref_sys WHERE srid = {}".format(srid)
                    else:
                        sql = "SELECT proj4text AS proj_string FROM spatial_ref_sys WHERE srid = {}".format(srid)

                    ret = db_engine.execute(sql)
                    projection_string = ''

                    for row in ret:
                        projection_string = row.proj_string
                finally:
                    db_engine.dispose()

                if srid not in self._projection_string:
                    self._projection_string[srid] = {}

                self._projection_string[srid].update({proj_format: projection_string})

            return self._projection_string[srid][proj_format]
        ```

