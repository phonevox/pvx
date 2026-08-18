import unittest

from plan import DEFAULT_PORT, DEFAULT_PUBLIC_KEY, DEFAULT_ROOT_PASSWORD, DEFAULT_USERNAME, build_plan


class BuildPlanTest(unittest.TestCase):
    def test_returns_none_when_nothing_selected(self):
        plan = build_plan(
            lock_root=False,
            root_password=None,
            create_user=False,
            username=None,
            public_key=None,
            allow_password=False,
            user_password=None,
            change_port=False,
            port=None,
        )
        self.assertIsNone(plan)

    def test_applies_default_root_password_when_locking_root_without_one(self):
        plan = build_plan(
            lock_root=True, root_password=None,
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertEqual(plan["root_password"], DEFAULT_ROOT_PASSWORD)

    def test_keeps_explicit_root_password_when_provided(self):
        plan = build_plan(
            lock_root=True, root_password="custom-pass",
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertEqual(plan["root_password"], "custom-pass")

    def test_root_password_is_none_when_lock_root_is_false(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertIsNone(plan["root_password"])

    def test_applies_default_username_and_key_when_creating_user_without_them(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertEqual(plan["username"], DEFAULT_USERNAME)
        self.assertEqual(plan["public_key"], DEFAULT_PUBLIC_KEY)

    def test_raises_on_invalid_username(self):
        with self.assertRaises(ValueError):
            build_plan(
                lock_root=False, root_password=None,
                create_user=True, username="Invalid User", public_key=None, allow_password=False, user_password=None,
                change_port=False, port=None,
            )

    def test_raises_on_invalid_public_key(self):
        with self.assertRaises(ValueError):
            build_plan(
                lock_root=False, root_password=None,
                create_user=True, username=None, public_key="not-a-key", allow_password=False, user_password=None,
                change_port=False, port=None,
            )

    def test_generates_a_24_char_password_when_allow_password_and_none_given(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=True, user_password=None,
            change_port=False, port=None,
        )
        self.assertEqual(len(plan["user_password"]), 24)
        self.assertTrue(plan["user_password"].isalnum())

    def test_keeps_explicit_user_password_when_provided(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=True, user_password="mypass",
            change_port=False, port=None,
        )
        self.assertEqual(plan["user_password"], "mypass")

    def test_user_password_is_none_when_allow_password_is_false(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertIsNone(plan["user_password"])

    def test_applies_default_port_when_changing_port_without_one(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=True, port=None,
        )
        self.assertEqual(plan["port"], DEFAULT_PORT)

    def test_raises_on_invalid_port(self):
        with self.assertRaises(ValueError):
            build_plan(
                lock_root=False, root_password=None,
                create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
                change_port=True, port="99999",
            )

    def test_plan_reflects_only_the_selected_toggles(self):
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )
        self.assertFalse(plan["lock_root"])
        self.assertTrue(plan["create_user"])
        self.assertFalse(plan["change_port"])
        self.assertIsNone(plan["port"])


if __name__ == "__main__":
    unittest.main()
