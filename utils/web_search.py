import os
import requests
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Define the structure of a search result entry
ResponseEntry = Tuple[str, str, str]


if not os.getenv("BING_API_KEY"):
    load_dotenv()


class WebSearch:
    """
    A class that encapsulates the functionality to perform web searches using
    Google Custom Search API or Bing Search API based on the provided configuration.
    """

    def __init__(self):
        """
        Initializes the WebSearch class with the provided configuration.

        Parameters:
        - config (dict): A dictionary containing configuration settings.
        """
        self.config = {
            "result_count": 2,
            # Bing Search enter these values
            "bing_api_key": os.getenv("BING_API_KEY"),
        }

    def search_query(self, query: str) -> Optional[List[ResponseEntry]]:
        """
        Performs a web search based on the query and configuration.

        Parameters:
        - query (str): The search query string.

        Returns:
        - A list of ResponseEntry tuples containing the title, URL, and snippet of each result.
        """
        result_count = int(self.config.get("result_count", 3))
        try:
            return self._search_bing(query, cnt=result_count)
        except ValueError as e:
            print(f"An error occurred: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        return None
    

    def _search_bing(self, query: str, cnt: int) -> Optional[List[ResponseEntry]]:
        """
        Performs a Bing search and processes the results.

        Parameters:
        - query (str): The search query string.
        - cnt (int): The number of search results to return.

        Returns:
        - A list of ResponseEntry tuples containing the name, URL, and snippet of each Bing search result.
        """
        api_key = self.config.get("bing_api_key")
        url = f"https://api.bing.microsoft.com/v7.0/search?q={query}"
        if cnt > 0:
            url += f"&count={cnt}"
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result_list: List[ResponseEntry] = []
            for item in response.json().get("webPages", {}).get("value", []):
                # Get content from the url
                content_response = requests.get(item["url"])
                if response.status_code == 200:
                    soup = BeautifulSoup(content_response.text, "html.parser")
                    cleaned_text = soup.get_text(separator=" ", strip=True)
                    item["snippet"] = cleaned_text

                result_list.append((item["name"], item["url"], item["snippet"]))
            return result_list
        else:
            print(f"Error with Bing Search API: {response.status_code}")
            return None

# Remember to replace the placeholders in CONFIG with your actual API keys.
# Example usage
# search = WebSearch()
# results = search.search_query("How to use python ta library")
# if results is not None:
#     for title, link, snippet in results:
#         print(title, link, snippet)
