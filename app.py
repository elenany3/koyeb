from fastapi import FastAPI, WebSocket, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.middleware.cors import CORSMiddleware
from typing import List

# تعريف قاعدة البيانات ومكونات SQLAlchemy
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class QueueItem(Base):
    __tablename__ = "queue_items"
    id = Column(Integer, primary_key=True, index=True)
    value = Column(String, index=True)

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

active_connections: List[WebSocket] = []

async def broadcast_queue_count():
    db = next(get_db())
    queue_count = db.query(QueueItem).count()
    for connection in active_connections:
        await connection.send_json({"queue_count": queue_count})

@app.websocket("/ws/queue_status")
async def websocket_queue_status(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep the connection open
    except WebSocketDisconnect:
        active_connections.remove(websocket)

@app.post("/enqueue/")
async def enqueue(item_value: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    new_item = QueueItem(value=item_value)
    db.add(new_item)
    db.commit()
    background_tasks.add_task(broadcast_queue_count)
    return {"message": "Item added to the queue"}

@app.get("/dequeue/")
async def dequeue(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    item = db.query(QueueItem).first()
    if item:
        db.delete(item)
        db.commit()
        background_tasks.add_task(broadcast_queue_count)
        return {"value": item.value}
    raise HTTPException(status_code=404, detail="Queue is empty")

@app.delete("/clear/")
async def clear_queue(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db.query(QueueItem).delete()
    db.commit()
    background_tasks.add_task(broadcast_queue_count)
    return {"message": "Queue cleared"}


@app.get("/")
async def read_root():
    return {"message": "hello from api"}
