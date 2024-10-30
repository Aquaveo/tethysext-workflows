"""
********************************************************************************
* Name: __init__.py
* Author: nswain
* Created On: April 19, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""


class TethysWorkflowsException(Exception):
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


__all__ = [TethysWorkflowsException, UnboundFileCollectionError, UnboundFileDatabaseError, FileCollectionNotFoundError,
           FileCollectionItemNotFoundError, FileDatabaseNotFoundError, FileCollectionItemAlreadyExistsError]
