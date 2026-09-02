"""长期记忆管理 API：查看/删除自动抽取的用户事实。

抽取与召回是自动的（chat 流程内），这里只暴露管理入口，方便排查
"模型为什么记得这个" 以及删除错误/过期的事实。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.storage.db import list_facts, delete_fact, recall_facts

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
