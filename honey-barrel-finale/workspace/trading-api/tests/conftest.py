import os
import tempfile

os.environ["T212_MODE"] = "mock"
os.environ["AUTO_EXECUTE"] = "false"
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
