"""
********************************************************************************
* Name: __init__.py
* Author: nswain
* Created On: April 19, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""


class ATCoreException(Exception):
    pass


class ModelDatabaseError(ATCoreException):
    pass


class ModelDatabaseInitializationError(ModelDatabaseError):
    pass


class ModelFileDatabaseInitializationError(ModelDatabaseError):
    pass


class UnboundFileCollectionError(Exception):
    pass


class UnboundFileDatabaseError(Exception):
    pass


class FileCollectionNotFoundError(Exception):
    pass


class FileCollectionItemNotFoundError(Exception):
    pass


class FileDatabaseNotFoundError(Exception):
    pass


class FileCollectionItemAlreadyExistsError(Exception):
    pass


class InvalidSpatialResourceExtentTypeError(Exception):
    pass

__all__ = [ATCoreException, ModelDatabaseError, ModelDatabaseInitializationError, ModelFileDatabaseInitializationError,
           UnboundFileCollectionError, UnboundFileDatabaseError, FileCollectionNotFoundError,
           FileCollectionItemNotFoundError, FileDatabaseNotFoundError, FileCollectionItemAlreadyExistsError,
           InvalidSpatialResourceExtentTypeError]
