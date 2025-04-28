import os
import sys
import time
import logging
from dotenv import load_dotenv
from typing import Optional, List, Any # Corrected List import

import json

from utils.file_utils import generate_uuid_from_string

# Load environment variables from .env file
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add the parent directory (code) to the Python path to find the utils module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from client.content_understanding_client import AzureContentUnderstandingClient


class ContentAnalyzer:
    def __init__(
        self,
        analyzer_id: str,
        file_type: str = "image",
        base_data_path: Optional[str] = None,
        analyzer_schema_path: Optional[str] = None,
    ):
        """
        Initialize the ContentAnalyzer with configuration settings.
        
        Args:
            analyzer_id: The ID of the analyzer to use
            file_type: Type of file to analyze (default: "image")
            base_data_path: Base directory for data (default: '../data/test')
            analyzer_schema_path: Path to the analyzer schema file (default: derived from analyzer_id)
        """
        
        
        # Get credentials from environment variables
        self.endpoint = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_ENDPOINT")
        self.api_key = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_KEY")
        self.api_version = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_API_VERSION")
        
        # Set configuration values
        self.analyzer_id = analyzer_id
        self.file_type = file_type
        
        # Set default paths if not provided
        if base_data_path is None:
            self.base_data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'test'))
        else:
            self.base_data_path = base_data_path
            
        if analyzer_schema_path is None:
            self.analyzer_schema_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), 'analyzer', f"{analyzer_id}.json")
            )
        else:
            self.analyzer_schema_path = analyzer_schema_path
            
        self.output_dir = os.path.join(self.base_data_path, self.analyzer_id)
        self.cu_client = None
        
    def initialize_client(self) -> bool:
        """Initialize the Azure Content Understanding client."""
        logging.info("--- Initializing AzureContentUnderstandingClient ---")
        
        logging.info(f"Loaded environment variables: ENDPOINT={self.endpoint}, API_VERSION={self.api_version}")
        logging.info(f"API_KEY={'*' * len(self.api_key) if self.api_key else 'Not Set'}")

        if not all([self.endpoint, self.api_key, self.api_version]):
            logging.error("Missing required environment variables (ENDPOINT, KEY, API_VERSION). Exiting.")
            return False

        try:
            self.cu_client = AzureContentUnderstandingClient(
                endpoint=self.endpoint,
                api_version=self.api_version,
                subscription_key=self.api_key
            )
            logging.info("AzureContentUnderstandingClient initialized successfully.")
            return True
        except ValueError as e:
            logging.error(f"Client initialization failed: {e}")
            return False
    
    def ensure_output_directory(self) -> bool:
        """Ensure that the output directory exists."""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            logging.info(f"Ensured output directory exists: {self.output_dir}")
            return True
        except OSError as e:
            logging.error(f"Failed to create output directory {self.output_dir}: {e}")
            return False
    
    def ensure_analyzer_exists(self) -> bool:
        """Ensure that the analyzer exists or create it."""
        logging.info(f"--- Ensuring analyzer '{self.analyzer_id}' exists ---")
        try:
            self.cu_client.ensure_analyzer_exists(self.analyzer_id, self.analyzer_schema_path)
            logging.info(f"Checking analyzer status...")
            # Add a small delay, especially if creation might have been triggered
            time.sleep(5) 
            details = self.cu_client.get_analyzer_detail_by_id(self.analyzer_id)
            logging.info(f"Successfully ensured analyzer '{details.get('analyzerId')}' exists.")
            return True
        except FileNotFoundError as e:
            logging.error(f"Analyzer schema file not found: {e}. Cannot create analyzer.")
            return False
        except Exception as e:
            logging.error(f"Failed to ensure analyzer exists: {e}")
            return False
    
    def analyze_files(self, input_file_paths: list[str]) -> bool:
        """Analyze a list of files using the Content Understanding client."""
        logging.info(f"--- Analyzing {len(input_file_paths)} files ---")
        results = []
        
        # Basic check if the list is empty
        if not input_file_paths:
            logging.warning("Input file list is empty. Nothing to analyze.")
            return False

        # Check existence of files before submitting to avoid unnecessary API calls for non-existent files
        valid_file_paths = []
        for file_path in input_file_paths:
            if os.path.exists(file_path):
                valid_file_paths.append(file_path)
            else:
                logging.error(f"Input file not found: {file_path}. Skipping this file.")
        
        if not valid_file_paths:
            logging.error("No valid input files found to analyze.")
            return False

        logging.info(f"Submitting {len(valid_file_paths)} valid files for analysis.")
        try:
            results = self.cu_client.analyze_files_in_parallel(
                analyzer_id=self.analyzer_id,
                file_paths=valid_file_paths, # Use the filtered list
                output_dir=self.output_dir,
                max_workers=1 # Keep max_workers=1 as per original code, adjust if needed
            )
            
            # Check if results list is not empty and contains no None values (indicating failures)
            if results and all(result is not None for result in results):
                logging.info(f"Analysis completed for {len(results)} files.")
                # Further check if expected JSON files were created for all valid inputs
                all_json_created = True
                for file_path in valid_file_paths:
                    input_file_name = os.path.basename(file_path)
                    expected_json_output = os.path.join(
                        self.output_dir, f"{os.path.splitext(input_file_name)[0]}.json"
                    )
                    if not os.path.exists(expected_json_output):
                        logging.error(f"JSON output file WAS NOT created for: {input_file_name} at {expected_json_output}")
                        all_json_created = False
                
                if all_json_created:
                    logging.info("All expected JSON output files were created.")
                    return True, results
                else:
                    logging.error("Some JSON output files were missing.")
                    return False, results
            elif results:
                 logging.error(f"Analysis failed for some files. Results: {results}")
                 return False, results
            else:
                logging.error("Analysis failed or returned no results.")
                return False, results
            
        except Exception as e:
            logging.error(f"File analysis failed with exception: {e}", exc_info=True)
            return False, results
    
    
    def process_results(self, input_file_paths: list[str], results: Any) -> bool:
        """Process analysis results for each input file, generating a markdown file for each."""
        all_processed_successfully = True
        final_markdown_outputs = {}

        for input_file_path in input_file_paths:
            input_file_name_base = os.path.splitext(os.path.basename(input_file_path))[0]
            # Define the expected JSON result file path
            json_result_path = os.path.join(self.output_dir, f"{input_file_name_base}.json")

            if not os.path.exists(json_result_path):
                logging.error(f"JSON result file not found for {input_file_path} at {json_result_path}. Skipping processing.")
                all_processed_successfully = False
                continue

        for result in results:
            try:
                # Check if the result is a valid JSON object
                cu_result, file_path, elapsed_time = result
                input_file_name_base = os.path.splitext(os.path.basename(file_path))[0]
                output_md_name = f"{input_file_name_base}.{generate_uuid_from_string(file_path)}.cu_text.md"
                output_md_path = os.path.join(self.output_dir, output_md_name)
                logging.info(f"--- Processing result for '{file_path}' to '{output_md_path}' ---")
                markdown_content = self._generate_markdown_for_single_result(cu_result, input_file_name_base)

                # Save the generated markdown to the specific file
                with open(output_md_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                logging.info(f"Markdown output saved to: {output_md_path}")
                final_markdown_outputs[file_path] = output_md_path

            except Exception as e:
                logging.error(f"Processing result for {file_path} failed: {e}", exc_info=True)
                all_processed_successfully = False
        
        # Return True only if all files were processed successfully
        # Consider returning the dictionary of generated paths instead or in addition
        return all_processed_successfully, final_markdown_outputs
    

    def _generate_markdown_for_single_result(self, json_result_data: dict, file_name_base: str) -> str:
        """Helper method to generate markdown content from a single JSON result object."""
        markdown_output = [f"## Analysis Results for: `{file_name_base}`\n"]
        try:
            # --- Parsing logic based on file_type (same as in client method) ---
            if (self.file_type == "document") or (self.file_type == "image"):
                contents = json_result_data.get("result", {}).get("contents", [])
                if contents:
                    fields = contents[0].get("fields", {})
                    
                    # Extract and format each field (simplified example)
                    page_section_title = fields.get("PageSectionTitle", {}).get("valueString", "")
                    if page_section_title: markdown_output.append(f"### {page_section_title}\n")

                    body_text = fields.get("BodyText", {}).get("valueString", "")
                    if body_text: markdown_output.append(f"**Body Text:**\n{body_text}\n")

                    summary = fields.get("Summary", {}).get("valueString", "")
                    if summary: markdown_output.append(f"**Summary:**\n{summary}\n")

                    page_keywords = fields.get("PageKeywords", {}).get("valueString", "")
                    if page_keywords: markdown_output.append(f"**Keywords:** `{page_keywords}`\n")

                    figure_ids = fields.get("FigureIds", {}).get("valueString", "")
                    if figure_ids: markdown_output.append(f"**Figure IDs:** `{figure_ids}`\n")

                    figure_captions = fields.get("FigureCaptions", {}).get("valueString", "")
                    if figure_captions: markdown_output.append(f"**Figure Captions:** {figure_captions}\n")

                    figure_type = fields.get("FigureType", {}).get("valueString", "")
                    if figure_type: markdown_output.append(f"**Figure Type:** `{figure_type}`\n")

                    figure_descriptions = fields.get("FigureDescriptions", {}).get("valueString", "")
                    if figure_descriptions: markdown_output.append(f"**Figure Descriptions:**\n{figure_descriptions}\n")

                    figure_analyses = fields.get("FigureAnalyses", {}).get("valueString", "")
                    if figure_analyses: markdown_output.append(f"**Figure Analyses:**\n{figure_analyses}\n")

                    important_warnings = fields.get("ImportantWarnings", {}).get("valueString", "")
                    if important_warnings: markdown_output.append(f"**Important Warnings:**\n{important_warnings}\n")


                else:
                    logging.warning(f"No 'contents' found in result for {file_name_base}. Adding basic info.")
                    markdown_output.append("*No content fields extracted.*\n")
            else:
                logging.warning(f"Unknown or unhandled file type '{self.file_type}' for {file_name_base}. Including basic info.")
                markdown_output.append("*Analysis results for this file type are not specifically formatted.*\n")

        except Exception as e:
            logging.warning(f"Could not parse result for {file_name_base} using expected schema: {e}. Adding basic info.")
            markdown_output.append(f"*Error parsing content fields: {e}*\n")
        
        markdown_output.append("\n---\n") # Separator
        return "".join(markdown_output)
        
    
    def run_analysis(self, 
                     input_file_paths: list[str]) -> bool:
        """Run the complete analysis process on a list of files."""
        logging.info("--- Starting Content Analysis Process ---")
        
        # Initialize the client
        if not self.initialize_client():
            return False 
        
        # Ensure output directory exists
        if not self.ensure_output_directory():
            return False
        
        # Ensure analyzer exists
        if not self.ensure_analyzer_exists():
            return False
        
        # Analyze the files
        analysis_successful, results = self.analyze_files(input_file_paths)
        
        # Process results if analysis was successful
        final_markdown_outputs = {}
        if analysis_successful:
            processing_success, final_markdown_outputs = self.process_results(input_file_paths, results)

            logging.info("--- Analysis Process Finished ---")
            return processing_success, final_markdown_outputs # Return the success status of processing
        else:
            logging.warning("--- Skipped processing results due to analysis failure ---")
            logging.info("--- Analysis Process Finished ---")
            return False, {}


if __name__ == "__main__":
    # Example usage
    analyzer = ContentAnalyzer(
        analyzer_id="cu_page_image_analyzer",
        file_type="image"
        # base_data_path="custom/path" # Optional: Override default data path
    )
    
    # List of image files to analyze
    image_paths = [
        os.path.join(analyzer.base_data_path, "page96.png"),
        # Add more file paths here if needed
        # os.path.join(analyzer.base_data_path, "another_image.png"), 
    ]
    
    # Run the analysis on the list of files
    success = analyzer.run_analysis(input_file_paths=image_paths)
    
    if success:
        logging.info("Analysis and processing completed successfully for all files!")
    else:
        logging.error("Analysis or processing process failed for one or more files.")