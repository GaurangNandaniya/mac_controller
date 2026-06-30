from flask import Blueprint, jsonify, request, send_file
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from ..utils import setup_logger
from src.utils.auth_manager import auth_manager

logger = setup_logger()

files_bp = Blueprint('files', __name__)
files_bp.before_request(auth_manager.auth_middleware())

# Shared transfer folder — phone uploads land here, and anything here is
# downloadable from the phone.
_FILES_BASE = os.path.realpath(os.path.expanduser("~/Desktop/MacController"))


def _ensure_base():
    os.makedirs(_FILES_BASE, exist_ok=True)


def _safe_path(name):
    """Resolve a filename inside the shared folder, or None if it escapes it."""
    name = os.path.basename(name or "")
    if not name:
        return None
    target = os.path.realpath(os.path.join(_FILES_BASE, name))
    if target == _FILES_BASE or not target.startswith(_FILES_BASE + os.sep):
        return None
    return target


@files_bp.route('/upload', methods=['POST'])
def upload():
    """Phone → Mac. Multipart form with a 'file' field."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "error": "No file provided"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"status": "error", "error": "Empty filename"}), 400

    _ensure_base()
    name = secure_filename(f.filename) or f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target = _safe_path(name)
    if not target:
        return jsonify({"status": "error", "error": "Invalid filename"}), 400

    # Don't clobber an existing file — suffix with a time stamp.
    if os.path.exists(target):
        base, ext = os.path.splitext(name)
        name = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
        target = _safe_path(name)

    f.save(target)
    logger.info(f"File uploaded: {name}")
    return jsonify({"status": "success", "name": name})


@files_bp.route('/list', methods=['POST'])
def list_files():
    """List files in the shared folder (newest first)."""
    _ensure_base()
    files = []
    for name in os.listdir(_FILES_BASE):
        p = os.path.join(_FILES_BASE, name)
        if os.path.isfile(p):
            st = os.stat(p)
            files.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"status": "success", "files": files})


@files_bp.route('/download', methods=['GET'])
def download():
    """Mac → Phone. Query: name, token (so a link/download can authenticate)."""
    target = _safe_path(request.args.get("name", ""))
    if not target or not os.path.isfile(target):
        return jsonify({"status": "error", "error": "not found"}), 404
    return send_file(target, as_attachment=True)


@files_bp.route('/delete', methods=['POST'])
def delete():
    """Remove a file from the shared folder. Body: {"name": "..."}."""
    target = _safe_path((request.get_json(silent=True) or {}).get("name", ""))
    if not target or not os.path.isfile(target):
        return jsonify({"status": "error", "error": "not found"}), 404
    os.remove(target)
    logger.info("File deleted from shared folder")
    return jsonify({"status": "success"})
