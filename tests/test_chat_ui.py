"""Focused frontend behavior tests, independent of model credentials."""
import subprocess
from pathlib import Path


def test_chat_session_retry_and_card_bridge():
    subprocess.run(['node', 'tests/chat_ui.cjs'], check=True)


def test_chat_assets_contain_no_credential_persistence():
    script = Path('apps/chat.js').read_text()
    assert 'localStorage' not in script and 'sessionStorage' not in script
    assert 'innerHTML' not in script
    html = Path('apps/chat.html').read_text()
    assert 'login-token' not in html
    assert 'JSON.stringify({password})' in script
    assert 'JSON.stringify({token})' not in script
    assert "setAttribute('sandbox', 'allow-scripts')" in script
