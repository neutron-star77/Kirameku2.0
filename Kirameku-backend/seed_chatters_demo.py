"""临时演示用：向 kirameku 数据库直插 3 条 published 说说（可安全重复运行）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlmodel import Session, select

from app.database import engine
from app.models import Chatter

demo = [
    {"content": "今天把前端接上了真实数据接口，说说终于不是写死的了！", "mood": "开心"},
    {"content": "学习进度存进档案，下次打开接着学。", "mood": "记录"},
    {"content": "熬夜写代码第 3 天，肝完这页就睡……", "mood": "困"},
]

with Session(engine) as session:
    existing = set(session.exec(select(Chatter.content)).all())
    inserted = 0
    for d in demo:
        if d["content"] in existing:
            continue
        session.add(Chatter(content=d["content"], mood=d["mood"], status="published"))
        inserted += 1
    session.commit()
    total = len(session.exec(select(Chatter).where(Chatter.status == "published")).all())
    print(f"新插入 {inserted} 条；当前 published 说说共 {total} 条")