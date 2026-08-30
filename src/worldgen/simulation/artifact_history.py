"""Event-sourced ownership, location, and condition histories for legendary artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent

ARTIFACT_TRANSITIONS = (
    "gift",
    "inheritance",
    "trade",
    "theft",
    "loss",
    "recovery",
    "destruction",
)
ARTIFACT_STATUSES = {"intact", "lost", "destroyed"}


@dataclass(frozen=True)
class ArtifactHistoryEntry:
    entry_id: str
    artifact_id: str
    transition: str
    prior_owner_id: str
    new_owner_id: str
    prior_site_id: str
    new_site_id: str
    prior_status: str
    new_status: str
    prior_event_id: str
    event_id: str
    year: int


def project_artifact_histories(
    seed: int,
    events: tuple[HistoryEvent, ...],
) -> tuple[ArtifactHistoryEntry, ...]:
    """Validate a complete, causal lifecycle for every commissioned artifact."""
    event_by_id = {event.event_id: event for event in events}
    current: dict[str, tuple[str, str, str, str]] = {}
    entries: list[ArtifactHistoryEntry] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is ConsequenceKind.ARTIFACT_CREATE:
                if event.kind is not EventKind.COMMISSION or consequence.subject in current:
                    raise ValueError("WG-ARTIFACT-HISTORY: invalid or duplicate creation")
                current[consequence.subject] = (
                    consequence.target,
                    consequence.value,
                    "intact",
                    event.event_id,
                )
                entries.append(
                    ArtifactHistoryEntry(
                        stable_id(
                            "artifact_history_entry",
                            seed,
                            identity("event_id", event.event_id),
                            identity("consequence_index", index),
                        ),
                        consequence.subject,
                        "creation",
                        "",
                        consequence.target,
                        "",
                        consequence.value,
                        "",
                        "intact",
                        "",
                        event.event_id,
                        event.year,
                    )
                )
            elif consequence.kind is ConsequenceKind.ARTIFACT_TRANSITION:
                details = dict(consequence.details)
                prior = current.get(consequence.subject)
                transition = details.get("transition", "")
                new_owner = consequence.target
                new_site = details.get("new_site_id", "")
                new_status = details.get("new_status", "")
                if (
                    event.kind is not EventKind.ARTIFACT_HISTORY
                    or prior is None
                    or transition not in ARTIFACT_TRANSITIONS
                    or new_status not in ARTIFACT_STATUSES
                    or details.get("prior_owner_id", "") != prior[0]
                    or details.get("prior_site_id", "") != prior[1]
                    or details.get("prior_status", "") != prior[2]
                    or details.get("prior_event_id", "") != prior[3]
                    or prior[3] not in event.causes
                    or (
                        transition == "inheritance"
                        and not any(
                            cause in event_by_id and event_by_id[cause].kind is EventKind.SUCCESSION
                            for cause in event.causes
                        )
                    )
                    or (transition == "loss" and (new_owner or new_status != "lost"))
                    or (transition == "destruction" and new_status != "destroyed")
                    or (transition == "recovery" and (not new_owner or new_status != "intact"))
                    or (
                        transition in {"gift", "inheritance", "trade", "theft"}
                        and (not new_owner or new_status != "intact")
                    )
                ):
                    raise ValueError("WG-ARTIFACT-HISTORY: broken lifecycle transition")
                current[consequence.subject] = (
                    new_owner,
                    new_site,
                    new_status,
                    event.event_id,
                )
                entries.append(
                    ArtifactHistoryEntry(
                        stable_id(
                            "artifact_history_entry",
                            seed,
                            identity("event_id", event.event_id),
                            identity("consequence_index", index),
                        ),
                        consequence.subject,
                        transition,
                        prior[0],
                        new_owner,
                        prior[1],
                        new_site,
                        prior[2],
                        new_status,
                        prior[3],
                        event.event_id,
                        event.year,
                    )
                )
    if len({entry.entry_id for entry in entries}) != len(entries):
        raise ValueError("WG-ARTIFACT-HISTORY: duplicate entry identity")
    if any(entry.prior_event_id and entry.prior_event_id not in event_by_id for entry in entries):
        raise ValueError("WG-ARTIFACT-HISTORY: missing predecessor event")
    return tuple(entries)
