class SourceDiscoveryError(Exception):
    """A safe, user-facing source failure that excludes upstream response data."""


class SourceFetchError(SourceDiscoveryError):
    pass


class SourceNormalizationError(SourceDiscoveryError):
    pass
