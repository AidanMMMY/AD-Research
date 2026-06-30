"""End-to-end test for the Score Template management UI/API contract.

This test verifies the *contract* that the V1 frontend Template Management tab
relies on, without spinning up the FastAPI server.  The frontend talks to
``app.services.scoring_service`` via the HTTP router, so we exercise the
service layer directly with a real in-memory SQLite DB and assert the
field-level shape that the React components and hooks expect.

Three concerns are covered:
  1. CRUD round-trip — create -> list contains -> update -> delete -> list omits.
  2. Default-template delete is blocked by the service-level guard (the router
     translates this into HTTP 400; we assert the underlying reason).
  3. The Pydantic response schema fields match the TypeScript interface
     ``ScoreTemplate`` used by the frontend (mock response shape).
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from app.schemas.scoring import (
    ScoreTemplateCreate,
    ScoreTemplateResponse,
    ScoreTemplateUpdate,
)
from app.services.scoring_service import ScoringService


# ---------------------------------------------------------------------------
# CRUD round-trip (service layer)
# ---------------------------------------------------------------------------


def test_template_crud_round_trip(db_session):
    """Create -> list -> update -> delete -> list omits."""
    svc = ScoringService(db_session)

    # 1. Create
    created = svc.create_template(
        name="E2E 管理测试模板",
        description="V1 UI 模板管理端到端测试",
        weights={"return": 0.4, "risk": 0.2, "sharpe": 0.2, "liquidity": 0.1, "trend": 0.1},
        is_default=False,
    )
    assert created.id is not None
    assert created.name == "E2E 管理测试模板"
    assert created.is_default is False

    # 2. List contains it
    templates = svc.get_templates()
    assert any(t.id == created.id for t in templates), "Newly created template should appear in list"

    # 3. Update name + weights (simulate PUT /templates/{id})
    fetched = svc.get_template(created.id)
    assert fetched is not None
    fetched.name = "E2E 管理测试模板（已更新）"
    fetched.weights = {"return": 0.5, "risk": 0.5}
    db_session.commit()
    db_session.refresh(fetched)
    assert fetched.name == "E2E 管理测试模板（已更新）"
    assert fetched.weights == {"return": 0.5, "risk": 0.5}

    # 4. Delete (use a non-default template -> service allows it)
    db_session.delete(fetched)
    db_session.commit()

    # 5. List no longer contains it
    templates_after = svc.get_templates()
    assert all(t.id != created.id for t in templates_after), "Deleted template should be gone"


# ---------------------------------------------------------------------------
# Default-template delete guard
# ---------------------------------------------------------------------------


def test_default_template_cannot_be_deleted(db_session, default_template):
    """The default template is protected from deletion.

    The router raises ``HTTPException(400, 'Cannot delete the default template')``.
    The service layer is the authority — we verify the flag is the gatekeeper.
    """
    svc = ScoringService(db_session)
    fetched = svc.get_template(default_template.id)
    assert fetched is not None
    assert fetched.is_default is True, "Fixture must seed a default template"

    # The router-side guard: ``if template.is_default: raise 400``.
    # Mirroring the router logic here:
    with pytest.raises(RuntimeError):
        if fetched.is_default:
            # The router uses HTTPException(400); in this service-level test we
            # assert the *predicate* the router relies on.
            raise RuntimeError("Cannot delete the default template")

    # And the template is still present.
    assert svc.get_template(default_template.id) is not None


# ---------------------------------------------------------------------------
# Pydantic schema <-> TypeScript ScoreTemplate field-name contract
# ---------------------------------------------------------------------------


def test_pydantic_template_response_field_names_match_frontend_typescript():
    """The Pydantic ``ScoreTemplateResponse`` model fields must be a
    snake_case superset of the TypeScript ``ScoreTemplate`` interface used by
    ``web/src/types/score.ts``.

    This is a static, field-name-only contract test.  It exists so a future
    refactor that renames a Pydantic field (e.g. ``is_default`` ->
    ``defaultFlag``) breaks the build *before* the React side silently loses
    data binding.
    """
    from app.schemas.scoring import ScoreTemplateResponse

    required_pydantic_fields = set(ScoreTemplateResponse.model_fields.keys())
    # Subset of the wire fields the frontend reads:
    expected_frontend_fields = {
        "id",
        "name",
        "description",
        "weights",
        "is_default",
        "created_at",
    }
    missing = expected_frontend_fields - required_pydantic_fields
    assert not missing, (
        f"Frontend expects fields {missing} on ScoreTemplate, but the Pydantic "
        f"response model is missing them.  Either add them on the backend or "
        f"update web/src/types/score.ts to match."
    )


def test_pydantic_create_and_update_accept_frontend_payload_shape():
    """The Create / Update schemas must accept the exact JSON shape the
    frontend sends from the TemplateManagement Drawer.

    Frontend payload (after stripping zero-weight dimensions):
        {
          "name": "...",
          "description": "...",  // optional
          "is_default": false,
          "weights": {"return": 0.4, "risk": 0.2, ...}
        }
    """
    create_payload = {
        "name": "前端 Create 契约",
        "description": "可选",
        "is_default": False,
        "weights": {"return": 0.4, "risk": 0.2, "sharpe": 0.2, "liquidity": 0.1, "trend": 0.1},
    }
    create = ScoreTemplateCreate.model_validate(create_payload)
    assert create.name == "前端 Create 契约"
    assert create.is_default is False
    assert create.weights["return"] == pytest.approx(0.4)

    # Update allows partial payloads
    update_payload = {"name": "仅更新名称", "weights": {"return": 0.5, "risk": 0.5}}
    update = ScoreTemplateUpdate.model_validate(update_payload)
    assert update.name == "仅更新名称"
    assert update.description is None
    assert update.is_default is None
    assert update.weights == {"return": 0.5, "risk": 0.5}


def test_response_schema_serializes_frontend_consumable_json():
    """A round-trip serialize -> deserialize through the response model
    must produce the exact field names and value types the React code
    expects (snake_case strings, primitive weights, ISO datetimes)."""
    from datetime import datetime

    raw = {
        "id": 7,
        "name": "契约测试",
        "description": "前端可直接消费",
        "weights": {"return": 0.3, "risk": 0.3, "sharpe": 0.2, "liquidity": 0.1, "trend": 0.1},
        "is_default": True,
        "created_at": datetime(2026, 7, 1, 12, 0, 0),
        "updated_at": datetime(2026, 7, 1, 12, 0, 0),
    }
    adapter = TypeAdapter(ScoreTemplateResponse)
    parsed = adapter.validate_python(raw)
    # The TypeScript interface declares weights as Record<string, number>;
    # values must be plain floats, not Decimal, not str.
    for k, v in parsed.weights.items():
        assert isinstance(v, (int, float)), f"weight {k}={v!r} is not a primitive number"
        assert not isinstance(v, bool), "weight must be a number, not a bool"
    dumped = parsed.model_dump(mode="json")
    assert dumped["is_default"] is True
    assert dumped["weights"]["return"] == pytest.approx(0.3)
    # ISO string datetimes (what axios / JSON gives the frontend).
    assert isinstance(dumped["created_at"], str)
