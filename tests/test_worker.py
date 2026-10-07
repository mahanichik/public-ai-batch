import json,pathlib,subprocess,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORKER=ROOT/"worker.py"

class WorkerTests(unittest.TestCase):
  def run_job(self,job):
    with tempfile.TemporaryDirectory() as td:
      d=pathlib.Path(td);jp=d/"job.json";out=d/"out"
      jp.write_text(json.dumps(job),encoding="utf-8")
      subprocess.run([sys.executable,str(WORKER),"--job",str(jp),"--out",str(out),"--deterministic-only"],check=True)
      return json.loads((out/"result.json").read_text()),json.loads((out/"receipt.json").read_text())

  def test_dedupe_stale_empty(self):
    job={"job_id":"t1","task_type":"prospect_classify","max_age_days":30,"records":[
      {"id":"a","text":"Current public market signal","observed_at":"2099-01-01T00:00:00Z","metadata":{"x":1}},
      {"id":"b","text":"Current public market signal","observed_at":"2099-01-01T00:00:00Z","metadata":{"x":1}},
      {"id":"c","text":"short","observed_at":"2099-01-01T00:00:00Z"},
      {"id":"d","text":"Old public signal that is stale","observed_at":"2020-01-01T00:00:00Z"}
    ]}
    result,receipt=self.run_job(job)
    self.assertEqual(receipt["input_count"],4);self.assertEqual(receipt["output_count"],1)
    self.assertEqual(receipt["duplicate_count"],1);self.assertEqual(receipt["stale_count"],1)
    self.assertEqual(receipt["reasons"]["empty"],1);self.assertEqual(len(result["results"]),1)

  def test_all_task_contracts_accept_deterministic_mode(self):
    for task in ["prospect_classify","market_trends","content_brief","outcome_analysis"]:
      result,receipt=self.run_job({"job_id":task,"task_type":task,"records":[{"id":"x","text":"Enough public evidence text for deterministic processing."}]})
      self.assertEqual(receipt["activity_type"],task);self.assertEqual(receipt["provider"],"deterministic");self.assertEqual(len(result["results"]),1)

if __name__=="__main__":unittest.main()
