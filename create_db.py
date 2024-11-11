from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import hashlib
import random

Base = declarative_base()

class LadybirdDB(Base):
    __tablename__ = 'ladybirds'
    id = Column(String, primary_key=True)
    class_ = Column(String)

def create_database():
    engine = create_engine('sqlite:///test_1000.db')
    Base.metadata.create_all(engine)


create_database()
