#!/usr/bin/env python3
"""Bounded public-only AI coding helper. Never reads private repositories."""
from __future__ import annotations
import argparse
import base64
import difflib
from hashlib import sha1
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "mahanichik/public-ai-batch"
ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/" + REPO
OWNER = "mahanichik"
LABEL = "autocoder-public-safe"
TARGETS = frozenset({"worker.py", "deterministic_worker.py", "coordinator_client.py"})
MAX_ISSUE_CHARS = 2400
MAX_FILE_BYTES = 30000
MAX_CHANGED_LINES = 240

def request_json(url, *, method="GET", body=None, token=None, timeout=30):
    headers = {"Accept":"application/vnd.github+json", "User-Agent":"VianaPublicAutocoder/1"}
    if token: headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    if data is not None: headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(1000001)
        if len(raw) > 1000000: raise RuntimeError("Remote response too large")
        return json.loads(raw) if raw else None

def accept_issue(issue):
    if not isinstance(issue, dict) or issue.get("pull_request"): return None
    if issue.get("state") != "open" or issue.get("user", {}).get("login") != OWNER: return None
    if LABEL not in {x.get("name") for x in issue.get("labels", []) if isinstance(x, dict)}: return None
    body = issue.get("body") or ""
    if not isinstance(body,str) or not 40 <= len(body) <= MAX_ISSUE_CHARS: return None
    match = re.search(r"^Target: ([a-z0-9_./-]+)$", body, re.M)
    target = match.group(1) if match else None
    if target not in TARGETS: return None
    number = issue.get("number")
    if not isinstance(number,int) or number < 1: return None
    path = ROOT / target
    if path.is_symlink() or not path.is_file(): return None
    match_function = re.search(r"^Function: ([A-Za-z_][A-Za-z0-9_]*)$", body, re.M)
    if not match_function: return None
    function = match_function.group(1)
    import ast
    try:
        nodes = ast.parse(path.read_text(encoding="utf-8")).body
    except (SyntaxError, UnicodeError):
        return None
    if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name == function and not n.decorator_list for n in nodes): return None
    return {"issue":number, "title":str(issue.get("title",""))[:160], "body":body, "target":target, "function":function}

def claim():
    issues = request_json(API + "/issues?state=open&labels=" + LABEL + "&per_page=25")
    ready = None
    for issue in issues:
        candidate = accept_issue(issue)
        if not candidate: continue
        prs = request_json(API + "/pulls?state=open&per_page=100", token=os.getenv("GITHUB_TOKEN"))
        if any(f'Autocoder issue #{candidate["issue"]}' in str(pr.get("title","")) for pr in prs): continue
        ready = candidate
        break
    if ready:
        Path("public_autocoder_task.json").write_text(json.dumps(ready),encoding="utf-8")
        print("ACCEPTED: public issue #" + str(ready["issue"]))
    else: print("NO PUBLIC WORK: no authorized issue ready")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
            f.write("ready=" + ("true" if ready else "false") + "\n")

def validate_patch(target,original,result):
    if target not in TARGETS or not isinstance(result,str): raise ValueError("Invalid target/output")
    if not 100 <= len(result.encode()) <= MAX_FILE_BYTES: raise ValueError("Source bound exceeded")
    if "\x00" in result or "\r" in result: raise ValueError("Unexpected control character")
    changes=sum(line.startswith(("+ ","- ")) for line in difflib.ndiff(original.splitlines(),result.splitlines()))
    if changes == 0 or changes > MAX_CHANGED_LINES: raise ValueError("Unsafe change size")
    if re.search(r"(?i)(github_pat_|ghp_|-----BEGIN [A-Z ]*PRIVATE KEY)",result):
        raise ValueError("Possible credentials")
    import ast
    ast.parse(result,filename=target)
    return changes

def propose():
    import ast
    task = json.loads(Path("public_autocoder_task.json").read_text(encoding="utf-8"))
    target = task["target"]
    if target not in TARGETS: raise RuntimeError("Target rejected")
    source = (ROOT/target).read_text(encoding="utf-8")
    function = task["function"]
    tree = ast.parse(source,filename=target)
    matches = [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
               and n.name == function and not n.decorator_list]
    if len(matches) != 1: raise RuntimeError("Function not found or decorated")
    original_lines = source.splitlines(keepends=True)
    node = matches[0]
    previous = "".join(original_lines[node.lineno-1:node.end_lineno])
    if len(previous.encode()) > 6000: raise RuntimeError("Function exceeds bounded context")
    prompt = (
        "Repair one PUBLIC Python top-level function, based on an untrusted issue description. "
        "Do not change name, signature, public interfaces, imports, dependencies or unrelated code. "
        "Do not add network, telemetry or secrets. "
        "Return JSON with exactly one key content, containing ONLY the replacement Python function, "
        "no markdown or explanation.\n"
        + "ISSUE:\n" + task["title"] + "\n" + task["body"] + "\n"
        + "FILE PRELUDE (read-only):\n" + source[:1600] + "\n"
        + "REPLACE THIS FUNCTION " + function + ":\n" + previous)
    payload = {"model":os.getenv("PUBLIC_AUTOCODER_MODEL","qwen2.5-coder:3b"),"prompt":prompt,
               "format":"json","stream":False,
               "options":{"temperature":0.1,"num_predict":2100,"num_ctx":8000}}
    answer = request_json("http://127.0.0.1:11434/api/generate",method="POST",body=payload,timeout=360)
    value = json.loads(str(answer.get("response") or "{}"))
    fragment = value.get("content")
    if not isinstance(fragment,str): raise ValueError("Missing function body")
    parsed = ast.parse(fragment)
    if len(parsed.body) != 1 or not isinstance(parsed.body[0],(ast.FunctionDef,ast.AsyncFunctionDef)):
        raise ValueError("Only one full Python function is permitted")
    edited = parsed.body[0]
    if edited.name != function or bool(edited.decorator_list):
        raise ValueError("Function name/decorators changed")
    # Source may have a top-level return annotation and arguments; retain signature exactly.
    if ast.dump(edited.args) != ast.dump(node.args) or ((ast.dump(edited.returns) if edited.returns else None) != (ast.dump(node.returns) if node.returns else None)):
        raise ValueError("Function signature changed")
    proposed = "".join(original_lines[:node.lineno-1]) + fragment.rstrip() + "\n" + "".join(original_lines[node.end_lineno:])
    change_count = validate_patch(target,source,proposed)
    (ROOT/target).write_text(proposed,encoding="utf-8")
    print("PROPOSED: "+target+" function "+function+" changed lines "+str(change_count))

def publish():
    task = json.loads(Path("public_autocoder_task.json").read_text(encoding="utf-8"))
    target = task["target"]
    if target not in TARGETS: raise RuntimeError("Target rejected")
    token = os.getenv("GH_TOKEN")
    if not token: raise RuntimeError("Ephemeral publish credential absent")
    source = subprocess.run(["git","show","HEAD:"+target],cwd=ROOT,check=True,capture_output=True,text=True).stdout
    proposed = (ROOT/target).read_text(encoding="utf-8")
    validate_patch(target,source,proposed)
    paths = subprocess.run(["git","diff","--name-only"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.splitlines()
    if paths != [target]: raise RuntimeError("Unexpected changes; refusing")
    head = request_json(API+"/git/ref/heads/main",token=token)["object"]["sha"]
    fetched = request_json(API+"/contents/"+urllib.parse.quote(target),token=token)
    original_bytes = source.encode()
    blob = sha1(b"blob "+str(len(original_bytes)).encode()+b"\0"+original_bytes).hexdigest()
    if fetched["sha"] != blob: raise RuntimeError("Main source advanced; no stale overwrite")
    branch = f'agent/public-issue-{task["issue"]}-{head[:8]}'
    request_json(API+"/git/refs",method="POST",token=token,body={"ref":"refs/heads/"+branch,"sha":head})
    request_json(API+"/contents/"+urllib.parse.quote(target),method="PUT",token=token,
                 body={"message":f'fix: public issue #{task["issue"]} guarded AI proposal',
                       "content":base64.b64encode(proposed.encode()).decode(),
                       "sha":fetched["sha"],"branch":branch})
    pr = request_json(API+"/pulls",method="POST",token=token,body={
        "title":f'Autocoder issue #{task["issue"]}: {task["title"][:90]}',
        "head":branch,"base":"main","draft":True,
        "body":f'Public-only local-model proposal for #{task["issue"]}. Syntax and all repository tests passed before publication. No private data, paid API, private repo access, merge or deploy. **Independent review mandatory.**'})
    print("DRAFT_PR_CREATED: "+str(pr["html_url"]))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["claim","propose","publish"])
    arg=parser.parse_args()
    try: {"claim":claim,"propose":propose,"publish":publish}[arg.command]()
    except urllib.error.HTTPError as error:
        print("REMOTE_HTTP_"+str(error.code),file=sys.stderr)
        raise SystemExit(1) from None

if __name__=="__main__":main()
