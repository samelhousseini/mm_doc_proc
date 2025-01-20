import os
import shutil
import pytest
from pathlib import Path

import sys
sys.path.append('./')
sys.path.append('../')
sys.path.append('../../')

from configuration_models import ProcessingPipelineConfiguration
from pdf_ingestion_pipeline import PDFIngestionPipeline  
from data_models import DocumentContent
from utils.file_utils import read_json_file

# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------
@pytest.fixture
def sample_pdf_path(tmp_path):
    """
    Fixture to copy a small test PDF into a temporary directory (tmp_path).
    Returns the path to the test PDF. This fixture ensures we have a
    disposable PDF file to work with.
    """
    # Suppose you store a small test PDF in tests/data/sample.pdf
    # This fixture copies it to the pytest-provided tmp_path.
    test_pdf_dir = Path(__file__).parent / "data"
    source_pdf = test_pdf_dir / "1_London_Brochure.pdf"
    target_pdf = tmp_path / "1_London_Brochure.pdf"
    shutil.copy(str(source_pdf), str(target_pdf))

    return str(target_pdf)


@pytest.fixture
def output_dir(tmp_path):
    """
    Returns a temporary directory that the pipeline can use for output.
    """
    return str(tmp_path / "output")


# ------------------------------------------------------------------------------
# Test: Basic Workflow with Default Config
# ------------------------------------------------------------------------------
def test_pdf_ingestion_basic_workflow(sample_pdf_path, output_dir):
    """
    Test the pipeline with a valid PDF, using default settings.
    Assert that the pipeline completes without error and that key
    output files are generated.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_pages_as_jpg=True,    # test param
        process_text=True,           # test param
        process_images=True,         # test param
        process_tables=True,         # test param
        save_text_files=True,        # post-processing param
        generate_condensed_text=True,# post-processing param
        generate_table_of_contents=True
    )

    pipeline = PDFIngestionPipeline(config)
    document_content = pipeline.process_pdf()

    # Check that DocumentContent is returned
    assert isinstance(document_content, DocumentContent)

    # Check that the main output directory was created
    assert os.path.isdir(output_dir), "Output directory was not created."

    # Check presence of some expected files:
    #   - document_content.json
    #   - text_twin.md
    #   - condensed_text.md
    #   - table_of_contents.md
    document_content_path = Path(output_dir) / "document_content.json"
    text_twin_path = Path(output_dir) / "text_twin.md"
    condensed_text_path = Path(output_dir) / "condensed_text.md"
    toc_path = Path(output_dir) / "table_of_contents.md"

    assert document_content_path.is_file(), "document_content.json not found."
    assert text_twin_path.is_file(), "text_twin.md not found."
    assert condensed_text_path.is_file(), "condensed_text.md not found."
    assert toc_path.is_file(), "table_of_contents.md not found."

    # Check that the pages folder exists
    pages_dir = Path(output_dir) / "pages"
    assert pages_dir.is_dir(), "pages/ subfolder not found."
    
    # Each page folder should exist; check for page_1 or page_X etc.
    page_subdirs = [p for p in pages_dir.iterdir() if p.is_dir() and p.name.startswith("page_")]
    assert len(page_subdirs) > 0, "No page_ subfolders found."

    # Optional: Load JSON and verify its structure
    doc_json = read_json_file(document_content_path)
    assert "metadata" in doc_json, "metadata missing from document_content JSON."
    assert "pages" in doc_json, "pages missing from document_content JSON."


# ------------------------------------------------------------------------------
# Test: Invalid PDF Path
# ------------------------------------------------------------------------------
def test_pdf_ingestion_invalid_pdf_path(output_dir):
    """
    Attempt to run pipeline on an invalid PDF path. 
    Expect a FileNotFoundError (or a custom exception).
    """
    config = ProcessingPipelineConfiguration(
        pdf_path="this_file_does_not_exist.pdf",
        output_directory=output_dir
    )

    with pytest.raises(FileNotFoundError):
        PDFIngestionPipeline(config)


# ------------------------------------------------------------------------------
# Test: Skipping Text Extraction
# ------------------------------------------------------------------------------
def test_skip_text_extraction(sample_pdf_path, output_dir):
    """
    Test pipeline with process_text=False. 
    Verify that no extracted text files are created.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_text=False,
        process_images=True,
        process_tables=True,
        save_text_files=True,  # We'll still check if text twin is created or not
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()


    # With process_text=False, we expect no text processing with LLMs
    assert pipeline.document.pages[0].text.processed_or_raw_text == False, "Processed text even though process_text=False."

# ------------------------------------------------------------------------------
# Test: Skipping Image Extraction
# ------------------------------------------------------------------------------
def test_skip_image_extraction(sample_pdf_path, output_dir):
    """
    Test pipeline with process_images=False.
    Ensure no images subfolders or image text files are generated.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_images=False,
        process_text=True,
        process_tables=True,
        save_text_files=True,
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()

    pages_dir = Path(output_dir) / "pages"
    # Look for subfolders named "images"
    image_dirs = list(pages_dir.glob("**/images"))
    assert len(image_dirs) == 0, "Images folder found but process_images=False was set."


# ------------------------------------------------------------------------------
# Test: Skipping Table Extraction
# ------------------------------------------------------------------------------
def test_skip_table_extraction(sample_pdf_path, output_dir):
    """
    Test pipeline with process_tables=False.
    Ensure no tables subfolders or table text files are generated.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_tables=False,
        process_text=True,
        process_images=True,
        save_text_files=True,
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()

    pages_dir = Path(output_dir) / "pages"
    # Look for subfolders named "tables"
    table_dirs = list(pages_dir.glob("**/tables"))
    assert len(table_dirs) == 0, "Tables folder found but process_tables=False was set."


# ------------------------------------------------------------------------------
# Test: No Post-Processing
# ------------------------------------------------------------------------------
def test_no_post_processing(sample_pdf_path, output_dir):
    """
    Test pipeline with post-processing disabled.
    Check that no doc-level text files (text_twin.md, condensed_text.md, 
    table_of_contents.md) are created.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_text=True,
        process_images=True,
        process_tables=True,
        save_text_files=False,
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()

    # With all post-processing flags off, we expect no text_twin, condensed_text, or TOC
    text_twin = Path(output_dir) / "text_twin.md"
    condensed_text = Path(output_dir) / "condensed_text.md"
    toc_file = Path(output_dir) / "table_of_contents.md"

    assert not text_twin.exists(), "text_twin.md exists even though save_text_files=False."
    assert not condensed_text.exists(), "condensed_text.md exists even though generate_condensed_text=False."
    assert not toc_file.exists(), "table_of_contents.md exists even though generate_table_of_contents=False."


# ------------------------------------------------------------------------------
# Test: Check JSON Structure After Processing
# ------------------------------------------------------------------------------
def test_document_content_json_structure(sample_pdf_path, output_dir):
    """
    After processing, ensure the `document_content.json` has the correct keys
    and that the page data is consistent.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_text=True,
        process_images=True,
        process_tables=True,
        save_text_files=True,
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    document = pipeline.process_pdf()

    doc_json_path = Path(output_dir) / "document_content.json"
    assert doc_json_path.is_file(), "document_content.json was not created."

    doc_data = read_json_file(doc_json_path)

    # Basic checks on top-level keys
    assert "metadata" in doc_data, "metadata key is missing in document_content.json"
    assert "pages" in doc_data, "pages key is missing in document_content.json"

    # Check the metadata
    meta = doc_data["metadata"]
    assert "document_id" in meta, "document_id missing from metadata"
    assert "total_pages" in meta, "total_pages missing from metadata"
    assert meta["total_pages"] == len(doc_data["pages"]), (
        "metadata.total_pages does not match the length of pages array"
    )

    # Check page content structure
    for page in doc_data["pages"]:
        assert "page_number" in page, "page_number missing from page content"
        assert "text" in page, "text missing from page content"
        assert "images" in page, "images missing from page content"
        assert "tables" in page, "tables missing from page content"


# ------------------------------------------------------------------------------
# Test: Output Directory Cleanup Between Runs
# ------------------------------------------------------------------------------
def test_output_directory_cleanup(sample_pdf_path, output_dir):
    """
    Ensure that running the pipeline does not leave behind stale files 
    when re-run with the same output directory. Typically you might want 
    to test if the pipeline either overwrites or warns about existing files.

    If your pipeline does NOT implement cleanup, you may skip or adjust this test.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_text=True,
        process_images=True,
        process_tables=True,
        save_text_files=True,
        generate_condensed_text=True,
        generate_table_of_contents=True
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()

    # Capture the state of output directory
    initial_files = set(Path(output_dir).rglob("*"))

    # Run pipeline again (simulate a second run).
    pipeline2 = PDFIngestionPipeline(config)
    pipeline2.process_pdf()

    # Capture new state
    second_run_files = set(Path(output_dir).rglob("*"))

    # One possible assertion: the sets of files are the same 
    # if the pipeline overwrote files in place without duplication.
    # Adjust this test based on your actual expectations.
    assert initial_files == second_run_files, (
        "Output directory contains different files after re-run. "
        "Check if duplicate or stale files are being left behind."
    )


# ------------------------------------------------------------------------------
# Test: process_pages_as_jpg=False
# ------------------------------------------------------------------------------
def test_process_pages_as_png(sample_pdf_path, output_dir):
    """
    If process_pages_as_jpg=False, ensure that pages are saved as PNG, not JPG.
    """
    config = ProcessingPipelineConfiguration(
        pdf_path=sample_pdf_path,
        output_directory=output_dir,
        process_pages_as_jpg=False,  # explicitly PNG
        process_text=True,
        process_images=False,
        process_tables=False,
        save_text_files=False,
        generate_condensed_text=False,
        generate_table_of_contents=False
    )

    pipeline = PDFIngestionPipeline(config)
    pipeline.process_pdf()

    pages_dir = Path(output_dir) / "pages"
    page_pngs = list(pages_dir.glob("**/*.png"))
    page_jpgs = list(pages_dir.glob("**/*.jpg"))

    assert len(page_pngs) > 0, "No PNG files found despite process_pages_as_jpg=False."
    assert len(page_jpgs) == 0, "Found JPG files even though process_pages_as_jpg=False."
