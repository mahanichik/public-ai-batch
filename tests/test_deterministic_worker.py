import json,pathlib,subprocess,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORKER=ROOT/"deterministic_worker.py"
PASSTHROUGH={
  "contentType":"application/vnd.gorules.decision",
  "nodes":[
    {"type":"inputNode","id":"4354dede-b4ed-4a57-9b80-45c1e33e2326","name":"request","position":{"x":90,"y":200}},
    {"type":"outputNode","id":"27e18970-f565-43eb-859e-568c9f53b7a8","name":"response","position":{"x":510,"y":200}}
  ],
  "edges":[{"id":"4c036317-bc39-4ad2-a825-adbfd4ca2df6","sourceId":"4354dede-b4ed-4a57-9b80-45c1e33e2326","type":"edge","targetId":"27e18970-f565-43eb-859e-568c9f53b7a8"}]
}
class DeterministicTests(unittest.TestCase):
  def run_job(self,job):
    with tempfile.TemporaryDirectory() as td:
      d=pathlib.Path(td);jp=d/"job.json";out=d/"out"
      jp.write_text(json.dumps(job),encoding="utf-8")
      subprocess.run([sys.executable,str(WORKER),"--job",str(jp),"--out",str(out)],check=True)
      return json.loads((out/"result.json").read_text()),json.loads((out/"receipt.json").read_text())

  def test_rapidfuzz_conservative_cluster(self):
    result,receipt=self.run_job({"job_id":"rf","task_type":"rapidfuzz_dedupe","threshold":92,"match_fields":["name","city"],"records":[
      {"id":"a","name":"Example Hotel","city":"Example City"},{"id":"b","name":"Example Hotels","city":"Example City"},{"id":"c","name":"Different Cafe","city":"Example City"}]})
    self.assertEqual(receipt["status"],"completed")
    self.assertEqual(len(result["clusters"]),2)

  def test_splink_exact_identifier_link(self):
    result,receipt=self.run_job({"job_id":"sp","task_type":"splink_entity_resolution","block_fields":["domain"],"records":[
      {"id":"a","domain":"example.test"},{"id":"b","domain":"example.test"},{"id":"c","domain":"other.test"}]})
    self.assertEqual(receipt["status"],"completed")
    groups=[set(x["members"]) for x in result["clusters"]]
    self.assertIn({"a","b"},groups)

  def test_zen_passthrough(self):
    result,receipt=self.run_job({"job_id":"zen","task_type":"zen_evaluate","decision":PASSTHROUGH,"inputs":[{"value":7}]})
    self.assertEqual(receipt["status"],"completed")
    self.assertEqual(len(result["results"]),1)

if __name__=="__main__":unittest.main()
