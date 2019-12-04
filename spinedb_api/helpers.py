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
General helper functions and classes.

:author: Manuel Marin (KTH)
:date:   15.8.2018
"""

import warnings
from sqlalchemy import (
    create_engine,
    Table,
    Column,
    MetaData,
    select,
    inspect,
    String,
    Float,
    Integer,
    BigInteger,
    null,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
)
from sqlalchemy.ext.automap import generate_relationship
from sqlalchemy.engine import reflection
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.mysql import TINYINT, DOUBLE
from sqlalchemy.orm import interfaces
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.environment import EnvironmentContext
from .exception import SpineDBAPIError, SpineDBVersionError
from .import_functions import import_data
from spinedb_api.parameter_value import Duration, DateTime as Date

# Supported dialects and recommended dbapi. Restricted to mysql and sqlite for now:
# - sqlite works
# - mysql is trying to work
SUPPORTED_DIALECTS = {
    "mysql": "pymysql",
    "sqlite": "sqlite3",
    # "mssql": "pyodbc",
    # "postgresql": "psycopg2",
    # "oracle": "cx_oracle",
}


naming_convention = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

model_meta = MetaData(naming_convention=naming_convention)

# NOTE: Deactivated since foreign keys are too difficult to get right in the diff tables.
# For example, the diff_object table would need a `class_id` field and a `diff_class_id` field,
# plus a CHECK constraint that at least one of the two is NOT NULL.
# @event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    module_name = dbapi_connection.__class__.__module__
    if not module_name.lower().startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@compiles(TINYINT, "sqlite")
def compile_TINYINT_mysql_sqlite(element, compiler, **kw):
    """ Handles mysql TINYINT datatype as INTEGER in sqlite """
    return compiler.visit_INTEGER(element, **kw)


@compiles(DOUBLE, "sqlite")
def compile_DOUBLE_mysql_sqlite(element, compiler, **kw):
    """ Handles mysql DOUBLE datatype as REAL in sqlite """
    return compiler.visit_REAL(element, **kw)


def attr_dict(item):
    """A dictionary of all attributes of item."""
    return {c.key: getattr(item, c.key) for c in inspect(item).mapper.column_attrs}


def is_head(db_url, upgrade=False):
    """Check whether or not db_url is head.

    Args:
        db_url (str): database url
        upgrade (Bool): if True, upgrade db to head
    """
    engine = create_engine(db_url)
    return is_head_from_engine(engine, upgrade=upgrade)


def is_head_from_engine(engine, upgrade=False):
    """Check whether or not engine is head.

    Args:
        engine (Engine): database engine
        upgrade (Bool): if True, upgrade db to head
    """
    config = Config()
    config.set_main_option("script_location", "spinedb_api:alembic")
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        current_rev = migration_context.get_current_revision()
        if current_rev == head:
            return True
        if not upgrade:
            return False
        # Upgrade function
        def fn(rev, context):
            return script._upgrade_revs("head", rev)

        with EnvironmentContext(
            config, script, fn=fn, as_sql=False, starting_rev=None, destination_rev="head", tag=None
        ) as environment_context:
            environment_context.configure(connection=connection, target_metadata=model_meta)
            with environment_context.begin_transaction():
                environment_context.run_migrations()
    return True


def copy_database(dest_url, source_url, overwrite=True, upgrade=False, only_tables=(), skip_tables=()):
    """Copy the database from source_url into dest_url."""
    if not is_head(source_url, upgrade=upgrade):
        raise SpineDBVersionError(url=source_url)
    source_engine = create_engine(source_url)
    dest_engine = create_engine(dest_url)
    insp = inspect(dest_engine)
    meta = MetaData()
    meta.reflect(source_engine)
    if insp.get_table_names():
        if not overwrite:
            raise SpineDBAPIError(
                "The database at '{}' is not empty. "
                "If you want to overwrite it, please pass the argument `overwrite=True` "
                "to the function call.".format(dest_url)
            )
        meta.drop_all(dest_engine)
    source_meta = MetaData(bind=source_engine)
    dest_meta = MetaData(bind=dest_engine)
    for t in meta.sorted_tables:
        # Create table in dest
        source_table = Table(t, source_meta, autoload=True)
        source_table.create(dest_engine)
        if t.name not in ("alembic_version", "next_id"):
            # Skip tables according to `only_tables` and `skip_tables`
            if only_tables and t.name not in only_tables:
                continue
            if t.name in skip_tables:
                continue
        dest_table = Table(source_table, dest_meta, autoload=True)
        sel = select([source_table])
        result = source_engine.execute(sel)
        # Insert data from source into destination
        data = result.fetchall()
        if not data:
            continue
        ins = dest_table.insert()
        try:
            dest_engine.execute(ins, data)
        except IntegrityError as e:
            warnings.warn("Skipping table {0}: {1}".format(t.name, e.orig.args))


def custom_generate_relationship(base, direction, return_fn, attrname, local_cls, referred_cls, **kw):
    """Make all relationships view only to avoid warnings."""
    kw["viewonly"] = True
    return generate_relationship(base, direction, return_fn, attrname, local_cls, referred_cls, **kw)


def is_unlocked(db_url, timeout=0):
    """Return True if the SQLite db_url is unlocked, after waiting at most timeout seconds.
    Otherwise return False."""
    if not db_url.startswith("sqlite"):
        return False
    try:
        engine = create_engine(db_url, connect_args={"timeout": timeout})
        engine.execute("BEGIN IMMEDIATE")
        return True
    except OperationalError:
        return False


def compare_schemas(left_engine, right_engine):
    """Whether or not the left and right engine have the same schema."""
    left_insp = inspect(left_engine)
    right_insp = inspect(right_engine)
    left_dict = schema_dict(left_insp)
    right_dict = schema_dict(right_insp)
    return str(left_dict) == str(right_dict)


def schema_dict(insp):
    return {
        table_name: {
            "columns": sorted(insp.get_columns(table_name), key=lambda x: x["name"]),
            "pk_constraint": insp.get_pk_constraint(table_name),
            "foreign_keys": sorted(insp.get_foreign_keys(table_name), key=lambda x: x["name"] or ""),
            "check_constraints": insp.get_check_constraints(table_name),
        }
        for table_name in insp.get_table_names()
    }


def is_empty(db_url):
    try:
        engine = create_engine(db_url)
    except DatabaseError as e:
        raise SpineDBAPIError("Could not connect to '{}': {}".format(db_url, e.orig.args))
    insp = inspect(engine)
    if insp.get_table_names():
        return False
    return True


def create_new_spine_database(db_url, for_spine_model=False):
    """Create a new Spine database at the given url."""
    try:
        engine = create_engine(db_url)
    except DatabaseError as e:
        raise SpineDBAPIError("Could not connect to '{}': {}".format(db_url, e.orig.args))
    # Drop existing tables. This is a Spine db now...
    meta = MetaData(engine)
    meta.reflect()
    meta.drop_all(engine)
    # Create new tables
    meta = MetaData(naming_convention=naming_convention)
    Table(
        "commit",
        meta,
        Column("id", Integer, primary_key=True),
        Column("comment", String(255), nullable=False),
        Column("date", DateTime, nullable=False),
        Column("user", String(45)),
    )
    Table(
        "entity_class_type",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), nullable=False),
        Column("commit_id", Integer, ForeignKey("commit.id"), nullable=True),
    )
    Table(
        "entity_type",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), nullable=False),
        Column("commit_id", Integer, ForeignKey("commit.id"), nullable=True),
    )
    Table(
        "entity_class",
        meta,
        Column("id", Integer, primary_key=True),
        Column(
            "type_id",
            Integer,
            ForeignKey("entity_class_type.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("name", String(255), nullable=False),
        Column("description", String(255), server_default=null()),
        Column("display_order", Integer, server_default="99"),
        Column("display_icon", BigInteger, server_default=null()),
        Column("hidden", Integer, server_default="0"),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("id", "type_id"),
        UniqueConstraint("type_id", "name"),
    )
    Table(
        "object_class",
        meta,
        Column("entity_class_id", Integer, primary_key=True),
        Column("type_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ("entity_class_id", "type_id"),
            ("entity_class.id", "entity_class.type_id"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        CheckConstraint("`type_id` = 1", name="type_id"),  # make sure object class can only have object type
    )
    Table(
        "relationship_class",
        meta,
        Column("entity_class_id", Integer, primary_key=True),
        Column("type_id", Integer, nullable=False),
        # TODO: Check if automap keeps working after removing this
        # PrimaryKeyConstraint("entity_class_id", name="relationship_class_PK"),
        ForeignKeyConstraint(
            ("entity_class_id", "type_id"),
            ("entity_class.id", "entity_class.type_id"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        CheckConstraint("`type_id` = 2", name="type_id"),
    )
    Table(
        "relationship_entity_class",
        meta,
        Column(
            "entity_class_id",
            Integer,
            ForeignKey("relationship_class.entity_class_id", onupdate="CASCADE", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("dimension", Integer, primary_key=True),
        Column("member_class_id", Integer, nullable=False),
        Column("member_class_type_id", Integer, nullable=False),
        # TODO: Why this one below???
        # UniqueConstraint("dimension", "entity_class_id", "member_class_id"),
        ForeignKeyConstraint(
            ("member_class_id", "member_class_type_id"),
            ("entity_class.id", "entity_class.type_id"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        CheckConstraint("`member_class_type_id` != 2", name="member_class_type_id"),
    )
    Table(
        "entity",
        meta,
        Column("id", Integer, primary_key=True),
        Column("type_id", Integer, ForeignKey("entity_type.id", onupdate="CASCADE", ondelete="CASCADE")),
        Column("class_id", Integer, ForeignKey("entity_class.id", onupdate="CASCADE", ondelete="CASCADE")),
        Column("name", String(255), nullable=False),
        Column("description", String(255), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("id", "class_id"),
        UniqueConstraint("id", "type_id", "class_id"),
        UniqueConstraint("class_id", "name"),
    )
    Table(
        "object",
        meta,
        Column("entity_id", Integer, primary_key=True),
        Column("type_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ("entity_id", "type_id"), ("entity.id", "entity.type_id"), onupdate="CASCADE", ondelete="CASCADE"
        ),
        CheckConstraint("`type_id` = 1", name="type_id"),  # make sure object can only have object type
    )
    Table(
        "relationship",
        meta,
        Column("entity_id", Integer, primary_key=True),
        Column("entity_class_id", Integer, nullable=False),
        Column("type_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ("entity_id", "type_id"), ("entity.id", "entity.type_id"), onupdate="CASCADE", ondelete="CASCADE"
        ),
        CheckConstraint("`type_id` = 2", name="type_id"),
    )
    Table(
        "relationship_entity",
        meta,
        Column("entity_id", Integer, primary_key=True),
        Column("entity_class_id", Integer, nullable=False),
        Column("dimension", Integer, primary_key=True),
        Column("member_id", Integer, nullable=False),
        Column("member_class_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ("member_id", "member_class_id"), ("entity.id", "entity.class_id"), onupdate="CASCADE", ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ("entity_class_id", "dimension", "member_class_id"),
            (
                "relationship_entity_class.entity_class_id",
                "relationship_entity_class.dimension",
                "relationship_entity_class.member_class_id",
            ),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("entity_id", "entity_class_id"),
            ("relationship.entity_id", "relationship.entity_class_id"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    Table(
        "parameter_definition",
        meta,
        Column("id", Integer, primary_key=True),
        Column(
            "entity_class_id",
            Integer,
            ForeignKey("entity_class.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("name", String(155), nullable=False),
        Column("description", String(155), server_default=null()),
        Column("data_type", String(155), server_default="NUMERIC"),
        Column("default_value", String(155), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        Column("parameter_value_list_id", Integer),
        UniqueConstraint("id", "entity_class_id"),
        UniqueConstraint("entity_class_id", "name"),
    )
    Table(
        "parameter_tag",
        meta,
        Column("id", Integer, primary_key=True),
        Column("tag", String(155), nullable=False, unique=True),
        Column("description", String(255), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "parameter_definition_tag",
        meta,
        Column("id", Integer, primary_key=True),
        Column("parameter_definition_id", Integer, ForeignKey("parameter_definition.id"), nullable=False),
        Column("parameter_tag_id", Integer, ForeignKey("parameter_tag.id"), nullable=False),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("parameter_definition_id", "parameter_tag_id"),
    )
    Table(
        "parameter_value",
        meta,
        Column("id", Integer, primary_key=True),
        Column("parameter_definition_id", Integer, nullable=False),
        Column("entity_id", Integer, nullable=False),
        Column("entity_class_id", Integer, nullable=False),
        Column("value", String(155), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("parameter_definition_id", "entity_id"),
        ForeignKeyConstraint(
            ("entity_id", "entity_class_id"), ("entity.id", "entity.class_id"), onupdate="CASCADE", ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ("parameter_definition_id", "entity_class_id"),
            ("parameter_definition.id", "parameter_definition.entity_class_id"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    Table(
        "parameter_value_list",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(155), nullable=False),
        Column("value_index", Integer, primary_key=True, nullable=False),
        Column("value", String(255), nullable=False),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "alembic_version",
        meta,
        Column("version_num", String(32), nullable=False),
        PrimaryKeyConstraint("version_num", name="alembic_version_pkc"),
    )
    try:
        meta.create_all(engine)
        engine.execute("INSERT INTO entity_class_type VALUES (1, 'object', null), (2, 'relationship', null)")
        engine.execute("INSERT INTO entity_type VALUES (1, 'object', null), (2, 'relationship', null)")
        engine.execute("INSERT INTO alembic_version VALUES ('070a0eb89e88')")
    except DatabaseError as e:
        raise SpineDBAPIError("Unable to create Spine database: {}".format(e.orig.args))
    if for_spine_model:
        add_specifc_data_structure_for_spine_model(db_url)
    return engine


def _create_first_spine_database(db_url):
    """Creates a Spine database with the very first version at the given url.
    Used internally.
    """
    try:
        engine = create_engine(db_url)
    except DatabaseError as e:
        raise SpineDBAPIError("Could not connect to '{}': {}".format(db_url, e.orig.args))
    # Drop existing tables. This is a Spine db now...
    meta = MetaData(engine)
    meta.reflect()
    meta.drop_all(engine)
    # Create new tables
    meta = MetaData(naming_convention=naming_convention)
    Table(
        "commit",
        meta,
        Column("id", Integer, primary_key=True),
        Column("comment", String(255), nullable=False),
        Column("date", DateTime, nullable=False),
        Column("user", String(45)),
    )
    Table(
        "object_class_category",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), nullable=False, unique=True),
        Column("description", String(255), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "object_class",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), nullable=False, unique=True),
        Column("description", String(255), server_default=null()),
        Column("category_id", Integer, ForeignKey("object_class_category.id"), server_default=null()),
        Column("display_order", Integer, server_default="99"),
        Column("display_icon", BigInteger, server_default=null()),
        Column("hidden", Integer, server_default="0"),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "object_category",
        meta,
        Column("id", Integer, primary_key=True),
        Column("object_class_id", Integer, ForeignKey("object_class.id")),
        Column("name", String(255), nullable=False, unique=True),
        Column("description", String(255), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "object",
        meta,
        Column("id", Integer, primary_key=True),
        Column("class_id", Integer, ForeignKey("object_class.id", onupdate="CASCADE", ondelete="CASCADE")),
        Column("name", String(255), nullable=False, unique=True),
        Column("description", String(255), server_default=null()),
        Column("category_id", Integer, ForeignKey("object_category.id")),
        Column("commit_id", Integer, ForeignKey("commit.id")),
    )
    Table(
        "relationship_class",
        meta,
        Column("id", Integer, primary_key=True),
        Column("dimension", Integer, primary_key=True),
        Column("object_class_id", Integer, ForeignKey("object_class.id")),
        Column("name", String(255), nullable=False),
        Column("hidden", Integer, server_default="0"),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("dimension", "name"),
    )
    Table(
        "relationship",
        meta,
        Column("id", Integer, primary_key=True),
        Column("dimension", Integer, primary_key=True),
        Column("object_id", Integer, ForeignKey("object.id")),
        Column("class_id", Integer, nullable=False),
        Column("name", String(255), nullable=False),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        UniqueConstraint("dimension", "name"),
        ForeignKeyConstraint(
            ("class_id", "dimension"),
            ("relationship_class.id", "relationship_class.dimension"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    Table(
        "parameter",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(155), nullable=False, unique=True),
        Column("description", String(155), server_default=null()),
        Column("data_type", String(155), server_default="NUMERIC"),
        Column("relationship_class_id", Integer, default=null()),
        Column(
            "object_class_id",
            Integer,
            ForeignKey("object_class.id", onupdate="CASCADE", ondelete="CASCADE"),
            server_default=null(),
        ),
        Column("can_have_time_series", Integer, server_default="0"),
        Column("can_have_time_pattern", Integer, server_default="1"),
        Column("can_be_stochastic", Integer, server_default="0"),
        Column("default_value", String(155), server_default="0"),
        Column("is_mandatory", Integer, server_default="0"),
        Column("precision", Integer, server_default="2"),
        Column("unit", String(155), server_default=null()),
        Column("minimum_value", Float, server_default=null()),
        Column("maximum_value", Float, server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        CheckConstraint(
            "`relationship_class_id` IS NOT NULL OR `object_class_id` IS NOT NULL",
            name="obj_or_rel_class_id_is_not_null",
        ),
    )
    Table(
        "parameter_value",
        meta,
        Column("id", Integer, primary_key=True),
        Column("parameter_id", Integer, ForeignKey("parameter.id", onupdate="CASCADE", ondelete="CASCADE")),
        Column("relationship_id", Integer, server_default=null()),
        Column("dummy_relationship_dimension", Integer, server_default="0"),
        Column(
            "object_id", Integer, ForeignKey("object.id", onupdate="CASCADE", ondelete="CASCADE"), server_default=null()
        ),
        Column("index", Integer, server_default="1"),
        Column("value", String(155), server_default=null()),
        Column("json", String(255), server_default=null()),
        Column("expression", String(155), server_default=null()),
        Column("time_pattern", String(155), server_default=null()),
        Column("time_series_id", String(155), server_default=null()),
        Column("stochastic_model_id", String(155), server_default=null()),
        Column("commit_id", Integer, ForeignKey("commit.id")),
        CheckConstraint("`relationship_id` IS NOT NULL OR `object_id` IS NOT NULL", name="obj_or_rel_id_is_not_null"),
        UniqueConstraint("parameter_id", "object_id"),
        UniqueConstraint("parameter_id", "relationship_id"),
        ForeignKeyConstraint(
            ("relationship_id", "dummy_relationship_dimension"),
            ("relationship.id", "relationship.dimension"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    try:
        meta.create_all(engine)
    except DatabaseError as e:
        raise SpineDBAPIError("Unable to create Spine database: {}".format(e.orig.args))
    return engine


def add_specifc_data_structure_for_spine_model(db_url):
    """Add as much of the specific data structure for spine model as possible.
    If called on a database which already has some content, it will add what's missing.
    This can be useful for eg updating a db to the latest version of spine model, in case
    we added stuff on the go (which we'll probably do).
    """
    from .diff_database_mapping import DiffDatabaseMapping

    db_map = DiffDatabaseMapping(db_url)
    object_classes = (
        ("direction", "A flow direction", 1, 281105626296654),
        ("unit", "An entity where an energy conversion process takes place", 2, 281470681805429),
        ("connection", "An entity where an energy transfer takes place", 3, 280378317271233),
        ("storage", "A storage", 4, 280376899531934),
        ("commodity", "A commodity", 5, 281473533932880),
        ("node", "An entity where an energy balance takes place", 6, 280740554077951),
        ("model", "A modelling time horizon", 7, 280376891207703),
        ("temporal_block", "A temporal block", 8, 280376891207703),
        ("rolling", "A rolling horizon", 9, 281107043971546),
        ("output", "Results", 10),
        ("report", "Results", 10),

    )
    db_map.add_object_classes(
        *[dict(zip(("name", "description", "display_order", "display_icon"), x)) for x in object_classes]
    )
    import_data(
        db_map,
        objects=(("direction", "from_node"), ("direction", "to_node")),
        relationship_classes=(
            ("unit__node__direction", ("unit", "node", "direction")),
            ("connection__node__direction", ("connection", "node", "direction")),
            ("node__commodity", ("node", "commodity")),
            ("unit_group__unit", ("unit", "unit")),
            ("commodity_group__commodity", ("commodity", "commodity")),
            ("node_group__node", ("node", "node")),
            ("unit_group__commodity_group", ("unit", "commodity")),
            ("commodity_group__node_group", ("commodity", "node")),
            ("unit__commodity", ("unit", "commodity")),
            ("unit__commodity__direction", ("unit", "commodity", "direction")),
            ("unit__commodity__commodity", ("unit", "commodity", "commodity")),
            ("connection__node__node", ("connection", "node", "node")),
            ("connection__node", ("connection", "node")),
            ("node__temporal_block", ("node", "temporal_block")),
            ("storage__unit", ("storage", "unit")),
            ("storage__connection", ("storage", "connection")),
            ("storage__commodity", ("storage", "commodity")),
            ("storage__storage", ("storage", "storage")),
            ("report__output", ("report", "output")),
        ),
        object_parameters=(
            ("unit", "fom_cost", None),
            ("unit", "start_up_cost", None),
            ("unit", "shut_down_cost", None),
            ("unit", "number_of_units", 1),
            ("unit", "avail_factor", 1),
            ("unit", "min_down_time", None),
            ("unit", "min_up_time", None),
            ("unit", "online_variable_type", "no_online_variable"),
            ("unit", "fix_units_on", None),
            ("temporal_block", "block_start", None),
            ("temporal_block", "block_end", None),
            ("temporal_block", "resolution", Duration("1 hours")),
            ("node", "demand", 0),
            ("storage", "stor_state_cap", None),
            ("storage", "stor_state_min", 0),
            ("storage", "frac_state_loss", 0),
            ("storage", "state_coeff", 1),
            ("model", "model_start", Date("2000-01-01T00:00:00")),
            ("model", "model_end", Date("2000-01-02T00:00:00")),
            ("model", "roll_forward", None),
        ),
        relationship_parameters=(
            ("unit__commodity", "unit_conv_cap_to_flow", 1),
            ("unit__commodity", "minimum_operating_point", None),
            ("unit__commodity__direction", "unit_capacity", None),
            ("unit__commodity__direction", "operating_cost", None),
            ("unit__commodity__direction", "vom_cost", None),
            ("commodity_group__node_group", "tax_net_flow", None),
            ("commodity_group__node_group", "tax_out_flow", None),
            ("commodity_group__node_group", "tax_in_flow", None),
            ("unit__commodity__commodity", "fix_ratio_in_in_flow", None),
            ("unit__commodity__commodity", "max_ratio_in_in_flow", None),
            ("unit__commodity__commodity", "min_ratio_in_in_flow", None),
            ("unit__commodity__commodity", "fix_ratio_out_in_flow", None),
            ("unit__commodity__commodity", "max_ratio_out_in_flow", None),
            ("unit__commodity__commodity", "min_ratio_out_in_flow", None),
            ("unit__commodity__commodity", "fix_ratio_out_out_flow", None),
            ("unit__commodity__commodity", "max_ratio_out_out_flow", None),
            ("unit__commodity__commodity", "min_ratio_out_out_flow", None),
            ("connection__node__direction", "fix_ratio_out_in_trans", None),
            ("connection__node__direction", "max_ratio_out_in_trans", None),
            ("connection__node__direction", "min_ratio_out_in_trans", None),
            ("connection__node__direction", "fix_trans", None),
            ("connection__node__direction", "conn_capacity", None),
            ("connection__node", "conn_avail_factor", 1),
            ("connection__node", "conn_conv_cap_to_trans", 1),
            ("storage__unit", "stor_unit_discharg_eff", 1),
            ("storage__unit", "stor_unit_charg_eff", 1),
            ("storage__connection", "stor_conn_discharg_eff", 1),
            ("storage__connection", "stor_conn_charg_eff", 1),
            ("storage__storage", "diff_coeff", None),
            ("unit_group__commodity_group", "max_cum_in_flow_bound", None),
            ("unit__node__direction", "fix_flow", None),
        ),
    )
    db_map.commit_session("Add specific data structure for Spine Model.")
    db_map.connection.close()


def forward_sweep(root, func):
    """Recursively visit, using `get_children()`, the given sqlalchemy object.
    Apply `func` on every visited node."""
    current = root
    parent = {}
    children = {current: iter(current.get_children(column_collections=False))}
    while True:
        func(current)
        # Try and visit next children
        next_ = next(children[current], None)
        if next_ is not None:
            parent[next_] = current
            children[next_] = iter(next_.get_children(column_collections=False))
            current = next_
            continue
        # No (more) children, try and visit next sibling
        current_parent = parent[current]
        next_ = next(children[current_parent], None)
        if next_ is not None:
            parent[next_] = current_parent
            children[next_] = iter(next_.get_children(column_collections=False))
            current = next_
            continue
        # No (more) siblings, go back to parent
        current = current_parent
        if current == root:
            break
