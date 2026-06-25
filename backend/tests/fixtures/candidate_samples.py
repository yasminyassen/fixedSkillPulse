"""Reference candidate code samples for scoring calibration tests."""

EXCELLENT_API = '''
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/books", tags=["books"])


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1000, le=2100)


class Book(BookCreate):
    id: int


class BookRepository:
    def __init__(self) -> None:
        self._items: dict[int, Book] = {}
        self._next_id = 1

    def create(self, payload: BookCreate) -> Book:
        book = Book(id=self._next_id, **payload.model_dump())
        self._items[self._next_id] = book
        self._next_id += 1
        return book

    def get(self, book_id: int) -> Book:
        book = self._items.get(book_id)
        if book is None:
            raise KeyError(book_id)
        return book

    def list_all(self) -> list[Book]:
        return list(self._items.values())

    def delete(self, book_id: int) -> None:
        if book_id not in self._items:
            raise KeyError(book_id)
        del self._items[book_id]


def get_repository() -> BookRepository:
    return BookRepository()


@router.post("", response_model=Book, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, repo: BookRepository = Depends(get_repository)) -> Book:
    return repo.create(payload)


@router.get("/{book_id}", response_model=Book)
def get_book(book_id: int, repo: BookRepository = Depends(get_repository)) -> Book:
    try:
        return repo.get(book_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Book not found") from exc
'''

GOOD_API = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Book Inventory API")


class BookCreate(BaseModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    year: int = Field(ge=1000, le=2100)


class Book(BookCreate):
    id: int


books: dict[int, Book] = {}
next_book_id = 1


@app.post("/books", response_model=Book)
def create_book(payload: BookCreate) -> Book:
    global next_book_id
    book = Book(id=next_book_id, **payload.model_dump())
    books[next_book_id] = book
    next_book_id += 1
    return book


@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int) -> Book:
    book = books.get(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
'''

AVERAGE_API = '''
from fastapi import FastAPI

app = FastAPI()
books = []
next_id = 1


@app.post("/books")
def create_book(title, author, year):
    global next_id
    book = {"id": next_id, "title": title, "author": author, "year": year}
    books.append(book)
    next_id += 1
    return book


@app.get("/books/{book_id}")
def get_book(book_id: int):
    for book in books:
        if book["id"] == book_id:
            return book
    return None
'''

WEAK_API = '''
from fastapi import FastAPI

app = FastAPI()
books = []
counter = 0


@app.post("/books")
def create_book(book: dict):
    global counter
    counter += 1
    book["id"] = counter
    books.append(book)
    return book


@app.get("/books/{book_id}")
def get_book(book_id):
    for book in books:
        if book["id"] == book_id:
            return book
    return {"error": "not found"}
'''

POOR_API = '''
from fastapi import FastAPI

app = FastAPI()
SECRET_KEY = "super-secret-api-key-123"
books = []
counter = 0


@app.post("/books")
def create_book(book: dict):
    global counter
    counter += 1
    book["id"] = counter
    books.append(book)
    return book


@app.get("/books/{book_id}")
def get_book(book_id: int):
    for book in books:
        if book["id"] == book_id:
            return book
    return {"error": "not found"}


@app.get("/debug/eval")
def debug_eval(expression: str):
    return {"result": eval(expression)}
'''

CANDIDATE_LEVELS = {
    "excellent": EXCELLENT_API,
    "good": GOOD_API,
    "average": AVERAGE_API,
    "weak": WEAK_API,
    "poor": POOR_API,
}
