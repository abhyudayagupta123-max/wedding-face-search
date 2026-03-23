from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API is running 🚀"}

# Allow frontend (Lovable) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for now keep open
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# GET PEOPLE LIST
# -----------------------------
@app.get("/api/people")
def get_people():
    return [
        {"id": "sam", "label": "Sam"},
        {"id": "vinay", "label": "Vinay"},
        {"id": "abhy", "label": "Abhy"},
        {"id": "mohini", "label": "Mohini"}
    ]


# -----------------------------
# SEARCH PHOTOS (DUMMY DATA)
# -----------------------------
@app.get("/api/search")
def search_photos(people: str = "", mode: str = "all"):
    
    # Dummy dataset
    photos = [
        {
            "photo_key": "img1.jpg",
            "image_url": "https://via.placeholder.com/600",
            "thumbnail_url": "https://via.placeholder.com/150",
            "matched_people": ["sam", "vinay"]
        },
        {
            "photo_key": "img2.jpg",
            "image_url": "https://via.placeholder.com/600",
            "thumbnail_url": "https://via.placeholder.com/150",
            "matched_people": ["abhy"]
        },
        {
            "photo_key": "img3.jpg",
            "image_url": "https://via.placeholder.com/600",
            "thumbnail_url": "https://via.placeholder.com/150",
            "matched_people": []
        }
    ]

    # If no people selected → return all photos
    if not people:
        return {
            "count": len(photos),
            "results": photos
        }

    # Convert query string to list
    selected_people = people.split(",")

    filtered = []

    for photo in photos:
        if mode == "all":
            if all(p in photo["matched_people"] for p in selected_people):
                filtered.append(photo)
        else:  # mode == "any"
            if any(p in photo["matched_people"] for p in selected_people):
                filtered.append(photo)

    return {
        "count": len(filtered),
        "results": filtered
    }
