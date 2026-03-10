import streamlit.components.v1 as components
import base64
from pathlib import Path

def _get_downloads_folder() -> Path:
    """Get the user's Downloads folder path."""
    return Path.home() / "Downloads"

def _save_file(data, filename: str) -> str:
    """Save file to Downloads folder. Returns the full path."""
    downloads = _get_downloads_folder()
    downloads.mkdir(exist_ok=True)
    filepath = downloads / filename
    if isinstance(data, str):
        filepath.write_text(data, encoding="utf-8")
    else:
        filepath.write_bytes(data)
    return str(filepath)

def _js_download(data, filename: str, mime: str):
    """Trigger a browser download with correct filename via JavaScript."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    b64 = base64.b64encode(data).decode()
    js = f"""
    <script>
    const link = document.createElement('a');
    link.href = 'data:{mime};base64,{b64}';
    link.download = '{filename}';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    </script>
    """
    components.html(js, height=0)
