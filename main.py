import os
import random
import threading
import gc
import time
import urllib.parse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = FastAPI(title="Simplified Image API")

# 👇 新增：配置 CORS 跨域中间件，允许所有来源访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGE_DIR = "/app/images"
image_db = []
reload_timer = None
db_lock = threading.Lock()

app.mount("/i", StaticFiles(directory=IMAGE_DIR), name="images")

# --- 核心加载与监控逻辑保持不变 ---
def load_images():
    global image_db
    new_db = []
    valid_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
        
    for category in os.listdir(IMAGE_DIR):
        cat_path = os.path.join(IMAGE_DIR, category)
        if os.path.isdir(cat_path):
            for filename in os.listdir(cat_path):
                if os.path.splitext(filename)[1].lower() in valid_ext:
                    file_path = os.path.join(cat_path, filename)
                    try:
                        with Image.open(file_path) as img:
                            w, h = img.size
                            orient = "pc" if w >= h else "mobile"
                            new_db.append({"path": file_path, "category": category.lower(), "orientation": orient})
                    except: continue
                    
    with db_lock: image_db = new_db
    print(f"🔄 索引已更新，当前图片总数: {len(image_db)}")
    gc.collect()

def trigger_reload():
    global reload_timer
    if reload_timer is not None: reload_timer.cancel()
    reload_timer = threading.Timer(3.0, load_images)
    reload_timer.start()

class ImageUpdateHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if not event.is_directory and not os.path.basename(event.src_path).startswith('.'):
            trigger_reload()

def start_watcher():
    observer = Observer()
    observer.schedule(ImageUpdateHandler(), IMAGE_DIR, recursive=True)
    observer.start()

@app.on_event("startup")
def startup_event():
    load_images()
    threading.Thread(target=start_watcher, daemon=True).start()

# 👇 核心升级：路由逻辑加入 Request 参数以获取前端真实的域名和协议
def fetch_image(request: Request, cat=None, orient=None):
    with db_lock:
        filtered = image_db
        
    if cat: filtered = [i for i in filtered if i["category"] == cat.lower()]
    if orient: filtered = [i for i in filtered if i["orientation"] == orient.lower()]
    
    if not filtered: raise HTTPException(status_code=404, detail="未找到图片")
        
    selected = random.choice(filtered)
    rel_path = os.path.relpath(selected["path"], IMAGE_DIR)
    safe_path = urllib.parse.quote(rel_path)
    
    # 智能识别协议 (http/https) 和域名 (处理经过 Nginx/Cloudflare 代理的情况)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    
    # 拼接出绝对路径：比如 https://pic.o.hhxin.top/i/anime/1.jpg?t=123456
    absolute_url = f"{scheme}://{host}/i/{safe_path}?t={int(time.time() * 1000)}"
    
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return RedirectResponse(url=absolute_url, status_code=307, headers=headers)

# 👇 注意：所有路由函数都需要加上 request: Request 参数
@app.get("/api/random")
def get_any(request: Request): return fetch_image(request)

@app.get("/api/pc")
def get_all_pc(request: Request): return fetch_image(request, orient="pc")

@app.get("/api/mobile")
def get_all_mobile(request: Request): return fetch_image(request, orient="mobile")

@app.get("/api/{category}")
def get_category_random(request: Request, category: str): return fetch_image(request, cat=category)

@app.get("/api/{category}/{orientation}")
def get_category_with_orient(request: Request, category: str, orientation: str):
    if orientation not in ["pc", "mobile"]: raise HTTPException(status_code=400, detail="方向错误")
    return fetch_image(request, cat=category, orient=orientation)
