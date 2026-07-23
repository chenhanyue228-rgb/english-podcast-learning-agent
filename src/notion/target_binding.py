"""Validate that every production Notion write targets one intended database group."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from src.notion.config import NotionConfig, NotionConfigError, load_notion_config
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    REQUIRED_DATABASE_PROPERTIES,
    REQUIRED_DATABASE_RELATIONS,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
    WORKSPACE_DATABASE_ORDER,
)


TARGET_PARENT_NOT_CONFIGURED = "target_parent_not_configured"
TARGET_PARENT_MISMATCH = "target_parent_mismatch"
CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP = (
    "configured_data_sources_not_same_group"
)
TARGET_DATABASE_MISSING = "target_database_missing"
TARGET_DATABASE_AMBIGUOUS = "target_database_ambiguous"
TARGET_DATABASE_ROLE_MISMATCH = "target_database_role_mismatch"
TARGET_RELATION_OUTSIDE_GROUP = "target_relation_outside_group"
TARGET_RELATION_MODE_INVALID = "target_relation_mode_invalid"
TARGET_PAGE_OUTSIDE_GROUP = "target_page_outside_group"
TARGET_BINDING_RETRIEVE_FAILED = "target_binding_retrieve_failed"
TARGET_BINDING_VALIDATION_FAILED = "target_binding_validation_failed"

_CACHE_ATTRIBUTE = "_epla_target_binding_proof"
_PAGE_CACHE_ATTRIBUTE = "_epla_target_page_role_proofs"


class NotionTargetBindingError(RuntimeError):
    """A stable, redacted failure raised before any production Notion write."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class NotionTargetBindingResult:
    """Public, immutable proof containing no raw Notion identifiers."""

    valid: bool
    verified_roles: tuple[str, ...]
    target_parent_fingerprint: str
    target_group_fingerprint: str
    configured_parent_matches_expected: bool
    all_data_sources_same_group: bool
    internal_relations_verified: bool


@dataclass(frozen=True, repr=False)
class _NotionTargetBindingProof:
    result: NotionTargetBindingResult
    role_ids: tuple[tuple[str, str], ...] = field(repr=False)

    def role_mapping(self) -> dict[str, str]:
        return dict(self.role_ids)


def normalize_notion_id(value: object) -> str:
    """Normalize Notion UUID formatting for stable comparisons."""
    return str(value or "").strip().replace("-", "").casefold()


def notion_id_fingerprint(value: object) -> str:
    """Return an irreversible eight-character fingerprint."""
    normalized = normalize_notion_id(value)
    if not normalized:
        return "00000000"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def notion_group_fingerprint(role_ids: Mapping[str, str]) -> str:
    """Return a stable fingerprint for a complete role-to-data-source group."""
    material = "|".join(
        f"{role}:{normalize_notion_id(role_ids[role])}"
        for role in WORKSPACE_DATABASE_ORDER
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]


def _rich_text_plain_text(items: object) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(
        str(item.get("plain_text", ""))
        for item in items
        if isinstance(item, Mapping)
    ).strip()


def _object_title(payload: Mapping[str, Any]) -> str:
    direct_name = payload.get("name")
    if isinstance(direct_name, str) and direct_name.strip():
        return direct_name.strip()
    direct_title = payload.get("title")
    if isinstance(direct_title, list):
        return _rich_text_plain_text(direct_title)
    properties = payload.get("properties")
    if isinstance(properties, Mapping):
        for prop in properties.values():
            if isinstance(prop, Mapping) and prop.get("type") == "title":
                return _rich_text_plain_text(prop.get("title"))
    return ""


def _configured_role_ids(config: NotionConfig) -> dict[str, str]:
    return {
        PODCAST_LIBRARY: config.podcast_database_id,
        EXPRESSION_DATABASE: config.expression_database_id,
        VOCABULARY_DATABASE: config.vocabulary_database_id,
        WEEKLY_REVIEW: config.weekly_database_id,
    }


def _retrieve_data_source(notion: Any, data_source_id: str) -> Mapping[str, Any]:
    try:
        payload = notion.data_sources.retrieve(data_source_id=data_source_id)
    except Exception:
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED) from None
    if not isinstance(payload, Mapping):
        raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
    return payload


def _retrieve_database(notion: Any, database_id: str) -> Mapping[str, Any]:
    try:
        payload = notion.databases.retrieve(database_id=database_id)
    except Exception:
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED) from None
    if not isinstance(payload, Mapping):
        raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
    return payload


def _retrieve_parent_page(notion: Any, page_id: str) -> None:
    try:
        payload = notion.pages.retrieve(page_id=page_id)
    except Exception:
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED) from None
    if not isinstance(payload, Mapping):
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED)


def _validate_schema(
    role: str,
    data_source: Mapping[str, Any],
    role_ids: Mapping[str, str],
) -> None:
    properties = data_source.get("properties")
    if not isinstance(properties, Mapping):
        raise NotionTargetBindingError(TARGET_BINDING_VALIDATION_FAILED)

    for property_name, expected_type in REQUIRED_DATABASE_PROPERTIES[role].items():
        prop = properties.get(property_name)
        if not isinstance(prop, Mapping) or prop.get("type") != expected_type:
            raise NotionTargetBindingError(TARGET_BINDING_VALIDATION_FAILED)
        relation_target_role = (
            REQUIRED_DATABASE_RELATIONS.get(role) or {}
        ).get(property_name)
        if not relation_target_role:
            continue
        relation = prop.get("relation")
        if not isinstance(relation, Mapping):
            raise NotionTargetBindingError(TARGET_BINDING_VALIDATION_FAILED)
        if normalize_notion_id(relation.get("data_source_id")) != (
            normalize_notion_id(role_ids[relation_target_role])
        ):
            raise NotionTargetBindingError(TARGET_RELATION_OUTSIDE_GROUP)
        if "single_property" not in relation or "dual_property" in relation:
            raise NotionTargetBindingError(TARGET_RELATION_MODE_INVALID)


def validate_notion_target_binding(
    notion: Any,
    config: NotionConfig,
) -> NotionTargetBindingResult:
    """Validate Data Source, Database, parent, schema, and relation binding."""
    expected_parent = normalize_notion_id(config.target_parent_page_id)
    if not expected_parent:
        raise NotionTargetBindingError(TARGET_PARENT_NOT_CONFIGURED)

    role_ids = _configured_role_ids(config)
    normalized_role_ids = {
        role: normalize_notion_id(value) for role, value in role_ids.items()
    }
    if any(not value for value in normalized_role_ids.values()):
        raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
    if len(set(normalized_role_ids.values())) != len(WORKSPACE_DATABASE_ORDER):
        raise NotionTargetBindingError(TARGET_DATABASE_AMBIGUOUS)

    parent_ids: set[str] = set()
    database_ids: set[str] = set()
    data_sources: dict[str, Mapping[str, Any]] = {}

    for role in WORKSPACE_DATABASE_ORDER:
        data_source = _retrieve_data_source(notion, role_ids[role])
        if _object_title(data_source) != role:
            raise NotionTargetBindingError(TARGET_DATABASE_ROLE_MISMATCH)
        data_source_parent = data_source.get("parent")
        if not isinstance(data_source_parent, Mapping):
            raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
        raw_database_id = data_source_parent.get("database_id")
        database_id = normalize_notion_id(raw_database_id)
        if not database_id:
            raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
        if database_id in database_ids:
            raise NotionTargetBindingError(TARGET_DATABASE_AMBIGUOUS)
        database_ids.add(database_id)

        database = _retrieve_database(notion, str(raw_database_id))
        if _object_title(database) != role:
            raise NotionTargetBindingError(TARGET_DATABASE_ROLE_MISMATCH)
        database_sources = database.get("data_sources")
        if not isinstance(database_sources, list) or len(database_sources) != 1:
            raise NotionTargetBindingError(TARGET_DATABASE_AMBIGUOUS)
        listed_data_source_id = normalize_notion_id(
            (
                database_sources[0].get("id")
                if isinstance(database_sources[0], Mapping)
                else ""
            )
        )
        if listed_data_source_id != normalized_role_ids[role]:
            raise NotionTargetBindingError(TARGET_DATABASE_ROLE_MISMATCH)

        database_parent = database.get("parent")
        if not isinstance(database_parent, Mapping):
            raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
        parent_page_id = normalize_notion_id(database_parent.get("page_id"))
        if not parent_page_id:
            raise NotionTargetBindingError(TARGET_DATABASE_MISSING)
        parent_ids.add(parent_page_id)
        data_sources[role] = data_source

    if len(parent_ids) != 1:
        raise NotionTargetBindingError(CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP)
    configured_parent = next(iter(parent_ids))
    if configured_parent != expected_parent:
        raise NotionTargetBindingError(TARGET_PARENT_MISMATCH)

    _retrieve_parent_page(notion, config.target_parent_page_id)
    for role in WORKSPACE_DATABASE_ORDER:
        _validate_schema(role, data_sources[role], role_ids)

    result = NotionTargetBindingResult(
        valid=True,
        verified_roles=tuple(WORKSPACE_DATABASE_ORDER),
        target_parent_fingerprint=notion_id_fingerprint(configured_parent),
        target_group_fingerprint=notion_group_fingerprint(role_ids),
        configured_parent_matches_expected=True,
        all_data_sources_same_group=True,
        internal_relations_verified=True,
    )
    setattr(
        notion,
        _CACHE_ATTRIBUTE,
        _NotionTargetBindingProof(
            result=result,
            role_ids=tuple(
                (role, normalized_role_ids[role])
                for role in WORKSPACE_DATABASE_ORDER
            ),
        ),
    )
    return result


def ensure_notion_target_binding_for_write(
    notion: Any,
    *,
    configured_role_ids: Optional[Mapping[str, str]] = None,
    config: Optional[NotionConfig] = None,
) -> NotionTargetBindingResult:
    """Return a cached/validated proof before any production write call."""
    proof = getattr(notion, _CACHE_ATTRIBUTE, None)
    if isinstance(proof, _NotionTargetBindingProof):
        if configured_role_ids:
            proof_ids = proof.role_mapping()
            for role, value in configured_role_ids.items():
                if normalize_notion_id(value) != proof_ids.get(role):
                    raise NotionTargetBindingError(
                        TARGET_DATABASE_ROLE_MISMATCH
                    )
        return proof.result

    if config is None:
        try:
            config = load_notion_config()
        except NotionConfigError as exc:
            if "NOTION_TARGET_PARENT_PAGE_ID" in str(exc):
                raise NotionTargetBindingError(
                    TARGET_PARENT_NOT_CONFIGURED
                ) from None
            raise NotionTargetBindingError(
                TARGET_BINDING_VALIDATION_FAILED
            ) from None

    if configured_role_ids:
        config_ids = _configured_role_ids(config)
        for role, value in configured_role_ids.items():
            if normalize_notion_id(value) != normalize_notion_id(
                config_ids.get(role)
            ):
                raise NotionTargetBindingError(TARGET_DATABASE_ROLE_MISMATCH)

    return validate_notion_target_binding(notion, config)


def ensure_notion_page_belongs_to_role(
    notion: Any,
    page_id: str,
    expected_role: str,
    *,
    config: Optional[NotionConfig] = None,
) -> NotionTargetBindingResult:
    """Prove a caller-supplied page belongs to the configured role."""
    normalized_page_id = normalize_notion_id(page_id)
    if not normalized_page_id:
        raise NotionTargetBindingError(TARGET_PAGE_OUTSIDE_GROUP)

    result = ensure_notion_target_binding_for_write(notion, config=config)
    proof = getattr(notion, _CACHE_ATTRIBUTE, None)
    if not isinstance(proof, _NotionTargetBindingProof):
        raise NotionTargetBindingError(TARGET_BINDING_VALIDATION_FAILED)
    expected_data_source_id = proof.role_mapping().get(expected_role)
    if not expected_data_source_id:
        raise NotionTargetBindingError(TARGET_DATABASE_ROLE_MISMATCH)

    cache = getattr(notion, _PAGE_CACHE_ATTRIBUTE, None)
    if not isinstance(cache, set):
        cache = set()
        setattr(notion, _PAGE_CACHE_ATTRIBUTE, cache)
    cache_key = (normalized_page_id, expected_role)
    if cache_key in cache:
        return result

    try:
        page = notion.pages.retrieve(page_id=page_id)
    except Exception:
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED) from None
    if not isinstance(page, Mapping):
        raise NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED)
    parent = page.get("parent")
    if not isinstance(parent, Mapping):
        raise NotionTargetBindingError(TARGET_PAGE_OUTSIDE_GROUP)
    if parent.get("type") != "data_source_id":
        raise NotionTargetBindingError(TARGET_PAGE_OUTSIDE_GROUP)
    actual_data_source_id = normalize_notion_id(parent.get("data_source_id"))
    if actual_data_source_id != expected_data_source_id:
        raise NotionTargetBindingError(TARGET_PAGE_OUTSIDE_GROUP)

    cache.add(cache_key)
    return result
