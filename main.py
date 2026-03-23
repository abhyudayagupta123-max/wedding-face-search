    from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import csv
import os
from collections import defaultdict
from urllib.parse import unquote

import boto3


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================
CSV_FILE = "all_people_matches_master.csv"
S3_BUCKET = "wedding-pictures-sam-vinay"
AWS_REGION = "ap-south-1"

# Render will use IAM/env if available.
# Locally, boto3 will use your configured AWS credentials.
s3_client = boto3.client("s3", region_name=AWS_REGION)


# =========================
# HELPERS
# =========================
def generate_presigned_url(photo_key: str, expires_in: int = 3600) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": photo_key},
        ExpiresIn=expires_in,
    )


def normalize_people(raw_people: str):
    if not raw_people:
        return []
    return [p.strip().lower() for p in raw_people.split(",") if p.strip()]


def load_people_from_csv():
    people_set = set()

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue

            matched_person = row[3].strip().lower()
            if matched_person:
                people_set.add(matched_person)

    people_list = [{"id": p, "label": p.capitalize()} for p in sorted(people_set)]
    return people_list


def load_photos_from_csv():
    """
    Expected CSV row format (based on your file):
    0 = photo_key
    1 = face index
    2 = person label maybe duplicate
    3 = person id / matched person
    ... rest scores
    """
    grouped = defaultdict(set)

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue

            photo_key = row[0].strip()
            person_id = row[3].strip().lower()

            if not photo_key:
                continue

            if person_id:
                grouped[photo_key].add(person_id)

            # If row exists with empty person match, still keep photo
            if photo_key not in grouped:
                grouped[photo_key] = set()

    photos = []
    for photo_key, matched_people in grouped.items():
        try:
            image_url = generate_presigned_url(photo_key)
            thumbnail_url = image_url
        except Exception:
            image_url = ""
            thumbnail_url = ""

        photos.append(
            {
                "photo_key": photo_key,
                "image_url": image_url,
                "thumbnail_url": thumbnail_url,
                "matched_people": sorted(list(matched_people)),
            }
        )

    return photos


# =========================
# ROUTES
# =========================
@app.get("/")
def home():
    return {"message": "API is running 🚀"}


@app.get("/api/people")
def get_people():
    return load_people_from_csv()


@app.get("/api/search")
def search_photos(people: str = "", mode: str = "all"):
    selected_people = normalize_people(people)
    all_photos = load_photos_from_csv()

    if not selected_people:
        return {
            "count": len(all_photos),
            "results": all_photos,
        }

    results = []
    selected_set = set(selected_people)

    for photo in all_photos:
        matched_set = set(photo["matched_people"])

        if mode == "any":
            if matched_set.intersection(selected_set):
                results.append(photo)
        else:
            if selected_set.issubset(matched_set):
                results.append(photo)

    return {
        "count": len(results),
        "results": results,
    }
