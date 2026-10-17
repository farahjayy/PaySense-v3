"""Errors shared by the UAT tools. Kept apart so the persona shifter (used by the API's
`load_personas.py`) needs no analysis dependencies."""


class UatDataError(ValueError):
    """A response file that cannot be trusted."""
