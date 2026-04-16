import os
import random
import threading
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = FastAPI(title="Simplified Image API")

IMAGE_DIR = "/app/images"
image_db = []

# 1. 核心加载逻辑
def load_images():
    global image_db
    new_db = []
    valid_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    if not os.path.exists(IMAGE_DIR):
        os.makedirs(IMAGE_DIR)
        
    for category in os.listdir(IMAGE_DIR):
        cat_path = os.path.join(IMAGE_DIR, category)
        if os.path.isdir(cat_path):
            for filename in os.listdir(cat_path):
                if os.path.splitext(filename)[1].lower() in valid_ext:
                    file_path = os.path.join(cat_path, filename)
                    try:
                        with Image.open(file_path) as img:
                            w, h = img.size
                            # 映射语义：横屏->pc, 竖屏->mobile
                            orient = "pc" if w >= h else "mobile"
                            new_db.append({
                                "path": file_path,
                                "category": category.lower(),
                                "orientation": orient
                            })
                    except: continue
    image_db = new_db
    print(f"🔄 索引已更新，当前图片总数: {len(image_db)}")

# 2. 文件监控逻辑
class ImageUpdateHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if not event.is_directory:
            # 简单防抖：避免大批量上传时频繁刷新
            load_images()

def start_watcher():
    observer = Observer()
    observer.schedule(ImageUpdateHandler(), IMAGE_DIR, recursive=True)
    observer.start()

@app.on_event("startup")
def startup_event():
    load_images()
    # 开启后台线程监控文件
    threading.Thread(target=start_watcher, daemon=True).start()

# 3. 简化后的路由逻辑
def fetch_image(cat=None, orient=None):
    filtered = image_db
    if cat:
        filtered = [i for i in filtered if i["category"] == cat.lower()]
    if orient:
        filtered = [i for i in filtered if i["orientation"] == orient.lower()]
    
    if not filtered:
        raise HTTPException(status_code=404, detail="未找到图片")
    return FileResponse(random.choice(filtered)["path"])

@app.get("/api/random")
def get_any():
    return fetch_image()

@app.get("/api/pc")
def get_all_pc():
    return fetch_image(orient="pc")

@app.get("/api/mobile")
def get_all_mobile():
    return fetch_image(orient="mobile")

@app.get("/api/{category}")
def get_category_random(category: str):
    # 处理特殊路由：如果用户输入 /api/pc 或 /api/mobile 会被上面的路由拦截
    # 这里的 category 将匹配文件夹名
    return fetch_image(cat=category)

@app.get("/api/{category}/{orientation}")
def get_category_with_orient(category: str, orientation: str):
    # 支持 /api/anime/pc 或 /api/dota2/mobile
    if orientation not in ["pc", "mobile"]:
        raise HTTPException(status_code=400, detail="方向参数错误，仅限 pc 或 mobile")
    return fetch_image(cat=category, orient=orientation)