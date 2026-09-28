# AI Use Statement

## 1. What did you use an AI assistant for, and what did you do yourself?

I used an AI assistant to explain the homework requirements, help debug FastAPI and React errors, suggest troubleshooting commands, explain the N+1 query problem, and organize the benchmark results and report files.

I wrote and ran the application code, created the database configuration, seeded the MySQL database, ran the measurements, tested the API and React frontend, captured screenshots, and verified the results myself.

## 2. What AI-produced output was wrong or unsuitable, or what did you independently verify?

An initial suggested health-endpoint change referred to a model named `Incident`, but this project uses the model name `IncidentRecord`.

## 3. How did you detect the problem or verify the result?

When I restarted FastAPI, it produced an import error:

```text
ImportError: cannot import name 'Incident' from 'src.hw4_models'
```

I checked the model definitions and the seed script, which confirmed that the correct model was `IncidentRecord`.

## 4. What did you change, and why does it work now?

I changed the import and health query to use the actual model:

```python
db.query(hw4_models.IncidentRecord).count()
```

I also added the database session dependency using `db_session_basede26`. After restarting FastAPI, the health endpoint returned:

```json
{
  "status": "ok",
  "port": 8498,
  "record_count": 5000
}
```

This confirms that the endpoint is counting records from MySQL instead of using the old in-memory list.