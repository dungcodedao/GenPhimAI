import base64
import json
import unittest
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensing import verify_token, LicenseError


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key()
        self.payload = dict(v=1, product='AppVideoAI', machine='A'*32,
                            customer='Tester', issued_at=1900000000,
                            expires_at=2000000000, license_id='test-id')

    def token(self):
        data = json.dumps(self.payload).encode()
        return base64.urlsafe_b64encode(data).decode() + '.' + base64.urlsafe_b64encode(self.private.sign(data)).decode()

    def verify(self, token=None, machine='A'*32, now=1950000000):
        return verify_token(token or self.token(), self.public, machine, now)

    def test_valid(self):
        self.assertEqual(self.verify()['customer'], 'Tester')

    def test_wrong_machine(self):
        with self.assertRaises(LicenseError):
            self.verify(machine='B'*32)

    def test_portable_key_accepts_another_machine(self):
        self.payload['machine'] = '*'
        self.assertEqual(self.verify(machine='B'*32)['machine'], '*')

    def test_portable_key_still_expires(self):
        self.payload['machine'] = '*'
        with self.assertRaises(LicenseError):
            self.verify(now=2000000000)

    def test_expired_at_boundary(self):
        with self.assertRaises(LicenseError):
            self.verify(now=2000000000)

    def test_tampering(self):
        token = self.token()
        data, signature = token.split('.')
        changed = base64.urlsafe_b64encode(base64.urlsafe_b64decode(data).replace(b'Tester', b'Hacker')).decode()
        with self.assertRaises(LicenseError):
            self.verify(changed + '.' + signature)

    def test_wrong_signing_key(self):
        with self.assertRaises(LicenseError):
            verify_token(self.token(), Ed25519PrivateKey.generate().public_key(), 'A'*32, 1950000000)

    def test_clock_before_issue(self):
        with self.assertRaises(LicenseError):
            self.verify(now=1800000000)

    def test_bad_schema(self):
        self.payload['expires_at'] = 'forever'
        with self.assertRaises(LicenseError):
            self.verify()

    def test_malformed(self):
        for token in ['abc', '!.!', 'x'*9000]:
            with self.assertRaises(LicenseError):
                self.verify(token)
