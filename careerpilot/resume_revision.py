"""Replaceable revision boundary. No paid/API provider is enabled by default."""
from typing import Protocol


class RevisionProvider(Protocol):
    def capability(self) -> dict: ...
    def revise(self, verified_facts: list, job_description: str | None = None) -> list: ...


class ManualRevision:
    def capability(self):
        return {'available': False, 'mode': 'Manual revision with deterministic checks',
                'reason': 'No approved AI execution provider is configured. No documents leave this host.'}

    def revise(self, verified_facts, job_description=None):
        raise ValueError('Automated AI revision is unavailable; use the manual editor')


# A future provider requires separately verified execution capability and user authorization.
revision_provider: RevisionProvider = ManualRevision()
