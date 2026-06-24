from fastapi import FastAPI

app = FastAPI(title="GnuCash Web")


@app.get("/")
def root():
    return {"message": "Hello, World!"}
