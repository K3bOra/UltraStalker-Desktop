from __future__ import annotations

import unittest
from unittest.mock import patch

from ultrastalker_desktop import single_instance


class SingleInstanceGuardTests(unittest.TestCase):
    def test_non_windows_dev_guard_is_noop_and_reusable(self):
        guard = single_instance.SingleInstanceGuard(platform_name="posix")
        self.assertTrue(guard.acquire())
        self.assertTrue(guard.acquire())
        guard.release()
        self.assertTrue(guard.acquire())
        guard.release()

    def test_windows_first_instance_keeps_mutex_handle_until_release(self):
        closed = []
        api = (lambda _sa, _owner, _name: 123, lambda handle: closed.append(handle) or True, lambda: 0)
        guard = single_instance.SingleInstanceGuard(platform_name="nt")
        with patch.object(single_instance, "_windows_mutex_api", return_value=api):
            self.assertTrue(guard.acquire())
            self.assertEqual(closed, [])
            guard.release()
        self.assertEqual(closed, [123])

    def test_windows_second_instance_closes_duplicate_handle_and_refuses(self):
        closed = []
        api = (
            lambda _sa, _owner, _name: 456,
            lambda handle: closed.append(handle) or True,
            lambda: single_instance.ERROR_ALREADY_EXISTS,
        )
        guard = single_instance.SingleInstanceGuard(platform_name="nt")
        with patch.object(single_instance, "_windows_mutex_api", return_value=api):
            self.assertFalse(guard.acquire())
        self.assertEqual(closed, [456])
        self.assertIsNone(guard._handle)

    def test_windows_mutex_creation_failure_is_fail_closed(self):
        api = (lambda _sa, _owner, _name: 0, lambda _handle: True, lambda: 5)
        guard = single_instance.SingleInstanceGuard(platform_name="nt")
        with patch.object(single_instance, "_windows_mutex_api", return_value=api):
            with self.assertRaises(OSError):
                guard.acquire()
        self.assertIsNone(guard._handle)


if __name__ == "__main__":
    unittest.main()
