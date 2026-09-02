"""Search API."""
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field
from app.storage.hybrid import hybrid_search_with_expansion

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="检索关键词或问题")
    top_k: int = Field(5, ge=1, le=20)
    base_url: str | None = Field(None, description="自定义 embedding 节点 URL")
    source_type: str | None = Field(None, description="按来源过滤：uploaded | feishu | url")
    tag: str | None = Field(None, description="按标签过滤（精确匹配一个 tag）")
    date_from: str | None = Field(None, description="起始日期 ISO 8601")
    date_to: str | None = Field(None, description="结束日期 ISO 8601")
    rerank: bool = Field(False, description="是否用 LLM 对 top 结果重排序")
    expand: bool = Field(False, description="是否先用 LLM 改写 query 再检索")


@router.post("/search")
async def search(
    body: SearchRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_embedding_base_url: str | None = Header(None, alias="X-Embedding-Base-URL"),
):
    if not body.query.strip():
        raise HTTPException(400, "query 不能为空")
    base_url = (body.base_url or x_embedding_base_url or "").strip() or None
    hits = hybrid_search_with_expansion(
        body.query, top_k=body.top_k, api_key=x_api_key, base_url=base_url,
        source_type=body.source_type, tag=body.tag,
        date_from=body.date_from, date_to=body.date_to,
        rerank=body.rerank, expand=body.expand,
    )
    return {"query": body.query, "count": len(hits), "results": hits}
