"""
User-facing HTTP error messages (shown in the UI via FastAPI `detail`).

Log the real exception separately with `get_logger()` — never rely on raw tracebacks
in API responses for 4xx paths.
"""

# --- server path validation (e.g. filesystem_dir inputs) ---
PATH_NOT_FOUND = "We couldn’t find that folder on the server. Check that the path exists and try again."
PATH_NOT_A_FOLDER = "That path isn’t a folder. Please use a directory path."
PATH_PERMISSION_DENIED = "The server can’t read that folder (permission denied). Try another location or fix permissions."

# --- generic API errors ---
GENERIC_BAD_REQUEST = (
    "We couldn’t use that request. Please check your input and try again."
)
GENERIC_SERVER_ERROR = (
    "Something went wrong on the server. Please try again in a moment."
)

# --- process-batch ---
PROCESSING_FAILED = "Processing couldn’t finish. Please try again."
BATCH_JOB_NOT_FOUND = (
    "We couldn’t find that batch job. It may have expired — start processing again."
)

# --- download batch output ---
BATCH_DOWNLOAD_NOT_FOUND = "That download link is invalid or the file is no longer available. Run processing again."
