class VantaError(Exception):
    """
    Base class for all VantaEther-specific exceptions.
    
    Attributes:
        message (str): Explanation of the error.
        original_error (Exception, optional): The underlying exception that caused this error.
    """
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error

class DependencyError(VantaError):
    """Raised when an external system dependency (ffmpeg, ffprobe) is missing or incompatible."""
    pass

class NetworkError(VantaError):
    """Raised when a network operation fails (DNS, Timeout, Connection Refused)."""
    pass

class DownloadError(VantaError):
    """Raised when the download process fails (yt-dlp errors, 403 Forbidden, DRM)."""
    pass

class FileSystemError(VantaError):
    """Raised when file I/O operations fail (Permission denied, Disk full, Path invalid)."""
    pass

class AnalysisError(VantaError):
    """Raised when media analysis/parsing fails (JSON decode error, invalid codec data)."""
    pass

class ConfigurationError(VantaError):
    """Raised when there is an issue with the server or application configuration."""
    pass