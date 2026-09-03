"""长期记忆管理 API：查看/删除自动抽取的用户事实。

抽取与召回是自动的（chat 流程内），这里只暴露管理入口，方便排查
"模型为什么记得这个" 以及删除错误/过期的事实。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.storage.db import list_facts, delete_fact, recall_facts, save_facts

router = APIRouter(tags=["memory"])


@router.get("/memory/facts")
def get_facts(limit: int = 200):
  """列出全部长期记忆事实（时间倒序）。"""
  return {"facts": list_facts(limit=min(max(limit, 1), 500))}


@router.get("/memory/recall")
def recall(query: str, limit: int = 8):
  """调试用：看某问题会召回哪些事实。"""
  if not query.strip():
    raise HTTPException(status_code=400, detail="query is required")
  return {"facts": recall_facts(query, limit=min(max(limit, 1), 20))}


@router.delete("/memory/facts/{fact_id}")
def remove_fact(fact_id: int):
  if not delete_fact(fact_id):
    raise HTTPException(status_code=404, detail="fact not found")
  return {"ok": True}


class AddFactRequest(BaseModel):
  content: str
  session_id: Optional[str] = None


class EditFactRequest(BaseModel):
  content: str


@router.post("/memory/facts")
def add_fact(body: AddFactRequest):
  """Manually pin a fact into long-term memory.

  Deduped against existing facts by simple substring match so the user
  can keep typing without creating near-duplicate rows.
  """
  content = (body.content or "").strip()
  if not content:
    raise HTTPException(status_code=400, detail="content is required")
  if len(content) > 500:
    raise HTTPException(status_code=400, detail="content too long (max 500 chars)")
  existing = [f.get("content", "") for f in list_facts(limit=500)]
  norm = content.lower().strip()
  for e in existing:
    if e and (e.lower().strip() == norm or norm in e.lower() or e.lower() in norm):
      raise HTTPException(status_code=409, detail="fact already exists or is near-duplicate")
  inserted = save_facts([content], session_id=body.session_id)
  if not inserted:
    raise HTTPException(status_code=500, detail="insert failed")
  return {"ok": True, "inserted": inserted, "content": content}


@router.put("/memory/facts/{fact_id}")
def update_fact(fact_id: int, body: EditFactRequest):
  """Edit an existing fact (typo fix, re-phrasing)."""
  content = (body.content or "").strip()
  if not content:
    raise HTTPException(status_code=400, detail="content is required")
  from app.storage.db import update_fact as _update_fact
  ok = _update_fact(fact_id, content)
  if not ok:
    raise HTTPException(status_code=404, detail="fact not found")
  return {"ok": True, "fact_id": fact_id, "content": content}

