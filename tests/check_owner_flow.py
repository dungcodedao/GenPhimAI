"""Manual integration check under the owner's Windows account; no license retained."""
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from admin_tools.key_manager import issue
import licensing
from engine import run_process, binary

private = Path(__file__).resolve().parents[2] / 'AppVideoAI-Owner' / 'owner-private.dpapi'
token, payload = issue(private, licensing.machine_id(), 'Integration check', int(time.time()) + 600)
with tempfile.TemporaryDirectory(prefix='license-check-', dir=Path(__file__).resolve().parents[1]) as tmp:
    root = Path(tmp)
    with patch('licensing.license_path', return_value=root / 'license.key'):
        data = licensing.activate(token)
        assert licensing.require_license()['license_id'] == payload['license_id']
        run_process([binary('ffmpeg'), '-version'], root, root / 'process.log', threading.Event())
        with patch('licensing.time.time', return_value=payload['expires_at']):
            try:
                run_process([binary('ffmpeg'), '-version'], root, root / 'expired.log', threading.Event())
            except licensing.LicenseError:
                pass
            else:
                raise AssertionError('Expired key did not block processing')
print('Owner signing, activation persistence, export gate and expiry: PASS. No active license saved.')
