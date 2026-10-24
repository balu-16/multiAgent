class DependencyUnavailable(Exception):
    """A dependency is unavailable; messages must never contain credentials."""


class DuplicateEmail(Exception):
    pass


class ProviderError(Exception):
    pass
