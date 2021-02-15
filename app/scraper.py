from app import app, db, celery
from app.models import Person
from .s3 import ImageUploader

from PIL import Image
from io import BytesIO
import os
import requests
import re
import json
from bs4 import BeautifulSoup
import yaledirectory
import string
from cryptography.fernet import Fernet


with open('app/res/majors.txt') as f:
    MAJORS = f.read().splitlines()
with open('app/res/major_full_names.json') as f:
    MAJOR_FULL_NAMES = json.load(f)
RE_ROOM = re.compile(r'^([A-Z]+)-([A-Z]+)(\d+)(\d)([A-Z]+)?$')
RE_BIRTHDAY = re.compile(r'^[A-Z][a-z]{2} \d{1,2}$')
RE_ACCESS_CODE = re.compile(r'[0-9]-[0-9]+')
RE_PHONE = re.compile(r'[0-9]{3}-[0-9]{3}-[0-9]{4}')

FERNET_KEY = os.environ.get('FERNET_KEY')


def get_html(cookie):
    filename = 'page.html'
    if not os.path.exists(filename):
        print('Page not cached, fetching.')
        requests.get('https://students.yale.edu/facebook/ChangeCollege',
                     params={
                        'newOrg': 'Yale College'
                     },
                     headers={
                         'Cookie': cookie,
                     })
        r = requests.get('https://students.yale.edu/facebook/PhotoPageNew',
                         params={
                             'currentIndex': -1,
                             'numberToGet': -1,
                         },
                         headers={
                             'Cookie': cookie,
                         })
        html = r.text
        with open(filename, 'w') as f:
            f.write(html)
        print('Done fetching page.')
    else:
        print('Using cached page.')
        with open(filename, 'r') as f:
            html = f.read()
    return html


def get_tree(html):
    print('Building tree.')
    tree = BeautifulSoup(html, 'html.parser')
    print('Done building tree.')
    return tree


def get_containers(tree):
    return tree.find_all('div', {'class': 'student_container'})


def clean_image_id(image_src):
    image_id = image_src.lstrip('/facebook/Photo?id=')
    # Check if image is not found
    if image_id == 0:
        return None
    return int(image_id)


def clean_name(name):
    print('Parsing ' + name)
    first_name, last_name = name.strip().split(', ', 1)
    return first_name, last_name


def clean_year(year):
    year = year.lstrip('\'')
    if not year:
        return None
    return 2000 + int(year)


def get_directory_entry(directory, person):
    query = {
        'first_name': person['first_name'],
        'last_name': person['last_name'],
        'school': 'YC'
    }
    if person.get('email'):
        query['email'] = person['email']
    if person.get('college'):
        query['college'] = person['college'] + ' College'
    people = directory.people(**query)
    print('Found %d matching people in directory.' % len(people))
    if not people:
        # If nothing found, do a broader search and return first result
        person = directory.person(first_name=person['first_name'], last_name=person['last_name'])
        if person:
            print('Found matching person searching only by name.')
        return person
    return people[0]


def compare_years(page_key, people, emails):
    print(f'Comparing years from {page_key} store.')
    with open(f'app/res/{page_key}.html.fernet', 'rb') as f:
        fernet = Fernet(FERNET_KEY)
        html = fernet.decrypt(f.read())
    tree = get_tree(html)
    containers = get_containers(tree)

    for container in containers:
        year = clean_year(container.find('div', {'class': 'student_year'}).text)
        info = container.find_all('div', {'class': 'student_info'})
        try:
            email = info[1].find('a').text
        except AttributeError:
            continue
        if not people[emails[email]].get('leave') and email in emails and year is not None and people[emails[email]]['year'] is not None:
            people[emails[email]]['leave'] = (year < people[emails[email]]['year'])
            print(email + ' is' + (' not' if not people[emails[email]]['leave'] else '') + ' taking a leave.')
    return people


def split_id_name(combined):
    print('Splitting ' + combined)
    if not combined:
        return None, None
    ID_RE = re.compile(r'^[A-Z_]+$')
    id, name = combined.split(' ', 1)
    if ID_RE.match(id):
        return id, name
    return '', combined


def add_directory_to_person(person, entry):
    if not person.get('netid'):
        person.update({
            'netid': entry.netid,
            'first_name': entry.first_name,
            'last_name': entry.last_name,
            'college': entry.residential_college_name.replace(' College', ''),
            'upi': entry.upi,
            'email': entry.email,
        })
    organization_id, organization = split_id_name(entry.organization_name)
    unit_id, unit = split_id_name(entry.organization_unit_name)
    person.update({
        'title': entry.directory_title,
        'nickname': entry.known_as if entry.known_as != entry.first_name else None,
        'middle_name': entry.middle_name,
        'suffix': entry.suffix,
        'phone': entry.phone_number,
        'college_code': entry.residential_college_code,
        'school': entry.primary_school_name,
        'school_code': entry.primary_school_code,
        # Always the same as organization_unit
        #'primary_organization': entry.primary_organization_name,
        # Always empty
        #'primary_organization_id': entry.primary_organization_id,
        'organization_id': organization_id,
        'organization': organization,
        'unit_id': unit_id,
        'unit': unit,
        'unit_code': entry.primary_organization_code,
        # Always the same as organization
        #'primary_division': entry.primary_division_name,
        'curriculum': entry.student_curriculum,
        'mailbox': entry.mailbox,
        'postal_address': entry.postal_address,
        # TODO: do we really want to merge these? Will there ever be both?
        'address': person.get('address') or entry.student_address or entry.registered_address,
        'office': entry.internal_location,
    })
    if entry.primary_organization_name != entry.organization_unit_name:
        print('Warning: primary_organization_name and organization_unit_name are different!')
    if entry.organization_name != entry.primary_division_name:
        print('Warning: organization_name and primary_division_name are diferent!')
    if not person.get('year') and entry.student_expected_graduation_year:
        person['year'] = int(entry.student_expected_graduation_year)
    return person


letters = string.ascii_lowercase
numbers = string.digits
characters = letters + numbers


def read_directory(directory, prefix: str = ''):
    print('Attempting prefix ' + prefix)
    people, total = directory.people(netid=prefix, include_total=True)

    if total == len(people):
        print(f'Successfully found {total} people.')
        return people
    print(f'Found {total} people; trying more specific prefixes.')

    # NetIds have 2-3 characters followed by any amount of numbers.
    MIN_CHARS_IN_PREFIX = 2
    MAX_CHARS_IN_PREFIX = 3
    if len(prefix) < MIN_CHARS_IN_PREFIX:
        choices = letters
    elif len(prefix) >= MAX_CHARS_IN_PREFIX or (len(prefix) != 0 and prefix[-1] not in letters):
        choices = numbers
    else:
        choices = characters

    res = []
    for choice in choices:
        res += read_directory(directory, prefix + choice)
    return res


@celery.task
def scrape(face_book_cookie, people_search_session_cookie, csrf_token):
    html = get_html(face_book_cookie)
    tree = get_tree(html)
    containers = get_containers(tree)

    if len(containers) == 0:
        print('No people were found on this page. There may be something wrong with authentication, aborting.')
        return

    directory = yaledirectory.API(people_search_session_cookie, csrf_token)
    watermark_mask = Image.open('app/res/watermark_mask.png')

    image_uploader = ImageUploader()
    print('Already hosting {} images.'.format(len(image_uploader.image_ids)))

    emails = {}
    people = []

    for container in containers:
        person = {}

        person['last_name'], person['first_name'] = clean_name(container.find('h5', {'class': 'yalehead'}).text)
        person['image_id'] = clean_image_id(container.find('img')['src'])

        if person['image_id']:
            if person['image_id'] in image_uploader.image_ids:
                person['image'] = image_uploader.get_image_url(person['image_id'])
            else:
                print('Image has not been processed yet.')
                image_r = requests.get('https://students.yale.edu/facebook/Photo?id=' + str(person['image_id']),
                                       headers={
                                           'Cookie': face_book_cookie,
                                       },
                                       stream=True)
                image_r.raw.decode_content = True
                try:
                    im = Image.open(image_r.raw)

                    # Paste mask over watermark
                    im.paste(watermark_mask, (0, 0), watermark_mask)

                    output = BytesIO()
                    im.save(output, format='JPEG', mode='RGB')

                    person['image'] = image_uploader.upload_image(person['image_id'], output)
                except OSError:
                    # "Cannot identify image" error
                    print('PIL could not identify image.')

        person['year'] = clean_year(container.find('div', {'class': 'student_year'}).text)
        pronoun = container.find('div', {'class': 'student_info_pronoun'}).text
        person['pronoun'] = pronoun if pronoun else None

        info = container.find_all('div', {'class': 'student_info'})

        person['college'] = info[0].text.replace(' College', '')
        try:
            person['email'] = info[1].find('a').text
        except AttributeError:
            pass
            #person.email = guess_email(person)
        trivia = info[1].find_all(text=True, recursive=False)
        try:
            room = trivia.pop(0) if RE_ROOM.match(trivia[0]) else None
            if room:
                person['residence'] = room
                result = RE_ROOM.search(room)
                person['building_code'], person['entryway'], person['floor'], person['suite'], person['room'] = result.groups()
            person['birthday'] = trivia.pop() if RE_BIRTHDAY.match(trivia[-1]) else None
            person['major'] = trivia.pop() if trivia[-1] in MAJORS else None
            if person['major'] and person['major'] in MAJOR_FULL_NAMES:
                person['major'] = MAJOR_FULL_NAMES[person['major']]
        except IndexError:
            pass

        new_trivia = []
        for r in range(len(trivia)):
            row = trivia[r].strip()
            if row.endswith(' /'):
                row = row.rstrip(' /')
                if RE_ACCESS_CODE.match(row):
                    person['access_code'] = row
                if RE_PHONE.match(row):
                    person['phone'] = row
                if len(new_trivia) == 1 and not person.get('residence'):
                    person['residence'] = new_trivia.pop(0)
            else:
                new_trivia.append(row)
        trivia = new_trivia

        # Handle first row of address being duplicated for residence
        if len(trivia) >= 2 and trivia[0] == trivia[1] and not person.get('residence'):
            person['residence'] = trivia.pop(0)

        person['address'] = '\n'.join(trivia)

        directory_entry = get_directory_entry(directory, person)
        if directory_entry is not None:
            person['netid'] = directory_entry.netid
            person['upi'] = directory_entry.upi
            if not person.get('email'):
                person['email'] = directory_entry.email
            if not person.get('year') and directory_entry.student_expected_graduation_year:
                person['year'] = int(directory_entry.student_expected_graduation_year)
                # This may not always be the case. But it's probably a safe bet.
                person['eli_whitney'] = True
            person = add_directory_to_person(person, directory_entry)
        else:
            print('Could not find directory entry.')

        if person.get('email'):
            emails[person['email']] = len(people)
        people.append(person)

    # Check leaves
    people = compare_years('pre2020', people, emails)
    people = compare_years('fall2020', people, emails)

    # Fetch non-undergrad users by iterating netids
    # Get set of netids for students we've already processed
    checked_netids = {person_dict.get('netid') for person_dict in people if 'netid' in person_dict}
    directory_entries = read_directory(directory)
    for entry in directory_entries:
        if entry.netid not in checked_netids:
            print('Parsing directory entry with NetID ' + entry.netid)
            checked_netids.add(entry.netid)
            person = add_directory_to_person({}, entry)
            people.append(person)

    # Store people into database
    Person.query.delete()
    for person_dict in people:
        db.session.add(Person(**{k: v for k, v in person_dict.items() if v}))
    db.session.commit()
    print('Done.')
