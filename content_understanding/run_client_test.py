import os
import sys
import time
import logging
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add the parent directory (code) to the Python path to find the utils module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from client.content_understanding_client import AzureContentUnderstandingClient

# Load environment variables from .env file (assuming it's in the root of the project)
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
# load_dotenv(dotenv_path=dotenv_path)
load_dotenv()

def run_test():
    """Runs a sequence of tests using the AzureContentUnderstandingClient."""
    logging.info("--- Starting AzureContentUnderstandingClient Test Run ---")

    # --- Get Credentials and Configuration ---
    endpoint = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_ENDPOINT")
    api_key = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_KEY")
    api_version = os.getenv("AZURE_AI_CONTENT_UNDERSTANDING_API_VERSION")

    logging.info(f"Loaded environment variables: ENDPOINT={endpoint}, API_VERSION={api_version}")
    logging.info(f"API_KEY={'*' * len(api_key) if api_key else 'Not Set'}")

    if not all([endpoint, api_key, api_version]):
        logging.error("Missing required environment variables (ENDPOINT, KEY, API_VERSION). Exiting.")
        return

    # Configuration derived from the CLI command: python process_files.py image ../data/test cu_pag_image_analyzer
    file_type = "image"
    base_data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'test'))
    analyzer_id = "cu_page_image_analyzer"
    analyzer_schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'analyzer', f"{analyzer_id}.json"))
    output_dir = os.path.join(base_data_path, analyzer_id)
    output_csv_path = os.path.join(output_dir, "manual_test_results.csv") # Distinct CSV name
    input_file_name = "page96.png"
    input_file_path = os.path.join(base_data_path, input_file_name)

    logging.info(f"Configuration:")
    logging.info(f"  File Type: {file_type}")
    logging.info(f"  Data Path: {base_data_path}")
    logging.info(f"  Analyzer ID: {analyzer_id}")
    logging.info(f"  Schema Path: {analyzer_schema_path}")
    logging.info(f"  Output Dir: {output_dir}")
    logging.info(f"  Output CSV: {output_csv_path}")
    logging.info(f"  Input File: {input_file_path}")

    # Ensure output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"Ensured output directory exists: {output_dir}")
    except OSError as e:
        logging.error(f"Failed to create output directory {output_dir}: {e}")
        return

    # --- Initialize Client ---
    try:
        cu_client = AzureContentUnderstandingClient(
            endpoint=endpoint,
            api_version=api_version,
            subscription_key=api_key
        )
        logging.info("AzureContentUnderstandingClient initialized successfully.")
    except ValueError as e:
        logging.error(f"Client initialization failed: {e}")
        return

    # --- Test Step 1: Ensure Analyzer Exists ---
    logging.info(f"\n--- Step 1: Ensuring analyzer '{analyzer_id}' exists ---")
    try:
        cu_client.ensure_analyzer_exists(analyzer_id, analyzer_schema_path)
        logging.info(f"Checking analyzer status...")
        # Add a small delay, especially if creation might have been triggered
        time.sleep(5) 
        details = cu_client.get_analyzer_detail_by_id(analyzer_id)
        logging.info(f"Successfully ensured analyzer '{details.get('analyzerId')}' exists.")
    except FileNotFoundError as e:
         logging.error(f"Analyzer schema file not found: {e}. Cannot create analyzer.")
         return # Stop if schema is missing for creation
    except Exception as e:
        logging.error(f"Failed to ensure analyzer exists: {e}")
        return # Stop the test if this fails

    # --- Test Step 2: Analyze File ---
    logging.info(f"\n--- Step 2: Analyzing file '{input_file_path}' ---")
    if not os.path.exists(input_file_path):
        logging.error(f"Input file not found: {input_file_path}. Skipping analysis.")
        return

    analysis_successful = False
    try:
        results = cu_client.analyze_files_in_parallel(
            analyzer_id=analyzer_id,
            file_paths=[input_file_path],
            output_dir=output_dir,
            max_workers=1
        )
        if results and results[0] is not None:
            logging.info(f"Analysis completed for {results[0][0]} in {results[0][1]:.2f} seconds.")
            expected_json_output = os.path.join(output_dir, f"{os.path.splitext(input_file_name)[0]}.json")
            if os.path.exists(expected_json_output):
                logging.info(f"JSON output file created: {expected_json_output}")
                analysis_successful = True
            else:
                logging.error(f"JSON output file WAS NOT created: {expected_json_output}")
        else:
            logging.error("Analysis failed or returned no results.")
    except Exception as e:
        logging.error(f"File analysis failed: {e}")

    # --- Test Step 3: Process Results to CSV ---
    if analysis_successful:
        logging.info(f"\n--- Step 3: Processing results in '{output_dir}' to CSV ---")
        try:
            cu_client.process_analysis_results_to_csv(
                results_dir=output_dir,
                file_type=file_type, # Use the correct file type
                output_csv_path=output_csv_path
            )
            if os.path.exists(output_csv_path):
                logging.info(f"Successfully created CSV results file: {output_csv_path}")
            else:
                logging.error(f"CSV results file WAS NOT created: {output_csv_path}")
        except Exception as e:
            logging.error(f"Processing results to CSV failed: {e}")
    else:
        logging.warning("\n--- Step 3: Skipped processing results to CSV due to analysis failure. ---")

    logging.info("\n--- Test Run Finished ---")

if __name__ == "__main__":
    run_test()
