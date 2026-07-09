
import os
import json
import logging
from engine import KnowledgeBase, get_kb
from pathlib import Path

from unittest.mock import MagicMock

# Mock environment if needed
os.environ['HF_TOKEN'] = os.environ.get('HF_TOKEN', 'mock_token')

logging.basicConfig(level=logging.INFO)

def test_kb_logic():
    from engine import KnowledgeBase
    kb_dir = Path("test_kb")
    kb_dir.mkdir(exist_ok=True)

    # Create a dummy file
    test_file = kb_dir / "test.txt"
    test_file.write_text("Physics is the study of matter and energy. ICT is Information and Communication Technology.")

    print(f"--- Initializing KB in {kb_dir} ---")
    # Patch KnowledgeBase to use a mock hf_client
    original_init = KnowledgeBase.__init__
    def mocked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.hf_client = MagicMock()
        # Mock feature_extraction to return dummy embeddings
        self.hf_client.feature_extraction.side_effect = lambda chunks, model: [[0.1]*384 for _ in chunks]

    # Temporarily override __init__ for the test if needed, or just set it after
    # We pass an empty HF_TOKEN to avoid actual API calls before we mock
    os.environ['HF_TOKEN'] = ''
    kb = KnowledgeBase(directory="test_kb")
    kb.hf_client = MagicMock()
    kb.hf_client.feature_extraction.side_effect = lambda chunks, model: [[0.1]*384 for _ in (chunks if isinstance(chunks, list) else [chunks])]

    # Clear processed files to force re-processing with mock
    from database import get_db
    conn = get_db()
    conn.execute("DELETE FROM kb_processed_files")
    conn.commit()
    conn.close()
    kb._processed_files = {}

    # Re-trigger load to use the mock
    kb.load_and_process()

    print(f"Chunks loaded: {len(kb.chunks)}")

    # Check database for metadata
    from database import get_db
    conn = get_db()
    row = conn.execute("SELECT * FROM kb_processed_files WHERE filename = ?", ("test.txt",)).fetchone()
    conn.close()

    if row:
        print(f"Database entry found: {dict(row)}")
        assert row['filename'] == "test.txt"
    else:
        print("Error: kb_processed_files entry not found in database")
        assert False, "Metadata not saved to database"

    # Test Search (Local Fallback if no embeddings)
    print("Testing search (expecting local search if embeddings are None)...")
    results = kb.search("What is Physics?")
    print(f"Search results: {results}")

    # Clean up
    # test_file.unlink()
    # processed_files_path.unlink()
    # kb_dir.rmdir()

if __name__ == "__main__":
    test_kb_logic()
