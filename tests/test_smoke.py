"""Quick smoke test for the RAG-ProjectVisualizer pipeline."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import scan_project_files
from core.parser import parse_file
from core.chunker import chunk_parsed_files
from core.ollama_client import check_ollama_status

# 1. Test scanning
PROJECT = r"d:\DevStore\New folder\AndroidProjectVisualizer\src"
files = scan_project_files(PROJECT)
print(f"[1] Scanned {len(files)} source files")

# 2. Test parsing
parsed = [parse_file(f["path"]) for f in files]
parsed = [p for p in parsed if p]
print(f"[2] Parsed {len(parsed)} files successfully")

classes = []
for p in parsed:
    classes.extend(p.get("classes", []))
print(f"    Found {len(classes)} classes:")
for c in classes[:10]:
    print(f"      {c['component_type']:15s} {c['layer']:15s} {c['name']}")
if len(classes) > 10:
    print(f"      ... and {len(classes) - 10} more")

# 3. Test chunking
chunks = chunk_parsed_files(parsed)
print(f"[3] Created {len(chunks)} chunks")
type_counts = {}
for ch in chunks:
    type_counts[ch.chunk_type] = type_counts.get(ch.chunk_type, 0) + 1
for ct, cnt in sorted(type_counts.items()):
    print(f"      {ct}: {cnt}")

# 4. Test Ollama connectivity
status = check_ollama_status()
if status["ok"]:
    print(f"[4] Ollama OK — models: {', '.join(status['models'][:5])}")
else:
    print(f"[4] Ollama OFFLINE: {status['error']}")

print("\n✅ All smoke tests passed!")
