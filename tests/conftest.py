import os
import tempfile

# Point the real app at a throwaway data dir before any app module is imported,
# so tests never touch the development database.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="flat-expenses-test-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_PASSWORD", None)
