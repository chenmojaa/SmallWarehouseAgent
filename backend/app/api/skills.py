"""Local skill package registry with folder/archive installs and GitHub imports."""
from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import urlopen

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings

router = APIRouter(prefix="/skills", tags=["skills"])

_REGISTRY_LOCK = threading.Lock()
_MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
_MAX_ENTRY_BYTES = 80 * 1024 * 1024
_MAX_ENTRIES = 8000

RECOMMENDED = [
    {
        "id": "docx",
        "name": "Word 文档专家",
        "description": "创建、编辑和批处理 .docx 文件，适合报告、合同与文档自动化。",
        "category": "documents",
        "emoji": "📄",
        "badge": "文档",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/docx",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/docx",
    },
    {
        "id": "xlsx",
        "name": "表格数据助手",
        "description": "读取、清洗和分析 Excel 工作簿，可生成公式与多表汇总。",
        "category": "data",
        "emoji": "📊",
        "badge": "数据",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/xlsx",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/xlsx",
    },
    {
        "id": "pdf",
        "name": "PDF 处理工具箱",
        "description": "提取文本与表格、合并拆分页面，并支持常规 PDF 生成任务。",
        "category": "documents",
        "emoji": "🧾",
        "badge": "实用",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/pdf",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/pdf",
    },
    {
        "id": "webapp-testing",
        "name": "Web 应用测试",
        "description": "用浏览器自动化检查页面流程、控制台错误和交互回归。",
        "category": "engineering",
        "emoji": "🧪",
        "badge": "质量",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/webapp-testing",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/webapp-testing",
    },
    {
        "id": "frontend-design",
        "name": "前端设计审查",
        "description": "优化界面层级、设计系统一致性和可访问的前端视觉实现。",
        "category": "design",
        "emoji": "🎨",
        "badge": "设计",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/frontend-design",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/frontend-design",
    },
    {
        "id": "skill-creator",
        "name": "技能创建器",
        "description": "按 Agent Skills 规范编写结构清晰、可维护的新技能包。",
        "category": "agent",
        "emoji": "🛠️",
        "badge": "推荐",
        "source_url": "https://github.com/anthropics/skills/tree/main/skills/skill-creator",
        "archive_url": "https://codeload.github.com/anthropics/skills/zip/refs/heads/main",
        "source_dir": "skills-main/skills/skill-creator",
    },
]


def _root() -> Path:
    return Path(settings.data_dir) / "skills"


def _registry_path() -> Path:
    return _root() / "installed.json"


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
    temporary.replace(path)


def _load_installed() -> list[dict]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_installed(items: list[dict]) -> None:
    _atomic_write(_registry_path(), {"items": items})


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "skill"


def _manifest(directory: Path) -> dict[str, str]:
    manifest_path = directory / "SKILL.md"
    if not manifest_path.exists():
        raise ValueError("技能包缺少 SKILL.md")
    text = manifest_path.read_text(encoding="utf-8-sig", errors="replace")
    result: dict[str, str] = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            item = line.split(":", 1)
            if len(item) == 2:
                result[item[0].strip().lower()] = item[1].strip().strip('"').strip("'")
    if not result.get("name"):
        heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        result["name"] = heading.group(1).strip() if heading else directory.name
    result.setdefault("description", "")
    return result


def _tree_stats(directory: Path) -> tuple[int, int]:
    files = [item for item in directory.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def _register_directory(source: Path, source_label: str, source_type: str,
                        source_url: str = "", commit: bool = True) -> dict:
    metadata = _manifest(source)
    installed_id = _slug(metadata.get("name") or source.name)
    destination = _root() / "installed" / installed_id
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    file_count, size_bytes = _tree_stats(destination)
    record = {
        "id": installed_id,
        "name": metadata.get("name") or installed_id,
        "description": metadata.get("description", ""),
        "emoji": "",
        "category": "custom",
        "file_count": file_count,
        "size_bytes": size_bytes,
        "path": str(destination),
        "source_type": source_type,
        "source_label": source_label,
        "source_url": source_url,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not commit:
        return record
    with _REGISTRY_LOCK:
        items = [item for item in _load_installed() if item["id"] != installed_id]
        items.insert(0, record)
        _save_installed(items)
    return record


def _safe_member(name: str) -> bool:
    PurePosixPath(name)
    windows_name = name.replace("\\", "/")
    if windows_name.startswith("/") or ":" in windows_name:
        return False
    parts = [part for part in windows_name.split("/") if part not in ("", ".")]
    return ".." not in parts


def _extract_zip(data: bytes, destination: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ENTRIES:
            raise ValueError("压缩包文件数量超出限制")
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            if not _safe_member(info.filename):
                raise ValueError(f"压缩包包含不安全路径：{info.filename}")
            if info.file_size > _MAX_ENTRY_BYTES:
                raise ValueError("压缩包内单个文件过大")
            total += info.file_size
            if total > _MAX_ARCHIVE_BYTES:
                raise ValueError("压缩包解压后总大小超出限制")
            target = destination / Path(info.filename.replace("\\", "/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as incoming, open(target, "wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)


def _extract_tar(data: bytes, destination: Path) -> None:
    count = 0
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for member in archive:
            if not member.isfile() and not member.isdir():
                raise ValueError("压缩包包含链接或特殊文件，已拒绝安装")
            if not _safe_member(member.name):
                raise ValueError(f"压缩包包含不安全路径：{member.name}")
            count += int(member.isfile())
            total += max(0, member.size)
            if count > _MAX_ENTRIES or total > _MAX_ARCHIVE_BYTES:
                raise ValueError("压缩包大小或文件数量超出限制")
            if member.isdir():
                (destination / Path(member.name)).mkdir(parents=True, exist_ok=True)
                continue
            target = destination / Path(member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            with extracted, open(target, "wb") as output:
                shutil.copyfileobj(extracted, output)


def _find_skill_roots(base: Path) -> list[Path]:
    matches = sorted(
        base.rglob("SKILL.md"),
        key=lambda path: (len(path.parts), str(path).lower()),
    )
    roots: list[Path] = []
    seen: set[Path] = set()
    for manifest in matches:
        root = manifest.parent.resolve()
        if root not in seen and base.resolve() in root.parents:
            roots.append(root)
            seen.add(root)
    return roots


@router.get("/recommended")
def recommended_skills():
    installed_ids = {item["id"] for item in _load_installed()}
    items = [{**item, "installed": item["id"] in installed_ids} for item in RECOMMENDED]
    return {"items": items}


@router.get("")
def list_skills():
    return {"items": sorted(_load_installed(), key=lambda item: item["installed_at"], reverse=True)}


@router.post("/upload")
async def upload_skill(files: list[UploadFile] = File(...), source_name: str = "uploaded-skill"):
    if not files:
        raise HTTPException(status_code=400, detail="请选择技能文件夹或压缩包")
    staging = Path(tempfile.mkdtemp(prefix="hd-skills-"))
    try:
        archives = [item for item in files if Path(item.filename or "").suffix.lower() in {".zip", ".tgz"} or (item.filename or "").lower().endswith((".tar.gz", ".tar"))]
        folders = [item for item in files if item not in archives]
        if len(archives) > 1:
            raise HTTPException(status_code=400, detail="一次只能导入一个压缩包")
        if archives:
            payload = await archives[0].read()
            if len(payload) > _MAX_ARCHIVE_BYTES:
                raise HTTPException(status_code=413, detail="压缩包超过 100 MB 限制")
            extraction = staging / "archive"
            extraction.mkdir()
            filename = (archives[0].filename or "").lower()
            if filename.endswith(".zip"):
                _extract_zip(payload, extraction)
            elif filename.endswith((".tar.gz", ".tgz", ".tar")):
                _extract_tar(payload, extraction)
            else:
                raise HTTPException(status_code=400, detail="仅支持 ZIP、TAR 和 TAR.GZ")
            candidates = _find_skill_roots(extraction)
            if not candidates:
                raise HTTPException(status_code=400, detail="压缩包中未找到 SKILL.md")
            records = [_register_directory(item, archives[0].filename or "archive.zip", "archive") for item in candidates[:20]]
        elif folders:
            for upload in folders:
                relative = (upload.filename or "").replace("\\", "/").strip("/")
                if not relative or not _safe_member(relative):
                    raise HTTPException(status_code=400, detail=f"无效的文件夹路径：{upload.filename}")
                target = staging / "folder" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "wb") as output:
                    shutil.copyfileobj(upload.file, output)
            tree = staging / "folder"
            candidates = _find_skill_roots(tree)
            if not candidates:
                raise HTTPException(status_code=400, detail="所选内容中未找到 SKILL.md")
            root_name = candidates[0].name
            display_source = source_name or root_name
            records = [_register_directory(item, display_source, "folder") for item in candidates[:20]]
        else:
            raise HTTPException(status_code=400, detail="请选择包含 SKILL.md 的文件夹或压缩包")
        return {"items": records}
    except (zipfile.BadZipFile, tarfile.TarError, ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@router.post("/install/{skill_id}")
def install_recommended(skill_id: str):
    catalog = next((item for item in RECOMMENDED if item["id"] == skill_id), None)
    if catalog is None:
        raise HTTPException(status_code=404, detail="推荐技能不存在")
    request = urlopen(catalog["archive_url"], timeout=45)
    try:
        payload = request.read()
    finally:
        request.close()
    if len(payload) > _MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="远程技能包超过大小限制")
    staging = Path(tempfile.mkdtemp(prefix="hd-github-"))
    try:
        extraction = staging / "remote"
        extraction.mkdir()
        _extract_zip(payload, extraction)
        candidate = extraction / catalog["source_dir"]
        if not candidate.exists():
            raise HTTPException(status_code=502, detail="远程归档中未找到指定技能目录")
        record = _register_directory(candidate, f"GitHub · {catalog['id']}", "github", catalog["source_url"])
        return record
    except (zipfile.BadZipFile, OSError) as error:
        raise HTTPException(status_code=502, detail=f"下载或解压失败：{error}") from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@router.delete("/{skill_id}")
def remove_skill(skill_id: str):
    with _REGISTRY_LOCK:
        items = _load_installed()
        remaining = [item for item in items if item["id"] != skill_id]
        if len(remaining) == len(items):
            raise HTTPException(status_code=404, detail="技能不存在")
        target = _root() / "installed" / skill_id
        resolved_target = target.resolve()
        allowed_root = (_root() / "installed").resolve()
        if allowed_root in resolved_target.parents:
            shutil.rmtree(resolved_target, ignore_errors=True)
        _save_installed(remaining)
    return {"ok": True}
