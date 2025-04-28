import os
import logging

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Assuming content_analyzer.py is in the same directory or Python path is set correctly
from content_analyzer import ContentAnalyzer


def run_analyzer_test():
    """Runs a test using the ContentAnalyzer class."""
    logging.info("--- Starting ContentAnalyzer Test ---")

    # Define paths relative to the script location or use absolute paths
    # Assuming this script is in the content_understanding folder
    script_dir = os.path.dirname(__file__)
    workspace_root = os.path.abspath(os.path.join(script_dir, '..')) # Go up one level to the root

    analyzer_id = "cu_page_image_analyzer"
    # Construct absolute path for the schema
    analyzer_schema_path = os.path.join(script_dir, 'analyzer', f"{analyzer_id}.json")
    # Construct absolute path for the input image
    input_image_paths = [os.path.join(script_dir, 'test', 'page96.png'),
                         os.path.join(script_dir, 'test', 'page97.jpg')]
    # Define where the output CSV should go (within the default output dir)
    output_csv_name = "test_analysis_results.csv"
    # Define base data path explicitly if needed, otherwise defaults are used
    # base_data_path = os.path.join(script_dir, 'test') # Example if you want output in content_understanding/test/cu_page_image_analyzer

    logging.info(f"Analyzer ID: {analyzer_id}")
    logging.info(f"Analyzer Schema Path: {analyzer_schema_path}")
    logging.info(f"Input Image Path: {input_image_paths}")
    logging.info(f"Output CSV Name: {output_csv_name}")

    # Check if files exist before proceeding
    if not os.path.exists(analyzer_schema_path):
        logging.error(f"Analyzer schema file not found: {analyzer_schema_path}")
        return
    for input_image_path in input_image_paths:
        if not os.path.exists(input_image_path):
            logging.error(f"Input image file not found: {input_image_path}")
            return

    try:
        # Create an instance of ContentAnalyzer
        # Pass the specific schema path. Base data path will default to ../data/test
        analyzer = ContentAnalyzer(
            analyzer_id=analyzer_id,
            analyzer_schema_path=analyzer_schema_path
            # base_data_path=base_data_path # Uncomment and set if you want a different base data path
        )

        # Run the analysis process
        success, results = analyzer.run_analysis(
            input_file_paths=input_image_paths
        )

        if success:
            logging.info("ContentAnalyzer test completed successfully!")
            logging.info(f"Check output in: {analyzer.output_dir}")
            logging.info(f"Results: {results}")
        else:
            logging.error("ContentAnalyzer test process failed.")

    except Exception as e:
        logging.error(f"An error occurred during the ContentAnalyzer test: {e}", exc_info=True)

    logging.info("--- ContentAnalyzer Test Finished ---")

if __name__ == "__main__":
    run_analyzer_test()
