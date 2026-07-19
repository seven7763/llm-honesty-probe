import unittest

from llm_honesty_probe import redaction


class RedactionTest(unittest.TestCase):
    def setUp(self):
        redaction.clear_secrets()

    def tearDown(self):
        redaction.clear_secrets()

    def test_registered_secret_is_scrubbed(self):
        redaction.register_secret("super-secret-value-123456")
        out = redaction.redact("here is super-secret-value-123456 in text")
        self.assertNotIn("super-secret-value-123456", out)
        self.assertIn("***REDACTED***", out)

    def test_openai_key_shape_scrubbed(self):
        out = redaction.redact("Authorization: Bearer sk-abcdEFGH1234567890xyz")
        self.assertNotIn("sk-abcdEFGH1234567890xyz", out)

    def test_anthropic_key_shape_scrubbed(self):
        out = redaction.redact("x-api-key: sk-ant-abcdEFGH1234567890")
        self.assertNotIn("sk-ant-abcdEFGH1234567890", out)

    def test_empty_is_safe(self):
        self.assertEqual(redaction.redact(""), "")


if __name__ == "__main__":
    unittest.main()
