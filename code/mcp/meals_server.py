"""TheMealDB MCP server for DATA-260 HW5.

The server uses STDIO. Do not use print(), because stdout belongs to the
JSON-RPC stream. Operational messages are sent to stderr through logging.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


BASE_URL = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("hw5.meals")

mcp = FastMCP("meals")


def _request(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}/{endpoint}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.exception("TheMealDB request failed: %s", url)
        raise RuntimeError(f"TheMealDB network request failed: {exc}") from exc
    except ValueError as exc:
        logger.exception("TheMealDB returned invalid JSON: %s", url)
        raise RuntimeError("TheMealDB returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("TheMealDB returned an unexpected JSON object")
    return payload


def _check_limit(limit: int, maximum: int = 25) -> int:
    if not 1 <= limit <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return limit


def _summary(meal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "area": meal.get("strArea"),
        "category": meal.get("strCategory"),
        "thumb": meal.get("strMealThumb"),
    }


def _ingredient_summary(meal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "thumb": meal.get("strMealThumb"),
    }


def _details(meal: dict[str, Any]) -> dict[str, Any]:
    ingredients = []
    for index in range(1, 21):
        name = (meal.get(f"strIngredient{index}") or "").strip()
        measure = (meal.get(f"strMeasure{index}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": measure})

    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"),
        "ingredients": ingredients,
    }


def _no_matches() -> dict[str, Any]:
    return {"items": [], "message": "no matches"}


@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5):
    """Search TheMealDB by meal name."""
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    _check_limit(limit)

    payload = _request("search.php", {"s": query})
    meals = payload.get("meals")
    if meals is None:
        return _no_matches()
    return [_summary(meal) for meal in meals[:limit]]


@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12):
    """Find meals by their main ingredient."""
    ingredient = ingredient.strip()
    if not ingredient:
        raise ValueError("ingredient must not be empty")
    _check_limit(limit)

    payload = _request("filter.php", {"i": ingredient})
    meals = payload.get("meals")
    if meals is None:
        return _no_matches()
    return [_ingredient_summary(meal) for meal in meals[:limit]]


@mcp.tool()
def meal_details(id: str | int) -> dict[str, Any]:
    """Return the full recipe details for a meal ID."""
    meal_id = str(id).strip()
    if not meal_id:
        raise ValueError("id must not be empty")

    payload = _request("lookup.php", {"i": meal_id})
    meals = payload.get("meals")
    if meals is None:
        return _no_matches()
    return _details(meals[0])


@mcp.tool()
def random_meal() -> dict[str, Any]:
    """Return one random recipe from TheMealDB."""
    payload = _request("random.php")
    meals = payload.get("meals")
    if meals is None:
        return _no_matches()
    return _details(meals[0])


if __name__ == "__main__":
    mcp.run(transport="stdio")
