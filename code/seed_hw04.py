import argparse
import random
from datetime import datetime, timedelta

from sqlalchemy import func, select

from src.hw4_database import Base, db_session_basede26, engine
from src.hw4_models import (
    IncidentRecord,
    IncidentRelatedData,
    User,
)
from src.hw4_security import hash_password


SEED = 4098
TARGET_INCIDENTS = 5000
TARGET_RELATED = 200

DEMO_EMAIL = "samina.hw4@example.com"
DEMO_PASSWORD = "Transit4098!"

CATEGORIES = [
    "delay",
    "collision",
    "service-suspension",
    "infrastructure-issue",
]

ROUTES = [
    "VTA Route 22",
    "VTA Green Line",
    "VTA Route 522",
    "VTA Orange Line",
    "VTA Route 55",
]

RELATED_TYPES = [
    "operator_note",
    "maintenance_note",
    "follow_up",
]



        incident_count = db.scalar(
            select(func.count()).select_from(IncidentRecord)
        )

        related_count = db.scalar(
            select(func.count()).select_from(IncidentRelatedData)
        )

        if incident_count or related_count:
            print(
                f"Database already contains {incident_count} incidents "
                f"and {related_count} related rows."
            )
            print("Use --reset only if you want to rebuild the test data.")
            return

        demo_user = db.scalar(
            select(User).where(User.email == DEMO_EMAIL)
        )

        if demo_user is None:
            db.add(
                User(
                    name="Samina Maraj",
                    email=DEMO_EMAIL,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )
            db.commit()

        rng = random.Random(SEED)
        incidents = []
        start_time = datetime.utcnow() - timedelta(days=365)

        for index in range(TARGET_INCIDENTS):
            category = rng.choice(CATEGORIES)
            route = rng.choice(ROUTES)

            incidents.append(
                IncidentRecord(
                    incident_title=(
                        f"Transit {category.replace('-', ' ').title()} "
                        f"Incident {index + 1}"
                    ),
                    route_line=route,
                    submitter_email=DEMO_EMAIL,
                    description=(
                        f"This seeded municipal transit incident describes "
                        f"a {category.replace('-', ' ')} affecting {route}."
                    ),
                    category=category,
                    terms_accepted=True,
                    submission_date=start_time + timedelta(
                        minutes=index
                    ),
                )
            )

        db.add_all(incidents)
        db.commit()

        related_rows = []

        for index in range(TARGET_RELATED):
            incident = incidents[(index * 37) % TARGET_INCIDENTS]

            related_rows.append(
                IncidentRelatedData(
                    incident_id=incident.id,
                    related_type=rng.choice(RELATED_TYPES),
                    related_text=(
                        f"Related test note {index + 1} for "
                        f"incident {incident.id}."
                    ),
                )
            )

        db.add_all(related_rows)
        db.commit()

        print(f"Seed: {SEED}")
        print(f"Inserted incidents: {len(incidents)}")
        print(f"Inserted related rows: {len(related_rows)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()