import unittest

import destinations


class DestinationSpecsTest(unittest.TestCase):
    def test_ixcsoft_names_carry_a_distinguishing_suffix(self):
        specs = destinations.destination_specs("ixcsoft")
        names = [name for name, _, _ in specs]
        self.assertIn("inicio-ixcsoft", names)
        self.assertIn("feriado-ixcsoft", names)
        self.assertIn("fechado-ixcsoft", names)
        self.assertIn("from-internal", names)

    def test_sgp_names_have_no_suffix(self):
        specs = destinations.destination_specs("sgp")
        names = [name for name, _, _ in specs]
        self.assertIn("inicio", names)
        self.assertNotIn("inicio-ixcsoft", names)

    def test_labels_use_uppercased_type(self):
        specs = destinations.destination_specs("sgp")
        labels = [label for _, _, label in specs]
        self.assertTrue(any("SGP" in label for label in labels))

    def test_from_internal_context_uses_departamento_variable(self):
        specs = destinations.destination_specs("ixcsoft")
        context = next(context for name, context, _ in specs if name == "from-internal")
        self.assertEqual(context, "${departamento}")


if __name__ == "__main__":
    unittest.main()
