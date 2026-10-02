"""Idempotent HW5 schema/data migration for the transit incident database.

Run a mysqldump before running this script. The script keeps route_line and
incident_related_data so the HW4 application and benchmark remain compatible.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import inspect, select, text

from src.hw4_database import Base, db_session_basede26, engine
from src.hw4_models import IncidentRecord, Route


ROUTE_CODE_PATTERN = "RT-{number:03d}"
INCIDENT_CODE_PATTERN = "INC-{number:06d}"


def existing_columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in inspect(engine).get_columns(table_name)
    }


def add_missing_incident_columns() -> None:
    columns = existing_columns("incidents")
    statements = {
        "incident_code": (
            "ALTER TABLE incidents ADD COLUMN incident_code "
            "VARCHAR(20) NULL"
        ),
        "passengers_affected": (
            "ALTER TABLE incidents ADD COLUMN passengers_affected "
            "INT NOT NULL DEFAULT 0"
        ),
        "route_id": (
            "ALTER TABLE incidents ADD COLUMN route_id INT NULL"
        ),
        "created_at": (
            "ALTER TABLE incidents ADD COLUMN created_at DATETIME NULL"
        ),
        "updated_at": (
            "ALTER TABLE incidents ADD COLUMN updated_at DATETIME NULL"
        ),
    }

    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in columns:
                connection.execute(text(statement))


def add_unique_incident_code_constraint() -> None:
    indexes = inspect(engine).get_unique_constraints("incidents")
    has_constraint = any(
        "incident_code" in constraint.get("column_names", [])
        for constraint in indexes
    )

    if not has_constraint:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE incidents ADD CONSTRAINT "
                    "uq_incidents_incident_code UNIQUE (incident_code)"
                )
            )


def add_route_foreign_key() -> None:
    foreign_keys = inspect(engine).get_foreign_keys("incidents")
    has_route_fk = any(
        foreign_key.get("referred_table") == "routes"
        and foreign_key.get("constrained_columns") == ["route_id"]
        for foreign_key in foreign_keys
    )

    if not has_route_fk:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE incidents ADD CONSTRAINT "
                    "fk_incidents_route_id_routes FOREIGN KEY (route_id) "
                    "REFERENCES routes (id) ON DELETE RESTRICT"
                )
            )


def next_route_number(routes: list[Route]) -> int:
    numbers = []
    for route in routes:
        if route.route_code.startswith("RT-"):
            suffix = route.route_code[3:]
            if suffix.isdigit():
                numbers.append(int(suffix))
    return max(numbers, default=0) + 1


def migrate_data() -> None:
    db = db_session_basede26()
    try:
        routes = db.scalars(select(Route).order_by(Route.id)).all()
        route_by_name = {route.route_name: route for route in routes}
        route_number = next_route_number(routes)

        route_lines = db.scalars(
            select(IncidentRecord.route_line)
            .distinct()
            .order_by(IncidentRecord.route_line)
        ).all()

        for route_line in route_lines:
            route_name = (route_line or "Unknown Route").strip()
            if route_name not in route_by_name:
                route = Route(
                    route_name=route_name,
                    operator="VTA",
                    route_code=ROUTE_CODE_PATTERN.format(
                        number=route_number
                    ),
                )
                db.add(route)
                db.flush()
                route_by_name[route_name] = route
                route_number += 1

        incidents = db.scalars(
            select(IncidentRecord).order_by(IncidentRecord.id)
        ).all()
        now = datetime.utcnow()

        for incident in incidents:
            route_name = (incident.route_line or "Unknown Route").strip()
            route = route_by_name[route_name]
            incident.route_id = route.id

            if not incident.incident_code:
                incident.incident_code = INCIDENT_CODE_PATTERN.format(
                    number=incident.id
                )

            if not incident.created_at:
                incident.created_at = incident.submission_date or now
            if not incident.updated_at:
                incident.updated_at = incident.created_at
            if incident.passengers_affected is None:
                incident.passengers_affected = 0

        db.commit()

        print("Route mapping (route_line -> route_code):")
        for route in db.scalars(select(Route).order_by(Route.id)):
            print(f"  {route.route_name} -> {route.route_code}")
        print(f"Migrated routes: {len(route_by_name)}")
        print(f"Migrated incidents: {len(incidents)}")
    finally:
        db.close()


def make_columns_required() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE incidents MODIFY COLUMN incident_code "
                "VARCHAR(20) NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE incidents MODIFY COLUMN route_id "
                "INT NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE incidents MODIFY COLUMN created_at "
                "DATETIME NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE incidents MODIFY COLUMN updated_at "
                "DATETIME NOT NULL"
            )
        )


def main() -> None:
    if not inspect(engine).has_table("incidents"):
        raise SystemExit(
            "The incidents table does not exist. Run the existing HW4 seed "
            "setup first."
        )

    Base.metadata.tables["routes"].create(bind=engine, checkfirst=True)
    add_missing_incident_columns()
    migrate_data()
    add_unique_incident_code_constraint()
    add_route_foreign_key()
    make_columns_required()

    inspector = inspect(engine)
    with engine.connect() as connection:
        incident_count = connection.execute(
            text("SELECT COUNT(*) FROM incidents")
        ).scalar_one()
        route_count = connection.execute(
            text("SELECT COUNT(*) FROM routes")
        ).scalar_one()

    print(f"Final incidents: {incident_count}")
    print(f"Final routes: {route_count}")
    print(
        "Migration complete; existing route_line and "
        "incident_related_data were preserved."
    )


if __name__ == "__main__":
    main()
