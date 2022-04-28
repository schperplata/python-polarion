from abc import ABC
from typing import Optional

from polarion.base.polarion_object import PolarionObject


class Comments(PolarionObject, ABC):

    # TODO comment type?
    def addComment(self, title: str, comment: str, parent: Optional["Comment"] = None):
        """Adds a comment to the workitem.
        Throws an exception if the function is disabled in Polarion.

        :param title: Title of the comment (will be None for a reply)
        :param comment: The comment, may contain html
        :param parent: A parent comment, if none provided it's a root comment.
        """
        service = self._polarion.getService('Tracker')
        if hasattr(service, 'addComment'):
            if parent is None:
                parent = self.uri
            else:
                # force title to be empty, not allowed for reply comments
                title = None
            content = {
                'type': 'text/html',
                'content': comment,
                'contentLossy': False
            }
            service.addComment(parent, title, content)
            self._reloadFromPolarion()
        else:
            raise Exception("addComment binding not found in Tracker Service. Adding comments might be disabled.")
