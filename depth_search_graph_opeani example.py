"""
depth_search_graph_opeani example
"""

from dotenv import load_dotenv

from scrapegraphai.graphs import DepthSearchGraph

load_dotenv()

graph_config = {
    "llm": {
        "model": "ollama/qwen2.5:7b",
        "temperature": 0,
        "format": "json",  # Ollama needs the format to be specified explicitly
    },
    "verbose": True,
    "headless": False,
    "depth": 2,
    "only_inside_links": False,
}
              
search_graph = DepthSearchGraph(
    prompt= "Extract only the following from this website, Name, Address, Is it a chain, Type of hotel, Support number and email, Website, Guest rating, Pricing of each type of room",
    source="https://www.aasareinn.com/",
    config=graph_config,
)

result = search_graph.run()
print(result)