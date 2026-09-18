"""Brand lane registry — path resolution, fan-out, integration gating."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spec import JobSpec

VALID_BRAND_MODES = frozenset({"global", "per_brand", "fanout_internal"})
BRAND_MODE_UNSET = "__unset__"


def _brands_file() -> Path:
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        return Path(bundled) / "brands.json"
    return Path(__file__).resolve().parents[3] / "data" / "brands.json"


@lru_cache(maxsize=1)
def load_brands_registry() -> dict:
    path = _brands_file()
    if not path.is_file():
        return {"brands": {}, "integrations": {}}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def clear_brands_cache() -> None:
    load_brands_registry.cache_clear()


def integration_catalog_keys() -> frozenset[str]:
    reg = load_brands_registry()
    return frozenset((reg.get("integrations") or {}).keys())


def active_brand_ids() -> tuple[str, ...]:
    from _lib.marketing_calendar import VALID_BRAND_IDS

    reg = load_brands_registry()
    brands = reg.get("brands") or {}
    out: list[str] = []
    for bid in VALID_BRAND_IDS:
        entry = brands.get(bid) or {}
        if entry.get("active", True):
            out.append(bid)
    return tuple(out)


def _brand_safe(brand_id: str) -> str:
    return brand_id.upper().replace("-", "_")


def _env_any(*names: str) -> bool:
    for name in names:
        if (os.environ.get(name) or "").strip():
            return True
    return False


def _credential_file_exists(credential_ref: str) -> bool:
    if not credential_ref:
        return False
    for base in (
        os.environ.get("DATA_DIR"),
        os.environ.get("BUNDLED_DATA_DIR"),
        "/data",
    ):
        if not base:
            continue
        path = os.path.join(base, "credentials", credential_ref)
        if os.path.isfile(path):
            return True
    return False


def integration_applies(brand_id: str, integration_id: str) -> bool:
    reg = load_brands_registry()
    brand = (reg.get("brands") or {}).get(brand_id) or {}
    scope = (brand.get("integration_scope") or {}).get(integration_id)
    if scope is not None:
        return bool(scope.get("applies", True))
    integ = (reg.get("integrations") or {}).get(integration_id) or {}
    if integ.get("scope_class") == "shared_global":
        return False
    return True


def integration_state(brand_id: str, integration_id: str) -> str:
    """Return connected | partial | missing | na for a brand+integration pair."""
    reg = load_brands_registry()
    brand = (reg.get("brands") or {}).get(brand_id) or {}
    scope = (brand.get("integration_scope") or {}).get(integration_id)

    if scope is not None and not scope.get("applies", True):
        return "na"

    if scope is None:
        integ = (reg.get("integrations") or {}).get(integration_id) or {}
        if integ.get("scope_class") == "shared_global":
            return "na"
        return "missing"

    env_names = list(scope.get("env") or [])
    cred_ref = scope.get("credential_ref")
    has_cred = _env_any(*env_names) if env_names else False
    if cred_ref and _credential_file_exists(cred_ref):
        has_cred = True

    if not has_cred:
        return "missing"

    if env_names and not all((os.environ.get(n) or "").strip() for n in env_names):
        return "partial"

    return "connected"


def resolve_brands(spec: JobSpec) -> tuple[str, ...]:
    """Brands that should run (connected or partial on required integrations)."""
    if spec.brand_mode in ("global", "fanout_internal"):
        return ()
    runnable, _ = partition_brands(spec)
    return runnable


def skipped_brands(spec: JobSpec) -> tuple[str, ...]:
    """Brands in scope but blocked on integrations — SKIPPED, not FAILED."""
    if spec.brand_mode != "per_brand":
        return ()
    _, skipped = partition_brands(spec)
    return skipped


def partition_brands(spec: JobSpec) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if spec.brand_mode != "per_brand":
        return (), ()

    candidates = spec.brands if spec.brands else active_brand_ids()
    runnable: list[str] = []
    skipped: list[str] = []

    for brand_id in candidates:
        if not spec.requires_integrations:
            runnable.append(brand_id)
            continue

        applicable = [
            i
            for i in spec.requires_integrations
            if integration_applies(brand_id, i)
        ]
        if not applicable:
            continue

        states = [integration_state(brand_id, i) for i in applicable]
        if all(s in ("connected", "partial") for s in states):
            runnable.append(brand_id)
        elif any(s == "missing" for s in states):
            skipped.append(brand_id)

    return tuple(runnable), tuple(skipped)


def resolve_path(spec: JobSpec, rel: str, brand: str | None) -> str:
    if (
        spec.brand_mode != "per_brand"
        or rel in spec.shared_writes
        or rel in spec.shared_reads
    ):
        return rel
    if not brand:
        raise ValueError(f"{spec.name}: per_brand job needs a brand to resolve {rel!r}")
    return f"brands/{brand}/{rel}"


def _global_writes(jobs: dict[str, JobSpec]) -> frozenset[str]:
    out: set[str] = set()
    for job in jobs.values():
        if job.brand_mode == "global":
            out.update(job.writes)
    return frozenset(out)


def validate_job_spec(spec: JobSpec, jobs: dict[str, JobSpec] | None = None) -> None:
    """Import-time invariants — raise on violation."""
    if spec.brand_mode == BRAND_MODE_UNSET:
        raise ValueError(f"{spec.name}: brand_mode must be set explicitly")

    if spec.brand_mode not in VALID_BRAND_MODES:
        raise ValueError(
            f"{spec.name}: invalid brand_mode {spec.brand_mode!r}; "
            f"expected one of {sorted(VALID_BRAND_MODES)}"
        )

    from _lib.marketing_calendar import VALID_BRAND_IDS

    for brand_id in spec.brands:
        if brand_id not in VALID_BRAND_IDS:
            raise ValueError(f"{spec.name}: unknown brand {brand_id!r}")

    if spec.brand_mode == "global":
        if spec.brands or spec.requires_integrations:
            raise ValueError(
                f"{spec.name}: global jobs must not declare brands or requires_integrations"
            )

    catalog = integration_catalog_keys()
    for integration_id in spec.requires_integrations:
        if integration_id not in catalog:
            raise ValueError(
                f"{spec.name}: unknown integration {integration_id!r} "
                f"(not in brands.json integrations catalog)"
            )

    for rel in spec.shared_writes:
        if rel not in spec.writes:
            raise ValueError(f"{spec.name}: shared_writes entry {rel!r} not in writes")

    for rel in spec.shared_reads:
        if rel not in spec.reads:
            raise ValueError(f"{spec.name}: shared_reads entry {rel!r} not in reads")

    if jobs and spec.brand_mode == "per_brand":
        global_writes = _global_writes(jobs)
        for rel in spec.reads:
            if rel in global_writes and rel not in spec.shared_reads:
                raise ValueError(
                    f"{spec.name}: per_brand read {rel!r} comes from a global job output "
                    f"but is not listed in shared_reads"
                )


def validate_brands_registry() -> None:
    """Schema validation for brands.json integration_scope blocks."""
    reg = load_brands_registry()
    integrations = reg.get("integrations") or {}
    if not integrations:
        raise ValueError("brands.json missing top-level integrations catalog")

    for brand_id, brand in (reg.get("brands") or {}).items():
        scope = brand.get("integration_scope") or {}
        for integration_id, entry in scope.items():
            if integration_id not in integrations:
                raise ValueError(
                    f"brand {brand_id}: integration_scope key {integration_id!r} "
                    f"not in integrations catalog"
                )
            if entry.get("applies") is False:
                reason = (entry.get("na_reason") or "").strip()
                if not reason:
                    raise ValueError(
                        f"brand {brand_id}: integration {integration_id} "
                        f"applies=false requires non-empty na_reason"
                    )
