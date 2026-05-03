import requests
import base64
import time
import os
import io
import concurrent.futures
from PIL import Image
import ebooklib
from ebooklib import epub

BASE_URL = "https://yctpublication.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Origin": BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def login(email, password):
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(f"{BASE_URL}/login", headers={**HEADERS, "Referer": BASE_URL})
    resp = session.post(
        f"{BASE_URL}/LoginController/login1",
        data={"email": email, "password": password},
        headers={**HEADERS, "Referer": f"{BASE_URL}/login", "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
        timeout=30,
    )
    if "login" in resp.url.lower():
        raise Exception("Login failed. Check credentials.")
    cookie = session.cookies.get("ci_session")
    if not cookie:
        raise Exception("No session cookie received after login.")
    return cookie


def verify_access(session_cookie, book_id):
    s = requests.Session()
    s.cookies.set("ci_session", session_cookie)
    s.headers.update(HEADERS)
    resp = s.get(
        f"{BASE_URL}/getPage/{book_id}/1",
        headers={**HEADERS, "Referer": f"{BASE_URL}/readbook/{book_id}/1"},
        timeout=30,
    )
    if resp.content[:4] != b'\x89PNG' and resp.content[:2] != b'\xff\xd8':
        raise Exception(f"No access to Book {book_id}. Check your subscription.")


def _make_session(session_cookie):
    s = requests.Session()
    s.cookies.set("ci_session", session_cookie)
    s.headers.update(HEADERS)
    return s


def download_page(args):
    page, book_id, session_cookie, folder = args
    png_path = os.path.join(folder, f"page_{page:04d}.png")
    jpg_path = os.path.join(folder, f"page_{page:04d}.jpg")

    if os.path.exists(png_path):
        return page, "skipped", png_path
    if os.path.exists(jpg_path):
        return page, "skipped", jpg_path

    s = _make_session(session_cookie)
    s.headers.update({"Referer": f"{BASE_URL}/readbook/{book_id}/{page}"})
    url = f"{BASE_URL}/getPage/{book_id}/{page}"

    for attempt in range(3):
        try:
            resp = s.get(url, timeout=30)
            if resp.status_code != 200:
                time.sleep(2)
                continue
            content = resp.content
            text = resp.text.strip()

            if content[:4] == b'\x89PNG':
                with open(png_path, "wb") as f:
                    f.write(content)
                return page, "ok", png_path
            elif content[:2] == b'\xff\xd8':
                with open(jpg_path, "wb") as f:
                    f.write(content)
                return page, "ok", jpg_path
            elif "data:image/png;base64," in text:
                b64 = text.split("data:image/png;base64,", 1)[1]
                b64 = b64.split('"')[0].split("'")[0].split("<")[0].strip()
                with open(png_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return page, "ok", png_path
            elif "data:image/jpeg;base64," in text:
                b64 = text.split("data:image/jpeg;base64,", 1)[1]
                b64 = b64.split('"')[0].split("'")[0].split("<")[0].strip()
                with open(jpg_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return page, "ok", jpg_path
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)

    return page, "failed", None


def download_pages(session_cookie, book_id, start_page, end_page, max_workers, folder, log_fn):
    pages = list(range(start_page, end_page + 1))
    args_list = [(p, book_id, session_cookie, folder) for p in pages]

    ok, skipped, failed = 0, 0, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_page, args): args[0] for args in args_list}
        for future in concurrent.futures.as_completed(futures):
            page, status, path = future.result()
            if status == "ok":
                ok += 1
                log_fn(f"✅ Page {page} downloaded")
            elif status == "skipped":
                skipped += 1
                log_fn(f"⏭️ Page {page} skipped (exists)")
            else:
                failed.append(page)
                log_fn(f"❌ Page {page} FAILED")

    return ok, skipped, failed


def make_pdf(folder, pdf_path, compress, log_fn):
    image_files = sorted([f for f in os.listdir(folder) if f.endswith((".png", ".jpg"))])
    if not image_files:
        raise Exception("No images found for PDF.")
    images = []
    for fname in image_files:
        try:
            img = Image.open(os.path.join(folder, fname)).convert("RGB")
            if compress:
                img = img.resize((1240, 1754), Image.LANCZOS)
            images.append(img)
        except Exception as e:
            log_fn(f"⚠️ Skipping {fname}: {e}")
    if not images:
        raise Exception("No valid images to build PDF.")
    images[0].save(pdf_path, save_all=True, append_images=images[1:])
    size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    log_fn(f"✅ PDF created: {size_mb:.1f} MB")
    return size_mb


def make_epub(folder, epub_path, book_id, start_page, book_title, author, compress, log_fn):
    image_files = sorted([f for f in os.listdir(folder) if f.endswith((".png", ".jpg"))])
    if not image_files:
        raise Exception("No images found for EPUB.")

    book = epub.EpubBook()
    book.set_identifier(f"yct_{book_id}_{start_page}")
    book.set_title(book_title)
    book.set_language("hi")
    book.add_author(author)

    try:
        cover_img = Image.open(os.path.join(folder, image_files[0])).convert("RGB")
        cover_buf = io.BytesIO()
        cover_img.save(cover_buf, format="JPEG", quality=70)
        book.set_cover("cover.jpg", cover_buf.getvalue())
    except Exception as e:
        log_fn(f"⚠️ Cover skipped: {e}")

    css = epub.EpubItem(
        uid="style", file_name="style.css", media_type="text/css",
        content=b"body{margin:0;padding:0;background:#000;} img{width:100%;height:auto;display:block;}"
    )
    book.add_item(css)
    chapters = []

    for i, fname in enumerate(image_files):
        page_num = start_page + i
        try:
            img = Image.open(os.path.join(folder, fname)).convert("RGB")
            if compress:
                img = img.resize((1240, 1754), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=72, optimize=True)

            book.add_item(epub.EpubItem(
                uid=f"img{page_num:04d}",
                file_name=f"img{page_num:04d}.jpg",
                media_type="image/jpeg",
                content=buf.getvalue()
            ))
            html = (
                f"<html><head><link rel='stylesheet' href='style.css'/>"
                f"<title>Page {page_num}</title></head><body>"
                f"<img src='img{page_num:04d}.jpg' alt='Page {page_num}'/></body></html>"
            )
            chap = epub.EpubHtml(
                uid=f"chap{page_num:04d}", title=f"Page {page_num}",
                file_name=f"p{page_num:04d}.xhtml", lang="hi", content=html
            )
            chap.add_item(css)
            book.add_item(chap)
            chapters.append(chap)
        except Exception as e:
            log_fn(f"⚠️ Page {page_num}: {e}")

    book.toc = chapters
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(epub_path, book, {})

    size_mb = os.path.getsize(epub_path) / (1024 * 1024)
    log_fn(f"✅ EPUB created: {size_mb:.1f} MB")
    return size_mb


def send_to_telegram(filepath, caption, tg_token, tg_chat_id, log_fn):
    try:
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > 49:
            log_fn(f"⚠️ {os.path.basename(filepath)} is {size_mb:.1f} MB — too large for Telegram")
            return False
        log_fn(f"📤 Sending {os.path.basename(filepath)} to Telegram ({size_mb:.1f} MB)...")
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendDocument",
                data={"chat_id": tg_chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"document": f},
                timeout=120,
            )
        if resp.status_code == 200:
            log_fn("✅ Sent to Telegram!")
            return True
        else:
            log_fn(f"❌ Telegram error: {resp.text[:100]}")
            return False
    except Exception as e:
        log_fn(f"❌ Telegram send failed: {e}")
        return False
