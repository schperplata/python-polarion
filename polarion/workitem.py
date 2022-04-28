import copy
import os
from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional

from zeep import xsd

from .base.comments import Comments
from .base.custom_fields import CustomFields
from .factory import Creator
from .user import User
from .document import Document

class Workitem(CustomFields, Comments):
    """
    Create a Polarion workitem object either from and id or from an Polarion uri.

    :param polarion: Polarion client object
    :param project: Polarion Project object
    :param id: Workitem ID
    :param uri: Polarion uri
    :param polarion_workitem: Polarion workitem content
    """
    class HyperlinkRoles(Enum):
        """
        Hyperlink reference type enum
        """
        INTERNAL_REF = 'internal reference'
        EXTERNAL_REF = 'external reference'

    def __init__(self, polarion,
                 project, id: Optional[str] = None,
                 uri: Optional[str] = None,
                 new_workitem_type: Optional[str] = None,
                 new_workitem_fields: Optional[List[str]] = None,
                 polarion_workitem: Optional["Workitem"] = None):  # TODO polarion and project types, circular import
        super().__init__(polarion, project, id, uri)
        self._polarion = polarion
        self._project = project
        self._id = id
        self._uri = uri

        service = self._polarion.getService('Tracker')

        if self._uri:
            try:
                self._polarion_item = service.getWorkItemByUri(self._uri)
                self._id = self._polarion_item.id
            except Exception:
                raise Exception(
                    f'Cannot find workitem {self._id} in project {self._project.id}')
        elif id is not None:
            try:
                self._polarion_item = service.getWorkItemById(
                    self._project.id, self._id)
            except Exception:
                raise Exception(
                    f'Cannot find workitem {self._id} in project {self._project.id}')
        elif new_workitem_type is not None:
            # construct empty workitem
            self._polarion_item = self._polarion.WorkItemType(
                type=self._polarion.EnumOptionIdType(id=new_workitem_type))
            self._polarion_item.project = self._project.polarion_data

            # get the required field for a new item
            required_features = service.getInitialWorkflowActionForProjectAndType(self._project.id, self._polarion.EnumOptionIdType(id=new_workitem_type))
            if required_features.requiredFeatures is not None:
                # if there are any, go and check if they are all supplied
                if new_workitem_fields is None or not set(required_features.requiredFeatures.item) <= new_workitem_fields.keys():
                    # let the user know with a better error
                    raise Exception(f'New workitem required field: {required_features.requiredFeatures.item} to be filled in using new_workitem_fields')

            if new_workitem_fields is not None:
                for new_field in new_workitem_fields:
                    if new_field in self._polarion_item:
                        self._polarion_item[new_field] = new_workitem_fields[new_field]
                    else:
                        raise Exception(f'{new_field} in new_workitem_fields is not recognised as a workitem field')

            # and create it
            new_uri = service.createWorkItem(self._polarion_item)
            # reload from polarion
            self._polarion_item = service.getWorkItemByUri(new_uri)
            self._id = self._polarion_item.id

        elif polarion_workitem is not None:
            self._polarion_item = polarion_workitem
            self._id = self._polarion_item.id
        else:
            raise Exception('No id, uri, polarion workitem or new workitem type specified!')

        self._buildWorkitemFromPolarion()

    def _buildWorkitemFromPolarion(self):
        if self._polarion_item is not None and not self._polarion_item.unresolvable:
            self._original_polarion = copy.deepcopy(self._polarion_item)
            for attr, value in self._polarion_item.__dict__.items():
                for key in value:
                    setattr(self, key, value[key])
            self._polarion_test_steps = None
            try:
                # get the custom fields
                service = self._polarion.getService('Tracker')
                custom_fields = service.getCustomFieldTypes(self.uri)
                # check if any of the field has the test steps
                if any(field.id == 'testSteps' for field in custom_fields):
                    service_test = self._polarion.getService('TestManagement')
                    self._polarion_test_steps = service_test.getTestSteps(self.uri)
            except Exception as  e:
                # fail silently as there are probably not test steps for this workitem
                # todo: logging support
                pass
            self._parsed_test_steps = None
            if self._polarion_test_steps is not None:
                if self._polarion_test_steps.keys is not None and self._polarion_test_steps.steps:
                    # oh god, parse the test steps...
                    columns = []
                    self._parsed_test_steps = []
                    for col in self._polarion_test_steps.keys.EnumOptionId:
                        columns.append(col.id)
                    # now parse the rows
                    for row in self._polarion_test_steps.steps.TestStep:
                        current_row = {}
                        for col_id in range(len(row.values.Text)):
                            current_row[columns[col_id]] = row.values.Text[col_id].content
                        self._parsed_test_steps.append(current_row)
        else:
            raise Exception(f'Workitem not retrieved from Polarion')

    def getAuthor(self) -> User:
        """Get the author of the workitem

        :return: Author
        """
        if self.author is not None:
            return User(self._polarion, self.author)
        return None

    def removeApprovee(self, user: User):
        """Remove a user from the approvers

        :param user: The user object to remove
        """
        service = self._polarion.getService('Tracker')
        service.removeApprovee(self.uri, user.id)
        self._reloadFromPolarion()

    def addApprovee(self, user: User, remove_others: bool = False):
        """Adds a user as approver

        :param user: The user object to add
        :param remove_others: Set to True to make the new user the only approver user.
        """
        service = self._polarion.getService('Tracker')

        if remove_others:
            current_users = self.getApproverUsers()
            for current_user in current_users:
                service.removeApprovee(self.uri, current_user.id)

        service.addApprovee(self.uri, user.id)
        self._reloadFromPolarion()

    def getApproverUsers(self) -> List[User]:
        """Get an array of approval users

        :return: An array of User objects
        """
        assigned_users = []
        if self.approvals is not None:
            for approval in self.approvals.Approval:
                assigned_users.append(User(self._polarion, approval.user))
        return assigned_users

    def getAssignedUsers(self) -> List[User]:
        """Get an array of assigned users

        :return: An array of User objects
        """
        assigned_users = []
        if self.assignee is not None:
            for user in self.assignee.User:
                assigned_users.append(User(self._polarion, user))
        return assigned_users

    def removeAssignee(self, user: User):
        """Remove a user from the assignees

        :param user: The user object to remove
        """
        service = self._polarion.getService('Tracker')
        service.removeAssignee(self.uri, user.id)
        self._reloadFromPolarion()

    def addAssignee(self, user: User, remove_others: bool=False):
        """Adds a user as assignee

        :param user: The user object to add
        :param remove_others: Set to True to make the new user the only assigned user.
        """
        service = self._polarion.getService('Tracker')

        if remove_others:
            current_users = self.getAssignedUsers()
            for current_user in current_users:
                service.removeAssignee(self.uri, current_user.id)

        service.addAssignee(self.uri, user.id)
        self._reloadFromPolarion()

    def getStatusEnum(self) -> List[str]: # TODO is this type correct?
        """Try to get the status enum of this workitem type
        When it fails to get it, the list will be empty

        :return: An array of strings of the statusses
        """
        try:
            enum = self._project.getEnum(f'{self.type.id}-status')
            return enum
        except Exception:
            return []

    def getResolutionEnum(self) -> List[str]: # TODO is this type correct?
        """Try to get the resolution enum of this workitem type
        When it fails to get it, the list will be empty

        :return: An array of strings of the resolutions
        """
        try:
            enum = self._project.getEnum(f'{self.type.id}-resolution')
            return enum
        except Exception:
            return []

    def getSeverityEnum(self) -> List[str]: # TODO is this type correct?
        """Try to get the severity enum of this workitem type
        When it fails to get it, the list will be empty

        :return: An array of strings of the severities
        """
        try:
            enum = self._project.getEnum(f'{self.type.id}-severity')
            return enum
        except Exception:
            return []

    def getAllowedCustomKeys(self) -> List[str]:
        """Gets the list of keys that the workitem is allowed to have.

        :return: An array of strings of the keys
        """
        try:
            service = self._polarion.getService('Tracker')
            return service.getCustomFieldKeys(self.uri)
        except Exception:
            return []

    def isCustomFieldAllowed(self, key: str) -> bool:
        """Checks if the custom field of a given key is allowed.

        :return: Trye/False if the field is allowed/forbidden
        """
        return key in self.getAllowedCustomKeys()

    def getAvailableStatus(self) -> List[str]:
        """Get all available status option for this workitem

        :return: An array of string of the statusses
        """
        available_status = []
        service = self._polarion.getService('Tracker')
        av_status = service.getAvailableEnumOptionIdsForId(self.uri, 'status')
        for status in av_status:
            available_status.append(status.id)
        return available_status

    def getAvailableActionsDetails(self) -> List[str]: # TODO value type?
        """Get all actions option for this workitem with details

        :return: An array of dictionaries of the actions
        """
        available_actions = []
        service = self._polarion.getService('Tracker')
        av_actions = service.getAvailableActions(self.uri)
        for action in av_actions:
            available_actions.append(action)
        return available_actions

    def getAvailableActions(self) -> List[str]:
        """Get all actions option for this workitem without details

        :return: An array of strings of the actions
        """
        available_actions = []
        service = self._polarion.getService('Tracker')
        av_actions = service.getAvailableActions(self.uri)
        for action in av_actions:
            available_actions.append(action.nativeActionId)
        return available_actions

    def performAction(self, action_name: str):
        """Perform selected action. An exception will be thrown if some prerequisite is not set.

        :param action_name: string containing the action name
        """
        # get id from action name
        service = self._polarion.getService('Tracker')
        av_actions = service.getAvailableActions(self.uri)
        for action in av_actions:
            if action.nativeActionId == action_name or action.actionName == action_name:
                service.performWorkflowAction(self.uri, action.actionId)

    def performActionId(self, actionId: int):
        """Perform selected action. An exception will be thrown if some prerequisite is not set.

        :param actionId: number for the action to perform
        """
        service = self._polarion.getService('Tracker')
        service.performWorkflowAction(self.uri, actionId)

    def setStatus(self, status: str):
        """Sets the status opf the workitem and saves the workitem, not respecting any project configured limits or requirements.

        :param status: name of the status
        """
        if status in self.getAvailableStatus():
            self.status.id = status
            self.save()

    def getDescription(self) -> str:
        """Get a comment if available. The comment may contain HTML if edited in Polarion!

        :return: The content of the description, may contain HTML
        """
        if self.description is not None:
            return self.description.content
        return None

    def setDescription(self, description: str):
        """Sets the description and saves the workitem

        :param description: the description
        """
        self.description = self._polarion.TextType(
            content=description, type='text/html', contentLossy=False)
        self.save()

    def setResolution(self, resolution: str):
        """Sets the resolution and saves the workitem

        :param resolution: the resolution
        """
        if self.resolution is not None:
            self.resolution.id = resolution
        else:
            self.resolution = self._polarion.EnumOptionIdType(
                id=resolution)
        self.save()

    def hasTestSteps(self) -> bool:
        """Checks if the workitem has test steps

        :return: True/False
        """
        if self._parsed_test_steps is not None:
            return len(self._parsed_test_steps) > 0
        return False

    def addHyperlink(self, url: str, hyperlink_type: HyperlinkRoles):
        """Adds a hyperlink to the workitem.

        :param url: The URL to add
        :param hyperlink_type: Select internal or external hyperlink
        """
        service = self._polarion.getService('Tracker')
        service.addHyperlink(self.uri, url, {'id': hyperlink_type.value})
        self._reloadFromPolarion()

    def addLinkedItem(self, workitem: "Workitem", link_type: str):
        """Add a link to a workitem

        :param workitem: A workitem
        :param link_type: The link type
        """
        service = self._polarion.getService('Tracker')
        service.addLinkedItem(self.uri, workitem.uri, role={'id': link_type})
        self._reloadFromPolarion()
        workitem._reloadFromPolarion()

    def removeLinkedItem(self, workitem: "WorkItem", role:Optional[str]=None):
        """Remove the workitem from the linked items list. If the role is specified, the specified link will be removed.
        If not specified, all links with the workitem will be removed

        :param workitem: Workitem to be removed
        :param role: the role to remove
        """
        service = self._polarion.getService('Tracker')
        if role is not None:
            service.removeLinkedItem(self.uri, workitem.uri, role={'id': role})
        else:
            if self.linkedWorkItems is not None:
                for linked_item in self.linkedWorkItems.LinkedWorkItem:
                    if linked_item.workItemURI == workitem.uri:
                        service.removeLinkedItem(self.uri, linked_item.workItemURI, role=linked_item.role)
            if self.linkedWorkItemsDerived is not None:
                for linked_item in self.linkedWorkItemsDerived.LinkedWorkItem:
                    if linked_item.workItemURI == workitem.uri:
                        service.removeLinkedItem(linked_item.workItemURI, self.uri, role=linked_item.role)
        self._reloadFromPolarion()
        workitem._reloadFromPolarion()

    def hasAttachment(self) -> bool:
        """Checks if the workitem has attachments

        :return: True/False
        """
        if self.attachments is not None:
            return True
        return False

    def getAttachment(self, id: str) -> List[bytes]: # TODO List[bytes] or bytearray?
        """Get the attachment data

        :param id: The attachment id
        :return: list of bytes
        """
        service = self._polarion.getService('Tracker')
        return service.getAttachment(self.uri, id)

    def saveAttachmentAsFile(self, id: str, file_path: str):
        """Save an attachment to file.

        :param id: The attachment id
        :param file_path: File where to save the attachment
        """
        bin = self.getAttachment(id)
        with open(file_path, "wb") as file:
            file.write(bin)

    def deleteAttachment(self, id: str):
        """Delete an attachment.

        :param id: The attachment id
        """
        service = self._polarion.getService('Tracker')
        service.deleteAttachment(self.uri, id)
        self._reloadFromPolarion()

    def addAttachment(self, file_path: str, title: str):
        """Upload an attachment

        :param file_path: Source file to upload
        :param title: The title of the attachment
        """
        service = self._polarion.getService('Tracker')
        file_name = os.path.split(file_path)[1]
        with open(file_path, "rb") as file_content:
            service.createAttachment(self.uri, file_name, title, file_content.read())
        self._reloadFromPolarion()

    def updateAttachment(self, id: str, file_path: str, title: str):
        """
        Upload an attachment

        :param id: The attachment id
        :param file_path: Source file to upload
        :param title: The title of the attachment
        """
        service = self._polarion.getService('Tracker')
        file_name = os.path.split(file_path)[1]
        with open(file_path, "rb") as file_content:
            service.updateAttachment(self.uri, id, file_name, title, file_content.read())
        self._reloadFromPolarion()

    def delete(self):
        """Delete the work item in polarion"""
        service = self._polarion.getService('Tracker')
        service.deleteWorkItem(self.uri)

    def moveToDocument(self, document: Document, parent: Optional["WorkItem"]):
        """Move the work item into a document as a child of another workitem

        :param document: Target document
        :param parent: Parent workitem, None if it shall be placed as top item
        """
        service = self._polarion.getService('Tracker')
        service.moveWorkItemToDocument(self.uri, document.uri, parent.uri if parent is not None else xsd.const.Nil, -1,
                                       False)

    def save(self):
        """Update the workitem in polarion"""
        updated_item = {}

        for attr, value in self._polarion_item.__dict__.items():
            for key in value:
                current_value = getattr(self, key)
                prev_value = getattr(self._original_polarion, key)
                if current_value != prev_value:
                    updated_item[key] = current_value
        if len(updated_item) > 0:
            updated_item['uri'] = self.uri
            service = self._polarion.getService('Tracker')
            service.updateWorkItem(updated_item)
            self._reloadFromPolarion()

    def _reloadFromPolarion(self):
        service = self._polarion.getService('Tracker')
        self._polarion_item = service.getWorkItemByUri(self._polarion_item.uri)
        self._buildWorkitemFromPolarion()
        self._original_polarion = copy.deepcopy(self._polarion_item)

    def __eq__(self, other):
        try:
            a = vars(self)
            b = vars(other)
        except Exception:
            return False
        return self._compareType(a, b)

    def _compareType(self, a, b) -> bool:
        basic_types = [int, float,
                       bool, type(None), str, datetime, date]

        for key in a:
            if key.startswith('_'):
                # skip private types
                continue
            # first to a quick type compare to catch any easy differences
            if type(a[key]) == type(b[key]):
                if type(a[key]) in basic_types:
                    # direct compare capable
                    if a[key] != b[key]:
                        return False
                elif isinstance(a[key], list):
                    # special case for list items
                    if len(a[key]) != len(b[key]):
                        return False
                    for idx, sub_a in enumerate(a[key]):
                        self._compareType(sub_a, b[key][idx])
                else:
                    if not self._compareType(a[key], b[key]):
                        return False
            else:
                # exit, type mismatch
                return False
        # survived all exits, must be good then
        return True

    def __repr__(self):
        return f'{self._id}: {self.title}'

    def __str__(self):
        return f'{self._id}: {self.title}'


class WorkitemCreator(Creator):
    def createFromUri(self, polarion, project, uri: str) -> Workitem: # TODO polarion and project types, circular import
        return Workitem(polarion, project, None, uri)
