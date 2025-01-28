import os
from dotenv import load_dotenv
load_dotenv()



from rich.console import Console
console = Console()

console.print(f"hello world, {os.getenv('USER')}!")