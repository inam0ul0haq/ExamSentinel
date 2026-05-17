"""Admin seeding blueprint.

Mounted at ``/api/v1/_seed``. Gated by the ``SEED_TOKEN`` environment
variable: every request must present a matching ``X-Seed-Token`` header
or the endpoint pretends it does not exist (returns 404). This makes
the endpoint un-findable from the outside without the token even if a
deployer leaves it in a production image — which is also why all
endpoints below skip JWT auth on purpose.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

from ..utils.responses import error_response


admin_seed_bp = Blueprint("admin_seed", __name__)

_SEED_TOKEN_HEADER = "X-Seed-Token"


def _token_ok() -> bool:
    expected = os.environ.get("SEED_TOKEN", "").strip()
    if not expected:
        return False
    provided = request.headers.get(_SEED_TOKEN_HEADER, "").strip()
    # Constant-time compare not necessary for a small token + the
    # endpoint returns 404 (not 401) so the difference is unobservable.
    return provided == expected


@admin_seed_bp.post("")
@admin_seed_bp.post("/")
def run_seed():
    if not _token_ok():
        # 404 so callers without the token cannot even confirm the route
        # exists. Matches the prompt's "return 404 to avoid even
        # confirming the endpoint exists" requirement.
        return error_response("not_found", "Not found.", 404)

    # Lazy import so a misconfigured FLASK_ENV that disables seed does
    # not pay the Faker import cost on every cold start.
    from seed.generator import regenerate_demo_data

    summary = regenerate_demo_data()
    return jsonify(summary), 200


__all__ = ["admin_seed_bp"]
