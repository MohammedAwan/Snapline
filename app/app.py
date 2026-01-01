from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from app.schemas import PostCreate, PostResponse, UserCreate, UserRead, UserUpdate
from app.db import Post, create_db_and_tables, get_async_session, User
from sqlalchemy.ext.asyncio import AsyncSession       # Async session to create db(if not exsits) as soon as the app starts 
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import shutil
import os
import uuid
import tempfile
from app.users import auth_backend, current_active_user, fastapi_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield
        
app = FastAPI(lifespan = lifespan) # Initializing FASTAPI

app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix = '/auth', tags=['auth'])
app.include_router(fastapi_users.get_verify_router(UserRead), prefix = "/auth", tags=['auth'])
app.include_router(fastapi_users.get_reset_password_router(), prefix = "/auth", tags=['auth'])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix = "/users", tags = ['users'])
'''
#First End point of our API
@app.get("/hello_world")
def hello_world():
    return {"message" : "Hello World"}
'''

''' # Commenting the basic code and writing clean and modular code
text_posts = { 
    1 :{'Title' : 'Cool first post', 'content': 'Such a nice feeling to develop an API'},
    2 :{'Title' : 'Learning Python', 'content': 'Python makes backend development simple and enjoyable'},
    3 :{'Title' : 'API Basics', 'content': 'Understanding REST APIs is essential for modern applications'},
    4 :{'Title' : 'Debugging Day', 'content': 'Fixed a tricky bug after hours of debugging'},
    5 :{'Title' : 'FastAPI Fun', 'content': 'FastAPI makes building APIs fast and clean'},
    6 :{'Title' : 'Database Thoughts', 'content': 'Designing schemas properly saves a lot of time later'},
    7 :{'Title' : 'Error Handling', 'content': 'Good error messages improve developer experience'},
    8 :{'Title' : 'Testing APIs', 'content': 'Writing tests gives confidence before deployment'},
    9 :{'Title' : 'Deployment Wins', 'content': 'Successfully deployed my first backend service'},
    10 :{'Title' : 'Continuous Learning', 'content': 'Every project teaches something new'}
    }

@app.get("/posts")
def get_all_posts(limit : int = None):
    if limit :
        return list(text_posts.values())[:limit]   # returning only limited number of values
    return text_posts

# To get individual posts using id
@app.get("/posts/{id}") # using parameter in endpoint
def get_post(id:int):
    if id not in text_posts:
        raise HTTPException(status_code=404, detail = "Post not found") # raising exception
    return text_posts[id]

# POST method to get new posts
@app.post("/posts")
def create_posts(post : PostCreate) -> PostResponse:        #PostCreate and PostResponse are pydantic models
    new_post = {"Title" : post.title, "content": post.content}
    text_posts[max(text_posts.keys()) + 1] = new_post
    return new_post    
'''

'''
must use async for evry function, and use await whenever querying db 
'''
@app.post("/upload")
async def upload_file(
        file : UploadFile = File(...),
        caption : str = Form(""),
        user : User = Depends(current_active_user),         # forcing the function to get current active user inorder to protect endpoints  
        session : AsyncSession = Depends(get_async_session)
    ):
    temp_file_path = None
    
    try:
        with tempfile.NamedTemporaryFile(delete = False, suffix = os.path.splitext(file.filename)[1]) as temp_file:    # creating a temp file with same suffix as orignal eg. png
            temp_file_path = temp_file.name
            shutil.copyfileobj(file.file, temp_file)
        
        upload_result = imagekit.upload_file(
            file = open(temp_file_path, "rb"),
            file_name = file.filename,
            options = UploadFileRequestOptions(
                use_unique_file_name = True,
                tags = ["backend-upload"]
            )
        )
        
        if upload_result.response_metadata.http_status_code == 200:    # if upload successfull
            post = Post(
                user_id = user.id,
                caption =caption,
                url = upload_result.url,
                file_type = "video" if file.content_type.startswith('video/') else "image",
                file_name = upload_result.name
            )
            session.add(post)
            await session.commit()
            await session.refresh(post)
            return post
        
    except Exception as e:
        print("file upload failed", e)
        raise HTTPException(status_code= 500, detail=str(e))
    
    finally:
        if temp_file_path and os.path.exists(temp_file_path):    # CLeaning up the temp file
            os.unlink(temp_file_path)
        file.file.close()

@app.get("/feed")
async def get_feed(
    session : AsyncSession = Depends(get_async_session),
    user : User = Depends(current_active_user)
):
    
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))   # Querying the database
    posts = [row[0] for row in result.all()]
    
    result = await session.execute(select(User))
    users = [row[0] for row in result.all()]
    user_dict = {u.id : u.email for u in users}
    print(user_dict)

    
    posts_data = []
    for post in posts:
        posts_data.append(
            {
                "id" : str(post.id),
                "user_id" : str(post.user_id),
                "caption": post.caption,
                "url" : post.url,
                "file_type" : post.file_type,
                "file_name" : post.file_name,
                "created_at" : post.created_at.isoformat(),
                "is_owner" : post.user_id == user.id,
                "email": user_dict.get(post.user_id, "Unknown")
            }
        )
    return {"posts" : posts_data}

# To delete a post
@app.delete("/posts/{post_id}")
async def delete_post(post_id : str, session :AsyncSession = Depends(get_async_session),user : User = Depends(current_active_user)):
    try:
        post_uuid = uuid.UUID(post_id)
        result = await session.execute(select(Post).where(Post.id == post_uuid))
        post = result.scalars().first()                                         #Getting the uuid of the post
        
        if not post:
            raise HTTPException(status_code=404, detail = "Post not found")
        
        if post.user_id != user.id:                                             # checking if the post is created by the delete requestor
            raise HTTPException(status_code=403, detail="You dont have permission to delete this post")
        
        await session.delete(post)                                              # deleting the post
        await session.commit()
        
        return {"success" : True, "messsage": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500 , detail= str(e))