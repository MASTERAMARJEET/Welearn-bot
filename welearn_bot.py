#!/usr/bin/env python3

from requests import Session
from bs4 import BeautifulSoup as bs
from configparser import RawConfigParser
from datetime import datetime
from datetime import timedelta
import os, sys
import argparse
import json

# Get command line options
parser = argparse.ArgumentParser(description="A bot which can batch download files from WeLearn.")

parser.add_argument("courses", nargs="*", help="IDs of the courses to download files from. The word ALL selects all configured courses.")
parser.add_argument("-l", "--listcourses", action="store_true", help="display configured courses (ALL) and exit")
parser.add_argument("-a", "--assignments", action="store_true", help="show all assignments in given courses, download attachments and exit")
parser.add_argument("-d", "--dueassignments", action="store_true", help="show only due assignments, if -a was selected")
parser.add_argument("-f", "--forcedownload", action="store_true", help="force download files even if already downloaded")

args = parser.parse_args()
if len(args.courses) == 0 and not args.listcourses:
    print("No course names selected. Use the -h flag for usage.")
    sys.exit()

# Read the .welearnrc file from the home directory, and extract username and password
configfile = os.path.expanduser("~/.welearnrc")
config = RawConfigParser(allow_no_value=True)
config.read(configfile)
username = config["auth"]["username"]
password = config["auth"]["password"]

# Also extract the list of 'ALL' courses
all_courses = list(config["courses"].keys())
all_courses = map(str.strip, all_courses)
all_courses = map(str.upper, all_courses)
all_courses = list(all_courses)

# Select all courses from config if 'ALL' keyword is used
if 'ALL' in map(str.upper, args.courses):
    args.courses = all_courses

# List 'ALL' courses
if args.listcourses:
    for course in all_courses:
        print(course)
    sys.exit(0)
        
# Read from a cache of links
link_cache = set()
if os.path.exists(".link_cache"):
    with open(".link_cache") as link_cache_file:
        for link in link_cache_file.readlines():
            link_cache.add(link.strip())

with Session() as s:
    # Login to WeLearn with supplied credentials
    login_url = "https://welearn.iiserkol.ac.in/login/token.php"
    login_response = s.post(login_url, data = {'username' : username, 'password' : password, 'service' : 'moodle_mobile_app'})
    token = json.loads(login_response.content)['token']

    server_url = "https://welearn.iiserkol.ac.in/webservice/rest/server.php"

    # Helper function to retrieve a file/resource from the server
    def get_resource(res, prefix, indent=0):
        filename = res['filename']
        filepath = os.path.join(prefix, filename)
        fileurl = res['fileurl']
        
        # Only download if forced, or not already downloaded
        if not args.forcedownload and fileurl in link_cache:
            return
        
        # Create the course folder if not already existing
        if not os.path.exists(course_name):
            os.makedirs(course_name)
        
        # Download the file and write to the folder
        print(" " * indent + "Downloading " + filepath, end='')
        response = s.post(fileurl, data = {'token' : token})
        with open(filepath, "wb") as download:
            download.write(response.content)
        print(" ... DONE")
        
        # Add the file url to the cache
        link_cache.add(fileurl)
    

    if args.assignments:
        # Get assignment data from server
        assignments_response = s.post(server_url, \
            data = {'wstoken' : token, 'moodlewsrestformat' : 'json', 'wsfunction' : 'mod_assign_get_assignments'})
        # Parse as json
        assignments = json.loads(assignments_response.content)
        
        # Assignments are grouped by course
        for course in assignments['courses']:
            course_name = course['shortname']
            # Ignore unspecified courses
            if course_name not in args.courses:
                continue
            no_assignments = True
            for assignment in course['assignments']:
                # Get the assignment name, details, due date, and relative due date
                name = assignment['name']
                duedate = datetime.fromtimestamp(int(assignment['duedate']))
                due_str = duedate.strftime('%a %d %b, %Y, %H:%M:%S')
                duedelta = duedate - datetime.now()
                # Calculate whether the due date is in the future
                due = duedelta.total_seconds() > 0
                if args.dueassignments and not due:
                    continue
                no_assignments = False
                if not no_assignments:
                    print(course_name)
                # Show assignment details
                duedelta_str = f"{abs(duedelta.days)} days, {duedelta.seconds // 3600} hours"
                detail = bs(assignment['intro'], "html.parser").text
                print(f"    {name} - {detail}")
                if due:
                    print(f"        Due on: {due_str}")
                    print(f"        Time remaining : {duedelta_str}")
                else:
                    print(f"        Due on: {due_str} ({duedelta_str} ago)")
                for attachment in assignment['introattachments']:
                    print(f"        Attachment: {course_name}/{attachment['filename']}")
                    get_resource(attachment, course_name, indent=8)
                print()

    else:
        # Get a list of all courses along with a list of available resources
        courses_response = s.post(server_url, \
            data = {'wstoken' : token, 'moodlewsrestformat' : 'json', 'wsfunction' : 'core_course_get_courses_by_field'})
        resources_response = s.post(server_url, \
            data = {'wstoken' : token, 'moodlewsrestformat' : 'json', 'wsfunction' : 'mod_resource_get_resources_by_courses'})
        
        # Parse as json
        courses = json.loads(courses_response.content)
        resources = json.loads(resources_response.content)
       
        # Create a dictionary of course ids versus course names
        course_ids = dict()
        for course in courses['courses']:
            course_name = course['shortname']
            if course_name in args.courses:
                course_ids[course['id']] = course_name
        
        # Iterate through all resources, and only fetch ones from the specified course
        for resource in resources['resources']:
            if resource['course'] in course_ids:
                course_name = course_ids[resource['course']]
                for subresource in resource['contentfiles']:
                    get_resource(subresource, course_name)

    # Update cached links
    with open(".link_cache", "w") as link_cache_file:
        for link in list(link_cache):
            link_cache_file.write(link + "\n")
