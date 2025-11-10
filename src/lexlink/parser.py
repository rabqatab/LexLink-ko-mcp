"""
XML/HTML parsing utilities for law.go.kr API responses.

Provides functions to parse XML responses and extract structured data
for ranking and further processing.
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


def parse_xml_response(xml_content: str) -> Optional[Dict[str, Any]]:
    """
    Parse law.go.kr XML response into structured dictionary.

    Args:
        xml_content: XML string from API response

    Returns:
        Parsed dictionary with extracted data, or None if parsing fails

    Examples:
        >>> xml = '''<?xml version="1.0"?>
        ... <LawSearch>
        ...   <totalCnt>2</totalCnt>
        ...   <law id="1">
        ...     <법령명한글><![CDATA[민법]]></법령명한글>
        ...   </law>
        ... </LawSearch>'''
        >>> result = parse_xml_response(xml)
        >>> result['totalCnt']
        '2'
        >>> len(result['law'])
        1
    """
    try:
        root = ET.fromstring(xml_content)
        return _element_to_dict(root)
    except ET.ParseError as e:
        logger.warning(f"XML parsing failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing XML: {e}")
        return None


def _element_to_dict(element: ET.Element) -> Dict[str, Any]:
    """
    Recursively convert XML element to dictionary.

    Args:
        element: XML element from ElementTree

    Returns:
        Dictionary representation of the element
    """
    result = {}

    # Add attributes
    if element.attrib:
        result.update(element.attrib)

    # Add text content
    if element.text and element.text.strip():
        if len(element) == 0:  # No children - leaf node
            return element.text.strip()
        result['_text'] = element.text.strip()

    # Process children
    for child in element:
        child_data = _element_to_dict(child)
        child_tag = child.tag

        # Handle multiple elements with same tag (make it a list)
        if child_tag in result:
            if not isinstance(result[child_tag], list):
                result[child_tag] = [result[child_tag]]
            result[child_tag].append(child_data)
        else:
            result[child_tag] = child_data

    return result if result else element.text


def extract_law_list(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract law list from parsed XML data.

    Handles both single law and multiple law responses.

    Args:
        parsed_data: Parsed dictionary from parse_xml_response()

    Returns:
        List of law dictionaries

    Examples:
        >>> data = {'law': {'법령명한글': '민법'}}
        >>> extract_law_list(data)
        [{'법령명한글': '민법'}]

        >>> data = {'law': [{'법령명한글': '민법'}, {'법령명한글': '형법'}]}
        >>> len(extract_law_list(data))
        2
    """
    if not parsed_data or 'law' not in parsed_data:
        return []

    laws = parsed_data['law']

    # Ensure laws is a list
    if not isinstance(laws, list):
        laws = [laws] if laws else []

    return laws


def update_law_list(parsed_data: Dict[str, Any], ranked_laws: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Update parsed data with ranked law list.

    Args:
        parsed_data: Original parsed dictionary
        ranked_laws: Re-ranked list of laws

    Returns:
        Updated dictionary with ranked laws
    """
    if not parsed_data:
        return parsed_data

    # Update the law list
    parsed_data['law'] = ranked_laws

    return parsed_data
