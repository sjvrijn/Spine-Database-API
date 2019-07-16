######################################################################################################################
# Copyright (C) 2017 - 2019 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Tests for the parameter_value module.

:authors: A. Soininen (VTT)
:date:   7.6.2019
"""

from datetime import datetime
import json
import unittest
import dateutil.parser
from dateutil.relativedelta import relativedelta
import numpy as np
import numpy.testing
from spinedb_api.parameter_value import (
    duration_to_relativedelta,
    from_database,
    to_database,
    DateTime,
    Duration,
    TimePattern,
    TimeSeriesFixedResolution,
    TimeSeriesVariableResolution,
)


class TestParameterValue(unittest.TestCase):
    """Test for the free functions and classes in parameter_value."""

    def test_duration_to_relativedelta_seconds(self):
        delta = duration_to_relativedelta("7s")
        self.assertEqual(delta, relativedelta(seconds=7))
        delta = duration_to_relativedelta("1 second")
        self.assertEqual(delta, relativedelta(seconds=1))
        delta = duration_to_relativedelta("7 seconds")
        self.assertEqual(delta, relativedelta(seconds=7))

    def test_duration_to_relativedelta_minutes(self):
        delta = duration_to_relativedelta("7m")
        self.assertEqual(delta, relativedelta(minutes=7))
        delta = duration_to_relativedelta("1 minute")
        self.assertEqual(delta, relativedelta(minutes=1))
        delta = duration_to_relativedelta("7 minutes")
        self.assertEqual(delta, relativedelta(minutes=7))

    def test_duration_to_relativedelta_hours(self):
        delta = duration_to_relativedelta("7h")
        self.assertEqual(delta, relativedelta(hours=7))
        delta = duration_to_relativedelta("1 hour")
        self.assertEqual(delta, relativedelta(hours=1))
        delta = duration_to_relativedelta("7 hours")
        self.assertEqual(delta, relativedelta(hours=7))

    def test_duration_to_relativedelta_days(self):
        delta = duration_to_relativedelta("7D")
        self.assertEqual(delta, relativedelta(days=7))
        delta = duration_to_relativedelta("1 day")
        self.assertEqual(delta, relativedelta(days=1))
        delta = duration_to_relativedelta("7 days")
        self.assertEqual(delta, relativedelta(days=7))

    def test_duration_to_relativedelta_months(self):
        delta = duration_to_relativedelta("7M")
        self.assertEqual(delta, relativedelta(months=7))
        delta = duration_to_relativedelta("1 month")
        self.assertEqual(delta, relativedelta(months=1))
        delta = duration_to_relativedelta("7 months")
        self.assertEqual(delta, relativedelta(months=7))

    def test_duration_to_relativedelta_years(self):
        delta = duration_to_relativedelta("7Y")
        self.assertEqual(delta, relativedelta(years=7))
        delta = duration_to_relativedelta("7Y")
        self.assertEqual(delta, relativedelta(years=7))
        delta = duration_to_relativedelta("1 year")
        self.assertEqual(delta, relativedelta(years=1))
        delta = duration_to_relativedelta("7 years")
        self.assertEqual(delta, relativedelta(years=7))

    def test_from_database_plain_number(self):
        database_value = "23.0"
        value = from_database(database_value)
        self.assertTrue(isinstance(value, float))
        self.assertEqual(value, 23.0)

    def test_to_database_plain_number(self):
        value = 23.0
        database_value = to_database(value)
        value_as_float = json.loads(database_value)
        self.assertEqual(value_as_float, value)

    def test_to_database_DateTime(self):
        value = DateTime(
            datetime(year=2019, month=6, day=26, hour=12, minute=50, second=13)
        )
        database_value = to_database(value)
        value_as_dict = json.loads(database_value)
        self.assertEqual(
            value_as_dict, {"type": "date_time", "data": "2019-06-26T12:50:13"}
        )

    def test_from_database_DateTime(self):
        database_value = '{"type": "date_time", "data": "2019-06-01T22:15:00+01:00"}'
        value = from_database(database_value)
        self.assertEqual(
            value.value, datetime.fromisoformat("2019-06-01T22:15:00+01:00")
        )

    def test_DateTime_to_database(self):
        value = DateTime(
            datetime(year=2019, month=6, day=26, hour=10, minute=50, second=34)
        )
        database_value = value.to_database()
        value_dict = json.loads(database_value)
        self.assertEqual(
            value_dict, {"type": "date_time", "data": "2019-06-26T10:50:34"}
        )

    def test_from_database_Duration(self):
        database_value = '{"type": "duration", "data": "4 seconds"}'
        value = from_database(database_value)
        self.assertEqual(value.value, relativedelta(seconds=4))

    def test_from_database_Duration_default_units(self):
        database_value = '{"type": "duration", "data": 23}'
        value = from_database(database_value)
        self.assertEqual(value.value, relativedelta(minutes=23))

    def test_from_database_Duration_as_list(self):
        database_value = '{"type": "duration", "data": ["1 hour", "1h", 60, "2 hours"]}'
        value = from_database(database_value)
        expected = [
            relativedelta(hours=1),
            relativedelta(hours=1),
            relativedelta(minutes=60),
            relativedelta(hours=2),
        ]
        self.assertEqual(value.value, expected)

    def test_Duration_to_database(self):
        value = Duration(duration_to_relativedelta("8 years"))
        database_value = value.to_database()
        value_as_dict = json.loads(database_value)
        self.assertEqual(value_as_dict, {"type": "duration", "data": "8Y"})

    def test_Duration_to_database_as_list(self):
        value = Duration([relativedelta(years=1), "3 minutes"])
        database_value = value.to_database()
        value_as_dict = json.loads(database_value)
        self.assertEqual(value_as_dict, {"type": "duration", "data": ["1Y", "3m"]})

    def test_from_database_TimePattern(self):
        database_value = """
        {
          "type": "time_pattern",
          "data": {  
            "m1-4,m9-12": 300,
            "m5-8": 221.5
          }
        }
        """
        value = from_database(database_value)
        self.assertEqual(len(value), 2)
        numpy.testing.assert_equal(value.indexes, ["m1-4,m9-12", "m5-8"])
        numpy.testing.assert_equal(value.values, numpy.array([300.0, 221.5]))

    def test_TimePattern_to_database(self):
        value = TimePattern(["m1-4,m9-12", "m5-8"], numpy.array([300.0, 221.5]))
        database_value = value.to_database()
        value_as_dict = json.loads(database_value)
        self.assertEqual(
            value_as_dict,
            {"type": "time_pattern", "data": {"m1-4,m9-12": 300.0, "m5-8": 221.5}},
        )

    def test_from_database_TimeSeriesVariableResolution_as_dictionary(self):
        releases = """{
                          "type": "time_series",
                          "data": {
                              "1977-05-25": 4,
                              "1980-05-21": 5,
                              "1983-05-25": 6
                          }
                      }"""
        time_series = from_database(releases)
        numpy.testing.assert_equal(
            time_series.indexes,
            numpy.array(
                [
                    numpy.datetime64("1977-05-25"),
                    numpy.datetime64("1980-05-21"),
                    numpy.datetime64("1983-05-25"),
                ],
                dtype="datetime64[D]",
            ),
        )
        self.assertEqual(len(time_series), 3)
        self.assertTrue(isinstance(time_series.values, numpy.ndarray))
        numpy.testing.assert_equal(time_series.values, numpy.array([4, 5, 6]))

    def test_from_database_TimeSeriesVariableResolution_as_two_column_array(self):
        releases = """{
                          "type": "time_series",
                          "data": [
                              ["1977-05-25", 4],
                              ["1980-05-21", 5],
                              ["1983-05-25", 6]
                          ]
                      }"""
        time_series = from_database(releases)
        numpy.testing.assert_equal(
            time_series.indexes,
            numpy.array(
                [
                    numpy.datetime64("1977-05-25"),
                    numpy.datetime64("1980-05-21"),
                    numpy.datetime64("1983-05-25"),
                ],
                dtype="datetime64[D]",
            ),
        )
        self.assertEqual(len(time_series), 3)
        self.assertTrue(isinstance(time_series.values, numpy.ndarray))
        numpy.testing.assert_equal(time_series.values, numpy.array([4, 5, 6]))

    def test_from_database_TimeSeriesFixedResolution_default_repeat(self):
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "ignore_year": true
                                   },
                                   "data": [["2019-07-02T10:00:00", 7.0],
                                            ["2019-07-02T10:00:01", 4.0]]
                               }"""
        time_series = from_database(database_value)
        self.assertTrue(time_series.ignore_year)
        self.assertFalse(time_series.repeat)

    def test_TimeSeriesVariableResolution_to_database(self):
        dates = numpy.array(
            ["1999-05-19", "2002-05-16", "2005-05-19"], dtype="datetime64[D]"
        )
        episodes = numpy.array([1, 2, 3], dtype=float)
        value = TimeSeriesVariableResolution(dates, episodes, False, False)
        as_json = value.to_database()
        releases = json.loads(as_json)
        self.assertEqual(
            releases,
            {
                "type": "time_series",
                "data": {"1999-05-19": 1, "2002-05-16": 2, "2005-05-19": 3},
            },
        )

    def test_TimeSeriesVariableResolution_to_database_with_ignore_year_and_repeat(self):
        dates = numpy.array(
            ["1999-05-19", "2002-05-16", "2005-05-19"], dtype="datetime64[D]"
        )
        episodes = numpy.array([1, 2, 3], dtype=float)
        value = TimeSeriesVariableResolution(dates, episodes, True, True)
        as_json = value.to_database()
        releases = json.loads(as_json)
        self.assertEqual(
            releases,
            {
                "type": "time_series",
                "data": {"1999-05-19": 1, "2002-05-16": 2, "2005-05-19": 3},
                "index": {"ignore_year": True, "repeat": True},
            },
        )

    def test_from_database_TimeSeriesFixedResolution(self):
        days_of_our_lives = """{
                                   "type": "time_series",
                                   "index": {
                                       "start": "2019-03-23",
                                       "resolution": "1 day",
                                       "ignore_year": false,
                                       "repeat": false
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(days_of_our_lives)
        self.assertEqual(len(time_series), 3)
        numpy.testing.assert_equal(
            time_series.indexes,
            numpy.array(
                [
                    numpy.datetime64("2019-03-23"),
                    numpy.datetime64("2019-03-24"),
                    numpy.datetime64("2019-03-25"),
                ],
                dtype="datetime64[s]",
            ),
        )
        self.assertTrue(isinstance(time_series.values, numpy.ndarray))
        numpy.testing.assert_equal(time_series.values, numpy.array([7.0, 5.0, 8.1]))
        self.assertEqual(time_series.start, datetime.fromisoformat("2019-03-23"))
        self.assertEqual(len(time_series.resolution), 1)
        self.assertEqual(time_series.resolution[0], relativedelta(days=1))
        self.assertFalse(time_series.ignore_year)
        self.assertFalse(time_series.repeat)

    def test_from_database_TimeSeriesFixedResolution_no_index(self):
        database_value = """{
                                "type": "time_series",
                                "data": [1, 2, 3, 4, 5, 8]
                            }
        """
        time_series = from_database(database_value)
        self.assertEqual(len(time_series), 6)
        numpy.testing.assert_equal(
            time_series.indexes,
            numpy.array(
                [
                    numpy.datetime64("0001-01-01T00:00:00"),
                    numpy.datetime64("0001-01-01T01:00:00"),
                    numpy.datetime64("0001-01-01T02:00:00"),
                    numpy.datetime64("0001-01-01T03:00:00"),
                    numpy.datetime64("0001-01-01T04:00:00"),
                    numpy.datetime64("0001-01-01T05:00:00"),
                ],
                dtype="datetime64[s]",
            ),
        )
        numpy.testing.assert_equal(
            time_series.values, numpy.array([1.0, 2.0, 3.0, 4.0, 5.0, 8.0])
        )
        self.assertEqual(
            time_series.start, datetime.fromisoformat("0001-01-01T00:00:00")
        )
        self.assertEqual(len(time_series.resolution), 1)
        self.assertEqual(time_series.resolution[0], relativedelta(hours=1))
        self.assertTrue(time_series.ignore_year)
        self.assertTrue(time_series.repeat)

    def test_from_database_TimeSeriesFixedResolution_resolution_list(self):
        database_value = """{
                                "type": "time_series",
                                "index": {
                                    "start": "2019-01-31",
                                    "resolution": ["1 day", "1M"],
                                    "ignore_year": false,
                                    "repeat": false
                                },
                                "data": [7.0, 5.0, 8.1, -4.1]
                            }"""
        time_series = from_database(database_value)
        self.assertEqual(len(time_series), 4)
        numpy.testing.assert_equal(
            time_series.indexes,
            numpy.array(
                [
                    numpy.datetime64("2019-01-31"),
                    numpy.datetime64("2019-02-01"),
                    numpy.datetime64("2019-03-01"),
                    numpy.datetime64("2019-03-02"),
                ],
                dtype="datetime64[s]",
            ),
        )
        numpy.testing.assert_equal(
            time_series.values, numpy.array([7.0, 5.0, 8.1, -4.1])
        )
        self.assertEqual(time_series.start, datetime.fromisoformat("2019-01-31"))
        self.assertEqual(len(time_series.resolution), 2)
        self.assertEqual(
            time_series.resolution, [relativedelta(days=1), relativedelta(months=1)]
        )
        self.assertFalse(time_series.ignore_year)
        self.assertFalse(time_series.repeat)

    def test_from_database_TimeSeriesFixedResolution_default_resolution_is_1hour(self):
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "start": "2019-03-23",
                                       "ignore_year": false,
                                       "repeat": false
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(database_value)
        self.assertEqual(len(time_series), 3)
        self.assertEqual(len(time_series.resolution), 1)
        self.assertEqual(time_series.resolution[0], relativedelta(hours=1))

    def test_from_database_TimeSeriesFixedResolution_default_resolution_unit_is_minutes(
        self
    ):
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "start": "2019-03-23",
                                       "resolution": 30
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(database_value)
        self.assertEqual(len(time_series), 3)
        self.assertEqual(len(time_series.resolution), 1)
        self.assertEqual(time_series.resolution[0], relativedelta(minutes=30))
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "start": "2019-03-23",
                                       "resolution": [30, 45]
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(database_value)
        self.assertEqual(len(time_series), 3)
        self.assertEqual(len(time_series.resolution), 2)
        self.assertEqual(time_series.resolution[0], relativedelta(minutes=30))
        self.assertEqual(time_series.resolution[1], relativedelta(minutes=45))

    def test_from_database_TimeSeriesFixedResolution_default_ignore_year(self):
        # Should be false if start is given
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "start": "2019-03-23",
                                       "resolution": "1 day",
                                       "repeat": false
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(database_value)
        self.assertFalse(time_series.ignore_year)
        # Should be true if start is omitted
        database_value = """{
                                   "type": "time_series",
                                   "index": {
                                       "resolution": "1 day",
                                       "repeat": false
                                   },
                                   "data": [7.0, 5.0, 8.1]
                               }"""
        time_series = from_database(database_value)
        self.assertTrue(time_series.ignore_year)

    def test_TimeSeriesFixedResolution_to_database(self):
        values = numpy.array([3, 2, 4], dtype=float)
        resolution = [duration_to_relativedelta("1 months")]
        start = datetime(year=2007, month=6, day=1)
        value = TimeSeriesFixedResolution(start, resolution, values, True, True)
        as_json = value.to_database()
        releases = json.loads(as_json)
        self.assertEqual(
            releases,
            {
                "type": "time_series",
                "index": {
                    "start": "2007-06-01 00:00:00",
                    "resolution": "1M",
                    "ignore_year": True,
                    "repeat": True,
                },
                "data": [3, 2, 4],
            },
        )

    def test_TimeSeriesFixedResolution_resolution_list_to_database(self):
        start = datetime(year=2007, month=1, day=1)
        resolutions = ["1 month", "1 year"]
        resolutions = [duration_to_relativedelta(r) for r in resolutions]
        values = numpy.array([3.0, 2.0, 4.0])
        value = TimeSeriesFixedResolution(start, resolutions, values, True, True)
        as_json = value.to_database()
        releases = json.loads(as_json)
        self.assertEqual(
            releases,
            {
                "type": "time_series",
                "index": {
                    "start": "2007-01-01 00:00:00",
                    "resolution": ["1M", "1Y"],
                    "ignore_year": True,
                    "repeat": True,
                },
                "data": [3.0, 2.0, 4.0],
            },
        )

    def test_TimeSeriesFixedResolution_init_conversions(self):
        series = TimeSeriesFixedResolution(
            "2019-01-03T00:30:33", "1D", [3.0, 2.0, 1.0], False, False
        )
        self.assertTrue(isinstance(series.start, datetime))
        self.assertTrue(isinstance(series.resolution, list))
        for element in series.resolution:
            self.assertTrue(isinstance(element, relativedelta))
        self.assertTrue(isinstance(series.values, numpy.ndarray))
        series = TimeSeriesFixedResolution(
            "2019-01-03T00:30:33", ["2h", "4h"], [3.0, 2.0, 1.0], False, False
        )
        self.assertTrue(isinstance(series.resolution, list))
        for element in series.resolution:
            self.assertTrue(isinstance(element, relativedelta))

    def test_TimeSeriesVariableResolution_init_conversion(self):
        series = TimeSeriesVariableResolution(
            ["2008-07-08T03:00", "2008-08-08T13:30"], [3.3, 4.4], True, True
        )
        self.assertTrue(isinstance(series.indexes, np.ndarray))
        for index in series.indexes:
            self.assertTrue(isinstance(index, np.datetime64))
        self.assertTrue(isinstance(series.values, np.ndarray))

    def test_DateTime_equality(self):
        date_time = DateTime(dateutil.parser.parse("2019-07-03T09:09:09"))
        self.assertEqual(date_time, date_time)
        equal_date_time = DateTime(dateutil.parser.parse("2019-07-03T09:09:09"))
        self.assertEqual(date_time, equal_date_time)
        inequal_date_time = DateTime(dateutil.parser.parse("2018-07-03T09:09:09"))
        self.assertNotEqual(date_time, inequal_date_time)

    def test_Duration_equality(self):
        duration = Duration(duration_to_relativedelta("3 minutes"))
        self.assertEqual(duration, duration)
        equal_duration = Duration(duration_to_relativedelta("3m"))
        self.assertEqual(duration, equal_duration)
        inequal_duration = Duration(duration_to_relativedelta("3 seconds"))
        self.assertNotEqual(duration, inequal_duration)

    def test_TimePattern_equality(self):
        pattern = TimePattern(["1d", "2-7d"], np.array([-2.3, -5.0]))
        self.assertEqual(pattern, pattern)
        equal_pattern = TimePattern(["1d", "2-7d"], np.array([-2.3, -5.0]))
        self.assertEqual(pattern, equal_pattern)
        inequal_pattern = TimePattern(["1-3m", "4-12m"], np.array([-5.0, 23.0]))
        self.assertNotEqual(pattern, inequal_pattern)

    def test_TimeSeriesFixedResolution_equality(self):
        series = TimeSeriesFixedResolution(
            "2019-01-03T00:30:33", "1D", [3.0, 2.0, 1.0], False, False
        )
        self.assertEqual(series, series)
        equal_series = TimeSeriesFixedResolution(
            "2019-01-03T00:30:33", "1D", [3.0, 2.0, 1.0], False, False
        )
        self.assertEqual(series, equal_series)
        inequal_series = TimeSeriesFixedResolution(
            "2019-01-03T00:30:33", "1D", [3.0, 2.0, 1.0], True, False
        )
        self.assertNotEqual(series, inequal_series)

    def test_TimeSeriesVariableResolution_equality(self):
        series = TimeSeriesVariableResolution(
            ["2000-01-01T00:00", "2001-01-01T00:00"], [4.2, 2.4], True, True
        )
        self.assertEqual(series, series)
        equal_series = TimeSeriesVariableResolution(
            ["2000-01-01T00:00", "2001-01-01T00:00"], [4.2, 2.4], True, True
        )
        self.assertEqual(series, equal_series)
        inequal_series = TimeSeriesVariableResolution(
            ["2000-01-01T00:00", "2002-01-01T00:00"], [4.2, 2.4], True, True
        )
        self.assertNotEqual(series, inequal_series)


if __name__ == "__main__":
    unittest.main()