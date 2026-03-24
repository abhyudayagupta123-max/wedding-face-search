from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import csv
import os
import boto3


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "all_people_matches_master.csv"
S3_BUCKET = "wedding-pictures-sam-vinay"
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

s3_client = boto3.client("s3", region_name=AWS_REGION)

NAME_MAP = {
    "sam": "Sam",
    "vinay": "Vinay",
    "abhy": "Abhy",
    "mohini": "Mohini",
    "samsmummy": "Sam's Mom",
    "samspapa": "Sam's Dad",
    "vinaysmummy": "Vinay's Mom",
    "vinayspapa": "Vinay's Dad",
}

ALIASES = {
    "sam_v2": "sam",
    "sam": "sam",
    "vinay_v2": "vinay",
    "vinay": "vinay",
    "abhy_v2": "abhy",
    "abhy": "abhy",
    "mohini_v2": "mohini",
    "mohini": "mohini",
    "samsmummy": "samsmummy",
    "samspapa": "samspapa",
    "vinaysmummy": "vinaysmummy",
    "vinayspapa": "vinayspapa",
    "matched_user_id": None,
    "": None,
}


def normalize_person(raw_person: str):
    if raw_person is None:
        return None

    person = str(raw_person).strip().lower()
    if not person:
        return None

    if person in ALIASES:
        return ALIASES[person]

    return person


def display_label(person_id: str) -> str:
    if not person_id:
        return ""

    if person_id in NAME_MAP:
        return NAME_MAP[person_id]

    return person_id.replace("_", " ").title()


def normalize_people(raw_people: str):
    if not raw_people:
        return []

    people = []
    for item in raw_people.split(","):
        normalized = normalize_person(item)
        if normalized and normalized not in people:
            people.append(normalized)

    return people


def generate_presigned_url(photo_key: str, expires_in: int = 3600) -> str:
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": photo_key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return ""


def load_people_from_csv():
    people_set = set()

    with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header row

        for row in reader:
            if not row or len(row) <= 3:
                continue

            person = normalize_person(row[3])
            if person:
                people_set.add(person)

    # force-add canonical people that must appear cleanly
    people_set.add("vinay")

    ordered_people = [
        "sam",
        "vinay",
        "abhy",
        "mohini",
        "samsmummy",
        "samspapa",
        "vinaysmummy",
        "vinayspapa",
    ]

    final_people = []
    for person_id in ordered_people:
        if person_id in people_set:
            final_people.append(
                {
                    "id": person_id,
                    "label": display_label(person_id),
                }
            )

    # include any extra normalized people from CSV after known names
    extras = sorted([p for p in people_set if p not in ordered_people])
    for person_id in extras:
        final_people.append(
            {
                "id": person_id,
                "label": display_label(person_id),
            }
        )

    return final_people


def load_photos_from_csv():
    photo_matches = defaultdict(set)

    with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header row

        for row in reader:
            if not row or len(row) <= 3:
                continue

            photo_key = str(row[0]).strip()
            person = normalize_person(row[3])

            if not photo_key:
                continue

            if person:
                photo_matches[photo_key].add(person)
            else:
                photo_matches[photo_key] = photo_matches[photo_key]

    photos = []
    for photo_key, matched_people in photo_matches.items():
        image_url = generate_presigned_url(photo_key)
        thumbnail_url = image_url

        photos.append(
            {
                "photo_key": photo_key,
                "image_url": image_url,
                "thumbnail_url": thumbnail_url,
                "matched_people": sorted(list(matched_people)),
            }
        )

    return photos


@app.get("/")
def root():
    return {"message": "API is running 🚀"}


@app.get("/api/people")
def get_people():
    return load_people_from_csv()


@app.get("/api/search")
def search_photos(
    people: str = Query(default=""),
    mode: str = Query(default="all"),
):
    selected_people = normalize_people(people)
    photos = load_photos_from_csv()

    if not selected_people:
        return photos

    mode = (mode or "all").strip().lower()
    if mode not in {"all", "any"}:
        mode = "all"

    filtered = []
    selected_set = set(selected_people)

    for photo in photos:
        matched_set = set(photo["matched_people"])

        if mode == "all":
            if selected_set.issubset(matched_set):
                filtered.append(photo)
        else:  # mode == "any"
            if selected_set.intersection(matched_set):
                filtered.append(photo)

    return filtered
