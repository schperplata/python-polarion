import atexit
import re
from urllib.parse import urljoin, urlparse
import requests
from zeep import Client, Transport
from zeep.plugins import HistoryPlugin
from typing import Any, Dict, Optional

from .project import Project

_baseServiceUrl = 'ws/services'


class Polarion(object):
    """
    Create a Polarion client which communicates to the Polarion server.

    :param polarion_url: The base URL for the polarion instance. For example http://example/com/polarion
    :param user: The user name to login
    :param password: The password for that user
    :param static_service_list: Set to True when this class may not use a request to get the services list
    :param skip_cert_verification: Set to True to skip certification validation for TLS connection
    :param svn_repo_url: Set to the correct url when the SVN repo is not accessible via <host>/repo. For example http://example/repo_extern

    """

    def __init__(self, polarion_url: str, user: str, password: str,
                 static_service_list: bool = False, skip_cert_verification: bool = False,
                 svn_repo_url: Optional[str] = None):
        self.user = user
        self.password = password
        self.url = polarion_url
        self.skip_cert_verification = skip_cert_verification
        self.svn_repo_url = svn_repo_url

        self.services: Dict[str, Dict[str, Any]] = {}

        if not self.url.endswith('/'):
            self.url += '/'
        self.url = urljoin(self.url, _baseServiceUrl)

        if static_service_list:
            self._getStaticServices()
        else:
            self._getServices()
        self._createSession()
        self._getTypes()

        atexit.register(self._atexit_cleanup)

    def _atexit_cleanup(self):
        """
        Cleanup function to logout when Python is shutting down.
        :return: None
        """
        self.services['Session']['client'].service.endSession()

    def _getStaticServices(self):
        default_services = ['Session', 'Project', 'Tracker',
                            'Builder', 'Planning', 'TestManagement', 'Security']
        service_base_url = self.url + '/'
        for service in default_services:
            self.services[service] = {'url': urljoin(
                service_base_url, service + 'WebService')}

    def _getServices(self):
        """
        Parse the list of services available in the overview
        """
        service_overview = requests.get(self.url, verify=not self.skip_cert_verification)
        service_base_url = self.url + '/'
        if service_overview.ok:
            services = re.findall(r"(\w+)WebService", service_overview.text)
            for service in services:
                if service not in self.services:
                    self.services[service] = {'url': urljoin(
                        service_base_url, service + 'WebService')}

    def _createSession(self):
        """
        Starts a session with the specified user/password
        """
        if 'Session' in self.services:
            self.history = HistoryPlugin()
            self.services['Session']['client'] = Client(
                self.services['Session']['url'] + '?wsdl', plugins=[self.history], transport=self._getTransport())
            try:
                self.sessionHeaderElement = None
                self.services['Session']['client'].service.logIn(
                    self.user, self.password)
                tree = self.history.last_received['envelope'].getroottree()
                self.sessionHeaderElement = tree.find(
                    './/{http://ws.polarion.com/session}sessionID')
            except Exception:
                raise Exception(
                    f'Could not log in to Polarion for user {self.user}')
            if self.sessionHeaderElement is not None:
                self._updateServices()
        else:
            raise Exception(
                'Cannot login because WSDL has no SessionWebService')

    def _updateServices(self):
        """
        Updates all services with the correct session ID
        """
        if self.sessionHeaderElement is None:
            raise Exception('Cannot update services when not logged in')
        for service in self.services:
            if service != 'Session':
                if 'client' not in service:
                    self.services[service]['client'] = Client(
                        self.services[service]['url'] + '?wsdl', transport=self._getTransport())
                self.services[service]['client'].set_default_soapheaders(
                    [self.sessionHeaderElement])
            if service == 'Tracker':
                if hasattr(self.services[service]['client'].service, 'addComment'):
                    # allow addComment to be send without title, needed for reply comments
                    self.services[service]['client'].service.addComment._proxy._binding.get(
                        'addComment').input.body.type._element[1].nillable = True
                    self.services[service]['client'].service.getModuleWorkItemUris._proxy._binding.get(
                        'getModuleWorkItemUris').input.body.type._element[1].nillable = True
                    self.services[service]['client'].service.moveWorkItemToDocument._proxy._binding.get(
                        'moveWorkItemToDocument').input.body.type._element[2].nillable = True
            if service == 'Planning':
                self.services[service]['client'].service.createPlan._proxy._binding.get(
                    'createPlan').input.body.type._element[3].nillable = True

    def _getTypes(self):
        # TODO: check if the namespace is always the same
        # TODO: type hinting + class instance variables defined outside __init__?
        self.EnumOptionIdType = self.getTypeFromService('TestManagement', 'ns3:EnumOptionId')
        self.TextType = self.getTypeFromService('TestManagement', 'ns1:Text')
        self.ArrayOfTestStepResultType = self.getTypeFromService('TestManagement', 'ns4:ArrayOfTestStepResult')
        self.TestStepResultType = self.getTypeFromService('TestManagement', 'ns4:TestStepResult')
        self.TestRecordType = self.getTypeFromService('TestManagement', 'ns4:TestRecord')
        self.WorkItemType = self.getTypeFromService('Tracker', 'ns2:WorkItem')
        self.LinkedWorkItemType = self.getTypeFromService('Tracker', 'ns2:LinkedWorkItem')
        self.LinkedWorkItemArrayType = self.getTypeFromService('Tracker', 'ns2:ArrayOfLinkedWorkItem')
        self.ArrayOfCustomType = self.getTypeFromService('Tracker', 'ns2:ArrayOfCustom')
        self.CustomType = self.getTypeFromService('Tracker', 'ns2:Custom')
        self.ArrayOfEnumOptionIdType = self.getTypeFromService('Tracker', 'ns2:ArrayOfEnumOptionId')
        self.ArrayOfSubterraURIType = self.getTypeFromService('Tracker', 'ns1:ArrayOfSubterraURI')

    def _getTransport(self) -> Transport:
        """
        Gets the zeep transport object
        """
        transport = Transport()
        transport.session.verify = not self.skip_cert_verification
        return transport

    def hasService(self, name: str) -> bool:
        """
        Checks if a WSDL service is available
        """
        if name in self.services:
            return True
        return False

    def getService(self, name: str) -> str:  # TODO service type?
        """
        Get a WSDL service client. The name can be 'Tracker' or 'Session'
        """
        # request user info to see if we're still logged in
        try:
            _user = self.services['Project']['client'].service.getUser(self.user)
        except Exception:
            # if not, create a new session
            self._createSession()

        if name in self.services:
            return self.services[name]['client'].service
        else:
            raise Exception('Service does not exists')

    def getTypeFromService(self, name: str, type_name: str) -> str:  # TODO type name?
        """
        """
        if name in self.services:
            return self.services[name]['client'].get_type(type_name)
        else:
            raise Exception('Service does not exists')

    def getProject(self, project_id: str) -> Project:
        """Get a Polarion project

        :param project_id: The ID of the project.
        :return: The request project
        """
        return Project(self, project_id)

    def downloadFromSvn(self, url) -> Optional[bytes]:
        if self.svn_repo_url is not None:
            # user specified new url to try, use that instead of the default value
            orig_url = urlparse(url)
            orig_url_path_without_repo = '/'.join(orig_url.path.split('/')[2:])
            new_root_url = urlparse(self.svn_repo_url)
            new_repo_url = f'{new_root_url.scheme}://{new_root_url.netloc}/{new_root_url.path.strip("/")}/{orig_url_path_without_repo}'
            resp = requests.get(new_repo_url, auth=(self.user, self.password))
            if resp.ok:
                return resp.content
            raise Exception(f'Could not download attachment from {url}. Got error {resp.status_code}: {resp.reason}')
        else:
            # try the url that was given
            resp = requests.get(url, auth=(self.user, self.password))
            if resp.ok:
                return resp.content

            # if that fails then sneakily try downloading it with the default polarion SVN repo user and password
            resp_default = requests.get(url, auth=('polarion', 'aurora'))
            if resp_default.ok:
                return resp_default.content

            # if that also fails, tough luck.
            raise Exception(f'Could not download attachment from {url}. Got error {resp.status_code}: {resp.reason}.\n'
                            f'Trying with the default polarion login details yielded {resp_default.status_code}: {resp_default.reason}')

    def __repr__(self):
        return f'Polarion client for {self.url} with user {self.user}'

    def __str__(self):
        return f'Polarion client for {self.url} with user {self.user}'
