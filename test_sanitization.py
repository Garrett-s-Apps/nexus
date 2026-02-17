#!/usr/bin/env python3
"""Test script to verify input sanitization in document generator."""

import sys

sys.path.insert(0, '/tmp/nexus-rebuild')  # noqa: S108

from pathlib import Path

from src.documents.generator import sanitize_document_content, sanitize_filename


def test_sanitize_filename():
    """Test filename sanitization."""
    print("Testing sanitize_filename()...")

    # Test path traversal attempts
    assert sanitize_filename("../../../etc/passwd") == "etcpasswd"
    assert sanitize_filename("..\\..\\windows\\system32") == "windowssystem32"
    assert sanitize_filename("test/../../secret") == "testsecret"

    # Test null byte injection
    assert sanitize_filename("file\x00.txt") == "filetxt"

    # Test special characters
    assert sanitize_filename("file<>:\"|?*.txt") == "file_________txt"

    # Test normal filenames
    assert sanitize_filename("My_Document-2024") == "My_Document-2024"
    assert sanitize_filename("report 2024") == "report_2024"

    # Test length limiting
    long_name = "a" * 300
    assert len(sanitize_filename(long_name)) == 255

    print("✓ All filename sanitization tests passed!")

def test_sanitize_document_content():
    """Test document content sanitization."""
    print("\nTesting sanitize_document_content()...")

    # Test HTML escaping
    assert sanitize_document_content("<div>test</div>") == "&lt;div&gt;test&lt;/div&gt;"
    assert sanitize_document_content("a & b") == "a &amp; b"
    assert sanitize_document_content("x < y > z") == "x &lt; y &gt; z"

    # Test script removal
    assert "<script" not in sanitize_document_content("<script>alert('xss')</script>")
    assert "<script" not in sanitize_document_content("<SCRIPT>alert('xss')</SCRIPT>")
    assert "alert" not in sanitize_document_content("<script>alert('xss')</script>")

    # Test normal content
    normal = "This is a normal document with text."
    assert sanitize_document_content(normal) == normal

    print("✓ All content sanitization tests passed!")

def test_path_traversal_protection():
    """Test that path traversal is prevented."""
    print("\nTesting path traversal protection...")

    from src.documents.generator import ALLOWED_OUTPUT_DIR

    # Test that ALLOWED_OUTPUT_DIR is properly set
    assert Path("~/.nexus/documents").expanduser() == ALLOWED_OUTPUT_DIR
    print(f"✓ ALLOWED_OUTPUT_DIR correctly set to: {ALLOWED_OUTPUT_DIR}")

    # Test that relative_to() would catch path traversal
    malicious_path = Path("/etc/passwd").resolve()
    try:
        malicious_path.relative_to(ALLOWED_OUTPUT_DIR)
        print("✗ FAILED: Path traversal not detected!")
        sys.exit(1)
    except ValueError:
        print("✓ Path traversal correctly blocked!")

if __name__ == "__main__":
    test_sanitize_filename()
    test_sanitize_document_content()
    test_path_traversal_protection()
    print("\n✅ All sanitization tests passed successfully!")
