tools = [
  {
    "name": "web_search",
    "description": "Performs a web search with the provided query string.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The search query string."
        }
      },
      "required": ["query"]
    }
  },
  {
    "name": "code_execution",
    "description": "Executes the provided code string.",
    "parameters": {
      "type": "object",
      "properties": {
        "code": {
          "type": "string",
          "description": "The code to execute."
        }
      },
      "required": ["code"]
    }
  },
  {
    "name": "image_explanation_online",
    "description": "Provides an explanation of an image from an online URL.",
    "parameters": {
      "type": "object",
      "properties": {
        "URL": {
          "type": "string",
          "description": "The URL of the image."
        }
      },
      "required": ["URL"]
    }
  },
  {
    "name": "image_explanation_local",
    "description": "Provides an explanation of an image from a local file path.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "The local file path of the image."
        }
      },
      "required": ["path"]
    }
  }
]
