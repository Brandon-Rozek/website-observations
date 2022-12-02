#!/usr/bin/env python
"""
Script to create Hugo markdown
files from iNaturalist Observations
"""

from urllib import request
from glob import glob
from http.client import HTTPResponse
from pathlib import Path
from typing import Any, Dict, Optional
import json
import sys
import time

CONTENT_LOCATION = "./"
USER_ID = "brandonrozek"
MIN_OBS_ID = -1


def retrieve_data_from_server():
    server_data = []
    server_ids = retrieve_obs_ids_from_server()
    for id_num in server_ids:
        # Grab observation from iNaturalist
        url = f"https://api.inaturalist.org/v1/observations/{id_num}"
        response: Optional[HTTPResponse] = None

        try:
            response = request.urlopen(url)
        except Exception:
            print(f"Unable to grab observation {id_num} from iNaturalist.")

        time.sleep(1) # Rate Limit: 1 request/sec

        if response is None:
            continue

        # Parse server response
        server_data_part = None
        try:
            server_data_part = json.loads(response.read())['results'][0]
            # Note: there is only one observation as a result
        except Exception:
            print(f"Malformed JSON response for observation {id_num}.")
            continue

        server_data_part = reformat_obs(id_num, server_data_part)
        server_data.append(server_data_part)


    print(f"Successfully obtained {len(server_data)} observations from the server.")
    return server_data


def retrieve_obs_ids_from_server():
    """
    Grabs observation ids from iNaturalist server
    """
    global MIN_OBS_ID
    server_data = []

    finished_retrieving = False
    while not finished_retrieving:
        # Grab observations from iNaturalist
        id_below = "&id_below=" + str(MIN_OBS_ID) \
            if MIN_OBS_ID > 0 else ""
        url = "https://api.inaturalist.org/v1/observations?order=desc&order_by=created_at&only_id=true&user_id=" + USER_ID + id_below
        response: Optional[HTTPResponse] = None

        try:
            response = request.urlopen(url)
        except Exception:
            print("Unable to grab observations from iNaturalist.")

        if response is None:
            sys.exit(-1)

        time.sleep(1) # Rate Limit: 1 request/sec

        # Parse server response
        server_data_part: Optional[list] = None
        try:
            server_data_part = json.loads(response.read())['results']
        except Exception:
            print("Malformed JSON response from server.")

        if server_data is None:
            sys.exit(-1)

        if not isinstance(server_data_part, list):
            print("Unexpected JSON response, should be of form list.")
            sys.exit(-1)

        # No more to retrieve
        if len(server_data_part) == 0:
            finished_retrieving = True
            break

        server_data_part = [d['id'] for d in server_data_part]

        # print(f"Retrieved {len(server_data_part)} observations from server")
        server_data.extend(server_data_part)
        MIN_OBS_ID = server_data_part[-1]

    print(f"Parsed a total of {len(server_data)} ids from server")
    return server_data


def reformat_obs(obsid, obs_json):
    """
    Takes a obs_json and
    slightly modifies it to match
    some of the fields Hugo expects.
    """
    obs_data = dict(
        id=str(obsid),
        metadata={},
        content=""
    )

    # Turn URL -> Syndication
    obs_data['metadata']['syndication'] = obs_json['uri']

    # Turn Created At -> Date
    obs_data['metadata']['date'] = obs_json['time_observed_at']

    # Grab some taxonomy information about the organism
    obs_data['metadata']['taxon'] = dict(
        name=obs_json['taxon']['name'],
        common_name=obs_json['taxon']['preferred_common_name']
    )

    # Grab only a few fields
    desired_fields = [
        'quality_grade', 'identifications_most_agree',
        'species_guess', 'identifications_most_disagree',
        'captive', 'project_ids',
        'community_taxon_id', 'geojson',
        'owners_identification_from_vision',
        'identifications_count', 'obscured',
        'num_identification_agreements',
        'num_identification_disagreements',
        'place_guess', "photos"
    ]
    for key in desired_fields:
        obs_data['metadata'][key] = obs_json[key]

    return obs_data

############################################################################

def findall(p, s):
    """
    Yields all the positions of
    the pattern p in the string s.
    Source: https://stackoverflow.com/a/34445090
    """
    i = s.find(p)
    while i != -1:
        yield i
        i = s.find(p, i+1)

def hugo_markdown_to_json(markdown_contents) -> Optional[Dict[Any, Any]]:
    """
    Take the contents from a Hugo markdown
    file and read the JSON frontmatter if it
    exists.
    """
    front_matter_indices = list(findall('---', markdown_contents))
    if len(front_matter_indices) < 2:
        return None
    front_matter = markdown_contents[(front_matter_indices[0] + 3):front_matter_indices[1]]
    json_contents = None
    try:
        json_contents = json.loads(front_matter)
    except Exception:
        pass
    if not isinstance(json_contents, dict):
        json_contents = None
    html_contents = markdown_contents[front_matter_indices[1] + 19:-17]
    return json_contents, html_contents

def create_markdown_str(frontmatter, content):
    """
    Takes a JSON frontmatter
    and creates a string representing
    the contents of a Hugo markdown
    file.
    """
    return "---\n" + \
        f"{json.dumps(frontmatter)}\n" +\
        "---\n" +\
        "{{< unsafe >}}\n" +\
        f"{content}\n" +\
        "{{< /unsafe >}}\n"

def file_from_id(idnum):
    """Returns filename from id"""
    return f"{CONTENT_LOCATION}/{idnum}.md"

def read_hugo_markdown(idnum) -> Optional[Dict[Any, Any]]:
    """
    Given an id, return the markdown file
    frontmatter and contents stored in Hugo
    if it exists.
    """
    try:
        with open(file_from_id(idnum), "r", encoding="UTF-8") as hugo_file:
            frontmatter, contents = hugo_markdown_to_json(hugo_file.read())
            return frontmatter, contents
    except Exception:
        return None

def write_markdown(id_num, frontmatter, contents):
    """
    Takes a frontmatter json
    and writes it to a hugo
    markdown content file.
    """
    try:
        with open(file_from_id(id_num), "w", encoding="UTF-8") as hugo_file:
            hugo_file.write(create_markdown_str(frontmatter, contents))
    except Exception as e:
        print("Failed to write", id_num)


############################################################################

# Read in saved data
saved_filenames = glob(CONTENT_LOCATION + "/*.md")
saved_ids = { Path(fname).stem for fname in saved_filenames }

server_data = retrieve_data_from_server()

# Data is structured like [{id: '', metadata: '', contents: ''}]
# Where metadata is a JSON and contents is HTML

for data in server_data:
    id_num = data['id']

    # If the observation already exists
    if id_num in saved_ids:
        saved_fm, saved_content = read_hugo_markdown(id_num)
        if saved_fm is None:
            print("Unable to read saved data id", id_num)

        # Only update if observation has changed
        elif saved_fm != data['metadata']:
            print("Updating id", id_num)
            write_markdown(id_num, data['metadata'], data['content'])

    # New observation found
    else:
        print("Creating id", id_num)
        write_markdown(id_num, data['metadata'], data['content'])

print("Completed")
