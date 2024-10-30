from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, constr
from databases import Database
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer
import os
import random
import uuid
import cv2
import numpy as np

app = FastAPI()

DATABASE_URL = "sqlite:///./data.db"
database = Database(DATABASE_URL)
metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("phone", String, primary_key=True),
    Column("name", String),
    Column("code", Integer)
)

posts_table = Table(
    "posts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("first_name", String),
    Column("second_name", String),
    Column("third_name", String),
    Column("phone", String),
    Column("image_name", String)
)

engine = create_engine(DATABASE_URL, echo=True, future=True)
metadata.create_all(bind=engine)

if not os.path.exists("uploads_img"):
    os.makedirs("uploads_img")

codes = {}

class PhoneNumber(BaseModel):
    phone: str
    name: str

class VerificationCode(BaseModel):
    phone: str
    code: str

@app.post("/send_code")
async def send_code(phone_number: PhoneNumber):
    code = random.randint(1000, 9999)
    codes[phone_number.phone] = code

    query = users_table.select().where(users_table.c.phone == phone_number.phone)
    existing_user = await database.fetch_one(query)

    if existing_user:
        query = users_table.update().where(users_table.c.phone == phone_number.phone).values(code=code, name=phone_number.name)
    else:
        query = users_table.insert().values(phone=phone_number.phone, name=phone_number.name, code=code)

    await database.execute(query)
    print(f"Sending code {code} to {phone_number.phone}")
    return {"message": "كود التحقق تم إرساله"}

@app.post("/verify_code")
async def verify_code(verification: VerificationCode):
    query = users_table.select().where(users_table.c.phone == verification.phone)
    user = await database.fetch_one(query)

    if user is None:
        raise HTTPException(status_code=404, detail="رقم الهاتف غير موجود")

    stored_code = user['code']
    if int(verification.code) == stored_code:
        return {"message": "تم التحقق من الكود بنجاح"}
    else:
        raise HTTPException(status_code=400, detail="كود غير صحيح")

@app.post("/user_post")
async def user_post(
    first_name: str = Form(...),
    second_name: str = Form(...),
    third_name: str = Form(...),
    phone: str = Form(...),
    file: UploadFile = File(...),
):
    unique_id = uuid.uuid4().hex
    image_name = f"{unique_id}.jpg"
    output_path = os.path.join("uploads_img", image_name)

    file_content = await file.read()
    image = cv2.imdecode(np.frombuffer(file_content, np.uint8), cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("الصورة لم تُحمل بنجاح. تحقق من الملف.")

    # معالجة الصورة هنا (تغويش أو غيره)

    cv2.imwrite(output_path, image)
    print(f"تم حفظ الصورة النهائية في: {output_path}")

    query = posts_table.insert().values(
        first_name=first_name,
        second_name=second_name,
        third_name=third_name,
        phone=phone,
        image_name=image_name
    )

    await database.execute(query)
    return {"message": "تم رفع المنشور بنجاح"}

@app.get("/posts")
async def get_all_posts():
    query = posts_table.select()
    posts = await database.fetch_all(query)

    if not posts:
        raise HTTPException(status_code=404, detail="لا توجد منشورات")

    result = []
    for post in posts:
        result.append({
            "id": post["id"],
            "first_name": post["first_name"],
            "second_name": post["second_name"],
            "third_name": post["third_name"],
            # لا نعيد رقم الهاتف
            "image_name": post["image_name"]
        })

    return {"posts": result}

app.mount("/uploads_img", StaticFiles(directory="uploads_img"), name="uploads_img")
