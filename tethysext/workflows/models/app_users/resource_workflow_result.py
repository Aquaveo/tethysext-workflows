"""
********************************************************************************
* Name: resource_workflow_result
* Author: nswain
* Created On: April 30, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.orm import relationship, backref
from sqlalchemy import Column, ForeignKey, String, PickleType, Integer
from ...models import GUID
from ...mixins import StatusMixin, AttributesMixin, OptionsMixin, SerializeMixin
from ..base import WorkflowsBase
import ControllerMetadata


__all__ = ['Result']

# TODO this file may need to be deleted
class Result(WorkflowsBase, StatusMixin, AttributesMixin, OptionsMixin, SerializeMixin):
    """
    Data model for storing information about resource workflow results.
    """
    __tablename__ = 'app_users_resource_workflow_results'
    CONTROLLER = 'tethysext.workflows.controllers.resource_workflows.workflow_results_view.WorkflowResultsView'
    TYPE = 'generic_workflow_result'

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    workflow_id = Column(GUID, ForeignKey('app_users_tethys_workflows.id'))
    controller_metadata_id = Column(GUID, ForeignKey('app_users_controller_metadata.id'))
    type = Column(String)
    name = Column(String)
    codename = Column(String)
    description = Column(String)
    order = Column(Integer)
    _data = Column(PickleType, default={})
    _options = Column(PickleType, default={})
    _attributes = Column(String)

    _controller = relationship(
        'ControllerMetadata',
        backref=backref('result'),
        cascade='all,delete',
        uselist=False,
    )

    __mapper_args__ = {
        'polymorphic_on': 'type',
        'polymorphic_identity': TYPE
    }

    def __init__(self, *args, **kwargs):
        controller = kwargs.pop('controller', self.CONTROLLER)
        super().__init__(*args, **kwargs)

        if 'options' in kwargs:
            self.options = kwargs['options']
        else:
            self._options = self.default_options

        self._controller = ControllerMetadata(path=controller)

    def __str__(self):
        return '<{} name="{}" id="{}" >'.format(self.__class__.__name__, self.name, self.id)

    def __repr__(self):
        return self.__str__()

    @property
    def controller(self):
        return self._controller

    @property
    def data(self):
        if not self._data:
            self._data = dict()
        return self._data

    @data.setter
    def data(self, value):
        self._data = dict()
        session = Session.object_session(self)
        session and session.commit()
        self._data = value
        session and session.commit()

    def reset(self):
        """
        Resets result to initial state.
        """
        self._data = dict()

    def serialize_base_fields(self, d: dict) -> dict:
        """Hook for ATCore base classes to add their custom fields to serialization.

        Args:
            d: Base serialized Resource dictionary.

        Returns:
            Serialized Resource dictionary.
        """
        d.update({
            'codename': self.codename,
            'data': self.data,
            'order': self.order,
        })
        return d
