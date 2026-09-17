import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import rate_limit


class RateLimitTest(unittest.TestCase):
    def setUp(self):
        rate_limit._attempts.clear()

    def request(self, peer, forwarded=None):
        request = Mock()
        request.client.host = peer
        request.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        return request

    def test_ignores_forwarded_header_from_untrusted_peer(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "127.0.0.1,::1"}):
            self.assertEqual(rate_limit.get_client_ip(self.request("203.0.113.8", "1.2.3.4")), "203.0.113.8")

    def test_uses_forwarded_header_from_trusted_proxy(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "127.0.0.1,::1"}):
            self.assertEqual(rate_limit.get_client_ip(self.request("127.0.0.1", "198.51.100.7, 127.0.0.1")), "198.51.100.7")

    def test_rejects_invalid_forwarded_ip(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "127.0.0.1"}):
            self.assertEqual(rate_limit.get_client_ip(self.request("127.0.0.1", "not-an-ip")), "127.0.0.1")

    def test_independent_account_and_ip_budgets(self):
        for _ in range(rate_limit.MAX_ATTEMPTS):
            rate_limit.record_failure("login:ip:user")
        with self.assertRaises(Exception):
            rate_limit.check_rate_limit("login:ip:user")
        rate_limit.check_rate_limit("login-ip:ip", max_attempts=rate_limit.MAX_IP_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
