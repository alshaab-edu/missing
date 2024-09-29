from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from databases import Database
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer
import os
import random
import uuid
import cv2
import numpy as np
app = FastAPI()

# إعداد قاعدة البيانات SQLite
DATABASE_URL = "sqlite:///./data.db"
database = Database(DATABASE_URL)
metadata = MetaData()

# تعريف جدول المستخدمين مع عمود `code`
users_table = Table(
    "users",
    metadata,
    Column("phone", String, primary_key=True),
    Column("name", String),
    Column("code", Integer)
)

# تعريف جدول `posts` لتخزين بيانات المستخدم والصورة
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

# إعداد محرك قاعدة البيانات
engine = create_engine(DATABASE_URL, echo=True, future=True)

# إنشاء الجداول في قاعدة البيانات
metadata.create_all(bind=engine)

# إنشاء مجلد لحفظ الصور إذا لم يكن موجودًا
if not os.path.exists("uploads_img"):
    os.makedirs("uploads_img")

# قاموس لتخزين الأكواد (غير مناسب للإنتاج)
codes = {}

class PhoneNumber(BaseModel):
    phone: str
    name: str

class VerificationCode(BaseModel):
    phone: str
    code: str

@app.on_event("startup")
async def startup():
    # إنشاء اتصال بقاعدة البيانات عند بدء تشغيل التطبيق
    await database.connect()
    print("Database connected")

@app.on_event("shutdown")
async def shutdown():
    # إغلاق اتصال قاعدة البيانات عند إيقاف تشغيل التطبيق
    await database.disconnect()
    print("Database disconnected")

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
    
    try:
        if int(verification.code) == stored_code:
            return {"message": "تم التحقق من الكود بنجاح"}
        else:
            raise HTTPException(status_code=400, detail="كود غير صحيح")
    except ValueError:
        raise HTTPException(status_code=400, detail="يجب أن يكون الكود رقماً")



@app.post("/user_post")
async def user_post(
    first_name: str = Form(...),
    second_name: str = Form(...),
    third_name: str = Form(...),
    phone: str = Form(...),
    file: UploadFile = File(...),
):
    # توليد اسم عشوائي للملف المعالج
    unique_id = uuid.uuid4().hex
    image_name = f"{unique_id}.jpg"
    output_path = os.path.join("uploads_img", f"{image_name}")

    # قراءة الملف المرفوع
    file_content = await file.read()

    # معالجة الصورة
    # تحميل الصورة من محتوى الملف
    image = cv2.imdecode(np.frombuffer(file_content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("الصورة لم تُحمل بنجاح. تحقق من الملف.")

    # تحويل الصورة إلى تدرجات الرمادي
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # تحميل مصنف الوجه
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        raise RuntimeError("مصنف الوجه لم يُحمّل بنجاح. تحقق من المسار.")

    # تحديد الوجوه في الصورة
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    if len(faces) == 0:
        print("لم يتم العثور على أي وجوه في الصورة.")
        # إذا لم يتم العثور على وجوه، استخدم نسبة تغويش أقل للصورة بالكامل
        blur_kernel = (15, 15)  # تقليل حجم النواة للتغويش
    else:
        # تغويش الصورة حول الوجوه
        blur_kernel = (25, 25)  # حجم النواة للتغويش في حالة وجود وجوه

    # تغويش الصورة بالكامل
    blurred_image = cv2.GaussianBlur(image, blur_kernel, 0)

    # زيادة حجم الإطار حول الوجه
    padding = 20

    # دمج الوجه الأصلي مع الصورة المغوشة في حالة وجود وجوه
    if len(faces) > 0:
        for (x, y, w, h) in faces:
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(image.shape[1], x + w + padding)
            y2 = min(image.shape[0], y + h + padding)
            blurred_image[y1:y2, x1:x2] = image[y1:y2, x1:x2]

    # حفظ الصورة النهائية
    cv2.imwrite(output_path, blurred_image)
    print(f"تم حفظ الصورة النهائية في: {output_path}")

    # إدخال بيانات المنشور إلى قاعدة البيانات
    query = posts_table.insert().values(
        first_name=first_name,
        second_name=second_name,
        third_name=third_name,
        phone=phone,
        image_name=image_name
    )

    await database.execute(query)
    return {"message": "تم رفع المنشور بنجاح"}











# @app.post("/user_post")
# async def user_post(
#     first_name: str = Form(...),
#     second_name: str = Form(...),
#     third_name: str = Form(...),
#     phone: str = Form(...),
#     file: UploadFile = File(...),
# ):
#     image_name = file.filename
#     image_path = os.path.join("uploads", image_name)

#     # التأكد من أن اسم الصورة يتم تعيينه بشكل صحيح وبالترميز المناسب
#     with open(image_path, "wb") as image_file:
#         image_file.write(file.file.read())

#     query = posts_table.insert().values(
#         first_name=first_name,
#         second_name=second_name,
#         third_name=third_name,
#         phone=phone,
#         image_name=image_name
#     )

#     await database.execute(query)
#     return {"message": "تم رفع المنشور بنجاح"}

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
            "phone": post["phone"],
            "image_name": post["image_name"]
        })
    
    return {"posts": result}

app.mount("/uploads_img", StaticFiles(directory="uploads_img"), name="uploads_img")
