import re
from abc import ABC, abstractmethod
from typing import Dict


class Creator(ABC):
    test = 1

    @abstractmethod
    def createFromUri(self, polarion, project, uri):
        pass


creator_list: Dict[str, Creator] = {}  # TODO is this true?


def addCreator(type_name, creator) -> Creator:
    creator_list[type_name] = creator


# TODO polarion and project types, circular import
def createFromUri(polarion, project, uri: str):
    type_name = _subterraUrl(uri)
    if type_name in creator_list:
        creator = creator_list[type_name]()
        return creator.createFromUri(polarion, project, uri)
    else:
        raise Exception(f'type {type_name} not supported')


def _subterraUrl(uri: str) -> str:
    uri_parts = uri.split(':')
    if uri_parts[0] != 'subterra':
        raise Exception(f'Not a subterra uri: {uri}')
    uri_type = re.findall(r"{(\w+)}", uri)
    if len(uri_type) >= 1:
        return uri_type[0].lower()
    else:
        raise Exception(f'{uri} is not a valid polarion uri')
