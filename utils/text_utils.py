import json
import json_repair
import re
import tiktoken
import pandas as pd


def show_json(obj):
    display(json.loads(obj.model_dump_json()))

def get_encoder(model = "gpt-4o"):
    if model == "gpt-4o":
        return tiktoken.get_encoding("o200k_base")       
    if model == "o1":
        return tiktoken.get_encoding("o200k_base")       
    if model == "mini":
        return tiktoken.get_encoding("o200k_base")       
    else:
        return tiktoken.get_encoding("o200k_base")

def get_token_count(text, model = "gpt-4o"):
    enc = get_encoder(model)
    return len(enc.encode(text))

def limit_token_count(text, limit = 100000, model = "gpt-4"):
    enc = get_encoder(model)
    return enc.decode(enc.encode(text)[:limit])

def extract_json(s):
    code = re.search(r"```json(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return s

def extract_sql(s):
    code = re.search(r"```sql(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return s

def extract_code(s):
    code = re.search(r"```python(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return ""

def extract_extracted_text(s):
    code = re.search(r"```EXTRACTED TEXT(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return ""


def extract_markdown(s):
    code = re.search(r"```markdown(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return ""

def extract_all_markdown(s):
    # Finds all markdown code blocks enclosed between ```markdown and ```
    blocks = re.findall(r"```markdown(.*?)```", s, re.DOTALL)
    return blocks  # Returns a list of all markdown block contents


def extract_mermaid(s):
    code = re.search(r"```mermaid(.*?)```", s, re.DOTALL)
    if code:
        return code.group(1)
    else:
        return ""

def extract_markdown_table(s):
    try:
        table_pattern = r"(\|.*\|\s*\n\|[-| ]+\|\s*\n(\|.*\|\s*\n)+)"
        tables = re.findall(table_pattern, s, re.MULTILINE)
    except:
        tables = []
        print("Error extracting markdown tables", f"Error extracting markdown tables from text '{s[:50]}'.")

    return tables

def extract_table_rows(markdown_table):
    lines = markdown_table.strip().split('\n')
    row_data = []

    for line in lines:
        if re.match(r"\|\s*[-]+\s*\|", line):
            continue  # Skip separator lines
        else:
            cells = re.findall(r"\|\s*([^|\n]+)\s*", line)
            if cells:
                row_data.append(tuple(cells))
    
    return row_data

def extract_markdown_table_as_df(s):
    try:
        matches = extract_table_rows(s)
        header = matches[0]
        data = matches[1:]

        df = pd.DataFrame(data, columns=header)
    except Exception as e:
        df = pd.DataFrame()
        print("Warning Only - Error extracting markdown tables as DataFrame", f"Error extracting markdown tables as DataFrame from text '{s[:50]}'. Error: {e}")
        print(s)

    return df

def remove_code(s):
    return re.sub(r"```python(.*?)```", "", s, flags=re.DOTALL)

def remove_markdown(s):
    return re.sub(r"```markdown(.*?)```", "", s, flags=re.DOTALL)

def remove_mermaid(s):
    return re.sub(r"```mermaid(.*?)```", "", s, flags=re.DOTALL)

def remove_extracted_text(s):
    return re.sub(r"```EXTRACTED TEXT(.*?)```", "", s, flags=re.DOTALL)

def clean_up_text(text):
    code = extract_code(text)
    text = text.replace(code, '')
    text = text.replace("```python", '')
    text = text.replace("```", '')
    return text

def recover_json(json_str, verbose = False):
    decoded_object = {}

    if '{' not in json_str:
        return json_str

    json_str = extract_json(json_str)

    try:
        decoded_object = json.loads(json_str)
        return decoded_object
    except Exception:
        try:
            decoded_object = json.loads(json_str.replace("'", '"'))
            return decoded_object
        except Exception:
            try:
                decoded_object = json_repair.loads(json_str.replace("'", '"'))

                for k, d in decoded_object.items():
                    dd = d.replace("'", '"')
                    decoded_object[k] = json.loads(dd)
                
                return decoded_object
            except:
                print(f"all json recovery operations have failed for {json_str}")
        
            if verbose:
                if isinstance(decoded_object, dict):
                    print(f"\n>>> Recovering JSON:\n{json.dumps(decoded_object, indent=3)}")
                else:
                    print(f"\n>>> Recovering JSON:\n{json_str}")


    return json_str

def extract_chunk_number(filename, verbose = False):
    match = re.search(r"chunk_(\d+)", filename)
    if match:
        chunk_number = match.group(1)
        if verbose: print(f"Extracted chunk number: {chunk_number}")
    else:
        chunk_number = 'unknown'

    return chunk_number


def convert_path(path):
    return str(path).replace("\\", "/")