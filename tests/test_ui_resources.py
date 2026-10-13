import subprocess
from apps.resources import MIME_TYPE, RESOURCES, resource_html
import pytest


def test_resources_are_self_contained_and_read_only():
    for uri in RESOURCES.values():
        html = resource_html(uri)
        assert '<html lang="en">' in html
        assert 'aria-live="polite"' in html
        assert 'ui/initialize' in html
        assert '<script src=' not in html
        assert 'tools/call' not in html
    assert MIME_TYPE == 'text/html;profile=mcp-app'
    with pytest.raises(ValueError):
        resource_html('ui://unknown')


def test_renderer_safety_and_bridge():
    subprocess.run(['node', 'tests/ui_renderer.cjs'], check=True)
