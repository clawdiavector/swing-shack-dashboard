"""Weekly retail campaign job — lodges review drafts with approve=False."""

from __future__ import annotations

from _lib import retail_campaign as rc

JOB_NAME = "retail_campaign"
OUTPUT = "retail-campaign/latest.json"


def run(*, brand: str | None = None) -> dict:
    return rc.run(brand=brand, lodge=True)
