# PDF Ingestion Pipeline

This repository contains a pipeline that utilizes multimodal Large Language Models (LLMs) to process PDF documents. It enables you to:
- Convert PDF pages to images (PNG or JPG).
- Extract text, images, and tables from each page.
- Generate consolidated text, condensed summaries, and table of contents.
- Save all extracted content (including text files, JSON metadata, and optional Markdown summaries) in an organized folder structure.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Output Structure](#output-structure)
7. [Model Information](#model-information)
8. [Contributing](#contributing)
9. [License](#license)

---

## Overview

The **PDF Ingestion Pipeline** reads a PDF file page by page, leverages multimodal LLMs to handle both text and images, and produces structured outputs for easy downstream consumption. You can enable or disable each component of the pipeline, depending on your needs—such as extracting only text, extracting images and tables, or generating additional processed outputs like condensed text and table of contents.

---

## Features

- **Page-by-Page Rendering**: Converts each PDF page to an image (JPG or PNG) for potential image-based analysis.
- **Text Extraction**: Uses a text-based LLM to process or refine extracted text.
- **Multimodal Image Analysis**: Uses a multimodal LLM to describe embedded photos or graphs.
- **Table Extraction**: Identifies tables in PDF pages and returns them as Markdown.
- **Optional Post-Processing**: 
  - Generates a single combined text file (`text_twin.md`) of the entire PDF.
  - Creates a condensed version of the text if requested.
  - Creates a table of contents if requested.
- **Structured JSON Output**: All data is summarized in a JSON file, allowing you to load and inspect document content programmatically later on.

---

## Installation

1. **Clone the Repository**: 
   ```bash
   git clone https://github.com/samelhousseini/pdf-ingestion-pipeline.git
   ```
2. **Install Dependencies**:  
   ```bash
   cd pdf-ingestion-pipeline
   pip install -r requirements.txt
   ```
   Make sure you have the required Python libraries (e.g., `pydantic`, `fitz`/`PyMuPDF`, `Pillow`, etc.).

3. **LLM Credentials**:
   - If you use Azure or OpenAI endpoints, ensure you set the appropriate environment variables (e.g., `OPENAI_API_KEY`) or supply the `endpoint` and `key` within the model configurations.

---

## Configuration

The pipeline uses a `ProcessingPipelineConfiguration` class to tailor the behavior. You can enable or disable features using boolean flags, and you can specify which models to use for text or multimodal processing.

Key flags and attributes include:
- `pdf_path`: Path to your PDF file (required).
- `output_directory`: Folder where all processed files will be placed (optional; defaults to a new folder).
- `process_pages_as_jpg`: Convert pages to JPG (`True`) or PNG (`False`).
- `process_text`: Extract and process text with an LLM if `True`.
- `process_images`: Detect and describe images (graphs or photos) with a multimodal model if `True`.
- `process_tables`: Extract tables from pages if `True`.
- `save_text_files`: Generate doc-level `.md` files containing extracted or combined text.
- `generate_condensed_text`: Produce a condensed version of the entire text content.
- `generate_table_of_contents`: Generate a table of contents in Markdown.

---

## Usage

Below is a minimal usage example showing how to set up and run the pipeline. This snippet assumes you have already imported the pipeline class (`PDFIngestionPipeline`) and the configuration class (`ProcessingPipelineConfiguration`).

```python
from your_project.configuration_models import ProcessingPipelineConfiguration
from your_project.pipeline import PDFIngestionPipeline
from your_project.utils.openai_data_models import (
    MulitmodalProcessingModelInfo, 
    TextProcessingModelnfo
)

# 1) Create a configuration
config = ProcessingPipelineConfiguration(
    pdf_path="sample_data/my_document.pdf",
    output_directory="my_pipeline_output",
    process_pages_as_jpg=True,
    process_text=True,
    process_images=True,
    process_tables=True,
    save_text_files=True,
    generate_condensed_text=True,
    generate_table_of_contents=True
)

# 2) (Optional) Specify the LLM models for text and multimodal analysis. 
config.multimodal_model = MulitmodalProcessingModelInfo(
    provider="azure",
    model_name="gpt-4o",
    reasoning_efforts="medium",
    endpoint="https://your-azure-endpoint", # this will be picked up from .env file once you specify the model name
    key="YOUR_AZURE_KEY",                   # this will be picked up from .env file once you specify the model name
    model="deployment-name"
)
config.text_model = TextProcessingModelnfo(
    provider="azure",
    model_name="gpt-4o",        
    reasoning_efforts="medium",
    endpoint="https://your-azure-endpoint", # this will be picked up from .env file once you specify the model name
    key="YOUR_AZURE_KEY",                   # this will be picked up from .env file once you specify the model name
    model="deployment-name"
)

# 3) Initialize and run the pipeline
pipeline = PDFIngestionPipeline(config)
document_content = pipeline.process_pdf()

# 'document_content' now holds structured data about the PDF.
# You can also explore the output folder to see the generated files.
```

---

## Output Structure

When the pipeline completes, the specified output directory will contain the following:

- **`pages/`**: A subfolder for each page, containing:
  - A rendered image of the page in PNG/JPG form.
  - Extracted text (`.txt`) if `process_text=True`.
  - An optional `images/` folder if any embedded images are detected, each described in a `.txt` file.
  - An optional `tables/` folder if any tables are detected, each described in a `.txt` file.
  - A combined `_twin.txt` file that merges text, image descriptions, and table content for that page.
- **`text_twin.md`**: A combined text file of all pages (if `save_text_files=True`).
- **`condensed_text.md`**: A condensed version of the entire document (if `generate_condensed_text=True`).
- **`table_of_contents.md`**: A table of contents based on the extracted text (if `generate_table_of_contents=True`).
- **`document_content.json`**: A JSON file containing the entire `DocumentContent` object.

---

## Model Information

### Multimodal Model (For Images + Table Analysis)

```python
MulitmodalProcessingModelInfo(
    provider="azure",                 # or "openai"
    model_name="gpt-4o",              # or "o1", depending on your model
    reasoning_efforts="medium",       # "low", "medium", or "high" for o1 model
    endpoint="...",                   # LLM endpoint
    key="...",                        # LLM auth key
    model="...",                      # Name of the actual deployment
    api_version="2024-12-01-preview"  # API version
)
```
- `provider`: Choose between `azure` or `openai`.
- `model_name`: Supported multimodal model names (e.g., `"gpt-4o"`, `"o1"`). 
- `reasoning_efforts`: Determine the depth and detail of the LLM's reasoning (`low`, `medium`, or `high`).

### Text Model (For Pure Text Processing)

```python
TextProcessingModelnfo(
    provider="azure",                 # or "openai"
    model_name="gpt-4o",              # "gpt-4o", "o1", or "o1-mini"
    reasoning_efforts="medium",       # "low", "medium", or "high"
    endpoint="...",
    key="...",
    model="...",
    api_version="2024-12-01-preview"
)
```
- Similar fields to `MulitmodalProcessingModelInfo`, but includes `"o1-mini"` for text tasks only. 
- `"o1-mini"` is **not** multimodal, so you must use it only for text-based processing.



- If your application needs embeddings for search or semantic indexing, you can configure this optional class.

---

## Contributing

Feel free to open issues or submit pull requests if you find bugs or want to add new features. We welcome community contributions that enhance the usability and performance of this pipeline.

---

## License

This project is licensed under the terms of the **MIT License**. See the [LICENSE](./LICENSE) file for details.
