######################################################################################################################
# Copyright (C) 2017 - 2020 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Tools and utilities to embed filtering information to database URLs.

:author: A. Soininen
:date:   7.10.2020
"""
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from .alternative_filter import (
    alternative_filter_config_to_shorthand,
    ALTERNATIVE_FILTER_SHORTHAND_TAG,
    alternative_filter_shorthand_to_config,
    ALTERNATIVE_FILTER_TYPE,
)
from .renamer import (
    entity_class_renamer_config_to_shorthand,
    ENTITY_CLASS_RENAMER_SHORTHAND_TAG,
    entity_class_renamer_shorthand_to_config,
    ENTITY_CLASS_RENAMER_TYPE,
)
from .scenario_filter import (
    scenario_filter_config_to_shorthand,
    SCENARIO_FILTER_TYPE,
    SCENARIO_SHORTHAND_TAG,
    scenario_filter_shorthand_to_config,
)
from .tool_filter import (
    tool_filter_config_to_shorthand,
    TOOL_FILTER_SHORTHAND_TAG,
    tool_filter_shorthand_to_config,
    TOOL_FILTER_TYPE,
)

FILTER_IDENTIFIER = "spinedbfilter"
SHORTHAND_TAG = "cfg:"


def append_filter_config(url, config):
    """
    Appends a filter config to given url.

    ``config`` can either be a configuration dictionary or a path to a JSON file that contains the dictionary.

    Args:
        url (str): base URL
        config (str or dict): path to the config file or config as a ``dict``.

    Returns:
        str: the modified URL
    """
    url = urlparse(url)
    query = parse_qs(url.query)
    filters = query.setdefault(FILTER_IDENTIFIER, list())
    if isinstance(config, dict):
        config = _config_to_shorthand(config)
    filters.append(config)
    url = url._replace(query=urlencode(query, doseq=True), path="//" + url.path)
    return url.geturl()


def pop_filter_configs(url):
    """
    Pops filter config files and dicts from URL's query part.

    Args:
        url (str): a URL

    Returns:
        tuple: a list of filter configs and the 'popped from' URL
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    try:
        filters = query.pop(FILTER_IDENTIFIER)
    except KeyError:
        return [], url
    parsed_filters = list()
    for filter_ in filters:
        if filter_.startswith(SHORTHAND_TAG):
            parsed_filters.append(_parse_shorthand(filter_[len(SHORTHAND_TAG) :]))
        else:
            parsed_filters.append(filter_)
    parsed = parsed._replace(query=urlencode(query, doseq=True), path="//" + parsed.path)
    return parsed_filters, urlunparse(parsed)


def clear_filter_configs(url):
    """
    Removes filter configuration queries from given URL.

    Args:
        url (str): a URL

    Returns:
        str: a cleared URL
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    try:
        del query[FILTER_IDENTIFIER]
    except KeyError:
        return url
    parsed = parsed._replace(query=urlencode(query, doseq=True), path="//" + parsed.path)
    return urlunparse(parsed)


def _config_to_shorthand(config):
    """
    Converts a filter config dictionary to shorthand.

    Args:
        config (dict): filter configuration

    Returns:
        str: config shorthand
    """
    shorthands = {
        ALTERNATIVE_FILTER_TYPE: alternative_filter_config_to_shorthand,
        ENTITY_CLASS_RENAMER_TYPE: entity_class_renamer_config_to_shorthand,
        SCENARIO_FILTER_TYPE: scenario_filter_config_to_shorthand,
        TOOL_FILTER_TYPE: tool_filter_config_to_shorthand,
    }
    return SHORTHAND_TAG + shorthands[config["type"]](config)


def _parse_shorthand(shorthand):
    """
    Converts shorthand filter config into configuration dictionary.

    Args:
        shorthand (str): a shorthand config string

    Returns:
        dict: filter configuration dictionary
    """
    shorthand_parsers = {
        ALTERNATIVE_FILTER_SHORTHAND_TAG: alternative_filter_shorthand_to_config,
        ENTITY_CLASS_RENAMER_SHORTHAND_TAG: entity_class_renamer_shorthand_to_config,
        SCENARIO_SHORTHAND_TAG: scenario_filter_shorthand_to_config,
        TOOL_FILTER_SHORTHAND_TAG: tool_filter_shorthand_to_config,
    }
    tag, _, _ = shorthand.partition(":")
    return shorthand_parsers[tag](shorthand)
