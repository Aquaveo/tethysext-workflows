"""
********************************************************************************
* Name: image_workflow_result.py
* Author: nathan, htran, msouff
* Created On: Oct 7, 2020
* Copyright: (c) Aquaveo 2020
********************************************************************************
"""
import base64
import copy
import io
import urllib

from ..models.workflow_result import Result

__all__ = ['ImageWorkflowResult']


class ImageWorkflowResult(Result):
    """
    Data model for storing image URI data for display.

    The URI string should be a base64 encoded string of a png image.

    For example, to generate one for a matplotlib plot:

    ```
    import matplotlib.pyplot as plt
    import base64
    import io

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3, 4], [1, 4, 2, 3])
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    string = base64.b64encode(buf.read())
    uri = urllib.parse.quote(string)
    ```
    """
    CONTROLLER = 'tethysext.workflows.controllers.workflows.results_views.image_workflow_results_view.ImageWorkflowResultView'  # noqa: E501
    TYPE = 'image_workflow_result'

    __mapper_args__ = {
        'polymorphic_on': 'type',
        'polymorphic_identity': TYPE
    }

    def __init__(self, *args, **kwargs):
        """
        Constructor.

        Args:
        """
        super().__init__(*args, **kwargs)

    @property
    def default_options(self):
        """
        Returns default options dictionary for the object.
        """

        default_options = super().default_options
        default_options.update({
            'no_image_message': 'No image found.'
        })
        return default_options

    @property
    def image(self):
        if 'image' not in self.data:
            self.data['image'] = ''
        return copy.deepcopy(self.data['image'])

    @image.setter
    def image(self, value):
        data = copy.deepcopy(self.data)
        data['image'] = value
        self.data = data

    def _add_image(self, image_object):
        """
        Update image object.

        Args:
            image_object(dict): The image.
        """
        self.image = image_object

    def image_from_matplotlib_figure(self, figure):
        """
        Adds a matplotlib plot figure object to the result.

        Args:
            figure(obj): matplotlib figure.
        """
        if not figure:
            raise ValueError('The matplotlib plot figure must not be empty.')

        buf = io.BytesIO()
        figure.savefig(buf, format='png')
        buf.seek(0)
        string = base64.b64encode(buf.read())
        uri = urllib.parse.quote(string)

        self.add_image(uri)

    def add_image(self, image, description=''):
        """
        Adds an image to the result.

        Args:
            image(str): base64 image uri.  Add only one image.
            description(str): description of the image.  Defaults to ''.
        """
        image_object = {
            'image_uri': image,
            'image_description': description,
        }

        self._add_image(image_object)

    def get_image_object(self):
        """
        Gets image object from the result.

        Returns image object.
        """
        return self.image
