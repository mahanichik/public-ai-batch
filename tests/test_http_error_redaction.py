import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("public_ai_worker_for_redaction",ROOT/"worker.py")
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class ErrorRedactionTests(unittest.TestCase):
    def test_public_http_error_never_echoes_provider_body(self):
        secret="PRIVATE-CUSTOMER-DATA-DO-NOT-LOG"
        error=HTTPError("https://provider.example/v1/query?key=HIDDEN",403,"Forbidden",{},
                        io.BytesIO(secret.encode()))
        with patch.object(worker.urllib.request,"urlopen",side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                worker.http_json("GET","https://provider.example/v1/query?key=HIDDEN")
        message=str(caught.exception)
        self.assertIn("HTTP 403",message)
        self.assertIn("provider.example",message)
        self.assertNotIn(secret,message)
        self.assertNotIn("HIDDEN",message)
        self.assertNotIn("/v1/query",message)

if __name__=="__main__":
    unittest.main()
