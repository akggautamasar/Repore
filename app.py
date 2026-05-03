import os
import uuid
import threading
import zipfile
import queue
import time
import json
from flask import Flask, request, jsonify, Response, send_file, render_template_string
from flask_cors import CORS
import downloader

app = Flask(__name__)
CORS(app)

# In-memory job store: {job_id: {status, log_queue, files, config}}
jobs = {}
jobs_lock = threading.Lock()

WORK_DIR = "/tmp/yct_jobs"
os.makedirs(WORK_DIR, exist_ok=True)

# ─── HTML FRONTEND ──────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
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
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:900px;margin:0 auto}
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
  .step-status{margin-left:auto;font-size:11px;text-transform:uppercase;font-family:monospace;letter-spacing:1px}
  .log-box{background:#070710;border:1px solid #1e1e38;border-radius:8px;padding:12px;height:180px;overflow-y:auto;font-family:'DM Mono',monospace;font-size:12px;color:#7878a8;margin-top:12px}
  .progress-bar-bg{background:#1e1e38;border-radius:4px;height:6px;overflow:hidden;margin-top:6px}
  .progress-bar-fill{height:100%;background:linear-gradient(90deg,#6c63ff,#f0a500);border-radius:4px;transition:width .3s}
  .progress-label{display:flex;justify-content:space-between;margin-top:10px;margin-bottom:4px;font-size:12px}
  .downloads{background:#0d1a0d;border:1px solid #22c55e44;border-radius:10px;padding:16px;margin-top:12px;display:none}
  .downloads h3{color:#22c55e;font-size:14px;margin-bottom:10px}
  .dl-btn{display:inline-block;padding:8px 16px;border-radius:7px;background:#6c63ff22;border:1px solid #6c63ff44;color:#9d97ff;font-size:13px;text-decoration:none;margin-right:8px;margin-bottom:8px;cursor:pointer;font-family:'DM Sans',sans-serif}
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
  <!-- CONFIG -->
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
    <div class="toggle-row"><span>Generate PDF</span><button class="toggle" id="tgl-pdf" onclick="toggle('pdf')"><div class="knob" id="knob-pdf" style="left:22px"></div></button></div>
    <div class="toggle-row"><span>Generate EPUB</span><button class="toggle" id="tgl-epub" onclick="toggle('epub')"><div class="knob" id="knob-epub" style="left:22px"></div></button></div>
    <div class="toggle-row"><span>Compress Images</span><button class="toggle" id="tgl-compress" onclick="toggle('compress')"><div class="knob" id="knob-compress" style="left:22px"></div></button></div>

    <div class="divider"></div>
    <div class="section-label">Telegram (optional)</div>
    <label>Bot Token</label>
    <input type="password" id="tgToken" placeholder="8284..."/>
    <label>Chat ID</label>
    <input type="text" id="tgChatId" placeholder="7441256901"/>
  </div>

  <!-- PROGRESS -->
  <div class="card">
    <div class="panel-label">▶ Pipeline Status</div>
    <div id="steps">
      <!-- steps injected by JS -->
    </div>
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
      <h3>✅ Files Ready</h3>
      <div id="dl-links"></div>
    </div>
  </div>
</div>

<script>
const STEPS = ["Login","Verify Access","Download Pages","Build PDF","Build EPUB","ZIP & Export"];
const state = {pdf:true, epub:true, compress:true};
let currentJobId = null;
let eventSource = null;
let stepStatuses = STEPS.map(()=>"idle");
let stepDetails = STEPS.map(()=>"");
let totalPages = 0;
let donePages = 0;

function toggle(key){
  state[key]=!state[key];
  const knob=document.getElementById('knob-'+key);
  const btn=document.getElementById('tgl-'+key);
  knob.style.left=state[key]?'22px':'3px';
  btn.style.background=state[key]?'#6c63ff':'#1e1e38';
}

// init toggle colors
['pdf','epub','compress'].forEach(k=>{
  document.getElementById('tgl-'+k).style.background='#6c63ff';
});

const statusColor={idle:"#4a4a6a",running:"#f0a500",done:"#22c55e",error:"#ef4444",skipped:"#6b7280"};
const statusIcon={idle:"○",running:"◌",done:"✓",error:"✗",skipped:"—"};

function renderSteps(){
  const el=document.getElementById('steps');
  el.innerHTML=STEPS.map((s,i)=>`
    <div class="step-row">
      <span class="step-icon" style="color:${statusColor[stepStatuses[i]]}">${statusIcon[stepStatuses[i]]}</span>
      <div>
        <div class="step-name" style="color:${stepStatuses[i]==='running'?'#f0a500':'#e2e2f0'}">${s}</div>
        ${stepDetails[i]?`<div class="step-detail">${stepDetails[i]}</div>`:''}
      </div>
      <span class="step-status" style="color:${statusColor[stepStatuses[i]]}">${stepStatuses[i]}</span>
    </div>
  `).join('');
}
renderSteps();

function addLog(msg){
  const box=document.getElementById('log-box');
  const line=document.createElement('div');
  line.textContent=msg;
  line.style.color=msg.startsWith('❌')?'#ef4444':msg.startsWith('✅')?'#22c55e':'#7878a8';
  line.style.marginBottom='2px';
  if(box.querySelector('span')) box.innerHTML='';
  box.appendChild(line);
  box.scrollTop=box.scrollHeight;
}

function updateProgress(done, total){
  if(total>0){
    document.getElementById('prog-wrap').style.display='block';
    document.getElementById('prog-text').textContent=`${done}/${total}`;
    document.getElementById('prog-fill').style.width=`${Math.round(done/total*100)}%`;
  }
}

async function startJob(){
  const email=document.getElementById('email').value.trim();
  const password=document.getElementById('password').value.trim();
  if(!email||!password){alert('Email and password are required.');return;}

  document.getElementById('run-btn').disabled=true;
  document.getElementById('run-btn').textContent='⏳ Running...';
  document.getElementById('dl-section').style.display='none';
  document.getElementById('log-box').innerHTML='';
  stepStatuses=STEPS.map(()=>"idle");
  stepDetails=STEPS.map(()=>"");
  renderSteps();

  const config={
    email, password,
    book_id: parseInt(document.getElementById('bookId').value),
    start_page: parseInt(document.getElementById('startPage').value),
    end_page: parseInt(document.getElementById('endPage').value),
    max_workers: parseInt(document.getElementById('maxWorkers').value),
    book_title: document.getElementById('bookTitle').value,
    author: document.getElementById('author').value,
    make_pdf: state.pdf,
    make_epub: state.epub,
    compress: state.compress,
    tg_token: document.getElementById('tgToken').value,
    tg_chat_id: document.getElementById('tgChatId').value,
  };
  totalPages=config.end_page-config.start_page+1;

  const resp=await fetch('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
  const data=await resp.json();
  if(!data.job_id){addLog('❌ Failed to start job: '+(data.error||'Unknown'));resetBtn();return;}

  currentJobId=data.job_id;
  listenSSE(currentJobId);
}

function listenSSE(jobId){
  if(eventSource) eventSource.close();
  eventSource=new EventSource('/stream/'+jobId);
  eventSource.onmessage=function(e){
    const msg=JSON.parse(e.data);

    if(msg.type==='log') addLog(msg.text);
    if(msg.type==='step'){
      stepStatuses[msg.index]=msg.status;
      stepDetails[msg.index]=msg.detail||'';
      renderSteps();
    }
    if(msg.type==='progress'){
      updateProgress(msg.done, msg.total);
    }
    if(msg.type==='done'){
      renderDoneLinks(msg.files);
      resetBtn();
      eventSource.close();
    }
    if(msg.type==='error'){
      addLog('❌ '+msg.text);
      resetBtn();
      eventSource.close();
    }
  };
  eventSource.onerror=function(){
    addLog('⚠️ Connection lost.');
    resetBtn();
    eventSource.close();
  };
}

function renderDoneLinks(files){
  const section=document.getElementById('dl-section');
  const links=document.getElementById('dl-links');
  section.style.display='block';
  links.innerHTML=files.map(f=>`<a class="dl-btn" href="/download/${currentJobId}/${f.name}" download>${f.label}</a>`).join('');
}

function resetBtn(){
  const btn=document.getElementById('run-btn');
  btn.disabled=false;
  btn.textContent='⚡ Run Downloader';
}
</script>
</body>
</html>"""


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/start", methods=["POST"])
def start_job():
    config = request.get_json()
    job_id = str(uuid.uuid4())
    log_q = queue.Queue()

    with jobs_lock:
        jobs[job_id] = {
            "status": "running",
            "log_queue": log_q,
            "files": [],
            "config": config,
        }

    thread = threading.Thread(target=run_job, args=(job_id, config, log_q), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        q = job["log_queue"]
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/download/<job_id>/<filename>")
def download_file(job_id, filename):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    job_dir = os.path.join(WORK_DIR, job_id)
    filepath = os.path.join(job_dir, filename)
    if not os.path.exists(filepath):
        return "File not found", 404
    return send_file(filepath, as_attachment=True)


# ─── JOB RUNNER ─────────────────────────────────────────────────────────────

def run_job(job_id, config, q):
    def send(msg):
        q.put(msg)

    def log(text):
        send({"type": "log", "text": text})

    def step(index, status, detail=""):
        send({"type": "step", "index": index, "status": status, "detail": detail})

    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    pages_dir = os.path.join(job_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    try:
        # Step 0: Login
        step(0, "running", f"Logging in as {config['email']}...")
        log("🔐 Logging in to yctpublication.com...")
        session_cookie = downloader.login(config["email"], config["password"])
        step(0, "done", f"Logged in as {config['email']}")
        log("✅ Login successful!")

        # Step 1: Verify
        step(1, "running", f"Checking Book {config['book_id']} access...")
        log(f"🔍 Verifying access to Book {config['book_id']}...")
        downloader.verify_access(session_cookie, config["book_id"])
        step(1, "done", f"Book {config['book_id']} accessible")
        log("✅ Access confirmed!")

        # Step 2: Download
        total = config["end_page"] - config["start_page"] + 1
        step(2, "running", f"Downloading {total} pages...")
        log(f"📖 Starting download: pages {config['start_page']}–{config['end_page']}")

        ok_count = [0]

        def log_with_progress(text):
            log(text)
            if text.startswith("✅ Page"):
                ok_count[0] += 1
                send({"type": "progress", "done": ok_count[0], "total": total})

        ok, skipped, failed = downloader.download_pages(
            session_cookie, config["book_id"],
            config["start_page"], config["end_page"],
            config["max_workers"], pages_dir, log_with_progress
        )
        step(2, "done", f"{ok} downloaded, {len(failed)} failed")
        log(f"📊 Download done! ✅ {ok} | ⏭️ {skipped} | ❌ {len(failed)}")

        generated_files = []

        # Step 3: PDF
        if config.get("make_pdf"):
            step(3, "running", "Building PDF...")
            log("📄 Creating PDF...")
            pdf_name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}.pdf"
            pdf_path = os.path.join(job_dir, pdf_name)
            downloader.make_pdf(pages_dir, pdf_path, config.get("compress", True), log)
            generated_files.append({"name": pdf_name, "label": f"📄 Download PDF"})
            step(3, "done", f"PDF ready")
        else:
            step(3, "skipped")

        # Step 4: EPUB
        if config.get("make_epub"):
            step(4, "running", "Building EPUB...")
            log("📚 Creating EPUB...")
            epub_name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}.epub"
            epub_path = os.path.join(job_dir, epub_name)
            downloader.make_epub(
                pages_dir, epub_path, config["book_id"],
                config["start_page"], config["book_title"],
                config["author"], config.get("compress", True), log
            )
            generated_files.append({"name": epub_name, "label": f"📚 Download EPUB"})
            step(4, "done", f"EPUB ready")
        else:
            step(4, "skipped")

        # Step 5: ZIP
        step(5, "running", "Creating ZIP...")
        log("📦 Zipping pages...")
        zip_name = f"yct_{config['book_id']}_{config['start_page']}_{config['end_page']}_pages.zip"
        zip_path = os.path.join(job_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(pages_dir):
                zf.write(os.path.join(pages_dir, fname), fname)
        zip_mb = os.path.getsize(zip_path) / (1024 * 1024)
        generated_files.append({"name": zip_name, "label": f"📦 Download ZIP ({zip_mb:.1f} MB)"})
        step(5, "done", f"ZIP ready — {zip_mb:.1f} MB")
        log(f"✅ ZIP ready! {zip_mb:.1f} MB")

        # Telegram
        if config.get("tg_token") and config.get("tg_chat_id"):
            for f in generated_files:
                fpath = os.path.join(job_dir, f["name"])
                downloader.send_to_telegram(
                    fpath,
                    f"<b>{config['book_title']}</b> | {f['label']}",
                    config["tg_token"], config["tg_chat_id"], log
                )

        log("🎉 All done!")
        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["files"] = generated_files
        send({"type": "done", "files": generated_files})

    except Exception as e:
        log(f"❌ Error: {e}")
        step_indices = [0, 1, 2, 3, 4, 5]
        for i in step_indices:
            pass  # don't mass-error all steps
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        send({"type": "error", "text": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
