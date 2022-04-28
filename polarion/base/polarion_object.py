from typing import Optional
class PolarionObject(object):
    # TODO polarion and project types, polarion_record, circular import
    def __init__(self, polarion, project, id: Optional[str] = None, uri: Optional[str] = None):
        self._polarion = polarion
        self._project = project
        self._id = id
        self._uri = uri

    def _reloadFromPolarion(self):
        raise NotImplementedError

    def save(self):
        raise NotImplementedError
