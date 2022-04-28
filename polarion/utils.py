import re
from abc import ABC
from html.parser import HTMLParser
from typing import Optional, Tuple

from polarion.project import Project
from xml.etree import ElementTree
from texttable import Texttable


class DescriptionParser(HTMLParser, ABC):

    def __init__(self, polarion_project: Optional[Project] = None):
        """A HTMLParser with to clean the HTML tags from a string.
        Can lookup Polarion links in HTML, present tables in a readable format and extracts formula's to text

        :param polarion_project: A polarion project used to search for the title of a workitem if the link type is 'long'.
        """
        super(DescriptionParser, self).__init__()
        self._polarion_project = polarion_project
        self._data = ''
        self._table_start = None
        self._table_end = None

    @property
    def data(self) -> str:
        """The parsed data"""
        return self._data

    def reset(self):
        """Reset the parsing state"""
        super(DescriptionParser, self).reset()
        self._data = ''
        self._table_start = None
        self._table_end = None

    def handle_data(self, data: str):
        """Handles the data within HTML tags
        
        :param data: the data inside a HTML tag
        """
        # handle data outside of table content
        if self._table_start is None:
            self._data += data

    # TODO: attrs type?
    def handle_starttag(self, tag: str, attrs: Tuple[str]):
        """Handles the start of a HTML tag. In some cases the start tag is the only tag and then it parses the attributes
        depending on the tag.
        
        :param tag: Tag identifier
        :param attrs: A tuple of attributes
        """
        # parse attributes to dict
        attributes = {}
        for attribute, value in attrs:
            attributes[attribute] = value

        if tag == 'span' and 'class' in attributes:
            if attributes['class'] == 'polarion-rte-link':
                self._handle_polarion_rte_link(attributes)
            elif attributes['class'] == 'polarion-rte-formula':
                self._handle_polarion_rte_formula(attributes)

        if tag == 'table':
            self._table_start = self.getpos()

    def handle_endtag(self, tag: str):
        """Handles the end of a tag.
        
        :param tag: Name of the tag
        """
        if tag == 'table':
            self._handle_table()

    def _handle_table(self):
        """Handles the HTML tables. It parses the table to a readable format."""
        # get the table HTML content
        self._table_end = self.getpos()
        table_content = self.rawdata.split('\n')
        correct_lines = table_content[self._table_start[0] - 1:self._table_end[0]]
        # iterate over table elements and parse to 2d array
        table = ElementTree.XML(''.join(correct_lines))
        content = []
        for tr in table.iter('tr'):
            content.append([])
            for th in tr.iter('th'):
                content[-1].append(th.text)
            for td in tr.iter('td'):
                content[-1].append(td.text)
        self._data += Texttable().add_rows(content).draw()
        self._table_start = None
        self._table_end = None

    # TODO: attrs type?
    def _handle_polarion_rte_link(self, attributes: Tuple[str]):
        """Gets either the workitem id from a link (short) or the workitem id and title (long)
        
        :param attributes: attributes to the link tag
        """
        if attributes['data-option-id'] == 'short' or (
                attributes['data-option-id'] == 'long' and self._polarion_project is None):
            self._data += attributes['data-item-id']
        else:
            linked_item = self._polarion_project.getWorkitem(
                attributes['data-item-id'])
            self._data += str(linked_item)

    # TODO: attrs type?
    def _handle_polarion_rte_formula(self, attributes: Tuple[str]):
        """Gets the formula for a polarion formula tag
        
        :param attributes: attributes to the formula tag
        """
        self._data += attributes['data-source']


def strip_html(raw_html: str) -> str:
    """Strips all HTML tags from HTML code leaving only plain text with no formatting.
    
    :param raw_html: HTML string
    :return: plain text string
    """
    clean = re.compile('<.*?>')
    clean_text = re.sub(clean, '', raw_html)
    return clean_text