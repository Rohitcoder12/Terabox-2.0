# database.py
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# --- Load Environment Variables ---
# It's better to manage this in the main script, but for simplicity here:
from dotenv import load_dotenv
load_dotenv()
MONGO_URI = os.environ.get("MONGO_URI")

# --- Database Connection ---
try:
    # Create a new client and connect to the server
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    db = client.terabox_bot # Use a database named 'terabox_bot'
    users_collection = db.users # Use a collection named 'users'
    
    # Send a ping to confirm a successful connection
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")

except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # You might want to exit or handle this more gracefully in a real app
    client = None
    users_collection = None


def get_or_create_user(user_id):
    """Retrieve a user from the database or create a new one if they don't exist."""
    if users_collection is None: return None

    user = users_collection.find_one({"user_id": user_id})
    if user is None:
        new_user = {
            "user_id": user_id,
            "usage_count": 0,
            "is_premium": False
        }
        users_collection.insert_one(new_user)
        return new_user
    return user

def increment_usage(user_id):
    """Increment the usage count for a given user."""
    if users_collection is None: return
    
    # Use the $inc operator to atomically increment the count
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"usage_count": 1}}
    )

def set_premium_status(user_id, status: bool):
    """Set the premium status for a user. Creates the user if they don't exist."""
    if users_collection is None: return

    # Use upsert=True to create the document if it doesn't exist
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": status}},
        upsert=True
    )