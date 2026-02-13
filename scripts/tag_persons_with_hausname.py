# Tag all persons who have a custom Event of type "Hausname"

from gramps.gen.db import DbTxn
from gramps.gen.lib import Tag

EVENT_TYPE_NAME = "Hausname"
TAG_NAME = "HAS_HAUSNAME"

db = dbstate.db  # provided by GRAMPS runscript environment

def get_or_create_tag(name):
    for th in db.get_tag_handles():
        t = db.get_tag_from_handle(th)
        if t.get_name() == name:
            return th

    tag = Tag()
    tag.set_name(name)
    with DbTxn(f"Create tag {name}", db) as trans:
        db.add_tag(tag, trans)
    return tag.handle


tag_handle = get_or_create_tag(TAG_NAME)

total = 0
matched = 0
tagged = 0

with DbTxn("Tag persons with Hausname event", db) as trans:
    for ph in db.get_person_handles():
        person = db.get_person_from_handle(ph)
        total += 1

        has_hausname = False
        for evref in person.get_event_ref_list():
            ev = db.get_event_from_handle(evref.ref)
            if not ev:
                continue

            # This is the crucial line for your data:
            if str(ev.get_type()) == EVENT_TYPE_NAME:
                has_hausname = True
                break

        if not has_hausname:
            continue

        matched += 1
        if tag_handle not in person.get_tag_list():
            person.add_tag(tag_handle)
            db.commit_person(person, trans)
            tagged += 1

print("Done.")
print(f"Scanned persons: {total}")
print(f"Persons with Hausname event: {matched}")
print(f"Newly tagged: {tagged}")
