from abc import ABC
from typing import Optional

from polarion.base.polarion_object import PolarionObject


class CustomFields(PolarionObject, ABC):
    # TODO polarion and project types, circular import
    def __init__(self, polarion, project, _id: Optional[str] = None, uri: Optional[str] = None):
        super().__init__(polarion, project, _id, uri)
        self.customFields = None

    def isCustomFieldAllowed(self, key: str) -> bool:
        raise NotImplementedError

    def setCustomField(self, key: str, value: str):
        """
        Set the custom field 'key' to the value
        :param key: custom field key
        :param value: custom field value
        :return: None
        """
        if not self.isCustomFieldAllowed(key):
            raise Exception(f"key {key} is not allowed for this workitem")

        if self.customFields is None:
            # nothing exists, create a custom field structure
            self.customFields = self._polarion.ArrayOfCustomType()
            self.customFields.Custom.append(self._polarion.CustomType(key=key, value=value))
        else:
            custom_field = next(
                (custom_field for custom_field in self.customFields.Custom if custom_field["key"] == key), None)
            if custom_field is not None:
                # custom field is there and we can update the value
                custom_field.value = value
            else:
                # custom field is not there, add it.
                self.customFields.Custom.append(self._polarion.CustomType(key=key, value=value))
        self.save()
