"""
********************************************************************************
* Name: file_database.py
* Author: glarsen
* Created On: October 30, 2020
* Copyright: (c) Aquaveo 2020
********************************************************************************
"""
import uuid

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from ...models import WorkflowsBase, GUID


class FileDatabase(WorkflowsBase):
    """A model representing a FileDatabase"""
    __tablename__ = "file_databases"

    id = Column('id', GUID, primary_key=True, default=uuid.uuid4)
    meta = Column('metadata', JSON)

    collections = relationship("FileCollection", back_populates="database")
