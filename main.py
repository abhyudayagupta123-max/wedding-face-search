from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from collections import defaultdict
import csv
import os
import boto3
import zipfile
import tempfile


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

# -----------------------------
# NAME NORMALIZATION
# -----------------------------

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
    return ALIASES.get(person, person)


def display_label(person_id: str) -> str:
    if not person_id:
        return ""
    return NAME_MAP.get(person_id, person_id.replace("_", " ").title())


def normalize_people(raw_people: str):
    if not raw_people:
        return []
    people = []
    for item in raw_people.split(","):
        normalized = normalize_person(item)
        if normalized and normalized not in people:
            people.append(normalized)
    return people


# -----------------------------
# EVENT DETECTION
# -----------------------------

def get_event_from_key(key):
    k = key.lower()
    if "haldi" in k:
        return "Haldi"
    elif "sangeet" in k:
        return "Sangeet"
    elif "wedding" in k:
        return "Wedding"
    else:
        return "Other"


# -----------------------------
# S3 URL
# -----------------------------

def generate_presigned_url(photo_key: str, expires_in: int = 3600):
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": photo_key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return ""


# -----------------------------
# LOAD PEOPLE
# -----------------------------

def load_people_from_csv():
    people_set = set()

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)

        for row in reader:
            if len(row) <= 3:
                continue
            person = normalize_person(row[3])
            if person:
                people_set.add(person)

    ordered_people = [
        "sam", "vinay", "abhy", "mohini",
        "samsmummy", "samspapa",
        "vinaysmummy", "vinayspapa"
    ]

    final = []
    for p in ordered_people:
        if p in people_set:
            final.append({"id": p, "label": display_label(p)})

    extras = sorted([p for p in people_set if p not in ordered_people])
    for p in extras:
        final.append({"id": p, "label": display_label(p)})

    return final


# -----------------------------
# LOAD PHOTOS
# -----------------------------

def load_photos_from_csv():
    photo_matches = defaultdict(set)

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)

        for row in reader:
            if len(row) <= 3:
                continue

            photo_key = row[0].strip()
            person = normalize_person(row[3])

            if photo_key:
                if person:
                    photo_matches[photo_key].add(person)
                else:
                    photo_matches[photo_key]

    photos = []

    for photo_key, matched_people in photo_matches.items():
        image_url = generate_presigned_url(photo_key)

        photos.append({
            "photo_key": photo_key,
            "image_url": image_url,
            "thumbnail_url": image_url,
            "matched_people": sorted(list(matched_people)),
            "event": get_event_from_key(photo_key),  # ✅ ADDED
        })

    return photos


# -----------------------------
# ROUTES
# -----------------------------

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

    mode = mode.lower()
    selected_set = set(selected_people)

    filtered = []

    for photo in photos:
        matched = set(photo["matched_people"])

        if mode == "all":
            if selected_set.issubset(matched):
                filtered.append(photo)
        else:
            if selected_set.intersection(matched):
                filtered.append(photo)

    return filtered


# -----------------------------
# DOWNLOAD ZIP API
# -----------------------------

@app.post("/download-zip")
async def download_zip(request: Request):
    data = await request.json()
    photo_keys = data.get("photo_keys", [])

    if not photo_keys:
        return {"error": "No photos selected"}

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "photos.zip")

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for key in photo_keys:
            local_path = os.path.join(temp_dir, os.path.basename(key))

            try:
                s3_client.download_file(S3_BUCKET, key, local_path)
                zipf.write(local_path, os.path.basename(key))
            except Exception:
                continue

    return FileResponse(zip_path, filename="photos.zip")
