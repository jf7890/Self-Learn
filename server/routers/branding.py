"""Public branding assets and admin branding management."""
import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from auth import require_admin
from db import get_conn, get_setting, set_setting
from schemas import BrandingUpdate
router=APIRouter()
BRANDING_DIR=os.path.join(os.path.dirname(os.environ.get("ULEARN_DB","/data/ulearn.db")),"branding")
ALLOWED_LOGO_TYPES={"image/png":"png","image/jpeg":"jpg","image/svg+xml":"svg","image/webp":"webp"}
ALLOWED_FAVICON_TYPES={"image/png":"png","image/svg+xml":"svg","image/webp":"webp","image/x-icon":"ico","image/vnd.microsoft.icon":"ico"}
MAX_BYTES=2*1024*1024

def asset_path(kind,ext): return os.path.join(BRANDING_DIR,f"{kind}.{ext}")
async def save_asset(kind,file,allowed,key):
    if file.content_type not in allowed: raise HTTPException(400,detail=f"{kind.capitalize()} must be one of: {', '.join(sorted(set(allowed.values())))}")
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES: raise HTTPException(400,detail=f"{kind.capitalize()} must be under 2MB")
    os.makedirs(BRANDING_DIR,exist_ok=True)
    with get_conn() as conn: old=get_setting(conn,key) or ""
    if old and os.path.isfile(asset_path(kind,old)): os.remove(asset_path(kind,old))
    ext=allowed[file.content_type]
    with open(asset_path(kind,ext),"wb") as output: output.write(content)
    with get_conn() as conn: set_setting(conn,key,ext)
def delete_asset(kind,key):
    with get_conn() as conn:
        old=get_setting(conn,key) or ""
        if old and os.path.isfile(asset_path(kind,old)): os.remove(asset_path(kind,old))
        set_setting(conn,key,"")
@router.get("/branding")
def get_branding():
    with get_conn() as conn:
        name=get_setting(conn,"site_name") or "uLearn"; color=get_setting(conn,"accent_color") or "#e8a33d"; logo=get_setting(conn,"logo_ext") or ""; favicon=get_setting(conn,"favicon_ext") or ""
    return {"site_name":name,"accent_color":color,"logo_url":"/branding/logo" if logo else None,"favicon_url":"/branding/favicon" if favicon else None}
def response_asset(kind,key,allowed):
    with get_conn() as conn: ext=get_setting(conn,key) or ""
    if not ext: raise HTTPException(404,detail=f"No {kind} uploaded")
    path=asset_path(kind,ext)
    if not os.path.isfile(path): raise HTTPException(404,detail=f"{kind.capitalize()} file missing on disk")
    return FileResponse(path,media_type={v:k for k,v in allowed.items()}.get(ext,"application/octet-stream"))
@router.get("/branding/logo")
def logo(): return response_asset("logo","logo_ext",ALLOWED_LOGO_TYPES)
@router.get("/branding/favicon")
def favicon(): return response_asset("favicon","favicon_ext",ALLOWED_FAVICON_TYPES)
@router.put("/admin/branding")
def update(body:BrandingUpdate,current=Depends(require_admin)):
    name=body.site_name.strip() or "uLearn"; color=body.accent_color.strip()
    if not __import__('re').fullmatch(r"#[0-9a-fA-F]{6}",color): raise HTTPException(400,detail="Accent color must be a hex value like #e8a33d")
    with get_conn() as conn: set_setting(conn,"site_name",name); set_setting(conn,"accent_color",color)
    return {"ok":True}
@router.post("/admin/branding/logo")
async def upload_logo(file:UploadFile=File(...),current=Depends(require_admin)): await save_asset("logo",file,ALLOWED_LOGO_TYPES,"logo_ext"); return {"ok":True}
@router.delete("/admin/branding/logo")
def delete_logo(current=Depends(require_admin)): delete_asset("logo","logo_ext"); return {"ok":True}
@router.post("/admin/branding/favicon")
async def upload_favicon(file:UploadFile=File(...),current=Depends(require_admin)): await save_asset("favicon",file,ALLOWED_FAVICON_TYPES,"favicon_ext"); return {"ok":True}
@router.delete("/admin/branding/favicon")
def delete_favicon(current=Depends(require_admin)): delete_asset("favicon","favicon_ext"); return {"ok":True}
