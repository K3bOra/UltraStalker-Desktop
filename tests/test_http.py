from __future__ import annotations

import unittest

from ultrastalker_desktop.core.http import make_session, request_timeout, safe_request_error


class HttpPolicyTests(unittest.TestCase):
    def test_request_timeout_keeps_read_budget_but_caps_connect_wait(self):
        self.assertEqual(request_timeout(15), (5.0, 15.0))
        self.assertEqual(request_timeout(20), (5.0, 20.0))
        self.assertEqual(request_timeout(8, 4), (4.0, 8.0))
        self.assertEqual(request_timeout(3), (3.0, 3.0))

    def test_retry_policy_is_bounded_and_get_only(self):
        session = make_session(retries=2, backoff=0.25)
        retry = session.get_adapter('https://').max_retries
        self.assertEqual(retry.total, 2)
        self.assertEqual(retry.connect, 2)
        self.assertEqual(retry.read, 2)
        self.assertEqual(retry.status, 2)
        self.assertIn('GET', retry.allowed_methods)
        self.assertIn('HEAD', retry.allowed_methods)
        self.assertNotIn('POST', retry.allowed_methods)
        self.assertEqual(set(retry.status_forcelist), {429, 500, 502, 503, 504})
        self.assertTrue(retry.respect_retry_after_header)

    def test_retry_policy_does_not_retry_auth_or_client_errors(self):
        retry = make_session().get_adapter('https://').max_retries
        for code in (400, 401, 403, 404, 405):
            self.assertNotIn(code, retry.status_forcelist)

    def test_safe_request_error_never_uses_exception_text(self):
        class BoomError(RuntimeError):
            pass
        exc = BoomError('https://user:password@example.test/path?token=secret')
        text = safe_request_error(exc, 'Portal failed')
        self.assertEqual(text, 'Portal failed (BoomError)')
        self.assertNotIn('secret', text.lower())
        self.assertNotIn('example.test', text)


if __name__ == '__main__':
    unittest.main()
