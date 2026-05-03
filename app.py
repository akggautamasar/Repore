import os
import uuid
import threading
import zipfile
import queue
import json
from flask import Flask, request, jsonify, Response, send_file, render_template_string
from flask_cors import CORS
import downloader

app = Flask(__name__)
CORS(app)

jobs = {}
jobs_lock = threading.Lock()

WORK_DIR = "/tmp/yct_jobs"
os.makedirs(WORK_DIR, exist_ok=True)

# ─── HTML FRONTEND ────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>YCT Book Downloader</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=DM+Mono&display=swap" rel="stylesheet"/>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#080815;color:#e2e2f0;font-family:'DM Sans',sans-serif;min-height:100vh;padding:32px 16px}
  h1{font-size:28px;font-weight:700;letter-spacing:-.5px}
  .sub{color:#4a4a6a;font-size:14px;margin-top:6px}
  .badge{display:inline-block;background:#6c63ff22;border:1px solid #6c63ff44;border-radius:24px;padding:3px 14px;font-size:11px;color:#9d97ff;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
  .header{text-align:center;margin-bottom:32px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:940px;margin:0 auto}
  @media(max-width:700px){.grid{grid-template-columns:1fr}}
  .card{background:#0d0d1a;border:1px solid #1e1e38;border-radius:14px;padding:24px}
  .section-label{font-size:11px;color:#4a4a6a;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;margin-top:18px}
  .section-label:first-child{margin-top:0}
  label{display:block;font-size:10px;color:#7878a8;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:5px}
  input[type=text],input[type=email],input[type=password],input[type=number]{width:100%;background:#070710;border:1px solid #2a2a4a;border-radius:6px;padding:9px 12px;color:#e2e2f0;font-size:13px;outline:none;font-family:'DM Mono',monospace;transition:border-color .2s;margin-bottom:14px}
  input:focus{border-color:#6c63ff}
  .row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
  .row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .toggle-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
  .toggle-row span{font-size:13px;color:#b0b0d0}
  .toggle{width:44px;height:24px;border-radius:12px;cursor:pointer;position:relative;transition:background .2s;border:none;outline:none}
  .toggle .knob{position:absolute;top:3px;width:18px;height:18px;border-radius:9px;background:#fff;transition:left .2s}
  .divider{height:1px;background:#1e1e38;margin:16px 0}
  .btn{width:100%;padding:14px;border-radius:10px;border:none;cursor:pointer;font-size:15px;font-weight:700;letter-spacing:.5px;transition:.2s;margin-top:12px}
  .btn-primary{background:linear-gradient(135deg,#6c63ff,#9d97ff);color:#fff}
  .btn-primary:disabled{background:#1e1e38;color:#4a4a6a;cursor:not-allowed}
  .step-row{display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid #1e1e38}
  .step-icon{font-family:monospace;font-size:18px;min-width:24px}
  .step-name{font-size:14px;font-weight:600}
  .step-detail{font-size:12px;color:#7878a8;margin-top:2px}
  .step-status{margin-left:auto;font-size:11px;text-transform:uppercase;font-family:monospace;letter-spacing:1px;white-space:nowrap;padding-left:8px}
  .log-box{background:#070710;border:1px solid #1e1e38;border-radius:8px;padding:12px;height:180px;overflow-y:auto;font-family:'DM Mono',monospace;font-size:12px;color:#7878a8;margin-top:12px}
  .progress-bar-bg{background:#1e1e38;border-radius:4px;height:6px;overflow:hidden;margin-top:6px}
  .progress-bar-fill{height:100%;background:linear-gradient(90deg,#6c63ff,#f0a500);border-radius:4px;transition:width .3s}
  .progress-label{display:flex;justify-content:space-between;margin-top:10px;margin-bottom:4px;font-size:12px}
  .downloads{background:#0d1a0d;border:1px solid #22c55e44;border-radius:10px;padding:16px;margin-top:12px;display:none}
  .downloads h3{color:#22c55e;font-size:14px;margin-bottom:10px}
  .dl-btn{display:inline-block;padding:8px 16px;border-radius:7px;background:#6c63ff22;border:1px solid #6c63ff44;color:#9d97ff;font-size:13px;text-decoration:none;margin-right:8px;margin-bottom:8px;cursor:pointer}
  .dl-btn:hover{background:#6c63ff44}
  .panel-label{font-size:11px;color:#6c63ff;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px;font-weight:600}
</style>
</head>
<body>
<div class="header">
  <div class="badge">YCT Publication Tool</div>
  <h1>Book Downloader</h1>
  <p class="sub">Configure, run, and download — deployed on Render</p>
</div>

<div class="grid">
  <div class="card">
    <div class="panel-label">⚙ Configuration</div>

    <div class="section-label">Account</div>
    <label>Email</label>
    <input type="email" id="email" placeholder="your@email.com"/>
    <label>Password</label>
    <input type="password" id="password" placeholder="••••••••"/>

    <div class="divider"></div>
    <div class="section-label">Book</div>
    <div class="row3">
      <div><label>Book ID</label><input type="number" id="bookId" value="3040"/></div>
      <div><label>Start Page</label><input type="number" id="startPage" value="1"/></div>
      <div><label>End Page</label><input type="number" id="endPage" value="50"/></div>
    </div>
    <label>Book Title</label>
    <input type="text" id="bookTitle" value="YCT Book"/>
    <div class="row2">
      <div><label>Author</label><input type="text" id="author" value="YCT Publication"/></div>
      <div><label>Workers</label><input type="number" id="maxWorkers" value="5" min="1" max="20"/></div>
    </div>

    <div class="divider"></div>
    <div class="section-label">Output</div>
    <div class="toggle-row"><span>Generate PDF</span><button class="toggle" id="tgl-pdf" onclick="doToggle('pdf')"><div class="knob" id="knob-pdf" style="left:22px"></div></button></div>
    <div class="toggle-row"><span>Generate EPUB</span><button class="toggle" id="tgl-epub" onclick="doToggle('epub')"><div class="knob" id="knob-epub" style="left:22px"></div></button></div>
    <div class="toggle-row"><span>Compress Images</span><button class="toggle" id="tgl-compress" onclick="doToggle('compress')"><div class="knob" id="knob-compress" style="left:22px"></div></button></div>

    <div class="divider"></div>
    <div class="section-label">Telegram (optional)</div>
    <label>Bot Token</label>
    <input type="password" id="tgToken" placeholder="Leave blank to skip"/>
    <label>Chat ID</label>
    <input type="text" id="tgChatId" placeholder="Leave blank to skip"/>
  </div>

  <div class="card">
    <div class="panel-label">▶ Pipeline Status</div>
    <div id="steps"></div>
    <div id="prog-wrap" style="display:none">
      <div class="progress-label">
        <span style="color:#7878a8;font-size:12px">Pages downloaded</span>
        <span id="prog-text" style="color:#f0a500;font-family:monospace;font-size:12px">0/0</span>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" id="prog-fill" style="width:0%"></div></div>
    </div>
    <div class="log-box" id="log-box"><span style="color:#2a2a4a">// output will appear here</span></div>
    <button class="btn btn-primary" id="run-btn" onclick="startJob()">⚡ Run Downloader</button>
    <div class="downloads" id="dl-section">
      <h3>✅ Files Ready — Download Before Leaving!</h3>
      <div id="dl-links"></div>
    </div>
  </div>
</div>

<script>
const STEPS = ["Login","Verify Access","Download Pages","Build PDF","Build EPUB","ZIP & Export"];
const state = {pdf:true, epub:true, compress:true};
let currentJobId = null;
let evtSrc = null;
let stepStatuses = STEPS.map(()=>"idle");
let stepDetails  = STEPS.map(()=>"");

function doToggle(key){
  state[key] = !state[key];
  document.getElementById('knob-'+key).style.left = state[key]?'22px':'3px';
  document.getElementById('tgl-'+key).style.background = state[key]?'#6c63ff':'#1e1e38';
}
['pdf','epub','compress'].forEach(k => document.getElementById('tgl-'+k).style.background='#6c63ff');

const COLOR = {idle:"#4a4a6a",running:"#f0a500",done:"#22c55e",error:"#ef4444",skipped:"#6b7280"};
const ICON  = {idle:"○",running:"◌",done:"✓",error:"✗",skipped:"—"};

function renderSteps(){
  document.getElementById('steps').innerHTML = STEPS.map((s,i)=>`
    <div class="step-row">
      <span class="step-icon" style="color:${COLOR[stepStatuses[i]]}">${ICON[stepStatuses[i]]}</span>
      <div style="flex:1;min-width:0">
        <div class="step-name" style="color:${stepStatuses[i]==='running'?'#f0a500':'#e2e2f0'}">${s}</div>
        ${stepDetails[i]?`<div class="step-detail">${stepDetails[i]}</div>`:''}
      </div>
      <span class="step-status" style="color:${COLOR[stepStatuses[i]]}">${stepStatuses[i]}</span>
    </div>`).join('');
}
renderSteps();

function addLog(msg){
  const box = document.getElementById('log-box');
  if(box.querySelector('span')) box.innerHTML='';
  const d = document.createElement('div');
  d.textContent = msg;
  d.style.color = msg.startsWith('❌')?'#ef4444': msg.startsWith('✅')?'#22c55e':'#7878a8';
  d.style.marginBottom = '2px';
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

function setProgress(done, total){
  document.getElementById('prog-wrap').style.display = 'block';
  document.getElementById('prog-text').textContent = `${done}/${total}`;
  document.getElementById('prog-fill').style.width = `${Math.round(done/total*100)}%`;
}

async function startJob(){
  const email    = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value.trim();
  if(!email || !password){ alert('Email and password are required.'); return; }

  document.getElementById('run-btn').disabled = true;
  document.getElementById('run-btn').textContent = '⏳ Running...';
  document.getElementById('dl-section').style.display = 'none';
  document.getElementById('log-box').innerHTML = '';
  document.getElementById('prog-wrap').style.display = 'none';
  stepStatuses = STEPS.map(()=>"idle");
  stepDetails  = STEPS.map(()=>"");
  renderSteps();

  const config = {
    email, password,
    book_id    : parseInt(document.getElementById('bookId').value),
    start_page : parseInt(document.getElementById('startPage').value),
    end_page   : parseInt(document.getElementById('endPage').value),
    max_workers: parseInt(document.getElementById('maxWorkers').value),
    book_title : document.getElementById('bookTitle').value,
    author     : document.getElementById('author').value,
    make_pdf   : state.pdf,
    make_epub  : state.epub,
    compress   : state.compress,
    tg_token   : document.getElementById('tgToken').value.trim(),
    tg_chat_id : document.getElementById('tgChatId').value.trim(),
  };

  try {
    const resp = await fetch('/start', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(config)
    });
    const data = await resp.json();
    if(!data.job_id){ addLog('❌ '+(data.error||'Failed to start job')); resetBtn(); return; }
    currentJobId = data.job_id;
    connectSSE(currentJobId);
  } catch(e){
    addLog('❌ Network error: '+e.message);
    resetBtn();
  }
}

function connectSSE(jobId){
  if(evtSrc) evtSrc.close();
  evtSrc = new EventSource('/stream/'+jobId);

  evtSrc.onmessage = function(e){
    let msg;
    try { msg = JSON.parse(e.data); } catch{ return; }
    if(msg.type === 'ping') return;
    if(msg.type === 'log')      addLog(msg.text);
    if(msg.type === 'step'){    stepStatuses[msg.index]=msg.status; stepDetails[msg.index]=msg.detail||''; renderSteps(); }
    if(msg.type === 'progress') setProgress(msg.done, msg.total);
    if(msg.type === 'done'){    showDownloads(msg.files); resetBtn(); evtSrc.close(); }
    if(msg.type === 'error'){   addLog('❌ '+msg.text); resetBtn(); evtSrc.close(); }
  };

  evtSrc.onerror = function(){
    addLog('⚠️ Connection lost. If the job was running, check Telegram or run again.');
    resetBtn();
    evtSrc.close();
  };
}

function showDownloads(files){
  document.getElementById('dl-section').style.display = 'block';
  document.getElementById('dl-links').innerHTML = files.map(f =>
    `<a class="dl-btn" href="/download/${currentJobId}/${encodeURIComponent(f.name)}" download="${f.name}">${f.label}</a>`
  ).join('');
}

function resetBtn(){
  const btn = document.getElementById('run-btn');
  btn.disabled = false;
  btn.textContent = '⚡ Run Downloader';
}
</script>
</body>
</html>"""


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/start", methods=["POST"])
def start_job():
    config = request.get_json(force=True, silent=True)
    if not config:
        return jsonify({"error": "Invalid JSON"}), 400

    for field in ["email", "password", "book_id", "start_page", "end_page"]:
        if field not in config:
            return jsonify({"error": f"Missing field: {field}"}), 400

    job_id = str(uuid.uuid4())
    log_q  = queue.Queue()

    with jobs_lock:
        jobs[job_id] = {"status": "running", "log_queue": log_q, "files": [], "config": config}

    threading.Thread(target=run_job, args=(job_id, config, log_q), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    q = job["log_queue"]

    def generate():
        while True:
            try:
                msg = q.get(timeout=25)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.route("/download/<job_id>/<filename>")
def download_file(job_id, filename):
    filename = os.path.basename(filename)          # prevent path traversal
    if not job_id or ".." in job_id:
        return "Bad request", 400
    filepath = os.path.join(WORK_DIR, job_id, filename)
    if not os.path.exists(filepath):
        return "File not found. Files are deleted on server restart — run the job again.", 404
    return send_file(filepath, as_attachment=True, download_name=filename)


# ─── JOB RUNNER ──────────────────────────────────────────────────────────────

def run_job(job_id, config, q):
    def send(msg):   q.put(msg)
    def log(text):   send({"type": "log", "text": text})
    def step(i, s, d=""): send({"type": "step", "index": i, "status": s, "detail": d})

    pages_dir = os.path.join(WORK_DIR, job_id, "pages")
    job_dir   = os.path.join(WORK_DIR, job_id)
    os.makedirs(pages_dir, exist_ok=True)

    try:
        # Step 0 — Login
        step(0, "running", f"Logging in as {config['email']}...")
        log("🔐 Logging in to yctpublication.com...")
        cookie = downloader.login(config["email"], config["password"])
        step(0, "done", f"Logged in")
        log("✅ Login successful!")

        # Step 1 — Verify
        step(1, "running", f"Checking Book {config['book_id']}...")
        log(f"🔍 Verifying Book {config['book_id']}...")
        downloader.verify_access(cookie, config["book_id"])
        step(1, "done", "Accessible")
        log("✅ Access confirmed!")

        # Step 2 — Download
        total = config["end_page"] - config["start_page"] + 1
        step(2, "running", f"Downloading {total} pages...")
        log(f"📖 Pages {config['start_page']}–{config['end_page']}")
        done_count = [0]

        def plog(text):
            log(text)
            if "downloaded" in text or "skipped" in text:
                done_count[0] += 1
                send({"type": "progress", "done": done_count[0], "total": total})

        ok, skipped, failed = downloader.download_pages(
            cookie, config["book_id"],
            config["start_page"], config["end_page"],
            config["max_workers"], pages_dir, plog,
        )
        step(2, "done", f"{ok} ok · {len(failed)} failed")
        log(f"📊 ✅ {ok} | ⏭️ {skipped} | ❌ {len(failed)}")

        generated = []

        # Step 3 — PDF
        if config.get("make_pdf"):
            step(3, "running", "Building PDF...")
            log("📄 Creating PDF...")
            name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}.pdf"
            mb   = downloader.make_pdf(pages_dir, os.path.join(job_dir, name), config.get("compress", True), log)
            generated.append({"name": name, "label": f"📄 PDF ({mb:.1f} MB)"})
            step(3, "done", f"{mb:.1f} MB")
        else:
            step(3, "skipped")

        # Step 4 — EPUB
        if config.get("make_epub"):
            step(4, "running", "Building EPUB...")
            log("📚 Creating EPUB...")
            name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}.epub"
            mb   = downloader.make_epub(
                pages_dir, os.path.join(job_dir, name),
                config["book_id"], config["start_page"],
                config["book_title"], config["author"],
                config.get("compress", True), log,
            )
            generated.append({"name": name, "label": f"📚 EPUB ({mb:.1f} MB)"})
            step(4, "done", f"{mb:.1f} MB")
        else:
            step(4, "skipped")

        # Step 5 — ZIP
        step(5, "running", "Zipping pages...")
        log("📦 Creating ZIP...")
        name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}_pages.zip"
        with zipfile.ZipFile(os.path.join(job_dir, name), "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in sorted(os.listdir(pages_dir)):
                zf.write(os.path.join(pages_dir, fname), fname)
        mb = os.path.getsize(os.path.join(job_dir, name)) / (1024 * 1024)
        generated.append({"name": name, "label": f"📦 ZIP ({mb:.1f} MB)"})
        step(5, "done", f"{mb:.1f} MB")
        log(f"✅ ZIP: {mb:.1f} MB")

        # Telegram
        tg_token   = config.get("tg_token", "").strip()
        tg_chat_id = config.get("tg_chat_id", "").strip()
        if tg_token and tg_chat_id:
            for f in generated:
                downloader.send_to_telegram(
                    os.path.join(job_dir, f["name"]),
                    f"<b>{config.get('book_title','YCT')}</b> | {f['label']}",
                    tg_token, tg_chat_id, log,
                )

        log("🎉 All done!")
        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["files"]  = generated
        send({"type": "done", "files": generated})

    except Exception as e:
        import traceback
        print(f"[JOB {job_id}] TRACEBACK:\n{traceback.format_exc()}")
        log(f"❌ {e}")
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        send({"type": "error", "text": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
