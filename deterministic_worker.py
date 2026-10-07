#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, re, time
from datetime import datetime, timezone
from typing import Any

TASKS={"rapidfuzz_dedupe","splink_entity_resolution","zen_evaluate"}

def clean(v:Any,limit:int=4000)->str:
    return re.sub(r"\s+"," ",str(v or "")).strip()[:limit]

def now()->str:
    return datetime.now(timezone.utc).isoformat()

def field(record:dict[str,Any],name:str):
    if name in record:return record.get(name)
    meta=record.get("metadata")
    return meta.get(name) if isinstance(meta,dict) else None

def validate_records(job):
    rows=job.get("records")
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError("records must be a list of at most 10000")
    out=[]
    for i,r in enumerate(rows):
        if not isinstance(r,dict):continue
        rid=clean(r.get("id"),200) or f"row_{i}"
        out.append({**r,"id":rid})
    return out

def rapidfuzz_dedupe(job):
    from rapidfuzz.fuzz import token_set_ratio
    rows=validate_records(job)
    fields=[clean(x,80) for x in (job.get("match_fields") or ["name","domain","city"]) if re.fullmatch(r"[A-Za-z0-9_]+",clean(x,80))]
    threshold=float(job.get("threshold") or 94)
    if not 70<=threshold<=100:raise ValueError("threshold must be between 70 and 100")
    reps=[];clusters=[]
    for row in rows:
        key=" | ".join(clean(field(row,f),300).lower() for f in fields if clean(field(row,f),300))
        best=-1;best_score=0.0
        for i,(rep_key,_) in enumerate(reps):
            score=float(token_set_ratio(key,rep_key)) if key and rep_key else 0.0
            if score>best_score:best_score=score;best=i
        if best>=0 and best_score>=threshold:
            clusters[best]["members"].append(row["id"])
            clusters[best]["scores"][row["id"]]=best_score
        else:
            reps.append((key,row["id"]))
            clusters.append({"canonical_id":row["id"],"members":[row["id"]],"scores":{row["id"]:100.0}})
    return {"clusters":clusters,"engine":"rapidfuzz","threshold":threshold,"match_fields":fields}

def splink_entity_resolution(job):
    import pandas as pd
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on
    rows=validate_records(job)
    fields=[clean(x,80) for x in (job.get("block_fields") or ["domain","email","phone"]) if re.fullmatch(r"[A-Za-z0-9_]+",clean(x,80))]
    if not fields:raise ValueError("At least one block field is required")
    data=[]
    for r in rows:
        item={"unique_id":r["id"]}
        for f in fields:item[f]=clean(field(r,f),500).lower() or None
        data.append(item)
    if not data:return {"clusters":[],"engine":"splink_deterministic","block_fields":fields}
    df=pd.DataFrame(data)
    db=DuckDBAPI()
    sdf=db.register(df,dataset_display_name="public_entities")
    rules=[block_on(f) for f in fields]
    settings=SettingsCreator(link_type="dedupe_only",blocking_rules_to_generate_predictions=rules)
    linker=Linker(sdf,settings)
    pairs=linker.inference.deterministic_link().as_pandas_dataframe()
    parent={r["unique_id"]:r["unique_id"] for r in data}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb:parent[rb]=ra
    for _,p in pairs.iterrows():
        a=str(p.get("unique_id_l"));b=str(p.get("unique_id_r"))
        if a in parent and b in parent:union(a,b)
    groups={}
    for x in parent:groups.setdefault(find(x),[]).append(x)
    clusters=[{"canonical_id":sorted(v)[0],"members":sorted(v)} for v in groups.values()]
    clusters.sort(key=lambda x:x["canonical_id"])
    return {"clusters":clusters,"engine":"splink_deterministic","block_fields":fields,"pair_count":int(len(pairs))}

def zen_evaluate(job):
    import zen
    decision=job.get("decision")
    inputs=job.get("inputs")
    if not isinstance(decision,dict):raise ValueError("decision must be a public JDM JSON object")
    if not isinstance(inputs,list) or len(inputs)>1000:raise ValueError("inputs must be a list of at most 1000")
    engine=zen.ZenEngine()
    compiled=engine.create_decision(json.dumps(decision))
    results=[]
    for i,item in enumerate(inputs):
        if not isinstance(item,dict):raise ValueError("each input must be an object")
        results.append({"index":i,"result":compiled.evaluate(item)})
    return {"results":results,"engine":"zen-engine"}

HANDLERS={"rapidfuzz_dedupe":rapidfuzz_dedupe,"splink_entity_resolution":splink_entity_resolution,"zen_evaluate":zen_evaluate}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--out",default="out")
    a=ap.parse_args();job=json.loads(pathlib.Path(a.job).read_text(encoding="utf-8"));task=str(job.get("task_type") or "")
    if task not in TASKS:raise SystemExit("Unsupported deterministic task")
    started=now();error=None;payload={}
    try:payload=HANDLERS[task](job)
    except Exception as e:error=f"{type(e).__name__}: {e}"
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    input_count=len(job.get("records") or job.get("inputs") or [])
    if task in {"rapidfuzz_dedupe","splink_entity_resolution"} and not error:
        clusters=payload.get("clusters") or [];output_count=len(clusters);dupes=max(0,input_count-output_count)
    else:
        output_count=len(payload.get("results") or []) if not error else 0;dupes=0
    receipt={"receipt_key":"public-deterministic:"+clean(job.get("job_id"),160) if job.get("job_id") else f"public-deterministic:{int(time.time())}","worker_key":"public_ai_worker","activity_type":task,"compute_class":"github_public","provider":"deterministic_library","model":payload.get("engine") if not error else None,"status":"failed" if error else "completed","input_count":input_count,"output_count":output_count,"rejected_count":0,"duplicate_count":dupes,"stale_count":0,"promoted_count":output_count,"reasons":{},"metrics":{k:v for k,v in payload.items() if k not in {"clusters","results"}} if not error else {},"summary":error or f"{task}: {input_count} input -> {output_count} output groups/results.","started_at":started,"completed_at":now()}
    (out/"result.json").write_text(json.dumps({"job_id":job.get("job_id"),"task_type":task,**payload},ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    (out/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False))
    if error:raise SystemExit(1)
if __name__=="__main__":main()
