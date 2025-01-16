import os
import base64
from PIL import Image
from utils.file_utils import write_to_file, replace_extension, read_asset_file
from utils.text_utils import clean_up_text, extract_markdown, extract_code
from utils.openai_utils import call_llm, call_llm_structured_outputs
from utils.data_models import EmbeddedImages, EmbeddedTables




def convert_png_to_jpg(image_path):
    """
    Converts a PNG image to JPG format.
    """
    if os.path.splitext(image_path)[1].lower() == '.png':
        with Image.open(image_path) as img:
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            new_image_path = os.path.splitext(image_path)[0] + '.jpg'
            img.save(new_image_path, 'JPEG')
            return new_image_path
    else:
        return image_path


def get_image_base64(image_path):
    """
    Encodes an image file in base64 format.
    """
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
        return encoded_string.decode('ascii')


def analyze_images(image_path, model_info=None):
    """
    Analyzes an image and generates descriptions or explanations.

    Args:
        image_path (str): Path to the image file.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Analysis response.
        str: Generated text filename.
    """
    image_prompt = read_asset_file('multimodal_processing_pipeline/prompts/image_description_prompt.txt')[0]
    image_path = convert_png_to_jpg(image_path)  # Ensure the image is in JPG format

    response = call_llm_structured_outputs(
        imgs=image_path,
        prompt=image_prompt,
        model_info=model_info,
        response_format=EmbeddedImages
    )

    return response


def analyze_tables(image_path, model_info=None):
    """
    Analyzes an image to extract table data and formats it as Markdown.

    Args:
        image_path (str): Path to the image file.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Table analysis response.
        str: Generated Markdown filename.
    """
    table_prompt = read_asset_file('multimodal_processing_pipeline/prompts/table_description_prompt.txt')[0]
    image_path = convert_png_to_jpg(image_path)  # Ensure the image is in JPG format

    response = call_llm_structured_outputs(
        imgs=image_path,
        prompt=table_prompt,
        model_info=model_info,
        response_format=EmbeddedTables
    )

    return response


def process_text(text, model_info=None):
    """
    Processes text using a language model.

    Args:
        text (str): The input text to process.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Processed text.
    """

    process_text_prompt = read_asset_file('multimodal_processing_pipeline/prompts/process_extracted_text_prompt.txt')[0]
    prompt = process_text_prompt.format(text=text)

    response = call_llm(
        prompt,
        model_info=model_info
    )

    return response


def condense_text(text, model_info=None):
    """
    Condenses text to a specified number of tokens.

    Args:
        text (str): The input text to condense.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Condensed text.
    """

    condense_text_prompt = read_asset_file('multimodal_processing_pipeline/prompts/document_condensation_prompt.txt')[0]
    prompt = condense_text_prompt.format(document=text)

    response = call_llm(
        prompt,
        model_info=model_info
    )

    return response