######################################################################################################################
# Copyright (C) 2017-2022 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Provides functions to apply filtering based on scenarios to subqueries.

:author: Antti Soininen (VTT)
:date:   21.8.2020
"""

from functools import partial
from sqlalchemy import desc, func
from ..exception import SpineDBAPIError

SCENARIO_FILTER_TYPE = "scenario_filter"
SCENARIO_SHORTHAND_TAG = "scenario"


def apply_scenario_filter_to_subqueries(db_map, scenario):
    """
    Replaces affected subqueries in ``db_map`` such that they return only values of given scenario.

    Args:
        db_map (DatabaseMappingBase): a database map to alter
        scenario (str or int): scenario name or id
    """
    state = _ScenarioFilterState(db_map, scenario)
    make_parameter_value_sq = partial(_make_scenario_filtered_parameter_value_sq, state=state)
    db_map.override_parameter_value_sq_maker(make_parameter_value_sq)
    make_alternative_sq = partial(_make_scenario_filtered_alternative_sq, state=state)
    db_map.override_alternative_sq_maker(make_alternative_sq)
    make_scenario_sq = partial(_make_scenario_filtered_scenario_sq, state=state)
    db_map.override_scenario_sq_maker(make_scenario_sq)
    make_scenario_alternative_sq = partial(_make_scenario_filtered_scenario_alternative_sq, state=state)
    db_map.override_scenario_alternative_sq_maker(make_scenario_alternative_sq)


def scenario_filter_config(scenario):
    """
    Creates a config dict for scenario filter.

    Args:
        scenario (str): scenario name

    Returns:
        dict: filter configuration
    """
    return {"type": SCENARIO_FILTER_TYPE, "scenario": scenario}


def scenario_filter_from_dict(db_map, config):
    """
    Applies scenario filter to given database map.

    Args:
        db_map (DatabaseMappingBase): target database map
        config (dict): scenario filter configuration
    """
    apply_scenario_filter_to_subqueries(db_map, config["scenario"])


def scenario_name_from_dict(config):
    """
    Returns scenario's name from filter config.

    Args:
        config (dict): scenario filter configuration

    Returns:
        str: scenario name or None if ``config`` is not a valid scenario filter configuration
    """
    return None if config["type"] != SCENARIO_FILTER_TYPE else config["scenario"]


def scenario_filter_config_to_shorthand(config):
    """
    Makes a shorthand string from scenario filter configuration.

    Args:
        config (dict): scenario filter configuration

    Returns:
        str: a shorthand string
    """
    return f"{SCENARIO_SHORTHAND_TAG}:" + config["scenario"]


def scenario_filter_shorthand_to_config(shorthand):
    """
    Makes configuration dictionary out of a shorthand string.

    Args:
        shorthand (str): a shorthand string

    Returns:
        dict: scenario filter configuration
    """
    _, _, scenario = shorthand.partition(":")
    return scenario_filter_config(scenario)


class _ScenarioFilterState:
    """
    Internal state for :func:`_make_scenario_filtered_parameter_value_sq`.

    Attributes:
        original_alternative_sq (Alias): previous ``alternative_sq``
        original_parameter_value_sq (Alias): previous ``parameter_value_sq``
        original_scenario_alternative_sq (Alias): previous ``scenario_alternative_sq``
        original_scenario_sq (Alias): previous ``scenario_sq``
        scenario_alternative_ids (list of int): ids of selected scenario's alternatives
        scenario_id (int): id of selected scenario
    """

    def __init__(self, db_map, scenario):
        """
        Args:
            db_map (DatabaseMappingBase): database the state applies to
            scenario (str or int): scenario name or ids
        """
        self.original_parameter_value_sq = db_map.parameter_value_sq
        self.original_scenario_sq = db_map.scenario_sq
        self.original_scenario_alternative_sq = db_map.scenario_alternative_sq
        self.original_alternative_sq = db_map.alternative_sq
        self.scenario_id = self._scenario_id(db_map, scenario)
        self.scenario_alternative_ids, self.alternative_ids = self._scenario_alternative_ids(db_map)

    @staticmethod
    def _scenario_id(db_map, scenario):
        """
        Finds id for given scenario.

        Args:
            db_map (DatabaseMappingBase): a database map
            scenario (str or int): scenario name or id

        Returns:
            int: scenario's id
        """
        if isinstance(scenario, str):
            scenario_name = scenario
            scenario_id = (
                db_map.query(db_map.scenario_sq.c.id).filter(db_map.scenario_sq.c.name == scenario_name).scalar()
            )
            if scenario_id is None:
                raise SpineDBAPIError(f"Scenario '{scenario_name}' not found.")
            return scenario_id
        scenario_id = scenario
        scenario = db_map.query(db_map.scenario_sq).filter(db_map.scenario_sq.c.id == scenario_id).one_or_none()
        if scenario is None:
            raise SpineDBAPIError(f"Scenario id {scenario_id} not found.")
        return scenario_id

    def _scenario_alternative_ids(self, db_map):
        """
        Finds scenario alternative and alternative ids of current scenario.

        Args:
            db_map (DatabaseMappingBase): a database map

        Returns:
            tuple: scenario alternative ids and alternative ids
        """
        alternative_ids = []
        scenario_alternative_ids = []
        for row in db_map.query(db_map.scenario_alternative_sq).filter(
            db_map.scenario_alternative_sq.c.scenario_id == self.scenario_id
        ):
            scenario_alternative_ids.append(row.id)
            alternative_ids.append(row.alternative_id)
        return scenario_alternative_ids, alternative_ids


def _make_scenario_filtered_parameter_value_sq(db_map, state):
    """
    Returns a scenario filtering subquery similar to :func:`DatabaseMappingBase.parameter_value_sq`.

    This function can be used as replacement for parameter value subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_ScenarioFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for parameter value filtered by selected scenario
    """
    ext_parameter_value_sq = (
        db_map.query(
            state.original_parameter_value_sq,
            func.row_number()
            .over(
                partition_by=[
                    state.original_parameter_value_sq.c.parameter_definition_id,
                    state.original_parameter_value_sq.c.entity_id,
                ],
                order_by=desc(db_map.scenario_alternative_sq.c.rank),
            )
            .label("max_rank_row_number"),
        )
        .filter(state.original_parameter_value_sq.c.alternative_id == db_map.scenario_alternative_sq.c.alternative_id)
        .filter(db_map.scenario_alternative_sq.c.scenario_id == state.scenario_id)
    ).subquery()
    return db_map.query(ext_parameter_value_sq).filter(ext_parameter_value_sq.c.max_rank_row_number == 1).subquery()


def _make_scenario_filtered_alternative_sq(db_map, state):
    """
    Returns an alternative filtering subquery similar to :func:`DatabaseMappingBase.alternative_sq`.

    This function can be used as replacement for alternative subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_ScenarioFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for alternative filtered by selected scenario
    """
    alternative_sq = state.original_alternative_sq
    return db_map.query(alternative_sq).filter(alternative_sq.c.id.in_(state.alternative_ids)).subquery()


def _make_scenario_filtered_scenario_sq(db_map, state):
    """
    Returns a scenario filtering subquery similar to :func:`DatabaseMappingBase.scenario_sq`.

    This function can be used as replacement for scenario subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_ScenarioFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for scenario filtered by selected scenario
    """
    scenario_sq = state.original_scenario_sq
    return db_map.query(scenario_sq).filter(scenario_sq.c.id == state.scenario_id).subquery()


def _make_scenario_filtered_scenario_alternative_sq(db_map, state):
    """
    Returns a scenario alternative filtering subquery similar to :func:`DatabaseMappingBase.scenario_alternative_sq`.

    This function can be used as replacement for scenario alternative subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_ScenarioFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for scenario alternative filtered by selected scenario
    """
    scenario_alternative_sq = state.original_scenario_alternative_sq
    return (
        db_map.query(scenario_alternative_sq)
        .filter(scenario_alternative_sq.c.id.in_(state.scenario_alternative_ids))
        .subquery()
    )
