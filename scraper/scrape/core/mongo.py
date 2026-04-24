import os

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


def get_mongo_client():
    uri = f"mongodb+srv://{os.getenv('MONGODB_USERNAME')}:{os.getenv('MONGODB_DB_PASSWORD')}@{os.getenv('MONGODB_DB_NAME')}.kdnx4hj.mongodb.net/?retryWrites=true&w=majority&appName={os.getenv('MONGODB_DB_NAME')}"
    return MongoClient(uri, server_api=ServerApi("1"))
