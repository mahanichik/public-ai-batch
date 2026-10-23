import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "ops" / "public_autocoder.py"
spec = importlib.util.spec_from_file_location("public_autocoder", path)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class PublicAutocoderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        before = agent.ROOT
        agent.ROOT = Path(self.tmp.name)
        self.addCleanup(lambda: setattr(agent, "ROOT", before))
        (agent.ROOT / "worker.py").write_text("def x():\n    return 1\n")
    def issue(self, target="worker.py", login="mahanichik", label=None):
        return {"number":42, "state":"open",
                "user":{"login":login}, "title":"Public regression",
                "labels":[{"name":label or agent.LABEL}],
                "body":f"Target: {target}\nFix this generic public source behavior with a small regression-safe change."}
    def test_owner_label_mandatory(self):
        self.assertIsNone(agent.accept_issue(self.issue(login="outsider")))
        self.assertIsNone(agent.accept_issue(self.issue(label="random")))
        self.assertEqual(agent.accept_issue(self.issue())["issue"],42)
    def test_public_allowlist(self):
        for target in ("AGENTS.md","../../private","secrets.env",".github/workflows/a.yml"):
            self.assertIsNone(agent.accept_issue(self.issue(target=target)))
    def test_no_empty_or_unbounded_patch(self):
        old = "def f():\n    return 1\n" * 10
        with self.assertRaises(ValueError): agent.validate_patch("worker.py",old,old)
        with self.assertRaises(ValueError): agent.validate_patch("worker.py",old,"def f(: pass")
        with self.assertRaises(ValueError): agent.validate_patch("AGENTS.md",old,old+"x")
    def test_syntax_and_credentials(self):
        old = "def f():\n    return 1\n" * 10
        good=old.replace("return 1","return 2",1)
        self.assertGreater(agent.validate_patch("worker.py",old,good),0)
        with self.assertRaises(ValueError):
            agent.validate_patch("worker.py",old,good+"\n"+"gh"+"p_"+("x"*24)+"\n")
    def test_refuses_overlarge_issue(self):
        bad=self.issue()
        bad["body"] += "x"*3000
        self.assertIsNone(agent.accept_issue(bad))
    def test_refuses_injected_pull_request(self):
        injected=self.issue()
        injected["pull_request"]={"url":"not-an-issue"}
        self.assertIsNone(agent.accept_issue(injected))
if __name__=="__main__": unittest.main()
