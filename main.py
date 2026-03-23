from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import csv
from collections import defaultdict
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

s3_client = boto3.client("s3", region_name=AWS_REGION)

# =========================
# NAME CLEANUP / DISPLAY MAP
# =========================
NAME_MAP = {
    "sam": "Sam",
    "vinay": "Vinay",
    "abhy": "Abhy",
    "mohini": "Mohini",
    "samsmummy": "Sam's Mom",
    "samspapa": "Sam's Dad",
    "vinaysmom": "Vinay's Mom",
    "vinaysdad": "Vinay's Dad",
}

# optional aliases from CSV
ALIASES = {
    "sam_v2": "sam",
    "vinay_v2": "vinay",
    "abhy_v2": "abhy",
    "mohini_v2": "mohini",
    "matched_user_id": None,
    "": None,
}


# =========================
# HELPERS
# =========================
def normalize_person(raw_person: str):
    raw_person = raw_person.strip().lower()

    if raw_person in ALIASES:
        return ALIASES[raw_person]

    cleaned = raw_person.replace("_v2", "")
    cleaned = cleaned.strip()

    if not cleaned or cleaned == "matched_user_id":
        return None

    return cleaned


def display_label(person_id: str):
    if person_id in NAME_MAP:
        return NAME_MAP[person_id]
    return person_id.replace("_", " ").title()


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
        next(reader, None)  # skip header

        for row in reader:
            if len(row) < 4:
                continue

            person_id = normalize_person(row[3])
            if person_id:
                people_set.add(person_id)

    people_list = [
        {"id": p, "label": display_label(p)}
        for p in sorted(people_set, key=lambda x: display_label(x).lower())
    ]
    return people_list


def load_photos_from_csv():
    """
    Expected CSV row format:
    0 = photo_key
    1 = face index
    2 = person label maybe duplicate
    3 = person id / matched person
    """
    grouped = defaultdict(set)

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header

        for row in reader:
            if len(row) < 4:
                continue

            photo_key = row[0].strip()
            person_id = normalize_person(row[3])

            if not photo_key:
                continue

            if person_id:
                grouped[photo_key].add(person_id)

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
