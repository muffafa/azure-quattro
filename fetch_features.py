import aiohttp
import asyncio
import base64
import json
import os
import re
from bs4 import BeautifulSoup  # For cleaning HTML content
from dotenv import load_dotenv

load_dotenv()

organization = "bordasw"
project = "Quattro"

url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version=7.1-preview.2"
pat_token = f":{os.getenv('pat')}"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic " + base64.b64encode(pat_token.encode()).decode(),
}

# Define the query here
query = """
SELECT 
  [System.Id], 
  [System.Title], 
  [System.WorkItemType], 
  [System.Description], 
  [System.IterationPath],
  [System.AreaPath]
FROM WorkItemLinks
WHERE 
  [Source].[System.TeamProject] = @project 
  AND (
    [Source].[System.WorkItemType] = 'Feature' 
    OR [Source].[System.WorkItemType] = 'Epic'
    OR [Source].[System.WorkItemType] = 'Module'
  )
  AND 
  [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
ORDER BY [System.AreaPath], [System.IterationPath], [System.WorkItemType], [System.Title]
MODE (Recursive)
"""

# List to store successfully fetched work item IDs
fetched_ids = []

# Regex pattern to identify URLs
url_pattern = re.compile(r'http[s]?://\S+')


async def fetch_work_item_details(session, item_id):
    item_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems/{item_id}?api-version=7.1-preview.3"
    async with session.get(item_url, headers=headers) as item_response:
        if item_response.status == 200:
            item_data = await item_response.json()

            if item_id in fetched_ids:
                print(f"Duplicate ID found: {item_id}. Exiting the program.")
                raise SystemExit(f"Duplicate ID found: {item_id}. Exiting the program.")

            fetched_ids.append(item_id)

            # Clean the description using BeautifulSoup
            description_html = item_data["fields"].get("System.Description", "No Description")
            soup = BeautifulSoup(description_html, "html.parser")
            cleaned_description = soup.get_text(separator=" ").strip()

            # Remove external links using regex
            cleaned_description = re.sub(url_pattern, '', cleaned_description)

            print(f"Successfully fetched work item ID: {item_id}")
            return {
                "id": item_id,
                "title": item_data["fields"].get("System.Title", "No Title"),
                "type": item_data["fields"].get("System.WorkItemType", "Unknown"),
                "description": cleaned_description,
            }
        else:
            print(f"Failed to fetch item details for ID: {item_id}")
            return None


async def fetch_work_items():
    async with aiohttp.ClientSession() as session:
        print("Fetching work items...")
        async with session.post(
            url, headers=headers, json={"query": query}
        ) as response:
            if response.status == 200:
                work_items = (await response.json())["workItemRelations"]
                print(f"Successfully fetched {len(work_items)} work item relations.")
                return work_items
            else:
                print(f"Failed to fetch work items. Status Code: {response.status}")
                return []


async def main():
    work_item_details = {}

    work_items = await fetch_work_items()

    tasks = []
    async with aiohttp.ClientSession() as session:
        for relation in work_items:
            item_id = relation["target"]["id"]
            print(f"Fetching details for work item ID: {item_id}")
            task = fetch_work_item_details(session, item_id)
            tasks.append(task)

        print("Fetching all work item details...")
        work_item_results = await asyncio.gather(*tasks)

        for work_item in work_item_results:
            if work_item:
                work_item_details[work_item["id"]] = work_item

    # Reconstruct the hierarchy
    hierarchy = {}

    for item_id, details in work_item_details.items():
        parent_id = details.get("parent_id", None)
        if parent_id is None:
            hierarchy[item_id] = details
            hierarchy[item_id]["children"] = []
        else:
            if parent_id in work_item_details:
                if "children" not in work_item_details[parent_id]:
                    work_item_details[parent_id]["children"] = []
                work_item_details[parent_id]["children"].append(details)

    # Write to a file
    with open("work_items_hierarchy.txt", "w", encoding="utf-8") as f:

        def write_hierarchy(items, level=0):
            for item in items:
                if item["type"] in ["Module", "Epic", "Feature"]:
                    if item["type"] == "Module":
                        f.write("\n")

                    f.write(
                        f"{' ' * level}{item['id']}: {item['type']}: {item['title']}"
                    )
                    if item["type"] == "Feature":
                        f.write(f" - {item['description']}")
                    f.write("\n")

                    if "children" in item:
                        write_hierarchy(item["children"], level + 1)

        write_hierarchy(hierarchy.values())

    print("Work items hierarchy has been written to work_items_hierarchy.txt")


if __name__ == "__main__":
    asyncio.run(main())
